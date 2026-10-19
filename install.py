#!/usr/bin/env python3
"""Install a coherent skill bundle; force replaces entries without nesting directories."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid


def install(destination, force=False):
    source = Path(__file__).resolve().parent
    destination = Path(destination).expanduser().resolve()
    if destination == source or destination == source / 'skills':
        raise ValueError('Do not install over source skills')
    entries = [p for p in (source / 'skills').iterdir() if p.is_dir() or p.name == 'manifest.yaml']
    entries.append(source / 'HARNESS.md')
    names = [p.name for p in entries]
    conflicts = [n for n in names if (destination / n).exists()]
    if conflicts and not force:
        raise ValueError('Existing bundle entries: ' + ', '.join(conflicts) + '; use --force for coherent replacement with backups')
    destination.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.gresearch-stage-', dir=destination))
    backup = destination / ('.gresearch-backup-' + uuid.uuid4().hex[:10])
    moved, installed = [], []
    try:
        for p in entries:
            if p.is_dir():
                shutil.copytree(p, stage / p.name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else: shutil.copy2(p, stage / p.name)
        for p in entries:
            target = destination / p.name
            if target.is_symlink() or (hasattr(target, 'is_junction') and target.is_junction()):
                raise ValueError('Refusing replacement through symlink/junction: ' + str(target))
            if target.exists():
                backup.mkdir(exist_ok=True)
                os.replace(target, backup / p.name)
                moved.append(p.name)
            os.replace(stage / p.name, target)
            installed.append(p.name)
        hashes = {}
        for name in installed:
            p = destination / name
            for f in (p.rglob('*') if p.is_dir() else [p]):
                if f.is_file(): hashes[f.relative_to(destination).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
        receipt = {'version': 2, 'destination': str(destination), 'entries': installed, 'sha256': hashes,
                   'backup': str(backup) if moved else None}
        (destination / '.gresearch-install.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding='utf-8')
        return receipt
    except BaseException:
        for name in reversed(installed):
            p = (destination / name).resolve()
            if p.parent != destination: raise RuntimeError('Unexpected installation target')
            if p.is_dir(): shutil.rmtree(p)
            else: p.unlink()
        for name in moved: os.replace(backup / name, destination / name)
        raise
    finally:
        if stage.resolve().parent != destination: raise RuntimeError('Unexpected staging directory')
        shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--dest', help='explicit runtime skill directory')
    group.add_argument('--project', action='store_true', help='install to current .claude/skills')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    destination = args.dest or (str(Path.cwd() / '.claude' / 'skills') if args.project else str(Path.home() / '.claude' / 'skills'))
    try:
        result = install(destination, args.force)
        print(json.dumps({'destination': result['destination'], 'entries': len(result['entries']), 'backup': result['backup']}, ensure_ascii=False))
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__': main()
