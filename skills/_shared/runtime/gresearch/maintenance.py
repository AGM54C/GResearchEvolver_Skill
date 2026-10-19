"""Quiescent full-store backup and verified restore into a new directory."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid

from .core import ResearchError, Store, atomic_bytes, digest, fingerprint, native_path, read_json, safe_path, valid_id, write_json, sync_directory
from .locking import resource_lock


def backup(store, destination):
    destination = native_path(destination)
    if destination.exists() or destination == store.root or store.root in destination.parents:
        raise ResearchError('Backup destination must be new and outside the source store')
    temporary = destination.with_name(destination.name + '.pending-' + uuid.uuid4().hex[:8])
    with ExitStack() as locks:
        locks.enter_context(resource_lock(store, 'maintenance', 'backup'))
        with store.tx():
            runs = [r['id'] for r in store.db.execute('SELECT id FROM runs ORDER BY id')]
            for run in runs:
                locks.enter_context(resource_lock(store, 'run', run))
                _, state = store.get(run)
                if state.get('worker') or any(s.get('active_attempt') or s.get('cleanup_pending') for s in state['stages'].values()):
                    raise ResearchError('Recover outstanding workers before backup')
            if any(q['status'] == 'running' for q in store.get_value('queue', [])):
                raise ResearchError('Recover running queue entries before backup')
            for row in store.db.execute("SELECT value FROM values_store WHERE key LIKE 'rsi:%'"):
                epoch = json.loads(row[0])
                locks.enter_context(resource_lock(store, 'rsi', epoch['name']))
                if epoch.get('running'):
                    raise ResearchError('Recover outstanding RSI trials before backup')
            checked = store.verify()
            if not checked['valid']:
                raise ResearchError('Source store integrity failed')
            temporary.mkdir(parents=True)
            # Use a separate reader: backup on the connection holding an active
            # write transaction can deadlock. BEGIN IMMEDIATE prevents new commits.
            reader = sqlite3.connect(store.root / 'state.sqlite3')
            target = sqlite3.connect(temporary / 'state.sqlite3')
            try: reader.backup(target)
            finally:
                target.close()
                reader.close()
            atomic_bytes(temporary / 'state.sqlite3', (temporary / 'state.sqlite3').read_bytes())
            files = {'state.sqlite3': digest((temporary / 'state.sqlite3').read_bytes())}
            for obj in store.objects.iterdir():
                name = 'objects/' + obj.name
                data = store.blob(obj.name)
                atomic_bytes(temporary / name, data)
                files[name] = digest(data)
            for managed in (store.root / 'runs', store.root / 'rsi'):
                for path in managed.rglob('*'):
                    if path.is_symlink() or (getattr(path.lstat(), 'st_file_attributes', 0) & 0x400):
                        raise ResearchError('Backup refuses symlinks/reparse points')
                    if path.is_file():
                        name = path.relative_to(store.root).as_posix()
                        data = path.read_bytes()
                        atomic_bytes(safe_path(temporary, name), data)
                        files[name] = digest(data)
            manifest = {'version': 1, 'files': files, 'runs': runs, 'scope': 'local store, graph revisions, CAS and workspaces; no external service state'}
            write_json(temporary / 'backup.json', manifest)
            atomic_bytes(temporary / '.done', fingerprint(manifest).encode())
            os.replace(temporary, destination)
            sync_directory(destination.parent)
    return {'backup': str(destination), 'sha256': fingerprint(manifest), 'files': len(files)}


def backup_manifest(directory):
    manifest = read_json(directory / 'backup.json')
    if (not isinstance(manifest, dict) or manifest.get('version') != 1
            or not isinstance(manifest.get('files'), dict) or not isinstance(manifest.get('runs'), list)):
        raise ResearchError('Invalid backup manifest')
    for name, expected in manifest['files'].items():
        safe_path(directory, name)
        if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ResearchError('Invalid backup file digest')
    for run in manifest['runs']:
        valid_id(run)
    if len(set(manifest['runs'])) != len(manifest['runs']):
        raise ResearchError('Duplicate backup run ID')
    return manifest


def verify_backup(directory):
    directory = native_path(directory)
    manifest = backup_manifest(directory)
    errors = []
    if manifest.get('version') != 1 or (directory / '.done').read_text() != fingerprint(manifest):
        errors.append('backup_manifest')
    for name, expected in manifest['files'].items():
        path = safe_path(directory, name)
        if not path.is_file() or digest(path.read_bytes()) != expected:
            errors.append(name)
    if 'state.sqlite3' not in manifest['files']:
        errors.append('missing database')
    return {'valid': not errors, 'errors': errors, 'sha256': fingerprint(manifest)}


def restore_backup(directory, destination):
    checked = verify_backup(directory)
    if not checked['valid']:
        raise ResearchError('Backup verification failed')
    destination = native_path(destination)
    if destination.exists():
        raise ResearchError('Restore destination must not exist')
    directory = native_path(directory)
    temporary = destination.with_name(destination.name + '.pending-' + uuid.uuid4().hex[:8])
    manifest = backup_manifest(directory)
    if fingerprint(manifest) != checked['sha256']:
        raise ResearchError('Backup manifest changed during restore')
    temporary.mkdir(parents=True)
    for name, expected in manifest['files'].items():
        data = safe_path(directory, name).read_bytes()
        if digest(data) != expected:
            raise ResearchError('Backup changed during restore')
        atomic_bytes(safe_path(temporary, name), data)
    for run in manifest['runs']:
        (temporary / 'runs' / run / 'work').mkdir(parents=True, exist_ok=True)
    restored = Store(temporary)
    try:
        if not restored.verify()['valid']:
            raise ResearchError('Restored store integrity failed')
    finally:
        restored.close()
    os.replace(temporary, destination)
    sync_directory(destination.parent)
    return {'store': str(destination), 'verified': True, 'backup_sha256': checked['sha256']}


def health(store):
    integrity = store.verify()
    runs = [dict(r) for r in store.db.execute('SELECT id,state FROM runs')]
    pending = []
    for row in runs:
        state = json.loads(row['state'])
        if state.get('worker') or any(s.get('active_attempt') or s.get('cleanup_pending') for s in state['stages'].values()):
            pending.append({'run': row['id'], 'worker': state.get('worker'), 'heartbeat': state.get('heartbeat')})
    return {'integrity': integrity, 'journal_mode': store.db.execute('PRAGMA journal_mode').fetchone()[0],
            'synchronous': store.db.execute('PRAGMA synchronous').fetchone()[0], 'workers_or_recovery': pending,
            'pending_memory_sync': [json.loads(r[0]) for r in store.db.execute('SELECT body FROM memory_outbox') if json.loads(r[0])['status'] != 'synced'],
            'deployment_scope': 'single host, local filesystem, cooperative trusted workers; no distributed lock or availability SLA'}
