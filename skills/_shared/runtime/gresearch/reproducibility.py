"""Observable environment locks. Matching these is necessary, not sufficient for reproducibility."""
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import sys

from .core import ResearchError, digest, fingerprint, safe_path


SAFE_ENV = ('PYTHONHASHSEED', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'CUBLAS_WORKSPACE_CONFIG', 'TZ', 'LANG')


def capture(root, packages=None, files=()):
    versions = {}
    if packages is None:
        packages = {d.metadata['Name'] for d in importlib.metadata.distributions() if d.metadata.get('Name')}
    for name in sorted(set(packages)):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    runtime = Path(__file__).parent
    value = {
        'version': 1,
        'python': {'implementation': platform.python_implementation(), 'version': platform.python_version(),
                   'executable_sha256': digest(Path(sys.executable).read_bytes())},
        'platform': {'system': platform.system(), 'machine': platform.machine()},
        'packages': versions,
        'files': {p: digest(safe_path(root, p).read_bytes()) for p in sorted(set(files))},
        'environment': {k: os.environ.get(k) for k in SAFE_ENV},
        'runtime_sha256': fingerprint({p.name: digest(p.read_bytes()) for p in sorted(runtime.glob('*.py'))}),
    }
    return {**value, 'sha256': fingerprint(value)}


def compare(expected, observed):
    for lock in (expected, observed):
        if not isinstance(lock, dict) or lock.get('version') != 1 or lock.get('sha256') != fingerprint({k: v for k, v in lock.items() if k != 'sha256'}):
            raise ResearchError('Invalid environment lock')
    differences = [k for k in sorted(set(expected) | set(observed)) if k != 'sha256' and expected.get(k) != observed.get(k)]
    return {'matches': not differences, 'differences': differences, 'expected': expected['sha256'], 'observed': observed['sha256'],
            'scope': 'runtime interpreter, selected packages/files, architecture and allowlisted environment; no guarantee of identical scientific results'}


def inspect_run(store, run, manifest):
    policy = manifest.get('reproducibility', {})
    expected = policy.get('lock')
    packages = expected.get('packages', {}) if expected else policy.get('packages')
    files = expected.get('files', {}) if expected else policy.get('files', [])
    observed = capture(store.work(run), packages, files)
    check = compare(expected, observed) if expected else {'matches': True, 'differences': [], 'mode': 'record_only'}
    if policy.get('mode') == 'strict' and not expected:
        raise ResearchError('Strict reproducibility requires a previously captured environment lock')
    return observed, check


def executable_receipt(argv, cwd):
    program = Path(argv[0])
    if not program.is_absolute():
        candidate = Path(cwd) / program
        resolved = str(candidate) if candidate.is_file() else shutil.which(argv[0])
        if not resolved:
            raise ResearchError('Executable not found: ' + argv[0])
        program = Path(resolved)
    return {'path': str(program.resolve()), 'sha256': digest(program.read_bytes())}
