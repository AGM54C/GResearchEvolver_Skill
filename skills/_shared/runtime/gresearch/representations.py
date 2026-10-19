"""Optional real frozen-encoder representations and a small supervised diagnostic.

This is not a reproduction of Latent Critic, ReCast, or hidden-state access to a
closed API model. We expose the encoder, layers, truncation and measured errors.
"""
from __future__ import annotations
import math
from pathlib import Path
from .core import ResearchError, digest, finite, fingerprint, write_json


def encode(config, texts):
    import torch
    from transformers import AutoModel, AutoTokenizer
    root=Path(config['model_dir']).resolve()
    if not root.is_dir():raise ResearchError('Provide a locally provisioned model snapshot')
    weights=list(root.glob('*.safetensors'))
    if not weights:raise ResearchError('This adapter requires safetensors weights; pickle checkpoints are not loaded')
    hashes={p.name:digest(p.read_bytes()) for p in sorted(root.iterdir()) if p.is_file()}
    if config.get('expected_files') and any(hashes.get(k)!=v for k,v in config['expected_files'].items()):
        raise ResearchError('Encoder files differ from pinned model')
    if not texts or len(texts)>1024 or any(not isinstance(t,str) or not t for t in texts):raise ResearchError('Provide 1..1024 nonempty texts')
    max_length=config.get('max_length',256)
    if type(max_length) is not int or not 8<=max_length<=512:raise ResearchError('max_length must be 8..512')
    tokenizer=AutoTokenizer.from_pretrained(root,local_files_only=True,trust_remote_code=False)
    model=AutoModel.from_pretrained(root,local_files_only=True,trust_remote_code=False,use_safetensors=True).eval()
    torch.set_num_threads(config.get('threads',2))
    layers=config.get('layers',[-1,-2]);vectors=[];truncated=[]
    with torch.inference_mode():
        for start in range(0,len(texts),8):
            batch=texts[start:start+8]
            sizes=[len(tokenizer(t,truncation=False)['input_ids']) for t in batch]
            truncated.extend(n>max_length for n in sizes)
            inputs=tokenizer(batch,padding=True,truncation=True,max_length=max_length,return_tensors='pt')
            output=model(**inputs,output_hidden_states=True)
            pooled=[]
            for layer in layers:
                if type(layer) is not int or not -len(output.hidden_states)<=layer<len(output.hidden_states):raise ResearchError('Unknown hidden-state layer')
                hidden=output.hidden_states[layer];mask=inputs['attention_mask'].unsqueeze(-1)
                mean=(hidden*mask).sum(1)/mask.sum(1).clamp(min=1)
                pooled.append(torch.nn.functional.normalize(mean,dim=1))
            vectors.extend(torch.cat(pooled,dim=1).tolist())
    return {'vectors':vectors,'text_hashes':[digest(t.encode('utf-8')) for t in texts],
            'model_files':hashes,'model_snapshot':root.name,'layers':layers,'dimension':len(vectors[0]),
            'truncated':truncated,'max_length':max_length,'pooling':'masked mean, per-layer L2 normalization, concatenate',
            'trained_encoder_this_run':False,'actual_hidden_states':True,'backend_versions':{'torch':torch.__version__}}


def train_critic(data):
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    rows=data['rows']; splits={'train','calibration','evaluation'}
    if any(r.get('split') not in splits for r in rows):raise ResearchError('Explicit train/calibration/evaluation split required')
    used={};ids=set()
    for row in rows:
        if row.get('gold') not in {'supports','contradicts','insufficient'}:raise ResearchError('Unknown critic label')
        if row['id'] in ids:raise ResearchError('Repeated critic example ID')
        ids.add(row['id'])
        if not row.get('groups'):raise ResearchError('Document/group IDs required')
        for g in row['groups']:
            if g in used and used[g]!=row['split']:raise ResearchError('Critic document/group leakage across splits')
            used[g]=row['split']
        for v in row['vector']:finite(v)
    parts={s:[r for r in rows if r['split']==s] for s in splits}
    if any(len(v)<3 for v in parts.values()):raise ResearchError('Each split needs >=3 real labelled examples')
    classes=sorted({r['gold'] for r in parts['train']})
    if len(classes)<3:raise ResearchError('Diagnostic requires at least three classes')
    fit=LogisticRegression(C=1,random_state=0,max_iter=500)
    fit.fit([r['vector'] for r in parts['train']],[r['gold'] for r in parts['train']])
    model={'classes':fit.classes_.tolist(),'coefficients':fit.coef_.tolist(),'intercept':fit.intercept_.tolist(),
           'encoder_hash':data['encoder_hash'],'training_hash':fingerprint(parts['train']),
           'method':'frozen encoder hidden states + multinomial logistic regression; C=1, no hyperparameter search'}
    calibration=predict_critic(model,[r['vector'] for r in parts['calibration']],data['encoder_hash'])
    curve=[]
    for threshold in (.5,.6,.75,.9,.99):
        kept=[(p,r) for p,r in zip(calibration,parts['calibration']) if p['confidence']>=threshold]
        curve.append({'threshold':threshold,'coverage':len(kept)/len(calibration),
                      'accuracy':sum(p['label']==r['gold'] for p,r in kept)/len(kept) if kept else None})
    valid=[x for x in curve if x['accuracy'] is not None and x['accuracy']>=.9]
    model['threshold']=max(valid,key=lambda x:(x['coverage'],-x['threshold']))['threshold'] if valid else 1.0
    predictions=predict_critic(model,[r['vector'] for r in parts['evaluation']],data['encoder_hash'])
    from .semantic import metrics
    measured=[{'id':r['id'],'gold':r['gold'],'prediction':p['label'] if p['confidence']>=model['threshold'] else 'abstain'} for p,r in zip(predictions,parts['evaluation'])]
    raw=[{**r,'prediction':p['label']} for r,p in zip(measured,predictions)]
    evaluation_rows=[{**r,'groups':source['groups'],'confidence':p['confidence'],'probabilities':p['probabilities'],
                      'selected_prediction':selected['prediction']}
                     for r,source,p,selected in zip(raw,parts['evaluation'],predictions,measured)]
    return {'model':model,'calibration_curve':curve,'evaluation':metrics(measured),'raw_evaluation':metrics(raw),
            'evaluation_rows':evaluation_rows,
            'counts':{s:len(v) for s,v in parts.items()},'experimental':True,
            'use':'Diagnostic triage only; out-of-domain use needs new labels and validation'}


def predict_critic(model,vectors,encoder_hash):
    if model['encoder_hash']!=encoder_hash:raise ResearchError('Critic encoder/layer identity mismatch')
    if len(model['classes'])!=3 or set(model['classes'])!={'supports','contradicts','insufficient'}:
        raise ResearchError('Critic needs exactly three unique supported classes')
    if len(model['coefficients'])!=3 or len(model['intercept'])!=3:
        raise ResearchError('Critic coefficient/intercept/class counts differ')
    for row in model['coefficients']:
        if not row:raise ResearchError('Empty critic representation')
        for value in row:finite(value)
    for value in model['intercept']:finite(value)
    predictions=[]
    for v in vectors:
        if any(len(c)!=len(v) for c in model['coefficients']):raise ResearchError('Critic representation dimension mismatch')
        for x in v:finite(x)
        scores=[sum(a*b for a,b in zip(c,v))+i for c,i in zip(model['coefficients'],model['intercept'])]
        for score in scores:finite(score)
        exp=[math.exp(x-max(scores)) for x in scores];probs=[x/sum(exp) for x in exp];best=max(range(len(probs)),key=probs.__getitem__)
        predictions.append({'label':model['classes'][best],'confidence':probs[best],'probabilities':dict(zip(model['classes'],probs))})
    return predictions
