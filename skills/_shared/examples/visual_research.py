"""Prepare a real rendering workflow with labelled fixtures and human checkpoints."""
import argparse
from pathlib import Path
import sys

SHARED = Path(__file__).resolve().parents[1]
SKILLS = SHARED.parent
sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(SHARED / 'runtime'))
from visual_artifacts import sha256, write_json
from gresearch.core import Store
from gresearch.execution import run_workflow


def materials(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    data = destination / 'sample.csv'
    data.write_text('step,value,lower,upper,comparison\n1,2,1.5,2.5,3\n2,3,2.4,3.6,2\n3,2.5,2,3,3.5\n4,4,3.2,4.8,4.5\n', encoding='utf-8')
    base = {'version': 1, 'purpose': 'Explain a visual workflow using labelled synthetic values', 'audience': 'Researcher reviewing software behavior',
            'rationale': 'Compare explicit values while preserving sources and researcher control.', 'evidence_status': 'illustrative',
            'sources': [{'id': 'data', 'path': 'sample.csv', 'sha256': sha256(data), 'label': 'Synthetic interface fixture'}],
            'claims': [{'id': 'demo', 'text': 'These values illustrate the interface only.', 'status': 'illustrative',
                        'evidence': [{'source': 'data', 'locator': 'rows 1-4'}]}]}
    figure = {**base, 'size_mm': [180, 100], 'dpi': 160, 'caption': 'Synthetic values; supplied intervals are not estimated confidence intervals.',
              'panels': [{'kind': 'line', 'source': 'data', 'title': 'Supplied intervals', 'x': 'step', 'xlabel': 'Step', 'ylabel': 'Illustrative value',
                          'claims': ['demo'], 'series': [{'y': 'value', 'label': 'Fixture', 'interval': {'low': 'lower', 'high': 'upper',
                          'definition': 'Supplied illustrative bounds, not statistical inference', 'sampling_unit': 'None: synthetic fixture'}}]},
                         {'kind': 'scatter', 'source': 'data', 'title': 'Comparison values', 'x': 'value', 'xlabel': 'Fixture value',
                          'ylabel': 'Comparison', 'claims': ['demo'], 'series': [{'y': 'comparison', 'label': 'Fixture'}]}]}
    diagram = {**base, 'size': [1100, 400], 'alt_text': 'A proposed workflow keeps researcher decisions before rendering and review.',
               'nodes': [{'id': 'brief', 'label': 'Researcher\nsets direction', 'box': [40, 130, 260, 110]},
                         {'id': 'build', 'label': 'Build\ntraceable artifacts', 'box': [420, 130, 260, 110]},
                         {'id': 'review', 'label': 'Researcher\nreviews changes', 'box': [800, 130, 260, 110]}],
               'edges': [{'from': 'brief', 'to': 'build', 'kind': 'flow', 'label': 'accepted brief'},
                         {'from': 'build', 'to': 'review', 'kind': 'flow', 'label': 'preview + evidence'}]}
    deck = {**base, 'duration_seconds': 240, 'slides': [
        {'title': 'Researcher control remains explicit', 'layout': 'title', 'body': ['A rendering workflow with versioned evidence', 'Synthetic demonstration only'],
         'seconds': 35, 'notes': 'Introduce the software demonstration. No scientific result or user-study outcome is claimed.', 'claims': ['demo']},
        {'title': 'Native charts retain the supplied values', 'layout': 'evidence', 'body': ['The chart is editable.', 'Values come from the hashed CSV.'],
         'chart': {'kind': 'bar', 'source': 'data', 'x': 'step', 'xlabel': 'Step', 'ylabel': 'Illustrative value', 'series': [{'y': 'value', 'label': 'Fixture'}]},
         'seconds': 60, 'notes': 'Show that the native chart workbook retains each CSV value. The earlier figure separately shows supplied bounds.', 'claims': ['demo']},
        {'title': 'Keep judgments separate', 'layout': 'comparison', 'columns': [
            {'title': 'Machine checks', 'body': ['Source bytes', 'File construction', 'Declared timing']},
            {'title': 'Researcher decisions', 'body': ['Scientific framing', 'Appropriate emphasis', 'Whether to adopt']}],
         'seconds': 55, 'notes': 'Explain why technical success does not approve scientific meaning or visual taste.', 'claims': ['demo']},
        {'title': 'What should change before adoption?', 'layout': 'discussion', 'body': ['Review the framing and evidence.', 'Request a revision or explanation.', 'Accept only the current artifact version.'],
         'seconds': 45, 'notes': 'Ask for actual feedback. The example does not synthesize approval.', 'claims': ['demo']}]}
    for name, value in [('figure-spec.json', figure), ('diagram-spec.json', diagram), ('deck-spec.json', deck)]:
        write_json(destination / name, value)
    (destination / 'brief-source.md').write_text('# Researcher review\n\nThis is a synthetic software demonstration.\n\nPlease review the framing, chart choices and presentation plan before rendering.\n', encoding='utf-8')
    return destination


def initialize(destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    source = materials(destination / 'sources')
    inputs = {p.name: p for p in source.iterdir()}
    for relative in ('_shared/visual_artifacts.py', 'figure-mimic/scripts/build_figure.py',
                     'figure-mimic/scripts/build_diagram.py', 'slides-builder/scripts/build_deck.py'):
        inputs['tools/' + relative] = SKILLS / relative
    stages = [{'id': 'brief', 'skill': 'research-control', 'requires': ['brief-source.md', 'figure-spec.json', 'diagram-spec.json', 'deck-spec.json', 'sample.csv'],
               'outputs': ['brief.md'], 'command': ['{python}', '-c', "from pathlib import Path;Path('brief.md').write_bytes(Path('brief-source.md').read_bytes())"],
               'rationale': 'A researcher reviews the intended framing and planned artifacts before rendering.',
               'instructions': 'Read the supplied specs and brief; accept, revise, explain or stop.',
               'review_questions': ['Does this storyboard express the intended question?', 'Should the chart or diagram meaning change?']}]
    for sid, skill, script, outputs in [
        ('figure', 'figure-mimic', 'build_figure.py', ['figure.png', 'figure.svg', 'figure.pdf', 'report.md', 'artifact-manifest.json']),
        ('diagram', 'figure-mimic', 'build_diagram.py', ['diagram.png', 'diagram.svg', 'diagram.pdf', 'diagram.drawio', 'report.md', 'artifact-manifest.json']),
        ('deck', 'slides-builder', 'build_deck.py', ['slides.pptx', 'speaker-notes.md', 'slides-ledger.json', 'report.md', 'artifact-manifest.json'])]:
        builder = f'tools/{skill}/scripts/{script}'
        stages.append({'id': sid, 'skill': skill, 'needs': [stages[-1]['id']],
                       'requires': [sid + '-spec.json', 'sample.csv', builder, 'tools/_shared/visual_artifacts.py'],
                       'outputs': [sid + '/' + output for output in outputs], 'timeout': 90,
                       'command': ['{python}', builder, sid + '-spec.json', '--output', sid],
                       'rationale': 'Render the agreed representation with input hashes and reproducible source.',
                       'instructions': 'Inspect the generated artifacts and recorded limits; PowerPoint visual rendering is a separate step.',
                       'review_questions': ['Does the actual artifact preserve the intended meaning?', 'Which specific object or claim needs revision?']})
    manifest = {'version': 2, 'objective': 'Human-supervised visual artifact demonstration; no scientific gain claimed',
                'authorization': {'effects': ['local']}, 'budget': {'seconds': 600, 'cost': 0},
                'hci': {'mode': 'every-stage', 'reviewers': ['researcher'], 'require_explanation': False}, 'stages': stages}
    write_json(destination / 'workflow.json', manifest)
    store = Store(destination / 'state')
    try:
        run = store.create(manifest, 'visual-demo', inputs)
        state = run_workflow(store, run)
        result = {'run': run, 'status': state['status'], 'human_feedback_synthesized': False,
                  'scientific_gain_claimed': False, 'source_kind': 'explicit synthetic fixture'}
    finally:
        store.close()
    write_json(destination / 'summary.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(initialize(args.output))
