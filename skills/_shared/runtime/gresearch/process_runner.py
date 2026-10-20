"""Shared supervised local-command transport for workflow and RSI callers."""
import os
import errno
from pathlib import Path
import subprocess
import sys
import time
import uuid

from .core import ResearchError, native_path, read_json, write_json


def run(argv, cwd, logdir, deadline, *, env=None, max_log_bytes=10_000_000, prepare=None, tick=None):
    logdir = native_path(logdir)
    logdir.mkdir(parents=True, exist_ok=True)
    if (logdir / 'request.json').exists():
        raise ResearchError('Each managed attempt needs a fresh log directory')
    identity = uuid.uuid4().hex
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {'attempt_id': identity, 'status': 'failed', 'exit_code': None, 'reason': 'timeout', 'cleanup_verified': True, 'seconds': 0}
    request = {'attempt_id': identity, 'argv': argv, 'cwd': str(native_path(cwd)), 'timeout': remaining,
               'deadline': deadline, 'max_log_bytes': max_log_bytes}
    write_json(logdir / 'request.json', request)
    if prepare: prepare(request)
    proc = None
    diagnostics = (logdir / 'supervisor-stderr.txt').open('wb')
    try:
        proc = subprocess.Popen([sys.executable, '-B', str(Path(__file__).with_name('local_worker.py')), str(logdir)],
                                env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=diagnostics,
                                start_new_session=os.name != 'nt')
        launched = False
        while proc.poll() is None:
            stopping = bool(tick and tick())
            if stopping: (logdir / 'cancel').touch()
            if not launched and not stopping and (logdir / 'ready.json').is_file():
                if read_json(logdir / 'ready.json').get('attempt_id') != identity:
                    raise ResearchError('Supervisor identity mismatch')
                try:
                    proc.stdin.write(b'G')
                    proc.stdin.flush()
                except OSError as exc:
                    # The supervisor may reach its deadline between poll and
                    # launch. Windows may report EINVAL for the same closed pipe.
                    # Accept no result here; settle and validate the worker receipt.
                    if exc.errno not in {errno.EPIPE, errno.EINVAL}: raise
                launched = True
            if time.monotonic() > deadline + 15:
                raise ResearchError('Supervisor did not acknowledge stop; recover before retry')
            time.sleep(.02)
        receipt = read_json(logdir / 'result.json')
        if receipt.get('attempt_id') != identity:
            raise ResearchError('Attempt receipt identity mismatch')
        receipt['supervisor_exit_code'] = proc.returncode
        if proc.returncode != 0:
            receipt.update(status='failed', reason='supervisor_exit')
        write_json(logdir / 'settlement.json', receipt)
        return receipt
    finally:
        try:
            if proc:
                try:
                    try: proc.stdin.close()
                    except OSError as exc:
                        if exc.errno not in {errno.EPIPE, errno.EINVAL}: raise
                finally:
                    try: proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        # Killing a Linux subreaper can orphan jobs; keep the attempt
                        # visibly unsettled so its caller cannot accept/retry silently.
                        raise ResearchError('Supervisor cleanup is still pending')
        finally:
            diagnostics.close()
