from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'skills' / '_shared' / 'runtime'))
from gresearch.core import ResearchError, Store, compare_runs, digest, fingerprint, native_path, read_json, safe_path, validate_manifest, verify_archive, write_json
from gresearch.execution import command_argv, process_exists, recover, run_workflow
from gresearch import statistics as stats, evidence, evolution, literature, review, projects
from gresearch import retrieval
from gresearch.console import make_server


def stage(name='analysis', code=None, **kwargs):
    return {'id': name, 'outputs': [name + '.json'], 'command': [sys.executable, '-c', code or f"import json;open('{name}.json','w').write(json.dumps({{'value':1}}))"], **kwargs}


def manifest(stages=None, **kwargs):
    return {'version': 2, 'objective': 'test scientific process', 'authorization': {'effects': ['local']},
            'budget': {'seconds': 30, 'cost': 0}, 'stages': stages or [stage()], **kwargs}


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gresearch-tests-')
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'store')

    def tearDown(self):
        self.store.close()
        assert self.root.name.startswith('gresearch-tests-') and self.root.parent.resolve() == Path(tempfile.gettempdir()).resolve()
        self.temp.name = str(native_path(self.root))
        self.temp.cleanup()

    def source(self, name, value):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value, encoding='utf-8')
        return p


class WorkflowTests(Workspace):
    def test_real_execution_and_raw_invocation(self):
        run = self.store.create(manifest())
        result = run_workflow(self.store, run)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(read_json(self.store.work(run) / 'analysis.json')['value'], 1)
        events = self.store.events(run)
        self.assertTrue(any(x['kind'] == 'invocation' and x['payload']['data']['argv'][0] == sys.executable for x in events))
        self.assertTrue(self.store.verify()['valid'])

    def test_stale_outputs_cannot_satisfy_new_run(self):
        run = self.store.create(manifest([stage(code='pass')]))
        write_json(self.store.work(run) / 'analysis.json', {'old': True})
        result = run_workflow(self.store, run)
        self.assertEqual(result['stages']['analysis']['status'], 'failed')
        self.assertFalse((self.store.work(run) / 'analysis.json').exists())

    def test_mutated_seed_input_rejected_before_command(self):
        original = self.source('seed.csv', 'original')
        run = self.store.create(manifest([stage(requires=['data.csv'])]), inputs={'data.csv': original})
        (self.store.work(run) / 'data.csv').write_text('tampered')
        result = run_workflow(self.store, run)
        self.assertEqual(result['stages']['analysis']['error']['changed_inputs'], ['data.csv'])

    def test_stage_cannot_mutate_required_input(self):
        original = self.source('seed.txt', 'original')
        code = "open('data.txt','w').write('changed');open('analysis.json','w').write('{}')"
        run = self.store.create(manifest([stage(code=code, requires=['data.txt'])]), inputs={'data.txt': original})
        result = run_workflow(self.store, run)
        self.assertEqual(result['stages']['analysis']['mutated_inputs'], ['data.txt'])
        self.assertEqual(result['stages']['analysis']['status'], 'failed')

    def test_dependency_errors_and_independent_progress(self):
        stages = [stage('bad', 'raise SystemExit(7)'), stage('blocked', needs=['bad'], requires=['bad.json']), stage('good')]
        run = self.store.create(manifest(stages))
        result = run_workflow(self.store, run)
        self.assertEqual(result['stages']['good']['status'], 'completed')
        self.assertEqual(result['stages']['blocked']['status'], 'pending')
        self.assertEqual(result['status'], 'blocked')

    def test_manifest_cycles_missing_edges_and_duplicate_outputs(self):
        for specs in ([stage('a', needs=['b']), stage('b', needs=['a'])],
                      [stage('a'), stage('b', requires=['a.json'])],
                      [stage('a'), {**stage('b'), 'outputs': ['a.json']}]):
            with self.assertRaises(ResearchError): validate_manifest(manifest(specs))

    def test_authorization_and_budget_fail_closed(self):
        run = self.store.create(manifest([stage(effect='external_write')]))
        self.assertEqual(run_workflow(self.store, run)['status'], 'blocked')
        run2 = self.store.create(manifest([stage(cost_estimate=1)]))
        self.assertEqual(run_workflow(self.store, run2)['status'], 'blocked')
        self.assertFalse((self.store.work(run2) / 'analysis.json').exists())

    def test_retry_cost_reserved_and_timeout(self):
        m = manifest([stage(code='import time;time.sleep(1)', timeout=.1)])
        run = self.store.create(m)
        self.assertTrue(run_workflow(self.store, run)['stages']['analysis']['timeout'])
        with self.assertRaises(ResearchError):
            validate_manifest(manifest([stage(retries=1)]))
        run = self.store.create(manifest([stage(cost_estimate=1, retries=1, idempotent=True)], budget={'seconds': 30, 'cost': 1}))
        self.assertEqual(run_workflow(self.store, run)['status'], 'blocked')

    def test_manual_submission_rechecks_inputs(self):
        data = self.source('data.txt', 'input')
        spec = stage(requires=['data.txt']); spec.pop('command')
        run = self.store.create(manifest([spec]), inputs={'data.txt': data})
        self.assertEqual(run_workflow(self.store, run)['stages']['analysis']['status'], 'awaiting_artifact')
        write_json(self.store.work(run) / 'analysis.json', {'manual': True})
        (self.store.work(run) / 'data.txt').write_text('changed')
        with self.assertRaises(ResearchError): self.store.finish(run, 'analysis')
        (self.store.work(run) / 'data.txt').write_text('input')
        self.store.finish(run, 'analysis')
        self.assertEqual(run_workflow(self.store, run)['status'], 'completed')

    def test_breakpoint_step_fork_and_checkpoint_fidelity(self):
        stages = [stage('first'), stage('second', needs=['first'], requires=['first.json'])]
        run = self.store.create(manifest(stages, breakpoints=['second']))
        self.assertEqual(run_workflow(self.store, run)['status'], 'paused')
        self.store.control(run, 'step')
        self.assertEqual(run_workflow(self.store, run)['stages']['second']['status'], 'completed')
        child = self.store.fork(run, 'second', {'second': {'command': [sys.executable, '-c', "open('second.json','w').write('{\"value\":2}')"]}})
        self.assertEqual(read_json(self.store.work(child) / 'first.json')['value'], 1)
        self.assertEqual(run_workflow(self.store, child)['status'], 'paused')
        self.store.control(child, 'resume')
        self.assertEqual(run_workflow(self.store, child)['status'], 'completed')
        self.assertEqual(read_json(self.store.work(child) / 'second.json')['value'], 2)
        self.assertEqual(read_json(self.store.work(run) / 'second.json')['value'], 1)

    def test_cancel_managed_process(self):
        run = self.store.create(manifest([stage(code='import time;time.sleep(20)')]))
        errors = []
        def worker():
            store = Store(self.store.root)
            try: run_workflow(store, run)
            except Exception as exc: errors.append(exc)
            finally: store.close()
        thread = threading.Thread(target=worker)
        thread.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any(x['kind'] == 'invocation' for x in self.store.events(run)): time.sleep(.02)
        self.store.control(run, 'cancel')
        thread.join(timeout=8)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)
        self.assertEqual(self.store.get(run)[1]['status'], 'cancelled')

    def test_liveness_check_never_kills_current_worker(self):
        import os
        self.assertTrue(process_exists(os.getpid()))
        run = self.store.create(manifest())
        with self.store.tx():
            _, state = self.store.get(run); state['worker'] = str(os.getpid()) + '-test'; self.store.save(run, state)
        with self.assertRaises(ResearchError): recover(self.store, run)

    def test_archive_noop_portability_and_tamper_detection(self):
        run = self.store.create(manifest())
        run_workflow(self.store, run)
        first = self.store.archive(run)
        self.assertTrue(self.store.archive(run)['unchanged'])
        portable = self.root / 'portable'
        shutil.copytree(first['archive'], portable)
        self.assertTrue(verify_archive(portable)['valid'])
        other = Store(self.root / 'restored')
        try:
            child = other.import_archive(portable)
            self.assertEqual(read_json(other.work(child) / 'analysis.json')['value'], 1)
            self.assertTrue(other.verify()['valid'])
            fork = other.fork(child, 'analysis')
            self.assertEqual(run_workflow(other, fork)['status'], 'completed')
        finally: other.close()
        (portable / 'artifacts' / 'analysis.json').write_text('tampered')
        self.assertFalse(verify_archive(portable)['valid'])

    def test_events_and_cas_tampering(self):
        run = self.store.create(manifest())
        h = self.store.put(b'evidence')
        (self.store.objects / h).write_bytes(b'bad')
        self.assertFalse(self.store.verify()['valid'])
        with self.assertRaises(ResearchError): self.store.blob(h)
        with self.store.tx(): self.store.db.execute("UPDATE events SET kind='forged'")
        self.assertTrue(any(x.startswith('event:') for x in self.store.verify()['errors']))

    def test_path_escape_and_ssh_quoting(self):
        for p in ('../outside', 'C:/outside', '/root', '..\\outside', '//host/share', 'nested/../../outside', 'nested/../alias'):
            with self.subTest(path=p), self.assertRaises(ResearchError): safe_path(self.root, p)
        argv = command_argv({'command': ['python3', 'analysis.py', 'a; touch bad'], 'ssh': {'host': 'user@example.org', 'cwd': '/tmp/research-1'}})
        self.assertIn("'a; touch bad'", argv[-1])
        with self.assertRaises(ResearchError): command_argv({'command': ['true'], 'ssh': {'host': '-ProxyCommand=bad', 'cwd': '/tmp/test'}})


class ScientificTests(Workspace):
    def test_clustered_pairs_not_seed_pseudoreplication(self):
        rows = [{'task': str(t), 'seed': s, 'candidate': t + 1, 'incumbent': t} for t in range(4) for s in range(10)]
        result = stats.paired_analysis(rows, resamples=400)
        self.assertEqual(result['tasks'], 4)
        self.assertEqual(result['pairs'], 40)
        self.assertEqual(result['ci'], [1, 1])
        with self.assertRaises(ResearchError): stats.paired_analysis(rows + [rows[0]])

    def test_invalid_samples_and_nonfinite_rejected(self):
        for rows in ([], [{'task': 'x', 'seed': 0, 'candidate': 2, 'incumbent': 1}],
                     [{'task': str(i), 'seed': 0, 'candidate': math.nan, 'incumbent': 1} for i in range(3)]):
            with self.assertRaises(ResearchError): stats.paired_analysis(rows)
        with self.assertRaises(ResearchError): stats.adjust_pvalues([1.2])

    def test_multiple_comparisons_and_meta_estimand(self):
        self.assertEqual(stats.adjust_pvalues([.01, .04, .03])['adjusted'], [.03, .06, .06])
        data = {'common_estimand': 'mean difference in units', 'independent_units_confirmed': True,
                'studies': [{'study_id': 'a', 'effect': 1, 'variance': 1}, {'study_id': 'b', 'effect': 3, 'variance': 1}]}
        result = stats.meta_analysis(data)
        self.assertEqual(result['fixed']['estimate'], 2)
        self.assertAlmostEqual(result['tau2'], 1)
        data['studies'][1]['study_id'] = 'a'
        with self.assertRaises(ResearchError): stats.meta_analysis(data)

    def test_sequential_validity_not_inferred(self):
        with self.assertRaises(ResearchError): stats.sequential_evidence({'tests': [{'p': .01}]})
        data = {'null': 'H0', 'design_hash': 'frozen', 'validity_review': 'external derivation',
                'tests': [{'id': 't1', 'subnull': 'h01', 'null_implies_subnull': 'proof', 'conditional_validity': 'external derivation',
                           'data_use': 'independent fresh sample', 'e_value': 25}]}
        self.assertTrue(stats.sequential_evidence(data)['reject_under_declared_assumptions'])
        data['tests'].append(data['tests'][0])
        with self.assertRaises(ResearchError): stats.sequential_evidence(data)

    def test_data_leakage_and_negative_result(self):
        result = stats.data_audit({'target': 'y', 'split_column': 'split', 'group_column': 'subject',
                                  'rows': [{'y': 1, 'copy': 1, 'subject': 'p1', 'split': 'train'}, {'y': 2, 'copy': 2, 'subject': 'p1', 'split': 'test'}]})
        self.assertEqual(len(result['leakage_flags']), 2)
        result = stats.paired_analysis([{'task': str(i), 'seed': 0, 'candidate': 1, 'incumbent': 1} for i in range(4)])
        self.assertEqual(result['mean_gain'], 0)

    def test_atomic_graph_quote_scope_and_binding(self):
        p = self.source('result.json', '{"metric": 2}')
        h = digest(p.read_bytes())
        graph = {'nodes': [{'id': 'r', 'type': 'result', 'path': p.name, 'sha256': h},
                           {'id': 'c', 'type': 'claim', 'text': 'metric is 2', 'scope': 'synthetic run', 'certainty': 'observed', 'status': 'verified'}],
                 'edges': [{'id': 'e', 'from': 'r', 'to': 'c', 'relation': 'supports',
                            'evidence': {'path': p.name, 'sha256': h, 'quote': '"metric": 2'},
                            'adjudication': {'status': 'accepted', 'reviewer': 'test-human', 'rationale': 'exact binding', 'scope_checked': True}}]}
        self.assertTrue(evidence.validate_graph(graph, self.root)['structurally_valid'])
        graph['edges'][0]['evidence']['quote'] = 'metric is 99'
        self.assertFalse(evidence.validate_graph(graph, self.root)['structurally_valid'])
        graph['nodes'][1]['quantities'] = [{'value': 2}, {'value': 3}]
        self.assertFalse(evidence.validate_graph(graph, self.root)['structurally_valid'])

    def test_writing_numbers_in_prose_and_table(self):
        doc = 'gain 2.00 units\n| invented | 9.00 |'
        result = {'id': 'r', 'value': 2, 'metric': 'gain', 'condition': 'test', 'unit': 'units', 'run': 'run-a'}
        source = self.source('measured.json', json.dumps({'result': result}))
        result['source'] = {'kind': 'computed', 'path': 'measured.json', 'sha256': digest(source.read_bytes()), 'pointer': ['result']}
        binding = {**result, 'start': 5, 'end': 9, 'literal': '2.00', 'result_id': 'r', 'decimals': 2}
        ledger = {'root': str(self.root), 'results': [result], 'bindings': [binding]}
        self.assertFalse(evidence.audit_writing(doc, ledger)['passed'])
        self.assertTrue(evidence.audit_writing('gain 2.00 units', ledger)['passed'])
        ledger['bindings'][0]['condition'] = 'other'
        self.assertFalse(evidence.audit_writing('gain 2.00 units', ledger)['passed'])

    def test_review_conflict_requires_adjudication(self):
        protocol = {'question': 'Q', 'eligibility': 'E', 'databases': ['fixture'], 'searches': ['s'], 'outcomes': ['gain'], 'reviewers': ['r1', 'r2']}
        review.freeze_review(self.store, 's', protocol)
        decisions = [{'record': 'p', 'stage': 'title_abstract', 'reviewer': who, 'decision': answer, 'reason': 'reviewed', 'independently_assessed': True}
                     for who, answer in [('r1', 'include'), ('r2', 'exclude')]]
        review.screen(self.store, 's', decisions)
        inventory = {'records': [{'id': 'p', 'study_id': 'study1'}]}
        report = review.review_report(self.store, 's', inventory)
        self.assertEqual(len(report['conflicts']), 1)
        self.assertFalse(report['ready_for_synthesis'])
        review.adjudicate(self.store, 's', [{'record': 'p', 'stage': 'title_abstract', 'reviewer': 'consensus', 'decision': 'include', 'reason': 'full criteria'}])
        full = [{**d, 'stage': 'full_text', 'decision': 'unavailable'} for d in decisions]
        review.screen(self.store, 's', full)
        report = review.review_report(self.store, 's', inventory)
        self.assertEqual(report['counts']['reports_unavailable'], 1)
        self.assertEqual(report['counts']['full_text_excluded'], 0)
        with self.assertRaises(ResearchError): review.screen(self.store, 's', decisions)

    def test_intervention_noncompliance_and_quality_not_truth(self):
        self.assertEqual(review.intervention_assessment({'followed': False})['classification'], 'Inconclusive')
        self.assertFalse(review.assess_quality({'studies': []})['record_complete'])

    def test_reference_import_dedup_and_lossless_export(self):
        path = self.source('refs.ris', 'TY  - JOUR\nID  - a\nTI  - Sample\nDO  - https://doi.org/10.1234/test\nAU  - Smith, A\nER  -\nTY  - JOUR\nID  - b\nTI  - Sample\nDO  - 10.1234/test\nER  -\n')
        imported = literature.import_references(path)
        unique = literature.deduplicate(imported['records'])
        self.assertEqual(unique['unique_count'], 1)
        self.assertEqual(unique['records'][0]['aliases'][0]['id'], 'b')
        unique['records'][0]['notes'] = ['keep note']
        dest = self.root / 'out.bib'
        literature.export_references(unique['records'], dest, 'bibtex')
        self.assertIn('Smith', dest.read_text())
        self.assertEqual(read_json(str(dest) + '.preserved.json')['records'][0]['notes'], ['keep note'])
        self.assertEqual(len(literature.import_references(dest)['records']), 1)
        collision = literature.deduplicate([{'id': 'a', 'DOI': '10.1/x', 'title': 'A'}, {'id': 'b', 'DOI': '10.1/x', 'title': 'B'}])
        self.assertEqual(len(collision['collisions']), 1)

    def test_nbib_endnote_xml_csl_and_bibtex(self):
        fixtures = [('a.nbib', 'PMID- 1\nTI  - Title\nAID - 10.1234/test [doi]\n\n'),
                    ('a.enw', '%0 Journal Article\n%T Title\n%A Smith\n%R 10.1234/test\n\n'),
                    ('a.xml', '<xml><records><record><rec-number>1</rec-number><titles><title>Title</title></titles></record></records></xml>'),
                    ('p.xml', '<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>Title</ArticleTitle></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'),
                    ('a.json', '[{"id":"1","title":"Title"}]'),
                    ('a.bib', '@article{x, title={A {Nested} Title}, year=2024, doi="10.1234/test"}')]
        for name, content in fixtures:
            with self.subTest(name=name): self.assertEqual(len(literature.import_references(self.source(name, content))['records']), 1)
        with self.assertRaises(ResearchError): literature.bib_records('@string{foo = "bar"}')

    def test_monitor_missing_is_not_retraction(self):
        a = {'id': 'a', 'title': 'first'}
        self.assertEqual(literature.monitor(self.store, 'm', [a])['new'], ['a'])
        self.assertEqual(literature.monitor(self.store, 'm', [{**a, 'title': 'revised'}])['changed'], ['a'])
        report = literature.monitor(self.store, 'm', [])
        self.assertEqual(report['missing_from_current_query'], ['a'])
        self.assertFalse(report['absence_means_retracted'])

    def test_grant_arithmetic_and_proof_unverified(self):
        plan = {'call': 'local fixture', 'aims': [{'id': 'a', 'hypothesis': 'h', 'success_criteria': 's', 'evidence': ['e']}],
                'work_packages': [{'id': 'w', 'aims': ['a'], 'start_month': 1, 'end_month': 2, 'owner': 'human', 'deliverable': 'data'}],
                'risks': [{'trigger': 'no signal', 'mitigation': 'controls', 'fallback': 'negative report'}],
                'budget': [{'quantity': 3, 'unit_cost': .1}], 'evidence': [{'id': 'e'}], 'currency': 'USD', 'budget_cap': 1}
        result = projects.grant_plan(plan)
        self.assertEqual(result['total'], '0.3')
        self.assertTrue(result['complete'])
        source = self.source('project/Test.lean', 'theorem pending : True := by sorry\n')
        proof = projects.proof_check({'project': str(source.parent), 'source': source.name, 'declarations': ['pending']}, self.root / 'proof.json')
        self.assertFalse(proof['passed'])
        self.assertEqual(proof['status'], 'rejected')


class EvolutionTests(Workspace):
    def setup_epoch(self, name='epoch', max_trials=3):
        scorer = '''import argparse,json,math
p=argparse.ArgumentParser();p.add_argument('--task');p.add_argument('--prediction');p.add_argument('--output');a=p.parse_args()
t=json.load(open(a.task));v=json.load(open(a.prediction))['prediction'];metric=1 if v==t['expected'] else 0
json.dump({'metric':metric,'checks':{'finite':isinstance(v,(int,float)) and math.isfinite(v)}},open(a.output,'w'))
'''
        def strategy(offset):
            return "import argparse,json\np=argparse.ArgumentParser();p.add_argument('--task');p.add_argument('--seed');p.add_argument('--output');a=p.parse_args()\nt=json.load(open(a.task));json.dump({'prediction':t['input']['x']+" + str(offset) + "},open(a.output,'w'))\n"
        evaluator = self.source('evaluator/score.py', scorer).parent
        incumbent = self.source('incumbent/agent.py', strategy(0)).parent
        candidate = self.source('candidate/agent.py', strategy(1)).parent
        self.source('candidate/self_test.txt', 'complete strategy includes tests')
        tasks = [{'id': split + str(i), 'split': split, 'domain': 'toy', 'input': {'x': i + 100 * si}, 'expected': i + 100 * si + 1}
                 for si, split in enumerate(('development', 'selection', 'audit', 'final')) for i in range(3)]
        protocol = {'tasks': tasks, 'seeds': [0], 'max_trials': max_trials, 'audit_policy': 'reuse-corrected', 'protected_checks': ['finite'], 'resamples': 300,
                    'scorer_command': ['{python}', 'score.py'], 'timeout': 10, 'trial_seconds': 30, 'required_domains': ['toy']}
        evolution.freeze(self.store, name, protocol, evaluator, incumbent, ['{python}', 'agent.py'])
        return candidate, incumbent

    def test_executed_promotion_tie_rejection_and_whole_bundle_rollback(self):
        candidate, incumbent = self.setup_epoch()
        result = evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'], promote=True)
        self.assertTrue(result['promoted'], result.get('reasons'))
        record = self.store.get_value('rsi:epoch')
        self.assertIn('self_test.txt', record['active']['files'])
        exported = evolution.materialize(self.store, 'epoch', self.root / 'promoted-strategy')
        self.assertTrue(Path(exported['inputs']['self_test.txt']).is_file())
        with self.assertRaises(ResearchError): evolution.materialize(self.store, 'epoch', self.root / 'promoted-strategy')
        tie = evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'], promote=True)
        self.assertFalse(tie['promoted'])
        self.assertIn('ties retain', ' '.join(tie['reasons']))
        restored = evolution.rollback(self.store, 'epoch', 0, 'reviewed rollback test')
        self.assertNotIn('self_test.txt', restored['files'])
        self.assertEqual(len(self.store.get_value('rsi:epoch')['history']), 2)

    def test_degraded_candidate_rejected(self):
        candidate, incumbent = self.setup_epoch()
        evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'], promote=True)
        result = evolution.evaluate(self.store, 'epoch', incumbent, ['{python}', 'agent.py'], promote=True)
        self.assertFalse(result['passed'])
        self.assertIn('task regression limit exceeded', result['reasons'])

    def test_frozen_evaluator_integrity_and_audit_budget(self):
        candidate, incumbent = self.setup_epoch(max_trials=1)
        evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'])
        with self.assertRaises(ResearchError): evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'])
        record = self.store.get_value('rsi:epoch')
        h = next(iter(record['evaluator'].values()))
        (self.store.objects / h).write_bytes(b'forged scorer')
        with self.assertRaises(ResearchError): evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'], split='development')

    def test_final_not_used_for_promotion_or_reused(self):
        candidate, incumbent = self.setup_epoch()
        with self.assertRaises(ResearchError): evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'], split='final', promote=True)
        self.assertTrue(evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'], promote=True)['promoted'])
        result = evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'], split='final')
        self.assertFalse(result['promoted'])
        self.assertEqual(result['comparison_role'], 'frozen_reporting_baseline')
        self.assertEqual(result['analysis']['mean_gain'], 1)
        with self.assertRaises(ResearchError): evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'], split='final')

    def test_exact_partition_leakage_and_interrupted_trial_recovery(self):
        candidate, incumbent = self.setup_epoch(max_trials=1)
        record = self.store.get_value('rsi:epoch')
        protocol = copy.deepcopy(record['protocol'])
        protocol['tasks'][3]['input'] = protocol['tasks'][0]['input']
        with self.assertRaises(ResearchError):
            evolution.freeze(self.store, 'leaky', protocol, self.root / 'evaluator', incumbent, ['{python}', 'agent.py'])
        record.update(running='interrupted', worker_pid=99999999)
        record['trials'].append({'id': 'interrupted', 'split': 'audit', 'status': 'running'})
        with self.store.tx(): self.store.set_value('rsi:epoch', record)
        with mock.patch('gresearch.execution.process_exists', return_value=False):
            result = evolution.recover_epoch(self.store, 'epoch', 'fixture crash; no external resources')
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(self.store.get_value('rsi:epoch')['running'])
        with self.assertRaises(ResearchError): evolution.evaluate(self.store, 'epoch', candidate, ['{python}', 'agent.py'])


class InterfaceTests(Workspace):
    def test_console_auth_and_real_state_controls(self):
        run = self.store.create(manifest())
        server = make_server(self.store.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(origin + '/api/run?run=' + run) as r:
                self.assertEqual(json.load(r)['state']['status'], 'ready')
            body = json.dumps({'action': 'pause', 'run': run}).encode()
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(urllib.request.Request(origin + '/api/action', body, {'Content-Type': 'application/json'}))
            self.assertEqual(caught.exception.code, 403)
            headers = {'Content-Type': 'application/json', 'Origin': origin, 'X-Research-Token': server.research_token}
            with urllib.request.urlopen(urllib.request.Request(origin + '/api/action', body, headers)) as r:
                self.assertEqual(json.load(r)['status'], 'paused')
            body = json.dumps({'action': 'annotate', 'run': run, 'target': 'analysis', 'text': 'Review the independent unit'}).encode()
            with urllib.request.urlopen(urllib.request.Request(origin + '/api/action', body, headers)) as r:
                self.assertEqual(json.load(r)['target'], 'analysis')
            with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(origin + '/api/artifact?run=' + run + '&path=../state.sqlite3')
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_resource_queue_executes_and_preserves_limits(self):
        run = self.store.create(manifest())
        projects.enqueue(self.store, run, {'cpu': 1, 'gpu': 1})
        self.assertEqual(projects.queue_next(self.store, {'cpu': 2, 'gpu': 0})['status'], 'no_fitting_job')
        self.assertEqual(projects.queue_next(self.store, {'cpu': 2, 'gpu': 1})['status'], 'completed')

    def test_install_twice_no_nested_skills_and_harness_included(self):
        spec = importlib.util.spec_from_file_location('bundle_installer', REPO / 'install.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        destination = self.root / 'installed'
        module.install(destination)
        with self.assertRaises(ValueError): module.install(destination)
        module.install(destination, force=True)
        module.install(destination, force=True)
        self.assertTrue((destination / 'HARNESS.md').is_file())
        self.assertTrue((destination / '_shared' / 'runtime' / 'research.py').is_file())
        self.assertFalse((destination / 'research-autopilot' / 'research-autopilot').exists())
        self.assertEqual(len(list(destination.glob('.gresearch-backup-*'))), 2)
        invoked = subprocess.run([sys.executable, str(destination / '_shared' / 'runtime' / 'research.py'), '--help'], capture_output=True, text=True)
        self.assertEqual(invoked.returncode, 0, invoked.stderr)


class RetrievalAndRegressionTests(Workspace):
    def test_real_pdf_extraction_and_scanned_page_state(self):
        try: import fitz
        except ImportError: self.skipTest('PyMuPDF not installed')
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((50, 50), 'Synthetic evidence page with a sufficiently long methodological statement.')
        pdf.new_page()
        path = self.root / 'paper.pdf'; pdf.save(path); pdf.close()
        dest = self.root / 'extracted'
        result = evidence.ingest_pdf(path, dest)
        self.assertEqual(len(result['pages']), 2)
        self.assertEqual(result['pages'][1]['status'], 'ocr_or_manual_check_needed')
        self.assertEqual(result['sha256'], digest(path.read_bytes()))
        self.assertEqual(digest((dest / 'page-0001.txt').read_bytes()), result['pages'][0]['sha256'])

    def test_provider_fixtures_and_raw_cache(self):
        fixtures = {
            'crossref': {'message': {'items': [{'DOI': '10.1234/a', 'title': ['Example']}], 'next-cursor': None}},
            'openalex': {'results': [{'id': 'W1', 'title': 'Example', 'doi': 'https://doi.org/10.1234/a'}], 'meta': {'next_cursor': None}},
            'semantic-scholar': {'data': [{'paperId': 'p1', 'title': 'Example'}]},
            'europepmc': {'resultList': {'result': [{'id': '1', 'source': 'MED', 'title': 'Example'}]}}
        }
        for provider, body in fixtures.items():
            with self.subTest(provider=provider), mock.patch.object(literature, 'get_bytes', return_value=json.dumps(body).encode()) as fetch:
                result = literature.search(provider, 'fixture query', self.root / provider, page_size=2)
                self.assertEqual(len(result['records']), 1)
                self.assertTrue(result['pagination_complete'])
                again = literature.search(provider, 'fixture query', self.root / provider, page_size=2)
                self.assertTrue(again['receipts'][0]['served_from_cache'])
                self.assertEqual(fetch.call_count, 1)
        xml = '<feed xmlns="http://www.w3.org/2005/Atom" xmlns:o="http://a9.com/-/spec/opensearch/1.1/"><o:totalResults>1</o:totalResults><entry><id>arxiv:1</id><title>Example</title><summary>Fixture</summary></entry></feed>'
        with mock.patch.object(literature, 'get_bytes', return_value=xml.encode()):
            self.assertEqual(len(literature.search('arxiv', 'all:example', self.root / 'arxiv')['records']), 1)

    def test_citation_absent_retraction_is_unknown(self):
        raw = json.dumps({'message': {'DOI': '10.1234/a', 'title': ['Example']}}).encode()
        with mock.patch.object(literature, 'get_bytes', return_value=raw):
            result = literature.citation_check('https://doi.org/10.1234/a', self.root / 'metadata')
        self.assertTrue(result['matched'])
        self.assertEqual(result['retraction_status'], 'unknown')

    def test_local_retrieval_fusion_and_source_mutation(self):
        self.source('a.txt', 'scientific evidence and independent experiments')
        self.source('b.txt', '科研证据与独立验证')
        index = retrieval.build_index({'root': str(self.root), 'embedding_model': 'explicit-fixture-v1', 'embedding_provenance': 'synthetic vectors to test cosine, not learned semantics',
                                       'documents': [{'id': 'a', 'path': 'a.txt', 'page': 1, 'embedding': [1, 0]}, {'id': 'b', 'path': 'b.txt', 'page': 1, 'embedding': [0, 1]}]})
        self.assertEqual(retrieval.query_index(index, 'independent')['results'][0]['id'], 'a')
        self.assertEqual(retrieval.query_index(index, '科研证据')['results'][0]['id'], 'b')
        result = retrieval.query_index(index, 'unknown', vector=[0, 1], embedding_model='explicit-fixture-v1')
        self.assertEqual(result['results'][0]['id'], 'b')
        with self.assertRaises(ResearchError): retrieval.query_index(index, 'unknown', vector=[0, 1], embedding_model='different')
        (self.root / 'a.txt').write_text('changed')
        with self.assertRaises(ResearchError): retrieval.query_index(index, 'evidence')

    def test_source_invalidation_and_notes_bridge(self):
        graph = {'nodes': [{'id': 's', 'type': 'source'}, {'id': 'c', 'type': 'claim', 'status': 'verified'}],
                 'edges': [{'from': 's', 'to': 'c', 'relation': 'supports', 'adjudication': {'status': 'accepted'}}]}
        result = retrieval.invalidate(graph, ['s'], 'publisher correction')
        self.assertEqual(result['graph']['nodes'][1]['status'], 'needs_review')
        self.assertEqual(graph['nodes'][1]['status'], 'verified')
        records = [{'id': 'parent', 'title': 'Study', 'DOI': '10.1234/a'},
                   {'id': 'note', 'title': '', 'zotero': {'data': {'parentItem': 'parent', 'itemType': 'annotation', 'annotationText': 'critical limitation'}}}]
        bridge = literature.export_notes(records, self.root / 'vault')
        saved = read_json(Path(bridge['directory']) / 'identity-map.json')
        text = (Path(bridge['directory']) / saved['note']).read_text(encoding='utf-8')
        self.assertIn('critical limitation', text)
        self.assertIn(saved['parent'][:-3], text)

    def test_failed_acceptance_output_not_marked_completed(self):
        spec = stage(code="open('analysis.json','w').write('{\"passed\":false}')", checks=[{'path': 'analysis.json', 'field': 'passed', 'equals': True}])
        run = self.store.create(manifest([spec]))
        result = run_workflow(self.store, run)
        self.assertEqual(result['stages']['analysis']['status'], 'failed')
        self.assertIn('Acceptance check failed', result['stages']['analysis']['error'])

    def test_windows_deep_archive_and_optional_input_integrity(self):
        deep = Store(self.root / ('long-' * 18) / 'store')
        try:
            run = deep.create(manifest())
            run_workflow(deep, run)
            archive = deep.archive(run)
            self.assertTrue(verify_archive(archive['archive'])['valid'])
        finally: deep.close()
        p = self.source('optional.txt', 'first')
        run = self.store.create(manifest([stage(optional=['extra.txt'])]), inputs={'extra.txt': p})
        (self.store.work(run) / 'extra.txt').write_text('changed')
        self.assertEqual(run_workflow(self.store, run)['stages']['analysis']['status'], 'failed')

    def test_empty_graph_and_unbound_ledger_rejected(self):
        self.assertFalse(evidence.validate_graph({'nodes': [], 'edges': []}, self.root)['structurally_valid'])
        result = {'id': 'r', 'value': 3, 'metric': 'x', 'condition': 'c', 'unit': 'u', 'run': 'r'}
        ledger = {'results': [result], 'bindings': [{**result, 'literal': '3', 'start': 0, 'end': 1, 'result_id': 'r'}]}
        self.assertFalse(evidence.audit_writing('3', ledger)['passed'])

    def test_milestone_alignment_and_conflicting_explicit_ids(self):
        left = self.store.create(manifest([stage('left-stage', milestone='Measure effect')]))
        right = self.store.create(manifest([stage('right-stage', milestone='Measure effect')]))
        result = compare_runs(self.store, left, right)
        self.assertEqual(result['alignments'][0]['by'], 'declared_milestone')
        self.assertFalse(result['unmatched_left'])
        a = self.store.create(manifest([stage(milestone_id='mean-estimate')]))
        b = self.store.create(manifest([stage(milestone_id='median-estimate')]))
        result = compare_runs(self.store, a, b)
        self.assertFalse(result['alignments'])
        self.assertEqual(len(result['alignment_conflicts']), 1)

    def test_intervention_changed_estimand_is_not_improvement(self):
        contract = {'estimand': 'mean loss', 'metric': 'loss', 'unit': 'squared units', 'analysis_unit': 'task', 'evaluation_data_hash': 'frozen-fixture'}
        data = {'followed': True, 'matched_controls': True, 'repetitions': 3, 'external_state_comparable': True,
                'measurement_contracts': {'control': contract, 'intervention': {**contract, 'estimand': 'median loss'}},
                'milestones': [{'achieved': True}], 'pairs': [{'task': str(i), 'seed': 0, 'candidate': 2, 'incumbent': 1} for i in range(3)]}
        self.assertEqual(review.intervention_assessment(data)['classification'], 'Inconclusive')
        data['measurement_contracts']['intervention'] = dict(contract)
        self.assertEqual(review.intervention_assessment(data)['classification'], 'Validated')


if __name__ == '__main__': unittest.main()
