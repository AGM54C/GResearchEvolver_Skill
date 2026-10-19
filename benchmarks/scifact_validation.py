"""Small real-label semantic pilot; freezes document-disjoint calibration/evaluation before calls."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / '_shared' / 'runtime'))
from gresearch import semantic
from gresearch.core import digest, fingerprint, write_json


def select(path, corpus, per_class, exclude, rng):
    claims = [json.loads(x) for x in path.read_text().splitlines()]
    rng.shuffle(claims); counts=Counter(); items=[]; used=set(exclude)
    for row in claims:
        docs=set(map(str,row['cited_doc_ids'])) | set(row['evidence'])
        if not docs or docs & used: continue
        labels={e['label'] for evidence in row['evidence'].values() for e in evidence}
        if len(labels)>1: continue
        gold={'SUPPORT':'supports','CONTRADICT':'contradicts'}.get(next(iter(labels),''),'insufficient')
        if counts[gold]>=per_class:continue
        sources=[{'id':d,'text':' '.join(corpus[d]['abstract']), 'locator':{'dataset':'SciFact','doc_id':d}} for d in sorted(docs)]
        items.append({'id':str(row['id']),'claim':row['claim'],'sources':sources,'gold':gold,
                      'gold_evidence':row['evidence'],'groups':sorted(docs)})
        used.update(docs);counts[gold]+=1
        if all(counts[x]==per_class for x in semantic.LABELS):break
    if len(items)!=3*per_class:raise RuntimeError('Insufficient disjoint labelled examples')
    return items,used


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',required=True);p.add_argument('--output',required=True)
    p.add_argument('--model',required=True);p.add_argument('--exclude-protocol');p.add_argument('--seed',type=int,default=20261019);a=p.parse_args()
    data=Path(a.data);root=Path(a.output);root.mkdir(parents=True,exist_ok=False)
    corpus={str(x['doc_id']):x for x in map(json.loads,(data/'corpus.jsonl').read_text().splitlines())}
    excluded=set()
    if a.exclude_protocol:
        previous=json.loads(Path(a.exclude_protocol).read_text(encoding='utf-8'))
        excluded={g for split in ('calibration','evaluation') for x in previous[split] for g in x['groups']}
    rng=random.Random(a.seed)
    calibration,used=select(data/'claims_train.jsonl',corpus,4,excluded,rng)
    evaluation,_=select(data/'claims_dev.jsonl',corpus,8,used,rng)
    config={'provider':'codex-config','model':a.model,'reasoning_effort':'low','max_output_tokens':6000,'timeout':120,'max_input_chars':85000}
    protocol={'dataset':'SciFact official train/dev; no test-set labels','source':json.loads((data/'source.json').read_text()),
              'config':config,'calibration':calibration,'evaluation':evaluation,'seed':a.seed,'excluded_prior_document_groups':sorted(excluded),
              'threshold_candidates':[.6,.75,.9,.99], 'calibration_rule':'highest coverage with empirical accuracy >= 0.9; if none, threshold=1.0',
              'source_hashes':{n:digest((data/n).read_bytes()) for n in ('corpus.jsonl','claims_train.jsonl','claims_dev.jsonl')},
              'script_hash':digest(Path(__file__).read_bytes()),'semantic_code_hash':digest(Path(semantic.__file__).read_bytes()),
              'frozen_at':time.time(),'batch_size':6,'max_calls':6,'retry_policy':'no retry; failures abstain'}
    write_json(root/'protocol.json',protocol)
    all_predictions={};failures=[];threshold=None
    for split,items in [('calibration',calibration),('evaluation',evaluation)]:
        for i in range(0,len(items),6):
            batch=items[i:i+6]
            try:
                out=semantic.review(config,batch,root/(split+'-'+str(i)),threshold=0)
                all_predictions.update({x['id']:x for x in out['judgments']})
            except Exception as exc:
                failures.append({'split':split,'batch':i,'error':type(exc).__name__})
            print(json.dumps({'split':split,'batch':i,'returned':len(all_predictions),'failed_batches':len(failures)}),flush=True)
        if split=='calibration':
            curve=[]
            for t in protocol['threshold_candidates']:
                rows=make_rows(calibration,all_predictions,t)
                curve.append({'threshold':t,**semantic.metrics(rows)})
            options=[x for x in curve if x['selective_accuracy'] is not None and x['selective_accuracy']>=.9]
            threshold=max(options,key=lambda x:(x['coverage'],-x['threshold']))['threshold'] if options else 1.0
            write_json(root/'calibration.json',{'threshold':threshold,'curve':curve,'frozen_before_evaluation':True})
    raw=make_rows(evaluation,all_predictions,0);selected=make_rows(evaluation,all_predictions,threshold)
    summary={'protocol_hash':fingerprint(protocol),'calibration_n':len(calibration),'evaluation_n':len(evaluation),'threshold':threshold,
             'raw_metrics':semantic.metrics(raw),'selected_metrics':semantic.metrics(selected),'rows':selected,'raw_rows':raw,'failures':failures,
             'limits':['Small purposive balanced pilot, not population-representative','Biomedical abstracts, not cross-domain semantic validation',
                       'Public examples may be in model pretraining','Label calibration does not validate every rationale/aspect or prove truth']}
    write_json(root/'summary.json',summary);print(json.dumps(summary),flush=True)


def make_rows(items,predictions,threshold):
    rows=[]
    for item in items:
        p=predictions.get(item['id'],{})
        prediction=p.get('label','abstain') if p.get('confidence',-1)>=threshold else 'abstain'
        rows.append({'id':item['id'],'gold':item['gold'],'prediction':prediction,'confidence':p.get('confidence'),'groups':item['groups']})
    return rows


if __name__=='__main__':main()
