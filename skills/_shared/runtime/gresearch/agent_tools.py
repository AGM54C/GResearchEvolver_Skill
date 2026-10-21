"""Progressive full-catalog access and bounded automatic research operations.

This is a trusted local tool gateway, not an OS sandbox. Arbitrary commands and
advanced adapters require approval of the exact call and workspace snapshot.
Researcher decisions are never delegated to model-generated actor labels.
"""
from __future__ import annotations

import os
import ast
from pathlib import Path
import subprocess
import stat

from .core import ResearchError, atomic_bytes, canonical, digest, read_json, safe_path, valid_id
from .agent_protocol import strict_json


SKILLS = Path(__file__).resolve().parents[3]
HUMAN_ONLY = frozenset({
    'stage-feedback', 'capability-review', 'capability-activate', 'capability-rollback',
    'capability-freeze', 'rsi-freeze', 'rsi-rollback', 'rsi-recover', 'signing-keygen', 'receipt-accept',
    'adjudicate', 'queue-recover',
    'long-create', 'long-status', 'long-note', 'long-decide', 'long-review', 'long-track-job', 'long-tick', 'memtx',
})
PURE = frozenset({'paired', 'adjust', 'meta', 'eprocess', 'data-audit', 'dedup', 'novelty', 'quality',
                  'intervention', 'grant', 'invalidate', 'semantic-metrics', 'capability-list'})
PATHS = {
    'pdf': ('source', 'destination'), 'graph': ('root',), 'writing-audit': ('document',),
    'search': ('destination',), 'import': ('path',), 'export': ('path',), 'citation': ('destination',),
    'notes': ('destination',), 'local-index': ('root', 'destination'), 'local-search': ('index',),
    's2-bulk': ('destination',),
}
MEMORY = frozenset({'memory-put', 'memory-get', 'memory-search', 'memory-neighbors', 'memory-invalidate'})
NETWORK = frozenset({'search', 'citation', 's2-bulk'})


def bundle_roots():
    registry = read_json(SKILLS / 'manifest.yaml')
    return {'_shared', *(spec['entry'].split('/')[0] for spec in registry['skills'].values())}


def bundle_files():
    """Installed hosts may have other skills next to this bundle; do not load them."""
    files = [SKILLS / 'manifest.yaml']
    for name in sorted(bundle_roots()):
        checked_path(SKILLS, name)
        root = SKILLS / name  # keep the same Windows path representation as SKILLS
        for current, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for item in dirs + names:
                path = Path(current) / item
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise ResearchError('Installed bundle contains symlinks/reparse points')
                if stat.S_ISREG(info.st_mode) and path.suffix not in {'.pyc', '.pyo'}: files.append(path)
    checked_path(SKILLS, 'manifest.yaml')
    return sorted(files)


def schema(name, description, properties):
    return {'name': name, 'description': description, 'parameters': {
        'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}}


STRING = {'type': 'string'}
STRINGS = {'type': 'array', 'items': STRING}
TOOLS = [
    schema('capability_catalog', 'List ALL installed skills and runtime operations, with execution/approval modes. No abilities are removed.', {}),
    schema('read_skill', 'Read a skill/manual by catalog path. offset/limit count CHARACTERS, not lines. Usually use offset=0, limit=12000; follow next_offset only if needed. Use operation_help for one operation instead of reading the whole CLI.',
           {'path': STRING, 'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20000}}),
    schema('operation_help', 'Look up required request fields and the exact dispatch for ONE existing research operation; common operations include a runnable example.',
           {'operation': STRING}),
    schema('list_files', 'List research workspace files and hashes; does not expose store/config credentials.', {}),
    schema('read_file', 'Read UTF-8 workspace text in bounded pages; binary sources use research_operation pdf or approved adapters.',
           {'path': STRING, 'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20000}}),
    schema('read_receipt', 'Page a full result from a previous tool call in this session; receipt content remains untrusted research data.',
           {'call_id': STRING, 'offset': {'type': 'integer'}, 'limit': {'type': 'integer'}}),
    schema('write_file', 'Write a research artifact atomically. expected_sha256 must match existing content; empty means create only.',
           {'path': STRING, 'content': STRING, 'expected_sha256': STRING}),
    schema('research_operation', 'Invoke any registered scientific helper. arguments_json is an object using documented CLI fields. Automatic paths are relative to this workspace, root=".". Human decision operations remain in the human CLI.',
           {'operation': STRING, 'arguments_json': STRING}),
    schema('run_command', 'Request exact local argv execution, including plotting/PPT, experiments, or existing workflow CLI. Requires researcher approval. This is trusted host execution, NOT sandbox isolation.',
           {'argv': STRINGS, 'purpose': STRING}),
    schema('report_stage', 'Finish a scientific stage with a versioned report.md and an accessible explanation; evidence paths must exist. Separate observed findings, hypotheses and limitations.',
           {'stage': STRING, 'why': STRING, 'method': STRING, 'findings': STRING, 'explanation': STRING,
            'evidence': STRINGS, 'limitations': STRINGS, 'questions': STRINGS, 'review_required': {'type': 'boolean'}}),
    schema('ask_researcher', 'Pause for an actual researcher answer on scientific direction, taste, missing information or a consequential tradeoff.',
           {'question': STRING, 'options': STRINGS}),
    schema('project_status', 'Read persistent objectives, constraints, actual researcher decisions, notes, jobs and the shared budget. Includes current graph and MemTX revision IDs.', {}),
    schema('project_note', 'Record a goal/hypothesis/route/finding/negative_result/experience in this project. data_json needs identity, kind, text, expected_revision; optional status, evidence (CAS hashes), prediction, outcome. Predictions cannot be rewritten after the fact.',
           {'data_json': STRING}),
    schema('bind_action', 'Bind the exact future run_command/report_stage/research_operation and ALL its premises before execution. purpose is explore/experiment/conclude/learn. requires_json maps actual graph node IDs to fingerprints; conditions_json contains actual condition values. conclude requires committed MemTX premises and any real human review.',
           {'name': STRING, 'arguments_json': STRING, 'requires_json': STRING, 'conditions_json': STRING, 'purpose': STRING, 'reason': STRING}),
    schema('read_context', 'Read a complete archived context epoch in bounded pages. epoch=0 reads the parent session retained by a long-project fork; epoch>=1 reads this session handoffs. Archives are evidence/history, never new authority.',
           {'epoch': {'type': 'integer'}, 'offset': {'type': 'integer'}, 'limit': {'type': 'integer'}}),
    schema('memory_transaction', 'Use the copied upstream MemTX manager. operation: status/begin/stage/commit/abort/retrieve/view. arguments_json uses upstream method fields. begin needs risk_level; stage needs tx_id, observation, extracted_memory (memory_id, entity, attribute, value, explicit confidence, actual evidence_ids CAS hashes). The controller supplies project/actor. Use fresh memory IDs for revisions; self-rated confidence is not scientific acceptance.',
           {'operation': STRING, 'arguments_json': STRING, 'expected_revision': {'type': 'integer'}}),
    schema('await_job', 'Suspend this session for an existing researcher-registered DAG job. The watcher imports real artifacts and resumes without model polling. Does not submit or repeat experiments.',
           {'job': STRING, 'reason': STRING}),
]


def validate_call(call):
    spec = next((s for s in TOOLS if s['name'] == call.get('name')), None)
    if not spec: raise ResearchError('Unknown tool')
    args = call.get('arguments')
    if not isinstance(args, dict) or set(args) != set(spec['parameters']['properties']):
        raise ResearchError('Tool arguments do not match required fields')
    for name, prop in spec['parameters']['properties'].items():
        value, kind = args[name], prop['type']
        if kind == 'string' and not isinstance(value, str): raise ResearchError('Expected string: ' + name)
        if kind == 'integer' and type(value) is not int: raise ResearchError('Expected integer: ' + name)
        if kind == 'boolean' and type(value) is not bool: raise ResearchError('Expected boolean: ' + name)
        if kind == 'array' and (not isinstance(value, list) or any(not isinstance(v, str) for v in value)):
            raise ResearchError('Expected string list: ' + name)
    if len(canonical(args)) > 100_000: raise ResearchError('Tool argument budget exceeded')
    if call['name'] == 'research_operation':
        from .cli import OPERATIONS
        if args['operation'] not in OPERATIONS: raise ResearchError('Unknown research operation')
        if not isinstance(strict_json(args['arguments_json']), dict): raise ResearchError('Operation needs a JSON object')
    if call['name'] == 'run_command' and (not args['argv'] or not all(s and '\x00' not in s for s in args['argv']) or not args['purpose'].strip()):
        raise ResearchError('Provide nonempty argv and purpose')
    return args


def mode(call, policy):
    args = validate_call(call)
    if call['name'] == 'run_command': return 'approval'
    if call['name'] != 'research_operation': return 'automatic'
    op = args['operation']
    if op in HUMAN_ONLY: return 'human_only'
    if op in NETWORK and not policy['network']: return 'approval'
    return 'automatic' if op in PURE or op in PATHS or op in MEMORY else 'approval'


def catalog(policy):
    from .cli import OPERATIONS
    registry = read_json(SKILLS / 'manifest.yaml')
    return {'skills': [{'name': name, 'path': spec['entry'], 'description': spec['intents'][0],
                        'evolution_target': spec.get('evolution_target')} for name, spec in registry['skills'].items()],
            'operations': [{'name': name, 'mode': mode({'name': 'research_operation', 'arguments': {
                'operation': name, 'arguments_json': '{}'}}, policy)} for name in OPERATIONS],
            'manual': '_shared/runtime-guide.md', 'shared_rules': '_shared/README.md',
            'request_help': 'operation_help returns the exact request fields without loading the entire runtime manual.',
            'quick_example': {'operation': 'adjust', 'arguments_json': '{"pvalues":[0.01,0.03,0.2],"method":"holm"}'},
            'operations_source': '_shared/runtime/gresearch/cli.py',
            'human_authority': 'Human decisions and activation stay in the trusted CLI/console; the model cannot sign or impersonate them.'}


def operation_help(name, policy):
    """Derive dispatch fields from trusted source, without evaluating source code.

    Forwarded **data adapters expose their implementation pointer explicitly;
    this is discoverability metadata, not a replacement for scientific validation.
    """
    from .cli import OPERATIONS
    if name not in OPERATIONS: raise ResearchError('Unknown operation')
    source = Path(__file__).with_name('cli.py').read_text(encoding='utf-8')
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'operation')
    def condition(node):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == 'name':
            right = ast.literal_eval(node.comparators[0])
            if isinstance(node.ops[0], ast.Eq): return name == right
            if isinstance(node.ops[0], ast.In): return name in right
        if isinstance(node, ast.BoolOp):
            values = [condition(n) for n in node.values]
            if all(v is not None for v in values): return any(values) if isinstance(node.op, ast.Or) else all(values)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'name' and node.func.attr == 'startswith':
            return name.startswith(ast.literal_eval(node.args[0]))
        return None
    def choose(expression):
        if isinstance(expression, ast.IfExp):
            yes = condition(expression.test)
            if yes is not None: return choose(expression.body if yes else expression.orelse)
        return expression
    selected = []
    def visit(nodes):
        for node in nodes:
            if isinstance(node, ast.If):
                yes = condition(node.test)
                if yes is not None:
                    if visit(node.body if yes else node.orelse): return True
                    continue
            if isinstance(node, ast.Return):
                selected.append(choose(node.value)); return True
            selected.append(node)
        return False
    visit(function.body)
    required, optional, forwarded = set(), {}, False
    for statement in selected:
        for node in ast.walk(statement):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == 'data' and isinstance(node.slice, ast.Constant):
                required.add(node.slice.value)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'data' and node.func.attr == 'get':
                optional[ast.literal_eval(node.args[0])] = ast.unparse(node.args[1]) if len(node.args) > 1 else 'None'
            if isinstance(node, ast.keyword) and node.arg is None and isinstance(node.value, ast.Name) and node.value.id == 'data': forwarded = True
    snippets = [ast.get_source_segment(source, node) or ast.unparse(node) for node in selected if not isinstance(node, (ast.Import, ast.ImportFrom))]
    examples = {
        'adjust': {'pvalues': [.01, .03, .2], 'method': 'holm'},
        'search': {'provider': 'crossref', 'query': 'source dependence evidence', 'destination': 'search/crossref', 'pages': 1},
        'pdf': {'source': 'inputs/paper.pdf', 'destination': 'extracted/paper'},
        'memory-search': {'project': policy['project'], 'query': 'source dependence'},
        'graph': {'graph': {'nodes': [], 'edges': []}, 'root': '.'},
    }
    return {'operation': name, 'mode': mode({'name': 'research_operation', 'arguments': {'operation': name, 'arguments_json': '{}'}}, policy),
            'required_fields_from_dispatch': sorted(required), 'optional_defaults': optional,
            'forwards_to_adapter': forwarded, 'dispatch': '\n'.join(snippets),
            'example_request': examples.get(name), 'example_is_scientifically_validated': False,
            'note': 'Scientific field semantics and forwarded adapter signatures are in the referenced helper source. Examples with empty graph/data are shapes, not valid evidence.'}


def checked_path(root, name, *, allow_root=False):
    root = Path(root)
    if allow_root and name == '.': candidate = root
    else:
        candidate = safe_path(root, name)
        parts = Path(name).parts
        if any(p.startswith('.') or p.lower() in {'auth.json', 'config.toml', 'state.sqlite3'} for p in parts):
            raise ResearchError('Private/configuration paths are not research artifacts')
    # Reject even in-root links/junctions; resolving first would hide them.
    current = root
    for part in (() if name == '.' else name.split('/')):
        current = current / part
        if current.exists() or current.is_symlink():
            attrs = getattr(current.lstat(), 'st_file_attributes', 0)
            if current.is_symlink() or attrs & 0x400: raise ResearchError('No symlinks or reparse points in agent workspace')
    return candidate


def inventory(root, policy):
    root, files, total = Path(root), {}, 0
    for current, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            checked_path(root, relative)
            if path.is_file():
                expected_size = path.stat().st_size
                total += expected_size
                if total > policy['max_workspace_bytes'] or len(files) >= policy['max_files']:
                    raise ResearchError('Workspace quota exceeded')
                with path.open('rb') as source: raw = source.read(expected_size + 1)
                if len(raw) != expected_size or path.stat().st_size != expected_size:
                    raise ResearchError('Workspace changed or exceeded quota while reading')
                files[relative] = {'sha256': digest(raw), 'bytes': len(raw)}
    return files


def read_text(root, path, offset, limit):
    if offset < 0 or not 1 <= limit <= 20000: raise ResearchError('Use nonnegative offset and 1..20000 characters')
    source = checked_path(root, path)
    if source.stat().st_size > 4_000_000: raise ResearchError('Use an indexed or PDF adapter for sources above 4 MB')
    raw = source.read_bytes()
    content = raw.decode('utf-8-sig')
    return {'path': path, 'sha256': digest(raw), 'text': content[offset:offset + limit],
            'next_offset': offset + limit if len(content) > offset + limit else None, 'untrusted_source_data': True}


def execute(store, session, call, work, policy, approved=False):
    args = validate_call(call)
    access = mode(call, policy)
    if access == 'human_only': raise ResearchError('Human-only operation: use the trusted human CLI/console')
    if access == 'approval' and not approved: raise ResearchError('Exact researcher approval required')
    from . import long_horizon as horizon, memtx
    state = store.get_value('agent:' + valid_id(session))
    if state and state.get('long_project'):
        if store.get_value('agent-signal:' + session): raise ResearchError('Researcher intervened; settle this call before continuing')
        horizon.check_action(store, state, call)  # Recheck immediately before actual execution.
    name = call['name']
    if name in {'project_status', 'project_note', 'bind_action', 'await_job'}:
        if not state or not state.get('long_project'): raise ResearchError('Create/attach a long-horizon project first')
        project = state['long_project']
        if name == 'project_status':
            result = horizon.get(store, project)
            result['memtx_revision'] = memtx.get(store, project)['revision']
            from . import memory
            try:
                graph = memory.get(store, project)
                from .core import fingerprint
                result['graph'] = {'snapshot': graph['snapshot'], 'revision': graph['revision'], 'node_pins': {n['id']: fingerprint(n) for n in graph['graph']['nodes']}}
            except ResearchError: result['graph'] = None
            return result
        if name == 'project_note':
            data = strict_json(args['data_json'])
            if not isinstance(data, dict) or set(data) - {'identity', 'kind', 'text', 'expected_revision', 'status', 'evidence', 'prediction', 'outcome'}:
                raise ResearchError('Invalid project note fields')
            return horizon.note(store, project, **data, actor='agent:' + session)
        if name == 'bind_action':
            return horizon.bind_action(store, session, args['name'], strict_json(args['arguments_json']), strict_json(args['requires_json']),
                                       strict_json(args['conditions_json']), args['purpose'], args['reason'])
        if args['job'] not in horizon.get(store, project)['jobs'] or not args['reason'].strip(): raise ResearchError('Wait requires a tracked job and reason')
        return args
    if name == 'read_context': return horizon.read_context(store, session, **args)
    if name == 'memory_transaction':
        if args['operation'] == 'status': return memtx.get(store, policy['project'])
        return memtx.transact(store, policy['project'], args['operation'], strict_json(args['arguments_json']),
                              expected_revision=args['expected_revision'], actor='agent:' + session)
    if name == 'capability_catalog': return catalog(policy)
    if name == 'operation_help': return operation_help(args['operation'], policy)
    if name == 'read_skill':
        if args['path'] != 'manifest.yaml' and args['path'].split('/')[0] not in bundle_roots():
            raise ResearchError('Only the registered GResearchEvolver bundle is available')
        return read_text(SKILLS, **args)
    if name == 'list_files': return inventory(work, policy)
    if name == 'read_file': return read_text(work, **args)
    if name == 'read_receipt':
        if args['offset'] < 0 or not 1 <= args['limit'] <= 20000: raise ResearchError('Invalid receipt page')
        state = store.get_value('agent:' + valid_id(session))
        call = state['calls'].get(args['call_id'])
        if not call or not call.get('result_hash'): raise ResearchError('No committed receipt for that call')
        raw = store.blob(call['result_hash']).decode('utf-8')
        return {'text': raw[args['offset']:args['offset'] + args['limit']], 'sha256': call['result_hash'],
                'next_offset': args['offset'] + args['limit'] if len(raw) > args['offset'] + args['limit'] else None}
    if name == 'write_file':
        path = checked_path(work, args['path'])
        actual = digest(path.read_bytes()) if path.exists() else ''
        if actual != args['expected_sha256']: raise ResearchError('Artifact changed; read it before writing')
        raw = args['content'].encode('utf-8')
        files = inventory(work, policy)
        total = sum(f['bytes'] for f in files.values()) - files.get(args['path'], {}).get('bytes', 0) + len(raw)
        if total > policy['max_workspace_bytes'] or (args['path'] not in files and len(files) >= policy['max_files']):
            raise ResearchError('Workspace quota exceeded')
        atomic_bytes(path, raw)
        return {'path': args['path'], 'sha256': digest(raw), 'bytes': len(raw)}
    if name == 'report_stage':
        valid_id(args['stage'])
        for key in ('why', 'method', 'findings', 'explanation'):
            if not args[key].strip(): raise ResearchError('Stage report field is empty: ' + key)
        for path in args['evidence']:
            if not checked_path(work, path).is_file(): raise ResearchError('Missing report evidence: ' + path)
        return {'kind': 'stage_report', **args}
    if name == 'ask_researcher':
        if not args['question'].strip(): raise ResearchError('Researcher question is empty')
        return {'kind': 'researcher_question', **args}
    if name == 'run_command':
        if not args['argv'] or not all(s and '\x00' not in s for s in args['argv']) or not args['purpose'].strip():
            raise ResearchError('Provide argv and purpose')
        # stdout/stderr go to the outer supervisor's bounded log files.
        from .reproducibility import executable_receipt
        executable = executable_receipt(args['argv'], work)
        completed = subprocess.run(args['argv'], cwd=work, stdin=subprocess.DEVNULL, shell=False, check=False)
        return {'exit_code': completed.returncode, 'success': completed.returncode == 0,
                'executable': executable,
                'logs': 'See this call supervisor stdout/stderr; external effects are not automatically reversible.'}
    if name == 'research_operation':
        from .cli import operation
        data, op = strict_json(args['arguments_json']), args['operation']
        if op in PATHS:
            for field in PATHS[op]:
                if field in data: data[field] = str(checked_path(work, data[field], allow_root=field == 'root'))
            if op == 'local-index':
                for doc in data.get('documents', []): checked_path(work, doc['path'])
            if op == 'local-search':
                index = read_json(data['index'])
                if Path(index['root']).resolve() != Path(work).resolve(): raise ResearchError('Index root must be this workspace')
                for doc in index['documents']: checked_path(work, doc['path'])
            if op == 'graph':
                # Evidence validator already validates all relative source paths.
                inventory(work, policy)
            if op == 'writing-audit':
                data['ledger'] = dict(data['ledger'])
                data['ledger']['root'] = str(work)
                for result in data['ledger'].get('results', []):
                    if result.get('source', {}).get('path'): checked_path(work, result['source']['path'])
            if op == 'search' and (not 1 <= data.get('pages', 1) <= 5 or not 1 <= data.get('page_size', 25) <= 100):
                raise ResearchError('Automatic search permits 1..5 pages of at most 100 results')
            if op == 's2-bulk' and not 1 <= data.get('max_records', 100) <= 500: raise ResearchError('Bulk search limit is 500')
        if op in MEMORY:
            if data.get('project') not in {None, policy['project']}: raise ResearchError('Use the session memory project')
            data['project'] = policy['project']
            if op in {'memory-put', 'memory-invalidate'}: data['actor'] = 'agent:' + session
        if op == 'rsi-evaluate' and data.get('promote'): raise ResearchError('Agent cannot promote RSI candidates')
        if op == 'paired' and data.get('options', {}).get('resamples', 4000) > 100000: raise ResearchError('Resampling budget exceeded')
        return operation(store, op, data)
    raise ResearchError('Unknown tool')
