"""Explicit SSH/SFTP transport for the leased Linux experiment supervisor."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shlex
import stat
import time
import uuid
from .core import ResearchError, digest, safe_path, write_json


def validate(remote):
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*',remote.get('host','')):raise ResearchError('Invalid SSH host')
    port=remote.get('port',22)
    if type(port) is not int or not 1<=port<=65535:raise ResearchError('Invalid SSH port')
    cwd=remote.get('cwd','')
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+',cwd) or '..' in cwd.split('/') or cwd=='/':raise ResearchError('Dedicated absolute remote cwd required')
    return remote


def connect(remote):
    import paramiko
    validate(remote)
    host=remote['host'];user=remote.get('user')
    if '@' in host:user,host=host.split('@',1)
    client=paramiko.SSHClient();client.load_system_host_keys()
    if remote.get('known_hosts'):client.load_host_keys(remote['known_hosts'])
    # New hosts must be enrolled/pinned by the operator, never silently accepted.
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    password=None
    if remote.get('password_env'):
        password=os.getenv(remote['password_env'])
        if not password:raise ResearchError('SSH password environment variable is unset')
    client.connect(host,port=remote.get('port',22),username=user,password=password,
                   key_filename=remote.get('identity_file'),timeout=15,banner_timeout=15,auth_timeout=15,
                   look_for_keys=password is None,allow_agent=password is None)
    return client


def execute_stage(store,run,spec):
    remote=validate(spec['ssh']);start=time.monotonic();manifest,state=store.get(run)
    timeout=min(spec.get('timeout',300),manifest.get('budget',{}).get('seconds',3600)-state['seconds'])
    if timeout<=0:raise ResearchError('No remote execution budget remains')
    if spec.get('env_from'):raise ResearchError('Managed SSH does not forward local secret environments; provision the remote environment explicitly')
    names=spec.get('requires',[])+spec.get('optional',[])+spec['outputs']
    if any(not re.fullmatch(r'[A-Za-z0-9_./-]+',n) for n in names):raise ResearchError('SSH paths must be relative POSIX names')
    # Check traversal using the same local path contract, before touching remote.
    for name in names:safe_path(store.work(run),name)
    job='gresearch-'+uuid.uuid4().hex;directory=remote['cwd'].rstrip('/')+'/'+job
    local=store.work(run)/'logs'/spec['id']/job;local.mkdir(parents=True)
    result={'status':'failed','seconds':0,'remote_job':directory,'remote_cleanup_verified':False}
    client=sftp=None;submitted=False
    try:
        client=connect(remote);sftp=client.open_sftp();sftp.get_channel().settimeout(15)
        # Requested remote parent must already exist. Each invocation gets a fresh directory.
        sftp.mkdir(directory,mode=0o700);sftp.mkdir(directory+'/work',mode=0o700)
        for name in spec.get('requires',[])+spec.get('optional',[]):
            source=safe_path(store.work(run),name)
            if not source.is_file():continue
            parent=directory+'/work'
            for part in name.split('/')[:-1]:
                parent+='/'+part
                try:sftp.mkdir(parent,mode=0o700)
                except OSError:
                    if not stat.S_ISDIR(sftp.lstat(parent).st_mode):raise
            sftp.put(str(source),directory+'/work/'+name)
        sftp.put(str(Path(__file__).with_name('remote_worker.py')),directory+'/worker.py')
        argv=[remote.get('python','python3') if x=='{python}' else x for x in spec['command']]
        request={'argv':argv,'timeout':max(.1,timeout-(time.monotonic()-start)),'lease_seconds':30,'job_id':job}
        with sftp.open(directory+'/request.json','w') as f:f.write(json.dumps(request))
        def touch(name):
            with sftp.open(directory+'/'+name,'w') as f:f.write(str(time.time()))
        touch('heartbeat')
        channel=client.get_transport().open_session(timeout=15)
        # Persist intent before dispatch: losing the acknowledgement leaves an
        # uncertain remote effect, never an apparently unstarted safe retry.
        with store.tx():
            _,current=store.get(run)
            current['stages'][spec['id']].update(cleanup_pending=True,remote_attempt={'job_id':job,'directory':directory})
            store.save(run,current)
            store.event(run,'remote_dispatch_intent',{'stage':spec['id'],'job_id':job,'directory':directory})
        submitted=True
        channel.exec_command('exec '+shlex.join([remote.get('python','python3'),directory+'/worker.py',directory]))
        last_beat=time.monotonic();cancel_sent=False
        while not channel.exit_status_ready():
            status=store.get(run)[1]['status']
            if (status=='cancel_requested' or time.monotonic()-start>=timeout) and not cancel_sent:
                touch('cancel');cancel_sent=True
            if time.monotonic()-last_beat>=3:touch('heartbeat');last_beat=time.monotonic()
            if time.monotonic()-start>=timeout+20:raise ResearchError('Remote supervisor did not acknowledge stop; heartbeat lease will expire')
            time.sleep(.1)
        remote_result=json.loads(sftp.open(directory+'/result.json').read())
        if remote_result.get('job_id')!=job:raise ResearchError('Remote job identity mismatch')
        result.update(remote_result,remote_cleanup_verified=remote_result.get('cleanup_verified',False),remote_job=directory)
        for name in ('stdout.txt','stderr.txt','result.json'):
            info=sftp.lstat(directory+'/'+name)
            if not stat.S_ISREG(info.st_mode) or info.st_size>10_000_000:raise ResearchError('Remote log is not a bounded regular file')
            sftp.get(directory+'/'+name,str(local/name))
        if result['status']=='completed':
            for name in spec['outputs']:
                target=safe_path(store.work(run),name);target.parent.mkdir(parents=True,exist_ok=True)
                info=sftp.lstat(directory+'/work/'+name)
                if not stat.S_ISREG(info.st_mode) or info.st_size>100_000_000:raise ResearchError('Remote output is not a bounded regular file')
                sftp.get(directory+'/work/'+name,str(target))
            result['outputs']=store.output_hashes(run,spec)
    except Exception as exc:
        result.update(status='failed',error=type(exc).__name__+': '+str(exc),
                      disconnect_policy='No heartbeat: supervisor expires in 30s and kills descendants; unconfirmed until remote result is inspected')
        if submitted and sftp:
            try:
                with sftp.open(directory+'/cancel','w') as f:f.write('client exception')
            except Exception:pass
    finally:
        if sftp:sftp.close()
        if client:client.close()
        result['seconds']=time.monotonic()-start
        result['cleanup_pending']=submitted and not result.get('remote_cleanup_verified',False)
        write_json(local/'transport.json',result)
    return result
