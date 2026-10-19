"""Real Linux descendant/lease tests inside Docker, distinct from live SSH transport validation."""
import argparse,json,shutil,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'))
from gresearch.isolation import run
from gresearch.core import write_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--image',required=True);a=p.parse_args()
    root=Path(a.output);root.mkdir(parents=True,exist_ok=False);code=root/'code';code.mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'/'gresearch'/'remote_worker.py',code/'remote_worker.py')
    (code/'agent.py').write_text('''import argparse,json,subprocess,time,os,threading
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--task');p.add_argument('--seed');p.add_argument('--output');a=p.parse_args()
results=[]
for mode in ('normal','cancel','timeout','lease'):
 root=Path('/tmp')/mode;root.mkdir();(root/'work').mkdir()
 child="import os,time,json;from pathlib import Path;os.setsid();Path('child.pid').write_text(str(os.getpid()));time.sleep(60)"
 program="import subprocess,time,sys;subprocess.Popen([sys.executable,'-c',"+repr(child)+"]);time.sleep("+('0.4' if mode=='normal' else '60')+")"
 request={'job_id':mode,'argv':['python3','-c',program],'timeout':1 if mode=='timeout' else 15,'lease_seconds':1 if mode=='lease' else 30}
 (root/'request.json').write_text(json.dumps(request));(root/'heartbeat').write_text('start')
 process=subprocess.Popen(['python3','/strategy/remote_worker.py',str(root)])
 if mode=='cancel':time.sleep(.8);(root/'cancel').write_text('cancel')
 process.wait(timeout=20);r=json.loads((root/'result.json').read_text());pid=int((root/'work'/'child.pid').read_text())
 r['descendant_absent']=not Path('/proc/'+str(pid)).exists();results.append(r)
 assert r['cleanup_verified'] and r['descendant_absent'],r
 assert r['reason']=={'normal':None,'cancel':'cancelled','timeout':'timeout','lease':'lease_expired'}[mode],r
json.dump({'cases':results,'scope':'real Linux supervision; SSH transport not tested by this script'},open(a.output,'w'))
''',encoding='utf-8')
    write_json(root/'task.json',{'input':{}})
    result=run({'kind':'docker','image':a.image},code,root/'task.json',['{python}','agent.py'],root/'execution',timeout=40)
    write_json(root/'summary.json',result);print(json.dumps(result))
    if result['status']!='completed':raise SystemExit(1)

if __name__=='__main__':main()
