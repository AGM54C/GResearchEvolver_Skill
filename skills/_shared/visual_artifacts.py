"""Local, evidence-bound visual artifacts. No model calls or implicit approval."""
from contextlib import contextmanager
import copy
import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import shutil
import uuid


class VisualError(ValueError):
    pass


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    def invalid(value):
        raise VisualError('Nonfinite JSON value: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=invalid)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise VisualError(name + ' must be nonempty text')
    return value


def number(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise VisualError(name + ' must be a finite number')
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise VisualError(name + ' is outside the supported range')
    return value


def load_spec(path):
    path = Path(path).resolve()
    spec = read_json(path)
    if not isinstance(spec, dict) or spec.get('version') != 1:
        raise VisualError('Expected a version:1 visual specification')
    for field in ('purpose', 'audience', 'rationale'):
        nonempty(spec.get(field), field)
    if spec.get('evidence_status') not in {'research', 'illustrative'}:
        raise VisualError('Declare evidence_status as research or illustrative')
    sources = {}
    if not isinstance(spec.get('sources'), list) or not spec['sources']:
        raise VisualError('Declare source files with SHA-256 hashes')
    for source in spec['sources']:
        identity = nonempty(source.get('id'), 'source id')
        if identity in sources:
            raise VisualError('Duplicate source id: ' + identity)
        source_path = (path.parent / nonempty(source.get('path'), 'source path')).resolve()
        if not source_path.is_file() or sha256(source_path) != source.get('sha256'):
            raise VisualError('Missing or changed source: ' + identity)
        sources[identity] = {**source, 'resolved_path': source_path}
    claims = {}
    for claim in spec.get('claims', []):
        identity = nonempty(claim.get('id'), 'claim id')
        if identity in claims:
            raise VisualError('Duplicate claim id')
        nonempty(claim.get('text'), 'claim text')
        if claim.get('status') not in {'source_reported', 'interpretation', 'hypothesis', 'unknown', 'illustrative'}:
            raise VisualError('Unknown claim status')
        if claim['status'] == 'source_reported' and not claim.get('evidence'):
            raise VisualError('Source-reported claims need evidence locators')
        for evidence in claim.get('evidence', []):
            if evidence.get('source') not in sources:
                raise VisualError('Unknown evidence source')
            nonempty(evidence.get('locator'), 'evidence locator')
            if 'quote' in evidence:
                raw = sources[evidence['source']]['resolved_path'].read_text(encoding='utf-8-sig')
                start, end = evidence.get('start'), evidence.get('end')
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(raw) or raw[start:end] != evidence['quote']:
                    raise VisualError('Exact evidence quote does not match source')
        claims[identity] = claim
    return spec, sources, claims


def references(item, claims):
    values = item.get('claims', [])
    if not isinstance(values, list) or any(v not in claims for v in values):
        raise VisualError('Unknown claim reference')
    return values


def source_path(sources, identity):
    if identity not in sources:
        raise VisualError('Unknown source: ' + str(identity))
    return sources[identity]['resolved_path']


def table(sources, identity):
    with source_path(sources, identity).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise VisualError('CSV needs unique column names')
        rows = list(reader)
    if not rows or len(rows) > 1000000:
        raise VisualError('CSV needs 1..1000000 rows')
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise VisualError('CSV row width differs from its header')
    return rows


def column(rows, key, *, numeric=True):
    if key not in rows[0]:
        raise VisualError('Unknown CSV column: ' + str(key))
    values = []
    for row in rows:
        raw = row[key]
        if not numeric:
            values.append(raw)
        elif raw.strip().lower() in {'', 'na', 'nan', 'null'}:
            values.append(float('nan'))
        else:
            try:
                value = float(raw)
            except ValueError as exc:
                raise VisualError('Nonnumeric value in ' + key) from exc
            if not math.isfinite(value):
                raise VisualError('Infinite value in ' + key)
            values.append(value)
    return values


@contextmanager
def output_bundle(destination):
    """Publish a complete new directory; never overwrite a previous revision."""
    destination = Path(destination).resolve()
    if destination.exists():
        raise VisualError('Use a new output directory for each revision')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Inherit the output parent's permissions. Python 3.13 mkdtemp on Windows
    # uses a private DACL that can make the published bundle unreadable to
    # other intended tools running with the parent's access rights.
    temporary = destination.parent / ('.visual-build-' + uuid.uuid4().hex)
    temporary.mkdir()
    try:
        yield temporary
        if destination.exists():
            raise VisualError('Output appeared during build')
        # Windows rename refuses existing destinations; parent must be cooperative.
        temporary.rename(destination)
    finally:
        if temporary.exists():
            if temporary.resolve().parent != destination.parent or not temporary.name.startswith('.visual-build-'):
                raise VisualError('Unexpected temporary directory')
            shutil.rmtree(temporary)


def finalize(directory, spec, sources, checks, *, builder, extra=None):
    # Keep a portable, source-bound rebuild spec instead of dangling paths to
    # the original machine. Never copy fonts or other licensed dependencies.
    portable_spec = copy.deepcopy(spec)
    (directory / 'inputs').mkdir()
    for index, entry in enumerate(portable_spec['sources']):
        source = sources[entry['id']]
        relative = 'inputs/input-' + str(index).zfill(3) + source['resolved_path'].suffix
        copied = directory / relative
        shutil.copyfile(source['resolved_path'], copied)
        if sha256(copied) != source['sha256']:
            raise VisualError('Source changed while copying: ' + entry['id'])
        entry['path'] = relative
    for identity, source in sources.items():
        if sha256(source['resolved_path']) != source['sha256']:
            raise VisualError('Source changed during build: ' + identity)
    write_json(directory / 'spec.json', portable_spec)
    versions = {}
    for distribution in ('matplotlib', 'python-pptx', 'Pillow', 'PyMuPDF'):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            pass
    font_record = None
    if checks.get('font'):
        from matplotlib import font_manager
        font_path = Path(font_manager.findfont(checks['font'], fallback_to_default=False))
        font_record = {'family': checks['font'], 'file': font_path.name, 'sha256': sha256(font_path)}
    record = {'version': 1, 'builder': str(builder.name), 'builder_sha256': sha256(builder),
              'shared_sha256': sha256(Path(__file__)), 'packages': versions,
              'python': platform.python_version(), 'platform': platform.platform(), 'font': font_record,
              'evidence_status': spec['evidence_status'], 'purpose': spec['purpose'],
              'sources': portable_spec['sources'],
              'checks': checks, 'human_review': 'pending', 'scientific_validity': 'not_established_by_build',
              **(extra or {})}
    lines = ['# Visual artifact report', '', spec['purpose'], '', '## Why', '', spec['rationale'], '',
             '## What was built and checked', '', '```json', json.dumps(checks, ensure_ascii=False, indent=2), '```', '',
             '## Researcher decisions', '', '- Does the framing express the intended scientific question?',
             '- Are the claims, alternatives, uncertainty and limitations represented accurately?',
             '- Is the selected visual encoding and information density appropriate for this audience?',
             '- What should be revised, explained, retained or stopped?', '',
             'Human review: pending. No approval was generated. File checks do not establish scientific correctness.',
             'Use the managed stage report and stage-feedback for review, branching and adoption.', '',
             '## Rebuild', '',
             'spec.json binds copies in inputs/; run the recorded builder against this spec with a new output directory.',
             'Use the recorded code and dependency versions; fonts are identified by hash and are not redistributed.',
             'This package contains copies of supplied sources. Review them before sharing the package.', '']
    (directory / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    record['outputs'] = {p.relative_to(directory).as_posix(): sha256(p) for p in directory.rglob('*') if p.is_file()}
    write_json(directory / 'artifact-manifest.json', record)
    write_json(directory / 'report.json', record)
    return record


def font_for(text, requested=None):
    from matplotlib import font_manager, ft2font
    names = [requested] if requested else ['Microsoft YaHei', 'Noto Sans CJK SC', 'Source Han Sans SC', 'DejaVu Sans']
    needed = {ord(c) for c in text if not c.isspace()}
    for name in names:
        try:
            path = font_manager.findfont(name, fallback_to_default=False)
            if needed.issubset(ft2font.FT2Font(path).get_charmap()):
                return name
        except (ValueError, RuntimeError):
            continue
    raise VisualError('No installed font covers the requested labels; specify an appropriate font')


def preview_pdf(pdf, destination):
    """Render every page and a contact sheet; never call this PPTX rendering."""
    import fitz
    from PIL import Image, ImageDraw
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    with fitz.open(pdf) as document:
        if not 1 <= len(document) <= 200:
            raise VisualError('Preview supports 1..200 pages')
        tiles = []
        for index, page in enumerate(document):
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            pix.save(destination / f'page-{index + 1:03d}.png')
            tile = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            tile.thumbnail((480, 280))
            cell = Image.new('RGB', (500, 315), 'white')
            cell.paste(tile, ((500 - tile.width) // 2, 25))
            ImageDraw.Draw(cell).text((10, 5), str(index + 1), fill='black')
            tiles.append(cell)
        # Separate sheets bound memory use for long decks.
        for start in range(0, len(tiles), 12):
            part = tiles[start:start + 12]
            sheet = Image.new('RGB', (1000, 315 * math.ceil(len(part) / 2)), '#dddddd')
            for index, tile in enumerate(part):
                sheet.paste(tile, ((index % 2) * 500, (index // 2) * 315))
            sheet.save(destination / f'contact-{start // 12 + 1:02d}.png')
    return {'pages': len(tiles), 'source_sha256': sha256(pdf)}
