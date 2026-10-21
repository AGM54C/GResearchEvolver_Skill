"""Versioned research property graphs, with an optional OpenViking projection.

Nodes remain research items; edges remain typed, directed records including their
provenance and adjudications. Summaries and vector hits cannot rewrite this graph.
"""
from collections import Counter
import json
import math
import time

from .core import ResearchError, canonical, fingerprint, valid_id, write_json
from .locking import resource_lock
from .retrieval import tokenize, invalidate


def validate(graph):
    if not isinstance(graph, dict) or not isinstance(graph.get('nodes'), list) or not isinstance(graph.get('edges'), list):
        raise ResearchError('Memory graph needs nodes[] and edges[]')
    for items in (graph['nodes'], graph['edges']):
        ids = set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not 1 <= len(item['id']) <= 256:
                raise ResearchError('Every node/edge needs a nonempty stable string ID, at most 256 characters')
            if item['id'] in ids:
                raise ResearchError('Duplicate graph ID: ' + item['id'])
            ids.add(item['id'])
    nodes = {n['id'] for n in graph['nodes']}
    if any(not isinstance(n.get('type'), str) or not n['type'].strip() for n in graph['nodes']):
        raise ResearchError('Every research node needs a type')
    for edge in graph['edges']:
        if edge.get('from') not in nodes or edge.get('to') not in nodes:
            raise ResearchError('Dangling graph edge: ' + edge['id'])
        if not isinstance(edge.get('relation'), str) or not edge['relation'].strip():
            raise ResearchError('Every edge needs a relation type')
    canonical(graph)  # reject non-finite / non-JSON values before persistence
    from .validity import structure
    structure(graph)
    return graph


def put(store, project, graph, expected_revision, *, actor, reason):
    valid_id(project)
    graph = validate(graph)
    if type(expected_revision) is not int or expected_revision < 0 or any(not isinstance(v, str) or not v.strip() for v in (actor, reason)):
        raise ResearchError('Graph write requires expected_revision >= 0, actor and reason')
    with store.tx():
        old = store.db.execute('SELECT * FROM memory_graphs WHERE project=?', (project,)).fetchone()
        revision = old['revision'] if old else 0
        if revision != expected_revision:
            raise ResearchError(f'Graph revision conflict: expected {expected_revision}, current {revision}')
        snapshot = {'version': 1, 'project': project, 'revision': revision + 1, 'parent': old['snapshot'] if old else None,
                    'created': time.time(), 'actor': actor, 'reason': reason, 'graph': graph,
                    'scientific_verification': 'not_implied_by_memory_storage'}
        key = store.put(canonical(snapshot).encode('utf-8'))
        store.db.execute('INSERT INTO memory_versions VALUES(?,?,?)', (project, revision + 1, key))
        store.db.execute('INSERT INTO memory_graphs VALUES(?,?,?) ON CONFLICT(project) DO UPDATE SET revision=excluded.revision,snapshot=excluded.snapshot',
                         (project, revision + 1, key))
        store.db.execute('DELETE FROM memory_edges WHERE project=?', (project,))
        store.db.execute('DELETE FROM memory_nodes WHERE project=?', (project,))
        store.db.executemany('INSERT INTO memory_nodes VALUES(?,?,?)', [(project, n['id'], canonical(n)) for n in graph['nodes']])
        store.db.executemany('INSERT INTO memory_edges VALUES(?,?,?,?,?,?)',
                             [(project, e['id'], e['from'], e['to'], e['relation'], canonical(e)) for e in graph['edges']])
        store.event('memory:' + project, 'graph_committed', {'revision': revision + 1, 'snapshot': key, 'actor': actor, 'reason': reason})
    return {'project': project, 'revision': revision + 1, 'snapshot': key, 'nodes': len(graph['nodes']), 'edges': len(graph['edges'])}


def get(store, project, revision=None):
    valid_id(project)
    if revision is None:
        row = store.db.execute('SELECT snapshot FROM memory_graphs WHERE project=?', (project,)).fetchone()
    else:
        row = store.db.execute('SELECT snapshot FROM memory_versions WHERE project=? AND revision=?', (project, revision)).fetchone()
    if not row:
        raise ResearchError('Unknown research graph/revision')
    value = json.loads(store.blob(row['snapshot']))
    return {**value, 'snapshot': row['snapshot']}


def neighbors(store, project, identities, *, hops=1, direction='both', max_nodes=200, revision=None):
    if type(hops) is not int or not 0 <= hops <= 10 or type(max_nodes) is not int or not 1 <= max_nodes <= 5000:
        raise ResearchError('Use 0..10 hops and 1..5000 max_nodes')
    if direction not in {'in', 'out', 'both'}:
        raise ResearchError('direction must be in, out or both')
    snapshot = get(store, project, revision)
    graph = snapshot['graph']
    by_id = {n['id']: n for n in graph['nodes']}
    selected = set(identities)
    if not selected or not selected.issubset(by_id) or len(selected) > max_nodes:
        raise ResearchError('Unknown or too many seed nodes')
    truncated = False
    for _ in range(hops):
        candidates = set()
        for edge in graph['edges']:
            if direction in {'out', 'both'} and edge['from'] in selected: candidates.add(edge['to'])
            if direction in {'in', 'both'} and edge['to'] in selected: candidates.add(edge['from'])
        extra = sorted(candidates - selected)
        available = max_nodes - len(selected)
        truncated |= len(extra) > available
        selected.update(extra[:available])
        if not extra or truncated: break
    return {'project': project, 'revision': snapshot['revision'], 'snapshot': snapshot['snapshot'],
            'nodes': [by_id[k] for k in sorted(selected)],
            'edges': [e for e in graph['edges'] if e['from'] in selected and e['to'] in selected],
            'truncated': truncated, 'scientific_verification': False}


def search(store, project, query, *, limit=10, revision=None):
    if not isinstance(query, str) or not query.strip() or type(limit) is not int or not 1 <= limit <= 100:
        raise ResearchError('Search needs a nonempty query and 1..100 results')
    snapshot = get(store, project, revision)
    docs = [(n, Counter(tokenize(canonical(n)))) for n in snapshot['graph']['nodes']]
    terms = set(tokenize(query))
    average = sum(sum(c.values()) for _, c in docs) / max(1, len(docs)) or 1
    ranking = []
    for node, counts in docs:
        score = 0
        for term in terms:
            tf = counts[term]
            if tf:
                df = sum(term in c for _, c in docs)
                score += math.log(1 + (len(docs) - df + .5) / (df + .5)) * tf * 2.2 / (tf + 1.2 * (.25 + .75 * sum(counts.values()) / average))
        if score:
            ranking.append({'node': node, 'score': score})
    ranking.sort(key=lambda x: (-x['score'], x['node']['id']))
    return {'project': project, 'revision': snapshot['revision'], 'snapshot': snapshot['snapshot'], 'results': ranking[:limit],
            'mode': 'local_bm25', 'scientific_verification': False}


def invalidate_sources(store, project, source_ids, expected_revision, *, actor, reason):
    snapshot = get(store, project, expected_revision)
    result = invalidate(snapshot['graph'], source_ids, reason)
    return {**put(store, project, result['graph'], expected_revision, actor=actor, reason=reason),
            **{k: v for k, v in result.items() if k != 'graph'}}


def export(store, project, destination, revision=None):
    snapshot = get(store, project, revision)
    write_json(destination, snapshot)
    return {'path': str(destination), 'snapshot': snapshot['snapshot'], 'revision': snapshot['revision']}


def import_snapshot(store, snapshot, project, expected_revision, *, actor, reason):
    body = {k: v for k, v in snapshot.items() if k != 'snapshot'}
    if snapshot.get('snapshot') != fingerprint(body):
        raise ResearchError('Memory snapshot digest mismatch')
    return put(store, project, body['graph'], expected_revision, actor=actor, reason=reason)


def sync(store, project, config, revision=None):
    from .openviking import Client, projection
    snapshot = get(store, project, revision)
    client = Client(config)
    destination = client.identity
    key = snapshot['snapshot']
    with resource_lock(store, 'memory-sync', fingerprint([key, destination])):
        row = store.db.execute('SELECT body FROM memory_outbox WHERE snapshot=? AND destination=?', (key, destination)).fetchone()
        delivery = json.loads(row['body']) if row else {'snapshot': key, 'destination': destination, 'attempts': 0}
        delivery.update(status='pending', attempts=delivery['attempts'] + 1, updated=time.time())
        with store.tx():
            store.db.execute('INSERT INTO memory_outbox VALUES(?,?,?) ON CONFLICT(snapshot,destination) DO UPDATE SET body=excluded.body', (key, destination, canonical(delivery)))
            store.event('memory:' + project, 'memory_sync_started', delivery)
        try:
            receipt = client.publish(snapshot)
            delivery.update(status='synced', receipt=receipt)
            delivery.pop('error', None)
        except Exception as exc:
            delivery.update(status='pending', error={'type': type(exc).__name__, 'code': getattr(exc, 'code', 'transport_or_contract'),
                                                    'retry': 'explicit sync reconciles immutable URIs before writing'})
            # Do not persist service bodies or auth-bearing exception text.
        with store.tx():
            store.db.execute('UPDATE memory_outbox SET body=? WHERE snapshot=? AND destination=?', (canonical(delivery), key, destination))
            store.event('memory:' + project, 'memory_sync_settled', delivery)
        return delivery


def remote_search(store, project, config, query, limit=10, revision=None):
    from .openviking import Client, projection
    if not query.strip() or type(limit) is not int or not 1 <= limit <= 100:
        raise ResearchError('Search needs a query and 1..100 results')
    snapshot = get(store, project, revision)
    client = Client(config)
    root, files = projection(snapshot, client.namespace)
    client.verify_commit(root, files, snapshot)
    hits = client.find(query, root + '/nodes', limit)
    node_uris = {root + '/nodes/' + fingerprint(n['id']) + '.json': n for n in snapshot['graph']['nodes']}
    accepted, rejected = [], 0
    seen = set()
    for hit in hits:
        uri = hit.get('uri') if isinstance(hit, dict) else None
        # Never follow a server-provided path outside this exact project/revision.
        if uri not in node_uris or uri in seen:
            rejected += 1
            continue
        seen.add(uri)
        client.verify_text(uri, files[uri])
        accepted.append({'node': node_uris[uri], 'score': hit.get('score'), 'uri': uri})
    return {'results': accepted, 'rejected_hits': rejected, 'snapshot': snapshot['snapshot'], 'revision': snapshot['revision'],
            'mode': 'openviking', 'scientific_verification': False}
