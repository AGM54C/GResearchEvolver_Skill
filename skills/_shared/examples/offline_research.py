#!/usr/bin/env python3
"""Execute a labelled synthetic research example; no model or paid API calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

RUNTIME = Path(__file__).resolve().parents[1] / 'runtime'
sys.path.insert(0, str(RUNTIME))
from gresearch.core import Store, digest, read_json, write_json
from gresearch.execution import run_workflow
from gresearch import evidence, evolution


ANALYSIS = '''import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path('_runtime').resolve()))
from gresearch.statistics import paired_analysis
p=argparse.ArgumentParser();p.add_argument('--run');p.add_argument('--drop',default='');a=p.parse_args()
rows=json.load(open('data.json',encoding='utf-8'))
rows=[r for r in rows if r['task']!=a.drop]
analysis=paired_analysis(rows,resamples=2000,seed=7)
control=paired_analysis([{**r,'candidate':r['incumbent']} for r in rows],resamples=2000,seed=7)
json.dump({'gain':{'value':analysis['mean_gain'],'metric':'paired gain','condition':'synthetic tasks; drop='+a.drop,'unit':'points','run':a.run},'analysis':analysis,'negative_control':control},open('results.json','w',encoding='utf-8'))
'''

AUDIT = '''import json,sys
from pathlib import Path
sys.path.insert(0,str(Path('_runtime').resolve()))
from gresearch.evidence import audit_writing
result=audit_writing(Path('draft.md').read_text(encoding='utf-8'),json.load(open('ledger.json',encoding='utf-8')))
json.dump(result,open('audit.json','w',encoding='utf-8'))
'''

AGENT = '''import argparse,json
p=argparse.ArgumentParser();p.add_argument('--task');p.add_argument('--seed');p.add_argument('--output');a=p.parse_args()
t=json.load(open(a.task));json.dump({'prediction':t['input']['x']+OFFSET},open(a.output,'w'))
'''

SCORER = '''import argparse,json,math
p=argparse.ArgumentParser();p.add_argument('--task');p.add_argument('--prediction');p.add_argument('--output');a=p.parse_args()
t=json.load(open(a.task));v=json.load(open(a.prediction))['prediction']
json.dump({'metric':float(v==t['expected']),'checks':{'finite':isinstance(v,(int,float)) and math.isfinite(v)}},open(a.output,'w'))
'''


def complete_writer(store, run):
    work = store.work(run)
    result = read_json(work / 'results.json')
    raw = result['gain']
    # Synthetic provenance is stated in the actual report, not just its filename.
    literal = f"{raw['value']:.3f}"
    doc = 'Synthetic interface demonstration. The paired mean gain was ' + literal + ' points. This is not evidence of real research-agent superiority.\n'
    (work / 'draft.md').write_text(doc, encoding='utf-8')
    row = {'id': 'gain', **raw, 'source': {'kind': 'computed', 'path': 'results.json', 'sha256': digest((work / 'results.json').read_bytes()), 'pointer': ['gain']}}
    start = doc.index(literal)
    binding = {'start': start, 'end': start + len(literal), 'literal': literal, 'result_id': 'gain', 'decimals': 3,
               **{k: raw[k] for k in ('metric', 'condition', 'unit', 'run')}}
    write_json(work / 'ledger.json', {'root': str(work), 'results': [row], 'bindings': [binding], 'references': []})
    store.finish(run, 'writing', actor='scripted-synthetic-example')


def execute(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    sources = destination / 'sources'
    sources.mkdir(exist_ok=True)
    rows = [{'task': 'task-' + str(i), 'seed': seed, 'incumbent': 10 + i,
             'candidate': 10 + i + gain + (.02 if seed else -.02)}
            for i, gain in enumerate([-.2, .7, 1., 1.1, .9, 1.3, 1.2, .8]) for seed in (0, 1)]
    write_json(sources / 'data.json', rows)
    (sources / 'analysis.py').write_text(ANALYSIS, encoding='utf-8')
    (sources / 'audit.py').write_text(AUDIT, encoding='utf-8')
    inputs = {p.name: str(p) for p in sources.iterdir() if p.is_file()}
    for p in (RUNTIME / 'gresearch').glob('*.py'):
        inputs['_runtime/gresearch/' + p.name] = str(p)
    runtime_files = [k for k in inputs if k.startswith('_runtime/')]
    manifest = {'version': 2, 'objective': 'Synthetic paired experiment with negative control and explicit human review',
                'authorization': {'effects': ['local']}, 'budget': {'seconds': 120, 'cost': 0},
                'stages': [
                    {'id': 'analysis', 'skill': 'statistical-analyst', 'milestone': 'Estimate task-level effect and no-signal control',
                     'requires': ['data.json', 'analysis.py', *runtime_files], 'outputs': ['results.json'],
                     'command': [sys.executable, 'analysis.py', '--run', 'synthetic-base']},
                    {'id': 'writing', 'skill': 'paper-writer', 'milestone': 'Bind all reported values to executed results',
                     'needs': ['analysis'], 'requires': ['results.json'], 'outputs': ['draft.md', 'ledger.json']},
                    {'id': 'audit', 'skill': 'paper-writer', 'milestone': 'Audit prose and source context', 'needs': ['writing'],
                     'requires': ['draft.md', 'ledger.json', 'audit.py', *runtime_files], 'outputs': ['audit.json'],
                     'checks': [{'path': 'audit.json', 'field': 'passed', 'equals': True}],
                     'command': [sys.executable, 'audit.py']}]}
    store = Store(destination / 'state')
    try:
        base = store.create(manifest, 'synthetic-base', inputs)
        state = run_workflow(store, base)
        assert state['stages']['writing']['status'] == 'awaiting_artifact'
        complete_writer(store, base)
        assert run_workflow(store, base)['status'] == 'completed'
        store.annotate(base, 'analysis', 'Sensitivity analysis: excluding a negative task is exploratory, not a replacement for the original result.', 'example-researcher')
        child = store.fork(base, 'analysis', {'analysis': {'command': [sys.executable, 'analysis.py', '--run', 'synthetic-sensitivity', '--drop', 'task-0']}}, 'synthetic-sensitivity')
        run_workflow(store, child)
        complete_writer(store, child)
        assert run_workflow(store, child)['status'] == 'completed'
        work = store.work(base)
        result = read_json(work / 'results.json')
        graph = {'nodes': [
            {'id': 'data', 'type': 'data', 'path': 'data.json', 'sha256': digest((work / 'data.json').read_bytes())},
            {'id': 'code', 'type': 'code', 'path': 'analysis.py', 'sha256': digest((work / 'analysis.py').read_bytes())},
            {'id': 'result', 'type': 'result', 'path': 'results.json', 'sha256': digest((work / 'results.json').read_bytes())},
            {'id': 'claim', 'type': 'claim', 'text': 'Positive mean on this synthetic sample', 'scope': 'these eight synthetic tasks', 'certainty': 'sample estimate', 'status': 'draft'}],
            'edges': [{'id': 'd-c', 'from': 'data', 'to': 'code', 'relation': 'used_by'},
                      {'id': 'c-r', 'from': 'code', 'to': 'result', 'relation': 'produces'},
                      {'id': 'r-q', 'from': 'result', 'to': 'claim', 'relation': 'supports',
                       'evidence': {'path': 'results.json', 'sha256': digest((work / 'results.json').read_bytes()), 'quote': '"metric": "paired gain"'}}]}
        graph_check = evidence.validate_graph(graph, work)
        write_json(destination / 'graph.json', graph)
        write_json(destination / 'graph-audit.json', graph_check)
        archives = [store.archive(base), store.archive(child)]
        for label, text in [('incumbent', AGENT.replace('OFFSET', '0')), ('candidate', AGENT.replace('OFFSET', '1')), ('evaluator', SCORER)]:
            directory = sources / label; directory.mkdir(exist_ok=True)
            (directory / ('score.py' if label == 'evaluator' else 'agent.py')).write_text(text, encoding='utf-8')
        (sources / 'candidate' / 'self-tests.txt').write_text('Part of the whole strategy bundle, not independent acceptance.', encoding='utf-8')
        protocol = {'tasks': [{'id': 'audit-' + str(i), 'split': 'audit', 'domain': 'synthetic-arithmetic', 'input': {'x': i}, 'expected': i + 1} for i in range(4)],
                    'seeds': [0], 'max_trials': 2, 'audit_policy': 'reuse-corrected', 'scorer_command': ['{python}', 'score.py'], 'protected_checks': ['finite'],
                    'required_domains': ['synthetic-arithmetic'], 'resamples': 1000, 'timeout': 10, 'trial_seconds': 60}
        evolution.freeze(store, 'synthetic', protocol, sources / 'evaluator', sources / 'incumbent', ['{python}', 'agent.py'])
        promoted = evolution.evaluate(store, 'synthetic', sources / 'candidate', ['{python}', 'agent.py'], promote=True)
        tied = evolution.evaluate(store, 'synthetic', sources / 'candidate', ['{python}', 'agent.py'], promote=True)
        rollback = evolution.rollback(store, 'synthetic', 0, 'Demonstrate restoration of the original whole bundle')
        report = {'scope': 'Synthetic software integration test; no measured research capability gain', 'base': base, 'fork': child,
                  'estimate': result['gain'], 'ci': result['analysis']['ci'], 'negative_control': result['negative_control']['mean_gain'],
                  'writing_audit': read_json(work / 'audit.json'), 'graph_audit': graph_check, 'archives': archives,
                  'rsi_promoted': promoted['promoted'], 'rsi_tie_promoted': tied['promoted'], 'rollback_files': list(rollback['files']),
                  'integrity': store.verify(), 'independent_scientific_reviewer': 'not performed; graph support remains unadjudicated'}
        assert report['rsi_promoted'] and not report['rsi_tie_promoted'] and report['integrity']['valid']
        write_json(destination / 'report.json', report)
        return report
    finally:
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='new directory for the demonstration')
    args = parser.parse_args()
    print(json.dumps(execute(args.output), ensure_ascii=False, indent=2))
