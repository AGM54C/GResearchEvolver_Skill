"""Small auditable statistics, with the sampling unit and assumptions in every result."""
from __future__ import annotations

import math
import random
from statistics import mean, stdev, NormalDist

from .core import ResearchError, finite, fingerprint


def quantile(values, probability):
    values = sorted(values)
    x = (len(values) - 1) * probability
    lo, hi = math.floor(x), math.ceil(x)
    return values[lo] + (values[hi] - values[lo]) * (x - lo)


def paired_analysis(rows, *, alpha=0.05, resamples=4000, seed=0, direction='higher'):
    """Equal-weight task means; seeds are nested repetitions, not independent tasks."""
    if not 0 < finite(alpha) < 1 or not isinstance(resamples, int) or resamples < 200:
        raise ResearchError('Require 0 < alpha < 1 and at least 200 resamples')
    if direction not in {'higher', 'lower'}:
        raise ResearchError('direction must be higher or lower')
    groups, pairs = {}, set()
    for row in rows:
        task, repetition = str(row['task']), str(row['seed'])
        if (task, repetition) in pairs:
            raise ResearchError('Duplicate task/seed pairing')
        pairs.add((task, repetition))
        a, b = finite(row['candidate']), finite(row['incumbent'])
        groups.setdefault(task, []).append((a - b) * (1 if direction == 'higher' else -1))
    if len(groups) < 3:
        raise ResearchError('At least 3 independent tasks/groups required; describe smaller samples without a promotion CI')
    differences = [mean(v) for _, v in sorted(groups.items())]
    rng = random.Random(seed)
    draws = [mean(rng.choices(differences, k=len(differences))) for _ in range(resamples)]
    sd = stdev(differences)
    return {'mean_gain': mean(differences), 'ci': [quantile(draws, alpha / 2), quantile(draws, 1 - alpha / 2)],
            'alpha': alpha, 'method': 'paired percentile bootstrap of equal-weight task means',
            'tasks': len(groups), 'pairs': len(pairs), 'standardized_paired_effect': mean(differences) / sd if sd else None,
            'task_gains': {k: mean(v) for k, v in groups.items()}, 'direction': direction,
            'resamples': resamples, 'seed': seed, 'input_hash': fingerprint(rows),
            'assumptions': 'tasks are independent sampling units; small samples and reused selection tasks weaken CI validity'}


def adjust_pvalues(values, method='holm'):
    if not values or any(not 0 <= finite(p) <= 1 for p in values):
        raise ResearchError('Require nonempty p-values in [0,1]')
    if method not in {'holm', 'bh'}:
        raise ResearchError('Supported corrections: holm, bh')
    n = len(values)
    order = sorted(range(n), key=values.__getitem__)
    adjusted = [0.0] * n
    if method == 'holm':
        current = 0
        for rank, i in enumerate(order):
            current = max(current, min(1, (n - rank) * values[i]))
            adjusted[i] = current
    else:
        current = 1
        for rank in range(n - 1, -1, -1):
            i = order[rank]
            current = min(current, values[i] * n / (rank + 1))
            adjusted[i] = current
    return {'method': method, 'adjusted': adjusted,
            'assumptions': 'valid p-values; BH needs independence or suitable positive dependence; Holm controls FWER'}


def meta_analysis(data):
    rows = data['studies']
    if len(rows) < 2 or not data.get('common_estimand') or data.get('independent_units_confirmed') is not True:
        raise ResearchError('Meta-analysis needs >=2 independent studies and an explicit common estimand')
    ids = [r['study_id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ResearchError('Repeated study: combine dependent reports before pooling')
    y = [finite(r['effect']) for r in rows]
    v = [finite(r['variance'], 'variance', 1e-15) for r in rows]
    weights = [1 / x for x in v]
    def pool(w):
        estimate = sum(a * b for a, b in zip(w, y)) / sum(w)
        se = math.sqrt(1 / sum(w))
        return {'estimate': estimate, 'se': se, 'ci': [estimate - 1.95996398454 * se, estimate + 1.95996398454 * se]}
    fixed = pool(weights)
    q = sum(w * (e - fixed['estimate']) ** 2 for w, e in zip(weights, y))
    df = len(rows) - 1
    c = sum(weights) - sum(w * w for w in weights) / sum(weights)
    tau = max(0, (q - df) / c)
    return {'estimand': data['common_estimand'], 'fixed': fixed, 'random_DL': pool([1 / (x + tau) for x in v]),
            'Q': q, 'I2_percent': max(0, (q - df) / q) * 100 if q else 0, 'tau2': tau, 'studies': len(rows),
            'limitations': 'Normal approximation and DerSimonian-Laird; few studies, dependence, publication bias and risk of bias require expert sensitivity analysis. Log effects remain on log scale.'}


def sequential_evidence(data):
    """Accumulate supplied valid conditional e-values; never manufacture validity."""
    if not data.get('null') or not data.get('design_hash') or not data.get('validity_review'):
        raise ResearchError('Provide null, frozen design hash, and independent validity review')
    alpha = finite(data.get('alpha', .05))
    if not 0 < alpha < 1:
        raise ResearchError('Invalid alpha')
    loge, history, used = 0.0, [], set()
    for row in data.get('tests', []):
        if not all(row.get(k) for k in ('subnull', 'null_implies_subnull', 'conditional_validity', 'data_use')):
            raise ResearchError('Each test needs implication, conditional validity and data-use justification')
        identifier = row['id']
        if identifier in used:
            raise ResearchError('Repeated test ID')
        used.add(identifier)
        e = finite(row['e_value'], 'e_value', 0)
        loge = -math.inf if e == 0 or loge == -math.inf else loge + math.log(e)
        history.append({'id': identifier, 'log_e': None if loge == -math.inf else loge, 'crossed': loge >= -math.log(alpha)})
    if not history:
        raise ResearchError('No executed tests')
    return {'history': history, 'reject_under_declared_assumptions': any(x['crossed'] for x in history),
            'threshold': 1 / alpha, 'validity': 'conditional on supplied mathematical and data-use justifications; not mechanically proved',
            'scope': 'per-hypothesis type-I control if conditions hold; neither truth nor family FDR is established'}


def data_audit(data):
    rows, target = data['rows'], data.get('target')
    if not rows:
        raise ResearchError('Empty dataset')
    columns = sorted({k for r in rows for k in r})
    stats = {}
    for c in columns:
        values = [r.get(c) for r in rows]
        nonmissing = [x for x in values if x is not None and x != '']
        numeric = [x for x in nonmissing if isinstance(x, (int, float)) and not isinstance(x, bool)]
        for x in numeric: finite(x, c)
        stats[c] = {'missing': len(rows) - len(nonmissing), 'unique': len({str(x) for x in nonmissing}),
                    'constant': bool(nonmissing) and len({str(x) for x in nonmissing}) == 1}
        if numeric and len(numeric) == len(nonmissing):
            stats[c].update(min=min(numeric), max=max(numeric), mean=mean(numeric))
    hashes = [fingerprint(r) for r in rows]
    leaks = []
    if target:
        for c in columns:
            if c != target and all(r.get(c) == r.get(target) for r in rows): leaks.append({'column': c, 'reason': 'identical to target'})
    split, group = data.get('split_column'), data.get('group_column')
    if split and group:
        groups = {}
        for r in rows: groups.setdefault(str(r.get(group)), set()).add(str(r.get(split)))
        leaks += [{'group': k, 'reason': 'crosses splits', 'splits': sorted(v)} for k, v in groups.items() if len(v) > 1]
    return {'rows': len(rows), 'columns': stats, 'duplicate_rows': len(rows) - len(set(hashes)),
            'leakage_flags': leaks, 'limitations': 'screening only; causal, temporal and preprocessing leakage need domain review'}
