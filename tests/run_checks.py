"""Run the complete offline suite and optionally retain a compact machine receipt."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report')
    parser.add_argument('--pattern', default='test_*.py')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(repo / 'tests'), pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    record = {'time_utc': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(), 'platform': platform.platform(),
              'tests': result.testsRun, 'passed': result.wasSuccessful(), 'skips': [(str(t), reason) for t, reason in result.skipped],
              'failures': [(str(t), detail) for t, detail in result.failures + result.errors], 'seconds': time.monotonic() - started,
              'packages': {name: importlib.metadata.version(name) for name in ('cryptography', 'numpy', 'PyMuPDF', 'matplotlib', 'Pillow', 'python-pptx') if importlib.util.find_spec({'PyMuPDF': 'fitz', 'Pillow': 'PIL', 'python-pptx': 'pptx'}.get(name, name))},
              'source_hashes': {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                for directory in (repo / 'skills', repo / 'tests') for p in sorted(directory.rglob('*.py'))}}
    if args.report:
        path = Path(args.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode())
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__': raise SystemExit(main())
