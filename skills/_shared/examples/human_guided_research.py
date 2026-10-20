#!/usr/bin/env python3
"""Local report/explanation demo; feedback is never synthesized in the default mode."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from gresearch.core import Store, digest, read_json, write_json
from gresearch.execution import run_workflow
from gresearch import hci, capabilities as cap
from offline_research import AGENT, SCORER


def execute(destination, scripted=False):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    sources = destination / 'sources'
    sources.mkdir()
    source = sources / 'source.txt'
    quote = 'Fixture observation: the sample contains three values.'
    source.write_text(quote + '\nNo population claim follows from this example.\n', encoding='utf-8')
    reviewer = 'scripted-researcher' if scripted else 'researcher'
    manifest = {'version': 2, 'objective': 'Interface demonstration with explicitly labelled fixture materials',
                'authorization': {'effects': ['local']}, 'budget': {'seconds': 60, 'cost': 0},
                'hci': {'mode': 'every-stage', 'reviewers': [reviewer], 'require_explanation': True},
                'stages': [{'id': 'analysis', 'skill': 'statistical-analyst', 'requires': ['source.txt'], 'outputs': ['result.json'],
                            'rationale': 'Show the descriptive result before deciding whether inference is justified.',
                            'goal': 'Describe a fixture sample', 'alternatives': ['A median is another descriptive summary.'],
                            'instructions': 'Compute the mean of the explicit fixture values [1, 2, 6].',
                            'review_questions': ['Is a descriptive summary enough for this question?'],
                            'command': ['{python}', '-c', "import json;json.dump({'mean':3},open('result.json','w'))"]}]}
    store = Store(destination / 'state')
    try:
        run = store.create(manifest, 'demo-parent', {'source.txt': source})
        run_workflow(store, run)
        bundle = {'topic': 'A sample summary and its limits', 'audience': 'beginner',
                  'intuition': 'A mean describes these observations; it does not determine the population.',
                  'technical': 'The fixture values [1, 2, 6] sum to 9, with mean 3 and median 2.',
                  'relevance': 'The researcher can request a different summary before proceeding.',
                  'assumptions': ['Only the three explicit fixture values are described.'],
                  'limitations': ['No sampling protocol or population inference is demonstrated.'],
                  'questions': ['What changes if one observation is extreme?'],
                  'claims': [{'id': 'sample', 'text': quote, 'status': 'source_reported', 'citations': [
                      {'path': 'source.txt', 'sha256': digest(source.read_bytes()), 'start': 0, 'end': len(quote), 'quote': quote}]},
                      {'id': 'arithmetic', 'text': 'For the specified fixture, the mean is 3 and median is 2.',
                       'status': 'interpretation', 'citations': []}]}
        report = hci.read(store, run, 'analysis')
        hci.explain(store, run, 'analysis', report['receipt']['id'], 'example-host', bundle)
        report = hci.read(store, run, 'analysis')
        result = {'run': run, 'status': store.get(run)[1]['status'],
                  'report': str(store.work(run) / report['receipt']['directory'] / 'report.md'),
                  'scripted_feedback': scripted, 'user_study': False, 'scientific_gain_claimed': False}
        if scripted:
            request = hci.feedback(store, run, 'analysis', report['receipt']['id'], reviewer, 'revise',
                                   'SCRIPTED FIXTURE: also report the median; not a real researcher observation.')
            child = hci.revise(store, run, 'analysis', request['feedback']['id'], {'analysis': {
                'command': ['{python}', '-c', "import json;json.dump({'mean':3,'median':2},open('result.json','w'))"],
                'instructions': 'Report both fixture summaries.', 'rationale': 'A scripted change request exercises branch execution.'}})['child']
            run_workflow(store, child)
            hci.explain(store, child, 'analysis', hci.read(store, child, 'analysis')['receipt']['id'], 'example-host', bundle)
            hci.feedback(store, child, 'analysis', hci.read(store, child, 'analysis')['receipt']['id'], reviewer, 'approve',
                         'SCRIPTED FIXTURE: accept the integration example, not its scientific validity.')
            run_workflow(store, child)
            graph = hci.to_memory(store, run, 'analysis', hci.read(store, run, 'analysis')['receipt']['id'],
                                 'demo-project', 0, actor=reviewer, reason='Keep fixture provenance')
            for name, content in [('incumbent/agent.py', AGENT.replace('OFFSET', '0')),
                                  ('candidate/agent.py', AGENT.replace('OFFSET', '1')), ('evaluator/score.py', SCORER)]:
                file = sources / name
                file.parent.mkdir(exist_ok=True)
                file.write_text(content, encoding='utf-8')
            protocol = {'metric_description': 'Toy x+1 exact match; not an explanation-quality metric',
                        'failure_definition': 'Wrong or nonfinite fixture prediction',
                        'tasks': [{'id': str(i), 'split': 'audit', 'input': {'x': i}, 'expected': i + 1} for i in range(3)],
                        'seeds': [0], 'max_trials': 1, 'protected_checks': ['finite'], 'resamples': 300,
                        'scorer_command': ['{python}', 'score.py'], 'timeout': 10, 'trial_seconds': 60}
            target = 'skill:research-explainer'
            cap.freeze(store, target, 'fixture-epoch', protocol, sources / 'evaluator', sources / 'incumbent', ['{python}', 'agent.py'],
                       actor='example-host', reason='Interface-only evaluator fixture', reviewers=[reviewer])
            proposal = cap.propose(store, target, 'fixture-epoch', sources / 'candidate', ['{python}', 'agent.py'],
                                   actor='example-host', reason='Exercise proposal/adoption, not a scientific improvement claim',
                                   sources=[{'run': run, 'stage': 'analysis', 'report_id': report['receipt']['id'],
                                             'feedback_id': request['feedback']['id']}])
            trial = cap.evaluate(store, proposal['id'])
            if not trial['passed']: raise RuntimeError('Fixture evaluation failed: ' + str(trial['reasons']))
            cap.review(store, proposal['id'], trial['id'], actor=reviewer, decision='approve', reason='SCRIPTED adoption fixture')
            adoption = cap.activate(store, proposal['id'], expected_revision=0, actor=reviewer, reason='SCRIPTED adoption fixture')
            rollback = cap.rollback(store, target, 0, expected_revision=1, actor=reviewer, reason='SCRIPTED rollback fixture')
            result.update(child=child, child_status=store.get(child)[1]['status'], parent_status=store.get(run)[1]['status'],
                          original=read_json(store.work(run) / 'result.json'), revised=read_json(store.work(child) / 'result.json'),
                          graph=graph, proposal=proposal['id'], audit_passed=trial['passed'], adoption=adoption, rollback=rollback)
        latest = hci.read(store, run, 'analysis')
        result.update(status=store.get(run)[1]['status'],
                      report=str(store.work(run) / latest['receipt']['directory'] / 'report.md'))
        result['store_verified'] = store.verify()['valid']
        write_json(destination / 'summary.json', result)
        return result
    finally:
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='New output directory')
    parser.add_argument('--scripted-demo', action='store_true', help='Explicitly simulate labelled feedback, adoption and rollback fixtures')
    args = parser.parse_args()
    result = execute(args.output, args.scripted_demo)
    print(result['report'])
    print('summary.json records the actual run state; default mode awaits real researcher feedback.')
