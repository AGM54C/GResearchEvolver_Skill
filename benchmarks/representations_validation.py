"""Offline real encoder/hidden-state diagnostic using an existing pinned model image."""
import argparse,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'))
from gresearch.core import write_json,fingerprint
from gresearch.isolation import run
from scifact_validation import select
import random

def main():
    p=argparse.ArgumentParser();p.add_argument('--data',required=True);p.add_argument('--output',required=True);p.add_argument('--image',required=True);p.add_argument('--model-dir',required=True);a=p.parse_args()
    root=Path(a.output);root.mkdir(parents=True,exist_ok=False);data=Path(a.data)
    corpus={str(x['doc_id']):x for x in map(json.loads,(data/'corpus.jsonl').read_text().splitlines())};rng=random.Random(2001)
    train,used=select(data/'claims_train.jsonl',corpus,20,set(),rng)
    calibration,used=select(data/'claims_train.jsonl',corpus,4,used,rng)
    evaluation,_=select(data/'claims_dev.jsonl',corpus,8,used,rng)
    rows=[]
    for split,items in [('train',train),('calibration',calibration),('evaluation',evaluation)]:
        for x in items:rows.append({'id':split+'-'+x['id'],'groups':x['groups'],'gold':x['gold'],'split':split,
                                   'text':x['claim']+' [SEP] '+' '.join(s['text'] for s in x['sources'])})
    request={'model_dir':a.model_dir,'layers':[-1,-2],'max_length':256,'rows':rows,'model_image':a.image}
    write_json(root/'task.json',{'input':request});code=root/'code';code.mkdir()
    shutil.copytree(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'/'gresearch',code/'gresearch',ignore=shutil.ignore_patterns('__pycache__'))
    (code/'agent.py').write_text('''import argparse,json
from gresearch.representations import encode,train_critic
from gresearch.core import fingerprint
p=argparse.ArgumentParser();p.add_argument('--task');p.add_argument('--seed');p.add_argument('--output');a=p.parse_args()
d=json.load(open(a.task))['input'];enc=encode(d,[r['text'] for r in d['rows']]);eh=fingerprint({k:enc[k] for k in ('model_files','layers','pooling','max_length')})
rows=[{**r,'vector':v} for r,v in zip(d['rows'],enc['vectors'])]
critic=train_critic({'rows':rows,'encoder_hash':eh})
json.dump({'encoder':{k:v for k,v in enc.items() if k!='vectors'},'encoder_hash':eh,'critic':critic,'example_vectors':enc['vectors'][:2]},open(a.output,'w'))
''',encoding='utf-8')
    receipt=run({'kind':'docker','image':a.image,'memory_mb':4096,'pids':128,'cpus':2},code,root/'task.json',['{python}','agent.py'],root/'execution',timeout=300)
    write_json(root/'summary.json',receipt);print(json.dumps(receipt))
    if receipt['status']!='completed':raise SystemExit(1)

if __name__=='__main__':main()
