"""Page-addressed source records, typed provenance, and explicit claim bindings."""
from __future__ import annotations

from pathlib import Path
import re

from .core import ResearchError, digest, finite, fingerprint, read_json, safe_path, write_json


def ingest_pdf(source, destination):
    try:
        import fitz
    except ImportError as exc:
        raise ResearchError('PDF ingestion requires PyMuPDF; install it in the project environment') from exc
    source, destination = Path(source), Path(destination)
    data = source.read_bytes()
    document = fitz.open(stream=data, filetype='pdf')
    if document.needs_pass:
        raise ResearchError('Encrypted PDF requires a decrypted authorized copy')
    destination.mkdir(parents=True, exist_ok=True)
    pdf_hash = digest(data)
    (destination / 'source.pdf').write_bytes(data)
    pages = []
    for i, page in enumerate(document):
        text = page.get_text()
        textpath = f'page-{i + 1:04d}.txt'
        # Hash the exact bytes written; Windows text mode would otherwise translate LF to CRLF.
        (destination / textpath).write_bytes(text.encode('utf-8'))
        pages.append({'page': i + 1, 'path': textpath, 'sha256': digest(text.encode('utf-8')),
                      'status': 'extracted' if len(text.strip()) >= 40 else 'ocr_or_manual_check_needed'})
    result = {'id': pdf_hash[:16], 'sha256': pdf_hash, 'source_name': source.name, 'source': 'source.pdf',
              'metadata': document.metadata, 'pages': pages,
              'limitations': 'PDF text order may differ from reading order; visual tables/formulae require manual verification; page numbers are physical PDF pages'}
    write_json(destination / 'source.json', result)
    document.close()
    return result


def normalize_text(value):
    return ' '.join(value.split())


def validate_graph(graph, root):
    nodes = graph.get('nodes', [])
    index = {n['id']: n for n in nodes}
    errors, unresolved = [], []
    if not nodes: errors.append('empty evidence graph')
    if len(nodes) != len(index): errors.append('duplicate node IDs')
    allowed = {'source', 'data', 'code', 'result', 'claim'}
    for n in nodes:
        if n.get('type') not in allowed:
            errors.append(f"{n['id']}: invalid type")
            continue
        if n['type'] != 'claim':
            if not n.get('path') or not n.get('sha256'):
                errors.append(f"{n['id']}: missing file locator/hash")
                continue
            p = safe_path(root, n['path'])
            if not p.is_file() or digest(p.read_bytes()) != n['sha256']:
                errors.append(f"{n['id']}: file missing or modified")
        else:
            for key in ('text', 'scope', 'certainty'):
                if not n.get(key): errors.append(f"{n['id']}: missing {key}")
            if len(n.get('quantities', [])) > 1:
                errors.append(f"{n['id']}: split multiple quantities into atomic claims")
            for q in n.get('quantities', []):
                finite(q['value'])
                if any(k not in q for k in ('metric', 'condition', 'unit', 'run')):
                    errors.append(f"{n['id']}: incomplete quantity binding")
    edgeids = set()
    types = {'used_by': ({'source', 'data', 'result'}, {'code'}), 'produces': ({'code'}, {'result'}),
             'supports': ({'source', 'result'}, {'claim'}), 'contradicts': ({'source', 'result'}, {'claim'}),
             'qualifies': ({'claim'}, {'claim'}), 'motivates': ({'claim', 'source'}, {'claim'})}
    supported = set()
    for e in graph.get('edges', []):
        eid = e['id']
        if eid in edgeids: errors.append('duplicate edge ID:' + eid)
        edgeids.add(eid)
        if e.get('from') not in index or e.get('to') not in index or e.get('relation') not in types:
            errors.append(f'{eid}: unknown endpoint/relation')
            continue
        src, dst = index[e['from']], index[e['to']]
        a, b = types[e['relation']]
        if src['type'] not in a or dst['type'] not in b:
            errors.append(f'{eid}: incompatible endpoint types')
        if e['relation'] in {'supports', 'contradicts'}:
            locator = e.get('evidence', {})
            try:
                path = safe_path(root, locator['path'])
                raw = path.read_bytes()
                if digest(raw) != locator['sha256']:
                    errors.append(f'{eid}: evidence hash mismatch')
                if not locator.get('quote') or normalize_text(locator['quote']) not in normalize_text(raw.decode('utf-8')):
                    errors.append(f'{eid}: quote absent from source text')
                if src['type'] == 'source' and (not isinstance(locator.get('page'), int) or locator['page'] < 1):
                    errors.append(f'{eid}: physical page required')
                if src['type'] == 'source':
                    extraction = read_json(safe_path(root, src['extraction']))
                    page = next((p for p in extraction['pages'] if p['page'] == locator.get('page')), None)
                    expected = safe_path(root, src['extraction']).parent / page['path'] if page else None
                    if extraction['sha256'] != src['sha256'] or not page or page['sha256'] != locator['sha256'] or expected.resolve() != path:
                        errors.append(f'{eid}: quote is not bound to the stated source/page extraction')
                elif locator['path'] != src['path'] or locator['sha256'] != src['sha256']:
                    errors.append(f'{eid}: result evidence does not match source node')
            except (KeyError, OSError, UnicodeError) as exc:
                errors.append(f'{eid}: unusable evidence locator ({exc})')
            adjudication = e.get('adjudication', {})
            if adjudication.get('status') != 'accepted' or not all(adjudication.get(k) for k in ('reviewer', 'rationale', 'scope_checked')):
                unresolved.append(eid)
            elif e['relation'] == 'supports':
                supported.add(e['to'])
    for n in nodes:
        if n['type'] == 'claim' and n.get('status') == 'verified' and n['id'] not in supported:
            errors.append(f"{n['id']}: verified status without adjudicated support")
    return {'structurally_valid': not errors, 'errors': errors, 'unadjudicated_edges': unresolved,
            'scientific_truth_proven': False, 'scope': 'hash/quote/type checks plus recorded semantic adjudications; adjudications may be wrong'}


def audit_writing(document, ledger):
    """Every numeric span is bound explicitly, including years/citations/section numbers.

    Values compare against a scoped result ledger; span offsets distinguish repeated
    values under different conditions. Human review checks context, negation and scope.
    """
    tokens = list(re.finditer(r'(?<![\w])[-+]?\d+(?:[.,]\d+)*(?:[eE][-+]?\d+)?%?', document))
    bindings = ledger.get('bindings', [])
    results = {r['id']: r for r in ledger.get('results', [])}
    errors, covered, exemptions = [], set(), []
    if len(results) != len(ledger.get('results', [])): errors.append('duplicate result IDs')
    provenance = []
    for result in results.values():
        source = result.get('source', {})
        try:
            path = safe_path(ledger['root'], source['path'])
            raw = path.read_bytes()
            if digest(raw) != source['sha256']:
                raise ResearchError('source file changed')
            if source.get('kind') == 'computed':
                obj = read_json(path)
                for key in source['pointer']:
                    obj = obj[int(key)] if isinstance(obj, list) else obj[key]
                for key in ('value', 'metric', 'condition', 'unit', 'run'):
                    if obj.get(key) != result.get(key):
                        raise ResearchError('source result/context does not match ledger')
            elif source.get('kind') == 'literature':
                if not source.get('quote') or normalize_text(source['quote']) not in normalize_text(raw.decode('utf-8')):
                    raise ResearchError('source quote absent')
                if not all(source.get(k) for k in ('page', 'reviewer', 'rationale')):
                    raise ResearchError('literature quantity needs page and recorded semantic adjudication')
            else: raise ResearchError('source kind must be computed or literature')
        except (ResearchError, KeyError, OSError, IndexError, TypeError, UnicodeError) as exc:
            provenance.append(f"{result['id']}: {exc}")
    for binding in bindings:
        start, end = binding['start'], binding['end']
        if (start, end) not in {t.span() for t in tokens}:
            errors.append(f'binding is not an exact numeric span: {start}:{end}')
        if (start, end) in covered:
            errors.append('duplicate span binding')
        covered.add((start, end))
        literal = document[start:end]
        if literal != binding.get('literal'):
            errors.append(f'span changed at {start}')
            continue
        if binding.get('kind') == 'non_result':
            if not binding.get('reason'): errors.append(f'unexplained non-result at {start}')
            exemptions.append(binding)
            continue
        result = results.get(binding.get('result_id'))
        if not result:
            errors.append(f'unknown result at {start}')
            continue
        for key in ('metric', 'condition', 'unit', 'run'):
            if binding.get(key) != result.get(key) or key not in result:
                errors.append(f'{key} binding mismatch at {start}')
        finite(result['value'])
        if literal.endswith('%') and result['unit'] not in {'%', 'percent', 'pct'}:
            errors.append(f'percentage literal has incompatible unit at {start}')
        try:
            value = float(literal.rstrip('%').replace(',', ''))
        except ValueError:
            errors.append(f'invalid numeric literal at {start}')
            continue
        decimals = binding.get('decimals', 6)
        if not isinstance(decimals, int) or not 0 <= decimals <= 12:
            errors.append('decimals must be 0..12')
            continue
        if abs(value - result['value']) > .500001 * 10 ** (-decimals):
            errors.append(f'unsupported number at {start}')
    for token in tokens:
        if token.span() not in covered:
            errors.append(f'unbound numeric span {token.start()}:{token.end()} {token.group()}')
    bibliography = {r['id'] for r in ledger.get('references', [])}
    cited = set(re.findall(r'\[@([^\]]+)\]', document))
    errors += ['unknown citation:' + k for k in cited - bibliography]
    return {'passed': not errors and not provenance, 'errors': errors, 'provenance_errors': provenance, 'numeric_spans': len(tokens), 'exemptions': exemptions,
            'semantic_review_required': ['scope', 'negation', 'hedging', 'causality', 'citation entailment'],
            'ledger_hash': fingerprint(ledger), 'document_text_hash': digest(document.encode('utf-8')),
            'text_hash_scope': 'UTF-8 of supplied Unicode text; raw artifact bytes are separately recorded by workflow'}


def novelty_matrix(data):
    if not data.get('searches') or not data.get('claims'):
        raise ResearchError('Novelty assessment needs dated search records and claim-level comparisons')
    problems = []
    for search in data['searches']:
        if not all(search.get(k) for k in ('query', 'provider', 'date', 'raw_hash')):
            problems.append('incomplete search provenance')
    for claim in data['claims']:
        if not claim.get('nearest_work'): problems.append(claim['id'] + ': missing nearest prior work')
        for work in claim.get('nearest_work', []):
            if not all(work.get(k) for k in ('reference', 'shared', 'difference', 'evidence')):
                problems.append(claim['id'] + ': incomplete prior-work comparison')
        if 'counterevidence' not in claim: problems.append(claim['id'] + ': counterevidence search absent')
    return {'complete': not problems, 'problems': problems,
            'conclusion_scope': 'differentiation within documented corpus/date; global priority is not established'}
