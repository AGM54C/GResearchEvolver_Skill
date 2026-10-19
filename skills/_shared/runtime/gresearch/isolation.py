"""Linux Docker candidate boundary. The controller, scorer and signer stay outside.

The Docker daemon/kernel and controller account are trusted. Containers are not a
defence against a compromised daemon/kernel. No same-permission fallback exists.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
import uuid
from pathlib import Path

from .core import ResearchError, digest, write_json


def docker(arguments, timeout=30, check=True):
    try:
        p = subprocess.run(['docker', *arguments], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResearchError('Docker unavailable or timed out; isolation did not run') from exc
    if check and p.returncode:
        # Docker arguments contain paths but never application credentials.
        raise ResearchError('Docker failed: ' + p.stderr.decode('utf-8', 'replace')[:2000])
    return p


def validate(config):
    if config.get('kind') != 'docker': raise ResearchError('Only the explicit docker isolation backend is supported')
    if not re.fullmatch(r'(?:[A-Za-z0-9_./:-]+@)?sha256:[0-9a-f]{64}', config.get('image', '')):
        raise ResearchError('Pin the container image by immutable sha256 digest, not a tag')
    for key, default, lo, hi in [('memory_mb', 256, 64, 16384), ('pids', 32, 4, 256), ('output_mb', 16, 1, 64)]:
        value = config.get(key, default)
        if type(value) is not int or not lo <= value <= hi: raise ResearchError('Invalid isolation ' + key)
    cpus = config.get('cpus', 1)
    if isinstance(cpus, bool) or not isinstance(cpus, (int, float)) or not .1 <= cpus <= 8:
        raise ResearchError('Invalid isolation cpus')
    return config


def run(config, code, task, command, destination, *, seed=0, timeout=60, cancelled=None):
    """Only mount the strategy and this task's public input; copy one regular result.

    Container output resides on a quota-limited tmpfs. It is never a host bind mount.
    Input and strategy paths must be controlled snapshots, not the evaluator tree.
    """
    validate(config)
    if not command or any(not isinstance(x, str) or '\x00' in x for x in command):
        raise ResearchError('Candidate command must be a nonempty argv array')
    if Path(code).is_symlink() or Path(task).is_symlink(): raise ResearchError('Symlink mounts are forbidden')
    code, task, dest = Path(code).resolve(), Path(task).resolve(), Path(destination)
    if not code.is_dir() or not task.is_file(): raise ResearchError('Missing candidate snapshot/input')
    if any(p.is_symlink() for p in code.rglob('*')) or task.is_symlink():
        raise ResearchError('Symlinks cannot be candidate mounts')
    if ',' in str(code) or ',' in str(task): raise ResearchError('Docker mount paths cannot contain commas')
    dest.mkdir(parents=True, exist_ok=False)
    name = 'gresearch-' + uuid.uuid4().hex
    # Docker's VM does not inherit the controller's network, files or credentials.
    argv = ['python3' if x == '{python}' else x for x in command]
    argv += ['--task', '/input/task.json', '--seed', str(seed), '--output', '/out/prediction.json']
    worker = Path(__file__).with_name('container_worker.py').resolve()
    def mount_path(path):
        value = str(path)
        if value.startswith('\\\\?\\'): value = value[4:]
        return value
    args = ['create', '--name', name, '--network', 'none', '--read-only', '--user', '0:0',
            '--cap-drop', 'ALL', '--cap-add', 'SETUID', '--cap-add', 'SETGID', '--cap-add', 'KILL',
            '--security-opt', 'no-new-privileges:true', '--pids-limit', str(config.get('pids', 32)),
            '--memory', str(config.get('memory_mb', 256)) + 'm', '--memory-swap', str(config.get('memory_mb', 256)) + 'm',
            '--cpus', str(config.get('cpus', 1)), '--ulimit', 'nofile=128:128',
            '--log-driver', 'local', '--log-opt', 'max-size=1m', '--log-opt', 'max-file=1', '--log-opt', 'compress=false',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=32m,mode=1777',
            '--tmpfs', '/state:rw,noexec,nosuid,size=1m,mode=700',
            '--tmpfs', '/out:rw,noexec,nosuid,size=' + str(config.get('output_mb', 16)) + 'm,mode=1777',
            '--mount', 'type=bind,source=' + mount_path(code) + ',target=/strategy,readonly',
            '--mount', 'type=bind,source=' + mount_path(task) + ',target=/input/task.json,readonly',
            '--mount', 'type=bind,source=' + mount_path(worker) + ',target=/supervisor.py,readonly',
            '--workdir', '/strategy', '--env', 'PYTHONDONTWRITEBYTECODE=1',
            '--entrypoint', 'python3', config['image'], '/supervisor.py', str(timeout), json.dumps(argv)]
    started = time.monotonic()
    result = {'container': name, 'backend': 'docker', 'image': config['image'], 'argv': argv,
              'status': 'failed', 'input_sha256': digest(task.read_bytes()), 'network': 'none',
              'user': '65534:65534', 'supervisor_uid': 0,
              'candidate_has_signer_or_scorer_mount': False}
    created = False
    try:
        created = True  # A timed-out create may still have created the named container.
        docker(args)
        docker(['start', name])
        while True:
            state = json.loads(docker(['inspect', '--format', '{{json .State}}', name]).stdout)
            if not state['Running']: raise ResearchError('Isolated supervisor exited before result export')
            marker = docker(['exec', '--user', '0', name, 'cat', '/state/result.json'], check=False)
            if marker.returncode == 0:
                status = json.loads(marker.stdout)
                break
            if cancelled and cancelled(): raise ResearchError('Isolated candidate cancelled')
            if time.monotonic() - started >= timeout: raise ResearchError('Isolated candidate timed out')
            time.sleep(.1)
        result.update(exit_code=status['exit_code'], timeout=status['timeout'], oom_killed=state.get('OOMKilled', False))
        logs = docker(['logs', '--tail', '100', name], check=False)
        (dest / 'stdout.txt').write_bytes(logs.stdout[:1048576])
        (dest / 'stderr.txt').write_bytes(logs.stderr[:1048576])
        if status['exit_code'] != 0 or status['timeout'] or state.get('OOMKilled'): raise ResearchError('Isolated candidate failed or timed out')
        exporter = ("import os,stat,sys; f=os.open('/out/prediction.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK); "
                    "s=os.fstat(f); assert stat.S_ISREG(s.st_mode) and s.st_size<=8000000; "
                    "b=os.read(f,8000001); assert len(b)<=8000000; sys.stdout.buffer.write(b)")
        blob = docker(['exec', '--user', '0', name, 'python3', '-c', exporter]).stdout
        prediction = json.loads(blob)
        if not isinstance(prediction, dict): raise ResearchError('Prediction must be a JSON object')
        (dest / 'prediction.json').write_bytes(blob)
        result.update(status='completed', prediction_sha256=digest(blob))
    except Exception as exc:
        result['error'] = str(exc)
    finally:
        if created:
            try:
                logs = docker(['logs', '--tail', '100', name], check=False)
                (dest / 'stdout.txt').write_bytes(logs.stdout[:1048576])
                (dest / 'stderr.txt').write_bytes(logs.stderr[:1048576])
            except Exception as exc:result['log_capture_error']=type(exc).__name__
            try:
                cleanup = docker(['rm', '--force', name], check=False)
                result['container_removed'] = cleanup.returncode == 0 or b'No such container' in cleanup.stderr
            except Exception as exc:
                result.update(container_removed=False,cleanup_error=type(exc).__name__)
            if not result['container_removed']: result.update(status='failed', error='Container removal unconfirmed; inspect by recorded name')
        result['seconds'] = time.monotonic() - started
        write_json(dest / 'receipt.json', result)
    return result
