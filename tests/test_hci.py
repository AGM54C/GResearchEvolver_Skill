"""Executed HCI/evolution integration fixtures, not a human learning study."""
import copy
import json
import os
import shutil
import sys
import threading
import urllib.error
import urllib.request
from unittest import mock

from test_runtime import Workspace, manifest, stage, REPO
import test_runtime as runtime_tests
from gresearch.core import ResearchError, Store, canonical, digest, fingerprint, read_json
from gresearch.execution import run_workflow
from gresearch import hci, capabilities as cap, evolution, memory, attestation
from gresearch.cli import OPERATIONS, operation
from gresearch.console import make_server


def teaching(source_hash=None):
    claims = [{'id': 'c1', 'text': 'The estimate is uncertain.', 'status': 'interpretation', 'citations': []}]
    if source_hash:
        claims = [{'id': 'c1', 'text': '样本均值为 2。', 'status': 'source_reported', 'citations': [
            {'path': 'source.txt', 'sha256': source_hash, 'start': 0, 'end': 8, 'quote': '样本均值为 2。'}]}]
    return {'topic': 'Interpreting an estimate', 'audience': 'beginner',
            'intuition': 'An estimate is a summary of the observations.',
            'technical': 'Uncertainty depends on the sampling procedure.',
            'relevance': 'Choose the independent unit before testing.',
            'assumptions': ['A measurement protocol is defined.'],
            'limitations': ['This fixture does not establish a scientific finding.'],
            'questions': ['What is the independent unit?'], 'claims': claims}


class HciTests(Workspace):
    def start(self, stages=None, **policy):
        source = self.source('source.txt', '样本均值为 2。\n不可直接推断总体。')
        return self.store.create(manifest(stages, hci={'mode': 'every-stage', 'reviewers': ['researcher'], **policy}),
                                 inputs={'source.txt': source})

    def report(self, run, sid='analysis'):
        return hci.read(self.store, run, sid)

    def feedback(self, run, decision, sid='analysis', **kwargs):
        return hci.feedback(self.store, run, sid, self.report(run, sid)['receipt']['id'],
                            kwargs.get('actor', 'researcher'), decision, 'Scripted fixture decision, not user-study data')

    def explain(self, run, sid='analysis'):
        bundle = teaching(self.store.get(run)[1]['artifacts']['source.txt'])
        return hci.explain(self.store, run, sid, self.report(run, sid)['receipt']['id'], 'host-agent', bundle)

    def test_every_stage_gate_and_feedback_are_execution_constraints(self):
        run = self.start([stage('design'), stage('analysis', needs=['design'])], require_explanation=True)
        initial = self.report(run, 'design')
        state = run_workflow(self.store, run)
        self.assertEqual(state['status'], 'awaiting_review')
        self.assertEqual(state['stages']['analysis']['status'], 'pending')
        with self.assertRaises(ResearchError): self.feedback(run, 'approve', 'design')
        self.feedback(run, 'comment', 'design')
        self.feedback(run, 'explain', 'design')
        for action in ('resume', 'step'):
            with self.assertRaises(ResearchError): self.store.control(run, action)
        self.assertEqual(run_workflow(self.store, run)['status'], 'awaiting_review')
        self.explain(run, 'design')
        with self.assertRaises(ResearchError): self.feedback(run, 'approve', 'design', actor='not-a-reviewer')
        self.feedback(run, 'approve', 'design')
        self.assertEqual(run_workflow(self.store, run)['stages']['analysis']['status'], 'completed')
        self.explain(run)
        self.feedback(run, 'approve')
        self.assertEqual(run_workflow(self.store, run)['status'], 'completed')
        self.assertEqual(hci.read(self.store, run, 'design', initial['receipt']['id']), initial)
        self.assertTrue(self.store.verify()['valid'])

    def test_checkpoint_and_legacy_observe_modes(self):
        run = self.start([stage('design'), stage('analysis', needs=['design'])], mode='checkpoints', checkpoints=['analysis'])
        state = run_workflow(self.store, run)
        self.assertEqual(state['status'], 'awaiting_review')
        self.assertEqual(state['stages']['design']['review']['status'], 'optional')
        legacy = self.store.create(manifest())
        self.assertEqual(run_workflow(self.store, legacy)['status'], 'completed')
        self.assertIn('尚未收到反馈', self.report(legacy)['markdown'])
        self.assertTrue((self.store.work(legacy) / self.report(legacy)['receipt']['directory'] / 'report.md').is_file())

    def test_stale_reports_modified_inputs_outputs_and_optional_absence_rejected(self):
        run = self.start([stage(requires=['source.txt'], optional=['extra.txt'])])
        run_workflow(self.store, run)
        old = self.report(run)['receipt']['id']
        self.feedback(run, 'comment')
        with self.assertRaisesRegex(ResearchError, 'Stale'):
            hci.feedback(self.store, run, 'analysis', old, 'researcher', 'approve', 'stale')
        for path, value in [('source.txt', b'changed'), ('analysis.json', b'{"value":9}'), ('extra.txt', b'new')]:
            file = self.store.work(run) / path
            original = file.read_bytes() if file.exists() else None
            file.write_bytes(value)
            with self.assertRaises(ResearchError): self.feedback(run, 'approve')
            if original is None: file.unlink()
            else: file.write_bytes(original)
        self.feedback(run, 'approve')

    def test_exact_quotes_source_integrity_and_new_explanation_invalidates_approval(self):
        run = self.start()
        run_workflow(self.store, run)
        good = teaching(self.store.get(run)[1]['artifacts']['source.txt'])
        for field, value in [('quote', 'wrong'), ('end', 7), ('sha256', 'a' * 64)]:
            bundle = copy.deepcopy(good)
            bundle['claims'][0]['citations'][0][field] = value
            with self.assertRaises(ResearchError):
                hci.explain(self.store, run, 'analysis', self.report(run)['receipt']['id'], 'host-agent', bundle)
        self.explain(run)
        self.feedback(run, 'approve')
        self.explain(run)
        self.assertEqual(self.store.get(run)[1]['status'], 'awaiting_review')
        (self.store.work(run) / 'source.txt').write_text('changed', encoding='utf-8')
        with self.assertRaises(ResearchError): self.feedback(run, 'approve')

    def test_revision_creates_changed_branch_preserves_parent_and_pending_feedback(self):
        run = self.start(mode='observe')
        run_workflow(self.store, run)
        original = (self.store.work(run) / 'analysis.json').read_bytes()
        change = self.feedback(run, 'revise')['feedback']['id']
        with self.assertRaises(ResearchError): self.store.control(run, 'resume')
        with self.assertRaises(ResearchError): hci.revise(self.store, run, 'analysis', change, {})
        branch = hci.revise(self.store, run, 'analysis', change, {'analysis': {
            'command': [sys.executable, '-c', "open('analysis.json','w').write('{\"value\":2}')"],
            'rationale': 'Researcher requested a changed fixture value.'}})['child']
        self.assertEqual(run_workflow(self.store, branch)['status'], 'completed')
        self.assertEqual(read_json(self.store.work(branch) / 'analysis.json')['value'], 2)
        self.assertEqual((self.store.work(run) / 'analysis.json').read_bytes(), original)
        parent = self.store.get(run)[1]
        self.assertTrue(parent['intervention_hold'])
        self.assertEqual(parent['stages']['analysis']['feedback_resolutions'][0]['child'], branch)

    def test_cancel_is_terminal_and_all_stages_report_cancellation(self):
        run = self.start([stage(), stage('later', needs=['analysis'])])
        run_workflow(self.store, run)
        self.feedback(run, 'stop')
        self.assertEqual(self.report(run, 'later')['report']['phase'], 'cancelled_before_start')
        for decision in ('approve', 'revise'):
            with self.assertRaises(ResearchError): self.feedback(run, decision)
        with self.assertRaises(ResearchError): self.explain(run)
        self.feedback(run, 'comment')
        self.assertEqual(run_workflow(self.store, run)['status'], 'cancelled')

    def test_failed_retry_preserves_history_without_stale_failure_flags(self):
        code = "from pathlib import Path;import sys;sys.exit(3) if not Path('switch').exists() else Path('analysis.json').write_text('{}')"
        run = self.start([stage(code=code)], mode='observe')
        self.assertEqual(run_workflow(self.store, run)['status'], 'blocked')
        failed = self.report(run)
        self.assertEqual(failed['report']['facts']['exit_code'], 3)
        (self.store.work(run) / 'switch').write_text('retry fixture')
        self.store.control(run, 'retry', stage='analysis')
        pending = self.report(run)['report']
        self.assertNotIn('exit_code', pending['facts'])
        self.assertEqual(pending['cycle'], 2)
        self.assertEqual(run_workflow(self.store, run)['status'], 'completed')
        self.assertEqual(hci.read(self.store, run, 'analysis', failed['receipt']['id']), failed)
        cancelled = self.start([stage('failure', code='raise SystemExit(1)')], mode='observe')
        run_workflow(self.store, cancelled)
        self.store.control(cancelled, 'cancel')
        with self.assertRaises(ResearchError): self.store.control(cancelled, 'retry', stage='failure')

    def test_manual_host_stage_and_run_blocker_report(self):
        run = self.start([{'id': 'analysis', 'skill': 'research-explainer', 'outputs': ['answer.txt']}])
        self.assertEqual(run_workflow(self.store, run)['stages']['analysis']['status'], 'awaiting_artifact')
        (self.store.work(run) / 'answer.txt').write_text('A host-authored artifact.')
        self.assertEqual(self.store.finish(run, 'analysis')['status'], 'awaiting_review')
        self.assertEqual(self.report(run)['report']['run_status'], 'awaiting_review')
        blocked = self.start([stage(effect='read_network')])
        run_workflow(self.store, blocked)
        self.assertEqual(self.report(blocked)['report']['blocker']['category'], 'authorization')

    def test_reports_rebuild_archive_and_missing_cas(self):
        run = self.start()
        run_workflow(self.store, run)
        self.explain(run)
        self.feedback(run, 'comment')
        latest = self.report(run)
        report_path = self.store.work(run) / latest['receipt']['directory'] / 'report.md'
        report_path.write_text('tampered view')
        hci.rebuild(self.store, run)
        self.assertEqual(report_path.read_bytes(), self.store.blob(latest['receipt']['markdown']))
        archive = self.store.archive(run)
        other = Store(self.root / 'imported')
        try:
            imported = other.import_archive(archive['archive'])
            self.assertTrue(other.verify()['valid'])
            self.assertEqual(len(other.get(imported)[1]['stages']['analysis']['feedback']), 1)
            self.assertEqual(other.get(imported)[1]['status'], 'awaiting_review')
        finally: other.close()
        (self.store.objects / latest['receipt']['markdown']).unlink()
        self.assertFalse(self.store.verify()['valid'])
        with self.assertRaises(ResearchError): self.report(run)

    def test_graph_preserves_nodes_edges_feedback_and_is_idempotent(self):
        run = self.start()
        run_workflow(self.store, run)
        self.explain(run)
        self.feedback(run, 'comment')
        report = self.report(run)['receipt']['id']
        memory.put(self.store, 'project', {'nodes': [{'id': 'existing', 'type': 'paper'}], 'edges': []}, 0, actor='fixture', reason='fixture')
        result = hci.to_memory(self.store, run, 'analysis', report, 'project', 1, actor='researcher', reason='Keep provenance')
        graph = memory.get(self.store, 'project')['graph']
        self.assertIn('existing', {n['id'] for n in graph['nodes']})
        self.assertTrue({'stage_report', 'claim', 'researcher_feedback', 'source_span'}.issubset(n['type'] for n in graph['nodes']))
        self.assertTrue({'responds_to', 'explains_claim', 'cites'}.issubset(e['relation'] for e in graph['edges']))
        self.assertNotIn('supports', {e['relation'] for e in graph['edges']})
        again = hci.to_memory(self.store, run, 'analysis', report, 'project', result['revision'], actor='researcher', reason='Retry')
        self.assertTrue(again['unchanged'])
        with self.assertRaises(ResearchError):
            hci.to_memory(self.store, run, 'analysis', report, 'project', 1, actor='researcher', reason='Stale write')

    def test_console_report_and_stale_feedback_use_same_gate(self):
        run = self.start()
        run_workflow(self.store, run)
        server = make_server(self.store.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(origin + '/api/report?run=' + run + '&stage=analysis') as response:
                report_id = json.load(response)['receipt']['id']
            body = canonical({'action': 'feedback', 'run': run, 'stage': 'analysis', 'report_id': report_id,
                              'actor': 'researcher', 'decision': 'comment', 'reason': 'HTTP fixture'}).encode()
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(urllib.request.Request(origin + '/api/action', body))
            self.assertEqual(caught.exception.code, 403)
            headers = {'Content-Type': 'application/json', 'Origin': origin, 'X-Research-Token': server.research_token}
            with urllib.request.urlopen(urllib.request.Request(origin + '/api/action', body, headers)) as response:
                self.assertEqual(json.load(response)['status'], 'awaiting_review')
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(urllib.request.Request(origin + '/api/action', body, headers))
            self.assertEqual(caught.exception.code, 400)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_manifest_reserved_paths_and_heartbeat_do_not_duplicate_reports(self):
        for path in ('_reports/o.json', './_reports/o.json', '_capabilities/o.json', '_REPORTS/o.json', 'folder/../_reports/o.json'):
            with self.assertRaises(ResearchError): self.start([stage(outputs=[path])])
        run = self.start()
        count = len(self.store.get(run)[1]['stages']['analysis']['report_history'])
        with self.store.tx():
            _, state = self.store.get(run)
            state['heartbeat'] = 123
            self.store.save(run, state)
        self.assertEqual(len(self.store.get(run)[1]['stages']['analysis']['report_history']), count)


class CapabilityTests(Workspace):
    target = 'skill:research-explainer'

    def setup_capability(self, max_trials=3):
        candidate, incumbent = runtime_tests.EvolutionTests.setup_epoch(self, 'fixture-unbound', max_trials)
        protocol = copy.deepcopy(self.store.get_value('rsi:fixture-unbound')['protocol'])
        protocol.update(metric_description='Toy integer prediction exact match', failure_definition='Wrong or nonfinite output')
        cap.freeze(self.store, self.target, 'cap-epoch', protocol, self.root / 'evaluator', incumbent, ['{python}', 'agent.py'],
                   actor='host-agent', reason='Fixture baseline', reviewers=['researcher'])
        run = self.store.create(manifest())
        run_workflow(self.store, run)
        source = {'run': run, 'stage': 'analysis', 'report_id': hci.read(self.store, run, 'analysis')['receipt']['id']}
        return candidate, incumbent, protocol, source

    def propose(self, candidate, source, epoch='cap-epoch'):
        return cap.propose(self.store, self.target, epoch, candidate, ['{python}', 'agent.py'],
                           actor='host-agent', reason='Fixture improvement', sources=[source])

    def approve(self, proposal, trial):
        return cap.review(self.store, proposal['id'], trial['id'], actor='researcher', decision='approve', reason='Fixture review')

    def activate(self, proposal, revision=0):
        return cap.activate(self.store, proposal['id'], expected_revision=revision, actor='researcher', reason='Fixture adoption')

    def bound_run(self):
        task = self.source('task.json', '{"input":{"x":10}}')
        spec = stage(capability=self.target, requires=['task.json'], command=[
            '{python}', '{bundle}/agent.py', '--task', 'task.json', '--seed', '0', '--output', 'analysis.json'])
        return self.store.create(manifest([spec]), inputs={'task.json': task})

    def test_catalog_covers_registered_skills_tools_and_visual_targets(self):
        catalog = {r['id']: r for r in cap.catalog()}
        registry = read_json(REPO / 'skills/manifest.yaml')
        self.assertEqual(len(registry['skills']), 26)
        self.assertTrue(all('skill:' + s in catalog for s in registry['skills']))
        self.assertTrue(all('tool:' + op in catalog for op in OPERATIONS))
        self.assertTrue(catalog['skill:figure-mimic']['in_scope'])
        self.assertTrue(catalog['skill:slides-builder']['in_scope'])
        self.assertEqual(operation(self.store, 'capability-list', {}), cap.catalog())

    def test_agent_report_and_actual_feedback_can_source_a_proposal(self):
        from gresearch import agent
        candidate, _, _, _ = self.setup_capability()
        session = agent.create(self.store, 'Proposal provenance fixture', {'provider': 'responses', 'model': 'fixture', 'base_url': 'https://example.com'})
        report = agent._stage_report(self.store, session, {'stage': 'analysis', 'why': 'fixture', 'method': 'fixture',
            'findings': 'fixture only', 'explanation': 'fixture only', 'evidence': [], 'limitations': ['not a real study'], 'questions': ['review fixture?'], 'review_required': True})
        session.update(status='awaiting_researcher', waiting={'kind': 'report', 'id': report['id']})
        with self.store.tx(): agent._save(self.store, session, 'fixture_stage_report')
        session = agent.feedback(self.store, session['id'], reference=report['id'], actor='researcher', decision='approve', reason='fixture feedback')
        source = {'agent': session['id'], 'report_id': report['id'], 'feedback_id': session['feedback'][-1]['id']}
        proposal = self.propose(candidate, source)
        self.assertEqual(proposal['sources'][0]['report_hash'], report['record_hash'])
        with self.assertRaises(ResearchError): self.propose(candidate, {**source, 'feedback_id': 'invented'})
        session['reports'][0]['findings'] = 'changed after storage'
        with self.store.tx(): self.store.set_value('agent:' + session['id'], session)
        with self.assertRaises(ResearchError): self.propose(candidate, source)

    def test_project_experience_requires_pinned_outcome_evidence_and_still_needs_review(self):
        from gresearch import long_horizon as horizon
        candidate, _, _, _ = self.setup_capability()
        project = horizon.create(self.store, 'long-test', 'Test experience provenance')
        evidence = self.store.put(b'Actual fixture failure receipt; not scientific evidence')
        note = horizon.note(self.store, 'long-test', 'experience1', 'experience', 'Retry caused duplication',
            expected_revision=project['revision'], actor='agent:test', prediction={'expected':'no duplicates'}, evidence=[evidence], outcome={'observed':'duplicate'})
        current = horizon.get(self.store, 'long-test')
        source = {'project':'long-test', 'note':'experience1', 'note_hash':fingerprint(note), 'snapshot':current['snapshot']}
        proposal = self.propose(candidate, source)
        self.assertEqual(proposal['status'], 'proposed')
        with self.assertRaises(ResearchError): self.activate(proposal)
        with self.assertRaises(ResearchError): self.propose(candidate, {**source,'note_hash':'0'*64})
        forged = {k:v for k,v in current.items() if k!='snapshot'}
        forged['objective']='fabricated project snapshot never recorded'
        counterfeit = self.store.put(canonical(forged).encode('utf-8'))
        with self.assertRaisesRegex(ResearchError,'not recorded'): self.propose(candidate,{**source,'snapshot':counterfeit})
        self.assertTrue(self.store.verify()['valid'], self.store.verify())

    def test_real_adoption_pins_new_runs_and_archive_preserves_old_bundle(self):
        candidate, incumbent, protocol, source = self.setup_capability()
        old = self.bound_run()
        proposal = self.propose(candidate, source)
        (candidate / 'agent.py').write_text('raise RuntimeError("mutable source is not authoritative")')
        trial = cap.evaluate(self.store, proposal['id'])
        self.assertTrue(trial['passed'], trial['reasons'])
        self.assertFalse(trial['promoted'])
        with self.assertRaises(ResearchError): self.activate(proposal)
        with self.assertRaises(ResearchError):
            cap.review(self.store, proposal['id'], trial['id'], actor='host-agent', decision='approve', reason='Self review')
        self.approve(proposal, trial)
        self.assertEqual(self.activate(proposal)['revision'], 1)
        self.assertEqual(run_workflow(self.store, old)['status'], 'completed')
        self.assertEqual(read_json(self.store.work(old) / 'analysis.json')['prediction'], 10)
        new = self.bound_run()
        self.assertEqual(run_workflow(self.store, new)['status'], 'completed')
        self.assertEqual(read_json(self.store.work(new) / 'analysis.json')['prediction'], 11)
        child = self.store.fork(old, 'analysis')
        self.assertEqual(run_workflow(self.store, child)['status'], 'completed')
        self.assertEqual(read_json(self.store.work(child) / 'analysis.json')['prediction'], 10)
        archive = self.store.archive(old)
        other = Store(self.root / 'other')
        try:
            imported = other.import_archive(archive['archive'])
            replay = other.fork(imported, 'analysis')
            self.assertEqual(run_workflow(other, replay)['status'], 'completed')
            self.assertEqual(read_json(other.work(replay) / 'analysis.json')['prediction'], 10)
            self.assertTrue(other.verify()['valid'])
        finally: other.close()
        for action in (lambda: cap.evaluate(self.store, proposal['id']), lambda: self.approve(proposal, trial)):
            with self.assertRaises(ResearchError): action()
        restored = cap.rollback(self.store, self.target, 0, expected_revision=1, actor='researcher', reason='Fixture rollback')
        self.assertEqual(restored['revision'], 2)
        with self.assertRaises(ResearchError): self.propose(incumbent, source)
        with self.assertRaises(ResearchError): self.activate(proposal, 2)
        self.assertTrue(self.store.verify()['valid'])

    def test_generic_promotion_bypass_tie_and_rejected_proposal(self):
        candidate, incumbent, protocol, source = self.setup_capability()
        with self.assertRaises(ResearchError):
            evolution.evaluate(self.store, 'cap-epoch', candidate, ['{python}', 'agent.py'], promote=True)
        with self.assertRaises(ResearchError): evolution.rollback(self.store, 'cap-epoch', 0, 'Bypass')
        tie = self.root / 'tie'
        shutil.copytree(incumbent, tie)
        (tie / 'metadata.txt').write_text('changed bytes, no gain')
        proposal = self.propose(tie, source)
        trial = cap.evaluate(self.store, proposal['id'])
        self.assertFalse(trial['passed'])
        with self.assertRaises(ResearchError): self.approve(proposal, trial)
        cap.review(self.store, proposal['id'], trial['id'], actor='researcher', decision='reject', reason='No measured gain')
        with self.assertRaises(ResearchError): cap.evaluate(self.store, proposal['id'])
        self.assertEqual(cap.state(self.store, self.target)['revision'], 0)

    def test_provenance_stale_review_frozen_candidate_and_rollback_epoch(self):
        candidate, incumbent, protocol, source = self.setup_capability()
        with self.assertRaises(ResearchError): self.propose(candidate, {**source, 'feedback_id': 'fabricated'})
        feedback = hci.feedback(self.store, source['run'], 'analysis', source['report_id'], 'researcher', 'comment', 'Improve fixture')
        proposal = self.propose(candidate, {**source, 'feedback_id': feedback['feedback']['id']})
        trial = cap.evaluate(self.store, proposal['id'])
        self.approve(proposal, trial)
        # An altered evaluated receipt must invalidate its prior review.
        frozen = self.store.get_value('rsi:cap-epoch')
        frozen['trials'][-1]['seconds']['candidate'] += 1
        with self.store.tx(): self.store.set_value('rsi:cap-epoch', frozen)
        with self.assertRaises(ResearchError): self.activate(proposal)
        path = self.store.root / 'rsi/cap-epoch/proposals' / proposal['id'] / 'agent.py'
        path.write_text('changed materialization')
        with self.assertRaises(ResearchError): cap.evaluate(self.store, proposal['id'])
        with self.assertRaises(ResearchError):
            cap.rollback(self.store, self.target, 0, expected_revision=0, actor='host-agent', reason='Undeclared reviewer')
        cap.rollback(self.store, self.target, 0, expected_revision=0, actor='researcher', reason='Invalidate comparisons')
        with self.assertRaises(ResearchError): cap.evaluate(self.store, proposal['id'])
        with self.assertRaises(ResearchError): self.propose(candidate, source)
        cap.freeze(self.store, self.target, 'new-epoch', protocol, self.root / 'evaluator', incumbent, ['{python}', 'agent.py'],
                   actor='host-agent', reason='Fresh baseline after rollback', reviewers=['researcher'])
        self.assertEqual(self.propose(candidate, source, 'new-epoch')['base_revision'], 1)

    def test_pin_tampering_rejected_for_command_and_manual_finish(self):
        self.setup_capability()
        run = self.bound_run()
        pin = self.store.get(run)[1]['stages']['analysis']['capability_pin']
        (self.store.work(run) / pin['directory'] / 'agent.py').write_text('tampered')
        self.assertEqual(run_workflow(self.store, run)['stages']['analysis']['status'], 'failed')
        manual = self.store.create(manifest([{'id': 'analysis', 'capability': self.target, 'outputs': ['answer.txt']}]))
        run_workflow(self.store, manual)
        item = self.store.get(manual)[1]['stages']['analysis']
        (self.store.work(manual) / item['capability_pin']['directory'] / 'agent.py').write_text('tampered')
        (self.store.work(manual) / 'answer.txt').write_text('host result')
        with self.assertRaises(ResearchError): self.store.finish(manual, 'analysis')

    def test_extra_bundle_files_and_execution_mutation_are_not_silently_accepted(self):
        self.setup_capability()
        run = self.bound_run()
        pin = self.store.get(run)[1]['stages']['analysis']['capability_pin']
        (self.store.work(run) / pin['directory'] / 'extra.py').write_text('unrecorded code')
        self.assertEqual(run_workflow(self.store, run)['stages']['analysis']['status'], 'failed')
        code = "open('{bundle}/extra.txt','w').write('mutated');open('analysis.json','w').write('{}')"
        run = self.store.create(manifest([stage(capability=self.target, command=['{python}', '-c', code])]))
        state = run_workflow(self.store, run)
        self.assertEqual(state['stages']['analysis']['status'], 'failed')
        self.assertEqual(state['stages']['analysis']['failure']['category'], 'input_mutation')

    def test_fork_reports_explicitly_mark_reused_upstream_work(self):
        run = self.store.create(manifest([stage('upstream'), stage('analysis', needs=['upstream'])]))
        run_workflow(self.store, run)
        child = self.store.fork(run, 'analysis')
        facts = hci.read(self.store, child, 'upstream')['report']['facts']
        self.assertEqual(facts['inherited_from']['run'], run)
        self.assertNotIn('inherited_from', hci.read(self.store, run, 'upstream')['report']['facts'])

    def test_freeze_registration_is_atomic_and_missing_bundle_is_detected(self):
        candidate, incumbent, protocol, source = self.setup_capability()
        original = self.store.set_value
        def fail(key, value):
            if key.startswith('capability:'): raise RuntimeError('injected registration failure')
            return original(key, value)
        with mock.patch.object(self.store, 'set_value', side_effect=fail):
            with self.assertRaises(RuntimeError):
                cap.freeze(self.store, self.target, 'interrupted', protocol, self.root / 'evaluator', incumbent, ['{python}', 'agent.py'],
                           actor='host-agent', reason='Crash fixture', reviewers=['researcher'])
        self.assertIsNone(self.store.get_value('rsi:interrupted'))
        proposal = self.propose(candidate, source)
        (self.store.objects / proposal['candidate']['files']['self_test.txt']).unlink()
        self.assertFalse(self.store.verify()['valid'])
        with self.assertRaises(ResearchError): cap.evaluate(self.store, proposal['id'])

    def test_signed_evaluation_receipt_is_distinct_from_adoption_and_binds_results(self):
        keys = attestation.keygen(self.root / 'keys')
        context = {'epoch': 'fixture', 'trial': 'trial-fixture', 'protocol_hash': 'a' * 64,
                   'evaluator_hash': 'b' * 64, 'candidate_hash': 'c' * 64, 'result_hash': 'd' * 64}
        with mock.patch.dict(os.environ, {'GRESEARCH_SIGNING_KEY': keys['private_key_path']}):
            receipt = attestation.sign(keys, {**context, 'split': 'audit', 'passed': True, 'promoted': False, 'isolation': 'docker'})
        self.assertEqual(attestation.verify_evaluation(receipt, keys['public_key'], context)['result_hash'], 'd' * 64)
        with self.assertRaises(ResearchError): attestation.accept(self.store, receipt, keys['public_key'], context)
        with self.assertRaises(ResearchError):
            attestation.verify_evaluation(receipt, keys['public_key'], {**context, 'result_hash': 'e' * 64})
        altered = copy.deepcopy(receipt)
        altered['payload']['passed'] = False
        with self.assertRaises(ResearchError): attestation.verify_evaluation(altered, keys['public_key'], context)
