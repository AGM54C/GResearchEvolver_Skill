"""Opt-in live public-provider checks. Never converts a failed request into a fixture pass."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / '_shared' / 'runtime'))
from gresearch import literature
from gresearch.core import write_json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', required=True)
parser.add_argument('--providers', nargs='+', default=['crossref', 'openalex', 'semantic-scholar', 'europepmc', 'arxiv'])
parser.add_argument('--zotero-demo-user', help='Public numeric user ID observed in Zotero API documentation')
args = parser.parse_args()
root = Path(args.output)
if root.exists(): raise SystemExit('Use a fresh output directory')
root.mkdir(parents=True)
results = []
for provider in args.providers:
    started = time.time()
    try:
        query = 'all:reproducibility' if provider == 'arxiv' else 'reproducibility'
        result = literature.search(provider, query, root / provider, page_size=2, pages=1, cache_seconds=0)
        results.append({'provider': provider, 'status': 'live_response', 'records': len(result['records']),
                        'receipts': result['receipts'], 'scope': 'connectivity and metadata parsing, not retrieval recall'})
    except Exception as exc:
        results.append({'provider': provider, 'status': 'failed', 'exception': type(exc).__name__,
                        'http_status': getattr(exc, 'code', None), 'seconds': time.time() - started})
    write_json(root / 'summary.json', results)
    print(json.dumps(results[-1]), flush=True)
if args.zotero_demo_user:
    try:
        result = literature.zotero_read('users', args.zotero_demo_user, root / 'zotero', max_pages=1)
        results.append({'provider': 'zotero', 'status': 'live_response', 'records': len(result['records']),
                        'receipts': result['receipts'], 'scope': 'public demo library; no private-library authorization tested'})
    except Exception as exc:
        results.append({'provider': 'zotero', 'status': 'failed', 'exception': type(exc).__name__, 'http_status': getattr(exc, 'code', None)})
    write_json(root / 'summary.json', results)
    print(json.dumps(results[-1]), flush=True)
