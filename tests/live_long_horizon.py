"""Bounded REAL model/tool smoke ending at a real, unapproved scientific review gate."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/_shared/runtime'))
from gresearch import agent, long_horizon as horizon, memory, memtx, statistics
from gresearch.core import Store, canonical, fingerprint, read_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True); parser.add_argument('--config')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output.exists(): raise ValueError('Use a fresh output directory')
    output.mkdir(parents=True)
    store = Store(output / 'state')
    try:
        observed = statistics.adjust_pvalues([.01,.03,.2], 'holm')
        evidence = store.put(canonical(observed).encode('utf-8'))
        node = {'id':'holm-fixture-v1','type':'tool_result','status':'current','version':1,
                'text':canonical(observed),'sha256':evidence,'scope':'arithmetic fixture, not a real research finding'}
        horizon.create(store,'live-long','Test real long-project tools and stop for actual human review',
            budget={'model_calls':10,'tool_calls':24,'active_seconds':360,'output_tokens':20000,'input_chars':500000},
            constraints=['This is an arithmetic integration fixture, never scientific evidence.','Do not impersonate human acceptance.'])
        memory.put(store,'live-long',{'nodes':[node],'edges':[]},0,actor='integration-setup',reason='actual calculator receipt')
        def tx(op,data):
            return memtx.transact(store,'live-long',op,data,expected_revision=memtx.get(store,'live-long')['revision'],actor='integration-setup')
        identity=tx('begin',{'task_id':'live-long','agent_id':'integration-setup','risk_level':'external_action'})['result']
        tx('stage',{'tx_id':identity,'observation':{'sha256':evidence},'extracted_memory':[
            {'memory_id':node['id'],'entity':'arithmetic-fixture','attribute':'result','value':node['text'],
             'confidence':.8,'source':{'type':'tool','id':'actual-calculator','authority':.1},'evidence_ids':[evidence]}]})
        tx('commit',{'tx_id':identity})
        pins={node['id']:fingerprint(node)}
        objective=('这是小规模真实工具链检查，不是科学能力研究。不联网、不运行命令。请尽快完成：'
            '1. project_status 读取项目；2. research_operation adjust 对 pvalues=[0.01,0.03,0.2]、method=holm 实际计算；'
            '3. 将真实工具结果及校正的适用局限写入 results.md；'
            '4. 准备 report_stage，stage=validation，说明 why/method/findings/explanation/evidence/limitations/questions/review_required=false，evidence=["results.md"]。'
            '先 bind_action：name=report_stage，arguments_json 是该报告完整参数，purpose=conclude，requires_json='+canonical(pins)+
            '，conditions_json={}，reason 说明只是集成检查。然后用一模一样的参数调用 report_stage。'
            '图和真实 MemTX 前提已由测试搭建保存，无需重复写入。控制器应该停止等待真实研究者审查，不要伪造批准，不要直接 final。'
            '这是一次暂未批准的测试结论门控，尚不构成专家科学认可。最多10次模型请求，优先完成产物和绑定。')
        config=read_json(args.config) if args.config else {'provider':'codex-config','max_output_tokens':2000,'timeout':120}
        state=agent.create(store,objective,config,identity='live-long-session',long_project='live-long',
            budget={'model_calls':10,'tool_calls':24,'active_seconds':360,'output_tokens':20000},policy={'network':False})
        state=agent.run(store,state['id'])
        receipts=[(c,json_from_blob(store,c['result_hash'])) for c in state['calls'].values() if c.get('result_hash')]
        correct=any(c['name']=='research_operation' and value.get('ok') and value.get('value',{}).get('adjusted')==[.03,.06,.2] for c,value in receipts)
        files=agent.gateway.inventory(agent.workdir(store,state['id']),state['policy'])
        waiting=state.get('waiting') or {}
        passed=state['status']=='awaiting_researcher' and waiting.get('kind')=='scientific_review' and correct and 'results.md' in files and store.verify()['valid']
        result={'kind':'real_model_long_project_integration_not_scientific_benchmark','passed':passed,'status':state['status'],
            'waiting_kind':waiting.get('kind'),'requested_model':state['config']['model'],'provider':state['provider'],
            'usage':state['usage'],'project_spent':horizon.get(store,'live-long')['spent'],'files':files,'holm_tool_correct':correct,
            'upstream_commit':memtx.get(store,'live-long')['upstream_commit'],'source_lock_hash':fingerprint(state['source_lock']),
            'integrity':store.verify(),'human_approval_performed':False,'user_study_performed':False,'last_error':state.get('last_error'),
            'calls':[{'name':c['name'],'status':c['status'],'result_hash':c.get('result_hash')} for c in state['calls'].values()]}
        write_json(output/'live-long.json',result)
        print(canonical(result))
        return 0 if passed else 1
    finally: store.close()


def json_from_blob(store,h):
    import json
    return json.loads(store.blob(h))


if __name__=='__main__': raise SystemExit(main())
