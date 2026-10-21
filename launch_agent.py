#!/usr/bin/env python3
"""Start the complete local research Agent workbench (Python 3.10+)."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'skills' / '_shared' / 'runtime'))
from gresearch.console import serve


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', default='.research-agent')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    serve(args.store, args.port)
