"""JSON boundary around the verbatim vendored MemTX implementation.

Separate process because upstream uses generic absolute imports (schema,
memory_manager, mock_tools). No upstream mock tool is executed by this bridge.
"""
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import sys


VENDOR = Path(__file__).resolve().parents[2] / 'vendor' / 'memtx'


def load():
    manifest = json.loads((VENDOR / 'UPSTREAM.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        if hashlib.sha256((VENDOR / item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Vendored MemTX changed without an explicit upstream pin update')
    sys.path.insert(0, str(VENDOR / 'src'))
    from memtx.memtx_manager import MemTXManager, Transaction
    from schema import MemoryRecord, IsolationLevel
    return MemTXManager, Transaction, MemoryRecord, IsolationLevel, manifest


def execute(request):
    Manager, Transaction, Record, Isolation, manifest = load()
    snapshot = request.get('snapshot') or {}
    manager = Manager(**snapshot.get('config', {}))
    records = []
    for item in snapshot.get('records', []):
        rec = Record.from_dict(item)
        rec.created_at = item['created_at']; rec.snapshot_id = item.get('snapshot_id')
        records.append(rec)
    manager.pre_load_memory(records)
    for item in snapshot.get('transactions', []):
        item = {**item, 'isolation': Isolation(item['isolation'])}
        manager._txns[item['tx_id']] = Transaction(**item)
    manager._revoked_ids.update(snapshot.get('revoked_ids', []))
    manager._verifier_calls = snapshot.get('verifier_calls', 0)
    manager.set_sim_now(request.get('logical_date') or snapshot.get('logical_date'))
    operation, args = request['operation'], request.get('arguments', {})
    methods = {'begin': 'begin_tx', 'stage': 'stage_write', 'commit': 'validate_and_commit',
               'abort': 'abort_or_rollback', 'revoke': 'abort_memory', 'retrieve': 'retrieve',
               'effect': 'record_tool_effect', 'view': 'current_belief_view'}
    if operation in methods:
        if operation == 'begin' and args.get('risk_level') not in {'low', 'medium', 'high', 'external_action'}:
            raise ValueError('Unknown MemTX risk level')
        if operation == 'stage':
            ids = [r['memory_id'] for r in args['extracted_memory']]
            if len(set(ids)) != len(ids) or any(i in manager._store for i in ids):
                raise ValueError('Use a fresh memory_id for every revision; do not overwrite upstream records')
            tx = manager._txns.get(args['tx_id'])
            if not tx or tx.status != 'open': raise ValueError('Transaction must be open')
            for item in args['extracted_memory']:
                validity = item.get('validity', item.get('validity_interval')) or {}
                for bound in ('valid_from', 'valid_until'):
                    if validity.get(bound) is not None and manager._parse_iso(validity[bound]) is None:
                        raise ValueError('Malformed validity date; do not silently treat it as unbounded')
        if operation == 'retrieve':
            top_k = args.get('top_k', 8)
            if type(top_k) is not int or not 1 <= top_k <= 1000: raise ValueError('Use top_k between 1 and 1000')
            result = manager.retrieve(**{**args, 'top_k': len(manager._store)})
            tx = manager._txns.get(args['tx_id'])
            result = [r for r in result if tx and r['memory_id'] in tx.snapshot_ids][:top_k]
        else: result = getattr(manager, methods[operation])(**args)
    elif operation == 'gate':
        # Register actual tool names as irreversible for this check. We use the
        # upstream gate, then require every actual premise, not an existential one.
        import mock_tools
        mock_tools.IRREVERSIBLE_TOOLS.add(args['tool_name'])
        result = manager.action_safe_check(args['tx_id'], args['tool_name'])
        tx = manager._txns.get(args['tx_id'])
        missing = [mid for mid in args['requires'] if not tx or mid not in tx.snapshot_ids
                   or mid not in manager._store or manager._store[mid].state.value != 'action_safe'
                   or mid in manager._revoked_ids or manager._dep_graph.has_pending_invalidation([mid], manager._revoked_ids)
                   or not manager._check_validity_interval(manager._store[mid])[0]]
        def stable(mid, visiting):
            if mid in visiting or mid not in manager._store: return False
            record = manager._store[mid]
            if record.state.value not in {'committed', 'action_safe'} or mid in manager._revoked_ids: return False
            return manager._check_validity_interval(record)[0] and all(stable(p, visiting | {mid}) for p in manager._dep_graph.parents(mid))
        missing.extend(mid for mid in args['requires'] if not stable(mid, set()))
        missing = sorted(set(missing))
        if not args['requires'] or missing: result = {'allow': False, 'reason': 'actual_premises_not_action_safe', 'missing': missing}
    elif operation == 'cascade_graph':
        graph, roots = args['graph'], set(args['sources'])
        by_id = {n['id']: n for n in graph['nodes']}
        # Scientific relation projection is application-specific; lifecycle and
        # typed cascade are executed by the original MemTX manager below.
        from schema import MemoryState
        ignored = {'related_to', 'same_topic', 'cites', 'motivates', 'supersedes'}
        unavailable = roots | {n['id'] for n in graph['nodes'] if n.get('status') in {'needs_review', 'stale', 'retracted', 'revoked', 'refuted', 'contested'}}
        edges = {identity: [e for e in graph['edges'] if e['to'] == identity and e['relation'] not in ignored] for identity in by_id}
        def viable_path(identity, visiting):
            if identity in unavailable or identity in visiting: return False
            node = by_id[identity]
            trail = visiting | {identity}
            groups = node.get('support_sets')
            required = [e['from'] for e in edges[identity] if not groups or e['relation'] != 'supports']
            return all(viable_path(p, trail) for p in required) and (not groups or any(all(viable_path(p, trail) for p in group) for group in groups))
        for node in graph['nodes']:
            parents = [e['from'] for e in graph['edges'] if e['to'] == node['id'] and e['relation'] not in ignored]
            groups = node.get('support_sets', [])
            viable = [g for g in groups if all(viable_path(p, {node['id']}) for p in g)]
            if viable:
                supporters = {e['from'] for e in graph['edges'] if e['to'] == node['id'] and e['relation'] == 'supports'}
                parents = sorted((set(parents) - supporters) | set(min(viable, key=lambda g: (len(g), sorted(g)))))
            kind = node.get('type')
            record = Record(memory_id=node['id'], entity=node['id'], attribute='research', value=node,
                            state=MemoryState.COMMITTED, derived_from=parents,
                            node_type=kind if kind in {'summary', 'profile', 'index_entry', 'shared_copy', 'tool_action'} else 'belief')
            manager.pre_load_memory([record])
        results = [manager.abort_memory(identity, args['reason']) for identity in sorted(roots)]
        result = {'affected': sorted({i for r in results for i in r.get('rolled_back_ids', [])}), 'receipts': results,
                  'compensation_log_only': True, 'external_effects_reversed': False}
    else: raise ValueError('Unsupported MemTX operation')
    state = {'config': snapshot.get('config', {}), 'records': [asdict(r) for r in manager._store.values()],
             'transactions': [asdict(t) for t in manager._txns.values()], 'revoked_ids': sorted(manager._revoked_ids),
             'verifier_calls': manager._verifier_calls, 'logical_date': manager._sim_now}
    return {'result': result, 'snapshot': state, 'upstream_commit': manifest['commit'], 'scientific_truth_proven': False,
            'compensation_log_only': True, 'external_effects_reversed': False}


if __name__ == '__main__':
    try:
        request = json.loads(sys.stdin.buffer.read().decode('utf-8'))
        result = execute(request)
        print(json.dumps({'ok': True, **result}, ensure_ascii=True, allow_nan=False))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc), 'type': type(exc).__name__}, ensure_ascii=True))
        raise SystemExit(2)
