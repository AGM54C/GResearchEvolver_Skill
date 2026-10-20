"""Render explicit CSV values; no implicit statistics, interpolation or model calls."""
import argparse
import math
from pathlib import Path
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '_shared'))
from visual_artifacts import (VisualError, column, finalize, font_for, load_spec,
                              nonempty, number, output_bundle, references, table)

PALETTE = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#555555', '#AA7700']


def clipped_text(fig, renderer):
    """Check drawn labels, excluding locator ticks outside the visible interval."""
    from matplotlib.text import Text
    excluded = set()
    for ax in fig.axes:
        if not ax.get_visible():
            excluded.update(ax.findobj(Text))
            continue
        for axis in (ax.xaxis, ax.yaxis):
            low, high = sorted(axis.get_view_interval())
            tolerance = (high - low) * 1e-10
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                if not axis.get_visible() or not low - tolerance <= tick.get_loc() <= high + tolerance:
                    excluded.update((tick.label1, tick.label2))
    return [artist.get_text() for artist in fig.findobj(Text)
            if artist not in excluded and artist.get_visible() and artist.get_text()
            and not all(fig.bbox.contains(*point) for point in artist.get_window_extent(renderer).get_points())]


def build(spec_path, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    spec, sources, claims = load_spec(spec_path)
    panels = spec.get('panels', [])
    if not 1 <= len(panels) <= 16:
        raise VisualError('Provide 1..16 panels')
    for panel in panels:
        references(panel, claims)
        for field in ('title', 'xlabel', 'ylabel'):
            nonempty(panel.get(field), field)
    width, height = spec.get('size_mm', [180, 110])
    number(width, 'width', 30, 600); number(height, 'height', 30, 600)
    dpi = number(spec.get('dpi', 300), 'dpi', 72, 1200)
    if width * height / 25.4 ** 2 * dpi ** 2 > 60000000:
        raise VisualError('Raster output would exceed 60 million pixels')
    formats = spec.get('formats', ['png', 'pdf', 'svg'])
    if not isinstance(formats, list) or not formats or set(formats) - {'png', 'pdf', 'svg', 'tiff'}:
        raise VisualError('Supported formats: png, pdf, svg, tiff')
    columns = spec.get('columns', min(2, len(panels)))
    if type(columns) is not int or not 1 <= columns <= 4:
        raise VisualError('columns must be 1..4')
    label_text = spec.get('caption', '') + ' '.join(str(p) for p in panels)
    font = font_for(label_text, spec.get('font'))
    panel_facts = []
    with plt.rc_context({'font.family': font, 'font.size': spec.get('font_size', 9),
                         'pdf.fonttype': 42, 'svg.fonttype': 'none', 'savefig.bbox': None}):
        fig, axes = plt.subplots(math.ceil(len(panels) / columns), columns, squeeze=False,
                                 figsize=(width / 25.4, height / 25.4), layout='constrained')
        try:
            for index, (panel, ax) in enumerate(zip(panels, axes.flat)):
                rows = table(sources, panel.get('source'))
                kind = panel.get('kind')
                missing = 0
                if kind == 'heatmap':
                    fields = panel.get('columns', [])
                    if not fields:
                        raise VisualError('Heatmap requires numeric columns')
                    values = np.array([column(rows, c) for c in fields]).T
                    missing = int(np.isnan(values).sum())
                    cmap = matplotlib.colormaps[panel.get('cmap', 'cividis')].with_extremes(bad='#dddddd')
                    image = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, aspect='auto', interpolation='nearest',
                                      vmin=panel.get('vmin'), vmax=panel.get('vmax'))
                    ax.set_xticks(range(len(fields)), fields, rotation=30, ha='right')
                    if panel.get('row_labels'):
                        ax.set_yticks(range(len(rows)), column(rows, panel['row_labels'], numeric=False))
                    fig.colorbar(image, ax=ax, label=nonempty(panel.get('colorbar'), 'colorbar label'))
                else:
                    series = panel.get('series', [])
                    if not series:
                        raise VisualError('Provide series with a CSV column and label')
                    distributions, labels = [], []
                    for s_index, series_item in enumerate(series):
                        label = nonempty(series_item.get('label'), 'series label')
                        values = column(rows, series_item.get('y'))
                        if series_item.get('interval') and kind not in {'line', 'scatter', 'bar'}:
                            raise VisualError('Intervals require a line, scatter or bar plot; do not silently discard them')
                        if panel.get('yscale') == 'log' and kind in {'box', 'violin'} and any(v <= 0 for v in values if math.isfinite(v)):
                            raise VisualError('Log scale cannot silently discard nonpositive values')
                        if panel.get('xscale') == 'log' and kind == 'histogram' and any(v <= 0 for v in values if math.isfinite(v)):
                            raise VisualError('Log scale cannot silently discard nonpositive values')
                        missing += sum(math.isnan(v) for v in values)
                        color = series_item.get('color', PALETTE[s_index % len(PALETTE)])
                        if kind in {'line', 'scatter', 'bar'}:
                            x = column(rows, panel.get('x'), numeric=kind != 'bar')
                            if panel.get('yscale') == 'log' and any(v <= 0 for v in values if math.isfinite(v)):
                                raise VisualError('Log scale cannot silently discard nonpositive values')
                            if panel.get('xscale') == 'log' and any(v <= 0 for v in x if isinstance(v, (int, float)) and math.isfinite(v)):
                                raise VisualError('Log scale cannot silently discard nonpositive x values')
                            if kind == 'line':
                                ax.plot(x, values, label=label, color=color, marker=['o', 's', '^', 'D'][s_index % 4],
                                        linestyle=['-', '--', ':', '-.'][s_index % 4], markersize=3)
                            elif kind == 'scatter':
                                ax.scatter(x, values, label=label, color=color, marker=['o', 's', '^', 'D'][s_index % 4], s=20)
                            else:
                                if len(series) != 1:
                                    raise VisualError('For grouped bars, use the custom-code workflow with explicit positions')
                                ax.bar(x, values, label=label, color=color)
                            if series_item.get('interval'):
                                interval = series_item['interval']
                                nonempty(interval.get('definition'), 'interval definition')
                                nonempty(interval.get('sampling_unit'), 'independent sampling unit')
                                low, high = column(rows, interval['low']), column(rows, interval['high'])
                                if any(l > h for l, h in zip(low, high)):
                                    raise VisualError('Reversed uncertainty interval')
                                if panel.get('yscale') == 'log' and any(v <= 0 for v in low + high if math.isfinite(v)):
                                    raise VisualError('Log scale cannot silently discard nonpositive interval bounds')
                                if kind == 'line':
                                    ax.fill_between(x, low, high, alpha=.16, color=color)
                                else:
                                    if any(l > y or h < y for l, y, h in zip(low, values, high)):
                                        raise VisualError('Error bars require the point to lie within its interval')
                                    ax.errorbar(x, values, yerr=[np.array(values) - low, np.array(high) - values],
                                                fmt='none', ecolor=color, capsize=3)
                        elif kind == 'histogram':
                            bins = panel.get('bins')
                            if not isinstance(bins, list) or len(bins) < 2 or any(a >= b for a, b in zip(bins, bins[1:])):
                                raise VisualError('Histogram requires explicit increasing bin edges')
                            observed = [v for v in values if math.isfinite(v)]
                            if not observed or min(observed) < bins[0] or max(observed) > bins[-1]:
                                raise VisualError('Histogram bins must cover every observed value')
                            ax.hist(observed, bins=bins, label=label, color=color, histtype='step', linewidth=1.5)
                        elif kind in {'box', 'violin'}:
                            distributions.append([v for v in values if math.isfinite(v)])
                            labels.append(label)
                        else:
                            raise VisualError('Unknown plot kind: ' + str(kind))
                    if distributions:
                        if any(not d for d in distributions):
                            raise VisualError('Distribution series has no observed values')
                        if kind == 'box':
                            ax.boxplot(distributions, tick_labels=labels, showfliers=False)
                        else:
                            if any(len(d) < 2 or min(d) == max(d) for d in distributions):
                                raise VisualError('Violin density needs varying observations; use a point or box plot')
                            ax.violinplot(distributions, showmedians=True)
                            ax.set_xticks(range(1, len(labels) + 1), labels)
                        # All observations, including boxplot outliers, remain visible.
                        for position, values in enumerate(distributions, 1):
                            ax.scatter([position] * len(values), values, s=12, color=PALETTE[(position - 1) % len(PALETTE)], alpha=.6)
                    else:
                        ax.legend(frameon=False)
                ax.set(title=f'({chr(97 + index)}) ' + panel['title'], xlabel=panel['xlabel'], ylabel=panel['ylabel'])
                for scale in ('xscale', 'yscale'):
                    if scale in panel:
                        if panel[scale] not in {'linear', 'log'}:
                            raise VisualError('Supported scales: linear, log')
                        getattr(ax, 'set_' + scale)(panel[scale])
                for axis in ('x', 'y'):
                    if axis + 'lim' in panel:
                        limits = panel[axis + 'lim']
                        if len(limits) != 2 or limits[0] >= limits[1]:
                            raise VisualError('Axis limits must increase')
                        for limit in limits:
                            number(limit, 'axis limit')
                        if panel.get(axis + 'scale') == 'log' and limits[0] <= 0:
                            raise VisualError('Log axis limits must be positive')
                        if kind == 'bar' and axis == 'y' and not limits[0] <= 0 <= limits[1]:
                            raise VisualError('Bar axis must include its zero baseline')
                        getattr(ax, 'set_' + axis + 'lim')(limits)
                ax.spines[['top', 'right']].set_visible(False)
                panel_facts.append({'kind': kind, 'source': panel['source'], 'rows': len(rows), 'missing_y_cells': missing,
                                    'statistics': 'values and intervals read as supplied; no tests or CI estimation performed'})
            for ax in list(axes.flat)[len(panels):]:
                ax.set_visible(False)
            if spec['evidence_status'] == 'illustrative':
                fig.suptitle('ILLUSTRATIVE DATA — NOT RESEARCH RESULTS', fontsize=9)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                fig.canvas.draw()
                renderer = fig.canvas.get_renderer()
                clipped = clipped_text(fig, renderer)
                if clipped:
                    raise VisualError('Text outside figure bounds; enlarge/reflow: ' + repr(clipped[:5]))
                if any('Glyph' in str(w.message) and 'missing' in str(w.message) for w in caught):
                    raise VisualError('Missing glyphs detected during rendering')
                with output_bundle(destination) as out:
                    for extension in dict.fromkeys(formats + ['png']):
                        fig.savefig(out / ('figure.' + extension), dpi=dpi, bbox_inches=None, facecolor='white')
                    with Image.open(out / 'figure.png') as preview:
                        preview.convert('L').save(out / 'grayscale.png')
                    (out / 'caption.md').write_text(spec.get('caption', '') + '\n', encoding='utf-8')
                    return finalize(out, spec, sources, {'panels': panel_facts, 'font': font, 'size_mm': [width, height],
                                    'dpi': dpi, 'bounds_screen': 'passed', 'visual_review': 'pending',
                                    'warnings': list(dict.fromkeys(str(w.message) for w in caught))}, builder=Path(__file__))
        finally:
            plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('spec'); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        build(args.spec, args.output)
    except (VisualError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + '\n')
