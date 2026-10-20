"""Research capability evolution with frozen evaluation and explicit adoption.

Activation selects a version in this store. It never rewrites the running
runtime, its evaluator, authorizations, or installed host skills.
"""
from pathlib import Path
import time
import uuid

from .core import ResearchError, fingerprint, read_json, valid_id
from .explanations import text
from .locking import resource_lock
from . import evolution as rsi


def catalog():
    from .cli import OPERATIONS
    root = Path(__file__).resolve().parents[3]
    registry = read_json(root / 'manifest.yaml')
    result = []
    for name, spec in registry['skills'].items():
        result.append({'id': 'skill:' + name, 'kind': 'skill', 'in_scope': not spec.get('outside_v2_upgrade', False),
                       'description': spec.get('intents', [name])[0], 'adoption': 'explicit pinned bundle or host installation'})
    for name in OPERATIONS:
        result.append({'id': 'tool:' + name, 'kind': 'tool', 'in_scope': True,
                       'adoption': 'explicit pinned adapter; built-in dispatch remains trusted'})
    for path in sorted(Path(__file__).parent.glob('*.py')):
        if path.stem.startswith('_'): continue
        result.append({'id': 'runtime:' + path.stem, 'kind': 'runtime', 'in_scope': True,
                       'adoption': 'export for independently reviewed release; no in-process replacement'})
    return result


def target_info(target):
    info = next((c for c in catalog() if c['id'] == target), None)
    if not info or not info['in_scope']: raise ResearchError('Unknown or out-of-scope evolution target')
    return info


def state(store, target):
    target_info(target)
    record = store.get_value('capability:' + target)
    if not record: raise ResearchError('Capability has no frozen baseline')
    return record


def freeze(store, target, name, protocol, evaluator_dir, incumbent_dir, incumbent_command, *, actor, reason, reviewers):
    target_info(target); text(actor, 'actor'); text(reason, 'reason')
    if not isinstance(reviewers, list) or not reviewers: raise ResearchError('Declare researcher reviewers')
    for reviewer in reviewers: text(reviewer, 'reviewer')
    if not isinstance(protocol, dict): raise ResearchError('Protocol must be an object')
    for key in ('metric_description', 'failure_definition'): text(protocol.get(key), key)
    if protocol.get('attestation') and not protocol.get('isolation'):
        raise ResearchError('Signed capability adoption requires an isolated evaluation protocol')
    policy = {**protocol, 'capability_target': target, 'promotion_policy': 'human-reviewed', 'reviewers': reviewers}
    with resource_lock(store, 'capability', fingerprint(target)):
        old = store.get_value('capability:' + target)
        policy['capability_revision'] = old['revision'] if old else 0
        record = None
        def register(epoch):
            nonlocal record
            baseline = epoch['active']
            if old and baseline != old['active']:
                raise ResearchError('A new epoch must start from the current active capability version')
            record = old or {'target': target, 'revision': 0, 'active': baseline, 'history': [baseline], 'epochs': []}
            record['epochs'].append(name)
            store.set_value('capability:' + target, record)
            store.event('capability:' + target, 'capability_epoch', {'epoch': name, 'actor': actor, 'reason': reason,
                        'protocol_hash': epoch['protocol_hash'], 'metric_description': protocol['metric_description']})
        rsi.freeze(store, name, policy, evaluator_dir, incumbent_dir, incumbent_command, _register=register)
    return record


def proposal(store, identity):
    valid_id(identity)
    record = store.get_value('proposal:' + identity)
    if not record: raise ResearchError('Unknown evolution proposal')
    return record


def propose(store, target, epoch, candidate_dir, candidate_command, *, actor, reason, sources):
    from .hci import read
    text(actor, 'actor'); text(reason, 'reason'); rsi.check_command(candidate_command)
    if not isinstance(sources, list) or not sources: raise ResearchError('Link concrete stage reports or researcher feedback')
    evidence = []
    for source in sources:
        if not isinstance(source, dict) or not {'run', 'stage', 'report_id'}.issubset(source) or set(source) - {'run', 'stage', 'report_id', 'feedback_id'}:
            raise ResearchError('Proposal sources need run, stage, report_id and optional feedback_id')
        report = read(store, source['run'], source['stage'], source['report_id'])
        if source.get('feedback_id'):
            _, s = store.get(source['run'])
            if not any(f['id'] == source['feedback_id'] and f['report_id'] == source['report_id']
                       for f in s['stages'][source['stage']].get('feedback', [])):
                raise ResearchError('Feedback provenance does not match the referenced report')
        evidence.append({**source, 'report_hash': report['receipt']['json']})
    with resource_lock(store, 'capability', fingerprint(target)):
        active = state(store, target)
        frozen = store.get_value('rsi:' + epoch)
        if epoch not in active['epochs'] or not frozen or frozen['protocol'].get('capability_target') != target:
            raise ResearchError('Epoch is not bound to this capability')
        rsi.verify_epoch(store, frozen)
        if frozen['active'] != active['active'] or frozen['protocol']['capability_revision'] != active['revision']:
            raise ResearchError('Create a new epoch for the current capability revision')
        candidate = {'files': store.files(candidate_dir), 'command': candidate_command}
        if not candidate['files'] or candidate == active['active']: raise ResearchError('Provide a concrete changed candidate bundle')
        identity = 'proposal-' + uuid.uuid4().hex[:16]
        record = {'id': identity, 'target': target, 'epoch': epoch, 'actor': actor, 'reason': reason,
                  'candidate': candidate, 'candidate_hash': fingerprint(candidate), 'base_revision': active['revision'],
                  'base_hash': fingerprint(active['active']), 'protocol_hash': frozen['protocol_hash'],
                  'evaluator_hash': frozen['evaluator_hash'], 'sources': evidence, 'status': 'proposed', 'trials': [],
                  'reviews': [], 'created': time.time()}
        with store.tx():
            store.set_value('proposal:' + identity, record)
            store.event('capability:' + target, 'improvement_proposed', record)
    return record


def evaluate(store, identity, split='audit'):
    target = proposal(store, identity)['target']
    with resource_lock(store, 'capability', fingerprint(target)), resource_lock(store, 'proposal', identity):
        item = proposal(store, identity)
        if item['status'] in {'adopted', 'rejected'}:
            raise ResearchError('Closed proposal; create a new proposal for further changes')
        active = state(store, item['target'])
        if active['revision'] != item['base_revision']: raise ResearchError('Baseline changed; propose a new comparison')
        frozen = store.get_value('rsi:' + item['epoch'])
        if frozen['active'] != active['active'] or frozen['protocol']['capability_revision'] != active['revision']:
            raise ResearchError('Create a new epoch for the current baseline')
        path = store.root / 'rsi' / item['epoch'] / 'proposals' / identity
        # CAS is authoritative: edited temporary materializations cannot redefine a proposal.
        if path.exists() and store.files(path) != item['candidate']['files']:
            raise ResearchError('Candidate materialization changed')
        store.restore(item['candidate']['files'], path)
        trial = rsi.evaluate(store, item['epoch'], path, item['candidate']['command'], split=split, promote=False)
        with store.tx():
            latest = proposal(store, identity)
            latest['trials'].append(trial['id'])
            latest['status'] = 'awaiting_review' if split == 'audit' and trial['passed'] else 'evaluated'
            store.set_value('proposal:' + identity, latest)
            store.event('capability:' + item['target'], 'proposal_evaluated', {'proposal': identity, 'trial': trial['id'], 'passed': trial['passed'], 'split': split})
    return trial


def checked_trial(store, item, trial_id):
    frozen = store.get_value('rsi:' + item['epoch'])
    rsi.verify_epoch(store, frozen)
    if frozen['protocol_hash'] != item['protocol_hash'] or frozen['evaluator_hash'] != item['evaluator_hash']:
        raise ResearchError('Proposal evaluation contract changed')
    trial = next((t for t in frozen['trials'] if t['id'] == trial_id and trial_id in item['trials']), None)
    if (not trial or item['trials'][-1] != trial_id or trial['split'] != 'audit' or trial['status'] != 'evaluated' or not trial['passed']
            or trial.get('cleanup_pending') or fingerprint(trial['candidate']) != item['candidate_hash']
            or fingerprint(trial['incumbent']) != item['base_hash']):
        raise ResearchError('Adoption requires this exact candidate to pass its frozen audit against its baseline')
    if frozen['protocol'].get('attestation'):
        from .attestation import verify_evaluation
        context = {'epoch': item['epoch'], 'trial': trial['id'], 'protocol_hash': item['protocol_hash'],
                   'evaluator_hash': item['evaluator_hash'], 'candidate_hash': item['candidate_hash'],
                   'result_hash': fingerprint({k: v for k, v in trial.items() if k != 'attestation'})}
        verify_evaluation(trial.get('attestation', {}), frozen['protocol']['attestation']['public_key'], context)
    return frozen, trial


def review(store, identity, trial_id, *, actor, decision, reason):
    text(actor, 'actor'); text(reason, 'reason')
    if decision not in {'approve', 'reject'}: raise ResearchError('Use approve or reject')
    target = proposal(store, identity)['target']
    with resource_lock(store, 'capability', fingerprint(target)), store.tx():
        item = proposal(store, identity)
        if item['status'] in {'adopted', 'rejected'}: raise ResearchError('Proposal is closed')
        if decision == 'approve':
            if state(store, target)['revision'] != item['base_revision']:
                raise ResearchError('Baseline changed; propose a new comparison')
            frozen, trial = checked_trial(store, item, trial_id)
        else:
            frozen = store.get_value('rsi:' + item['epoch'])
            rsi.verify_epoch(store, frozen)
            trial = next((t for t in frozen['trials'] if t['id'] == trial_id and trial_id in item['trials']), None)
            if not trial: raise ResearchError('Unknown proposal trial')
        if actor not in frozen['protocol']['reviewers'] or actor == item['actor']:
            raise ResearchError('Use a declared researcher reviewer distinct from the proposer')
        record = {'actor': actor, 'decision': decision, 'reason': reason, 'trial': trial_id,
                  'trial_hash': fingerprint(trial), 'candidate_hash': item['candidate_hash'], 'time': time.time()}
        item['reviews'].append(record)
        item['status'] = 'reviewed' if decision == 'approve' else 'rejected'
        store.set_value('proposal:' + identity, item)
        store.event('capability:' + item['target'], 'proposal_reviewed', {'proposal': identity, **record})
    return record


def activate(store, identity, *, expected_revision, actor, reason):
    text(actor, 'actor'); text(reason, 'reason')
    item = proposal(store, identity)
    with resource_lock(store, 'capability', fingerprint(item['target'])), resource_lock(store, 'rsi', item['epoch']):
        with store.tx():
            item = proposal(store, identity)
            current = state(store, item['target'])
            if type(expected_revision) is not int or current['revision'] != expected_revision or expected_revision != item['base_revision']:
                raise ResearchError('Capability revision conflict')
            approval = item['reviews'][-1] if item['reviews'] else None
            if not approval or approval['decision'] != 'approve' or item['status'] != 'reviewed':
                raise ResearchError('Current researcher approval required')
            frozen, trial = checked_trial(store, item, approval['trial'])
            if approval['trial_hash'] != fingerprint(trial) or current['active'] != trial['incumbent'] or frozen.get('running'):
                raise ResearchError('Audit or baseline changed since review')
            if actor not in frozen['protocol']['reviewers']:
                raise ResearchError('Adoption requires a declared researcher reviewer')
            if frozen['protocol'].get('attestation'):
                from .attestation import sign, verify
                context = {'epoch': item['epoch'], 'trial': trial['id'], 'protocol_hash': item['protocol_hash'],
                           'evaluator_hash': item['evaluator_hash'], 'candidate_hash': item['candidate_hash']}
                envelope = sign(frozen['protocol']['attestation'], {**context, 'split': 'audit', 'passed': True,
                                'promoted': True, 'isolation': frozen['isolation'], 'target': item['target'],
                                'proposal': identity, 'review_hash': fingerprint(approval), 'revision': current['revision'] + 1})
                verify(envelope, frozen['protocol']['attestation']['public_key'], context)
                item['adoption_attestation'] = envelope
            for key in item['candidate']['files'].values(): store.blob(key)
            current.update(active=item['candidate'], revision=current['revision'] + 1)
            current['history'].append(item['candidate'])
            frozen['active'] = item['candidate']
            frozen['history'].append(item['candidate'])
            item['status'] = 'adopted'
            store.set_value('rsi:' + item['epoch'], frozen)
            store.set_value('capability:' + item['target'], current)
            store.set_value('proposal:' + identity, item)
            store.event('capability:' + item['target'], 'capability_adopted', {'proposal': identity, 'revision': current['revision'], 'actor': actor, 'reason': reason})
    return {'target': item['target'], 'revision': current['revision'], 'bundle_hash': fingerprint(current['active']),
            'effect': 'future explicit capability bindings; running code and existing runs remain pinned'}


def rollback(store, target, index, *, expected_revision, actor, reason):
    text(actor, 'actor'); text(reason, 'reason')
    with resource_lock(store, 'capability', fingerprint(target)):
        with store.tx():
            current = state(store, target)
            if type(expected_revision) is not int or current['revision'] != expected_revision or type(index) is not int or not 0 <= index < len(current['history']):
                raise ResearchError('Invalid rollback revision/index')
            reviewers = store.get_value('rsi:' + current['epochs'][-1])['protocol']['reviewers']
            if actor not in reviewers: raise ResearchError('Rollback requires a declared researcher reviewer')
            bundle = current['history'][index]
            for key in bundle['files'].values(): store.blob(key)
            for epoch in current['epochs']:
                record = store.get_value('rsi:' + epoch)
                if record.get('running'): raise ResearchError('Wait for active evaluation before rollback')
            current.update(active=bundle, revision=current['revision'] + 1)
            current['history'].append(bundle)
            store.set_value('capability:' + target, current)
            store.event('capability:' + target, 'capability_rollback', {'revision': current['revision'], 'history_index': index, 'actor': actor, 'reason': reason,
                        'new_epoch_required': True})
    return {'revision': current['revision'], 'bundle_hash': fingerprint(bundle), 'new_epoch_required': True}


def export(store, target, destination):
    record = state(store, target)
    destination = Path(destination).resolve()
    if destination.exists(): raise ResearchError('Capability export destination must be new')
    store.restore(record['active']['files'], destination)
    return {'target': target, 'revision': record['revision'], 'bundle_hash': fingerprint(record['active']), 'destination': str(destination)}


def pins(store, manifest, inherited=None):
    result, inputs = {}, {}
    for spec in manifest['stages']:
        if not spec.get('capability'): continue
        if spec.get('command') and not any('{bundle}' in a for a in spec['command']):
            raise ResearchError('A capability-bound command must explicitly use {bundle}')
        if inherited is not None:
            pin = inherited.get(spec['id'])
            if not pin or pin['target'] != spec['capability']:
                raise ResearchError('Missing inherited capability pin')
        else:
            record = state(store, spec['capability'])
            pin = {'target': spec['capability'], 'revision': record['revision'], 'bundle': record['active'],
                   'directory': '_capabilities/' + spec['id'] + '/' + fingerprint(record['active'])}
        prefix = pin['directory']
        result[spec['id']] = pin
        for name, key in pin['bundle']['files'].items(): inputs[prefix + '/' + name] = store.blob(key)
    return result, inputs
