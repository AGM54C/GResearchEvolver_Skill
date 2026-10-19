"""Opt-in real OpenViking + cached MiniLM test in an isolated Docker network namespace.

No API keys, external network, global hooks or production stores are used.
Run: python -B tests/live_openviking.py --report /path/to/receipt.json
The two digest-pinned images must already be available locally.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'skills/_shared/runtime'))
OV_IMAGE = 'ghcr.io/volcengine/openviking@sha256:cbdca179a2101cf5cd6a3455c769875fca37a0e2a09cc834807371df675bc061'
ENCODER_IMAGE = 'sha256:e91c87665910d2f7979f01464eb9fc8205550b1e4e64cebdca96ef5a746e65fb'
MODEL = '/app/backend/data/cache/embedding/models/models--sentence-transformers--all-MiniLM-L6-v2/snapshots/8b3219a92973c328a8e22fadcfa821b5dc75636a'


def embed_server():
    import torch
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(1)
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    model = AutoModel.from_pretrained(MODEL, local_files_only=True, use_safetensors=True).eval()
    stats = {'embedding_requests': 0, 'vectors': 0, 'unexpected_requests': 0,
             'model_revision': Path(MODEL).name,
             'weights_sha256': hashlib.sha256((Path(MODEL) / 'model.safetensors').read_bytes()).hexdigest()}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def reply(self, status, value):
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self): self.reply(200, stats)
        def do_POST(self):
            if self.path != '/v1/embeddings':
                stats['unexpected_requests'] += 1
                return self.reply(503, {'error': 'Only actual local MiniLM embeddings are provided; no VLM fixture'})
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            texts = data['input']
            if isinstance(texts, str): texts = [texts]
            inputs = tokenizer(texts, return_tensors='pt', padding=True, truncation=True, max_length=256)
            with torch.inference_mode():
                hidden = model(**inputs).last_hidden_state
                mask = inputs['attention_mask'].unsqueeze(-1)
                vectors = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
                vectors = torch.nn.functional.normalize(vectors, p=2, dim=1).tolist()
            stats['embedding_requests'] += 1
            stats['vectors'] += len(vectors)
            return self.reply(200, {'object': 'list', 'model': 'all-MiniLM-L6-v2',
                                   'data': [{'object': 'embedding', 'index': i, 'embedding': v} for i, v in enumerate(vectors)],
                                   'usage': {'prompt_tokens': int(inputs['attention_mask'].sum()), 'total_tokens': int(inputs['attention_mask'].sum())}})
    ThreadingHTTPServer(('127.0.0.1', 8020), Handler).serve_forever()


def probe(phase):
    from gresearch import memory
    from gresearch.core import Store, read_json, write_json
    from gresearch.openviking import Client
    destination = Path('/validation')
    config = {'endpoint': 'http://127.0.0.1:1933', 'namespace': 'viking://resources/gresearch-validation',
              'processing_mode': 'vectors_only', 'timeout': 120}
    deadline = time.monotonic() + 60
    while True:
        try:
            with urllib.request.urlopen('http://127.0.0.1:1933/health', timeout=2) as response:
                if response.status == 200: break
        except OSError: pass
        if time.monotonic() >= deadline: raise RuntimeError('OpenViking health deadline exceeded')
        time.sleep(.5)
    store = Store(destination / ('control-' + phase))
    try:
        if phase == 'first':
            graph = {'nodes': [
                {'id': 'source/optics', 'type': 'source', 'text': 'Quantum optical sensors measure weak magnetic fields.', 'provenance': {'kind': 'integration_fixture'}},
                {'id': 'claim-1', 'type': 'claim', 'text': 'Optical measurement sensitivity must be tested against controls.', 'scope': 'laboratory', 'status': 'proposed'},
                {'id': 'trial-1', 'type': 'experiment', 'text': 'Repeat magnetic sensitivity measurements under matched controls.', 'seed': 17}],
                'edges': [{'id': 'e1', 'from': 'source/optics', 'to': 'claim-1', 'relation': 'motivates', 'evidence': {'quote': 'integration fixture; not scientific evidence'}},
                          {'id': 'e2', 'from': 'claim-1', 'to': 'trial-1', 'relation': 'tested_by', 'status': 'planned'}]}
            memory.put(store, 'optics', graph, 0, actor='integration-test', reason='real OpenViking graph roundtrip')
            snapshot = memory.get(store, 'optics')
            write_json(destination / 'expected.json', snapshot)
            receipt = memory.sync(store, 'optics', config)
            if receipt['status'] != 'synced': raise RuntimeError(json.dumps(receipt))
            second = memory.sync(store, 'optics', config)
            if second['status'] != 'synced': raise RuntimeError(json.dumps(second))
        else:
            snapshot = read_json(destination / 'expected.json')
            graph = snapshot['graph']
            memory.import_snapshot(store, snapshot, 'restored', 0, actor='integration-test', reason='restore graph after server restart')
        remote = Client(config).load('optics', snapshot['snapshot'])
        assert remote == snapshot
        # Search is scoped to the exact remote revision. Every accepted hit must
        # contain the original node bytes; it is not treated as entailment.
        client = Client(config)
        root = config['namespace'] + '/optics/' + snapshot['snapshot']
        hits = client.find('optical magnetic sensing measurement', root + '/nodes', 10)
        assert hits, 'No real vector search results'
        if phase == 'first':
            checked = memory.remote_search(store, 'optics', config, 'optical magnetic sensing measurement')
            assert checked['results'], 'No verified node hits'
        with urllib.request.urlopen('http://127.0.0.1:8020/stats', timeout=5) as r: stats = json.load(r)
        assert stats['embedding_requests'] > 0 and stats['unexpected_requests'] == 0, stats
        result = {'phase': phase, 'passed': True, 'snapshot': snapshot['snapshot'], 'nodes': len(graph['nodes']), 'edges': len(graph['edges']),
                  'returned_hits': len(hits), 'encoder': stats, 'graph_equal_after_roundtrip': True,
                  'scientific_quality_or_scaling_benchmark': False}
        write_json(destination / (phase + '.json'), result)
        print(json.dumps(result))
    finally: store.close()


def launch(report):
    def docker(*args, timeout=180):
        proc = subprocess.run(['docker', *args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
        if proc.returncode:
            raise RuntimeError(proc.stdout[-4000:] + proc.stderr[-4000:])
        return proc.stdout
    names = ['gresearch-embedding-' + uuid.uuid4().hex[:10], 'gresearch-openviking-' + uuid.uuid4().hex[:10]]
    temp = tempfile.TemporaryDirectory(prefix='.tmp-openviking-', dir=REPO.parent)
    scratch = Path(temp.name).resolve()
    results = {'openviking_image': OV_IMAGE, 'encoder_image': ENCODER_IMAGE, 'network': 'isolated shared network namespace; no external network', 'passed': False}
    try:
        config = {'storage': {'workspace': '/tmp/ov-validation', 'agfs': {'backend': 'local'}},
                  'server': {'host': '127.0.0.1', 'port': 1933, 'auth_mode': 'dev'},
                  'embedding': {'max_retries': 0, 'dense': {'provider': 'openai', 'api_base': 'http://127.0.0.1:8020/v1',
                               'api_key': 'local-test-only', 'model': 'all-MiniLM-L6-v2', 'dimension': 384, 'encoding_format': 'float'}},
                  'vlm': {'provider': 'openai', 'api_base': 'http://127.0.0.1:8020/v1', 'api_key': 'local-test-only', 'model': 'not-used'}}
        (scratch / 'ov.conf').write_text(json.dumps(config), encoding='utf-8')
        common = ['--mount', 'type=bind,source=' + str(REPO) + ',target=/repo,readonly', '--mount', 'type=bind,source=' + str(scratch) + ',target=/validation', '-e', 'PYTHONDONTWRITEBYTECODE=1']
        docker('run', '-d', '--name', names[0], '--network', 'none', *common, '--entrypoint', 'python', ENCODER_IMAGE, '/repo/tests/live_openviking.py', '--embedding')
        docker('run', '-d', '--name', names[1], '--network', 'container:' + names[0], *common,
               '--entrypoint', '/app/.venv/bin/openviking-server', OV_IMAGE, '--config', '/validation/ov.conf', '--host', '127.0.0.1', '--port', '1933')
        for phase in ('first', 'restart'):
            if phase == 'restart': docker('restart', names[1])
            print(docker('exec', names[1], '/app/.venv/bin/python', '-B', '/repo/tests/live_openviking.py', '--probe', phase, timeout=300), flush=True)
            results[phase] = json.loads((scratch / (phase + '.json')).read_text())
        results['passed'] = True
    except Exception as exc:
        results['error'] = str(exc)
        for name in names:
            try: results[name] = docker('logs', '--tail', '35', name)[-6000:]
            except Exception: pass
        raise
    finally:
        for name in reversed(names):
            try: docker('rm', '-f', name)
            except Exception: pass
        if report:
            from gresearch.core import write_json
            write_json(report, results)
        assert scratch.parent == REPO.parent.resolve() and scratch.name.startswith('.tmp-openviking-')
        temp.cleanup()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--embedding', action='store_true')
    parser.add_argument('--probe', choices=['first', 'restart'])
    parser.add_argument('--report')
    args = parser.parse_args()
    if args.embedding: embed_server()
    elif args.probe: probe(args.probe)
    else: launch(args.report)
