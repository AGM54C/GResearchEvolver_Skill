"""Local resource queue, proof receipts, and grant planning arithmetic."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from .core import ResearchError, digest, finite, fingerprint, safe_path, write_json
from .execution import run_workflow


def enqueue(store, run, resources, priority=0):
    store.get(run)
    for key in ('cpu', 'gpu'):
        if not isinstance(resources.get(key, 0), int) or resources.get(key, 0) < 0:
            raise ResearchError('Resources must be nonnegative integer CPU/GPU counts')
    if not isinstance(priority, int): raise ResearchError('Priority must be an integer')
    with store.tx():
        queue = store.get_value('queue', [])
        if any(q['run'] == run and q['status'] in {'queued', 'running'} for q in queue):
            raise ResearchError('Run already queued')
        item = {'id': 'job-' + uuid.uuid4().hex[:10], 'run': run, 'resources': resources, 'priority': priority,
                'status': 'queued', 'created': time.time()}
        queue.append(item)
        store.set_value('queue', queue)
        store.event(run, 'queued', item)
    return item


def queue_next(store, capacity):
    for key in ('cpu', 'gpu'):
        if not isinstance(capacity.get(key, 0), int) or capacity.get(key, 0) < 0:
            raise ResearchError('Capacity must be nonnegative integer CPU/GPU counts')
    with store.tx():
        queue = store.get_value('queue', [])
        used = {k: sum(q['resources'].get(k, 0) for q in queue if q['status'] == 'running') for k in ('cpu', 'gpu')}
        ready = sorted([q for q in queue if q['status'] == 'queued' and all(q['resources'].get(k, 0) <= capacity.get(k, 0) - used[k] for k in used)],
                       key=lambda q: (-q['priority'], q['created']))
        if not ready: return {'status': 'no_fitting_job', 'used': used}
        item = ready[0]
        item['status'] = 'running'
        store.set_value('queue', queue)
        store.event(item['run'], 'queue_started', item)
    try:
        status = run_workflow(store, item['run'])['status']
    except Exception as exc:
        status = 'failed'
        item['error'] = str(exc)
    with store.tx():
        queue = store.get_value('queue', [])
        target = next(q for q in queue if q['id'] == item['id'])
        target.update(status=status, finished=time.time())
        if 'error' in item: target['error'] = item['error']
        store.set_value('queue', queue)
        store.event(item['run'], 'queue_finished', target)
    return target


def queue_cancel(store, job):
    queue = store.get_value('queue', [])
    item = next((q for q in queue if q['id'] == job), None)
    if not item: raise ResearchError('Unknown job')
    if item['status'] == 'running':
        return store.control(item['run'], 'cancel', 'queue cancellation')
    if item['status'] != 'queued': raise ResearchError('Job is not queued/running')
    with store.tx():
        # Re-read under lock to avoid changing a job just claimed by another worker.
        queue = store.get_value('queue', [])
        target = next(q for q in queue if q['id'] == job)
        if target['status'] != 'queued': raise ResearchError('Job state changed; retry cancellation')
        target['status'] = 'cancelled'
        store.set_value('queue', queue)
        store.event(target['run'], 'queue_cancelled', target)
    return target


def proof_check(data, destination):
    project = Path(data['project']).resolve()
    source = safe_path(project, data['source'])
    text = source.read_text(encoding='utf-8')
    if not data.get('declarations') or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', d) for d in data['declarations']):
        raise ResearchError('Specify concrete theorem declarations for axiom inspection')
    forbidden = bool(re.search(r'\b(sorry|admit|axiom)\b', text))
    result = {'source_hash': digest(source.read_bytes()), 'project': str(project), 'source': data['source'],
              'passed': False, 'status': 'unverified', 'axiom_policy': data.get('allowed_axioms', ['propext', 'Classical.choice', 'Quot.sound'])}
    if forbidden:
        result.update(status='rejected', reason='sorry/admit/axiom token found; remove placeholders or explicitly review axiomatic assumptions')
    elif not shutil.which('lake'):
        result['reason'] = 'Lean/lake not installed'
    else:
        suffix = '\n' + '\n'.join('#print axioms ' + d for d in data['declarations']) + '\n'
        probe = source.with_name('GResearchAudit_' + uuid.uuid4().hex[:8] + '.lean')
        probe.write_text(text + suffix, encoding='utf-8')
        try:
            version = subprocess.run(['lake', 'env', 'lean', '--version'], cwd=project, capture_output=True, text=True, timeout=30)
            run = subprocess.run(['lake', 'env', 'lean', str(probe)], cwd=project, capture_output=True, text=True, timeout=data.get('timeout', 120))
            outputs = run.stdout + '\n' + run.stderr
            found = re.findall(r'depends on axioms:\s*\[([^\]]*)\]', outputs)
            axioms = sorted({x.strip() for group in found for x in group.split(',') if x.strip()})
            no_axioms = len(re.findall(r'does not depend on any axioms', outputs))
            inspected = len(found) + no_axioms >= len(data['declarations'])
            passed = run.returncode == 0 and inspected and set(axioms).issubset(result['axiom_policy']) and 'sorryAx' not in outputs
            result.update(status='checked', passed=passed, stdout=run.stdout, stderr=run.stderr, exit_code=run.returncode,
                          axioms=axioms, declarations_inspected=inspected, compiler=version.stdout.strip(),
                          dependencies={p: digest((project / p).read_bytes()) for p in ('lean-toolchain', 'lake-manifest.json') if (project / p).is_file()})
        finally:
            probe.unlink(missing_ok=True)
    result['limitation'] = 'Compiler proof of formal statement under listed axioms; does not verify that the formal statement matches the scientific claim'
    write_json(destination, result)
    return result


def grant_plan(data):
    errors = []
    for key in ('call', 'aims', 'work_packages', 'risks', 'budget', 'evidence'):
        if not data.get(key): errors.append('missing ' + key)
    aims = {x['id'] for x in data.get('aims', [])}
    evidence = {x['id'] for x in data.get('evidence', [])}
    for a in data.get('aims', []):
        if not a.get('hypothesis') or not a.get('success_criteria'):
            errors.append(a['id'] + ': hypothesis/success criterion absent')
        if not set(a.get('evidence', [])).issubset(evidence) or not a.get('evidence'):
            errors.append(a['id'] + ': unsupported evidence reference')
    for p in data.get('work_packages', []):
        if not p.get('aims') or not set(p['aims']).issubset(aims): errors.append(p['id'] + ': unknown aim')
        if finite(p.get('start_month', 0), minimum=1) > finite(p.get('end_month', 0), minimum=1): errors.append('invalid schedule')
        if not p.get('deliverable') or not p.get('owner'): errors.append(p['id'] + ': missing owner/deliverable')
    total = Decimal('0')
    items = []
    for row in data.get('budget', []):
        q, cost = Decimal(str(row['quantity'])), Decimal(str(row['unit_cost']))
        if not q.is_finite() or not cost.is_finite() or min(q, cost) < 0: raise ResearchError('Budget values must be finite and nonnegative')
        amount = q * cost
        total += amount
        items.append({**row, 'amount': str(amount)})
    if data.get('budget_cap') is not None and total > Decimal(str(data['budget_cap'])): errors.append('budget exceeds cap')
    for r in data.get('risks', []):
        if not all(r.get(k) for k in ('trigger', 'mitigation', 'fallback')): errors.append('risk needs trigger, mitigation, fallback')
    return {'complete': not errors, 'errors': errors, 'budget': items, 'total': str(total), 'currency': data.get('currency'),
            'funder_compliance': 'requires call-specific review of eligibility, overhead, ethics and page limits',
            'submission_performed': False, 'plan_hash': fingerprint(data)}
