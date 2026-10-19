"""Systematic-review decisions and evidence quality records, without simulated experts."""
from __future__ import annotations

from .core import ResearchError, fingerprint


def freeze_review(store, name, protocol):
    required = ('question', 'eligibility', 'databases', 'searches', 'outcomes', 'reviewers')
    if any(not protocol.get(k) for k in required):
        raise ResearchError('Review protocol needs question, eligibility, databases, searches, outcomes and reviewers')
    if len(set(protocol['reviewers'])) < 2:
        raise ResearchError('At least two independently acting reviewer identities are needed')
    with store.tx():
        if store.get_value('review:' + name): raise ResearchError('Protocol frozen; amendments need a new ID and parent/reason')
        result = {'protocol': protocol, 'hash': fingerprint(protocol), 'decisions': [], 'adjudications': []}
        store.set_value('review:' + name, result)
        store.event('review-' + name, 'protocol_frozen', {'hash': result['hash'], 'protocol': protocol})
    return result


def screen(store, name, decisions):
    with store.tx():
        record = store.get_value('review:' + name)
        if not record: raise ResearchError('Unknown review')
        if fingerprint(record['protocol']) != record['hash']: raise ResearchError('Protocol mutated')
        keys = {(d['record'], d['stage'], d['reviewer']) for d in record['decisions']}
        for d in decisions:
            key = (d['record'], d['stage'], d['reviewer'])
            if key in keys: raise ResearchError('Do not overwrite screening; amend with a new protocol/version')
            if d['stage'] not in {'title_abstract', 'full_text'} or d['decision'] not in {'include', 'exclude', 'uncertain', 'unavailable'}:
                raise ResearchError('Invalid stage/decision')
            if d['reviewer'] not in record['protocol']['reviewers']:
                raise ResearchError('Reviewer not registered')
            if d.get('independently_assessed') is not True:
                raise ResearchError('Record independent assessment; copying another reviewer is not independent')
            if d['decision'] == 'exclude' and not d.get('reason'):
                raise ResearchError('Exclusion reason required')
            if d['stage'] == 'full_text' and d['decision'] != 'unavailable' and not d.get('source_locator'):
                raise ResearchError('Full-text decision needs source locator')
            keys.add(key)
        record['decisions'].extend(decisions)
        store.set_value('review:' + name, record)
        store.event('review-' + name, 'screening', decisions)
    return record


def adjudicate(store, name, decisions):
    with store.tx():
        record = store.get_value('review:' + name)
        if not record: raise ResearchError('Unknown review')
        existing = {(d['record'], d['stage']) for d in record['adjudications']}
        for d in decisions:
            key = (d['record'], d['stage'])
            pair = [x for x in record['decisions'] if (x['record'], x['stage']) == key]
            if len({x['reviewer'] for x in pair}) < 2: raise ResearchError('Two assessments required before adjudication')
            if d.get('reviewer') in {x['reviewer'] for x in pair}: raise ResearchError('Use a third adjudicator or a named consensus meeting')
            if key in existing or not d.get('reason') or not d.get('reviewer'):
                raise ResearchError('Duplicate adjudication or missing adjudicator/reason')
            if d.get('decision') not in {'include', 'exclude', 'uncertain', 'unavailable'}:
                raise ResearchError('Invalid adjudication')
            existing.add(key)
        record['adjudications'].extend(decisions)
        store.set_value('review:' + name, record)
        store.event('review-' + name, 'adjudication', decisions)
    return record


def review_report(store, name, inventory):
    record = store.get_value('review:' + name)
    if not record: raise ResearchError('Unknown review')
    records = inventory['records']
    ids = [r['id'] for r in records]
    if len(ids) != len(set(ids)): raise ResearchError('Inventory contains duplicate IDs')
    if {d['record'] for d in record['decisions']} - set(ids):
        raise ResearchError('Inventory omits previously screened records')
    decisions, conflicts = {}, []
    adj = {(d['record'], d['stage']): d for d in record['adjudications']}
    for rid in ids:
        for stage in ('title_abstract', 'full_text'):
            pair = [d for d in record['decisions'] if d['record'] == rid and d['stage'] == stage]
            outcomes = {d['decision'] for d in pair}
            if (rid, stage) in adj: outcome = adj[rid, stage]['decision']
            elif len(pair) >= 2 and len(outcomes) == 1: outcome = next(iter(outcomes))
            else:
                outcome = 'pending'
                if len(pair) >= 2: conflicts.append({'record': rid, 'stage': stage, 'decisions': pair})
            decisions[rid, stage] = outcome
    included_reports = [r for r in records if decisions[r['id'], 'title_abstract'] == 'include' and decisions[r['id'], 'full_text'] == 'include']
    if any(not r.get('study_id') for r in included_reports): raise ResearchError('Included reports require study_id to avoid report/study double counting')
    full_sought = [r for r in records if decisions[r['id'], 'title_abstract'] == 'include']
    counts = {'identified': inventory.get('identified', len(records)), 'duplicates_removed': inventory.get('duplicates_removed', 0),
              'records_screened': len(records), 'title_abstract_excluded': sum(decisions[r, 'title_abstract'] == 'exclude' for r in ids),
              'title_abstract_pending': sum(decisions[r, 'title_abstract'] in {'pending', 'uncertain', 'unavailable'} for r in ids),
              'reports_sought': len(full_sought),
              'reports_unavailable': sum(decisions[r['id'], 'full_text'] == 'unavailable' for r in full_sought),
              'full_text_excluded': sum(decisions[r['id'], 'full_text'] == 'exclude' for r in full_sought),
              'full_text_pending': sum(decisions[r['id'], 'full_text'] in {'pending', 'uncertain'} for r in full_sought),
              'reports_included': len(included_reports), 'studies_included': len({r['study_id'] for r in included_reports})}
    accounting = counts['identified'] - counts['duplicates_removed'] == counts['records_screened']
    return {'protocol_hash': record['hash'], 'counts': counts, 'accounting_valid': accounting, 'conflicts': conflicts,
            'included': included_reports, 'decisions': [{'record': k[0], 'stage': k[1], 'decision': v} for k, v in decisions.items()],
            'ready_for_synthesis': accounting and not conflicts and not counts['title_abstract_pending'] and not counts['full_text_pending'],
            'unavailable_is_excluded': False, 'independence': 'reviewer declarations recorded, identity separation alone does not prove independent reasoning'}


def assess_quality(data):
    problems = []
    for study in data.get('studies', []):
        if not study.get('tool') or not study.get('reviewer') or not study.get('domains'):
            problems.append(study.get('study_id', '?') + ': missing tool/reviewer/domains')
        for domain in study.get('domains', []):
            if domain.get('judgment') not in {'low', 'some_concerns', 'high', 'unclear', 'not_applicable'} or not domain.get('rationale'):
                problems.append('missing justified risk-of-bias judgment')
            if domain.get('judgment') != 'not_applicable' and not domain.get('evidence'):
                problems.append('judgment needs source evidence')
    for outcome in data.get('outcomes', []):
        required = {'risk_of_bias', 'inconsistency', 'indirectness', 'imprecision', 'publication_bias'}
        if not required.issubset(outcome.get('grade_domains', {})):
            problems.append('GRADE domain record incomplete')
        if not outcome.get('reviewer') or not outcome.get('rationale'):
            problems.append('GRADE requires a reviewer and rationale')
    return {'record_complete': bool(data.get('studies')) and not problems, 'problems': problems,
            'clinical_or_domain_expertise_verified': False, 'certainty_automatically_inferred': False}


def intervention_assessment(data):
    """DoVer/AGDebugger-inspired causal discipline, including agent noncompliance."""
    if data.get('followed') is not True:
        return {'classification': 'Inconclusive', 'reason': 'intervention not followed or fidelity unverified'}
    if not data.get('matched_controls') or data.get('repetitions', 0) < 2 or not data.get('external_state_comparable'):
        return {'classification': 'Inconclusive', 'reason': 'need repeated matched controls and comparable external state'}
    contracts = data.get('measurement_contracts', {})
    control, intervention = contracts.get('control', {}), contracts.get('intervention', {})
    required = ('estimand', 'metric', 'unit', 'analysis_unit', 'evaluation_data_hash')
    if any(not control.get(k) or not intervention.get(k) for k in required):
        return {'classification': 'Inconclusive', 'reason': 'measurement comparability not established; provide both frozen measurement contracts'}
    changed = [k for k in required if control[k] != intervention[k]]
    if changed:
        return {'classification': 'Inconclusive', 'reason': 'measurement target or evaluation population changed; numbers do not establish intervention improvement', 'changed_measurement_fields': changed}
    if not data.get('milestones'):
        raise ResearchError('Declare scientific milestones, not skill-call counts')
    from .statistics import paired_analysis
    result = paired_analysis(data['pairs'], direction=data.get('direction', 'higher'))
    if result['ci'][0] > data.get('minimum_gain', 0): outcome = 'Validated'
    elif result['ci'][1] <= 0: outcome = 'Refuted'
    elif result['mean_gain'] > 0: outcome = 'Partially Validated'
    else: outcome = 'Inconclusive'
    return {'classification': outcome, 'analysis': result,
            'progress': sum(bool(m.get('achieved')) for m in data['milestones']) / len(data['milestones']),
            'measurement_contract': control,
            'scope': 'local intervention result conditional on accurate comparability declarations; not universal root-cause proof or independent validation of measurement semantics'}
