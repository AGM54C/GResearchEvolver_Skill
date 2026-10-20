"""Evidence-bound teaching artifacts; structural grounding is not entailment."""
from .core import ResearchError, digest, fingerprint, safe_path


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ResearchError(label + ' must be nonempty text')
    return value


def validate(bundle, root, artifacts):
    if not isinstance(bundle, dict):
        raise ResearchError('Explanation must be an object')
    for key in ('topic', 'intuition', 'technical', 'relevance'):
        text(bundle.get(key), key)
    if bundle.get('audience') not in {'beginner', 'intermediate', 'expert'}:
        raise ResearchError('Choose beginner, intermediate or expert audience')
    for key in ('assumptions', 'limitations', 'questions'):
        if not isinstance(bundle.get(key), list) or not bundle[key]:
            raise ResearchError(key + ' needs at least one explicit entry')
        for value in bundle[key]: text(value, key)
    claims = bundle.get('claims')
    if not isinstance(claims, list) or not claims:
        raise ResearchError('Explanation needs explicit claims and their evidence status')
    seen, references = set(), []
    for claim in claims:
        if not isinstance(claim, dict): raise ResearchError('Invalid explanation claim')
        identity = text(claim.get('id'), 'claim.id')
        if identity in seen: raise ResearchError('Duplicate explanation claim')
        seen.add(identity)
        text(claim.get('text'), 'claim.text')
        if claim.get('status') not in {'source_reported', 'interpretation', 'hypothesis', 'unknown'}:
            raise ResearchError('Explicit claim evidence status required')
        citations = claim.get('citations', [])
        if not isinstance(citations, list) or (claim['status'] == 'source_reported' and not citations):
            raise ResearchError('Source-reported claims need exact citations')
        for citation in citations:
            if not isinstance(citation, dict): raise ResearchError('Invalid citation')
            path = text(citation.get('path'), 'citation.path')
            expected = artifacts.get(path)
            if not expected or citation.get('sha256') != expected:
                raise ResearchError('Citation must bind a recorded input/output hash')
            raw = safe_path(root, path).read_bytes()
            if digest(raw) != expected: raise ResearchError('Explanation source changed: ' + path)
            try: source = raw.decode('utf-8-sig')
            except UnicodeDecodeError as exc:
                raise ResearchError('Cite extracted UTF-8 source text, not a binary PDF') from exc
            start, end = citation.get('start'), citation.get('end')
            quote = text(citation.get('quote'), 'citation.quote')
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source) or source[start:end] != quote:
                raise ResearchError('Citation offsets must reproduce the exact source quote')
            references.append({'path': path, 'sha256': expected, 'start': start, 'end': end})
    return {'bundle': bundle, 'sha256': fingerprint(bundle), 'references': references,
            'grounding': 'exact source bytes and Unicode offsets checked; entailment requires review',
            'scientific_verification': False}


def markdown(bundle):
    lines = [f"### {bundle['topic']}", '', f"阅读深度：{bundle['audience']}", '',
             '**直观解释**', '', bundle['intuition'], '', '**方法与技术细节**', '', bundle['technical'], '',
             '**与当前研究的关系**', '', bundle['relevance']]
    for key, title in (('assumptions', '成立前提'), ('limitations', '边界与不确定性'), ('questions', '理解检查与待讨论问题')):
        lines.extend(['', '**' + title + '**', ''] + ['- ' + v for v in bundle[key]])
    lines.extend(['', '**论断及证据状态**', ''])
    for claim in bundle['claims']:
        lines.append('- ' + claim['id'] + ' [' + claim['status'] + '] ' + claim['text'])
        for citation in claim.get('citations', []):
            lines.append('  - ' + citation['path'] + f"，字符 {citation['start']}:{citation['end']}，SHA-256 `{citation['sha256']}`；原文：" + citation['quote'])
    return '\n'.join(lines)
