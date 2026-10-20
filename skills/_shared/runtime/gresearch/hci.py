"""Versioned stage reports and cooperative, explicit researcher decisions.

Reports are deterministic views of durable facts plus attributed explanations.
Actor names are audit labels, not authentication or scientific endorsement.
"""
import json
import time
import uuid

from .core import ResearchError, atomic_bytes, canonical, digest, fingerprint, safe_path
from .explanations import text

MODES = {'observe', 'checkpoints', 'every-stage'}
def reserved(path):
    # safe_path separately rejects absolute/escaping paths; normalize benign aliases here.
    import posixpath
    from pathlib import PurePosixPath
    return PurePosixPath(posixpath.normpath(path)).parts[0].lower() in {'_reports', '_capabilities'}


def validate_policy(manifest):
    policy = manifest.get('hci', {})
    if not isinstance(policy, dict) or set(policy) - {'mode', 'checkpoints', 'reviewers', 'require_explanation'}:
        raise ResearchError('Invalid HCI policy')
    if policy.get('mode', 'observe') not in MODES:
        raise ResearchError('hci.mode must be observe, checkpoints or every-stage')
    for key in ('checkpoints', 'reviewers'):
        if not isinstance(policy.get(key, []), list): raise ResearchError(key + ' must be a list')
        for value in policy.get(key, []): text(value, key)
    if not set(policy.get('checkpoints', [])).issubset(s['id'] for s in manifest['stages']):
        raise ResearchError('Unknown HCI checkpoint')
    if type(policy.get('require_explanation', False)) is not bool:
        raise ResearchError('require_explanation must be boolean')
    for spec in manifest['stages']:
        if spec.get('capability'):
            text(spec['capability'], 'capability')
            if spec.get('ssh'): raise ResearchError('Export capability bundles explicitly for SSH stages')
        for key in ('rationale', 'goal', 'instructions'):
            if key in spec: text(spec[key], key)
        for key in ('alternatives', 'review_questions'):
            if not isinstance(spec.get(key, []), list): raise ResearchError(key + ' must be a list')
            for value in spec.get(key, []): text(value, key)
        for name in spec.get('outputs', []) + spec.get('requires', []) + spec.get('optional', []):
            if reserved(name): raise ResearchError('Reserved runtime artifact directory')


def required(manifest, sid):
    policy = manifest.get('hci', {})
    return policy.get('mode') == 'every-stage' or (policy.get('mode') == 'checkpoints' and sid in policy.get('checkpoints', []))


def assessment(run, spec, item):
    return fingerprint({'run': run, 'spec': spec, 'cycle': item.get('cycle', 1),
                        'status': item['status'], 'outputs': item.get('outputs'),
                        'explanation': item.get('explanation'), 'capability_pin': item.get('capability_pin')})


def pending(state):
    return [sid for sid, item in state['stages'].items() if item['status'] == 'completed'
            and item.get('review', {}).get('required') and item['review'].get('status') != 'approved']


def report_body(store, run, manifest, state, spec, item):
    phase = item['status']
    if phase == 'pending' and state['status'] == 'cancelled': phase = 'cancelled_before_start'
    factual = {key: item[key] for key in ('exit_code', 'timeout', 'cancelled', 'error', 'failure', 'seconds',
               'cleanup_pending', 'logs', 'log_hashes', 'outputs', 'mutated_inputs', 'attempt_history', 'capability_pin', 'inherited_from') if key in item}
    explanation = json.loads(store.blob(item['explanation']['object'])) if item.get('explanation') else None
    return {'version': 1, 'run': run, 'stage': spec['id'], 'cycle': item.get('cycle', 1), 'phase': phase,
            'run_status': state['status'], 'blocker': state.get('blocker'),
            'objective': manifest['objective'], 'goal': spec.get('goal', spec.get('milestone', spec['id'])),
            'rationale': spec.get('rationale'), 'alternatives': spec.get('alternatives', []),
            'method': spec.get('instructions'), 'command': spec.get('command'), 'skill': spec.get('skill'),
            'inputs': {p: state['artifacts'].get(p) for p in spec.get('requires', []) + spec.get('optional', [])},
            'declared_outputs': spec['outputs'], 'facts': factual,
            'review': item.get('review', {'required': required(manifest, spec['id']), 'status': 'not_ready'}),
            'questions': spec.get('review_questions') or ['研究目标和方法是否合适？有哪些需要修正的前提？', '哪些结果还需要查原文、补实验或进一步解释？'],
            'explanation_request': item.get('explanation_request'), 'feedback_resolutions': item.get('feedback_resolutions', []),
            'feedback': item.get('feedback', []), 'explanation': explanation,
            'scope': 'Execution facts and attributed teaching content; approval is not scientific verification'}


def render(body):
    facts = body['facts']
    lines = [f"# 阶段报告：{body['stage']}", '', f"运行：{body['run']}；第 {body['cycle']} 次执行；状态：{body['phase']}", '',
             '运行状态：' + body['run_status'], '',
             '阻塞原因：' + (canonical(body['blocker']) if body['blocker'] else '无已记录的执行阻塞'), '',
             '## 目标与选择理由', '', body['objective'], '', '本阶段目标：' + body['goal'], '',
             body['rationale'] or '尚未记录方案选择理由；需要阶段负责人补充，不能从执行成功推断方法合理。', '', '备选方案与取舍：', '']
    lines += ['- ' + value for value in body['alternatives']] or ['- 尚未记录。']
    lines += ['', '## 如何执行', '', body['method'] or '执行方式见下方命令或宿主技能；具体方法说明尚未补充。', '',
              '技能：' + (body['skill'] or '显式命令'), '', '命令：`' + canonical(body['command']) + '`', '',
              '输入及哈希：', '', '```json', json.dumps(body['inputs'], ensure_ascii=False, indent=2), '```', '',
              '## 完成情况与可核对结果', '', '```json', json.dumps(facts, ensure_ascii=False, indent=2), '```', '',
              '成功退出只表示执行/产物检查通过。失败、超时、取消及未确认清理状态需结合原始日志解释。', '',
              '## 知识点、论断与论文讲解', '']
    if body['explanation']:
        from .explanations import markdown
        lines += [markdown(body['explanation']['bundle']), '', body['explanation']['grounding']]
    else:
        lines += ['尚未提交证据绑定的讲解。可请求更直观的例子、技术细节、原文依据或对当前研究的影响。']
    lines += ['', '## 请研究者判断', ''] + ['- ' + q for q in body['questions']]
    lines += ['', '审阅状态：' + body['review']['status'], '', '## 已收到的反馈及处理', '']
    for entry in body['feedback']:
        lines += ['- ' + entry['actor'] + ' / ' + entry['decision'] + '：' + entry['reason'],
                  '  - 处理：' + entry['effect'] + '；对应报告：' + entry['report_id']]
    if not body['feedback']: lines += ['尚未收到反馈；不代填研究者同意。']
    if body['explanation_request']: lines += ['', '待回应的讲解请求：' + body['explanation_request']]
    for resolution in body['feedback_resolutions']:
        lines += ['', '修改已形成分支：' + resolution['child'] + '；对应反馈：' + resolution['feedback_id'] + '。修改效果仍需重新验证。']
    lines += ['', '## 后续条件', '',
              '需要审阅的阶段须收到绑定当前版本的明确同意；修改请求保持暂停，使用分支重跑保留原始轨迹。',
              '可随时提出异议、要求解释或停止。科研结论仍需证据与领域审查。', '']
    return '\n'.join(lines)


def refresh(store, run, manifest, state):
    """Called inside the caller's write transaction, before Store.save commits."""
    for spec in manifest['stages']:
        item = state['stages'][spec['id']]
        key = assessment(run, spec, item)
        if item['status'] == 'completed' and item.get('review', {}).get('assessment') != key:
            item['review'] = {'assessment': key, 'required': required(manifest, spec['id']), 'status': 'pending' if required(manifest, spec['id']) else 'optional'}
    if state['status'] == 'ready' and (pending(state) or state.get('intervention_hold')):
        state['status'] = 'awaiting_review'
    for spec in manifest['stages']:
        item = state['stages'][spec['id']]
        body = report_body(store, run, manifest, state, spec, item)
        content_hash = fingerprint(body)
        if item.get('report', {}).get('content_hash') == content_hash: continue
        identity = 'report-' + uuid.uuid4().hex[:16]
        revision = len(item.get('report_history', [])) + 1
        directory = f"_reports/{spec['id']}/attempt-{item.get('cycle', 1):03d}/{revision:04d}-{identity}"
        data = {**body, 'id': identity, 'revision': revision, 'created': time.time()}
        raw, markdown = (canonical(data) + '\n').encode(), render(data).encode()
        receipt = {'id': identity, 'revision': revision, 'content_hash': content_hash, 'directory': directory,
                   'json': store.put(raw), 'markdown': store.put(markdown)}
        atomic_bytes(safe_path(store.work(run), directory + '/report.json'), raw)
        atomic_bytes(safe_path(store.work(run), directory + '/report.md'), markdown)
        item.setdefault('report_history', []).append(receipt)
        item['report'] = receipt
        store.event(run, 'stage_report', {'stage': spec['id'], **receipt})


def read(store, run, stage, report_id=None):
    _, state = store.get(run)
    if stage not in state['stages']: raise ResearchError('Unknown stage')
    item = state['stages'][stage]
    receipt = next((r for r in item.get('report_history', []) if r['id'] == report_id), None) if report_id else item.get('report')
    if not receipt: raise ResearchError('Unknown stage report')
    return {'receipt': receipt, 'report': json.loads(store.blob(receipt['json'])), 'markdown': store.blob(receipt['markdown']).decode()}


def feedback(store, run, stage, report_id, actor, decision, reason):
    text(actor, 'actor'); text(reason, 'reason')
    if decision not in {'approve', 'revise', 'stop', 'comment', 'explain'}:
        raise ResearchError('Unknown feedback decision')
    with store.tx():
        manifest, state = store.get(run)
        item = state['stages'].get(stage)
        if not item or item.get('report', {}).get('id') != report_id:
            raise ResearchError('Stale report: read the latest version before submitting feedback')
        reviewers = manifest.get('hci', {}).get('reviewers', [])
        if state['status'] == 'cancelled' and decision in {'approve', 'revise', 'stop'}:
            raise ResearchError('Cancelled runs are terminal; fork to revise')
        if state['status'] == 'completed' and decision == 'stop':
            raise ResearchError('Completed run cannot be cancelled')
        if decision in {'approve', 'revise', 'stop'} and reviewers and actor not in reviewers:
            raise ResearchError('Actor is not a declared researcher reviewer')
        if decision == 'approve':
            if state.get('worker') or state['status'] == 'cancelled' or item['status'] != 'completed':
                raise ResearchError('Only an idle completed stage can be approved')
            if item.get('cleanup_pending') or item.get('active_attempt'):
                raise ResearchError('Settle cleanup before approval')
            if manifest.get('hci', {}).get('require_explanation') and not item.get('explanation'):
                raise ResearchError('Submit an evidence-bound explanation before approval')
            # Recheck the current output bytes; an old report cannot bless changed data.
            spec = next(s for s in manifest['stages'] if s['id'] == stage)
            validate_inputs(store, run, spec, item)
            if store.output_hashes(run, spec) != item.get('outputs'):
                raise ResearchError('Outputs changed since the report; fork and rerun')
            if item.get('explanation'):
                from .explanations import validate
                validate(json.loads(store.blob(item['explanation']['object']))['bundle'], store.work(run), state['artifacts'])
            item['review']['status'] = 'approved'
            if state.get('intervention_hold', {}).get('stage') == stage:
                state.pop('intervention_hold')
            effect = '已接受当前报告版本；允许继续符合既有授权的后续阶段'
        elif decision == 'revise':
            item.setdefault('review', {})['status'] = 'changes_requested'
            state['intervention_hold'] = {'stage': stage, 'report_id': report_id}
            if state['status'] != 'completed':
                state['status'] = 'pause_requested' if state.get('worker') else 'paused'
            effect = '已暂停；修改需建立分支或修订阶段后重新执行和审阅'
        elif decision == 'stop':
            state['status'] = 'cancel_requested' if state.get('worker') else 'cancelled'
            effect = '已请求停止；清理状态以执行回执为准'
        elif decision == 'explain':
            item['explanation_request'] = reason
            effect = '已记录讲解请求；不视为接受或改变科学结论'
        else:
            effect = '已记录意见；尚未声明已落实修改，也不解除审阅门槛'
        entry = {'id': 'feedback-' + uuid.uuid4().hex[:16], 'report_id': report_id, 'actor': actor,
                 'decision': decision, 'reason': reason, 'effect': effect, 'time': time.time()}
        item.setdefault('feedback', []).append(entry)
        if decision == 'approve' and not pending(state) and not state.get('intervention_hold') and state['status'] in {'awaiting_review', 'paused', 'blocked'}:
            state['status'] = 'ready'
        store.event(run, 'researcher_feedback', {'stage': stage, **entry})
        store.save(run, state)
    return {'feedback': entry, 'status': state['status'], 'report': item['report']}


def explain(store, run, stage, report_id, actor, bundle):
    from .explanations import validate
    text(actor, 'actor')
    with store.tx():
        manifest, state = store.get(run)
        item = state['stages'].get(stage)
        if state.get('worker') or state['status'] == 'cancelled' or not item or item.get('report', {}).get('id') != report_id:
            raise ResearchError('Explanation requires an idle stage and its current report')
        checked = validate(bundle, store.work(run), state['artifacts'])
        checked.update(actor=actor, based_on_report=report_id)
        item['explanation'] = {'object': store.put(canonical(checked).encode()), 'actor': actor}
        item.pop('explanation_request', None)
        if item['status'] == 'completed' and required(manifest, stage): state['status'] = 'awaiting_review'
        store.event(run, 'explanation_submitted', {'stage': stage, **item['explanation']})
        store.save(run, state)
    return item['report']


def validate_inputs(store, run, spec, item):
    """Accept only the bytes that the stage actually saw, including optional absence."""
    expected = {p: item.get('checkpoint', {}).get(p) for p in spec.get('requires', []) + spec.get('optional', [])}
    pin = item.get('capability_pin')
    if pin:
        if store.files(safe_path(store.work(run), pin['directory'])) != pin['bundle']['files']:
            raise ResearchError('Pinned capability file set changed')
        expected.update({pin['directory'] + '/' + p: key for p, key in pin['bundle']['files'].items()})
    for name, key in expected.items():
        path = safe_path(store.work(run), name)
        observed = digest(path.read_bytes()) if path.is_file() else None
        if observed != key or (name in spec.get('requires', []) and observed is None):
            raise ResearchError('Stage input or pinned capability changed: ' + name)


def revise(store, run, stage, feedback_id, changes, child=None):
    _, state = store.get(run)
    item = state['stages'].get(stage, {})
    entry = next((f for f in item.get('feedback', []) if f['id'] == feedback_id and f['decision'] == 'revise'), None)
    if not entry: raise ResearchError('Revision must reference an actual researcher change request')
    if not isinstance(changes, dict) or not changes: raise ResearchError('Supply concrete stage changes for the branch')
    child_run = store.fork(run, stage, changes, child)
    with store.tx():
        _, state = store.get(run)
        resolution = {'feedback_id': feedback_id, 'child': child_run, 'changes': changes, 'time': time.time()}
        state['stages'][stage].setdefault('feedback_resolutions', []).append(resolution)
        store.event(run, 'feedback_revision_branch', {'stage': stage, **resolution})
        store.save(run, state)
    return {'child': child_run, 'feedback_id': feedback_id, 'parent_preserved': True}


def rebuild(store, run):
    """Restore report views from immutable CAS, never invent missing execution facts."""
    from .locking import resource_lock
    with resource_lock(store, 'run', run):
        _, state = store.get(run)
        count = 0
        for item in state['stages'].values():
            for receipt in item.get('report_history', []):
                for filename, key in (('report.md', 'markdown'), ('report.json', 'json')):
                    atomic_bytes(safe_path(store.work(run), receipt['directory'] + '/' + filename), store.blob(receipt[key]))
                count += 1
        return {'restored_reports': count}


def to_memory(store, run, stage, report_id, project, expected_revision, *, actor, reason):
    """Explicit local projection: reports/claims/feedback are nodes, provenance is edges."""
    from . import memory
    text(actor, 'actor'); text(reason, 'reason')
    if type(expected_revision) is not int or expected_revision < 0:
        raise ResearchError('Use an explicit nonnegative graph revision')
    selected = read(store, run, stage, report_id)
    if expected_revision:
        previous = memory.get(store, project)
        if previous['revision'] != expected_revision: raise ResearchError('Graph revision conflict')
        graph = previous['graph']
    else:
        graph = {'nodes': [], 'edges': []}
    nodes = {n['id']: n for n in graph['nodes']}
    edges = {e['id']: e for e in graph['edges']}
    changed = False

    def node(identity, kind, **fields):
        nonlocal changed
        value = {'id': identity, 'type': kind, **fields}
        if identity in nodes and nodes[identity] != value:
            raise ResearchError('Existing provenance node differs: ' + identity)
        if identity not in nodes: changed = True
        nodes[identity] = value
        return identity

    def edge(left, right, relation):
        nonlocal changed
        identity = 'hci-edge:' + fingerprint([left, right, relation])
        value = {'id': identity, 'from': left, 'to': right, 'relation': relation}
        if identity in edges and edges[identity] != value:
            raise ResearchError('Existing provenance edge differs')
        if identity not in edges: changed = True
        edges[identity] = value

    def report_node(record):
        body = record['report']
        return node('report:' + body['id'], 'stage_report', run=body['run'], stage=body['stage'],
                    sha256=record['receipt']['json'], text=record['markdown'], scientific_verification=False)

    body = selected['report']
    anchor = report_node(selected)
    for entry in body['feedback']:
        fid = node(entry['id'], 'researcher_feedback', **{k: v for k, v in entry.items() if k != 'id'})
        prior = report_node(read(store, run, stage, entry['report_id']))
        edge(fid, prior, 'responds_to')
        edge(anchor, fid, 'records_feedback')
    if body['explanation']:
        explanation = body['explanation']
        eid = node('explanation:' + fingerprint(explanation), 'research_explanation', **explanation)
        edge(anchor, eid, 'includes_explanation')
        for claim in explanation['bundle']['claims']:
            cid = node('claim:' + fingerprint([eid, claim['id']]), 'claim',
                       text=claim['text'], evidence_status=claim['status'], scientific_verification=False)
            edge(eid, cid, 'explains_claim')
            for citation in claim.get('citations', []):
                source = node('source:' + citation['sha256'], 'source', sha256=citation['sha256'])
                qid = node('citation:' + fingerprint(citation), 'source_span', **citation)
                edge(qid, source, 'span_of')
                edge(cid, qid, 'cites')  # Citation is not an entailment assertion.
    if not changed:
        return {'project': project, 'revision': expected_revision, 'unchanged': True}
    merged = {**graph, 'nodes': list(nodes.values()), 'edges': list(edges.values())}
    return memory.put(store, project, merged, expected_revision, actor=actor, reason=reason)
