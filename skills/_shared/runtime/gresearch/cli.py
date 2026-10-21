"""Stable JSON-file command interface for hosts, humans and workflow stages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import sqlite3

from .core import ResearchError, Store, canonical, compare_runs, read_json, verify_archive, write_json


OPERATIONS = (
    'paired', 'adjust', 'meta', 'eprocess', 'data-audit', 'pdf', 'graph', 'writing-audit', 'novelty',
    'search', 'import', 'dedup', 'export', 'citation', 'zotero', 'monitor', 'notes', 'local-index', 'local-search', 'invalidate',
    'review-freeze', 'screen', 'adjudicate', 'review-report', 'quality', 'intervention',
    'rsi-freeze', 'rsi-evaluate', 'rsi-rollback', 'rsi-recover', 'rsi-export', 'rsi-compare', 'rsi-status',
    'enqueue', 'queue-next', 'queue-cancel', 'queue-status', 'queue-recover', 'proof', 'grant',
    'environment-lock', 'environment-check', 'memory-put', 'memory-get', 'memory-search', 'memory-neighbors',
    'stage-report', 'stage-feedback', 'stage-explain', 'stage-revise', 'stage-memory', 'reports-rebuild',
    'capability-list', 'capability-freeze', 'capability-status', 'capability-propose', 'capability-evaluate',
    'capability-review', 'capability-activate', 'capability-rollback', 'capability-export', 'proposal-status',
    'memory-invalidate', 'memory-export', 'memory-import', 'memory-sync', 'memory-remote-search', 'memory-pull',
    'model', 'embeddings', 'semantic-review', 'semantic-graph', 'semantic-metrics', 's2-bulk', 'isolated-run',
    'signing-keygen', 'receipt-accept', 'representations', 'critic-fit', 'critic-predict', 'study-plan', 'study-analyze',
    'long-create', 'long-status', 'long-note', 'long-decide', 'long-review', 'long-track-job', 'long-tick', 'memtx')


def operation(store, name, data):
    from . import statistics as st, evidence as ev, literature as lit, review as rv, evolution as rs, projects as pr, retrieval as rt
    if name.startswith('long-'):
        from . import long_horizon as horizon
        if name == 'long-create': return horizon.create(store, **data)
        if name == 'long-status': return horizon.get(store, data['project'])
        if name == 'long-note': return horizon.note(store, **data)
        if name == 'long-decide': return horizon.decide(store, **data)
        if name == 'long-review': return horizon.review(store, **data)
        if name == 'long-track-job': return horizon.track_job(store, **data)
        if name == 'long-tick': return horizon.tick(store, data['project'])
    if name == 'memtx':
        from . import memtx
        if data['operation'] == 'status': return memtx.get(store, data['project'])
        return memtx.transact(store, **data)
    if name.startswith('stage-') or name == 'reports-rebuild':
        from . import hci
        if name == 'stage-report': return hci.read(store, data['run'], data['stage'], data.get('report_id'))
        if name == 'stage-feedback': return hci.feedback(store, **data)
        if name == 'stage-explain': return hci.explain(store, **data)
        if name == 'stage-revise': return hci.revise(store, **data)
        if name == 'stage-memory': return hci.to_memory(store, **data)
        return hci.rebuild(store, data['run'])
    if name.startswith('capability-') or name == 'proposal-status':
        from . import capabilities as cap
        if name == 'capability-list': return cap.catalog()
        if name == 'capability-freeze': return cap.freeze(store, **data)
        if name == 'capability-status': return cap.state(store, data['target'])
        if name == 'capability-propose': return cap.propose(store, **data)
        if name == 'capability-evaluate': return cap.evaluate(store, **data)
        if name == 'capability-review': return cap.review(store, **data)
        if name == 'capability-activate': return cap.activate(store, **data)
        if name == 'capability-rollback': return cap.rollback(store, **data)
        if name == 'capability-export': return cap.export(store, **data)
        return cap.proposal(store, data['identity'])
    if name.startswith('memory-'):
        from . import memory
        if name == 'memory-put': return memory.put(store, data['project'], data['graph'], data['expected_revision'], actor=data['actor'], reason=data['reason'])
        if name == 'memory-get': return memory.get(store, data['project'], data.get('revision'))
        if name == 'memory-neighbors': return memory.neighbors(store, data['project'], data['nodes'], **data.get('options', {}))
        if name == 'memory-search': return memory.search(store, data['project'], data['query'], **data.get('options', {}))
        if name == 'memory-invalidate': return memory.invalidate_sources(store, data['project'], data['source_ids'], data['expected_revision'], actor=data['actor'], reason=data['reason'])
        if name == 'memory-export': return memory.export(store, data['project'], data['destination'], data.get('revision'))
        if name == 'memory-import': return memory.import_snapshot(store, read_json(data['path']), data['project'], data['expected_revision'], actor=data['actor'], reason=data['reason'])
        if name == 'memory-sync': return memory.sync(store, data['project'], data['config'], data.get('revision'))
        if name == 'memory-remote-search': return memory.remote_search(store, data['project'], data['config'], data['query'], data.get('limit', 10), data.get('revision'))
        if name == 'memory-pull':
            from .openviking import Client
            snapshot = Client(data['config']).load(data['source_project'], data['snapshot'])
            return memory.import_snapshot(store, snapshot, data['project'], data['expected_revision'], actor=data['actor'], reason=data['reason'])
    if name in {'environment-lock', 'environment-check'}:
        from .reproducibility import capture, compare
        lock = data.get('lock')
        observed = capture(data['root'], lock['packages'] if lock else data.get('packages'), lock['files'] if lock else data.get('files', []))
        return observed if name == 'environment-lock' else compare(lock, observed)
    if name in {'study-plan','study-analyze'}:
        from . import study
        return study.initialize(data['destination'],data.get('participants',12),data.get('seed',20261019)) if name=='study-plan' else study.analyze(data['protocol'],data['observations'])
    if name in {'model','embeddings'}:
        from . import models
        return models.generate(data['config'],data['messages'],data['destination']) if name=='model' else models.embeddings(data['config'],data['texts'],data['destination'])
    if name in {'semantic-review','semantic-metrics'}:
        from . import semantic
        return semantic.review(data['config'],data['items'],data['destination'],threshold=data.get('threshold',.9)) if name=='semantic-review' else semantic.metrics(data['rows'])
    if name=='semantic-graph':
        from .semantic import review_graph
        return review_graph(data['config'],data['graph'],data['root'],data['destination'],threshold=data.get('threshold',.9))
    if name=='s2-bulk':return lit.semantic_scholar_bulk(data['query'],data['destination'],data.get('max_records',100))
    if name=='isolated-run':
        from .isolation import run
        return run(data['isolation'],data['code'],data['task'],data['command'],data['destination'],seed=data.get('seed',0),timeout=data.get('timeout',60))
    if name in {'signing-keygen','receipt-accept'}:
        from . import attestation
        return attestation.keygen(data['destination']) if name=='signing-keygen' else attestation.accept(store,data['receipt'],data['public_key'],data['expected'])
    if name in {'representations','critic-fit','critic-predict'}:
        from . import representations as rep
        if name=='representations':return rep.encode(data['config'],data['texts'])
        if name=='critic-fit':return rep.train_critic(data)
        return rep.predict_critic(data['model'],data['vectors'],data['encoder_hash'])
    if name == 'paired': return st.paired_analysis(data['rows'], **data.get('options', {}))
    if name == 'adjust': return st.adjust_pvalues(data['pvalues'], data.get('method', 'holm'))
    if name == 'meta': return st.meta_analysis(data)
    if name == 'eprocess': return st.sequential_evidence(data)
    if name == 'data-audit': return st.data_audit(data)
    if name == 'pdf': return ev.ingest_pdf(data['source'], data['destination'])
    if name == 'graph': return ev.validate_graph(data['graph'], data['root'])
    if name == 'writing-audit': return ev.audit_writing(Path(data['document']).read_text(encoding='utf-8'), data['ledger'])
    if name == 'novelty': return ev.novelty_matrix(data)
    if name == 'search': return lit.search(data['provider'], data['query'], data['destination'], pages=data.get('pages', 1), page_size=data.get('page_size', 25), cache_seconds=data.get('cache_seconds', 3600))
    if name == 'import': return lit.import_references(data['path'], data.get('format'))
    if name == 'dedup': return lit.deduplicate(data['records'])
    if name == 'export': return lit.export_references(data['records'], data['path'], data.get('format', 'csl'))
    if name == 'citation': return lit.citation_check(data['doi'], data['destination'])
    if name == 'zotero': return lit.zotero_read(data['library_type'], data['library_id'], data['destination'], data.get('max_pages', 10))
    if name == 'monitor': return lit.monitor(store, data['name'], data['records'])
    if name == 'notes': return lit.export_notes(data['records'], data['destination'])
    if name == 'local-index': return rt.build_index(data)
    if name == 'local-search': return rt.query_index(read_json(data['index']), data['query'], **data.get('options', {}))
    if name == 'invalidate': return rt.invalidate(data['graph'], data['source_ids'], data['reason'])
    if name == 'review-freeze': return rv.freeze_review(store, data['name'], data['protocol'])
    if name == 'screen': return rv.screen(store, data['name'], data['decisions'])
    if name == 'adjudicate': return rv.adjudicate(store, data['name'], data['decisions'])
    if name == 'review-report': return rv.review_report(store, data['name'], data['inventory'])
    if name == 'quality': return rv.assess_quality(data)
    if name == 'intervention': return rv.intervention_assessment(data)
    if name == 'rsi-freeze': return rs.freeze(store, data['name'], data['protocol'], data['evaluator_dir'], data['incumbent_dir'], data['incumbent_command'])
    if name == 'rsi-evaluate': return rs.evaluate(store, data['name'], data['candidate_dir'], data['candidate_command'], split=data.get('split', 'audit'), promote=data.get('promote', False))
    if name == 'rsi-rollback': return rs.rollback(store, data['name'], data['index'], data['reason'])
    if name == 'rsi-recover': return rs.recover_epoch(store, data['name'], data['reason'], data.get('reconciliation'))
    if name == 'rsi-export': return rs.materialize(store, data['name'], data['destination'])
    if name == 'rsi-compare': return rs.epoch_comparison(store, data['left'], data['right'])
    if name == 'rsi-status': return store.get_value('rsi:' + data['name'])
    if name == 'enqueue': return pr.enqueue(store, data['run'], data.get('resources', {'cpu': 1, 'gpu': 0}), data.get('priority', 0))
    if name == 'queue-next': return pr.queue_next(store, data['capacity'])
    if name == 'queue-cancel': return pr.queue_cancel(store, data['job'])
    if name == 'queue-status': return store.get_value('queue', [])
    if name == 'queue-recover': return pr.queue_recover(store, data['job'], data.get('reconciliation'))
    if name == 'proof': return pr.proof_check(data, data['destination'])
    if name == 'grant': return pr.grant_plan(data)
    raise ResearchError('Unknown operation')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Evidence-based research runtime. Trusted local commands; optional explicit Docker candidate isolation.')
    parser.add_argument('--store', default='.research-v2', help='durable research state directory')
    parser.add_argument('--output', help='also write JSON result to a file')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='create run from explicit DAG manifest')
    init.add_argument('manifest'); init.add_argument('--inputs', help='JSON mapping workspace paths to source paths'); init.add_argument('--id')
    for name in ('run', 'status', 'events', 'archive', 'recover'):
        p = commands.add_parser(name); p.add_argument('run')
        if name == 'recover': p.add_argument('--reconciliation', help='JSON operator record for uncertain effects: actor, reason, effects_checked')
    commands.add_parser('list')
    commands.add_parser('verify')
    commands.add_parser('doctor')
    p = commands.add_parser('backup'); p.add_argument('destination')
    p = commands.add_parser('verify-backup'); p.add_argument('path')
    p = commands.add_parser('restore-backup'); p.add_argument('path'); p.add_argument('destination')
    p = commands.add_parser('verify-archive'); p.add_argument('path')
    p = commands.add_parser('import-archive'); p.add_argument('path'); p.add_argument('--id')
    p = commands.add_parser('control'); p.add_argument('run'); p.add_argument('action', choices=['pause', 'resume', 'step', 'cancel', 'breakpoint', 'retry']); p.add_argument('--stage'); p.add_argument('--reason', default='human control')
    p = commands.add_parser('annotate'); p.add_argument('run'); p.add_argument('target'); p.add_argument('text'); p.add_argument('--actor', default='human')
    p = commands.add_parser('finish'); p.add_argument('run'); p.add_argument('stage'); p.add_argument('--actor', default='host-agent')
    p = commands.add_parser('fork'); p.add_argument('run'); p.add_argument('stage'); p.add_argument('--patch'); p.add_argument('--id')
    p = commands.add_parser('compare'); p.add_argument('left'); p.add_argument('right')
    p = commands.add_parser('serve'); p.add_argument('--port', type=int, default=8765)
    p = commands.add_parser('agent-create', help='create a full-capability native-tool Agent session'); p.add_argument('request')
    commands.add_parser('agent-list')
    p = commands.add_parser('long-watch', help='observe actual DAG receipts without model polling')
    p.add_argument('project'); p.add_argument('--seconds', type=float, default=60)
    p.add_argument('--interval', type=float, default=1); p.add_argument('--resume', action='store_true')
    for name in ('agent-run', 'agent-status', 'agent-events'):
        p = commands.add_parser(name); p.add_argument('session')
    p = commands.add_parser('agent-control'); p.add_argument('session'); p.add_argument('action', choices=['pause', 'resume', 'cancel']); p.add_argument('--reason', default='human intervention')
    p = commands.add_parser('agent-feedback'); p.add_argument('session'); p.add_argument('request')
    p = commands.add_parser('agent-steer'); p.add_argument('session'); p.add_argument('text'); p.add_argument('--actor', default='researcher')
    p = commands.add_parser('agent-fork'); p.add_argument('session'); p.add_argument('request', help='new identity/objective/config/budget/policy JSON; original retained')
    p = commands.add_parser('agent-recover'); p.add_argument('session'); p.add_argument('--reconciliation')
    p = commands.add_parser('tool', help='run a scientific helper using a structured JSON request'); p.add_argument('operation', choices=OPERATIONS); p.add_argument('request')
    args = parser.parse_args(argv)
    store = None
    try:
        store = Store(args.store)
        from .execution import recover, run_workflow
        if args.command.startswith('agent-'):
            from . import agent
            if args.command == 'agent-create': result = agent.create(store, **read_json(args.request))
            elif args.command == 'agent-list': result = agent.list_sessions(store)
            elif args.command == 'agent-run': result = agent.run(store, args.session)
            elif args.command == 'agent-status': result = agent.inspect(store, args.session)
            elif args.command == 'agent-events': result = store.events('agent:' + args.session)
            elif args.command == 'agent-control': result = agent.control(store, args.session, args.action, reason=args.reason)
            elif args.command == 'agent-feedback': result = agent.feedback(store, args.session, **read_json(args.request))
            elif args.command == 'agent-steer': result = agent.steer(store, args.session, args.text, actor=args.actor)
            elif args.command == 'agent-fork': result = agent.fork(store, args.session, **read_json(args.request))
            else: result = agent.recover(store, args.session, read_json(args.reconciliation) if args.reconciliation else None)
        elif args.command == 'long-watch':
            from .long_horizon import watch
            result = watch(store, args.project, seconds=args.seconds, interval=args.interval, resume=args.resume)
        elif args.command == 'init':
            result = {'run': store.create(read_json(args.manifest), args.id, read_json(args.inputs) if args.inputs else {})}
        elif args.command == 'run': result = run_workflow(store, args.run)
        elif args.command == 'status':
            m, s = store.get(args.run); result = {'run': args.run, 'manifest': m, 'state': s, 'work': str(store.work(args.run))}
        elif args.command == 'events': result = store.events(args.run)
        elif args.command == 'archive': result = store.archive(args.run)
        elif args.command == 'recover': result = recover(store, args.run, read_json(args.reconciliation) if args.reconciliation else None)
        elif args.command in {'doctor', 'backup', 'verify-backup', 'restore-backup'}:
            from . import maintenance
            if args.command == 'doctor': result = maintenance.health(store)
            elif args.command == 'backup': result = maintenance.backup(store, args.destination)
            elif args.command == 'verify-backup': result = maintenance.verify_backup(args.path)
            else: result = maintenance.restore_backup(args.path, args.destination)
        elif args.command == 'list': result = [{'run': r['id'], 'state': json.loads(r['state'])} for r in store.db.execute('SELECT id,state FROM runs ORDER BY rowid')]
        elif args.command == 'verify': result = store.verify()
        elif args.command == 'verify-archive': result = verify_archive(args.path)
        elif args.command == 'import-archive': result = {'run': store.import_archive(args.path, args.id)}
        elif args.command == 'control': result = store.control(args.run, args.action, args.reason, args.stage)
        elif args.command == 'annotate': result = store.annotate(args.run, args.target, args.text, args.actor)
        elif args.command == 'finish': result = store.finish(args.run, args.stage, args.actor)
        elif args.command == 'fork': result = {'run': store.fork(args.run, args.stage, read_json(args.patch) if args.patch else {}, args.id)}
        elif args.command == 'compare': result = compare_runs(store, args.left, args.right)
        elif args.command == 'tool': result = operation(store, args.operation, read_json(args.request))
        else:
            from .console import serve
            store.close(); store = None
            serve(args.store, args.port)
            return 0
        if args.output: write_json(args.output, result)
        print(canonical(result))
        # A valid computation with a negative scientific result is still a successful command.
        # Workflow execution failure and integrity/audit failures have distinct nonzero exit status.
        if args.command == 'run' and result.get('status') != 'completed': return 3
        if args.command == 'agent-run' and result.get('status') != 'completed': return 3
        if args.command in {'verify', 'verify-archive', 'verify-backup'} and not result['valid']: return 2
        if args.command == 'doctor' and not result['integrity']['valid']: return 2
        if args.command == 'tool' and args.operation == 'memory-sync' and result['status'] != 'synced': return 3
        return 0
    except (ResearchError, OSError, KeyError, TypeError, json.JSONDecodeError, sqlite3.Error) as exc:
        print(canonical({'error': str(exc), 'type': type(exc).__name__}), file=sys.stderr)
        return 2
    finally:
        if store is not None: store.close()


if __name__ == '__main__':
    raise SystemExit(main())
