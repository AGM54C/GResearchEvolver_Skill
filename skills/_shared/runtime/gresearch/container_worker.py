"""Trusted PID-1 wrapper for isolation.py; never run directly on the host."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    if os.getpid() != 1 or not Path('/state').is_dir():
        raise SystemExit('This supervisor must be PID 1 in the dedicated container')
    timeout = float(sys.argv[1])
    argv = json.loads(sys.argv[2])
    def drop():
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
    p = subprocess.Popen(argv, preexec_fn=drop, start_new_session=True,
                         env={'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'),
                              'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1', 'HOME': '/tmp'})
    try:
        rc = p.wait(timeout=timeout)
        status = {'exit_code': rc, 'timeout': False}
    except subprocess.TimeoutExpired:
        status = {'exit_code': None, 'timeout': True}
    # kill(-1) is scoped to this PID namespace; PID 1 and this process are exempt.
    # This also kills children that escaped the candidate's process group.
    try: os.kill(-1, signal.SIGKILL)
    except ProcessLookupError: pass
    try: p.wait(timeout=2)
    except subprocess.TimeoutExpired: pass
    Path('/state/result.json').write_text(json.dumps(status), encoding='utf-8')
    # Keep tmpfs mounted for bounded result export; expire even if controller dies.
    time.sleep(30)


if __name__ == '__main__': main()
