"""Declared scientific dependencies and scoped invalidation, not a truth oracle.

Edges point from prerequisite to consumer. Independent support must be declared
as alternative support_sets; multiple supporting edges alone do not imply it.
Scientific checks are application-specific; cascading rollback uses the copied
upstream MemTX manager. Design references are documented in
docs/long-horizon/01-design/report.md.
"""
from __future__ import annotations

import copy

from .core import ResearchError, canonical, fingerprint


NON_DEPENDENCIES = frozenset({'related_to', 'same_topic', 'cites', 'motivates', 'supersedes'})
UNUSABLE = frozenset({'needs_review', 'stale', 'retracted', 'revoked', 'refuted', 'superseded',
                      'quarantined', 'contested', 'draft', 'tentative', 'proposed'})
USABLE = frozenset({'current', 'active', 'supported', 'validated', 'verified', 'committed'})


def structure(graph):
    if not isinstance(graph, dict) or not isinstance(graph.get('nodes'), list) or not isinstance(graph.get('edges'), list):
        raise ResearchError('Expected graph nodes/edges')
    nodes = {n['id']: n for n in graph['nodes']}
    if len(nodes) != len(graph['nodes']): raise ResearchError('Duplicate graph nodes')
    incoming = {identity: [] for identity in nodes}
    for edge in graph['edges']:
        if edge.get('from') not in nodes or edge.get('to') not in nodes or not isinstance(edge.get('relation'), str):
            raise ResearchError('Invalid dependency edge')
        if edge['relation'] not in NON_DEPENDENCIES:
            incoming[edge['to']].append(edge)
    for node in nodes.values():
        if 'support_sets' not in node: continue
        groups = node['support_sets']
        supporters = {e['from'] for e in incoming[node['id']] if e['relation'] == 'supports'}
        if (not isinstance(groups, list) or not groups or len(groups) > 100
                or any(not isinstance(g, list) or not g or any(not isinstance(i, str) or i not in supporters for i in g) for g in groups)
                or set(i for g in groups for i in g) != supporters):
            raise ResearchError('support_sets must cover exactly the explicit supporting nodes')
    return nodes, incoming


def invalidate(graph, identities, reason):
    if not isinstance(reason, str) or not reason.strip(): raise ResearchError('Invalidation requires reason')
    graph = copy.deepcopy(graph)
    nodes, incoming = structure(graph)
    affected = set(identities)
    if not affected or not affected.issubset(nodes): raise ResearchError('Unknown or empty source IDs')
    original = set(affected)
    from .memtx import invoke
    upstream = invoke('cascade_graph', {'graph': graph, 'sources': sorted(original), 'reason': reason})
    affected = set(upstream['result']['affected'])
    preserved = []
    for identity, node in nodes.items():
        if identity in affected:
            node.setdefault('previous_status', node.get('status'))
            node.update(status='needs_review', invalidation_reason=reason)
        elif any(e['from'] in affected for e in incoming[identity]):
            node['support_changed'] = {'sources': sorted(affected & {e['from'] for e in incoming[identity]}),
                                       'reason': reason, 'scope_review_required': True}
            preserved.append(identity)
    for edge in graph['edges']:
        if edge['from'] in affected or edge['to'] in affected:
            if edge['relation'] in NON_DEPENDENCIES: continue
            if 'adjudication' in edge: edge['previous_adjudication'] = edge.pop('adjudication')
            edge['status'] = 'needs_review'
    return {'graph': graph, 'affected': sorted(affected), 'preserved_with_other_support': sorted(preserved),
            'sources': sorted(original), 'reason': reason, 'artifacts_deleted': False,
            'memtx_commit': upstream['upstream_commit'], 'memtx_receipts': upstream['result']['receipts'],
            'scope': 'declared dependencies only; preservation does not establish truth or source independence'}


def check(graph, requirements, *, conditions=None):
    """Check ALL declared required nodes and a valid support path for each.

requirements maps node IDs to exact fingerprints. Conditions map condition IDs
to the actual values used by the action. Unknown status, cycles and version
mismatches fail closed. Alternative paths use fresh, compatible evidence only.
"""
    if not isinstance(requirements, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in requirements.items()):
        raise ResearchError('requires must map node IDs to exact fingerprints')
    conditions = conditions or {}
    if not isinstance(conditions, dict): raise ResearchError('conditions must be an object')
    nodes, incoming = structure(graph)
    cache, visiting = {}, set()

    def visit(identity):
        if identity in cache: return cache[identity]
        if identity in visiting: return False, {identity}, ['dependency cycle: ' + identity]
        if identity not in nodes: return False, set(), ['missing node: ' + identity]
        visiting.add(identity)
        node = nodes[identity]
        used, errors = {identity}, []
        if node.get('status') not in USABLE: errors.append('unusable status: ' + identity)
        if node.get('type') == 'condition':
            if identity not in conditions or canonical(node.get('value')) != canonical(conditions[identity]):
                errors.append('condition missing/mismatched: ' + identity)
        for condition, value in node.get('conditions', {}).items():
            if condition not in conditions or canonical(conditions[condition]) != canonical(value):
                errors.append('scope mismatch: ' + identity + ':' + condition)
        groups = node.get('support_sets')
        edges = incoming[identity]

        def consume(edge):
            parent = nodes[edge['from']]
            ok, closure, failures = visit(edge['from'])
            failures = list(failures)
            edge_id = edge.get('id', edge['from'] + '->' + edge['to'])
            if edge.get('status') in UNUSABLE: failures.append('unusable edge: ' + edge_id)
            if 'expected_version' in edge and parent.get('version') != edge['expected_version']:
                failures.append('version mismatch: ' + edge_id)
            if edge.get('expected_sha256') and parent.get('sha256') != edge['expected_sha256']:
                failures.append('content mismatch: ' + edge_id)
            return not failures and ok, closure, failures

        for edge in edges:
            if groups and edge['relation'] == 'supports': continue
            ok, closure, failures = consume(edge)
            used.update(closure); errors.extend(failures)
        if groups:
            alternatives = []
            for group in groups:
                group_used, group_errors = set(), []
                for edge in edges:
                    if edge['relation'] == 'supports' and edge['from'] in group:
                        ok, closure, failures = consume(edge)
                        group_used.update(closure); group_errors.extend(failures)
                if not group_errors: alternatives.append(group_used)
            if not alternatives: errors.append('no valid support set: ' + identity)
            else: used.update(min(alternatives, key=lambda group: (len(group), sorted(group))))
        visiting.remove(identity)
        cache[identity] = (not errors, used, errors)
        return cache[identity]

    used, errors = set(), []
    for identity, expected in requirements.items():
        if identity not in nodes or fingerprint(nodes[identity]) != expected:
            errors.append('node changed/missing: ' + identity)
        ok, closure, failures = visit(identity)
        used.update(closure); errors.extend(failures)
    return {'eligible': not errors, 'errors': sorted(set(errors)), 'nodes': sorted(used),
            'pins': {i: fingerprint(nodes[i]) for i in sorted(used) if i in nodes},
            'scientific_truth_proven': False, 'scope': 'declared premises and conditions; omitted dependencies need scientific review'}
