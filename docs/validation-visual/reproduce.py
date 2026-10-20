"""Rebuild labelled software examples; never generate researcher approval."""
import argparse
import importlib.util
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
SKILLS = REPO / 'skills'
sys.path.insert(0, str(SKILLS / '_shared'))
from visual_artifacts import read_json, write_json, sha256


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, SKILLS / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def build(destination, chinese=False):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    example = module('visual_example', '_shared/examples/visual_research.py')
    sources = example.materials(destination / 'sources')
    figures = module('visual_figures', 'figure-mimic/scripts/build_figure.py')
    diagrams = module('visual_diagrams', 'figure-mimic/scripts/build_diagram.py')
    decks = module('visual_decks', 'slides-builder/scripts/build_deck.py')
    if chinese:
        figure = read_json(sources / 'figure-spec.json')
        figure['panels'][0].update(title='保留给定区间', xlabel='步骤', ylabel='示例值')
        figure['panels'][1].update(title='对照示例值', xlabel='示例值', ylabel='对照值')
        figure['caption'] = '合成软件测试数据；给定区间不是估计的置信区间，不支持科研结论。'
        write_json(sources / 'figure-spec.json', figure)
        diagram = read_json(sources / 'diagram-spec.json')
        for node, label in zip(diagram['nodes'], ('研究者\n确定方向', '生成\n可追溯产物', '研究者\n审阅与修订')):
            node['label'] = label
        for edge, label in zip(diagram['edges'], ('已接受方案', '预览与证据')):
            edge['label'] = label
        diagram['font'] = 'Microsoft YaHei'
        write_json(sources / 'diagram-spec.json', diagram)
        deck = read_json(sources / 'deck-spec.json')
        for slide, title in zip(deck['slides'], ('研究方向由研究者掌握', '原生图表保留给定数据', '区分机器检查与科研判断', '采用前，哪些内容需要修改？')):
            slide['title'] = title
        deck['slides'][0]['body'] = ['有来源、有版本、可人工介入的视觉工作流', '仅为合成软件示例，不是科研实验结果']
        deck['slides'][1]['body'] = ['图表可编辑。', '数据绑定 CSV 哈希。']
        deck['slides'][2]['columns'] = [
            {'title': '机器检查', 'body': ['来源字节与文件结构', '时长与对象边界', '实际渲染结果']},
            {'title': '研究者判断', 'body': ['科学问题与证据强度', '适当的强调与叙事', '是否采用当前版本']}]
        deck['slides'][3]['body'] = ['核对方向、论断和证据。', '提出修订、解释或停止要求。', '只审阅当前产物版本。']
        write_json(sources / 'deck-spec.json', deck)
    figures.build(sources / 'figure-spec.json', destination / 'figure')
    diagrams.build(sources / 'diagram-spec.json', destination / 'diagram')
    deck = read_json(sources / 'deck-spec.json')
    figure_file = destination / 'figure/figure.png'
    deck['sources'].append({'id': 'figure', 'path': '../figure/figure.png', 'sha256': sha256(figure_file), 'label': 'Synthetic interval figure'})
    deck['slides'].insert(2, {'title': '保留区间与中文标注' if chinese else 'Preserve supplied intervals', 'layout': 'figure',
                             'image': {'source': 'figure', 'alt_text': 'Synthetic values with supplied bounds and comparison scatter.'},
                             'seconds': 40, 'notes': 'Explain the supplied bounds. They are not estimated confidence intervals. This is a software fixture.',
                             'claims': ['demo']})
    write_json(sources / 'deck-spec.json', deck)
    decks.build(sources / 'deck-spec.json', destination / 'deck')
    write_json(destination / 'summary.json', {'source_kind': 'labelled synthetic software fixture',
                                             'human_review': 'pending', 'scientific_gain_claimed': False,
                                             'office_render': 'separate command required'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--chinese', action='store_true', help='Requires an installed CJK font; example diagram requests Microsoft YaHei.')
    args = parser.parse_args()
    build(args.output, args.chinese)
