"""Executed candidate/incumbent evaluation with frozen scorer and whole-bundle rollback.

The default local executor is for trusted development. Explicit Docker mode puts
candidate code behind a permission boundary; the evaluator/signing host is trusted.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from .core import ResearchError, finite, fingerprint, read_json, safe_path, write_json
from .statistics import paired_analysis


def check_command(command):
    if not isinstance(command, list) or not command or any(not isinstance(x, str) for x in command):
        raise ResearchError('Commands must be argv arrays')


def freeze(store, name, protocol, evaluator_dir, incumbent_dir, incumbent_command):
    protocol = dict(protocol)
    protocol.setdefault('audit_policy', 'fresh-batches')
    if store.get_value('rsi:' + name):
        raise ResearchError('Epoch already exists; create a distinct epoch for changed evaluation')
    from .core import valid_id
    valid_id(name)
    tasks = protocol.get('tasks', [])
    if len({t['id'] for t in tasks}) != len(tasks):
        raise ResearchError('Duplicate tasks')
    if any(t.get('split') not in {'development', 'selection', 'audit', 'final', 'anchor'} for t in tasks):
        raise ResearchError('Explicit data split required')
    if len([t for t in tasks if t['split'] == 'audit']) < 3:
        raise ResearchError('At least three audit tasks required')
    partitions = {}
    audit_groups = set()
    for t in tasks:
        identity = t.get('group_id') or fingerprint(t['input'])
        if identity in partitions and partitions[identity] != t['split']:
            raise ResearchError('Identical input/group crosses evaluation partitions')
        partitions[identity] = t['split']
        if t['split'] == 'audit':
            if identity in audit_groups: raise ResearchError('Audit tasks must use distinct independent groups, including across batches')
            audit_groups.add(identity)
    if protocol['audit_policy'] not in {'fresh-batches', 'reuse-corrected'}:
        raise ResearchError('Unknown audit policy')
    if protocol['audit_policy'] == 'fresh-batches':
        batches = {}
        for t in tasks:
            if t['split'] == 'audit': batches.setdefault(str(t.get('batch', '0')), []).append(t)
        if any(len(v) < 3 for v in batches.values()): raise ResearchError('Each fresh audit batch needs at least three independent groups')
    isolation = protocol.get('isolation')
    if isolation:
        from .isolation import validate
        from .attestation import signer
        validate(isolation)
        if not protocol.get('attestation'): raise ResearchError('Isolated promotion epochs need a pinned evaluator signing key')
        signer(protocol['attestation'])
    if not protocol.get('seeds') or len(set(protocol['seeds'])) != len(protocol['seeds']):
        raise ResearchError('Unique nonempty seed list required')
    if protocol.get('direction', 'higher') not in {'higher', 'lower'}:
        raise ResearchError('Invalid metric direction')
    if not 0 < finite(protocol.get('alpha', .05)) < 1:
        raise ResearchError('Invalid alpha')
    if not isinstance(protocol.get('max_trials'), int) or protocol['max_trials'] < 1:
        raise ResearchError('Predeclare positive max_trials')
    for key, default in [('min_gain', 0), ('max_task_regression', 0), ('timeout', 60), ('trial_seconds', 600)]:
        finite(protocol.get(key, default), key, 0)
    if 'max_time_ratio' in protocol: finite(protocol['max_time_ratio'], 'max_time_ratio', .01)
    check_command(protocol['scorer_command'])
    check_command(incumbent_command)
    evaluator = store.files(evaluator_dir)
    incumbent = {'files': store.files(incumbent_dir), 'command': incumbent_command}
    if not evaluator or not incumbent['files']:
        raise ResearchError('Scorer and incumbent need concrete source files')
    if not protocol.get('protected_checks'):
        raise ResearchError('Declare independent protected checks returned by scorer')
    record = {'name': name, 'protocol': protocol, 'protocol_hash': fingerprint(protocol),
              'evaluator': evaluator, 'evaluator_hash': fingerprint(evaluator), 'active': incumbent,
              'reporting_baseline': incumbent, 'history': [incumbent], 'trials': [], 'final_used': False,
              'isolation': 'docker' if isolation else 'same-permission local processes; not sealed', 'created': time.time()}
    with store.tx():
        store.set_value('rsi:' + name, record)
        store.event('rsi-' + name, 'epoch_frozen', {k: record[k] for k in ('protocol_hash', 'evaluator_hash', 'isolation')})
    return record


def verify_epoch(store, record):
    if fingerprint(record['protocol']) != record['protocol_hash'] or fingerprint(record['evaluator']) != record['evaluator_hash']:
        raise ResearchError('Frozen protocol or evaluator changed')
    for files in [record['evaluator'], record['active']['files'], record.get('reporting_baseline', record['history'][0])['files']]:
        for h in files.values(): store.blob(h)


def invoke(command, directory, extra, timeout, log):
    argv = [sys.executable if x == '{python}' else x for x in command] + extra
    start = time.monotonic()
    with log.with_suffix('.stdout').open('wb') as out, log.with_suffix('.stderr').open('wb') as err:
        # Reuse workflow cancellation primitive so timed-out child trees are stopped locally.
        from .execution import terminate
        process = subprocess.Popen(argv, cwd=directory, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                   start_new_session=os.name != 'nt',
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        try:
            rc = process.wait(timeout=timeout)
        except BaseException:
            terminate(process)
            raise
    if rc:
        raise ResearchError(f'Command failed ({rc}); inspect {log}')
    return {'seconds': time.monotonic() - start, 'argv': argv, 'exit_code': rc}


def evaluate(store, name, candidate_dir, candidate_command, *, split='audit', promote=False):
    check_command(candidate_command)
    if split not in {'development', 'selection', 'audit', 'final'}:
        raise ResearchError('Unsupported split')
    if promote and split != 'audit':
        raise ResearchError('Only frozen audit can authorize promotion')
    key = 'rsi:' + name
    with store.tx():
        record = store.get_value(key)
        if not record:
            raise ResearchError('Unknown RSI epoch')
        verify_epoch(store, record)
        if record.get('running'):
            raise ResearchError('Epoch already evaluating; inspect interrupted trial before recovery')
        if split == 'final' and record['final_used']:
            raise ResearchError('Final reporting set already used; do not recycle it for optimization')
        if split == 'audit' and sum(t['split'] == 'audit' for t in record['trials']) >= record['protocol']['max_trials']:
            raise ResearchError('Audit reuse budget exhausted; new independent audit required')
        tasks = [t for t in record['protocol']['tasks'] if t['split'] == split]
        audit_batch = None
        if split == 'audit' and record['protocol'].get('audit_policy') == 'fresh-batches':
            used = {t.get('audit_batch') for t in record['trials'] if t['split'] == 'audit'}
            available = sorted({str(t.get('batch', '0')) for t in tasks} - used)
            if not available: raise ResearchError('Fresh audit batches exhausted; provision independent tasks in a new epoch')
            audit_batch = available[0]
            tasks = [t for t in tasks if str(t.get('batch', '0')) == audit_batch]
        if len(tasks) < 3:
            raise ResearchError('This split needs >=3 independent tasks')
        candidate = {'files': store.files(candidate_dir), 'command': candidate_command}
        if not candidate['files']:
            raise ResearchError('Candidate has no source')
        reference = record.get('reporting_baseline', record['history'][0]) if split == 'final' else record['active']
        trial = {'id': 'trial-' + uuid.uuid4().hex[:12], 'split': split, 'status': 'running',
                 'audit_batch': audit_batch, 'audit_policy': record['protocol'].get('audit_policy', 'reuse-corrected'),
                 'candidate': candidate, 'incumbent': reference, 'started': time.time(),
                 'comparison_role': 'frozen_reporting_baseline' if split == 'final' else 'current_incumbent'}
        record['trials'].append(trial)
        record['running'] = trial['id']
        record['worker_pid'] = os.getpid()
        if split == 'final': record['final_used'] = True
        store.set_value(key, record)
        store.event('rsi-' + name, 'trial_started', trial)
    root = store.root / 'rsi' / name / trial['id']
    root.mkdir(parents=True)
    protocol = record['protocol']
    rows, observations, reasons = [], [], []
    started = time.monotonic()
    try:
        for ti, task in enumerate(tasks):
            for seed in protocol['seeds']:
                scores = {}
                # Alternate order to reduce systematic warm-up/load-order bias.
                order = ['candidate', 'incumbent'] if (ti + protocol['seeds'].index(seed)) % 2 == 0 else ['incumbent', 'candidate']
                for label in order:
                    remaining = protocol.get('trial_seconds', 600) - (time.monotonic() - started)
                    if remaining <= 0: raise ResearchError('Trial wall-clock budget exhausted')
                    folder = root / f'{ti}-{protocol["seeds"].index(seed)}-{label}'
                    code, scorer = folder / 'strategy', folder / 'scorer'
                    code.mkdir(parents=True)
                    scorer.mkdir()
                    store.restore(trial[label]['files'], code)
                    store.restore(record['evaluator'], scorer)
                    taskpath, privatepath, prediction, scorepath = (folder / p for p in ('input.json', 'private-task.json', 'prediction.json', 'score.json'))
                    # Only task.input goes to strategy. Expected answers belong to the scorer.
                    write_json(taskpath, {'id': task['id'], 'input': task['input']})
                    write_json(privatepath, task)
                    if protocol.get('isolation'):
                        from .isolation import run as isolated_run
                        run = isolated_run(protocol['isolation'], code, taskpath, trial[label]['command'], folder / 'isolated',
                                           seed=seed, timeout=min(protocol.get('timeout', 60), remaining))
                        if run['status'] != 'completed': raise ResearchError(run.get('error', 'Isolated strategy failed'))
                        prediction.write_bytes((folder / 'isolated' / 'prediction.json').read_bytes())
                    else:
                        run = invoke(trial[label]['command'], code,
                                     ['--task', str(taskpath), '--seed', str(seed), '--output', str(prediction)],
                                     min(protocol.get('timeout', 60), remaining), folder / 'strategy')
                    if not prediction.is_file(): raise ResearchError('Strategy produced no prediction')
                    prediction_hash = store.put(prediction.read_bytes())
                    before = fingerprint(store.files(scorer))
                    remaining = protocol.get('trial_seconds', 600) - (time.monotonic() - started)
                    if remaining <= 0: raise ResearchError('Trial budget exhausted before scoring')
                    scoring = invoke(protocol['scorer_command'], scorer,
                                     ['--task', str(privatepath), '--prediction', str(prediction), '--output', str(scorepath)],
                                     min(protocol.get('timeout', 60), remaining), folder / 'scorer')
                    if before != fingerprint(store.files(scorer)) or before != record['evaluator_hash']:
                        raise ResearchError('Scorer files mutated during evaluation')
                    score = read_json(scorepath)
                    finite(score['metric'], 'scorer metric')
                    for check in protocol['protected_checks']:
                        if score.get('checks', {}).get(check) is not True:
                            reasons.append(f'{label}:{task["id"]}:protected check {check} failed')
                    scores[label] = score['metric']
                    observations.append({'task': task['id'], 'domain': task.get('domain', 'unspecified'), 'seed': seed,
                                         'strategy': label, 'run': run, 'scoring': scoring, 'score': score,
                                         'prediction_hash': prediction_hash, 'score_hash': store.put(scorepath.read_bytes())})
                rows.append({'task': task['id'], 'seed': seed, **scores})
        analysis = paired_analysis(rows, alpha=protocol.get('alpha', .05) / protocol['max_trials'],
                                   resamples=protocol.get('resamples', 4000), seed=protocol.get('bootstrap_seed', 0),
                                   direction=protocol.get('direction', 'higher'))
        if analysis['ci'][0] <= protocol.get('min_gain', 0): reasons.append('gain lower bound does not exceed minimum; ties retain incumbent')
        if min(analysis['task_gains'].values()) < -protocol.get('max_task_regression', 0): reasons.append('task regression limit exceeded')
        domains = {t.get('domain', 'unspecified') for t in tasks}
        if not set(protocol.get('required_domains', [])).issubset(domains): reasons.append('required domain coverage absent')
        seconds = {k: sum(o['run']['seconds'] for o in observations if o['strategy'] == k) for k in ('candidate', 'incumbent')}
        if seconds['candidate'] > seconds['incumbent'] * protocol.get('max_time_ratio', float('inf')):
            reasons.append('runtime ratio limit exceeded')
        trial.update(status='evaluated', rows=rows, observations=observations, analysis=analysis, reasons=reasons,
                     passed=not reasons, seconds=seconds, promoted=False,
                     uncertainty='bootstrap gate is approximate; fresh groups reduce reuse overfit but do not eliminate selection or pretraining contamination')
    except Exception as exc:
        trial.update(status='failed', reasons=[str(exc)], passed=False, promoted=False, observations=observations)
    with store.tx():
        latest = store.get_value(key)
        verify_epoch(store, latest)
        if latest['protocol_hash'] != record['protocol_hash'] or latest['active'] != record['active']:
            trial.update(passed=False, reasons=trial['reasons'] + ['epoch or active strategy changed during trial'])
        if promote and trial['passed']:
            trial['promoted'] = True
        if protocol.get('attestation'):
            from .attestation import sign
            payload = {'epoch': name, 'trial': trial['id'], 'protocol_hash': record['protocol_hash'],
                       'evaluator_hash': record['evaluator_hash'], 'candidate_hash': fingerprint(candidate),
                       'split': split, 'passed': trial['passed'], 'promoted': trial['promoted'],
                       'isolation': record['isolation'], 'audit_batch': audit_batch,
                       'result_hash': fingerprint(trial)}
            try: trial['attestation'] = sign(protocol['attestation'], payload)
            except Exception as exc:
                trial.update(passed=False, promoted=False, reasons=trial['reasons'] + ['attestation failed: ' + str(exc)])
        if trial['promoted']:
            latest['active'] = candidate
            latest['history'].append(candidate)
        latest['trials'][-1] = trial
        latest['running'] = None
        latest['worker_pid'] = None
        store.set_value(key, latest)
        store.event('rsi-' + name, 'trial_finished', trial)
    write_json(root / 'result.json', trial)
    return trial


def recover_epoch(store, name, reason):
    from .execution import process_exists
    if not reason: raise ResearchError('Record recovery reason and external-state inspection')
    with store.tx():
        record = store.get_value('rsi:' + name)
        if not record or not record.get('running'):
            raise ResearchError('No interrupted trial to recover')
        if record.get('worker_pid') and process_exists(record['worker_pid']):
            raise ResearchError('Trial worker still exists; do not start a concurrent evaluation')
        trial = next(t for t in record['trials'] if t['id'] == record['running'])
        trial.update(status='failed', passed=False, promoted=False, reasons=['interrupted trial; ' + reason])
        record.update(running=None, worker_pid=None)
        store.set_value('rsi:' + name, record)
        store.event('rsi-' + name, 'trial_recovered', {'trial': trial['id'], 'reason': reason, 'audit_use_retained': True})
    return trial


def rollback(store, name, index, reason):
    if not reason:
        raise ResearchError('Record rollback reason')
    with store.tx():
        record = store.get_value('rsi:' + name)
        if not record or record.get('running'):
            raise ResearchError('Unknown or busy epoch')
        if not 0 <= index < len(record['history']):
            raise ResearchError('Unknown strategy version')
        restored = record['history'][index]
        for h in restored['files'].values(): store.blob(h)
        record['active'] = restored
        store.set_value('rsi:' + name, record)
        store.event('rsi-' + name, 'rollback', {'index': index, 'reason': reason, 'strategy': restored})
    return restored


def materialize(store, name, destination):
    """Export the promoted whole strategy as explicit next-run inputs, never overwrite core."""
    from .core import native_path
    record = store.get_value('rsi:' + name)
    if not record: raise ResearchError('Unknown epoch')
    verify_epoch(store, record)
    destination = native_path(destination)
    if destination.exists(): raise ResearchError('Choose a new destination; existing strategies are not overwritten')
    destination.mkdir(parents=True)
    store.restore(record['active']['files'], destination / 'code')
    metadata = {'epoch': name, 'strategy_hash': fingerprint(record['active']), 'command': record['active']['command'],
                'files': record['active']['files'], 'protocol_hash': record['protocol_hash'],
                'inputs': {p: str(destination / 'code' / p) for p in record['active']['files']}}
    write_json(destination / 'strategy.json', metadata)
    with store.tx(): store.event('rsi-' + name, 'strategy_materialized', {'strategy_hash': metadata['strategy_hash'], 'destination': str(destination)})
    return metadata


def epoch_comparison(store, left, right):
    a, b = store.get_value('rsi:' + left), store.get_value('rsi:' + right)
    if not a or not b: raise ResearchError('Unknown epoch')
    anchors = lambda r: [t for t in r['protocol']['tasks'] if t['split'] == 'anchor']
    return {'same_evaluator': a['evaluator_hash'] == b['evaluator_hash'], 'same_anchor': bool(anchors(a)) and anchors(a) == anchors(b),
            'scores_comparable': a['protocol_hash'] == b['protocol_hash'] and a['evaluator_hash'] == b['evaluator_hash'],
            'required_for_changed_evaluator': 'Execute both evaluators on a frozen external anchor; semantic calibration must be reviewed. Retain history; invalidate dependent scores.'}
