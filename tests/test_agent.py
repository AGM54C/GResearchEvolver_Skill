"""Agent fault tests. Local scripted HTTP fixtures are NOT model evaluations."""
import copy
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / '_shared' / 'runtime'))
from gresearch import agent, agent_protocol as protocol, agent_tools as gateway, models
from gresearch.core import ResearchError, Store, canonical, digest, read_json, write_json
from gresearch.locking import LockBusy, resource_lock


def response(*calls, text=''):
    output = [{'type': 'function_call', 'call_id': identity, 'name': name, 'arguments': canonical(args), 'status': 'completed'}
              for identity, name, args in calls]
    if text: output.append({'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': text}], 'status': 'completed'})
    return {'status': 'completed', 'model': 'scripted-fixture', 'output': output, 'usage': {'input_tokens': 20, 'output_tokens': 10}}


def report(identity='report-call', review=False):
    return (identity, 'report_stage', {'stage': 'analysis', 'why': '检验实际工具链', 'method': '固定输入，调用统计工具并读取回执',
        'findings': '仅为测试 fixture，不是科研结论。', 'explanation': '像账本一样记录每步可检查的依据。',
        'evidence': [], 'limitations': ['没有真实模型推理'], 'questions': ['是否继续？'], 'review_required': review})


@contextmanager
def endpoint(script):
    requests, lock = [], threading.Lock()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:
                requests.append(data)
                entry = script.pop(0) if script else {'http': 500}
            if callable(entry): entry = entry(data)
            status = entry.get('http', 200)
            raw = json.dumps(entry.get('body', entry)).encode()
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Retry-After', entry.get('retry_after', '0'))
                self.end_headers(); self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    config = {'provider': 'responses', 'base_url': f'http://127.0.0.1:{server.server_port}', 'model': 'scripted-fixture',
              'stream': False, 'max_output_tokens': 300, 'timeout': 10}
    try: yield config, requests
    finally: server.shutdown(); server.server_close(); thread.join(timeout=3)


class ProtocolTests(unittest.TestCase):
    def test_native_responses_keep_reasoning_and_tool_only_reply(self):
        reply = response(('c1', 'list_files', {}))
        reasoning = {'type': 'reasoning', 'id': 'rs_1', 'summary': [], 'encrypted_content': 'opaque'}
        reply['output'].insert(0, reasoning)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(models, '_request', return_value=(canonical(reply).encode(), 'application/json')) as request:
            result = protocol.turn({'provider': 'responses', 'model': 'm', 'base_url': 'https://example.com'},
                                   [{'role': 'user', 'content': 'task'}], gateway.TOOLS, Path(tmp) / 'call')
            self.assertEqual(result['append'][0], reasoning)
            self.assertEqual(result['calls'][0]['arguments'], {})
            self.assertFalse(request.call_args.args[1]['store'])
            self.assertEqual(protocol.tool_output('responses', result['calls'][0], {'ok': True})['call_id'], 'c1')

    def test_chat_and_ollama_native_call_round_trip(self):
        call = {'id': 'c', 'type': 'function', 'function': {'name': 'list_files', 'arguments': '{}'}}
        chat = {'choices': [{'finish_reason': 'tool_calls', 'message': {'role': 'assistant', 'content': None, 'tool_calls': [call]}}]}
        parsed = protocol.parse_response('chat-completions', chat, 't')
        self.assertEqual(parsed['append'][0]['tool_calls'], [call])
        self.assertEqual(protocol.tool_output('chat-completions', parsed['calls'][0], {})['tool_call_id'], 'c')
        ollama = {'done': True, 'message': {'role': 'assistant', 'content': '', 'tool_calls': [{'function': {'name': 'list_files', 'arguments': {}}}]}}
        parsed = protocol.parse_response('ollama', ollama, 'turn-1')
        self.assertEqual(parsed['calls'][0]['id'], 'turn-1-0')
        self.assertEqual(protocol.tool_output('ollama', parsed['calls'][0], {})['tool_name'], 'list_files')

    def test_incomplete_duplicate_ids_and_invalid_arguments_fail_closed(self):
        cases = [response(('same', 'list_files', {}), ('same', 'list_files', {})),
                 {**response(('c', 'list_files', {})), 'status': 'incomplete'}]
        for raw in ('{"x":1,"x":2}', '{"x":NaN}', '{"unfinished":', '[]'):
            item = response(('c', 'list_files', {})); item['output'][0]['arguments'] = raw; cases.append(item)
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ResearchError): protocol.parse_response('responses', item, 'turn')

    def test_partial_stream_never_accepts_function_delta(self):
        raw = b'data: {"type":"response.function_call_arguments.delta","delta":"{}"}\n\ndata: [DONE]\n'
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(models, '_request', return_value=(raw, 'text/event-stream')):
            with self.assertRaises(ResearchError):
                protocol.turn({'provider': 'responses', 'model': 'm', 'base_url': 'https://example.com'},
                              [{'role': 'user', 'content': 'task'}], gateway.TOOLS, Path(tmp) / 'call')
            self.assertTrue(read_json(Path(tmp) / 'call' / 'failure.json')['counts_against_budget'])

    def test_http_error_is_sanitized_and_redirects_refused(self):
        error = urllib.error.HTTPError('https://example.com', 429, 'secret-body', {'Retry-After': '3'}, None)
        with mock.patch('urllib.request.OpenerDirector.open', side_effect=error):
            with self.assertRaises(models.ModelTransportError) as caught: models._request('https://example.com', {}, 'secret-key', 10)
        self.assertTrue(caught.exception.retryable)
        self.assertEqual(caught.exception.retry_after, 3)
        self.assertNotIn('secret', str(caught.exception))
        with self.assertRaises(models.ModelTransportError): models._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.com')


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'store')
    def tearDown(self):
        self.store.close(); self.tmp.cleanup()
    def create(self, config, **kwargs):
        return agent.create(self.store, '验证科研工具，保留完整证据和阶段报告。', config, identity='test', **kwargs)['id']

    def test_catalog_preserves_all_skills_operations_and_visual_features(self):
        from gresearch.cli import OPERATIONS
        catalog = gateway.catalog(agent.DEFAULT_POLICY)
        self.assertEqual(len(catalog['skills']), 26)
        self.assertEqual({x['name'] for x in catalog['operations']}, set(OPERATIONS))
        self.assertGreaterEqual(len(OPERATIONS), 82)
        self.assertTrue({'figure-mimic', 'slides-builder', 'research-explainer'} <= {x['name'] for x in catalog['skills']})
        self.assertEqual(gateway.mode({'name': 'research_operation', 'arguments': {'operation': 'capability-activate', 'arguments_json': '{}'}}, agent.DEFAULT_POLICY), 'human_only')

    def test_end_to_end_real_workers_stats_report_and_replay_free_continuation(self):
        call = ('adjust-1', 'research_operation', {'operation': 'adjust', 'arguments_json': '{"pvalues":[0.01,0.03,0.2]}'})
        with endpoint([response(call), response(report()), response(text='测试结束；结果不代表模型科研能力。')]) as (config, requests):
            identity = self.create(config)
            state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'completed', state.get('last_error'))
        result = json.loads(self.store.blob(state['calls']['adjust-1']['result_hash']))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['value']['adjusted'], [.03, .06, .2])
        self.assertEqual(state['usage']['model_calls'], 3)
        self.assertEqual(state['usage']['tool_calls'], 2)
        self.assertTrue(any(x.get('type') == 'function_call_output' for x in requests[1]['input']))
        self.assertTrue((agent.directory(self.store, identity) / 'reports/analysis/report-0001/report.md').is_file())
        self.assertTrue(self.store.verify()['valid'])
        with self.assertRaises(ResearchError): agent.run(self.store, identity)

    def test_report_gate_binds_reference_and_cannot_resume_past_feedback(self):
        with endpoint([response(report(review=True)), response(text='done')]) as (config, _):
            identity = self.create(config)
            state = agent.run(self.store, identity)
            self.assertEqual(state['status'], 'awaiting_researcher')
            with self.assertRaises(ResearchError): agent.control(self.store, identity, 'resume')
            with self.assertRaises(ResearchError): agent.feedback(self.store, identity, reference='stale', actor='human', decision='approve', reason='reviewed')
            agent.feedback(self.store, identity, reference=state['waiting']['id'], actor='human', decision='approve', reason='fixture reviewed')
            state = agent.run(self.store, identity)
            self.assertEqual(state['status'], 'completed')
            self.assertEqual(state['feedback'][0]['actor'], 'human')

    def test_exact_command_approval_and_changed_workspace_rejected(self):
        command = ('cmd', 'run_command', {'argv': [sys.executable, '-c', "from pathlib import Path;Path('ran.txt').write_text('executed')"], 'purpose': 'test command'})
        with endpoint([response(command)]) as (config, _):
            identity = self.create(config)
            state = agent.run(self.store, identity)
        self.assertEqual(state['waiting']['kind'], 'approval')
        self.assertFalse((agent.workdir(self.store, identity) / 'ran.txt').exists())
        (agent.workdir(self.store, identity) / 'changed.txt').write_text('new input')
        with self.assertRaises(ResearchError): agent.feedback(self.store, identity, reference='cmd', actor='human', decision='approve', reason='approve')
        agent.feedback(self.store, identity, reference='cmd', actor='human', decision='reject', reason='inputs changed')
        self.assertEqual(agent.get(self.store, identity)['calls']['cmd']['status'], 'failed')

    def test_approved_command_runs_once_and_is_supervised(self):
        command = ('cmd', 'run_command', {'argv': [sys.executable, '-c', "from pathlib import Path;Path('ran.txt').write_text('executed')"], 'purpose': 'test command'})
        with endpoint([response(command), response(report()), response(text='done')]) as (config, _):
            identity = self.create(config); state = agent.run(self.store, identity)
            agent.feedback(self.store, identity, reference=state['waiting']['id'], actor='human', decision='approve', reason='exact test command approved')
            state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'completed', state.get('last_error'))
        self.assertEqual((agent.workdir(self.store, identity) / 'ran.txt').read_text(), 'executed')
        self.assertEqual(sum(a['call_id'] == 'cmd' for a in state['attempts']), 1)

    def test_native_duplicate_across_turns_never_reexecutes(self):
        call = ('same', 'list_files', {})
        with endpoint([response(call), response(call)]) as (config, _):
            identity = self.create(config); state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(state['usage']['tool_calls'], 1)
        self.assertIsNone(state['active'])

    def test_model_retry_counts_budget_and_auth_failure_does_not_retry(self):
        with endpoint([{'http': 429}, response(report()), response(text='done')]) as (config, _):
            identity = self.create(config); state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'completed', state.get('last_error'))
        self.assertEqual(state['usage']['model_calls'], 3)
        self.assertEqual(state['usage']['unknown_model_usage'], 1)
        with endpoint([{'http': 401}]) as (config, requests):
            other = agent.create(self.store, 'auth test', config)['id']
            state = agent.run(self.store, other)
            self.assertEqual(state['status'], 'failed'); self.assertEqual(len(requests), 1)

    def test_retry_after_longer_than_budget_does_not_retry_early(self):
        with endpoint([{'http': 429, 'retry_after': '120'}]) as (config, requests):
            identity = self.create(config, budget={'active_seconds': 20})
            state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'budget_exhausted')
        self.assertEqual(len(requests), 1)

    def test_active_model_cancel_stops_supervised_worker(self):
        received, release = threading.Event(), threading.Event()
        def slow(_):
            received.set(); release.wait(8)
            return response(text='late response')
        with endpoint([slow]) as (config, _):
            identity = self.create(config)
            outcomes = []
            def worker():
                store = Store(self.store.root)
                try: outcomes.append(agent.run(store, identity))
                finally: store.close()
            thread = threading.Thread(target=worker, daemon=True); thread.start()
            try:
                self.assertTrue(received.wait(5), 'model worker did not reach fixture endpoint')
                agent.control(self.store, identity, 'cancel')
                thread.join(timeout=8)
                self.assertFalse(thread.is_alive())
                self.assertEqual(outcomes[0]['status'], 'cancelled')
                self.assertIsNone(outcomes[0]['active'])
            finally:
                release.set(); thread.join(timeout=5)

    def test_timed_out_tool_never_replays_without_operator_reconciliation(self):
        command = ('slow', 'run_command', {'argv': [sys.executable, '-c', "from pathlib import Path;import time;Path('effect.txt').write_text('effect');time.sleep(10)"], 'purpose': 'interruption test'})
        with endpoint([response(command)]) as (config, _):
            identity = self.create(config, policy={'tool_timeout': 5})
            state = agent.run(self.store, identity)
            agent.feedback(self.store, identity, reference='slow', actor='human', decision='approve', reason='fault injection fixture')
            state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'interrupted')
        self.assertTrue((agent.workdir(self.store, identity) / 'effect.txt').is_file())
        path = agent.directory(self.store, identity) / 'attempts' / state['active']['directory'] / 'supervisor/result.json'
        self.assertTrue(read_json(path)['cleanup_verified'])
        with self.assertRaises(ResearchError): agent.recover(self.store, identity)
        state = agent.recover(self.store, identity, {'actor': 'human', 'reason': 'verified supervisor result and marker', 'effects_checked': 'local marker retained; job cleanup verified; no remote task'})
        self.assertEqual(state['calls']['slow']['status'], 'failed')
        self.assertEqual(state['queue'], [])

    def test_researcher_direction_withdraws_old_plan_without_approving_it(self):
        with endpoint([response(('cmd', 'run_command', {'argv': [sys.executable, '--version'], 'purpose': 'old plan'}))]) as (config, _):
            identity = self.create(config); agent.run(self.store, identity)
            agent.steer(self.store, identity, '先解释局限，不要执行旧计划。', actor='researcher')
        state = agent.get(self.store, identity)
        self.assertEqual(state['status'], 'paused')
        self.assertIsNone(state['waiting'])
        self.assertEqual(state['queue'], [])
        self.assertEqual(state['calls']['cmd']['status'], 'failed')
        self.assertEqual(state['usage']['tool_calls'], 0)
        self.assertTrue(state['pending_messages'])

    def test_budget_exhaustion_keeps_pending_calls_without_execution(self):
        with endpoint([response(('a', 'list_files', {}), ('b', 'list_files', {}))]) as (config, _):
            identity = self.create(config, budget={'tool_calls': 1})
            state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'budget_exhausted')
        self.assertEqual(state['queue'], ['b'])
        with self.assertRaises(ResearchError): agent.control(self.store, identity, 'resume')

    def test_path_escape_private_files_symlinks_and_optimistic_write(self):
        work = self.root / 'work'; work.mkdir()
        for path in ('../outside', 'C:/secret', '.env', 'a/.codex/auth.json', 'a\\b'):
            with self.subTest(path=path), self.assertRaises(ResearchError): gateway.checked_path(work, path)
        call = {'name': 'write_file', 'arguments': {'path': 'note.md', 'content': 'evidence', 'expected_sha256': ''}}
        gateway.execute(self.store, 'test', call, work, agent.DEFAULT_POLICY)
        with self.assertRaises(ResearchError): gateway.execute(self.store, 'test', call, work, agent.DEFAULT_POLICY)
        try: (work / 'linked').symlink_to(work / 'note.md')
        except OSError: return  # Windows may require elevated symlink privilege.
        with self.assertRaises(ResearchError): gateway.checked_path(work, 'linked')

    def test_lock_prevents_two_controllers(self):
        with endpoint([]) as (config, _):
            identity = self.create(config)
            with resource_lock(self.store, 'agent', identity):
                with self.assertRaises(LockBusy): agent.run(self.store, identity)

    def test_commit_gap_recovery_uses_durable_output_without_replay(self):
        write = ('write', 'write_file', {'path': 'once.md', 'content': 'only once', 'expected_sha256': ''})
        original = agent._settle
        def crash(store, state, outcome):
            if state['active']['kind'] == 'tool': raise RuntimeError('simulated controller crash after worker result')
            return original(store, state, outcome)
        with endpoint([response(write), response(report()), response(text='done')]) as (config, _):
            identity = self.create(config)
            with mock.patch.object(agent, '_settle', side_effect=crash): state = agent.run(self.store, identity)
            self.assertEqual(state['status'], 'interrupted')
            self.assertEqual((agent.workdir(self.store, identity) / 'once.md').read_text(), 'only once')
            state = agent.recover(self.store, identity)
            self.assertEqual(state['calls']['write']['status'], 'completed')
            agent.control(self.store, identity, 'resume'); state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['usage']['tool_calls'], 2)

    def test_uncertain_tool_effects_need_reconciliation(self):
        with endpoint([]) as (config, _): identity = self.create(config)
        state = agent.get(self.store, identity)
        state['calls']['x'] = {'id': 'x', 'name': 'list_files', 'arguments': {}, 'status': 'running'}
        state['queue'] = ['x']
        state['active'] = {'kind': 'tool', 'call_id': 'x', 'directory': 'lost', 'transport_id': 'transport', 'attempt_token': 'token', 'started_at': time.time()}
        state['status'] = 'interrupted'
        with self.store.tx(): self.store.set_value('agent:test', state)
        with self.assertRaises(ResearchError): agent.recover(self.store, identity)
        state = agent.recover(self.store, identity, {'actor': 'human', 'reason': 'inspected fixture', 'effects_checked': 'no worker or external effects'})
        self.assertIsNone(state['active']); self.assertEqual(state['queue'], [])
        self.assertEqual(state['calls']['x']['status'], 'failed')

    def test_source_drift_cannot_silently_change_resumed_session(self):
        with endpoint([]) as (config, _): identity = self.create(config)
        with mock.patch.object(agent, 'source_lock', return_value={'changed.py': 'a' * 64}):
            with self.assertRaises(ResearchError): agent.run(self.store, identity)

    def test_installed_bundle_never_loads_adjacent_research_skills(self):
        host = self.root / 'host'
        (host / 'ours').mkdir(parents=True); (host / '_shared').mkdir()
        (host / 'other').mkdir()
        write_json(host / 'manifest.yaml', {'skills': {'ours': {'entry': 'ours/SKILL.md'}}})
        (host / 'ours/SKILL.md').write_text('our skill')
        (host / '_shared/manual.md').write_text('our manual')
        (host / 'other/SKILL.md').write_text('inactive unrelated research skill')
        with mock.patch.object(gateway, 'SKILLS', host):
            self.assertEqual(set(agent.source_lock()), {'manifest.yaml', 'ours/SKILL.md', '_shared/manual.md'})
            with self.assertRaises(ResearchError): gateway.execute(self.store, 'test', {'name': 'read_skill', 'arguments': {'path': 'other/SKILL.md', 'offset': 0, 'limit': 100}}, self.root, agent.DEFAULT_POLICY)

    def test_recovery_uses_settled_duration_not_time_waiting_for_researcher(self):
        with endpoint([]) as (config, _): identity = self.create(config)
        state = agent.get(self.store, identity)
        state['calls']['x'] = {'id': 'x', 'name': 'list_files', 'arguments': {}, 'status': 'running'}
        state['queue'] = ['x']
        state['active'] = {'kind': 'tool', 'call_id': 'x', 'directory': 'settled', 'transport_id': 'transport', 'attempt_token': 'token', 'started_at': time.time() - 86400}
        with self.store.tx(): self.store.set_value('agent:test', state)
        path = agent.directory(self.store, identity) / 'attempts/settled'
        write_json(path / 'supervisor/result.json', {'attempt_id': 'transport', 'cleanup_verified': True, 'seconds': 2.0})
        write_json(path / 'output.json', {'attempt_token': 'token', 'ok': True, 'value': {}})
        state = agent.recover(self.store, identity)
        self.assertEqual(state['usage']['active_seconds'], 2.0)

    def test_controller_crash_between_attempts_is_recoverable_without_replay(self):
        with endpoint([]) as (config, _): identity = self.create(config)
        state = agent.get(self.store, identity); state['status'] = 'running'
        with self.store.tx(): self.store.set_value('agent:test', state)
        recovered = agent.recover(self.store, identity)
        self.assertEqual(recovered['status'], 'paused')
        self.assertEqual(recovered['attempts'], [])
        self.assertEqual(recovered['usage']['model_calls'], 0)

    def test_backup_restores_agent_files_reports_receipts_and_detects_missing_cas(self):
        from gresearch import maintenance
        item = report(); item[2]['evidence'] = ['inputs/note.md']
        with endpoint([response(item), response(text='fixture completed')]) as (config, _):
            identity = self.create(config)
            agent.import_material(self.store, identity, 'inputs/note.md', b'test evidence')
            state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'completed')
        backup = self.root / 'backup'
        maintenance.backup(self.store, backup)
        self.assertEqual(read_json(backup / 'backup.json')['agents'], [identity])
        restored_path = self.root / 'restored'
        maintenance.restore_backup(backup, restored_path)
        restored = Store(restored_path)
        try:
            self.assertTrue(restored.verify()['valid'])
            self.assertEqual(agent.inspect(restored, identity)['files']['inputs/note.md']['sha256'], digest(b'test evidence'))
            self.assertTrue((agent.directory(restored, identity) / 'attempts' / state['attempts'][0]['directory'] / 'output.json').exists())
            child = agent.fork(restored, identity, identity='restored-child')
            self.assertEqual(child['status'], 'ready')
            (restored.objects / state['reports'][0]['record_hash']).unlink()
            self.assertFalse(restored.verify()['valid'])
        finally: restored.close()

    def test_backup_refuses_running_agent_and_unsafe_agent_ids(self):
        from gresearch import maintenance
        with endpoint([]) as (config, _): identity = self.create(config)
        state = agent.get(self.store, identity); state['status'] = 'running'
        with self.store.tx(): self.store.set_value('agent:test', state)
        self.assertTrue(any(p.get('agent') == identity for p in maintenance.health(self.store)['workers_or_recovery']))
        with self.assertRaises(ResearchError): maintenance.backup(self.store, self.root / 'unsafe-backup')
        root = self.root / 'bad-manifest'; root.mkdir()
        write_json(root / 'backup.json', {'version': 1, 'files': {}, 'runs': [], 'agents': ['../escape']})
        with self.assertRaises(ResearchError): maintenance.backup_manifest(root)

    def test_environment_drift_blocks_resume(self):
        with endpoint([]) as (config, _): identity = self.create(config)
        original = agent.capture
        def changed(*args, **kwargs):
            value = original(*args, **kwargs)
            value['packages']['numpy'] = 'changed'
            from gresearch.core import fingerprint
            value['sha256'] = fingerprint({k: v for k, v in value.items() if k != 'sha256'})
            return value
        with mock.patch.object(agent, 'capture', side_effect=changed):
            with self.assertRaises(ResearchError): agent.run(self.store, identity)

    def test_empty_command_is_rejected_before_approval(self):
        with self.assertRaises(ResearchError): gateway.mode({'name': 'run_command', 'arguments': {'argv': [], 'purpose': 'invalid'}}, agent.DEFAULT_POLICY)

    def test_operation_help_selects_actual_dispatch_and_budget_is_visible(self):
        from gresearch.cli import OPERATIONS
        for name in OPERATIONS:
            self.assertEqual(gateway.operation_help(name, agent.DEFAULT_POLICY)['operation'], name)
        help = gateway.operation_help('adjust', agent.DEFAULT_POLICY)
        self.assertEqual(help['required_fields_from_dispatch'], ['pvalues'])
        self.assertEqual(help['optional_defaults'], {'method': "'holm'"})
        with endpoint([]) as (config, _): identity = self.create(config, budget={'model_calls': 8})
        state = agent.get(self.store, identity)
        self.assertIn('remaining_model_requests_including_this_one', agent.model_history(state)[0]['content'])
        self.assertNotIn('remaining_model_requests_including_this_one', state['history'][0]['content'])

    def test_continuation_preserves_parent_and_materials_with_new_budget(self):
        with endpoint([]) as (config, _): identity = self.create(config)
        agent.import_material(self.store, identity, 'inputs/note.md', b'original research evidence')
        parent = agent.get(self.store, identity)
        child = agent.fork(self.store, identity, identity='child', budget={'model_calls': 5})
        self.assertEqual(agent.get(self.store, identity), parent)
        self.assertEqual(child['budget']['model_calls'], 5)
        self.assertEqual(child['usage']['model_calls'], 0)
        self.assertEqual(child['parent']['session'], identity)
        self.assertEqual((agent.workdir(self.store, 'child') / 'inputs/note.md').read_bytes(), b'original research evidence')

    def test_full_package_is_deterministic_and_under_competition_limit(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('build_agent', ROOT / 'build_agent.py')
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        a, b = self.root / 'a.zip', self.root / 'b.zip'
        result = builder.build(a); builder.build(b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        self.assertEqual(result['skills'], 26)
        self.assertLess(result['zip_bytes'], 200_000_000)

    def test_human_only_operation_and_bad_tool_arguments_are_tool_errors(self):
        denied = ('approve', 'research_operation', {'operation': 'stage-feedback', 'arguments_json': '{"actor":"human"}'})
        malformed = ('bad', 'write_file', {'path': '../secret'})
        with endpoint([response(denied, malformed), response(report()), response(text='done')]) as (config, _):
            identity = self.create(config); state = agent.run(self.store, identity)
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(state['calls']['approve']['status'], 'failed')
        self.assertEqual(state['calls']['bad']['status'], 'failed')
        self.assertEqual(state['usage']['tool_calls'], 1)

    def test_ui_origin_protection_import_and_catalog(self):
        from gresearch.console import make_server
        server = make_server(self.store.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(origin + '/agent') as result:
                self.assertIn('Agent 工作台', result.read().decode())
            with urllib.request.urlopen(origin + '/api/agent/catalog') as result: self.assertEqual(len(json.load(result)['skills']), 26)
            body = canonical({'action': 'create', 'objective': 'UI test', 'config': {'provider': 'responses', 'base_url': 'https://example.com', 'model': 'm'}}).encode()
            with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(urllib.request.Request(origin + '/api/agent/action', body))
            headers = {'Origin': origin, 'X-Research-Token': server.research_token, 'Content-Type': 'application/json'}
            with urllib.request.urlopen(urllib.request.Request(origin + '/api/agent/action', body, headers)) as result: identity = json.load(result)['id']
            body = canonical({'session': identity, 'action': 'import', 'path': 'inputs/source.md', 'base64': 'ZXZpZGVuY2U='}).encode()
            with urllib.request.urlopen(urllib.request.Request(origin + '/api/agent/action', body, headers)) as result: self.assertEqual(result.status, 200)
            with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(origin + '/api/agent/artifact?session=' + identity + '&path=../state.sqlite3')
        finally: server.shutdown(); server.server_close(); thread.join(timeout=3)


if __name__ == '__main__': unittest.main()
