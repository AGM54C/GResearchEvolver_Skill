#!/usr/bin/env python3
"""Build/verify a deterministic full-source Agent ZIP without state or credentials.

This is the runnable project package, not a completed competition submission:
real presentation/video/CodeArts proof must be supplied separately.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


ROOT = Path(__file__).resolve().parent
DIRECTORIES = ('skills', 'tests', 'docs', 'benchmarks', 'research-instance', '.github', 'dependencies', 'tools')
ROOT_FILES = ('.gitattributes', '.gitignore', 'README.md', 'LICENSE', 'INSTALL.md', 'HARNESS.md', 'SKILL-ARCHITECTURE.md',
              'install.py', 'install.sh', 'launch_agent.py', 'build_agent.py', 'product.json')
LIMIT = 200_000_000


def sha(raw): return hashlib.sha256(raw).hexdigest()


def build(destination):
    import runpy
    runpy.run_path(str(ROOT / 'tools/bundle_sync.py'))['verify'](ROOT)
    destination = Path(destination).resolve()
    paths = [ROOT / name for name in ROOT_FILES]
    for directory in DIRECTORIES:
        paths.extend(p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.pyo'})
    entries = {}
    for path in sorted(paths):
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Package does not follow symlinks/reparse points')
        if path == destination: raise ValueError('Output must be outside source directories')
        relative = path.relative_to(ROOT).as_posix()
        if any(part.startswith(('.env', '.research', '.tmp')) or part in {'auth.json', 'config.toml', 'state.sqlite3'} for part in path.relative_to(ROOT).parts):
            raise ValueError('State or credentials found in source package: ' + relative)
        entries[relative] = path.read_bytes()
    registry = json.loads(entries['skills/manifest.yaml'])
    for name, spec in registry['skills'].items():
        if 'skills/' + spec['entry'] not in entries: raise ValueError('Missing skill: ' + name)
    inventory = {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in entries.items()}
    manifest = {'format': 1, 'kind': 'full_source_agent_project', 'skills': sorted(registry['skills']),
                'files': inventory, 'raw_bytes': sum(map(len, entries.values())),
                'excludes': ['runtime states', 'credentials', 'model weights', 'virtual environments'],
                'competition_submission_complete': False}
    entries['PACKAGE-MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    if sum(map(len, entries.values())) > LIMIT: raise ValueError('Raw package exceeds 200 MB guard')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(entries.items()):
            info = zipfile.ZipInfo('GResearchEvolver-Agent/' + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100755 if name.endswith('.sh') else 0o100644) << 16
            archive.writestr(info, raw)
    if destination.stat().st_size > LIMIT: raise ValueError('ZIP exceeds 200 MB guard')
    result = {**verify(destination), 'sha256': sha(destination.read_bytes()), 'zip_bytes': destination.stat().st_size,
              'limit_bytes': LIMIT, 'competition_submission_complete': False}
    destination.with_suffix('.manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    destination.with_suffix('.sha256').write_text(result['sha256'] + '  ' + destination.name + '\n', encoding='utf-8')
    return result


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or sum(x.file_size for x in archive.infolist()) > LIMIT: raise ValueError('Invalid package inventory')
        prefix = 'GResearchEvolver-Agent/'
        for name in names:
            if not name.startswith(prefix) or '..' in PurePosixPath(name).parts or '\\' in name: raise ValueError('Unsafe archive path')
        manifest = json.loads(archive.read(prefix + 'PACKAGE-MANIFEST.json'))
        if set(names) != {prefix + n for n in manifest['files']} | {prefix + 'PACKAGE-MANIFEST.json'}: raise ValueError('Unexpected or missing package files')
        for name, expected in manifest['files'].items():
            raw = archive.read(prefix + name)
            if sha(raw) != expected['sha256'] or len(raw) != expected['bytes']: raise ValueError('Package content mismatch: ' + name)
        return {'valid': True, 'files': len(names), 'skills': len(manifest['skills']), 'raw_bytes': manifest['raw_bytes']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output'); group.add_argument('--verify')
    args = parser.parse_args()
    print(json.dumps(build(args.output) if args.output else verify(args.verify), ensure_ascii=False, indent=2))
