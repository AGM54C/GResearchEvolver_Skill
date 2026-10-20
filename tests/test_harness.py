"""Real process failures and storage invariants; no model or remote credentials required."""
import json
import errno
import os
from pathlib import Path
import subprocess
import sys
import time
from unittest import mock

from test_runtime import Workspace, manifest, stage, REPO
from gresearch.core import ResearchError, Store, digest, read_json
from gresearch.execution import recover, run_workflow, process_exists
from gresearch.locking import LockBusy, resource_lock
from gresearch import projects, reproducibility


def wait_for(predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(.03)
    raise AssertionError('Condition did not become true before deadline')


class HarnessTests(Workspace):
    def launch(self, run, queue=False):
        code = ("import sys;sys.path.insert(0,sys.argv[1]);from gresearch.core import Store;"
                "from gresearch.execution import run_workflow;from gresearch.projects import queue_next;"
                "s=Store(sys.argv[2]);" + ("queue_next(s,{'cpu':1,'gpu':0})" if queue else "run_workflow(s,sys.argv[3])"))
        process = subprocess.Popen([sys.executable, '-B', '-c', code, str(REPO / 'skills/_shared/runtime'), str(self.store.root), run],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        return process

    def test_os_lock_prevents_simultaneous_workers_and_recovery(self):
        run = self.store.create(manifest([stage(code="import time;open('started','w').write('1');time.sleep(30)")]))
        with resource_lock(self.store, 'run', run):
            with self.assertRaises(LockBusy): self.store.archive(run)
            with self.assertRaises(LockBusy): self.store.fork(run, 'analysis')
        p = self.launch(run)
        wait_for(lambda: (self.store.work(run) / 'started').exists())
        with self.assertRaises(LockBusy): run_workflow(self.store, run)
        with self.assertRaises(LockBusy): recover(self.store, run)
        self.store.control(run, 'cancel')
        p.wait(timeout=12)
        self.assertEqual(self.store.get(run)[1]['status'], 'cancelled')

    def test_controller_kill_reaps_detached_descendant_and_recovers_queue(self):
        child = "import time;time.sleep(90)"
        command = ("import subprocess,sys,json,os,time;"
                   f"p=subprocess.Popen([sys.executable,'-c',{child!r}],start_new_session=True);"
                   "open('pids.json','w').write(json.dumps([os.getpid(),p.pid]));time.sleep(90)")
        run = self.store.create(manifest([stage(code=command, timeout=120)], budget={'seconds': 180, 'cost': 0}))
        item = projects.enqueue(self.store, run, {'cpu': 1})
        p = self.launch(run, queue=True)
        wait_for(lambda: (self.store.work(run) / 'pids.json').exists())
        pids = read_json(self.store.work(run) / 'pids.json')
        active = self.store.get(run)[1]['stages']['analysis']['active_attempt']
        with self.assertRaises(LockBusy): projects.queue_recover(self.store, item['id'])
        p.kill()  # deliberately kill only the controller, not its process tree
        p.wait(timeout=5)
        receipt = self.store.work(run) / active['directory'] / 'result.json'
        wait_for(lambda: receipt.exists(), 12)
        self.assertTrue(read_json(receipt)['cleanup_verified'])
        for pid in pids:
            wait_for(lambda: not process_exists(pid), 5)
        # The cleanup receipt precedes interpreter exit. Windows keeps the
        # supervisor's diagnostic file open until that final process exit.
        supervisor_pid = read_json(receipt)['supervisor_pid']
        if os.name == 'nt':
            wait_for(lambda: not process_exists(supervisor_pid), 5)
        recovered = projects.queue_recover(self.store, item['id'])
        self.assertEqual(recovered['status'], 'interrupted')
        state = self.store.get(run)[1]
        self.assertEqual(state['stages']['analysis']['status'], 'failed')
        self.assertFalse(state['stages']['analysis']['cleanup_pending'])
        self.assertGreater(state['seconds'], 0)
        self.assertEqual(projects.queue_next(self.store, {'cpu': 1})['used']['cpu'], 0)

    def test_cancellation_before_launch_settles_without_running_command(self):
        from gresearch.process_runner import run as managed_run
        marker = self.root / 'must-not-run'
        receipt = managed_run([sys.executable, '-c', "open('must-not-run','w').write('unexpected')"],
                              self.root, self.root / 'prelaunch', time.monotonic() + 10,
                              tick=lambda: True)
        self.assertEqual(receipt['reason'], 'cancelled')
        self.assertTrue(receipt['cleanup_verified'])
        self.assertEqual(receipt['supervisor_exit_code'], 0)
        self.assertFalse(marker.exists())

    def test_closed_launch_pipe_still_settles_timeout_and_waits_for_supervisor(self):
        from gresearch.process_runner import run as managed_run
        real_popen, launched = subprocess.Popen, []
        class ClosedPipe:
            def __init__(self, original): self.original = original
            def write(self, data): raise OSError(errno.EINVAL, 'fixture: Windows closed launch pipe')
            def flush(self): raise AssertionError('A failed write must not be flushed')
            def close(self):
                self.original.close()
                raise OSError(errno.EINVAL, 'fixture: closed pipe on close')
        def launch(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            process.stdin = ClosedPipe(process.stdin)
            launched.append(process)
            return process
        with mock.patch('gresearch.process_runner.subprocess.Popen', side_effect=launch):
            receipt = managed_run([sys.executable, '-c', "open('must-not-run','w').write('unexpected')"],
                                  self.root, self.root / 'closed-pipe', time.monotonic() + .5)
        self.assertEqual(receipt['reason'], 'timeout')
        self.assertTrue(receipt['cleanup_verified'])
        self.assertIsNotNone(launched[0].poll())
        self.assertFalse((self.root / 'must-not-run').exists())

    def test_successful_parent_cannot_leave_background_process(self):
        code = ("import subprocess,sys,json;"
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(90)'],start_new_session=True);"
                "open('analysis.json','w').write(json.dumps({'pid':p.pid}))")
        run = self.store.create(manifest([stage(code=code)]))
        result = run_workflow(self.store, run)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['stages']['analysis']['supervisor']['supervisor_exit_code'], 0)
        pid = read_json(self.store.work(run) / 'analysis.json')['pid']
        wait_for(lambda: not process_exists(pid), 5)

    def test_rsi_evaluator_uses_the_same_descendant_cleanup(self):
        from gresearch.evolution import invoke
        work = self.root / 'scorer'
        work.mkdir()
        code = ("import subprocess,sys,json;"
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(90)'],start_new_session=True);"
                "open('pid.json','w').write(json.dumps(p.pid))")
        receipt = invoke([sys.executable, '-c', code], work, [], 10, self.root / 'scoring')
        self.assertTrue(receipt['supervisor']['cleanup_verified'])
        self.assertEqual(receipt['supervisor']['supervisor_exit_code'], 0)
        wait_for(lambda: not process_exists(read_json(work / 'pid.json')), 5)

    def test_remote_uncertainty_blocks_retry_until_reconciled(self):
        run = self.store.create(manifest())
        with self.store.tx():
            _, state = self.store.get(run)
            state['stages']['analysis'].update(status='failed', cleanup_pending=True,
                                               remote_attempt={'job_id': 'fixture', 'directory': '/test/fixture'})
            self.store.save(run, state)
        with self.assertRaises(ResearchError): self.store.control(run, 'retry', stage='analysis')
        with self.assertRaises(ResearchError): run_workflow(self.store, run)
        with self.assertRaises(ResearchError): recover(self.store, run)
        recover(self.store, run, {'actor': 'test', 'reason': 'fixture: no actual remote job', 'effects_checked': True})
        self.store.control(run, 'retry', stage='analysis')

    def test_log_flood_is_bounded_and_never_accepted(self):
        code = "import os,time;os.write(1,b'x'*200000);open('analysis.json','w').write('{}');time.sleep(5)"
        run = self.store.create(manifest([stage(code=code, max_log_bytes=4096)]))
        result = run_workflow(self.store, run)['stages']['analysis']
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['failure']['category'], 'log_limit')
        self.assertTrue(result['supervisor']['cleanup_verified'])
        self.assertLessEqual((self.store.work(run) / result['logs'] / 'stdout.txt').stat().st_size, 4096)

    def test_output_limit_and_corrupt_json_are_typed_failures(self):
        for code, limit in [("open('analysis.json','w').write('x'*100)", 10), ("open('analysis.json','w').write('not json')", 100)]:
            run = self.store.create(manifest([stage(code=code, max_output_bytes=limit)]))
            state = run_workflow(self.store, run)['stages']['analysis']
            self.assertEqual(state['status'], 'failed')
            self.assertFalse(state['failure']['retryable'])

    def test_retries_preserve_each_attempt_and_obey_total_deadline(self):
        code = ("from pathlib import Path;import sys;"
                "p=Path('counter');n=int(p.read_text()) if p.exists() else 0;p.write_text(str(n+1));"
                "open('analysis.json','w').write('{}');sys.exit(7 if n==0 else 0)")
        run = self.store.create(manifest([stage(code=code, retries=1, retry_exit_codes=[7], idempotent=True)]))
        state = run_workflow(self.store, run)['stages']['analysis']
        self.assertEqual(state['status'], 'completed')
        self.assertEqual(len(state['attempt_history']), 2)
        self.assertEqual([x['exit_code'] for x in state['attempt_history']], [7, 0])
        run = self.store.create(manifest([stage(code='raise SystemExit(7)', timeout=.8, retries=2,
                                               retry_exit_codes=[7], retry_backoff=3, idempotent=True)]))
        state = run_workflow(self.store, run)['stages']['analysis']
        self.assertEqual(state['attempts'], 1)
        self.assertFalse(any(e['kind'] == 'retry' for e in self.store.events(run)))

    def test_atomic_object_publication_survives_failed_rename(self):
        content = b'new scientific evidence'
        with mock.patch('gresearch.core.os.replace', side_effect=OSError('injected disk failure')):
            with self.assertRaises(OSError): self.store.put(content)
        self.assertFalse((self.store.objects / digest(content)).exists())
        self.assertTrue(self.store.verify()['valid'])
        self.assertEqual(self.store.blob(self.store.put(content)), content)

    def test_missing_referenced_object_and_future_schema_fail_closed(self):
        run = self.store.create(manifest())
        state = run_workflow(self.store, run)
        (self.store.objects / state['artifacts']['analysis.json']).unlink()
        self.assertFalse(self.store.verify()['valid'])
        with self.store.tx(): self.store.db.execute('PRAGMA user_version=999')
        with self.assertRaises(ResearchError): Store(self.store.root)

    def test_strict_environment_drift_blocks_before_command(self):
        lock = reproducibility.capture(self.root, packages=['missing-package-gresearch'])
        spec = manifest(reproducibility={'mode': 'strict', 'lock': lock})
        run = self.store.create(spec)
        with mock.patch.dict(os.environ, {'OMP_NUM_THREADS': '137'}):
            state = run_workflow(self.store, run)
        self.assertEqual(state['status'], 'blocked')
        self.assertFalse((self.store.work(run) / 'analysis.json').exists())
        self.assertIn('environment', state['environment_error']['differences'])

    def test_recovery_does_not_depend_on_pid_reuse_or_downgrade_completed_run(self):
        run = self.store.create(manifest())
        with self.store.tx():
            _, state = self.store.get(run)
            state.update(worker=str(os.getpid())+'-old', worker_lock_version=1)
            self.store.save(run, state)
        self.assertIsNone(recover(self.store, run)['worker'])
        self.assertEqual(run_workflow(self.store, run)['status'], 'completed')
        self.assertEqual(recover(self.store, run)['status'], 'completed')

    def test_uncertain_attempt_needs_reconciliation(self):
        run = self.store.create(manifest())
        directory = self.store.work(run) / 'logs' / 'analysis' / 'unknown'
        directory.mkdir(parents=True)
        with self.store.tx():
            _, state = self.store.get(run)
            state['stages']['analysis'].update(status='running', active_attempt={'id': 'unknown', 'directory': 'logs/analysis/unknown'})
            self.store.save(run, state)
        with self.assertRaises(ResearchError): recover(self.store, run)
        with self.assertRaises(ResearchError): run_workflow(self.store, run)
        with self.assertRaises(ResearchError): self.store.archive(run)
        result = recover(self.store, run, {'actor': 'test-operator', 'reason': 'fixture: never launched', 'effects_checked': True})
        self.assertFalse(result['stages']['analysis']['cleanup_pending'])
