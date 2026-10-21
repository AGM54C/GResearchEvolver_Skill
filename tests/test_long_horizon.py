"""Real upstream/worker/storage fault tests; scripted LLM fixtures are not research evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/_shared/runtime'))
from gresearch import agent, agent_tools as gateway, long_horizon as horizon, memtx, memory, validity, maintenance
from gresearch.core import Store, ResearchError, canonical, fingerprint, read_json
from gresearch.execution import run_workflow
from test_agent import endpoint, response, report
from test_runtime import manifest, stage


CONFIG = {'provider': 'responses', 'base_url': 'http://127.0.0.1:1', 'model': 'fixture', 'max_output_tokens': 300, 'timeout': 5}


class LongTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / 'state')
        horizon.create(self.store, 'p', 'Test bounded research', constraints=['Never convert a hypothesis into a measured result.'])
    def tearDown(self):
        self.store.close(); self.tmp.cleanup()
    def session(self, identity='s', config=None, **kwargs):
        return agent.create(self.store, 'Test an integration, not a scientific conclusion', config or CONFIG,
                            identity=identity, long_project='p', **kwargs)
    def mem(self, op, args, **kwargs):
        return memtx.transact(self.store, 'p', op, args, expected_revision=memtx.get(self.store, 'p')['revision'], actor='tester', **kwargs)
    def commit(self, identity='a', value='observed', confidence=.8, **kwargs):
        tx = self.mem('begin', {'task_id': 'p', 'agent_id': 'tester', 'risk_level': 'external_action'})['result']
        rec = {'memory_id': identity, 'entity': identity, 'attribute': 'research', 'value': value, 'confidence': confidence,
               'source': {'type': 'tool', 'id': 'test', 'authority': .2}, **kwargs}
        self.mem('stage', {'tx_id': tx, 'observation': {}, 'extracted_memory': [rec]})
        return self.mem('commit', {'tx_id': tx}), tx
    def graph(self):
        graph = {'nodes': [{'id': 'a', 'type': 'evidence', 'text': 'observed', 'status': 'current', 'version': 1}], 'edges': []}
        memory.put(self.store, 'p', graph, 0, actor='tester', reason='test fixture')
        return graph, {'a': fingerprint(graph['nodes'][0])}
    def queue(self, state, call):
        identity, name, args = call
        state['calls'][identity] = {'id': identity, 'name': name, 'arguments': args, 'status': 'queued'}
        state['queue'].append(identity)
        with self.store.tx(): agent._save(self.store, state, 'test_queued_call')

    def test_copied_files_match_pin_and_host_imports_are_clean(self):
        vendor = ROOT / 'skills/_shared/vendor/memtx'
        metadata = read_json(vendor / 'UPSTREAM.json')
        self.assertEqual(metadata['commit'], '4e1124ccd5fd384857463020e3497aa73ec93be6')
        self.assertEqual(metadata['license'], 'NOASSERTION')
        for item in metadata['files']:
            raw = (vendor / item['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), item['sha256'])
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            self.assertEqual(blob, item['git_blob'])
        self.commit()
        self.assertNotIn('mock_tools', sys.modules)
        self.assertNotIn('schema', sys.modules)

    def test_upstream_commit_quarantine_revoke_and_roundtrip(self):
        self.commit('a')
        committed, _ = self.commit('summary', node_type='summary', derived_from=['a'])
        self.assertEqual(committed['result']['status'], 'committed')
        weak, _ = self.commit('weak', confidence=.1)
        self.assertEqual(weak['result']['status'], 'aborted')
        before = memtx.get(self.store, 'p')['state']
        self.assertEqual(next(r for r in before['records'] if r['memory_id'] == 'weak')['state'], 'quarantined')
        revoked = self.mem('revoke', {'memory_id': 'a', 'reason': 'source corrected'})
        self.assertEqual(set(revoked['result']['rolled_back_ids']), {'a', 'summary'})
        self.assertTrue(any(r['action'] == 'invalidated' for r in revoked['result']['rollback_log']))
        restored = Store(self.root / 'state')
        try:
            after = memtx.get(restored, 'p')['state']
            self.assertEqual(after['logical_date'], before['logical_date'])
            self.assertEqual(after['records'][0]['created_at'], before['records'][0]['created_at'])
            self.assertFalse(memtx.gate(restored, 'p', ['a'], 'report_stage')['allow'])
            self.assertTrue(restored.verify()['valid'], restored.verify())
        finally: restored.close()

    def test_gate_checks_every_actual_premise_and_validity(self):
        self.commit('safe')
        self.commit('weak', confidence=.1)
        self.assertTrue(memtx.gate(self.store, 'p', ['safe'], 'report_stage')['allow'])
        self.assertFalse(memtx.gate(self.store, 'p', ['safe', 'weak'], 'report_stage')['allow'])
        self.assertFalse(memtx.gate(self.store, 'p', [], 'report_stage')['allow'])
        self.mem('begin', {'task_id': 'p', 'agent_id': 'tester', 'risk_level': 'low'}, logical_date='2000-01-01')
        self.commit('expired', validity={'valid_until': '2001-01-01'})
        self.assertFalse(memtx.gate(self.store, 'p', ['expired'], 'report_stage')['allow'])

    def test_gate_rejects_missing_and_superseded_ancestors(self):
        self.commit('old', 'v1', entity='slot')
        self.commit('derived', derived_from=['old'])
        self.assertTrue(memtx.gate(self.store,'p',['derived'],'report_stage')['allow'])
        self.commit('new', 'v2', entity='slot')  # Upstream same-source correction.
        self.assertFalse(memtx.gate(self.store,'p',['derived'],'report_stage')['allow'])
        self.commit('orphan', derived_from=['does-not-exist'])
        self.assertFalse(memtx.gate(self.store,'p',['orphan'],'report_stage')['allow'])

    def test_boundary_rejects_overwrite_unknown_risk_and_bad_date(self):
        self.commit('a')
        with self.assertRaises(ResearchError): self.commit('a')
        with self.assertRaises(ResearchError): self.mem('begin', {'task_id': 'p', 'agent_id': 'tester', 'risk_level': 'typo'})
        with self.assertRaises(ResearchError): self.commit('bad-date', validity={'valid_until': 'whenever'})

    def test_snapshot_reads_exclude_later_commits_and_conflicts_quarantine(self):
        tx = self.mem('begin', {'task_id': 'p', 'agent_id': 'tester', 'risk_level': 'low'})['result']
        self.commit('a', 'left', entity='same')
        result = self.mem('retrieve', {'tx_id': tx, 'query': '', 'requester': {}, 'purpose': 'test'})
        self.assertEqual(result['result'], [])
        conflict, _ = self.commit('b', 'right', entity='same', source={'type':'tool','id':'another-source','authority':.2})
        self.assertEqual(conflict['result']['status'], 'aborted')

    def test_read_only_memtx_queries_preserve_reviewed_binding(self):
        state=self.session(); _,pins=self.graph(); self.commit('a')
        args=report()[2]
        horizon.bind_action(self.store,'s','report_stage',args,pins,{},'conclude','test')
        horizon.review(self.store,'p',pins,{},actor='researcher',reason='Review fixture')
        before=memtx.get(self.store,'p')
        self.mem('view',{'requester':{},'purpose':'inspect'})
        self.assertEqual(memtx.get(self.store,'p')['snapshot'],before['snapshot'])
        self.assertEqual(memtx.get(self.store,'p')['revision'],before['revision'])
        self.assertEqual(horizon.check_action(self.store,state,{'name':'report_stage','arguments':args})['purpose'],'conclude')

    def test_model_cannot_impersonate_writer_or_use_another_transaction(self):
        evidence = self.store.put(b'actual receipt')
        actor = 'agent:s'
        def transact(op, args):
            return memtx.transact(self.store, 'p', op, args, expected_revision=memtx.get(self.store, 'p')['revision'], actor=actor)
        tx = transact('begin', {'risk_level': 'external_action', 'task_id': 'other', 'agent_id': 'human'})['result']
        transact('stage', {'tx_id': tx, 'observation': {}, 'extracted_memory': [{'memory_id': 'a', 'entity': 'test', 'attribute': 'value',
            'value': 'x', 'confidence': .1, 'evidence_ids': [evidence], 'source': {'type': 'user', 'id': 'professor', 'authority': 1}}]})
        result = transact('commit', {'tx_id': tx})
        self.assertEqual(result['result']['status'], 'aborted')
        record = memtx.get(self.store, 'p')['state']['records'][0]
        self.assertEqual(record['source']['id'], actor)
        other = self.mem('begin', {'task_id': 'p', 'agent_id': 'human', 'risk_level': 'low'})['result']
        with self.assertRaises(ResearchError): transact('abort', {'tx_id': other, 'reason': 'steal'})

    def test_scientific_gate_review_change_and_value_binding(self):
        state = self.session(); graph, pins = self.graph()
        self.commit('a')
        call = {'name': 'report_stage', 'arguments': report()[2]}
        horizon.bind_action(self.store, 's', call['name'], call['arguments'], pins, {}, 'conclude', 'test')
        with self.assertRaises(horizon.ReviewRequired): horizon.check_action(self.store, state, call)
        horizon.review(self.store, 'p', pins, {}, actor='researcher', reason='Reviewed actual fixture for integration test only')
        self.assertEqual(horizon.check_action(self.store, state, call)['purpose'], 'conclude')
        graph['nodes'][0]['version'] = 2
        memory.put(self.store, 'p', graph, 1, actor='tester', reason='new evidence version')
        with self.assertRaisesRegex(ResearchError, 'state changed'): horizon.check_action(self.store, state, call)
        pins = {'a': fingerprint(graph['nodes'][0])}
        graph['nodes'][0]['text'] = 'a different finding'
        memory.put(self.store, 'p', graph, 2, actor='tester', reason='correction')
        pins = {'a': fingerprint(graph['nodes'][0])}
        horizon.bind_action(self.store, 's', call['name'], call['arguments'], pins, {}, 'conclude', 'test')
        with self.assertRaisesRegex(ResearchError, 'actual MemTX value'): horizon.check_action(self.store, state, call)

    def test_typed_cascade_preserves_an_indirect_alternative(self):
        graph = {'nodes': [{'id': i, 'type': 'claim', 'status': 'current'} for i in ['a','b','d','c','summary','unrelated']], 'edges': []}
        graph['nodes'][3]['support_sets'] = [['b'], ['d']]
        for i, (a,b,r) in enumerate([('a','b','derived_from'), ('b','c','supports'), ('d','c','supports'), ('c','summary','derived_from'), ('a','unrelated','related_to')]):
            graph['edges'].append({'id': str(i), 'from': a, 'to': b, 'relation': r})
        result = validity.invalidate(graph, ['a'], 'source revised')
        self.assertEqual(result['affected'], ['a','b'])
        self.assertEqual(result['preserved_with_other_support'], ['c'])
        changed = result['graph']; node = next(n for n in changed['nodes'] if n['id']=='summary')
        self.assertTrue(validity.check(changed, {'summary': fingerprint(node)})['eligible'])
        graph['edges'].append({'id': 'indirect', 'from': 'a', 'to': 'd', 'relation': 'depends_on'})
        self.assertEqual(set(validity.invalidate(graph, ['a'], 'both paths rely on a')['affected']), {'a','b','c','d','summary'})

    def test_condition_and_version_changes_block_until_revalidation(self):
        graph = {'nodes': [{'id':'data','type':'dataset','status':'current','version':2}, {'id':'claim','type':'claim','status':'current','conditions':{'population':'adults'}}],
                 'edges':[{'id':'e','from':'data','to':'claim','relation':'supports','expected_version':1}]}
        pins = {'claim': fingerprint(graph['nodes'][1])}
        result = validity.check(graph, pins, conditions={'population':'children'})
        self.assertFalse(result['eligible']); self.assertEqual(len(result['errors']), 2)
        graph['edges'][0]['expected_version']=2
        self.assertTrue(validity.check(graph,pins,conditions={'population':'adults'})['eligible'])

    def test_compaction_preserves_human_feedback_archives_and_budget(self):
        state = self.session(config={**CONFIG, 'max_input_chars': 50000})
        feedback = {'id':'f','actor':'professor','reason':'Keep negative results and never change the endpoint','decision':'revise','reference':'session','time':1}
        state['feedback'].append(feedback)
        original = {'role':'assistant','content':'old detail '*16000}
        state['history'].append(original)
        self.assertTrue(horizon.compact(self.store,state,tools_size=len(canonical(gateway.TOOLS))))
        self.assertIn(feedback['reason'], canonical(agent.model_history(state)))
        archive = json.loads(self.store.blob(state['context_archives'][0]['sha256']))
        self.assertIn(original, archive['history'])
        state['history'].append({'role':'assistant','content':'another detail '*10000})
        self.assertTrue(horizon.compact(self.store,state,tools_size=len(canonical(gateway.TOOLS))))
        self.assertEqual(state['usage']['model_calls'],0)
        self.assertEqual(len(state['context_archives']),2)
        self.assertTrue(self.store.verify()['valid'], self.store.verify())
        state['config']['max_input_chars']=500
        self.assertFalse(horizon.compact(self.store,state,tools_size=0))

    def test_shared_budget_across_forks_and_atomic_concurrent_reservations(self):
        state = self.session()
        with self.store.tx():
            p=horizon.get(self.store,'p'); p['budget']['model_calls']=1; horizon.save(self.store,p,'test_budget')
        child=agent.fork(self.store,'s',identity='child')
        self.assertEqual(child['long_project'],'p')
        barrier=threading.Barrier(2); outcomes=[]
        def reserve(sid):
            local=Store(self.root/'state')
            try:
                barrier.wait()
                try: horizon.reserve(local,'p',sid,sid,{'model_calls':1,'active_seconds':1}); outcomes.append('reserved')
                except horizon.BudgetExhausted: outcomes.append('blocked')
            finally: local.close()
        threads=[threading.Thread(target=reserve,args=(sid,)) for sid in ['s','child']]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)
        self.assertEqual(sorted(outcomes),['blocked','reserved'])
        self.assertEqual(horizon.get(self.store,'p')['spent']['model_calls'],1)
        result=agent.run(self.store,'child')
        self.assertEqual(result['status'],'project_budget_exhausted',result.get('last_error'))
        self.assertIsNone(result['active'])

    def test_automatic_two_context_handoffs_do_not_replay_tools(self):
        script=[response(('one','list_files',{}),text='first-epoch '*5000),
                response(('two','list_files',{}),text='second-epoch '*5000),
                response(('human','ask_researcher',{'question':'Choose the next route','options':['review']}))]
        with endpoint(script) as (config, requests):
            self.session(config={**config,'max_input_chars':50000})
            state=agent.run(self.store,'s')
        self.assertEqual(state['status'],'awaiting_researcher',state.get('last_error'))
        self.assertEqual(len(state['context_archives']),2)
        self.assertEqual(len(requests),3)
        self.assertEqual(state['usage']['tool_calls'],3)
        self.assertEqual(len(state['calls']),3)
        self.assertTrue(self.store.verify()['valid'],self.store.verify())

    def test_fork_can_page_full_parent_history_not_only_recent_reports(self):
        state=self.session()
        state['history'].append({'role':'user','content':'old observation only in the parent'})
        with self.store.tx(): agent._save(self.store,state,'test_parent')
        child=agent.fork(self.store,'s',identity='child')
        raw=self.store.blob(child['parent']['archive_hash']).decode('utf-8')
        page=horizon.read_context(self.store,'child',0,raw.index('old observation'),80)
        self.assertIn('old observation only in the parent',page['text'])
        self.assertEqual(page['sha256'],child['parent']['archive_hash'])

    def test_external_artifact_quota_is_checked_before_copy(self):
        state=self.session(policy={'max_workspace_bytes':1})
        run=self.store.create(manifest(),'large')
        horizon.track_job(self.store,'p',run,actor='researcher')
        state.update(status='waiting_external',waiting={'kind':'external','id':run,'reason':'wait'})
        with self.store.tx(): agent._save(self.store,state,'test_wait')
        run_workflow(self.store,run)
        with self.assertRaisesRegex(ResearchError,'quota'): horizon.tick(self.store,'p')
        self.assertFalse((agent.workdir(self.store,'s')/'jobs').exists())

    def test_crash_recovery_settles_reserved_attempt_once(self):
        self.session()
        with mock.patch.object(agent.process_runner,'run',side_effect=RuntimeError('controller dies after intent')):
            state=agent.run(self.store,'s')
        self.assertEqual(state['status'],'interrupted')
        token=state['active']['attempt_token']
        self.assertEqual(horizon.get(self.store,'p')['reservations'][token]['status'],'reserved')
        agent.recover(self.store,'s')
        project=horizon.get(self.store,'p')
        self.assertEqual(project['spent']['model_calls'],1)
        self.assertEqual(project['reservations'][token]['status'],'settled')
        horizon.settle(self.store,'p',token,0)
        self.assertEqual(horizon.get(self.store,'p')['spent'],project['spent'])
        self.assertTrue(self.store.verify()['valid'],self.store.verify())

    def test_human_direction_invalidates_binding_and_predictions_are_immutable(self):
        state=self.session(); args=report()[2]
        horizon.bind_action(self.store,'s','report_stage',args,{}, {},'explore','provisional')
        p=horizon.get(self.store,'p')
        note=horizon.note(self.store,'p','route1','route','Test a route',expected_revision=p['revision'],prediction={'expected':'reduce error'},actor='agent:s')
        with self.assertRaises(ResearchError):
            horizon.note(self.store,'p','route1','route','Rewrite forecast',expected_revision=horizon.get(self.store,'p')['revision'],prediction={'expected':'increase error'},actor='agent:s')
        horizon.decide(self.store,'p','Stop this route; preserve its negative result',actor='professor',target='route1',expected_hash=fingerprint(note))
        with self.assertRaisesRegex(ResearchError,'direction changed'):
            horizon.check_action(self.store,state,{'name':'report_stage','arguments':args})
        self.assertEqual(agent.get(self.store,'s')['status'],'paused')
        self.assertTrue(agent.get(self.store,'s')['feedback'])

    def test_actual_external_workflow_wait_import_pause_and_failure(self):
        state=self.session()
        run=self.store.create(manifest(), 'experiment')
        horizon.track_job(self.store,'p',run,actor='researcher')
        state.update(status='waiting_external',waiting={'kind':'external','id':run,'reason':'actual result'})
        with self.store.tx(): agent._save(self.store,state,'test_wait')
        with mock.patch.object(agent,'run',side_effect=AssertionError('No model polling')):
            horizon.watch(self.store,'p',seconds=.1,interval=.1)
        self.assertEqual(agent.get(self.store,'s')['usage']['model_calls'],0)
        agent.control(self.store,'s','pause')
        self.assertEqual(run_workflow(self.store,run)['status'],'completed')
        horizon.tick(self.store,'p')
        self.assertEqual(agent.get(self.store,'s')['status'],'paused')
        agent.control(self.store,'s','resume')
        self.assertEqual(horizon.tick(self.store,'p')['awakened'],['s'])
        ready=agent.get(self.store,'s')
        self.assertEqual(ready['status'],'ready')
        self.assertTrue(list((agent.workdir(self.store,'s')/'jobs/experiment').glob('*/analysis.json')))
        self.assertEqual(horizon.tick(self.store,'p')['awakened'],[])
        failed=self.store.create(manifest([stage(code='raise SystemExit(5)')]),'bad')
        horizon.track_job(self.store,'p',failed,actor='researcher')
        ready.update(status='waiting_external',waiting={'kind':'external','id':failed,'reason':'test failure'})
        with self.store.tx(): agent._save(self.store,ready,'test_wait_bad')
        self.assertEqual(run_workflow(self.store,failed)['status'],'blocked')
        horizon.tick(self.store,'p')
        self.assertEqual(agent.get(self.store,'s')['status'],'awaiting_researcher')
        with self.assertRaises(ResearchError): agent.fork(self.store,'s',identity='bypass')

    def test_real_worker_scientific_review_then_complete_and_backup(self):
        graph,pins=self.graph(); self.commit('a')
        args=report()[2]
        binding={'name':'report_stage','arguments_json':canonical(args),'requires_json':canonical(pins),'conditions_json':'{}','purpose':'conclude','reason':'integration test only'}
        with endpoint([response(('bind','bind_action',binding),report()),response(text='Integration completed, not scientific proof')]) as (config,requests):
            self.session(config=config)
            state=agent.run(self.store,'s')
            self.assertEqual(state['status'],'awaiting_researcher',state.get('last_error'))
            self.assertEqual(state['waiting']['kind'],'scientific_review')
            agent.feedback(self.store,'s',reference=state['waiting']['id'],actor='researcher',decision='approve',reason='Reviewed test premises; no real scientific finding')
            state=agent.run(self.store,'s')
            self.assertEqual(state['status'],'completed',state.get('last_error'))
        self.assertEqual(len(requests),2)
        project=horizon.get(self.store,'p')
        self.assertEqual(project['spent']['model_calls'],2)
        self.assertEqual(project['spent']['tool_calls'],2)
        self.assertTrue(all(r['status']=='settled' for r in project['reservations'].values()))
        self.assertTrue(self.store.verify()['valid'],self.store.verify())
        maintenance.backup(self.store,self.root/'backup')
        maintenance.restore_backup(self.root/'backup',self.root/'restored')
        restored=Store(self.root/'restored')
        try:
            self.assertEqual(horizon.get(restored,'p')['spent'],project['spent'])
            self.assertTrue((restored.root/'projects/p/report.md').is_file())
            self.assertEqual(memtx.get(restored,'p')['state'],memtx.get(self.store,'p')['state'])
        finally: restored.close()


if __name__=='__main__': unittest.main()
