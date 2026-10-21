"""Durability adapter for the copied, unchanged upstream MemTX code."""
from pathlib import Path
import copy
from datetime import datetime, timezone
import subprocess
import sys

from .core import ResearchError, canonical, fingerprint, valid_id
from .locking import resource_lock


def invoke(operation, arguments, snapshot=None, logical_date=None):
    payload = {'operation': operation, 'arguments': arguments, 'snapshot': snapshot, 'logical_date': logical_date}
    raw = canonical(payload).encode('utf-8')
    if len(raw) > 8_000_000: raise ResearchError('MemTX request exceeds 8 MB bound')
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(Path(__file__).with_name('memtx_worker.py'))],
                            input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    from .agent_protocol import strict_json
    value = strict_json(result.stdout.decode('utf-8'))
    if result.returncode or not value.get('ok'): raise ResearchError('MemTX: ' + value.get('error', 'worker failed'))
    return value


def get(store, project):
    value = store.get_value('memtx:' + valid_id(project))
    if not value: return {'revision': 0, 'snapshot': None, 'state': {}}
    from .agent_protocol import strict_json
    return {**value, 'state': strict_json(store.blob(value['snapshot']).decode('utf-8'))}


def transact(store, project, operation, arguments, *, expected_revision, actor, logical_date=None):
    if operation not in {'begin', 'stage', 'commit', 'abort', 'revoke', 'retrieve', 'gate', 'effect', 'view'}:
        raise ResearchError('Unsupported memory transaction')
    if not isinstance(actor, str) or not actor.strip(): raise ResearchError('MemTX actor required')
    with resource_lock(store, 'memtx', valid_id(project)):
        old = get(store, project)
        if type(expected_revision) is not int or old['revision'] != expected_revision: raise ResearchError('MemTX revision conflict')
        arguments = copy.deepcopy(arguments)
        if not isinstance(arguments, dict): raise ResearchError('MemTX arguments must be an object')
        if actor.startswith('agent:'):
            if operation not in {'begin', 'stage', 'commit', 'abort', 'retrieve', 'view'}:
                raise ResearchError('Agent may only write its own proposed transactions or read memory')
            if operation == 'begin': arguments.update(task_id=project, agent_id=actor)
            elif operation != 'view':
                transaction = next((t for t in old['state'].get('transactions', []) if t['tx_id'] == arguments.get('tx_id')), None)
                if not transaction or transaction['agent_id'] != actor: raise ResearchError('Transaction belongs to another actor')
            if operation in {'retrieve', 'view'}: arguments['requester'] = {'role': 'agent', 'permissions': []}
            if operation == 'stage':
                for record in arguments.get('extracted_memory', []):
                    if type(record.get('confidence')) not in {int, float} or not 0 <= record['confidence'] <= 1:
                        raise ResearchError('Supply explicit confidence in [0,1]; it is not scientific verification')
                    if not record.get('evidence_ids'): raise ResearchError('Agent memory needs actual evidence CAS references')
                    for h in record['evidence_ids']: store.blob(h)
                    record['source'] = {'type': 'agent', 'id': actor, 'authority': 0.0}
                    record['permission'] = {'owner': actor, 'read_roles': [], 'write_roles': ['agent'], 'share_scope': 'shared'}
        result = invoke(operation, arguments, old['state'], logical_date or old['state'].get('logical_date') or datetime.now(timezone.utc).date().isoformat())
        if operation in {'retrieve', 'view', 'gate'}:
            return {k: v for k, v in {**old, 'result': result['result'], 'upstream_commit': result['upstream_commit'],
                    'scientific_truth_proven': False}.items() if k != 'state'}
        result['snapshot']['previous_snapshot'] = old['snapshot']
        snapshot = store.put(canonical(result['snapshot']).encode('utf-8'))
        record = {'revision': old['revision'] + 1, 'snapshot': snapshot, 'previous': old['snapshot'],
                  'upstream_commit': result['upstream_commit']}
        with store.tx():
            store.set_value('memtx:' + project, record)
            store.event('memory:' + project, 'memtx_' + operation, {'actor': actor, **record, 'result': result['result']})
        return {**record, 'result': result['result'], 'scientific_truth_proven': False}


def gate(store, project, node_ids, tool):
    """Read-only simulation of upstream action gate over the pinned store."""
    current = get(store, project)
    started = invoke('begin', {'task_id': project, 'agent_id': 'action-gate', 'risk_level': 'external_action'}, current['state'],
                     logical_date=datetime.now(timezone.utc).date().isoformat())
    checked = invoke('gate', {'tx_id': started['result'], 'tool_name': tool, 'requires': node_ids}, started['snapshot'])
    return {**checked['result'], 'snapshot': current['snapshot'], 'upstream_commit': checked['upstream_commit']}
