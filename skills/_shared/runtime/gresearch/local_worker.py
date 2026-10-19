"""Trusted local command supervisor. Parent pipe loss stops the entire job.

Windows uses a Job Object with a gated child, Linux a subreaper. This is not
an adversarial sandbox; Linux SIGKILL of this supervisor needs an external
container/cgroup owner. It does not depend on the workflow SQLite connection.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gresearch.core import read_json, write_json
from gresearch.locking import file_lock


class WindowsJob:
    def __init__(self):
        from ctypes import wintypes as w
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        class BASIC(ctypes.Structure):
            _fields_ = [('per_process', ctypes.c_int64), ('per_job', ctypes.c_int64), ('flags', w.DWORD),
                        ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t), ('active_limit', w.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
        class EXTENDED(ctypes.Structure):
            _fields_ = [('basic', BASIC), ('io', IO), ('process_mem', ctypes.c_size_t),
                        ('job_mem', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.api.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = EXTENDED()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, process):
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def stop(self):
        if not self.api.TerminateJobObject(self.handle, 125):
            raise ctypes.WinError(ctypes.get_last_error())
        # JOBOBJECT_BASIC_ACCOUNTING_INFORMATION: four LARGE_INTEGER then four DWORD.
        accounting = ctypes.create_string_buffer(48)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not self.api.QueryInformationJobObject(self.handle, 1, accounting, 48, None):
                raise ctypes.WinError(ctypes.get_last_error())
            if int.from_bytes(accounting.raw[40:44], 'little') == 0:
                return True
            time.sleep(.02)
        return False

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def gated_child(config_path):
    # Nothing executes before the supervisor has attached this helper to its job.
    if sys.stdin.buffer.read(1) != b'G':
        return 125
    config = read_json(config_path)
    return subprocess.call(config['argv'], cwd=config['cwd'], stdin=subprocess.DEVNULL)


def supervise(directory):
    root = Path(directory).resolve()
    config = read_json(root / 'request.json')
    result = {'attempt_id': config['attempt_id'], 'status': 'failed', 'cleanup_verified': False,
              'exit_code': None, 'reason': None, 'supervisor_pid': os.getpid()}
    started = time.monotonic()
    deadline = min(started + config['timeout'], config['deadline'])
    abandoned = threading.Event()
    launch = threading.Event()
    log_limit = threading.Event()
    io_errors = []
    counts = {}
    process = job = None
    readers = []

    def control():
        try:
            # A daemon blocked in BufferedReader.read holds Python's buffered IO
            # lock and can fatally abort interpreter shutdown. Read the private
            # descriptor directly; never hold that interpreter-owned lock.
            if os.read(sys.stdin.fileno(), 1) == b'G':
                launch.set()
                while os.read(sys.stdin.fileno(), 1024):
                    pass  # controller keeps pipe open while it owns this job
        finally:
            abandoned.set()

    def pump(pipe, name):
        size = 0
        try:
            with (root / name).open('wb') as out:
                while True:
                    chunk = pipe.read(8192)
                    if not chunk:
                        break
                    allowed = max(0, config['max_log_bytes'] - size)
                    out.write(chunk[:allowed])
                    size += len(chunk)
                    if size > config['max_log_bytes']:
                        log_limit.set()
                out.flush()
                os.fsync(out.fileno())
        except Exception as exc:
            io_errors.append(type(exc).__name__ + ': ' + str(exc))
            log_limit.set()
        finally:
            counts[name] = size
            pipe.close()

    with file_lock(root / 'supervisor.lock'):
        try:
            if os.name == 'nt':
                job = WindowsJob()
                result['containment'] = 'windows_job_object'
            elif sys.platform == 'linux':
                if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
                    raise RuntimeError('Cannot enable Linux child subreaper')
                result['containment'] = 'linux_subreaper'
            else:
                raise RuntimeError('Managed local execution currently requires Windows or Linux')
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_: abandoned.set())
            threading.Thread(target=control, daemon=True).start()
            write_json(root / 'ready.json', {'attempt_id': config['attempt_id'], 'pid': os.getpid()})
            while not launch.is_set():
                if abandoned.is_set() or (root / 'cancel').exists():
                    result['reason'] = 'controller_lost' if abandoned.is_set() else 'cancelled'
                    return result
                if time.monotonic() >= deadline:
                    result['reason'] = 'timeout'
                    return result
                time.sleep(.01)
            if abandoned.is_set() or (root / 'cancel').exists():
                result['reason'] = 'controller_lost' if abandoned.is_set() else 'cancelled'
                return result
            argv = [sys.executable, '-B', str(Path(__file__).resolve()), '--child', str(root / 'request.json')] if job else config['argv']
            process = subprocess.Popen(argv, cwd=config['cwd'], stdin=subprocess.PIPE if job else subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=os.name != 'nt')
            if job:
                job.assign(process)
                process.stdin.write(b'G')
                process.stdin.flush()
                process.stdin.close()
            for pipe, name in ((process.stdout, 'stdout.txt'), (process.stderr, 'stderr.txt')):
                t = threading.Thread(target=pump, args=(pipe, name), daemon=True)
                readers.append(t)
                t.start()
            while process.poll() is None:
                if abandoned.is_set(): result['reason'] = 'controller_lost'
                elif (root / 'cancel').exists(): result['reason'] = 'cancelled'
                elif log_limit.is_set(): result['reason'] = 'log_limit'
                elif time.monotonic() >= deadline: result['reason'] = 'timeout'
                if result['reason']:
                    break
                time.sleep(.02)
            result['exit_code'] = process.poll()
        except Exception as exc:
            result.update(reason='supervisor_error', error=type(exc).__name__ + ': ' + str(exc))
        finally:
            try:
                if job:
                    result['cleanup_verified'] = job.stop()
                elif sys.platform == 'linux':
                    from gresearch.remote_worker import cleanup
                    result['cleanup_verified'] = cleanup()
                if process:
                    # A gated helper whose assignment failed is not yet in the job.
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
                for t in readers:
                    t.join(timeout=5)
                if any(t.is_alive() for t in readers):
                    result['cleanup_verified'] = False
                if log_limit.is_set():
                    result['reason'] = 'log_limit'
                if io_errors:
                    result.update(reason='log_io_error', error=io_errors)
            except Exception as exc:
                result.update(cleanup_verified=False, cleanup_error=type(exc).__name__ + ': ' + str(exc))
            finally:
                if job:
                    job.close()
            result['seconds'] = time.monotonic() - started
            result['log_bytes_observed'] = counts
            result['status'] = 'completed' if result['exit_code'] == 0 and not result['reason'] and result['cleanup_verified'] else 'failed'
            write_json(root / 'result.json', result)
    return result


if __name__ == '__main__':
    if sys.argv[1] == '--child':
        raise SystemExit(gated_child(sys.argv[2]))
    supervise(sys.argv[1])
