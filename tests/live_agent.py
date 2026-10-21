"""Budgeted REAL provider/Agent integration smoke; not a scientific benchmark."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / '_shared' / 'runtime'))
from gresearch import agent
from gresearch.core import Store, digest, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--config', help='optional model JSON; defaults to existing codex-config')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists(): raise ValueError('Use a fresh output directory')
    output.mkdir(parents=True)
    config = read_json(args.config) if args.config else {'provider': 'codex-config', 'max_output_tokens': 2000, 'timeout': 120}
    store = Store(output / 'state')
    try:
        objective = ('这是一次真实 Agent 工具链小检查，不是科学能力基准。不要联网、不要运行命令。'
                     '请读取完整能力目录；实际用 research_operation adjust 对示例 pvalues=[0.01,0.03,0.2] 做 Holm 校正；'
                     '将真实工具结果写入 results.md 并用浅显中文解释独立实验单位、伪重复及校正的局限；'
                     '用 report_stage 保存原因、方法、结果、讲解、局限，evidence 引用 results.md，review_required=false。'
                     '最后简短交付。尽量只用 5 次模型请求，不要假称查询了论文或完成科研验证。')
        state = agent.create(store, objective, config, identity='live-agent-smoke',
            budget={'model_calls': 8, 'tool_calls': 12, 'active_seconds': 300, 'output_tokens': 16000},
            policy={'network': False, 'project': 'live-agent-smoke'})
        state = agent.run(store, state['id'])
        call_results = [{'id': c['id'], 'name': c['name'], 'status': c['status'], 'result_hash': c.get('result_hash')}
                        for c in state['calls'].values()]
        files = agent.gateway.inventory(agent.workdir(store, state['id']), state['policy'])
        result = {'kind': 'real_provider_agent_smoke_not_scientific_benchmark', 'status': state['status'],
                  'requested_model': state['config']['model'], 'provider': state['provider'], 'usage': state['usage'],
                  'calls': call_results, 'reports': [{k: r[k] for k in ('id', 'stage', 'record_hash', 'markdown_hash')} for r in state['reports']],
                  'files': files, 'integrity': store.verify(), 'last_error': state.get('last_error'),
                  'source_lock_hash': agent.fingerprint(state['source_lock']), 'environment_hash': state['environment']['sha256'],
                  'evidence_directory': 'state/agents/live-agent-smoke', 'human_research_study_performed': False}
        # Inspect actual calculator output, not the model's final success claim.
        statistics = [read_json(agent.directory(store, state['id']) / 'attempts' / a['directory'] / 'output.json')
                      for a in state['attempts'] if a['kind'] == 'tool' and state['calls'][a['call_id']]['name'] == 'research_operation']
        result['holm_tool_correct'] = any(r.get('ok') and r.get('value', {}).get('adjusted') == [.03, .06, .2] for r in statistics)
        result['passed'] = state['status'] == 'completed' and result['holm_tool_correct'] and bool(state['reports']) and 'results.md' in files and result['integrity']['valid']
        write_json(output / 'live-agent.json', result)
        print(agent.canonical(result))
        return 0 if result['passed'] else 1
    finally: store.close()


if __name__ == '__main__': raise SystemExit(main())
