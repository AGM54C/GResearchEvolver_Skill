"""Deterministic page/chunk BM25 and optional externally produced embedding fusion."""
from __future__ import annotations

import math
from pathlib import Path
import re
from collections import Counter

from .core import ResearchError, digest, finite, fingerprint, safe_path, write_json


def tokenize(text):
    lowered = text.lower()
    latin = re.findall(r'[a-z0-9_]+', lowered)
    chinese = re.findall(r'[\u3400-\u9fff]+', lowered)
    return latin + [s[i:i + 2] for s in chinese for i in range(max(1, len(s) - 1))]


def build_index(data):
    root = data['root']
    documents = []
    for spec in data['documents']:
        source = safe_path(root, spec['path'])
        raw = source.read_bytes()
        text = raw.decode('utf-8-sig')
        if spec.get('sha256') and digest(raw) != spec['sha256']:
            raise ResearchError('Source changed while indexing')
        if any(d['id'] == spec['id'] for d in documents): raise ResearchError('Duplicate document ID')
        item = {'id': spec['id'], 'path': spec['path'], 'sha256': digest(raw), 'page': spec.get('page'),
                'source_id': spec.get('source_id', spec['id']), 'text': text, 'terms': dict(Counter(tokenize(text)))}
        if 'embedding' in spec:
            if not data.get('embedding_model') or not data.get('embedding_provenance'):
                raise ResearchError('Embeddings need pinned model and actual generation provenance')
            if not spec['embedding'] or any(not isinstance(x, (int, float)) for x in spec['embedding']):
                raise ResearchError('Invalid embedding vector')
            for x in spec['embedding']: finite(x)
            if not any(x != 0 for x in spec['embedding']): raise ResearchError('Zero vector')
            item['embedding'] = spec['embedding']
        documents.append(item)
    if not documents: raise ResearchError('No documents to index')
    dimensions = {len(d['embedding']) for d in documents if 'embedding' in d}
    if len(dimensions) > 1: raise ResearchError('Embedding dimensions differ')
    index = {'version': 1, 'root': str(Path(root).resolve()), 'documents': documents,
             'embedding_model': data.get('embedding_model'), 'embedding_provenance': data.get('embedding_provenance'),
             'tokenizer': 'latin words + CJK bigrams v1', 'bm25': {'k1': 1.2, 'b': .75}}
    index['fingerprint'] = fingerprint(index)
    if data.get('destination'): write_json(data['destination'], index)
    return index


def query_index(index, query, *, aliases=None, top_k=10, vector=None, embedding_model=None):
    content = {k: v for k, v in index.items() if k != 'fingerprint'}
    if fingerprint(content) != index['fingerprint']: raise ResearchError('Index changed')
    if not query.strip() or not 1 <= top_k <= 100: raise ResearchError('Require a query and 1..100 results')
    for doc in index['documents']:
        p = safe_path(index['root'], doc['path'])
        if not p.is_file() or digest(p.read_bytes()) != doc['sha256']:
            raise ResearchError('Index source missing/changed: ' + doc['path'])
    documents = index['documents']
    terms = set(tokenize(' '.join([query, *(aliases or [])])))
    n = len(documents)
    average = sum(sum(d['terms'].values()) for d in documents) / n or 1
    lexical = []
    for d in documents:
        length, score = sum(d['terms'].values()), 0.0
        for term in terms:
            tf = d['terms'].get(term, 0)
            if tf:
                df = sum(term in item['terms'] for item in documents)
                idf = math.log(1 + (n - df + .5) / (df + .5))
                score += idf * tf * 2.2 / (tf + 1.2 * (.25 + .75 * length / average))
        if score > 0: lexical.append((d['id'], score))
    lexical.sort(key=lambda r: (-r[1], r[0]))
    semantic = []
    if vector is not None:
        if embedding_model != index.get('embedding_model') or not embedding_model:
            raise ResearchError('Query embedding model/version must match index')
        for x in vector: finite(x)
        qnorm = math.sqrt(sum(x * x for x in vector))
        if qnorm == 0: raise ResearchError('Zero query vector')
        for d in documents:
            v = d.get('embedding')
            if v is None: continue
            if len(v) != len(vector): raise ResearchError('Query dimension differs')
            similarity = sum(a * b for a, b in zip(v, vector)) / qnorm / math.sqrt(sum(x * x for x in v))
            semantic.append((d['id'], similarity))
        semantic.sort(key=lambda r: (-r[1], r[0]))
    fused = {}
    for ranking in (lexical, semantic):
        for rank, (identity, _) in enumerate(ranking): fused[identity] = fused.get(identity, 0) + 1 / (60 + rank + 1)
    by_id = {d['id']: d for d in documents}
    result = [{**{k: v for k, v in by_id[identity].items() if k not in {'embedding', 'terms'}}, 'rrf_score': score}
              for identity, score in sorted(fused.items(), key=lambda item: (-item[1], item[0]))[:top_k]]
    return {'query': query, 'aliases': aliases or [], 'results': result, 'index_hash': index['fingerprint'],
            'mode': 'BM25+embedding RRF' if vector is not None else 'BM25',
            'limitation': 'ranking is retrieval relevance, not factual support; multilingual aliases/embeddings need independent quality checks'}


def invalidate(graph, source_ids, reason):
    if not reason: raise ResearchError('Invalidation requires reason')
    import copy
    graph = copy.deepcopy(graph)
    ids = {n['id'] for n in graph['nodes']}
    if not set(source_ids).issubset(ids): raise ResearchError('Unknown source IDs')
    affected = set(source_ids)
    while True:
        new = affected | {e['to'] for e in graph.get('edges', []) if e['from'] in affected}
        if new == affected: break
        affected = new
    for node in graph['nodes']:
        if node['id'] in affected:
            node['previous_status'] = node.get('status')
            node.update(status='needs_review', invalidation_reason=reason)
    for edge in graph.get('edges', []):
        if edge['from'] in affected or edge['to'] in affected:
            if 'adjudication' in edge: edge['previous_adjudication'] = edge.pop('adjudication')
            edge['status'] = 'needs_review'
    return {'graph': graph, 'affected': sorted(affected), 'reason': reason, 'artifacts_deleted': False}
