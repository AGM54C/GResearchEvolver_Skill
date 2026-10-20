"""Create editable SVG and draw.io diagrams from explicit nodes and typed edges."""
import argparse
import math
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from visual_artifacts import VisualError, finalize, load_spec, nonempty, number, output_bundle, references


def build(spec_path, destination):
    import fitz
    spec, sources, claims = load_spec(spec_path)
    width, height = spec.get('size', [1200, 700])
    number(width, 'width', 100, 4000); number(height, 'height', 100, 4000)
    nodes, edges = spec.get('nodes', []), spec.get('edges', [])
    if not 1 <= len(nodes) <= 100 or len(edges) > 300:
        raise VisualError('Use 1..100 nodes and at most 300 edges')
    by_id = {}
    for node in nodes:
        identity = nonempty(node.get('id'), 'node id')
        if identity in by_id or identity in {'0', '1'} or identity.startswith('edge-'):
            raise VisualError('Node IDs must be unique and not 0/1 or start with reserved edge-')
        nonempty(node.get('label'), 'node label'); references(node, claims)
        x, y, w, h = node['box']
        for value in (x, y, w, h):
            number(value, 'node coordinate', 0, 4000)
        if w <= 0 or h <= 0 or x + w > width or y + h > height:
            raise VisualError('Node outside canvas')
        by_id[identity] = node
    for i, left in enumerate(nodes):
        x, y, w, h = left['box']
        for right in nodes[i + 1:]:
            a, b, c, d = right['box']
            if min(x + w, a + c) > max(x, a) and min(y + h, b + d) > max(y, b):
                raise VisualError('Overlapping nodes; revise their boxes')
    for edge in edges:
        if edge.get('from') not in by_id or edge.get('to') not in by_id:
            raise VisualError('Dangling diagram edge')
        if edge['from'] == edge['to']:
            raise VisualError('Self loops need explicit custom routing')
        if edge.get('kind') not in {'flow', 'association', 'causal', 'planned'}:
            raise VisualError('Explicit edge kind required')
        nonempty(edge.get('label'), 'edge meaning'); references(edge, claims)
    svg = ET.Element('svg', xmlns='http://www.w3.org/2000/svg', width=str(width), height=str(height), viewBox=f'0 0 {width} {height}')
    ET.SubElement(svg, 'title').text = spec['purpose']
    ET.SubElement(svg, 'desc').text = spec.get('alt_text', spec['rationale'])
    ET.SubElement(svg, 'rect', width=str(width), height=str(height), fill='white')
    mxfile = ET.Element('mxfile', host='app.diagrams.net')
    diagram = ET.SubElement(mxfile, 'diagram', id='research', name='Research diagram')
    model = ET.SubElement(diagram, 'mxGraphModel', pageWidth=str(width), pageHeight=str(height))
    root = ET.SubElement(model, 'root')
    ET.SubElement(root, 'mxCell', id='0'); ET.SubElement(root, 'mxCell', id='1', parent='0')
    for index, edge in enumerate(edges):
        a, b = by_id[edge['from']]['box'], by_id[edge['to']]['box']
        horizontal = abs(b[0] - a[0]) >= abs(b[1] - a[1])
        if horizontal:
            forward = b[0] >= a[0]
            start = (a[0] + (a[2] if forward else 0), a[1] + a[3] / 2)
            end = (b[0] + (0 if forward else b[2]), b[1] + b[3] / 2)
        else:
            forward = b[1] >= a[1]
            start = (a[0] + a[2] / 2, a[1] + (a[3] if forward else 0))
            end = (b[0] + b[2] / 2, b[1] + (0 if forward else b[3]))
        attributes = {'x1': str(start[0]), 'y1': str(start[1]), 'x2': str(end[0]), 'y2': str(end[1]), 'stroke': '#435365', 'stroke-width': '2'}
        if edge['kind'] == 'planned': attributes['stroke-dasharray'] = '8 5'
        ET.SubElement(svg, 'line', attributes)
        # Explicit geometry survives converters that omit SVG marker-end.
        if edge['kind'] != 'association':
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            if length < 16:
                raise VisualError('Nodes need space for a visible arrow; adjust boxes')
            dx, dy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
            base = (end[0] - 12 * dx, end[1] - 12 * dy)
            points = [end, (base[0] - 5 * dy, base[1] + 5 * dx), (base[0] + 5 * dy, base[1] - 5 * dx)]
            ET.SubElement(svg, 'polygon', points=' '.join(f'{x},{y}' for x, y in points), fill='#435365')
        ET.SubElement(svg, 'text', x=str((start[0] + end[0]) / 2), y=str((start[1] + end[1]) / 2 - 10),
                      fill='#243247', **{'font-size': '15', 'text-anchor': 'middle'}).text = edge['label']
        style = 'html=0;endArrow=' + ('none' if edge['kind'] == 'association' else 'block') + ';dashed=' + ('1' if edge['kind'] == 'planned' else '0') + ';'
        cell = ET.SubElement(root, 'mxCell', id='edge-' + str(index), value=edge['label'], style=style, edge='1', parent='1', source=edge['from'], target=edge['to'])
        ET.SubElement(cell, 'mxGeometry', {'relative': '1', 'as': 'geometry'})
    for node in nodes:
        x, y, w, h = node['box']
        fill = node.get('fill', '#edf3f8')
        ET.SubElement(svg, 'rect', x=str(x), y=str(y), width=str(w), height=str(h), rx='12', fill=fill, stroke='#435365')
        lines = node['label'].split('\n')
        for index, line in enumerate(lines):
            ET.SubElement(svg, 'text', x=str(x + w / 2), y=str(y + h / 2 + (index - (len(lines) - 1) / 2) * 24 + 6),
                          fill='#172638', **{'font-size': '20', 'font-family': spec.get('font', 'sans-serif'), 'text-anchor': 'middle'}).text = line
        cell = ET.SubElement(root, 'mxCell', id=node['id'], value=node['label'], vertex='1', parent='1',
                             style='rounded=1;whiteSpace=wrap;html=0;fillColor=' + fill + ';fontSize=20;')
        ET.SubElement(cell, 'mxGeometry', {'x': str(x), 'y': str(y), 'width': str(w), 'height': str(h), 'as': 'geometry'})
    if spec['evidence_status'] == 'illustrative':
        ET.SubElement(svg, 'text', x='20', y='28', fill='#8a3c00', **{'font-size': '16'}).text = 'ILLUSTRATIVE DIAGRAM — NOT VALIDATED FINDINGS'
    raw = ET.tostring(svg, encoding='utf-8', xml_declaration=True)
    with output_bundle(destination) as out:
        (out / 'diagram.svg').write_bytes(raw)
        ET.ElementTree(mxfile).write(out / 'diagram.drawio', encoding='utf-8', xml_declaration=True)
        with fitz.open('svg', raw) as document:
            pdf = document.convert_to_pdf()
        (out / 'diagram.pdf').write_bytes(pdf)
        with fitz.open('pdf', pdf) as document:
            document[0].get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).save(out / 'diagram.png')
        return finalize(out, spec, sources, {'nodes': len(nodes), 'edges': len(edges), 'bounds': 'passed',
                        'node_overlap': 'none', 'edge_routing_and_labels': 'require visual review',
                        'preview_renderer': 'PyMuPDF SVG converter; fonts may be substituted',
                        'relation_semantics': 'require researcher review; types are declarations'}, builder=Path(__file__))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec'); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        build(args.spec, args.output)
    except (VisualError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + '\n')
