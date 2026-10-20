"""Run trusted commands with persistent boundaries, cancellation and output capture."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import time
import uuid

from .core import ResearchError, Store, digest, fingerprint, safe_path, write_json, read_json
from .locking import LockBusy, file_lock, resource_lock
from .reproducibility import inspect_run, executable_receipt


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
    with resource_lock(store, 'run', run):
        return _run_workflow(store, run)


def _run_workflow(store, run):
    owner = str(os.getpid()) + "-" + uuid.uuid4().hex[:8]
    with store.tx():
        m, s = store.get(run)
        if s.get("worker"):
            raise ResearchError("Run has a worker; use status/control, or recover after confirming that worker exited")
        if any(v.get('active_attempt') or v.get('cleanup_pending') for v in s['stages'].values()):
            raise ResearchError('Recover unsettled attempts before starting more stages')
        from .hci import pending as pending_reviews
        if s['status'] in {'cancelled', 'completed'}: return s
        if pending_reviews(s) or s.get('intervention_hold'):
            s['status'] = 'awaiting_review'
            store.save(run, s)
            return s
        if s["status"] not in {"ready", "blocked"}:
            return s
        observed, check = inspect_run(store, run, m)
        s.pop('blocker', None)
        s['environment'] = observed
        store.event(run, 'environment_checked', {'observed': observed, 'check': check})
        if m.get('reproducibility', {}).get('mode') == 'strict' and not check['matches']:
            s.update(status='blocked', environment_error=check, blocker={'category': 'environment', 'check': check})
            store.save(run, s)
            return s
        s["worker"] = owner
        s['worker_lock_version'] = 1
        s['generation'] = s.get('generation', 0) + 1
        s['heartbeat'] = time.time()
        s["status"] = "running"
        store.save(run, s)
        store.event(run, "worker_started", {"owner": owner, "platform": platform.platform(), "python": sys.version,
                    "isolation": "trusted_local_process", "environment": {"executable": sys.executable}})
    try:
        while True:
            with store.tx():
                m, s = store.get(run)
                if s.get('worker') != owner:
                    raise ResearchError('Worker ownership changed; refusing stale state commit')
                if s["status"] in {"pause_requested", "cancel_requested"}:
                    s["status"] = "paused" if s["status"] == "pause_requested" else "cancelled"
                    store.save(run, s)
                    break
                if pending_reviews(s) or s.get('intervention_hold'):
                    s['status'] = 'awaiting_review'
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
                    s['blocker'] = {'category': 'authorization', 'stage': sid, 'effect': effect}
                    store.event(run, "authorization_required", {"stage": sid, "effect": effect, "digest": fingerprint(spec)})
                    store.save(run, s)
                    break
                budget = m.get("budget", {})
                reservation = spec.get('cost_estimate', 0) * (1 + spec.get('retries', 0))
                if s["seconds"] >= budget.get("seconds", 3600) or s["reserved_cost"] + reservation > budget.get("cost", 0):
                    s["status"] = "blocked"
                    s['blocker'] = {'category': 'budget', 'stage': sid, 'budget': budget}
                    store.event(run, "budget_exhausted", {"stage": sid, "budget": budget})
                    store.save(run, s)
                    break
                missing = [p for p in spec.get("requires", []) if not safe_path(store.work(run), p).is_file()]
                changed = [p for p in spec.get('requires', []) + spec.get('optional', []) if p in s['artifacts']
                           and (not safe_path(store.work(run), p).is_file() or digest(safe_path(store.work(run), p).read_bytes()) != s['artifacts'][p])]
                pin = s['stages'][sid].get('capability_pin')
                if pin:
                    if store.files(safe_path(store.work(run), pin['directory'])) != pin['bundle']['files']:
                        changed.append(pin['directory'] + ' (bundle file set)')
                    for name, expected in pin['bundle']['files'].items():
                        path = pin['directory'] + '/' + name
                        if not safe_path(store.work(run), path).is_file() or digest(safe_path(store.work(run), path).read_bytes()) != expected:
                            changed.append(path)
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
                s['stages'][sid]['started_at'] = time.time()
                s["reserved_cost"] += reservation
                store.event(run, 'stage_started', {'stage': sid, 'generation': s['generation'], 'owner': owner})
                store.save(run, s)
            stage_started = time.monotonic()
            try:
                outcome = execute_stage(store, run, spec)
            except Exception as exc:
                outcome = {'status': 'failed', 'error': str(exc), 'seconds': time.monotonic() - stage_started,
                           'failure': {'category': 'runtime_error', 'type': type(exc).__name__, 'retryable': False}}
            with store.tx():
                _, s = store.get(run)
                if s.get('worker') != owner:
                    raise ResearchError('Worker ownership changed; refusing stale result')
                if s['stages'][sid].get('active_attempt'):
                    outcome['cleanup_pending'] = True
                s["seconds"] += outcome["seconds"]
                s["stages"][sid].update(outcome)
                s['stages'][sid]['finished_at'] = time.time()
                if outcome["status"] == "completed":
                    s["artifacts"].update(outcome["outputs"])
                store.event(run, "stage_finished", {"stage": sid, **outcome})
                if s.get("single_step"):
                    s["status"] = "paused"
                    s["single_step"] = False
                store.save(run, s)
                if outcome.get('cleanup_pending'):
                    s['status'] = 'blocked'
                    store.save(run, s)
                    break
                if s["status"] == "paused":
                    break
    finally:
        with store.tx():
            _, s = store.get(run)
            if s.get('worker') == owner:
                s["worker"] = None
                if s["status"] == "running":
                    s["status"] = "blocked"
                store.save(run, s)
                store.event(run, "worker_stopped", {"owner": owner, "status": s["status"]})
    return store.get(run)[1]


def execute_stage(store, run, spec):
    if spec.get('ssh'):
        from .ssh_runner import execute_stage as managed_ssh
        return managed_ssh(store, run, spec)
    started = time.monotonic()
    m, state = store.get(run)
    limit = min(spec.get("timeout", 300), m.get("budget", {}).get("seconds", 3600) - state["seconds"])
    deadline = started + limit
    invocation = command_argv(spec)
    pin = state['stages'][spec['id']].get('capability_pin')
    bundled_inputs = []
    if pin:
        # Commands run in work(run). Relative POSIX paths avoid mixing a Windows
        # extended-length prefix with a caller's '/agent.py' suffix.
        invocation = [arg.replace('{bundle}', pin['directory']) for arg in invocation]
        bundled_inputs = [pin['directory'] + '/' + name for name in pin['bundle']['files']]
    env = os.environ.copy()
    # Host environment is inherited. env_from maps names; the runtime does not persist
    # their values, but trusted subprocesses can read/print them in captured raw logs.
    for target, source in spec.get("env_from", {}).items():
        if source not in os.environ:
            return {"status": "failed", "error": f"Missing environment variable: {source}", "seconds": 0,
                    'failure': {'category': 'configuration', 'retryable': False}}
        env[target] = os.environ[source]
    if 'seed' in spec:
        env.update(GRESEARCH_SEED=str(spec['seed']), PYTHONHASHSEED=str(spec['seed']))
    if pin:
        env['PYTHONDONTWRITEBYTECODE'] = '1'
    result = {"status": "failed", "seconds": 0}
    attempts = []
    for attempt in range(spec.get("retries", 0) + 1):
        if time.monotonic() >= deadline:
            result.update(status='failed', timeout=True, failure={'category': 'deadline', 'retryable': False})
            break
        if store.get(run)[1]['status'] == 'cancel_requested':
            result.update(status='failed', cancelled=True, failure={'category': 'cancelled', 'retryable': False})
            break
        clear_outputs(store, run, spec)
        logdir = store.work(run) / "logs" / spec["id"] / uuid.uuid4().hex[:12]
        logdir.mkdir(parents=True)
        before = {p: digest(safe_path(store.work(run), p).read_bytes()) if safe_path(store.work(run), p).is_file() else None
                  for p in spec.get('requires', []) + spec.get('optional', []) + bundled_inputs}
        with store.tx():
            store.event(run, "invocation", {"stage": spec["id"], "argv": invocation, "cwd": str(store.work(run)),
                        "input_hashes": before, "env_names": list(spec.get("env_from", {})), "attempt": attempt + 1,
                        "timeout": limit, "effect": spec.get("effect", "local"), "ssh": spec.get("ssh"),
                        "nondeterministic": spec.get("nondeterministic", True), 'seed': spec.get('seed'),
                        'executable': executable_receipt(invocation, store.work(run))})
        try:
            receipt = supervised_attempt(store, run, spec, invocation, env, logdir, deadline)
            rc = receipt['exit_code']
            timed_out = receipt.get('reason') == 'timeout'
            cancelled = receipt.get('reason') == 'cancelled'
            mutated = [p for p, h in before.items() if (digest(safe_path(store.work(run), p).read_bytes()) if safe_path(store.work(run), p).is_file() else None) != h]
            if pin and store.files(safe_path(store.work(run), pin['directory'])) != pin['bundle']['files']:
                mutated.append(pin['directory'] + ' (bundle file set)')
            result = {"status": "failed", "exit_code": rc, "timeout": timed_out, "cancelled": cancelled,
                      "attempts": attempt + 1, "logs": logdir.relative_to(store.work(run)).as_posix(), "mutated_inputs": mutated,
                      'supervisor': receipt, 'cleanup_pending': not receipt.get('cleanup_verified', False),
                      'log_hashes': {p.name: store.put(p.read_bytes()) for p in logdir.glob('*.txt')}}
            if receipt['status'] == 'completed' and not mutated:
                result.update(status="completed", outputs=store.output_hashes(run, spec))
                attempts.append(dict(result))
                break
            retryable = (not receipt.get('reason') and receipt.get('cleanup_verified') and not mutated
                         and rc in spec.get('retry_exit_codes', []) and attempt < spec.get('retries', 0))
            result['failure'] = {'category': 'input_mutation' if mutated else receipt.get('reason') or 'exit_code', 'retryable': bool(retryable)}
            attempts.append(dict(result))
            if not retryable:
                break
            delay = spec.get('retry_backoff', .25) * 2**attempt
            if time.monotonic() + delay >= deadline:
                result['failure']['retryable'] = False
                result['failure']['retry_suppressed'] = 'insufficient_remaining_budget'
                break
            with store.tx():
                store.event(run, "retry", {"stage": spec["id"], "exit_code": rc, "reason": "predeclared transient code", 'delay_seconds': delay})
            until = time.monotonic() + delay
            while time.monotonic() < until and store.get(run)[1]['status'] != 'cancel_requested':
                time.sleep(min(.05, max(0, until - time.monotonic())))
        except (OSError, ResearchError, subprocess.SubprocessError) as exc:
            result.update(status='failed', error=str(exc), failure={'category': 'validation_or_io', 'type': type(exc).__name__, 'retryable': False})
            attempts.append(dict(result))
            break
    result['attempt_history'] = attempts
    result["seconds"] = time.monotonic() - started
    return result


def supervised_attempt(store, run, spec, argv, env, logdir, deadline):
    from .process_runner import run as managed_run
    heartbeat = time.monotonic()

    def prepare(request):
        with store.tx():
            _, state = store.get(run)
            state['stages'][spec['id']]['active_attempt'] = {'id': request['attempt_id'], 'directory': logdir.relative_to(store.work(run)).as_posix()}
            store.save(run, state)
            store.event(run, 'attempt_prepared', {'stage': spec['id'], 'attempt_id': request['attempt_id'], 'request_hash': fingerprint(request)})

    def tick():
        nonlocal heartbeat
        if time.monotonic() - heartbeat >= 1:
            with store.tx():
                _, state = store.get(run)
                state['heartbeat'] = time.time()
                store.save(run, state)
            heartbeat = time.monotonic()
        return store.get(run)[1]['status'] == 'cancel_requested'

    receipt = managed_run(argv, store.work(run), logdir, deadline, env=env,
                          max_log_bytes=spec.get('max_log_bytes', 10_000_000), prepare=prepare, tick=tick)
    with store.tx():
        _, state = store.get(run)
        if receipt.get('cleanup_verified'):
            state['stages'][spec['id']]['active_attempt'] = None
        store.save(run, state)
        store.event(run, 'attempt_settled', {'stage': spec['id'], 'attempt_id': receipt['attempt_id'], 'receipt': receipt})
    return receipt


def clear_outputs(store, run, spec):
    for name in spec['outputs']:
        p = safe_path(store.work(run), name)
        if p.exists():
            if not p.is_file():
                raise ResearchError(f'Output is not a regular file: {name}')
            store.put(p.read_bytes())
            p.unlink()


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


def recover(store, run, reconciliation=None):
    """Recover only after OS lock release and verified attempt cleanup.

    Legacy stores still use conservative PID checks. Explicit reconciliation is
    an operator record for uncertain local/remote side effects, not an automatic
    claim of exactly-once execution.
    """
    with resource_lock(store, 'run', run):
        return _recover(store, run, reconciliation)


def _recover(store, run, reconciliation=None):
    with store.tx():
        _, s = store.get(run)
        if s.get("worker") and not s.get('worker_lock_version'):
            pid = int(s["worker"].split("-", 1)[0])
            if process_exists(pid):
                raise ResearchError("Worker process still exists; cancel or wait")
        if reconciliation is not None and (not isinstance(reconciliation, dict) or not all(reconciliation.get(k) for k in ('actor', 'reason', 'effects_checked'))):
            raise ResearchError('Reconciliation requires actor, reason and effects_checked')
        recovered = []
        for item in s["stages"].values():
            active = item.get('active_attempt')
            if active:
                directory = safe_path(store.work(run), active['directory'])
                (directory / 'cancel').touch()
                with file_lock(directory / 'supervisor.lock'):
                    receipt = read_json(directory / 'result.json') if (directory / 'result.json').is_file() else None
                    clean = receipt and receipt.get('attempt_id') == active['id'] and receipt.get('cleanup_verified') is True
                    if not clean and not reconciliation:
                        raise ResearchError('Attempt cleanup is uncertain; inspect the job, then supply explicit reconciliation')
                    recovered.append({'attempt_id': active['id'], 'receipt': receipt, 'reconciliation': reconciliation})
                    item.update(active_attempt=None, cleanup_pending=False)
            elif item.get('cleanup_pending'):
                if not reconciliation:
                    raise ResearchError('External cleanup is unconfirmed; inspect effects and supply reconciliation')
                item['cleanup_pending'] = False
            if item["status"] == "running":
                item.update(status="failed", error="interrupted; inspect possible side effects before retry",
                            failure={'category': 'controller_interrupted', 'retryable': False})
                elapsed = max(0, time.time() - item.get('started_at', time.time()))
                s['seconds'] += elapsed
        if s['status'] not in {'completed', 'cancelled'}:
            s['status'] = 'cancelled' if s['status'] == 'cancel_requested' else 'blocked'
        s.update(worker=None)
        store.save(run, s)
        store.event(run, "recovered", {"side_effects": "not_assumed_reversible", 'attempts': recovered, 'reconciliation': reconciliation})
    return s
