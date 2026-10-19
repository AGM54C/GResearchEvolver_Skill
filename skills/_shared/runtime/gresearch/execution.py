"""Run trusted commands with persistent boundaries, cancellation and output capture."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shlex
import signal
import subprocess
import sys
import time
import uuid

from .core import ResearchError, Store, digest, fingerprint, safe_path, write_json


def terminate(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15)
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGKILL)
        process.kill()
        process.wait(timeout=3)


def command_argv(spec):
    argv = [sys.executable if x == '{python}' else x for x in spec['command']] if not spec.get('ssh') else spec['command']
    if not spec.get("ssh"):
        return argv
    remote = spec["ssh"]
    host = remote.get("host", "")
    if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*', host):
        raise ResearchError("Invalid SSH host")
    cwd = remote.get("cwd")
    if not cwd or not re.fullmatch(r'/[A-Za-z0-9_./-]+', cwd) or '..' in cwd.split('/'):
        raise ResearchError("SSH requires an explicit absolute remote cwd")
    # No string interpolation of unquoted arguments into the remote shell.
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "--", host,
            "cd " + shlex.quote(cwd) + " && exec " + shlex.join(argv)]


def run_workflow(store: Store, run):
    owner = str(os.getpid()) + "-" + uuid.uuid4().hex[:8]
    with store.tx():
        m, s = store.get(run)
        if s.get("worker"):
            raise ResearchError("Run has a worker; use status/control, or recover after confirming that worker exited")
        if s["status"] not in {"ready", "blocked"}:
            return s
        s["worker"] = owner
        s["status"] = "running"
        store.save(run, s)
        store.event(run, "worker_started", {"owner": owner, "platform": platform.platform(), "python": sys.version,
                    "isolation": "trusted_local_process", "environment": {"executable": sys.executable}})
    try:
        while True:
            with store.tx():
                m, s = store.get(run)
                if s["status"] in {"pause_requested", "cancel_requested"}:
                    s["status"] = "paused" if s["status"] == "pause_requested" else "cancelled"
                    store.save(run, s)
                    break
                pending = [x for x in m["stages"] if s["stages"][x["id"]]["status"] == "pending"]
                ready = [x for x in pending if all(s["stages"][d]["status"] == "completed" for d in x.get("needs", []))]
                if not ready:
                    s["status"] = "completed" if all(v["status"] == "completed" for v in s["stages"].values()) else "blocked"
                    store.save(run, s)
                    break
                spec = ready[0]
                sid = spec["id"]
                bypass = s.pop('bypass_breakpoint', None)
                if sid in s["breakpoints"] and bypass != sid:
                    s["status"] = "paused"
                    s['stopped_at'] = sid
                    store.event(run, "breakpoint", {"stage": sid})
                    store.save(run, s)
                    break
                effect = spec.get("effect", "local")
                allowed = effect in m["authorization"]["effects"]
                if spec.get("ssh"):
                    allowed = allowed and spec["ssh"]["host"] in m["authorization"].get("ssh_hosts", [])
                if effect == "external_write":
                    allowed = allowed and fingerprint(spec) in m["authorization"].get("approved_stage_digests", [])
                if not allowed:
                    s["status"] = "blocked"
                    store.event(run, "authorization_required", {"stage": sid, "effect": effect, "digest": fingerprint(spec)})
                    store.save(run, s)
                    break
                budget = m.get("budget", {})
                reservation = spec.get('cost_estimate', 0) * (1 + spec.get('retries', 0))
                if s["seconds"] >= budget.get("seconds", 3600) or s["reserved_cost"] + reservation > budget.get("cost", 0):
                    s["status"] = "blocked"
                    store.event(run, "budget_exhausted", {"stage": sid, "budget": budget})
                    store.save(run, s)
                    break
                missing = [p for p in spec.get("requires", []) if not safe_path(store.work(run), p).is_file()]
                changed = [p for p in spec.get('requires', []) + spec.get('optional', []) if p in s['artifacts']
                           and (not safe_path(store.work(run), p).is_file() or digest(safe_path(store.work(run), p).read_bytes()) != s['artifacts'][p])]
                if missing or changed:
                    s["stages"][sid].update(status="failed", error={"missing": missing, "changed_inputs": changed})
                    store.event(run, "input_invalid", {"stage": sid, "missing": missing, "changed": changed})
                    store.save(run, s)
                    continue
                s["stages"][sid]["checkpoint"] = store.files(store.work(run))
                clear_outputs(store, run, spec)
                if not spec.get("command"):
                    s["stages"][sid]["status"] = "awaiting_artifact"
                    s["status"] = "blocked"
                    store.event(run, "host_skill_required", {"stage": sid, "skill": spec.get("skill"), "outputs": spec["outputs"]})
                    store.save(run, s)
                    # Independent ready stages may run in a subsequent worker invocation.
                    break
                s["stages"][sid]["status"] = "running"
                s["reserved_cost"] += reservation
                store.save(run, s)
            try:
                outcome = execute_stage(store, run, spec)
            except Exception as exc:
                outcome = {'status': 'failed', 'error': str(exc), 'seconds': 0}
            with store.tx():
                _, s = store.get(run)
                s["seconds"] += outcome["seconds"]
                s["stages"][sid].update(outcome)
                if outcome["status"] == "completed":
                    s["artifacts"].update(outcome["outputs"])
                store.event(run, "stage_finished", {"stage": sid, **outcome})
                if s.get("single_step"):
                    s["status"] = "paused"
                    s["single_step"] = False
                store.save(run, s)
                if s["status"] == "paused":
                    break
    finally:
        with store.tx():
            _, s = store.get(run)
            s["worker"] = None
            if s["status"] == "running":
                s["status"] = "blocked"
            store.save(run, s)
            store.event(run, "worker_stopped", {"owner": owner, "status": s["status"]})
    return store.get(run)[1]


def execute_stage(store, run, spec):
    started = time.monotonic()
    m, state = store.get(run)
    limit = min(spec.get("timeout", 300), m.get("budget", {}).get("seconds", 3600) - state["seconds"])
    invocation = command_argv(spec)
    env = os.environ.copy()
    # Host environment is inherited. env_from maps names; the runtime does not persist
    # their values, but trusted subprocesses can read/print them in captured raw logs.
    for target, source in spec.get("env_from", {}).items():
        if source not in os.environ:
            return {"status": "failed", "error": f"Missing environment variable: {source}", "seconds": 0}
        env[target] = os.environ[source]
    result = {"status": "failed", "seconds": 0}
    for attempt in range(spec.get("retries", 0) + 1):
        clear_outputs(store, run, spec)
        logdir = store.work(run) / "logs" / spec["id"] / uuid.uuid4().hex[:12]
        logdir.mkdir(parents=True)
        before = {p: digest(safe_path(store.work(run), p).read_bytes()) if safe_path(store.work(run), p).is_file() else None
                  for p in spec.get('requires', []) + spec.get('optional', [])}
        with store.tx():
            store.event(run, "invocation", {"stage": spec["id"], "argv": invocation, "cwd": str(store.work(run)),
                        "input_hashes": before, "env_names": list(spec.get("env_from", {})), "attempt": attempt + 1,
                        "timeout": limit, "effect": spec.get("effect", "local"), "ssh": spec.get("ssh"),
                        "nondeterministic": spec.get("nondeterministic", True)})
        timed_out = cancelled = False
        process = None
        try:
            if spec.get('ssh'):
                remote_transfer(store, run, spec, 'upload', max(0.1, limit - (time.monotonic() - started)))
            with (logdir / "stdout.txt").open("wb") as stdout, (logdir / "stderr.txt").open("wb") as stderr:
                process = subprocess.Popen(invocation, cwd=store.work(run), env=env, stdout=stdout, stderr=stderr,
                                           stdin=subprocess.DEVNULL, start_new_session=os.name != "nt",
                                           creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
                while process.poll() is None:
                    if store.get(run)[1]["status"] == "cancel_requested":
                        cancelled = True
                        terminate(process)
                        break
                    if time.monotonic() - started >= limit:
                        timed_out = True
                        terminate(process)
                        break
                    time.sleep(0.05)
                rc = process.wait()
            mutated = [p for p, h in before.items() if (digest(safe_path(store.work(run), p).read_bytes()) if safe_path(store.work(run), p).is_file() else None) != h]
            result = {"status": "failed", "exit_code": rc, "timeout": timed_out, "cancelled": cancelled,
                      "attempts": attempt + 1, "logs": logdir.relative_to(store.work(run)).as_posix(), "mutated_inputs": mutated}
            if rc == 0 and not timed_out and not cancelled and not mutated:
                if spec.get('ssh'):
                    remote_transfer(store, run, spec, 'download', max(0.1, limit - (time.monotonic() - started)))
                result.update(status="completed", outputs=store.output_hashes(run, spec))
                break
            if cancelled or timed_out or mutated or rc not in spec.get("retry_exit_codes", []):
                break
            with store.tx():
                store.event(run, "retry", {"stage": spec["id"], "exit_code": rc, "reason": "predeclared transient code", "stderr": store.put((logdir / "stderr.txt").read_bytes())})
        except (OSError, ResearchError, subprocess.SubprocessError) as exc:
            result["error"] = str(exc)
            break
        finally:
            if process and process.poll() is None:
                terminate(process)
    result["seconds"] = time.monotonic() - started
    return result


def clear_outputs(store, run, spec):
    for name in spec['outputs']:
        p = safe_path(store.work(run), name)
        if p.exists():
            if not p.is_file():
                raise ResearchError(f'Output is not a regular file: {name}')
            store.put(p.read_bytes())
            p.unlink()


def remote_transfer(store, run, spec, direction, timeout):
    """OpenSSH adapter: explicit files only; remote POSIX paths restricted for SCP safety.

    Remote cwd must be a dedicated workspace. Cancellation stops the SSH client;
    remote descendants require host-specific scheduler cancellation and are not assumed stopped.
    """
    command_argv(spec)  # validates host and cwd
    remote = spec['ssh']
    host, cwd = remote['host'], remote['cwd']
    names = spec.get('requires', []) + spec.get('optional', []) if direction == 'upload' else spec['outputs']
    deadline = time.monotonic() + timeout
    def remaining():
        value = deadline - time.monotonic()
        if value <= 0: raise ResearchError('SSH transfer budget exhausted')
        if store.get(run)[1]['status'] == 'cancel_requested': raise ResearchError('Cancelled during SSH transfer; inspect remote state')
        return value
    for name in names:
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', name):
            raise ResearchError('SSH transfer paths must use letters, digits, _, -, ., /')
        local = safe_path(store.work(run), name)
        target = cwd.rstrip('/') + '/' + name
        if direction == 'upload':
            if not local.is_file():
                continue
            parent = target.rsplit('/', 1)[0]
            subprocess.run(['ssh', '-o', 'BatchMode=yes', '--', host, 'mkdir -p -- ' + shlex.quote(parent)],
                           check=True, capture_output=True, timeout=remaining())
            pair = ['./' + name, host + ':' + target]
        else:
            local.parent.mkdir(parents=True, exist_ok=True)
            pair = [host + ':' + target, './' + name]
        subprocess.run(['scp', '-B', '-o', 'ConnectTimeout=15', '--', *pair], cwd=store.work(run), check=True, capture_output=True, timeout=remaining())
    if direction == 'upload':
        # Ensure old remote results cannot pass a fresh execution. Only explicitly declared files.
        paths = [cwd.rstrip('/') + '/' + p for p in spec['outputs']]
        if any(not re.fullmatch(r'/[A-Za-z0-9_./-]+', p) for p in paths):
            raise ResearchError('Unsafe remote output path')
        subprocess.run(['ssh', '-o', 'BatchMode=yes', '--', host,
                        'rm -f -- ' + ' '.join(shlex.quote(p) for p in paths)], check=True, capture_output=True, timeout=remaining())


def process_exists(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: PID does not exist
                return False
            raise ResearchError('Cannot establish worker liveness (access denied or OS error)')
        try:
            code = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise ResearchError('Cannot read worker process status')
            return code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        raise ResearchError('Cannot establish worker liveness') from exc


def recover(store, run):
    """Explicit recovery: never infer that a running worker is dead from elapsed time."""
    with store.tx():
        _, s = store.get(run)
        if s.get("worker"):
            pid = int(s["worker"].split("-", 1)[0])
            if process_exists(pid):
                raise ResearchError("Worker process still exists; cancel or wait")
        for item in s["stages"].values():
            if item["status"] == "running":
                item.update(status="failed", error="interrupted; inspect possible side effects before retry")
        s.update(status="blocked", worker=None)
        store.save(run, s)
        store.event(run, "recovered", {"side_effects": "not_assumed_reversible"})
    return s
