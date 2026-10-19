"""Opt-in real Docker security/cancellation checks and a signed RSI promotion.

Uses deliberately artificial strategy outputs only to test isolation, never as
scientific ability measurements. Requires a locally available pinned Python image.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / '_shared' / 'runtime'))
from gresearch import isolation, attestation, evolution
from gresearch.core import Store, write_json, fingerprint


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', required=True); p.add_argument('--output', required=True)
    a = p.parse_args(); root = Path(a.output).resolve(); root.mkdir(parents=True, exist_ok=False)
    cfg = {'kind':'docker', 'image':a.image, 'memory_mb':256, 'pids':32}
    secret = root / 'hidden-answer.txt'; secret.write_text('DO_NOT_EXPOSE_TO_CANDIDATE')
    code = root / 'code'; code.mkdir(); task = root / 'task.json'; write_json(task, {'input': {'value': 3}})
    source = '''import argparse,json,os,socket,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--task');p.add_argument('--seed');p.add_argument('--output');a=p.parse_args()
checks={'nonroot':os.getuid()==65534,'host_secret_absent':not Path(HIDDEN).exists(),'docker_socket_absent':not Path('/var/run/docker.sock').exists(),'host_env_absent':'GRESEARCH_SIGNING_KEY' not in os.environ}
for name,path in [('input_readonly',a.task),('code_readonly','/strategy/agent.py'),('root_readonly','/etc/probe'),('supervisor_private','/state/probe')]:
 try: open(path,'a').write('bad');checks[name]=False
 except OSError: checks[name]=True
try:
 socket.create_connection(('1.1.1.1',443),timeout=1).close();checks['network_denied']=False
except OSError:checks['network_denied']=True
checks['candidate_capabilities_zero']='CapEff:\\t0000000000000000' in Path('/proc/self/status').read_text()
Path(a.output).write_text(json.dumps(checks))
'''.replace('HIDDEN', repr(secret.as_posix()))
    (code / 'agent.py').write_text(source, encoding='utf-8')
    normal = isolation.run(cfg, code, task, ['{python}', 'agent.py'], root / 'normal', timeout=20)
    if normal['status'] != 'completed': raise RuntimeError(json.dumps(normal))
    checks = json.loads((root/'normal'/'prediction.json').read_text())
    if not all(checks.values()): raise RuntimeError(json.dumps(checks))
    (code / 'agent.py').write_text("import subprocess,time; subprocess.Popen(['python3','-c','import os,time;os.setsid();time.sleep(60)']); time.sleep(60)")
    timeout = isolation.run(cfg, code, task, ['{python}', 'agent.py'], root / 'timeout', timeout=2)
    if timeout['status'] != 'failed' or not timeout['container_removed']: raise RuntimeError('Timeout boundary failed')
    # A forged link must never be copied as a controller file.
    (code/'agent.py').write_text("import os;os.symlink('/etc/passwd','/out/prediction.json')")
    link = isolation.run(cfg, code, task, ['{python}', 'agent.py'], root/'symlink', timeout=10)
    if link['status'] != 'failed': raise RuntimeError('Symlink output accepted')
    keys = attestation.keygen(root/'keys'); os.environ['GRESEARCH_SIGNING_KEY'] = keys['private_key_path']
    scorer=root/'scorer'; incumbent=root/'incumbent'; candidate=root/'candidate'
    for d in (scorer,incumbent,candidate):d.mkdir()
    prefix="import argparse,json\np=argparse.ArgumentParser();p.add_argument('--task');p.add_argument('--output');p.add_argument('--seed');p.add_argument('--prediction');a=p.parse_args()\n"
    (scorer/'score.py').write_text(prefix+"v=json.load(open(a.prediction))['value'];t=json.load(open(a.task));json.dump({'metric':float(v==t['expected']),'checks':{'finite':True}},open(a.output,'w'))")
    for d,expression in [(incumbent,'0'),(candidate,"json.load(open(a.task))['input']['value']")]:
        (d/'agent.py').write_text(prefix+"json.dump({'value':"+expression+"},open(a.output,'w'))")
    tasks=[{'id':str(i),'group_id':str(i),'split':'audit','batch':'A','input':{'value':i},'expected':i} for i in (1,2,3)]
    protocol={'tasks':tasks,'seeds':[0],'max_trials':2,'resamples':300,'scorer_command':['{python}','score.py'],
              'protected_checks':['finite'],'isolation':cfg,'attestation':{'public_key':keys['public_key']},'trial_seconds':300}
    with closing(Store(root/'store')) as store:
        epoch=evolution.freeze(store,'isolated',protocol,scorer,incumbent,['{python}','agent.py'])
        trial=evolution.evaluate(store,'isolated',candidate,['{python}','agent.py'],promote=True)
        if not trial['promoted']: raise RuntimeError(json.dumps(trial['reasons']))
        expected={'epoch':'isolated','trial':trial['id'],'protocol_hash':epoch['protocol_hash'],
                  'evaluator_hash':epoch['evaluator_hash'],'candidate_hash':fingerprint(trial['candidate'])}
        accepted=attestation.accept(store,trial['attestation'],keys['public_key'],expected)
        replay_rejected=fresh_rejected=False
        try:attestation.accept(store,trial['attestation'],keys['public_key'],expected)
        except Exception:replay_rejected=True
        try:evolution.evaluate(store,'isolated',candidate,['{python}','agent.py'],promote=True)
        except Exception:fresh_rejected=True
    summary={'scope':'synthetic security/integration checks, not scientific ability','image':a.image,
             'checks':checks,'normal':normal,'timeout':timeout,'symlink':link,'promotion':trial['attestation'],
             'receipt_accepted':accepted,'replay_rejected':replay_rejected,'fresh_batch_reuse_rejected':fresh_rejected}
    write_json(root/'summary.json',summary);print(json.dumps(summary),flush=True)


if __name__=='__main__':main()
