"""Matched model/task/budget pilot on three real datasets (six analysis microtasks).

This measures a bounded instruction treatment, not autonomous full-research quality
or superiority to another skill suite. No generated answers exist at freeze time.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'))
from gresearch import models, isolation, statistics
from gresearch.core import digest, fingerprint, write_json
from gresearch.semantic import parse_json


def prepare(root,model,image):
    import numpy as np
    import sklearn
    from sklearn import datasets
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.neighbors import NearestCentroid
    from sklearn.metrics import balanced_accuracy_score, accuracy_score
    repo=Path(__file__).resolve().parents[1]
    sources=['skills/statistical-analyst/SKILL.md','skills/experiment-replicator/SKILL.md','skills/_shared/README.md']
    snapshots={p:(repo/p).read_text(encoding='utf-8') for p in sources}
    shared='Return JSON only with one key python_code containing a standalone Python 3 program. It receives --task PATH --seed N --output PATH. Load JSON at --task and use its input. Write the requested answer JSON to --output. Use only the Python standard library. Do not access network or other files. You have one generation and one execution; no repair call.'
    prompts={'direct':'Complete the requested research analysis carefully. '+shared,
             'evidence_skill':'Apply the following research skills to this bounded analysis request.\n'+ '\n'.join(snapshots.values())+'\n'+shared}
    tasks=[]
    for domain,loader,columns in [('botany',datasets.load_iris,[0,1,2,3]),('chemistry',datasets.load_wine,[0,1,9,12]),('oncology',datasets.load_breast_cancer,[0,1,2,3])]:
        d=loader(); x=d.data[:,columns];y=d.target
        metadata={'domain':domain,'dataset':loader.__name__,'features':[str(d.feature_names[i]) for i in columns],
                  'class_names':list(map(str,d.target_names)), 'source_description':d.DESCR,
                  'provenance':'Real bundled scikit-learn dataset, original rows; selected feature columns',
                  'dataset_sha256':digest(x.tobytes()+y.tobytes())}
        rows=[{'x':list(map(float,v)),'y':int(label)} for v,label in zip(x,y)]
        a=x[y==0,0];b=x[y==1,0]
        expected={'n0':len(a),'n1':len(b),'mean_difference':float(b.mean()-a.mean()),
                  'standard_error':float(np.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))),
                  'causality_established':False,'external_validation_established':False}
        request='On feature index 0 compare class 1 minus class 0. Return n0,n1,mean_difference,standard_error (sqrt(sample_variance_0/n0+sample_variance_1/n1), ddof=1), and two booleans: causality_established and external_validation_established. Judge those from the supplied study/data design, not from the size of a difference.'
        tasks.append({'id':domain+'-summary','group_id':domain,'input':{'metadata':metadata,'rows':rows,'request':request},'expected':expected})
        train,test=train_test_split(np.arange(len(y)),test_size=.3,random_state=4242,stratify=y)
        pipeline=make_pipeline(StandardScaler(),NearestCentroid());pipeline.fit(x[train],y[train]);pred=pipeline.predict(x[test])
        expected={'train_n':len(train),'test_n':len(test),'accuracy':float(accuracy_score(y[test],pred)),
                  'balanced_accuracy':float(balanced_accuracy_score(y[test],pred)),
                  'causality_established':False,'external_validation_established':False}
        request='Fit a nearest-class-centroid classifier using only the provided training rows. Standardize each feature with training population mean/std (ddof=0; zero std becomes 1); compute class means in standardized training space, then nearest centroid by squared Euclidean distance. Evaluate on test rows: return train_n,test_n,accuracy,balanced_accuracy (mean recall of every class present in test),causality_established,external_validation_established. Judge design validity from the supplied data; this is one internal random split of an observational dataset.'
        tasks.append({'id':domain+'-prediction','group_id':domain,'input':{'metadata':metadata,'train':[rows[i] for i in train],'test':[rows[i] for i in test],'request':request},'expected':expected})
    config={'provider':'codex-config','model':model,'reasoning_effort':'low','max_output_tokens':2400,'timeout':120,'max_input_chars':100000}
    protocol={'model':config,'image':image,'sklearn':sklearn.__version__,'numpy':np.__version__,'tasks':tasks,
              'prompts':prompts,'skill_snapshots':snapshots,'freeze_time':time.time(),'script_sha256':digest(Path(__file__).read_bytes()),
              'budget_per_arm_task':{'model_calls':1,'input_tokens_including_provider_overhead':24000,'output_tokens':2400,'model_seconds':120,'execution_seconds':30,'repairs':0},
              'scoring':'mean of six fields; numeric abs tolerance 1e-6, booleans exact; failed/budget-violating attempts score 0',
              'independent_unit':'dataset; the two tasks per dataset are dependent and must be clustered',
              'order':'alternate arms by task index','primary_comparison':'evidence_skill minus direct',
              'scope':'six bounded coding/data interpretation microtasks, not full autonomous research or competitor comparison'}
    write_json(root/'protocol.json',protocol)
    return protocol


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);p.add_argument('--model',required=True);p.add_argument('--image',required=True)
    a=p.parse_args();root=Path(a.output);root.mkdir(parents=True,exist_ok=False);protocol=prepare(root,a.model,a.image)
    protocol_hash=fingerprint(protocol);rows=[]
    for i,task in enumerate(protocol['tasks']):
        order=['direct','evidence_skill'] if i%2==0 else ['evidence_skill','direct']
        for arm in order:
            dest=root/task['id']/arm;dest.mkdir(parents=True)
            row={'task':task['id'],'group_id':task['group_id'],'arm':arm,'score':0,'status':'failed'}
            try:
                # Verify freeze before each attempt, without allowing result-driven changes.
                if fingerprint(json.loads((root/'protocol.json').read_text(encoding='utf-8')))!=protocol_hash:raise RuntimeError('Protocol changed')
                result=models.generate(protocol['model'],[{'role':'system','content':protocol['prompts'][arm]},
                                     {'role':'user','content':json.dumps(task['input'],ensure_ascii=False)}],dest/'model')
                row.update(usage=result['usage'],model_seconds=result['seconds'],returned_model=result['returned_model'],response_hash=result['response_sha256'])
                usage=result['usage']
                if result['returned_model']!=a.model or result['incomplete'] or result['seconds']>120:raise RuntimeError('Model or time budget mismatch')
                if usage.get('input_tokens',10**9)>24000 or usage.get('output_tokens',10**9)>2400:raise RuntimeError('Token budget violation or missing usage')
                answer=parse_json(result['text']);code=dest/'code';code.mkdir();(code/'analysis.py').write_text(answer['python_code'],encoding='utf-8')
                input_path=dest/'task.json';write_json(input_path,{'id':task['id'],'input':task['input']})
                executed=isolation.run({'kind':'docker','image':a.image},code,input_path,['{python}','analysis.py'],dest/'execution',timeout=30)
                row['execution']=executed
                if executed['status']!='completed':raise RuntimeError('Generated program execution failed')
                prediction=json.loads((dest/'execution'/'prediction.json').read_text())
                scores={}
                for key,value in task['expected'].items():
                    pred=prediction.get(key)
                    scores[key]=(pred is value) if isinstance(value,bool) else (type(pred) in (int,float) and math.isfinite(pred) and abs(pred-value)<=1e-6)
                row.update(status='scored',prediction=prediction,checks=scores,score=sum(scores.values())/len(scores))
            except Exception as exc: row['error']=str(exc)
            rows.append(row);write_json(root/'results.json',rows);print(json.dumps({k:row[k] for k in ('task','arm','score','status')}),flush=True)
    pairs=[]
    for task in protocol['tasks']:
        pair={r['arm']:r['score'] for r in rows if r['task']==task['id']}
        pairs.append({'task':task['group_id'],'seed':task['id'],'candidate':pair['evidence_skill'],'incumbent':pair['direct']})
    summary={'protocol_hash':protocol_hash,'rows':rows,'analysis':statistics.paired_analysis(pairs,resamples=4000,seed=20261019),
             'arm_means':{a:sum(r['score'] for r in rows if r['arm']==a)/6 for a in ('direct','evidence_skill')},
             'limits':['Only three independent datasets; bootstrap interval is exploratory','No repeated model calls: stochastic variability unmeasured',
                       'Public datasets may occur in pretraining','One bounded instruction treatment; no claim of end-to-end or competitor superiority']}
    write_json(root/'summary.json',summary);print(json.dumps({'analysis':summary['analysis'],'arm_means':summary['arm_means']}),flush=True)


if __name__=='__main__':main()
