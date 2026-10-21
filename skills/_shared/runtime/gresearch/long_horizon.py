"""Persistent research projects, bounded context handoffs and scientific gates.

This is a single-host coordinator over the existing Store and Agent, not a new
executor. All model/tool attempts reserve from one project ledger. Human decisions
and raw context archives survive handoffs. Semantic truth is not inferred here.
"""
from __future__ import annotations

from contextlib import nullcontext
import copy
import time
import uuid

from .core import ResearchError, atomic_bytes, canonical, fingerprint, valid_id
from . import memory, validity


LIMITS = {'model_calls': 120, 'tool_calls': 400, 'active_seconds': 14400,
          'output_tokens': 240000, 'input_chars': 12000000, 'external_cost': 0}
POLICY = {'max_compactions': 20, 'require_review': True, 'max_notes': 300}
NOTE_TYPES = {'goal', 'hypothesis', 'route', 'finding', 'negative_result', 'experience'}
JOB_SETTLED = {'completed', 'failed', 'cancelled', 'blocked', 'paused', 'awaiting_review'}


class ReviewRequired(ResearchError):
    def __init__(self, binding):
        super().__init__('Researcher review of the exact premises/conditions is pending')
        self.binding = binding


class BudgetExhausted(ResearchError): pass


def tx(store): return nullcontext() if store.db.in_transaction else store.tx()
def key(identity): return 'long-project:' + valid_id(identity)


def get(store, project):
    value = store.get_value(key(project))
    if not value: raise ResearchError('Unknown long-horizon project')
    return value


def recorded_snapshot(store, project, snapshot):
    """A CAS object is not provenance by itself; require an actual project event."""
    get(store, project)
    if not any(event['payload']['data'].get('snapshot') == snapshot for event in store.events(key(project))):
        raise ResearchError('Snapshot was not recorded by this project')
    from .agent_protocol import strict_json
    return strict_json(store.blob(snapshot).decode('utf-8'))


def save(store, project, event, detail=None):
    project['previous_snapshot'] = project.get('snapshot')
    project['revision'] += 1
    project['updated_at'] = time.time()
    body = {k: v for k, v in project.items() if k != 'snapshot'}
    project['snapshot'] = store.put(canonical(body).encode('utf-8'))
    store.set_value(key(project['id']), project)
    store.event(key(project['id']), event, {'snapshot': project['snapshot'], 'detail': detail})


def create(store, identity, objective, *, constraints=None, budget=None, policy=None, actor='researcher'):
    valid_id(identity)
    if not isinstance(objective, str) or not objective.strip() or len(objective) > 20000: raise ResearchError('Bounded project objective required')
    limits, options = {**LIMITS, **(budget or {})}, {**POLICY, **(policy or {})}
    if set(limits) != set(LIMITS) or set(options) != set(POLICY): raise ResearchError('Unknown project budget/policy field')
    for name, value in limits.items():
        if type(value) not in {int, float} or value < 0 or value > 1e12: raise ResearchError('Invalid project budget: ' + name)
    canonical(limits)
    if type(options['require_review']) is not bool: raise ResearchError('require_review must be boolean')
    for name, maximum in [('max_compactions', 100), ('max_notes', 1000)]:
        if type(options[name]) is not int or not 1 <= options[name] <= maximum: raise ResearchError('Invalid project policy: ' + name)
    constraints = constraints or []
    if not isinstance(constraints, list) or any(not isinstance(c, str) or not c.strip() or len(c) > 4000 for c in constraints) or len(constraints) > 100:
        raise ResearchError('Use at most 100 bounded project constraints')
    human(actor)
    with tx(store):
        if store.get_value(key(identity)): raise ResearchError('Project already exists')
        project = {'id': identity, 'objective': objective, 'constraints': constraints, 'budget': limits, 'policy': options,
                   'revision': 0, 'spent': {k: 0 for k in limits}, 'reservations': {}, 'sessions': [], 'notes': {},
                   'decisions': [], 'reviews': {}, 'jobs': {}, 'reports': [], 'created_by': actor}
        save(store, project, 'project_created')
    report(store, identity)
    return project


def human(actor):
    if not isinstance(actor, str) or not actor.strip() or actor.startswith('agent:'): raise ResearchError('Use the actual researcher identity')


def attach(store, project, session):
    with tx(store):
        p = get(store, project)
        if session not in p['sessions']: p['sessions'].append(session)
        save(store, p, 'session_attached', session)


def remaining(project): return {k: max(0, project['budget'][k] - project['spent'][k]) for k in LIMITS}


def reserve(store, project, token, session, amounts):
    """Called in the same transaction as the Agent's durable attempt intent."""
    with tx(store):
        p = get(store, project)
        if token in p['reservations']: raise ResearchError('Duplicate project reservation')
        if session not in p['sessions']: raise ResearchError('Session is outside this project')
        amounts = dict(amounts)
        left = remaining(p)
        if 'active_seconds' in amounts: amounts['active_seconds'] = min(amounts['active_seconds'], left['active_seconds'])
        if left['active_seconds'] <= 0 or any(v < 0 or v > left[k] for k, v in amounts.items()):
            raise BudgetExhausted('Project budget exhausted')
        for k, v in amounts.items(): p['spent'][k] += v
        p['reservations'][token] = {'session': session, 'amounts': amounts, 'status': 'reserved'}
        save(store, p, 'budget_reserved', token)
    return amounts


def settle(store, project, token, seconds, usage=None):
    with tx(store):
        p = get(store, project); entry = p['reservations'].get(token)
        if not entry: raise ResearchError('Missing project reservation')
        if entry['status'] == 'settled': return entry
        # With no reliable cleanup duration retain the full time reservation.
        actual = entry['amounts'].get('active_seconds', 0) if seconds is None else max(0, seconds)
        p['spent']['active_seconds'] += actual - entry['amounts'].get('active_seconds', 0)
        entry.update(status='settled', actual_seconds=actual, usage=usage)
        save(store, p, 'budget_settled', token)
    return entry


def note(store, project, identity, kind, text, *, expected_revision, status='proposed', evidence=None, prediction=None, outcome=None, actor):
    valid_id(identity)
    if kind not in NOTE_TYPES or status not in {'proposed', 'active', 'paused', 'completed', 'rejected'}: raise ResearchError('Invalid research note type/status')
    if not isinstance(text, str) or not text.strip() or len(text) > 6000: raise ResearchError('Use a bounded substantive research note')
    evidence = evidence or []
    if type(expected_revision) is not int: raise ResearchError('expected_revision must be an integer')
    if not isinstance(evidence, list) or len(evidence) > 100: raise ResearchError('evidence must list at most 100 CAS hashes')
    if len(canonical({'prediction': prediction, 'outcome': outcome})) > 12000: raise ResearchError('Prediction/outcome too large; use evidence references')
    for h in evidence: store.blob(h)
    with tx(store):
        p = get(store, project)
        if p['revision'] != expected_revision: raise ResearchError('Project revision changed; read before editing')
        if identity not in p['notes'] and len(p['notes']) >= p['policy']['max_notes']: raise ResearchError('Project note limit reached')
        previous = p['notes'].get(identity)
        item = {'id': identity, 'kind': kind, 'text': text, 'status': status, 'evidence': evidence,
                'prediction': prediction if prediction is not None else (previous or {}).get('prediction'),
                'outcome': outcome if outcome is not None else (previous or {}).get('outcome'), 'actor': actor, 'previous': fingerprint(previous) if previous else None,
                'scientific_validation': 'not_implied'}
        if previous and previous.get('prediction') is not None and prediction is not None and prediction != previous['prediction']:
            raise ResearchError('Predictions are immutable; record a new proposal before seeing its outcome')
        p['notes'][identity] = item
        save(store, p, 'research_note', item)
    return item


def decide(store, project, text, *, actor, target=None, expected_hash=None):
    human(actor)
    if not isinstance(text, str) or not text.strip() or len(text) > 6000: raise ResearchError('Decision needs bounded text')
    with tx(store):
        p = get(store, project)
        if target and (target not in p['notes'] or fingerprint(p['notes'][target]) != expected_hash):
            raise ResearchError('Decision target changed; inspect the current note')
        item = {'id': 'decision-' + uuid.uuid4().hex[:12], 'target': target, 'target_hash': expected_hash,
                'actor': actor, 'text': text, 'time': time.time()}
        p['decisions'].append(item)
        p['reviews'] = {}  # Scientific acceptance must be reconsidered under changed direction.
        save(store, p, 'researcher_decision', item)
    # The existing durable steering inbox withdraws old queued intentions.
    from . import agent
    for sid in p['sessions']:
        s = agent.get(store, sid)
        if s['status'] not in {'completed', 'cancelled'}: agent.steer(store, sid, text, actor=actor)
    report(store, project)
    return item


def review(store, project, requirements, conditions, *, actor, reason):
    human(actor)
    if not reason.strip() or not requirements: raise ResearchError('Review requires exact premises and a reason')
    snap = memory.get(store, project)
    result = validity.check(snap['graph'], requirements, conditions=conditions)
    if not result['eligible']: raise ResearchError('Resolve invalid premises before acceptance: ' + canonical(result['errors']))
    context = {'graph_snapshot': snap['snapshot'], 'requires': requirements, 'conditions': conditions}
    record = {**context, 'actor': actor, 'reason': reason, 'time': time.time()}
    with tx(store):
        if memory.get(store, project)['snapshot'] != snap['snapshot']: raise ResearchError('Graph changed during review')
        p = get(store, project); p['reviews'][fingerprint(context)] = record; save(store, p, 'scientific_review', record)
    return record


def bind_action(store, session, name, arguments, requirements, conditions, purpose, reason):
    from . import agent_tools as gateway
    state = store.get_value('agent:' + valid_id(session))
    if not state or not state.get('long_project'): raise ResearchError('Action binding requires a long-horizon session')
    if name not in {'run_command', 'report_stage', 'research_operation'} or purpose not in {'explore', 'experiment', 'conclude', 'learn'}:
        raise ResearchError('Unsupported action purpose/target')
    if not isinstance(reason, str) or not reason.strip(): raise ResearchError('Action binding needs rationale')
    gateway.validate_call({'name': name, 'arguments': arguments})
    p = get(store, state['long_project'])
    if not requirements and purpose != 'explore': raise ResearchError('Scientific actions require explicit premises')
    if not isinstance(requirements, dict) or not isinstance(conditions, dict): raise ResearchError('Premises/conditions must be objects')
    snap = memory.get(store, p['id']) if requirements else None
    result = validity.check(snap['graph'], requirements, conditions=conditions) if snap else {'eligible': True, 'pins': {}, 'nodes': [], 'errors': []}
    record = {'name': name, 'arguments': arguments, 'requires': requirements, 'conditions': conditions, 'purpose': purpose,
              'reason': reason, 'graph_snapshot': snap['snapshot'] if snap else None, 'check': result,
              'decisions_hash': fingerprint(p['decisions'])}
    from . import memtx
    record['memtx_snapshot'] = memtx.get(store, p['id'])['snapshot']
    signature = fingerprint({'name': name, 'arguments': arguments})
    with tx(store):
        store.set_value('action-binding:' + session + ':' + signature, record)
        store.event('agent:' + session, 'action_bound', {'signature': signature, **record})
    return {'call_hash': signature, **record, 'review_required': p['policy']['require_review'] and purpose != 'explore'}


def guarded(call):
    return call['name'] in {'run_command', 'report_stage'} or (call['name'] == 'research_operation' and call['arguments']['operation'] in {'capability-propose', 'rsi-evaluate'})


def check_action(store, state, call):
    if not state.get('long_project') or not guarded(call): return None
    signature = fingerprint({'name': call['name'], 'arguments': call['arguments']})
    binding = store.get_value('action-binding:' + state['id'] + ':' + signature)
    if not binding: raise ResearchError('Use bind_action for this exact call and its scientific premises first')
    p = get(store, state['long_project'])
    if fingerprint(p['decisions']) != binding['decisions_hash']: raise ResearchError('Researcher direction changed; rebind the action')
    if binding['requires']:
        snap = memory.get(store, p['id'])
        if snap['snapshot'] != binding['graph_snapshot']: raise ResearchError('Scientific state changed; rebind the action')
        check = validity.check(snap['graph'], binding['requires'], conditions=binding['conditions'])
        if not check['eligible']: raise ResearchError('Scientific premises need repair: ' + canonical(check['errors']))
        if binding['purpose'] != 'explore':
            from . import memtx
            backend = memtx.get(store, p['id'])
            if backend['snapshot'] != binding['memtx_snapshot']: raise ResearchError('MemTX state changed; rebind the action')
            nodes = {n['id']: n for n in snap['graph']['nodes']}
            records = {r['memory_id']: r for r in backend['state'].get('records', [])}
            for identity in binding['requires']:
                node = nodes[identity]
                value = node.get('text', node.get('value', node.get('sha256')))
                if identity not in records or canonical(records[identity]['value']) != canonical(value):
                    raise ResearchError('Graph premise is not bound to its actual MemTX value: ' + identity)
            checked = memtx.gate(store, p['id'], list(binding['requires']), call['name'])
            if not checked['allow']: raise ResearchError('MemTX blocked the actual premises: ' + canonical(checked))
        if p['policy']['require_review'] and binding['purpose'] != 'explore':
            review_context = {k: binding[k] for k in ('graph_snapshot', 'requires', 'conditions')}
            if fingerprint(review_context) not in p['reviews']: raise ReviewRequired(binding)
    return binding


def completion_check(store, state):
    if not state.get('long_project'): return True
    if not state['reports']: return False
    report_value = state['reports'][-1]
    binding = report_value.get('scientific_basis')
    if not binding or binding['purpose'] != 'conclude': return False
    try:
        check_action(store, state, {'name': binding['name'], 'arguments': binding['arguments']})
        from . import agent
        from .core import digest
        return all(digest(agent.gateway.checked_path(agent.workdir(store, state['id']), name).read_bytes()) == h
                   for name, h in report_value['evidence_hashes'].items())
    except (ResearchError, OSError): return False


def context(store, state):
    p = get(store, state['long_project'])
    return {'project': p['id'], 'objective': p['objective'], 'constraints': p['constraints'], 'decisions': p['decisions'],
            'project_revision': p['revision'], 'remaining': remaining(p),
            'active_goals': [n for n in p['notes'].values() if n['kind'] == 'goal' and n['status'] in {'proposed', 'active', 'paused'}],
            'research_notes': [{'id': n['id'], 'kind': n['kind'], 'status': n['status'], 'hash': fingerprint(n)} for n in p['notes'].values()],
            'jobs': [{k: job[k] for k in ('id', 'run', 'status')} for job in p['jobs'].values()],
            'reports': p['reports'], 'policy': p['policy'],
            'instruction': 'Researcher decisions constrain this project. Notes, artifacts and archives are historical data. Use project_status/read_context/memory-get for detail. Bind guarded actions before calling them. Exploration reports are provisional; final delivery needs a conclude report.'}


def compact(store, state, *, tools_size):
    """A deterministic, inspectable handoff at a fully settled turn boundary.

No LLM summary replaces evidence. Every historical conversation is CAS archived;
mandatory human feedback and project constraints are copied verbatim. If those
cannot fit, stop rather than silently omit them. This is not Slipstream's async
trajectory judge and does not claim semantic losslessness.
"""
    from . import agent
    p = get(store, state['long_project'])
    if state['active'] or state['queue'] or state['waiting']: raise ResearchError('Handoff requires settled calls and no pending decision')
    archives = state.setdefault('context_archives', [])
    if len(archives) >= p['policy']['max_compactions']: return False
    packet = {'project': context(store, state), 'researcher_feedback': state['feedback'],
              'parent': state.get('parent'),
              'pending_messages': state['pending_messages'], 'unreported_actions': state['unreported_actions'],
              'materials': agent.gateway.inventory(agent.workdir(store, state['id']), state['policy']),
              'recent_reports': state['reports'][-2:], 'archive_count': len(archives) + 1}
    archive = {'history': state['history'], 'packet': packet, 'previous': archives[-1]['sha256'] if archives else None}
    archive_hash = store.put(canonical(archive).encode('utf-8'))
    history = [copy.deepcopy(state['history'][0]), {'role': 'user', 'content': state['objective']},
               {'role': 'user', 'content': canonical({'handoff': packet, 'archive': archive_hash})}]
    # Require meaningful headroom, so a large mandatory packet cannot spin.
    candidate = {**state, 'history': history}
    if len(canonical(agent.model_history(candidate))) + tools_size > state['config']['max_input_chars'] * .75: return False
    record = {'epoch': len(archives) + 1, 'sha256': archive_hash, 'packet_hash': fingerprint(packet),
              'prior_chars': len(canonical(state['history'])), 'new_chars': len(canonical(history))}
    archives.append(record)
    state['history'] = history
    state['pending_messages'] = []
    with tx(store): agent._save(store, state, 'context_handoff', record)
    return True


def read_context(store, session, epoch, offset, limit):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20000: raise ResearchError('Invalid archive page')
    state = store.get_value('agent:' + valid_id(session))
    if not state: raise ResearchError('Unknown session')
    archives = state.get('context_archives', [])
    if type(epoch) is not int: raise ResearchError('Unknown context epoch')
    if epoch == 0 and state.get('parent', {}).get('archive_hash'): archive_hash = state['parent']['archive_hash']
    elif 1 <= epoch <= len(archives): archive_hash = archives[epoch - 1]['sha256']
    else: raise ResearchError('Unknown context epoch; epoch 0 is the retained parent session')
    raw = store.blob(archive_hash).decode('utf-8')
    return {'text': raw[offset:offset + limit], 'next_offset': offset + limit if len(raw) > offset + limit else None,
            'sha256': archive_hash, 'untrusted_source_data': True}


def track_job(store, project, run, *, actor, cost=0):
    """Bind an existing authorized DAG (including SSH stages), before execution.

The existing run/queue is the executor. We reserve its declared cost here and
observe durable results instead of inventing a new SSH submission protocol.
"""
    human(actor)
    manifest, state = store.get(run)
    if type(cost) not in {int, float} or cost < manifest.get('budget', {}).get('cost', 0): raise ResearchError('Reserve at least the declared workflow cost')
    canonical(cost)
    if state['status'] != 'ready' or state.get('worker'): raise ResearchError('Track a ready workflow before execution')
    with tx(store):
        p = get(store, project)
        if run in p['jobs']: raise ResearchError('Workflow already tracked')
        if cost > remaining(p)['external_cost']: raise ResearchError('Project external cost budget exhausted')
        p['spent']['external_cost'] += cost
        p['jobs'][run] = {'id': run, 'run': run, 'manifest_hash': fingerprint(manifest), 'status': 'pending',
                          'reserved_cost': cost, 'actor': actor, 'outputs': {}, 'cost_status': 'reserved_not_provider_invoice'}
        save(store, p, 'workflow_tracked', run)
    return p['jobs'][run]


def tick(store, project):
    """Refresh workflow receipts and ready waiting sessions; never replay a job."""
    from . import agent
    from .locking import resource_lock, LockBusy
    with tx(store):
        p = get(store, project)
        changed = False
        for job in p['jobs'].values():
            if job['status'] in {'completed', 'cancelled'}: continue
            manifest, state = store.get(job['run'])
            if fingerprint(manifest) != job['manifest_hash']: raise ResearchError('Tracked workflow manifest changed')
            if state['status'] in JOB_SETTLED:
                receipt = store.put(canonical(state).encode('utf-8'))
                if job.get('receipt') != receipt:
                    job.update(status=state['status'], outputs=state['artifacts'], receipt=receipt)
                    changed = True
            elif job['status'] != 'pending':
                job['status'] = 'pending'; changed = True
        if changed: save(store, p, 'workflow_results_observed')
    awakened = []
    for sid in p['sessions']:
        try:
            with resource_lock(store, 'agent', sid):
                state = agent.get(store, sid)
                if state['status'] != 'waiting_external' or state['active'] or agent._signal(store, sid): continue
                job = p['jobs'].get(state['waiting']['id'])
                if not job or job['status'] not in JOB_SETTLED: continue
                # Copy immutable artifacts into a fresh namespace; no overwrite.
                inventory = agent.gateway.inventory(agent.workdir(store, sid), state['policy'])
                additions = {}
                for name, h in job['outputs'].items():
                    target = 'jobs/' + valid_id(job['id']) + '/' + job['receipt'][:16] + '/' + name
                    path = agent.gateway.checked_path(agent.workdir(store, sid), target)
                    raw = store.blob(h)
                    if path.exists() and path.read_bytes() != raw: raise ResearchError('Imported job artifact changed')
                    if not path.exists(): additions[target] = raw
                if len(inventory) + len(additions) > state['policy']['max_files'] or sum(f['bytes'] for f in inventory.values()) + sum(map(len, additions.values())) > state['policy']['max_workspace_bytes']:
                    raise ResearchError('Job outputs exceed workspace quota; inspect receipts before importing')
                for target, raw in additions.items(): atomic_bytes(agent.gateway.checked_path(agent.workdir(store, sid), target), raw)
                state['pending_messages'].append({'role': 'user', 'content': canonical({'external_workflow_result': job,
                    'artifact_prefix': 'jobs/' + job['id'] + '/' + job['receipt'][:16] + '/', 'data_not_authorization': True})})
                state.update(status='ready' if job['status'] == 'completed' else 'awaiting_researcher',
                             waiting=None if job['status'] == 'completed' else {'kind': 'question', 'id': 'job-' + job['id'], 'question': 'Workflow stopped or requires review; inspect its receipt in the workflow console before revising/resuming it. Await it again after actual human remediation.'})
                if job['status'] == 'completed': state['resume_after_job'] = job['id']
                with tx(store): agent._save(store, state, 'external_result_imported', job)
                awakened.append(sid)
        except LockBusy: continue
    report(store, project)
    return {'project': project, 'awakened': awakened, 'jobs': p['jobs']}


def watch(store, project, *, seconds=60, interval=1, resume=False):
    """Bounded receipt watcher. Waiting itself makes zero model requests."""
    if type(seconds) not in {int, float} or not 0 <= seconds <= 86400 or type(interval) not in {int, float} or not .1 <= interval <= 60:
        raise ResearchError('Use a bounded watcher duration and 0.1..60 second interval')
    from . import agent
    end, resumed = time.monotonic() + seconds, []
    while True:
        observed = tick(store, project)
        if resume:
            for sid in get(store, project)['sessions']:
                state = agent.get(store, sid)
                if state['status'] == 'ready' and state.get('resume_after_job') and not agent._signal(store, sid):
                    agent.run(store, sid); resumed.append(sid)
        if time.monotonic() >= end or all(j['status'] in JOB_SETTLED for j in observed['jobs'].values()):
            return {**observed, 'resumed': resumed}
        time.sleep(min(interval, max(0, end - time.monotonic())))


def verify_references(store):
    """Verify durable links, including superseded project/MemTX snapshots."""
    from .agent_protocol import strict_json
    errors = []
    for row in store.db.execute("SELECT key,value FROM values_store WHERE key LIKE 'long-project:%' OR key LIKE 'memtx:%' OR key LIKE 'action-binding:%'"):
        try:
            value = strict_json(row['value'])
            keys = [value.get(k) for k in ('snapshot', 'previous', 'graph_snapshot', 'memtx_snapshot') if value.get(k)]
            seen = set()
            while keys:
                h = keys.pop()
                if h in seen: continue
                seen.add(h)
                body = strict_json(store.blob(h).decode('utf-8'))
                if body.get('previous_snapshot'): keys.append(body['previous_snapshot'])
                for item in body.get('notes', {}).values():
                    for evidence in item['evidence']: store.blob(evidence)
                for record in body.get('records', []):
                    for evidence in record.get('evidence_ids', []):
                        # Imported human MemTX records may use upstream external IDs.
                        if len(evidence) == 64: store.blob(evidence)
                keys.extend(r['hash'] for r in body.get('reports', []))
                for job in body.get('jobs', {}).values():
                    if job.get('receipt'): keys.append(job['receipt'])
                    for digest_value in job.get('outputs', {}).values(): store.blob(digest_value)
            if row['key'].startswith('long-project:') and fingerprint({k: v for k, v in value.items() if k != 'snapshot'}) != value['snapshot']:
                raise ResearchError('Project snapshot binding mismatch')
        except (ResearchError, OSError, ValueError, TypeError, KeyError): errors.append('long_reference:' + row['key'])
    return errors


def report(store, project):
    p = get(store, project)
    body = '# 长程科研项目报告\n\n目标：' + p['objective'] + '\n\n'
    body += '## 为什么与如何执行\n\n跨上下文维护研究目标、人工决定、证据状态与累计预算；等待实验时读取真实工作流回执。\n\n'
    body += '## 实现与进展\n\n```json\n' + canonical({'spent': p['spent'], 'remaining': remaining(p), 'sessions': p['sessions'], 'notes': p['notes'], 'jobs': p['jobs']}) + '\n```\n\n'
    body += '## 人的决定与待反馈事项\n\n' + canonical(p['decisions']) + '\n\n'
    body += '请审阅未决目标、证据适用条件、路线选择与预算；记录反馈后才视为实际决定。\n\n'
    body += '## 边界\n\n状态检查只覆盖已声明依赖；执行完成、模型预测和人工接受都不能独立证明科学结论。外部成本为保守预留，非提供方账单。\n'
    raw = body.encode('utf-8')
    atomic_bytes(store.root / 'projects' / valid_id(project) / 'report.md', raw)
    return body
