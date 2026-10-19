"""Linux remote job supervisor: cancellation, heartbeat lease and descendant cleanup.

For trusted experiments. This is process management, not an adversarial sandbox.
No project imports: the file can be uploaded alone to a dedicated SSH job directory.
"""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def processes():
    result={}
    for p in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields=p.read_text().rsplit(')',1)[1].split()
            result[int(p.parent.name)]={'ppid':int(fields[1]),'state':fields[0],'start':fields[19]}
        except (OSError,ValueError,IndexError):pass
    return result


def descendants(table,root):
    selected={root}
    while True:
        new={p for p,v in table.items() if v['ppid'] in selected}
        if new.issubset(selected):return selected-{root}
        selected.update(new)


def cleanup():
    # Subreaper adoption retains descendants even when their parent exits/setsid.
    for sig,wait in [(signal.SIGTERM,.5),(signal.SIGKILL,3)]:
        end=time.monotonic()+wait
        while True:
            table=processes();children=descendants(table,os.getpid())
            alive=[p for p in children if table[p]['state']!='Z']
            for pid in alive:
                try:os.kill(pid,sig)
                except ProcessLookupError:pass
            while True:
                try:
                    if os.waitpid(-1,os.WNOHANG)[0]==0:break
                except ChildProcessError:break
            if not alive: return True
            if time.monotonic()>=end:break
            time.sleep(.05)
    table=processes()
    return not any(table[p]['state']!='Z' for p in descendants(table,os.getpid()))


def main(path):
    root=Path(path).resolve();config=json.loads((root/'request.json').read_text())
    if sys.platform!='linux':raise RuntimeError('Managed SSH execution currently requires Linux /proc')
    if ctypes.CDLL(None,use_errno=True).prctl(36,1,0,0,0)!=0:raise RuntimeError('Cannot enable child subreaper')
    interrupted=[]
    for sig in (signal.SIGTERM,signal.SIGHUP,signal.SIGINT):signal.signal(sig,lambda s,f:interrupted.append(s))
    start=last_heartbeat=time.monotonic();last_stamp=None;reason=None;exit_code=None
    result={'job_id':config['job_id'],'supervisor_pid':os.getpid(),'cleanup_verified':False}
    try:
        with (root/'stdout.txt').open('wb') as out,(root/'stderr.txt').open('wb') as err:
            p=subprocess.Popen(config['argv'],cwd=root/'work',stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True)
            while p.poll() is None:
                try:stamp=(root/'heartbeat').stat().st_mtime_ns
                except OSError:stamp=None
                if stamp is not None and stamp!=last_stamp:last_stamp=stamp;last_heartbeat=time.monotonic()
                elapsed=time.monotonic()-start
                if interrupted:reason='signal'
                elif (root/'cancel').exists():reason='cancelled'
                elif elapsed>=config['timeout']:reason='timeout'
                elif time.monotonic()-last_heartbeat>=config.get('lease_seconds',30):reason='lease_expired'
                if reason:break
                time.sleep(.1)
            exit_code=p.poll()
    except Exception as exc:result['error']=type(exc).__name__
    finally:
        result.update(exit_code=exit_code,reason=reason,seconds=time.monotonic()-start,cleanup_verified=cleanup())
        result['status']='completed' if exit_code==0 and not reason and result['cleanup_verified'] and not result.get('error') else 'failed'
        tmp=root/'result.tmp';tmp.write_text(json.dumps(result));tmp.replace(root/'result.json')
    return result


if __name__=='__main__':main(sys.argv[1])
