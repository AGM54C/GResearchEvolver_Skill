"""Opt-in real SSH/SFTP loopback test with an ephemeral Linux Paramiko server.

The server is a test harness, not a production SSH daemon. Bind only loopback,
use throwaway credentials, and remove the container in finally. Provisioning
Paramiko in a temporary container requires --install-paramiko and network access.
"""
import argparse
from contextlib import closing
import json,os,secrets,subprocess,sys,threading,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills'/'_shared'/'runtime'))
from gresearch.core import Store,digest,write_json
from gresearch.execution import run_workflow
from gresearch import ssh_runner

SERVER=r'''
import errno,os,socket,subprocess,threading,time
from pathlib import Path
import paramiko
BASE=Path('/tmp/gresearch');BASE.mkdir()
key=paramiko.RSAKey.generate(2048)
Path('/tmp/host-key.pub').write_text(key.get_name()+' '+key.get_base64())
class Files(paramiko.SFTPServerInterface):
 def path(self,p):
  resolved=Path(p).resolve()
  if not resolved.is_relative_to(BASE):raise OSError(errno.EACCES,'Outside test workspace')
  return resolved
 def stat(self,p):
  try:return paramiko.SFTPAttributes.from_stat(self.path(p).stat())
  except OSError as e:return paramiko.SFTPServer.convert_errno(e.errno)
 def lstat(self,p):
  try:return paramiko.SFTPAttributes.from_stat(self.path(p).lstat())
  except OSError as e:return paramiko.SFTPServer.convert_errno(e.errno)
 def mkdir(self,p,attr):
  try:self.path(p).mkdir(mode=attr.st_mode or 0o700);return paramiko.SFTP_OK
  except OSError as e:return paramiko.SFTPServer.convert_errno(e.errno)
 def open(self,p,flags,attr):
  try:
   fd=os.open(self.path(p),flags,attr.st_mode or 0o600)
   mode='r+b' if flags&os.O_RDWR else 'wb' if flags&os.O_WRONLY else 'rb'
   f=os.fdopen(fd,mode);h=paramiko.SFTPHandle(flags)
   if flags&os.O_RDWR or not flags&os.O_WRONLY:h.readfile=f
   if flags&os.O_RDWR or flags&os.O_WRONLY:h.writefile=f
   return h
  except OSError as e:return paramiko.SFTPServer.convert_errno(e.errno)
class Server(paramiko.ServerInterface):
 def check_auth_password(self,user,password):
  return paramiko.AUTH_SUCCESSFUL if user=='test' and password==os.environ['TEST_SSH_PASSWORD'] else paramiko.AUTH_FAILED
 def get_allowed_auths(self,user):return 'password'
 def check_channel_request(self,kind,chanid):return paramiko.OPEN_SUCCEEDED if kind=='session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED
 def check_channel_exec_request(self,channel,command):
  def execute():
   try:
    p=subprocess.run(command.decode(),shell=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if p.stdout:channel.sendall(p.stdout)
    if p.stderr:channel.sendall_stderr(p.stderr)
    channel.send_exit_status(p.returncode)
   finally:channel.close()
  threading.Thread(target=execute,daemon=True).start();return True
def connection(client):
 transport=paramiko.Transport(client)
 transport.add_server_key(key);transport.set_subsystem_handler('sftp',paramiko.SFTPServer,Files)
 transport.start_server(server=Server())
 while transport.is_active():time.sleep(.1)
sock=socket.socket();sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(('0.0.0.0',2222));sock.listen(8)
print('READY',flush=True)
while True:
 client,_=sock.accept();threading.Thread(target=connection,args=(client,),daemon=True).start()
'''


def docker(*args,check=True,timeout=60):
    return subprocess.run(['docker',*args],capture_output=True,text=True,encoding='utf-8',check=check,timeout=timeout)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',required=True);p.add_argument('--output',required=True)
    p.add_argument('--install-paramiko',action='store_true');a=p.parse_args()
    root=Path(a.output).resolve();root.mkdir(parents=True,exist_ok=False)
    server=root/'server.py';server.write_text(SERVER,encoding='utf-8')
    name='gresearch-ssh-test-'+uuid.uuid4().hex
    env_key='GRESEARCH_LOOPBACK_SSH_PASSWORD';os.environ[env_key]=secrets.token_urlsafe(32)
    summary={'scope':'Real loopback SSH/SFTP to a Linux test server; supplied external host not tested here','cases':[]}
    try:
        docker('run','-d','--name',name,'--user','65534:65534','--read-only','--cap-drop','ALL',
               '--security-opt','no-new-privileges:true','--pids-limit','128','--memory','512m',
               '--tmpfs','/tmp:rw,exec,nosuid,size=160m,mode=1777','-p','127.0.0.1::2222',
               '-e','TEST_SSH_PASSWORD='+os.environ[env_key],'--mount','type=bind,source='+str(server)+',target=/server.py,readonly',
               '--entrypoint','python3',a.image,'-c','import time;time.sleep(600)')
        if a.install_paramiko:
            install=docker('exec',name,'python3','-m','pip','install','--no-input','--disable-pip-version-check',
                           '--target','/tmp/sshdeps','paramiko==4.0.0',timeout=180)
            (root/'provisioning.txt').write_text(install.stdout+install.stderr,encoding='utf-8')
        launch="import os,runpy; f=os.open('/tmp/server.log',os.O_WRONLY|os.O_CREAT,0o600);os.dup2(f,1);os.dup2(f,2);runpy.run_path('/server.py',run_name='__main__')"
        docker('exec','-d','-e','PYTHONPATH=/tmp/sshdeps',name,'python3','-c',launch)
        pub=None
        for _ in range(50):
            probe=docker('exec',name,'cat','/tmp/host-key.pub',check=False)
            if probe.returncode==0:pub=probe.stdout;break
            time.sleep(.2)
        if not pub:raise RuntimeError('SSH test server did not start: '+docker('exec',name,'cat','/tmp/server.log',check=False).stdout)
        port=int(docker('port',name,'2222/tcp').stdout.strip().rsplit(':',1)[1])
        known=root/'known_hosts';known.write_text(f'[127.0.0.1]:{port} '+pub+'\n')
        remote={'host':'127.0.0.1','user':'test','port':port,'cwd':'/tmp/gresearch',
                'known_hosts':str(known),'password_env':env_key}
        summary['host_key_sha256']=digest(pub.encode())
        summary['server_versions']=json.loads(docker('exec','-e','PYTHONPATH=/tmp/sshdeps',name,'python3','-c',
                              "import paramiko,sys,json;print(json.dumps({'paramiko':paramiko.__version__,'python':sys.version}))").stdout)
        # A pinned but different key must reject this actual handshake.
        import paramiko
        wrong=paramiko.RSAKey.generate(2048);bad=root/'wrong_known_hosts'
        bad.write_text(f'[127.0.0.1]:{port} '+wrong.get_name()+' '+wrong.get_base64()+'\n')
        try:
            client=ssh_runner.connect({**remote,'known_hosts':str(bad)});client.close()
            raise AssertionError('Wrong host key accepted')
        except paramiko.BadHostKeyException:summary['host_key_mismatch_rejected']=True
        for mode in ('normal','cancel','timeout'):
            script=root/(mode+'.py')
            child="import os,time;from pathlib import Path;os.setsid();Path('child.pid').write_text(str(os.getpid()));time.sleep(90)"
            source="import json,subprocess,sys,time\nfrom pathlib import Path\n"
            source+="subprocess.Popen([sys.executable,'-c',"+repr(child)+"])\n"
            source+="time.sleep("+('.4' if mode=='normal' else '90')+")\n"
            source+="x=json.loads(Path('input.json').read_text());Path('result.json').write_text(json.dumps({'answer':x['value']*2}))\n"
            script.write_text(source,encoding='utf-8');write_json(root/'input.json',{'value':21})
            spec={'id':'remote','command':['{python}','agent.py'],'requires':['agent.py','input.json'],
                  'outputs':['result.json'],'timeout':4 if mode=='timeout' else 20,'ssh':remote}
            manifest={'version':2,'objective':'SSH loopback validation','authorization':{'effects':['local'],'ssh_hosts':['127.0.0.1']},
                      'budget':{'seconds':40,'cost':0},'stages':[spec]}
            with closing(Store(root/('store-'+mode))) as store:
                run=store.create(manifest,inputs={'agent.py':script,'input.json':root/'input.json'})
                timer=None
                if mode=='cancel':
                    def cancel():
                        with closing(Store(root/('store-'+mode))) as other:other.control(run,'cancel','loopback test')
                    timer=threading.Timer(2,cancel);timer.start()
                state=run_workflow(store,run)
                if timer:timer.join()
                receipts=list(store.work(run).glob('logs/remote/*/transport.json'))
                if len(receipts)!=1:raise RuntimeError('Missing unique transport receipt')
                receipt=json.loads(receipts[0].read_text())
                client=ssh_runner.connect(remote)
                with client.open_sftp() as sftp:
                    pid=int(sftp.open(receipt['remote_job']+'/work/child.pid').read())
                client.close()
                absent=docker('exec',name,'python3','-c',f"from pathlib import Path;print(not Path('/proc/{pid}').exists())").stdout.strip()=='True'
                result={'mode':mode,'workflow_status':state['status'],'transport':receipt,'descendant_absent':absent}
                if mode=='normal':result['returned_output']=json.loads((store.work(run)/'result.json').read_text())
                assert receipt['remote_cleanup_verified'] and absent,result
                if mode=='normal':assert receipt['status']=='completed' and result['returned_output']=={'answer':42},result
                else:assert receipt['status']=='failed' and receipt['reason'] in ({'cancelled'} if mode=='cancel' else {'timeout','cancelled'}),result
                summary['cases'].append(result);print(json.dumps({'mode':mode,'passed':True}),flush=True)
        summary['all_passed']=True
    except Exception as exc:
        summary.update(all_passed=False,error=type(exc).__name__+': '+str(exc))
        raise
    finally:
        cleanup=docker('rm','--force',name,check=False)
        summary['container_removed']=cleanup.returncode==0 or 'No such container' in cleanup.stderr
        os.environ.pop(env_key,None)
        write_json(root/'summary.json',summary)
        print(json.dumps({'all_passed':summary.get('all_passed',False),'container_removed':summary['container_removed']}),flush=True)


if __name__=='__main__':main()
