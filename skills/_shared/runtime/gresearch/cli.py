"""Stable JSON-file command interface for hosts, humans and workflow stages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .core import ResearchError, Store, canonical, compare_runs, read_json, verify_archive, write_json


OPERATIONS = (
    'paired', 'adjust', 'meta', 'eprocess', 'data-audit', 'pdf', 'graph', 'writing-audit', 'novelty',
    'search', 'import', 'dedup', 'export', 'citation', 'zotero', 'monitor', 'notes', 'local-index', 'local-search', 'invalidate',
    'review-freeze', 'screen', 'adjudicate', 'review-report', 'quality', 'intervention',
    'rsi-freeze', 'rsi-evaluate', 'rsi-rollback', 'rsi-recover', 'rsi-export', 'rsi-compare', 'rsi-status',
    'enqueue', 'queue-next', 'queue-cancel', 'queue-status', 'proof', 'grant',
    'model', 'embeddings', 'semantic-review', 'semantic-graph', 'semantic-metrics', 's2-bulk', 'isolated-run',
    'signing-keygen', 'receipt-accept', 'representations', 'critic-fit', 'critic-predict', 'study-plan', 'study-analyze')


def operation(store, name, data):
    from . import statistics as st, evidence as ev, literature as lit, review as rv, evolution as rs, projects as pr, retrieval as rt
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
    if name == 'rsi-recover': return rs.recover_epoch(store, data['name'], data['reason'])
    if name == 'rsi-export': return rs.materialize(store, data['name'], data['destination'])
    if name == 'rsi-compare': return rs.epoch_comparison(store, data['left'], data['right'])
    if name == 'rsi-status': return store.get_value('rsi:' + data['name'])
    if name == 'enqueue': return pr.enqueue(store, data['run'], data.get('resources', {'cpu': 1, 'gpu': 0}), data.get('priority', 0))
    if name == 'queue-next': return pr.queue_next(store, data['capacity'])
    if name == 'queue-cancel': return pr.queue_cancel(store, data['job'])
    if name == 'queue-status': return store.get_value('queue', [])
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
    commands.add_parser('list')
    commands.add_parser('verify')
    p = commands.add_parser('verify-archive'); p.add_argument('path')
    p = commands.add_parser('import-archive'); p.add_argument('path'); p.add_argument('--id')
    p = commands.add_parser('control'); p.add_argument('run'); p.add_argument('action', choices=['pause', 'resume', 'step', 'cancel', 'breakpoint', 'retry']); p.add_argument('--stage'); p.add_argument('--reason', default='human control')
    p = commands.add_parser('annotate'); p.add_argument('run'); p.add_argument('target'); p.add_argument('text'); p.add_argument('--actor', default='human')
    p = commands.add_parser('finish'); p.add_argument('run'); p.add_argument('stage'); p.add_argument('--actor', default='host-agent')
    p = commands.add_parser('fork'); p.add_argument('run'); p.add_argument('stage'); p.add_argument('--patch'); p.add_argument('--id')
    p = commands.add_parser('compare'); p.add_argument('left'); p.add_argument('right')
    p = commands.add_parser('serve'); p.add_argument('--port', type=int, default=8765)
    p = commands.add_parser('tool', help='run a scientific helper using a structured JSON request'); p.add_argument('operation', choices=OPERATIONS); p.add_argument('request')
    args = parser.parse_args(argv)
    store = None
    try:
        store = Store(args.store)
        from .execution import recover, run_workflow
        if args.command == 'init':
            result = {'run': store.create(read_json(args.manifest), args.id, read_json(args.inputs) if args.inputs else {})}
        elif args.command == 'run': result = run_workflow(store, args.run)
        elif args.command == 'status':
            m, s = store.get(args.run); result = {'run': args.run, 'manifest': m, 'state': s, 'work': str(store.work(args.run))}
        elif args.command == 'events': result = store.events(args.run)
        elif args.command == 'archive': result = store.archive(args.run)
        elif args.command == 'recover': result = recover(store, args.run)
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
        if args.command in {'verify', 'verify-archive'} and not result['valid']: return 2
        return 0
    except (ResearchError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(canonical({'error': str(exc), 'type': type(exc).__name__}), file=sys.stderr)
        return 2
    finally:
        if store is not None: store.close()


if __name__ == '__main__':
    raise SystemExit(main())
