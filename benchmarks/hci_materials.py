"""Generate real-data HCI pilot tasks with intentionally seeded, disclosed study faults.

Distribute participant folders only. Reviewers must check/freeze the scoring key
before recruitment. Generating these tasks is not conducting a user study.
"""
import argparse,csv,json,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'))
from gresearch.core import digest,write_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--scifact',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    root=Path(a.output);root.mkdir(parents=True,exist_ok=False)
    reviewers=root/'reviewers';reviewers.mkdir()
    from sklearn.datasets import load_wine
    d=load_wine();A=root/'A'/'participant';A.mkdir(parents=True)
    with (A/'data.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['alcohol','class'])
        writer.writerows((float(x[0]),int(y)) for x,y in zip(d.data,d.target) if y in (0,1))
    (A/'data-description.txt').write_text(d.DESCR,encoding='utf-8')
    (A/'request.md').write_text('检查按协议执行的两组比较，定位并修复结果或表述中的问题。估计目标：class 1 减 class 0 的 alcohol 算术均值差；单位使用数据词典原单位。保留原运行和修正原因，重新执行，并交付与新结果一致的 report.md。该公开数据是观察性数据。',encoding='utf-8')
    (A/'analysis.py').write_text("import csv,json,statistics\nr=list(csv.DictReader(open('data.csv')));g={i:[float(x['alcohol']) for x in r if int(x['class'])==i] for i in (0,1)}\nv=statistics.median(g[1])-statistics.median(g[0])\njson.dump({'metric':'mean_difference','value':v,'n0':len(g[0]),'n1':len(g[1])},open('result.json','w'))\n",encoding='utf-8')
    (A/'writing.py').write_text("import json\nr=json.load(open('result.json'))\nopen('report.md','w',encoding='utf-8').write('Class membership causes a difference of '+str(r['value'])+' in alcohol. This establishes an effect in all wine populations.')\n",encoding='utf-8')
    oracle={'study_faults_intentionally_seeded':True,'mean_difference':float(d.data[d.target==1,0].mean()-d.data[d.target==0,0].mean()),
            'checks':['uses arithmetic means','numeric value matches source data','causal claim removed','universal generalization removed','actual rerun/hash recorded','original branch and intervention rationale preserved']}
    write_json(reviewers/'A.json',oracle)
    B=root/'B'/'participant';B.mkdir(parents=True);data=Path(a.scifact)
    corpus={str(x['doc_id']):x for x in map(json.loads,(data/'corpus.jsonl').read_text().splitlines())}
    selected={}
    for row in map(json.loads,(data/'claims_dev.jsonl').read_text().splitlines()):
        labels={e['label'] for ev in row['evidence'].values() for e in ev}
        if len(labels)>1 or len(row['cited_doc_ids'])!=1:continue
        label={'SUPPORT':'supports','CONTRADICT':'contradicts'}.get(next(iter(labels),''),'insufficient')
        if label not in selected:selected[label]=row
        if len(selected)==3:break
    sources=[];gold=[]
    for label,row in selected.items():
        doc_id=str(row['cited_doc_ids'][0]);doc=corpus[doc_id]
        sources.append({'id':str(row['id']),'claim':row['claim'],'doc_id':doc_id,'title':doc['title'],'sentences':doc['abstract'],
                        'locator':'SciFact corpus doc_id; zero-based abstract sentence index','source_dataset':'https://github.com/allenai/scifact'})
        gold.append({'id':str(row['id']),'label':label,'annotated_evidence':row['evidence']})
    write_json(B/'sources.json',sources);write_json(B/'decisions.json',[{'id':x['id'],'label':'supports','quote':x['sentences'][0]} for x in sources])
    (B/'request.md').write_text('检查三条科研论断与所附原始摘要的支持关系。区分 supports / contradicts / insufficient，给出准确的原文句子与定位；修正 decisions.json 后，保留原运行和干预理由，重新执行并提交 report.md。摘要的存在或引用真实不能单独证明论断。',encoding='utf-8')
    (B/'analysis.py').write_text("import json\nx=json.load(open('decisions.json',encoding='utf-8'));json.dump({'decisions':x},open('result.json','w'))\n",encoding='utf-8')
    (B/'writing.py').write_text("import json\nr=json.load(open('result.json'));s={x['id']:x for x in json.load(open('sources.json',encoding='utf-8'))}\nopen('report.md','w',encoding='utf-8').write('\\n\\n'.join(s[x['id']]['claim']+'\\nDecision: '+x['label']+'\\nQuote: '+x.get('quote','') for x in r['decisions']))\n",encoding='utf-8')
    write_json(reviewers/'B.json',{'study_faults_intentionally_seeded':True,'reference_labels':gold,
               'expert_review_before_freeze_required':True,'checks':['correct relation for each of three claims','quotes/locators bound to supplied abstract','actual rerun/new result used','original branch and rationale preserved']})
    for task,folder,inputs in [('A',A,['data.csv','analysis.py']),('B',B,['decisions.json','sources.json','analysis.py'])]:
        manifest={'version':2,'objective':'HCI pilot task '+task,'authorization':{'effects':['local']},'budget':{'seconds':1200,'cost':0},
                  'stages':[{'id':'analysis','command':['{python}','analysis.py'],'requires':inputs,'outputs':['result.json']},
                            {'id':'writing','needs':['analysis'],'command':['{python}','writing.py'],'requires':['result.json','writing.py']+(['sources.json'] if task=='B' else []),'outputs':['report.md']}]}
        write_json(folder/'workflow.json',manifest)
        files={f.name:digest(f.read_bytes()) for f in folder.iterdir() if f.is_file()}
        write_json(folder/'materials.json',{'task':task,'files':files,'study_conducted':False})
    write_json(root/'provenance.json',{'status':'prepared_not_conducted','scifact_source':json.loads((data/'source.json').read_text()),
                                     'wine_source':'sklearn.datasets.load_wine; UCI Wine','scoring_key_for_reviewer_only':True})
    print(json.dumps({'materials':str(root),'study_conducted':False}))

if __name__=='__main__':main()
