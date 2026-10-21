"""Synchronize a pinned Git snapshot between the Agent and Skill products.

Only the owning repository is edited. Consumers commit generated snapshots so
clones, source ZIPs and host installations work offline without submodules.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORIES = {
    'runtime': 'AGM54C/GResearchEvolver_Agent',
    'skills': 'AGM54C/GResearchEvolver_Skill',
}
ENGINE_DIRS = ('skills/_shared/runtime/', 'skills/_shared/vendor/', 'tests/',
               'docs/agent-upgrade/', 'docs/long-horizon/')
ENGINE_FILES = {'launch_agent.py', 'build_agent.py', 'tools/bundle_sync.py',
                'skills/_shared/THIRD_PARTY.md', 'skills/_shared/agent-workbench.md',
                'skills/_shared/long-horizon-guide.md', 'skills/_shared/examples/agent-session.json'}
SKILL_FILES = {'install.py', 'install.sh', 'INSTALL.md', 'HARNESS.md', 'SKILL-ARCHITECTURE.md'}
IGNORED = {'.git', '__pycache__', '.artifacts', 'node_modules', '.dependency-source'}


def selected(name, profile):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe bundle path: ' + name)
    if set(path.parts) & IGNORED or path.suffix in {'.pyc', '.pyo'}:
        return False
    engine = name in ENGINE_FILES or name.startswith(ENGINE_DIRS)
    return engine if profile == 'runtime' else (name.startswith('skills/') or name in SKILL_FILES) and not engine


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory(files):
    return {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in sorted(files.items())}


def git(source, *args, data=None):
    source = Path(source).resolve()
    result = subprocess.run(['git', '-c', 'safe.directory=' + source.as_posix(), '-C', str(source), *args],
                            input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    if result.returncode:
        raise ValueError('Git snapshot read failed: ' + result.stderr.decode('utf-8', 'replace'))
    return result.stdout


def snapshot(source, revision, profile):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Use a full 40-character commit SHA, never a mutable branch or tag')
    actual = git(source, 'rev-parse', '--verify', revision + '^{commit}').decode().strip()
    if actual != revision:
        raise ValueError('Pin must identify a commit')
    entries = []
    for row in git(source, 'ls-tree', '-rz', '--full-tree', revision).split(b'\0'):
        if not row:
            continue
        meta, encoded = row.split(b'\t', 1)
        name = encoded.decode('utf-8')
        if not selected(name, profile):
            continue
        mode, kind, identity = meta.split()
        if kind != b'blob' or mode not in {b'100644', b'100755'}:
            raise ValueError('Bundle may contain only ordinary files: ' + name)
        entries.append((name, identity))
    if not entries:
        raise ValueError('Source commit contains no selected files')
    output = git(source, 'cat-file', '--batch', data=b''.join(h + b'\n' for _, h in entries))
    result, cursor = {}, 0
    for name, identity in entries:
        end = output.index(b'\n', cursor)
        h, kind, size = output[cursor:end].split()
        size = int(size)
        if h != identity or kind != b'blob' or size > 20_000_000:
            raise ValueError('Invalid or oversized Git object')
        raw = output[end + 1:end + 1 + size]
        if len(raw) != size or output[end + 1 + size:end + 2 + size] != b'\n':
            raise ValueError('Truncated Git object')
        result[name] = raw
        cursor = end + 2 + size
    if sum(map(len, result.values())) > 100_000_000:
        raise ValueError('Dependency snapshot exceeds 100 MB')
    return result


def checked(root, name):
    if not name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe destination: ' + name)
    root = Path(root).resolve()
    path = root / name
    current = path
    while current != root:
        if current.is_symlink() or (current.exists() and getattr(current.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Refusing symlink/reparse destination: ' + name)
        current = current.parent
    path.resolve().relative_to(root)
    return path


def local_files(root, profile):
    files = {}
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in IGNORED and not d.startswith(('.research', '.tmp')) and d != 'dist']
        for directory in dirs:
            relative = (Path(current) / directory).relative_to(root).as_posix()
            checked(root, relative)
        for name in names:
            relative = (Path(current) / name).relative_to(root).as_posix()
            if selected(relative, profile):
                files[relative] = checked(root, relative).read_bytes()
    return files


def read_product(root):
    product = json.loads(checked(root, 'product.json').read_text(encoding='utf-8'))
    if product.get('product') not in {'agent', 'skill'} or product.get('dependency') != {'agent': 'skills', 'skill': 'runtime'}[product['product']]:
        raise ValueError('Invalid product ownership')
    return product


def lock_path(root, profile):
    return checked(root, 'dependencies/' + profile + '.lock.json')


def verify(root=ROOT, source=None):
    root = Path(root).resolve()
    profile = read_product(root)['dependency']
    lock = json.loads(lock_path(root, profile).read_text(encoding='utf-8'))
    if lock.get('format') != 1 or lock.get('profile') != profile or lock.get('repository') != REPOSITORIES[profile]:
        raise ValueError('Invalid dependency lock')
    if not re.fullmatch(r'[0-9a-f]{40}', lock.get('commit', '')):
        raise ValueError('Invalid pinned commit')
    expected = lock['files']
    if not expected or any(not selected(name, profile) for name in expected):
        raise ValueError('Lock crosses the ownership boundary')
    actual = inventory(local_files(root, profile))
    if actual != expected:
        changed = sorted(name for name in actual.keys() | expected.keys() if actual.get(name) != expected.get(name))
        raise ValueError('Generated dependency drift; edit its owning repository and sync: ' + ', '.join(changed[:15]))
    if source is not None and inventory(snapshot(source, lock['commit'], profile)) != expected:
        raise ValueError('Dependency lock does not match the pinned Git commit')
    return {'valid': True, 'profile': profile, 'repository': lock['repository'], 'commit': lock['commit'],
            'files': len(actual), 'source_verified': source is not None}


def atomic(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.bundle-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def synchronize(root, source, revision, initialize=False):
    root = Path(root).resolve()
    profile = read_product(root)['dependency']
    target_lock = lock_path(root, profile)
    if target_lock.exists():
        if initialize:
            raise ValueError('--initialize is only for a first migration with no lock')
        verify(root)
    elif not initialize:
        raise ValueError('First migration requires --initialize after preserving existing work')
    incoming = snapshot(source, revision, profile)
    current = local_files(root, profile)
    for name in incoming.keys() | current.keys():
        checked(root, name)
    lock = {'format': 1, 'profile': profile, 'repository': REPOSITORIES[profile], 'commit': revision,
            'maintenance': 'Generated snapshot; modify the owning repository, then sync a reviewed commit.',
            'files': inventory(incoming)}
    for name, raw in incoming.items():
        atomic(checked(root, name), raw)
    for name in current.keys() - incoming.keys():
        checked(root, name).unlink()
    atomic(target_lock, (json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8'))
    return verify(root, source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('verify')
    check.add_argument('--source', type=Path)
    sync = commands.add_parser('sync')
    sync.add_argument('--source', type=Path, required=True)
    sync.add_argument('--revision', required=True)
    sync.add_argument('--initialize', action='store_true')
    args = parser.parse_args()
    try:
        result = verify(args.root, args.source) if args.command == 'verify' else synchronize(args.root, args.source, args.revision, args.initialize)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, str(exc) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
