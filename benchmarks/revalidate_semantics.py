"""Recheck saved SciFact responses under current rules, without new model calls.

This is a post-run software revalidation of the same observations. It neither
creates independent samples nor changes the originally frozen confidence cutoff.
"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'))
from gresearch import semantic
from gresearch.core import digest, write_json
from scifact_validation import make_rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    root=Path(args.run);out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'))
    original=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    judgments={};failures=[]
    for split in ('calibration','evaluation'):
        for start in range(0,len(protocol[split]),protocol['batch_size']):
            batch=root/(split+'-'+str(start))
            try:
                receipt=json.loads((batch/'model'/'result.json').read_text(encoding='utf-8'))
                items=semantic.prepare(protocol[split][start:start+protocol['batch_size']])
                rows=semantic.validate_judgments(items,semantic.parse_json(receipt['text']),threshold=0)
                if receipt['incomplete']:
                    for row in rows:row.update(label='abstain',problems=row['problems']+['incomplete model response'])
                judgments.update({r['id']:r for r in rows})
            except Exception as exc:
                failures.append({'batch':batch.name,'exception':type(exc).__name__,'message':str(exc)})
    raw=make_rows(protocol['evaluation'],judgments,0)
    selected=make_rows(protocol['evaluation'],judgments,original['threshold'])
    before={r['id']:r['prediction'] for r in original['raw_rows']}
    result={'status':'post_run_deterministic_revalidation','new_model_calls':0,
            'original_summary_sha256':digest((root/'summary.json').read_bytes()),
            'semantic_source_sha256':digest(Path(semantic.__file__).read_bytes()),
            'threshold':original['threshold'],'threshold_reselected':False,
            'original_raw_metrics':original['raw_metrics'],
            'raw_metrics':semantic.metrics(raw),'selected_metrics':semantic.metrics(selected),
            'raw_rows':raw,'rows':selected,'judgments':list(judgments.values()),'failures':failures,
            'changed_predictions':[{'id':r['id'],'before':before.get(r['id']),'after':r['prediction']}
                                   for r in raw if before.get(r['id'])!=r['prediction']],
            'limitation':'Same recorded responses, not an independent experiment or unseen evaluation.'}
    write_json(out/'summary.json',result)
    print(json.dumps({k:result[k] for k in ('status','raw_metrics','selected_metrics','changed_predictions','failures')}))


if __name__=='__main__':main()
