"""Graph invariants and fault-injected OpenViking HTTP contract tests.

The in-process service below is a labelled contract fixture, not evidence of a
real OpenViking deployment. Live validation uses the upstream server separately.
"""
import copy
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import urllib.parse
from unittest import mock

from test_runtime import Workspace, manifest
from gresearch import memory, maintenance
from gresearch.core import ResearchError, Store, canonical, fingerprint, read_json, write_json
from gresearch.openviking import Client, VikingError, projection


def graph():
    return {'nodes': [
        {'id': 'paper:doi/1', 'type': 'source', 'text': '量子传感 measurement', 'sha256': 'a'*64},
        {'id': 'claim-1', 'type': 'claim', 'text': 'Improved measurement sensitivity', 'scope': 'laboratory', 'status': 'proposed'},
        {'id': 'trial-1', 'type': 'experiment', 'text': 'Repeat measurement with a control'}],
        'edges': [
            {'id': 'support-1', 'from': 'paper:doi/1', 'to': 'claim-1', 'relation': 'supports',
             'evidence': {'quote': 'sensitivity increased', 'page': 3}, 'adjudication': {'status': 'pending'}},
            {'id': 'test-1', 'from': 'claim-1', 'to': 'trial-1', 'relation': 'tested_by', 'certainty': 'planned'}]}


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def reply(self, status, result=None, code=None):
        value = {'status': 'error', 'error': {'code': code}} if code else {'status': 'ok', 'result': result}
        raw = canonical(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if getattr(self.server, 'reject_reads', False):
            return self.reply(200, code='PERMISSION_DENIED')
        parsed = urllib.parse.urlsplit(self.path)
        uri = urllib.parse.parse_qs(parsed.query).get('uri', [''])[0]
        if parsed.path.endswith('/stat'):
            return self.reply(200, {'isDir': uri in self.server.directories})
        if uri not in self.server.files:
            return self.reply(404, code='NOT_FOUND')
        self.reply(200, self.server.files[uri])

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        uri = payload.get('uri')
        if self.path.endswith('/mkdir'):
            if uri in self.server.directories: return self.reply(409, code='ALREADY_EXISTS')
            self.server.directories.add(uri)
            return self.reply(200, None)
        if self.path.endswith('/write'):
            if payload['mode'] != 'create' or payload['processing_mode'] not in {'vectors_only', 'semantic_and_vectors'}:
                return self.reply(422, code='INVALID_ARGUMENT')
            if uri in self.server.files: return self.reply(409, code='ALREADY_EXISTS')
            self.server.files[uri] = payload['content']
            self.server.writes += 1
            if self.server.drop_ack:
                self.server.drop_ack = False
                self.connection.shutdown(2)
                self.connection.close()
                return
            return self.reply(200, {'uri': uri})
        if self.path.endswith('/find'):
            return self.reply(200, {'resources': self.server.hits})
        self.reply(404, code='NOT_FOUND')


class MemoryTests(Workspace):
    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        self.server.files, self.server.directories, self.server.hits = {}, set(), []
        self.server.writes, self.server.drop_ack = 0, False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = {'endpoint': 'http://127.0.0.1:' + str(self.server.server_port), 'timeout': 10}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        super().tearDown()

    def put(self, project='study', value=None, expected=0):
        return memory.put(self.store, project, value or graph(), expected, actor='researcher', reason='record research graph')

    def test_exact_graph_history_and_revision_conflict(self):
        self.put()
        first = memory.get(self.store, 'study')
        self.assertEqual(first['graph'], graph())
        changed = graph()
        changed['nodes'][1]['text'] = 'Revised hypothesis'
        self.put(value=changed, expected=1)
        with self.assertRaises(ResearchError): self.put(value=graph(), expected=1)
        self.assertEqual(memory.get(self.store, 'study', 1), first)
        self.assertEqual(memory.get(self.store, 'study')['graph'], changed)

    def test_dangling_edge_rejected_without_partial_commit(self):
        bad = graph()
        bad['edges'][0]['to'] = 'missing'
        with self.assertRaises(ResearchError): self.put(value=bad)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM memory_nodes').fetchone()[0], 0)

    def test_graph_traversal_and_source_invalidation_preserve_evidence(self):
        self.put()
        result = memory.neighbors(self.store, 'study', ['paper:doi/1'], hops=2, direction='out')
        self.assertEqual(len(result['nodes']), 3)
        self.assertEqual(result['edges'], graph()['edges'])
        self.assertTrue(memory.neighbors(self.store, 'study', ['paper:doi/1'], hops=2, max_nodes=2)['truncated'])
        changed = memory.invalidate_sources(self.store, 'study', ['paper:doi/1'], 1, actor='reviewer', reason='source retracted')
        self.assertEqual(len(changed['affected']), 3)
        self.assertNotIn('adjudication', memory.get(self.store, 'study')['graph']['edges'][0])
        self.assertEqual(memory.get(self.store, 'study', 1)['graph'], graph())

    def test_lossless_export_import_and_project_scope(self):
        self.put()
        memory.export(self.store, 'study', self.root / 'graph.json')
        original = read_json(self.root / 'graph.json')
        memory.import_snapshot(self.store, original, 'copied', 0, actor='user', reason='portable import')
        self.assertEqual(memory.get(self.store, 'copied')['graph'], graph())
        self.assertTrue(memory.search(self.store, 'study', '量子传感')['results'])
        self.assertFalse(memory.search(self.store, 'copied', 'missingwords')['results'])
        original['graph']['nodes'][0]['text'] = 'tampered'
        with self.assertRaises(ResearchError): memory.import_snapshot(self.store, original, 'bad', 0, actor='u', reason='test')

    def test_openviking_sync_lost_ack_is_reconciled_without_duplicate_writes(self):
        self.put()
        self.server.drop_ack = True
        result = memory.sync(self.store, 'study', self.config)
        self.assertEqual(result['status'], 'synced')
        count = self.server.writes
        self.assertEqual(memory.sync(self.store, 'study', self.config)['status'], 'synced')
        self.assertEqual(self.server.writes, count)
        snapshot = memory.get(self.store, 'study')
        loaded = Client(self.config).load('study', snapshot['snapshot'])
        self.assertEqual(loaded, snapshot)
        root, files = projection(snapshot, 'viking://resources/gresearch')
        edge = json.loads(next(value for uri, value in files.items() if '/edges/' in uri))
        self.assertIn(edge['record'], graph()['edges'])
        self.assertTrue(edge['from_uri'].startswith(root + '/nodes/'))

    def test_offline_delivery_preserves_local_graph_and_can_resume(self):
        self.put()
        with mock.patch.object(Client, 'publish', side_effect=OSError('connection lost')):
            result = memory.sync(self.store, 'study', self.config)
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(memory.get(self.store, 'study')['graph'], graph())
        result = memory.sync(self.store, 'study', self.config)
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(result['status'], 'synced')

    def test_partial_upload_is_not_a_committed_graph(self):
        self.put()
        real = Client.ensure_file
        def fail_on_edge(client, uri, value):
            if '/edges/' in uri: raise VikingError('injected_failure')
            return real(client, uri, value)
        with mock.patch.object(Client, 'ensure_file', fail_on_edge):
            self.assertEqual(memory.sync(self.store, 'study', self.config)['status'], 'pending')
        self.assertFalse(any(uri.endswith('/commit.json') for uri in self.server.files))
        self.assertEqual(memory.sync(self.store, 'study', self.config)['status'], 'synced')

    def test_remote_tampering_and_cross_project_hits_are_rejected(self):
        self.put()
        memory.sync(self.store, 'study', self.config)
        uri = next(k for k in self.server.files if '/nodes/' in k)
        self.server.hits = [{'uri': uri, 'score': .8}, {'uri': 'viking://resources/other/private.json', 'score': 1}]
        result = memory.remote_search(self.store, 'study', self.config, 'measurement')
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['rejected_hits'], 1)
        self.server.files[uri] = 'changed'
        with self.assertRaises(VikingError): memory.remote_search(self.store, 'study', self.config, 'measurement')
        self.assertEqual(memory.sync(self.store, 'study', self.config)['status'], 'pending')

    def test_credentials_are_never_part_of_graph_or_receipts(self):
        self.put()
        secret = 'temporary-fixture-auth-not-real'
        with mock.patch.dict(os.environ, {'OV_TEST_TOKEN': secret}):
            result = memory.sync(self.store, 'study', {**self.config, 'api_key_env': 'OV_TEST_TOKEN'})
        self.assertEqual(result['status'], 'synced')
        self.assertNotIn(secret, canonical(self.store.events()))
        self.assertNotIn(secret, canonical(result))
        with self.assertRaises(ResearchError): Client({**self.config, 'api_key': secret})

    def test_error_envelopes_and_oversized_responses_do_not_pass(self):
        self.server.reject_reads = True
        with self.assertRaises(VikingError) as error:
            Client(self.config).read('viking://resources/test/file')
        self.assertEqual(error.exception.code, 'PERMISSION_DENIED')
        self.server.reject_reads = False
        uri = 'viking://resources/test/large'
        self.server.files[uri] = 'x' * 2048
        with self.assertRaises(VikingError) as error:
            Client({**self.config, 'max_response_bytes': 1024}).read(uri)
        self.assertEqual(error.exception.code, 'response_too_large')

    def test_full_store_backup_restores_graph_versions_and_detects_corruption(self):
        run = self.store.create(manifest())
        self.put()
        self.put(expected=1)
        original = memory.get(self.store, 'study')
        receipt = maintenance.backup(self.store, self.root / 'backup')
        self.assertTrue(maintenance.verify_backup(receipt['backup'])['valid'])
        maintenance.restore_backup(receipt['backup'], self.root / 'restored')
        restored = Store(self.root / 'restored')
        try:
            self.assertEqual(memory.get(restored, 'study'), original)
            self.assertEqual(memory.get(restored, 'study', 1)['graph'], graph())
            self.assertEqual(restored.get(run)[1]['status'], 'ready')
            self.assertTrue(restored.verify()['valid'])
        finally: restored.close()
        (Path(receipt['backup']) / 'state.sqlite3').write_bytes(b'corrupt')
        self.assertFalse(maintenance.verify_backup(receipt['backup'])['valid'])
        with self.assertRaises(ResearchError): maintenance.restore_backup(receipt['backup'], self.root / 'should-not-exist')

    def test_backup_rejects_unsafe_run_ids_even_with_matching_manifest_digest(self):
        directory = self.root / 'backup'
        maintenance.backup(self.store, directory)
        data = read_json(directory / 'backup.json')
        data['runs'] = ['../../outside']
        write_json(directory / 'backup.json', data)
        (directory / '.done').write_text(fingerprint(data))
        with self.assertRaises(ResearchError):
            maintenance.restore_backup(directory, self.root / 'restored')
        self.assertFalse((self.root / 'restored').exists())
        self.assertFalse((self.root / 'outside').exists())
