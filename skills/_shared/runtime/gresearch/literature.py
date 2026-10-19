"""Bounded public metadata retrieval and loss-preserving reference interchange."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import os
from pathlib import Path
import re
import time
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from .core import ResearchError, digest, fingerprint, read_json, safe_path, write_json


def doi(value):
    return re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)', '', str(value).strip(), flags=re.I).lower().rstrip('.')


def xml_root(text):
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ResearchError('DTD/entity declarations are not supported')
    return ET.fromstring(text)


def get_bytes(url, headers=None):
    request = urllib.request.Request(url, headers={'User-Agent': 'GResearchEvolver/2.0 (research metadata client)', **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(20_000_001)
            break
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 502, 503, 504} or attempt == 2: raise
            retry_after = exc.headers.get('Retry-After')
            try: delay = max(.5, float(retry_after)) if retry_after else 2 ** attempt
            except ValueError:
                try: delay = max(.5, (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds())
                except (ValueError, TypeError): delay = 2 ** attempt
            # Respect provider delays. If too long for this bounded operation,
            # surface throttling instead of retrying earlier than requested.
            if delay > 20: raise
            time.sleep(delay)
    if len(data) > 20_000_000:
        raise ResearchError('Metadata response exceeds 20 MB bound')
    return data


def normalize(item, provider):
    if provider == 'crossref':
        return {'id': item.get('DOI'), 'DOI': doi(item.get('DOI', '')), 'title': (item.get('title') or [''])[0],
                'author': item.get('author', []), 'issued': item.get('issued'), 'type': item.get('type'),
                'URL': item.get('URL'), 'updates': item.get('update-to', []), 'raw': item}
    if provider == 'openalex':
        return {'id': item['id'], 'DOI': doi(item.get('doi') or ''), 'title': item.get('title'),
                'year': item.get('publication_year'), 'author': [a['author'] for a in item.get('authorships', [])],
                'retraction_flag': item.get('is_retracted'), 'raw': item}
    if provider == 'semantic-scholar':
        return {'id': item['paperId'], 'DOI': doi(item.get('externalIds', {}).get('DOI') or ''),
                'title': item.get('title'), 'year': item.get('year'), 'author': item.get('authors', []), 'raw': item}
    if provider == 'europepmc':
        return {'id': item.get('source', '') + ':' + item['id'], 'DOI': doi(item.get('doi', '')),
                'title': item.get('title'), 'year': item.get('pubYear'), 'author_text': item.get('authorString'), 'raw': item}
    raise ResearchError('Unknown provider')


def search(provider, query, destination, *, pages=1, page_size=25, cache_seconds=3600):
    if provider not in {'crossref', 'openalex', 'semantic-scholar', 'europepmc', 'arxiv'}:
        raise ResearchError('Unsupported search provider')
    if not 1 <= pages <= 20 or not 1 <= page_size <= 100 or not query.strip() or not 0 <= cache_seconds <= 604800:
        raise ResearchError('Require a query, 1..20 pages, 1..100 records/page')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    records, receipts, cursor, complete = [], [], '*', False
    for page in range(pages):
        headers = {}
        if provider == 'crossref':
            base, params = 'https://api.crossref.org/works', {'query': query, 'rows': page_size, 'cursor': cursor}
        elif provider == 'openalex':
            base, params = 'https://api.openalex.org/works', {'search': query, 'per-page': page_size, 'cursor': cursor}
            if os.getenv('OPENALEX_API_KEY'): headers['Authorization'] = 'Bearer ' + os.environ['OPENALEX_API_KEY']
        elif provider == 'semantic-scholar':
            base, params = 'https://api.semanticscholar.org/graph/v1/paper/search', {'query': query, 'limit': page_size, 'offset': page * page_size,
                                                                              'fields': 'title,year,authors,externalIds,url,abstract'}
            if os.getenv('S2_API_KEY'): headers['x-api-key'] = os.environ['S2_API_KEY']
        elif provider == 'europepmc':
            base, params = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search', {'query': query, 'format': 'json', 'pageSize': page_size, 'cursorMark': cursor}
        else:
            base, params = 'https://export.arxiv.org/api/query', {'search_query': query, 'start': page * page_size, 'max_results': page_size}
        url = base + '?' + urllib.parse.urlencode(params)
        cache = destination / ('request-' + fingerprint(url) + '.json')
        cached = read_json(cache) if cache.is_file() else None
        served_from_cache = bool(cached and time.time() - cached['retrieved_at'] <= cache_seconds)
        if served_from_cache:
            raw = safe_path(destination, cached['raw_file']).read_bytes()
            if digest(raw) != cached['sha256']: raise ResearchError('Cached response corrupted')
            retrieved = cached['retrieved_at']
        else:
            raw = get_bytes(url, headers)
            retrieved = time.time()
        h = digest(raw)
        raw_file = h + ('.xml' if provider == 'arxiv' else '.json')
        (destination / raw_file).write_bytes(raw)
        write_json(cache, {'raw_file': raw_file, 'sha256': h, 'retrieved_at': retrieved})
        receipts.append({'url': url, 'sha256': h, 'retrieved_at': retrieved, 'served_from_cache': served_from_cache, 'page': page + 1})
        if provider == 'arxiv':
            root = xml_root(raw.decode('utf-8'))
            ns = {'a': 'http://www.w3.org/2005/Atom', 'o': 'http://a9.com/-/spec/opensearch/1.1/'}
            entries = root.findall('a:entry', ns)
            batch = [{'id': e.findtext('a:id', '', ns), 'title': ' '.join(e.findtext('a:title', '', ns).split()),
                      'abstract': e.findtext('a:summary', '', ns), 'updated': e.findtext('a:updated', '', ns),
                      'author': [a.findtext('a:name', '', ns) for a in e.findall('a:author', ns)]} for e in entries]
            total = int(root.findtext('o:totalResults', '0', ns))
            complete = (page + 1) * page_size >= total
        else:
            body = json.loads(raw)
            if provider == 'crossref':
                items = body['message']['items']
                next_cursor = body['message'].get('next-cursor')
                complete = not items or len(items) < page_size or not next_cursor or next_cursor == cursor
                cursor = next_cursor
            elif provider == 'openalex':
                items = body['results']
                cursor = body['meta'].get('next_cursor')
                complete = not cursor or len(items) < page_size
            elif provider == 'semantic-scholar':
                items = body.get('data', [])
                complete = 'next' not in body or len(items) < page_size
            else:
                items = body['resultList']['result']
                nxt = body.get('nextCursorMark')
                complete = not nxt or nxt == cursor or len(items) < page_size
                cursor = nxt
            batch = [normalize(x, provider) for x in items]
        records.extend(batch)
        if complete: break
        if page + 1 < pages: time.sleep(.35 if provider != 'arxiv' else 3)
    result = {'provider': provider, 'query': query, 'records': records, 'receipts': receipts, 'pagination_complete': complete,
              'search_exhaustive': False, 'coverage': 'provider index and query scope only', 'limits': {'pages': pages, 'page_size': page_size}}
    write_json(destination / 'search.json', result)
    return result


def semantic_scholar_bulk(query, destination, max_records=100):
    """Explicit documented bulk endpoint; not a silent relevance-search fallback."""
    if not query.strip() or type(max_records) is not int or not 1 <= max_records <= 1000:
        raise ResearchError('Bulk query needs 1..1000 maximum records')
    destination = Path(destination); destination.mkdir(parents=True, exist_ok=False)
    params = {'query':query,'fields':'title,year,authors,externalIds,url,abstract'}
    url = 'https://api.semanticscholar.org/graph/v1/paper/search/bulk?' + urllib.parse.urlencode(params)
    headers = {'x-api-key':os.environ['S2_API_KEY']} if os.getenv('S2_API_KEY') else {}
    raw = get_bytes(url, headers); body = json.loads(raw); h=digest(raw)
    (destination/'response.json').write_bytes(raw)
    records = [normalize(x,'semantic-scholar') for x in body.get('data',[])[:max_records]]
    result = {'provider':'semantic-scholar','mode':'bulk','query':query,'records':records,
              'receipt':{'url':url,'sha256':h,'retrieved_at':time.time()},'total':body.get('total'),
              'truncated':len(body.get('data',[]))>max_records,'next_token':body.get('token'),
              'search_exhaustive':False,'scope':'bounded first bulk page, not relevance ranking; raw page retained'}
    write_json(destination/'search.json',result)
    return result


def bib_records(text):
    """Balanced-brace/quoted BibTeX literals. Fail explicitly on macros/concatenation."""
    records = []
    pos = 0
    while True:
        match = re.search(r'@(\w+)\s*\{', text[pos:])
        if not match: break
        typ = match[1].lower()
        start = pos + match.end()
        depth, quote, escape, i = 1, False, False, start
        while i < len(text) and depth:
            c = text[i]
            if escape: escape = False
            elif c == '\\': escape = True
            elif c == '"' and depth == 1: quote = not quote
            elif not quote and c == '{': depth += 1
            elif not quote and c == '}': depth -= 1
            i += 1
        if depth: raise ResearchError('Unbalanced BibTeX entry')
        body, pos = text[start:i - 1], i
        if typ in {'comment', 'preamble'}: continue
        if typ == 'string': raise ResearchError('BibTeX macros require normalization with a full BibTeX parser first')
        if ',' not in body: raise ResearchError('BibTeX entry lacks fields')
        key, fields = body.split(',', 1)
        record, at = {'id': key.strip(), 'type': typ}, 0
        while at < len(fields):
            m = re.match(r'\s*,?\s*([\w-]+)\s*=\s*', fields[at:])
            if not m:
                if fields[at:].strip(' \r\n\t,'): raise ResearchError('Unsupported BibTeX field syntax')
                break
            name = m[1].lower()
            at += m.end()
            if at >= len(fields): raise ResearchError('Missing BibTeX field value')
            c = fields[at]
            if c in '{"':
                end, level, escaped = at + 1, 1, False
                while end < len(fields):
                    ch = fields[end]
                    if escaped: escaped = False
                    elif ch == '\\': escaped = True
                    elif c == '"' and ch == '"': break
                    elif c == '{' and ch == '{': level += 1
                    elif c == '{' and ch == '}':
                        level -= 1
                        if level == 0: break
                    end += 1
                if end >= len(fields): raise ResearchError('Unclosed BibTeX value')
                value, at = fields[at + 1:end], end + 1
            else:
                mval = re.match(r'\d+', fields[at:])
                if not mval: raise ResearchError('BibTeX bare macros are not resolved')
                value, at = mval[0], at + mval.end()
            record['DOI' if name == 'doi' else name] = value
        records.append(record)
    if not records: raise ResearchError('No BibTeX records')
    return records


def import_references(path, format=None):
    path = Path(path)
    raw = path.read_bytes()
    if len(raw) > 20_000_000: raise ResearchError('Reference file exceeds 20 MB')
    text = raw.decode('utf-8-sig')
    format = format or {'.bib': 'bibtex', '.ris': 'ris', '.nbib': 'nbib', '.xml': 'xml', '.enw': 'endnote'}.get(path.suffix.lower(), 'csl')
    if format == 'csl':
        obj = json.loads(text)
        records = obj if isinstance(obj, list) else obj.get('records', obj.get('items', []))
    elif format == 'bibtex': records = bib_records(text)
    elif format in {'ris', 'nbib', 'endnote'}:
        records, fields, last = [], {}, None
        def flush():
            if fields:
                mapping = {'TI': 'title', 'T1': 'title', 'DO': 'DOI', 'A1': 'author', 'AU': 'author', 'PY': 'year',
                           'Y1': 'year', 'ID': 'id', 'PMID': 'id', 'LID': 'identifier', 'JT': 'container-title',
                           '%T': 'title', '%A': 'author', '%D': 'year', '%R': 'DOI', '%0': 'type'}
                r = {'raw_fields': dict(fields)}
                for k, values in fields.items():
                    name = mapping.get(k, k)
                    r[name] = values if name == 'author' else ' '.join(values)
                if format == 'nbib':
                    for v in fields.get('AID', []) + fields.get('LID', []):
                        if v.endswith('[doi]'): r['DOI'] = v[:-5].strip()
                records.append(r)
        for line in text.splitlines() + ['ER  -' if format == 'ris' else '']:
            match = re.match(r'^(%\S)\s+(.*)$' if format == 'endnote' else r'^([A-Z0-9]{2,4})\s*-\s?(.*)$', line)
            if (format == 'ris' and line.startswith('ER')) or (format != 'ris' and not line.strip()):
                flush(); fields, last = {}, None
            elif match:
                last = match[1]
                fields.setdefault(last, []).append(match[2])
            elif line.strip() and last:
                fields[last][-1] += ' ' + line.strip()
        if fields: flush()
    elif format == 'xml':
        root = xml_root(text)
        records = []
        for r in root.findall('.//PubmedArticle'):
            records.append({'id': r.findtext('.//PMID'), 'title': ''.join(r.find('.//ArticleTitle').itertext()) if r.find('.//ArticleTitle') is not None else '',
                            'DOI': next((x.text for x in r.findall('.//ArticleId') if x.get('IdType') == 'doi'), ''),
                            'raw_xml': ET.tostring(r, encoding='unicode')})
        if not records:
            for r in root.findall('.//record'):
                def value(p):
                    node = r.find(p)
                    return ''.join(node.itertext()) if node is not None else ''
                records.append({'id': value('rec-number'), 'title': value('titles/title'), 'DOI': value('electronic-resource-num'),
                                'year': value('dates/year'), 'raw_xml': ET.tostring(r, encoding='unicode')})
    else: raise ResearchError('Supported formats: csl, bibtex, ris, nbib, endnote, xml')
    if not records: raise ResearchError('No records imported')
    for i, record in enumerate(records):
        record['id'] = str(record.get('id') or f'{digest(raw)[:10]}-{i}')
        if record.get('DOI'): record['DOI'] = doi(record['DOI'])
        record['import_provenance'] = {'file': path.name, 'sha256': digest(raw), 'record': i, 'format': format}
    return {'records': records, 'source_hash': digest(raw), 'source_text': text, 'format': format}


def deduplicate(records):
    result, by_doi, collisions = [], {}, []
    for r in records:
        r = dict(r)
        d = doi(r.get('DOI', ''))
        if d and d in by_doi:
            prev = by_doi[d]
            norm = lambda s: re.sub(r'\W+', '', str(s).lower())
            if prev.get('title') and r.get('title') and norm(prev['title']) != norm(r['title']):
                collisions.append({'DOI': d, 'left': prev['id'], 'right': r['id'], 'action': 'kept_separate_for_review'})
                result.append(r)
            else:
                prev.setdefault('aliases', []).append(r)
        else:
            result.append(r)
            if d: by_doi[d] = r
    return {'records': result, 'collisions': collisions, 'original_count': len(records), 'unique_count': len(result)}


def export_references(records, path, format='csl'):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    def authors(r):
        value = r.get('author', [])
        if isinstance(value, str): return value.split(' and ')
        return [a if isinstance(a, str) else a.get('literal') or (a.get('family', a.get('name', '')) + (', ' + a['given'] if a.get('given') else '')) for a in value]
    def year(r):
        return r.get('year') or (r.get('issued') or {}).get('date-parts', [['']])[0][0]
    if format == 'csl': write_json(path, records)
    elif format == 'ris':
        lines = []
        for r in records:
            typ = {'article': 'JOUR', 'article-journal': 'JOUR', 'journal-article': 'JOUR', 'book': 'BOOK', 'chapter': 'CHAP', 'inproceedings': 'CONF', 'paper-conference': 'CONF'}.get(r.get('type', ''), r.get('TY', 'GEN'))
            lines += ['TY  - ' + typ, 'ID  - ' + r['id'].replace('\n', ' '), 'TI  - ' + str(r.get('title', '')).replace('\n', ' '), 'DO  - ' + r.get('DOI', '').replace('\n', ' ')]
            for a in authors(r): lines.append('AU  - ' + a.replace('\n', ' '))
            for tag, field in [('JO', 'container-title'), ('VL', 'volume'), ('IS', 'issue'), ('SP', 'page'), ('UR', 'URL'), ('AB', 'abstract')]:
                if r.get(field): lines.append(tag + '  - ' + str(r[field]).replace('\n', ' '))
            lines += ['PY  - ' + str(year(r)), 'ER  -', '']
        Path(path).write_text('\n'.join(lines), encoding='utf-8')
    elif format == 'bibtex':
        translations = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '%': r'\%', '&': r'\&', '_': r'\_', '$': r'\$', '#': r'\#', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
        esc = lambda x: ''.join(translations.get(c, c) for c in str(x))
        entries = []
        for i, r in enumerate(records):
            key = re.sub(r'[^A-Za-z0-9_:-]', '_', r['id']) or 'ref' + str(i)
            fields = {'title': r.get('title', ''), 'author': ' and '.join(authors(r)), 'year': year(r), 'doi': r.get('DOI', ''),
                      'journal': r.get('container-title', r.get('journal', '')), 'volume': r.get('volume', ''),
                      'number': r.get('issue', ''), 'pages': r.get('page', r.get('pages', '')), 'url': r.get('URL', r.get('url', ''))}
            typ = {'article': 'article', 'article-journal': 'article', 'journal-article': 'article', 'JOUR': 'article', 'book': 'book', 'BOOK': 'book', 'chapter': 'incollection', 'inproceedings': 'inproceedings', 'paper-conference': 'inproceedings'}.get(r.get('type', r.get('TY', '')), 'misc')
            encode = str if r.get('import_provenance', {}).get('format') == 'bibtex' else esc
            entries.append('@' + typ + '{' + key + ',\n' + ',\n'.join('  ' + k + ' = {' + encode(v) + '}' for k, v in fields.items() if v != '') + '\n}')
        Path(path).write_text('\n\n'.join(entries), encoding='utf-8')
    else: raise ResearchError('Export formats: csl, ris, bibtex')
    # Lossless sidecar prevents format limitations from silently dropping notes/attachments/IDs.
    write_json(str(path) + '.preserved.json', {'records': records, 'export_format': format})
    return {'path': str(path), 'records': len(records), 'lossless_sidecar': str(path) + '.preserved.json'}


def citation_check(identifier, destination):
    d = doi(identifier)
    if not re.fullmatch(r'10\.\d{4,9}/\S+', d): raise ResearchError('Invalid DOI')
    raw = get_bytes('https://api.crossref.org/works/' + urllib.parse.quote(d, safe=''))
    response = json.loads(raw)['message']
    Path(destination).mkdir(parents=True, exist_ok=True)
    (Path(destination) / (digest(raw) + '.json')).write_bytes(raw)
    updates = response.get('update-to', [])
    return {'DOI': d, 'matched': doi(response.get('DOI', '')) == d, 'metadata': normalize(response, 'crossref'),
            'raw_hash': digest(raw), 'checked_at': time.time(), 'updates': updates,
            'retraction_status': 'flagged' if any('retract' in str(x.get('type', '')).lower() for x in updates) else 'unknown',
            'correction_status': 'flagged' if any(any(word in str(x.get('type', '')).lower() for word in ('correct', 'errat')) for x in updates) else 'unknown',
            'limitation': 'Crossref update metadata may describe notices rather than the original work; absence is not proof of no retraction. Verify publisher/Crossmark and record dated adjudication.'}


def zotero_read(library_type, library_id, destination, max_pages=10):
    if library_type not in {'users', 'groups'} or not str(library_id).isdigit() or not 1 <= max_pages <= 100:
        raise ResearchError('Zotero requires users/groups, numeric library ID and bounded pages')
    headers = {'Zotero-API-Version': '3'}
    if os.getenv('ZOTERO_API_KEY'): headers['Zotero-API-Key'] = os.environ['ZOTERO_API_KEY']
    dest = Path(destination); dest.mkdir(parents=True, exist_ok=True)
    records, receipts, complete = [], [], False
    for page in range(max_pages):
        url = f'https://api.zotero.org/{library_type}/{library_id}/items?format=json&limit=100&start={page * 100}'
        raw = get_bytes(url, headers)
        (dest / (digest(raw) + '.json')).write_bytes(raw)
        batch = json.loads(raw)
        receipts.append({'url': url, 'sha256': digest(raw), 'retrieved_at': time.time()})
        for x in batch:
            records.append({'id': x['key'], 'version': x['version'], 'title': x['data'].get('title', ''),
                            'DOI': doi(x['data'].get('DOI', '')), 'zotero': x})
        if len(batch) < 100: complete = True; break
    result = {'records': records, 'receipts': receipts, 'pagination_complete': complete,
              'attachments': 'metadata and links preserved; attachment binary download not implied'}
    write_json(dest / 'zotero.json', result)
    return result


def monitor(store, name, records):
    previous = store.get_value('monitor:' + name, {})
    current = {}
    for r in records:
        identity = doi(r.get('DOI', '')) or str(r.get('id', ''))
        if not identity or identity in current: raise ResearchError('Monitor requires unique stable IDs; deduplicate first')
        normalized = {k: v for k, v in r.items() if k not in {'retrieved_at', 'import_provenance'}}
        current[identity] = {'hash': fingerprint(normalized), 'record': r}
    report = {'new': [k for k in current if k not in previous],
              'changed': [k for k in current if k in previous and current[k]['hash'] != previous[k]['hash']],
              'flagged': [k for k, v in current.items() if v['record'].get('retraction_flag') is True or v['record'].get('retraction_status') == 'flagged'],
              'missing_from_current_query': sorted(set(previous) - set(current)), 'absence_means_retracted': False}
    with store.tx():
        # A bounded/incomplete search must not delete prior records.
        store.set_value('monitor:' + name, {**previous, **current})
        store.event('monitor-' + name, 'digest', report)
    return report


def export_notes(records, destination):
    """Versioned Obsidian/plain-Markdown bridge; keeps parent IDs and original metadata."""
    import html
    version = fingerprint(records)[:16]
    dest = Path(destination) / ('library-' + version)
    dest.mkdir(parents=True, exist_ok=True)
    names = {r['id']: fingerprint(r['id'])[:16] + '.md' for r in records}
    if len(names) != len(records): raise ResearchError('Notes export needs unique IDs')
    links = []
    for r in records:
        item = r.get('zotero', {}).get('data', {})
        title = r.get('title') or item.get('title') or item.get('itemType') or r['id']
        lines = ['# ' + html.escape(str(title)), '', 'Reference ID: ' + r['id'], '', 'DOI: ' + r.get('DOI', ''), '']
        parent = item.get('parentItem')
        if parent: lines += ['Parent: ' + ('[[' + names[parent][:-3] + ']]' if parent in names else parent), '']
        notes = r.get('notes', [])
        if isinstance(notes, str): notes = [notes]
        for note in notes + [item.get('note', ''), item.get('annotationText', ''), item.get('annotationComment', '')]:
            if note: lines += [html.escape(str(note)), '']
        if item.get('filename') or item.get('url'):
            lines += ['Attachment/link metadata: ' + html.escape(str({k: item[k] for k in ('filename', 'url', 'contentType', 'linkMode') if k in item})), '']
        (dest / names[r['id']]).write_text('\n'.join(lines), encoding='utf-8')
        links.append('- [[' + names[r['id']][:-3] + '|' + html.escape(str(title)).replace('|', ' ') + ']]')
    (dest / 'index.md').write_text('# Reference library\n\n' + '\n'.join(links) + '\n', encoding='utf-8')
    write_json(dest / 'records.json', records)
    write_json(dest / 'identity-map.json', names)
    return {'directory': str(dest), 'version': version, 'records': len(records),
            'scope': 'versioned local notes/annotation metadata export; no bidirectional remote edits or attachment binary sync'}
