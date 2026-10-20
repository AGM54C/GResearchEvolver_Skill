"""Durable provenance and cooperative workflow control (not a security sandbox)."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time
import uuid
import tempfile
from contextlib import contextmanager


class ResearchError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return digest(canonical(value).encode("utf-8"))


def native_path(path):
    resolved = Path(path).resolve()
    text = str(resolved)
    if os.name == 'nt' and not text.startswith('\\\\?\\'):
        text = '\\\\?\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\\\?\\' + text
        return Path(text)
    return resolved


def read_json(path):
    return json.loads(native_path(path).read_text(encoding="utf-8-sig"), parse_constant=lambda x: (_ for _ in ()).throw(ResearchError(f"Non-finite number: {x}")))


def write_json(path, value):
    atomic_bytes(path, (canonical(value) + '\n').encode('utf-8'))


def sync_directory(path):
    if os.name != 'nt':
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_bytes(path, data):
    path = native_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open('xb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        sync_directory(path.parent)
    finally:
        tmp.unlink(missing_ok=True)


def safe_path(root, name):
    root = native_path(root)
    name = str(name)
    # A leading POSIX slash has no Windows drive, and older pathlib versions
    # differ when resolving '..' under an extended-length prefix. Reject both
    # lexically before relying on native path resolution.
    if not name or name.startswith('/') or '..' in name.split('/') or Path(name).is_absolute() or ':' in name or "\\" in name:
        raise ResearchError(f"Expected a relative POSIX path: {name}")
    target = (root / name).resolve()
    if target == root or root not in target.parents:
        raise ResearchError(f"Path escapes root: {name}")
    return target


def valid_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
        raise ResearchError(f"Invalid ID: {value!r}")
    return value


def finite(value, name="number", minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ResearchError(f"{name} must be finite")
    if minimum is not None and value < minimum:
        raise ResearchError(f"{name} must be >= {minimum}")
    return value


def validate_manifest(m):
    if not isinstance(m, dict) or m.get("version") != 2 or not isinstance(m.get('objective'), str) or not m['objective'].strip():
        raise ResearchError("Manifest requires version=2 and objective")
    stages = m.get("stages", [])
    if not isinstance(stages, list) or not stages or any(not isinstance(s, dict) for s in stages):
        raise ResearchError("No stages")
    ids = [valid_id(s["id"]) for s in stages]
    if len(ids) != len(set(ids)):
        raise ResearchError("Duplicate stage IDs; iterations need distinct IDs")
    seen, outputs = set(), set()
    for s in stages:
        if not isinstance(s.get('needs', []), list):
            raise ResearchError('needs must be a list')
        for field in ('milestone', 'milestone_id'):
            if field in s and (not isinstance(s[field], str) or not s[field].strip()):
                raise ResearchError(f'{field} must be a nonempty string')
        if not set(s.get("needs", [])).issubset(set(ids)) or s["id"] in s.get("needs", []):
            raise ResearchError("Unknown or self dependency")
        for key in ("requires", "optional", "outputs"):
            if not isinstance(s.get(key, []), list):
                raise ResearchError(f'{key} must be a list')
            for p in s.get(key, []):
                if not isinstance(p, str): raise ResearchError('Artifact paths must be strings')
                safe_path(Path.cwd(), p)
            if len(s.get(key, [])) != len(set(s.get(key, []))):
                raise ResearchError('Duplicate paths in ' + key)
        if not s.get("outputs"):
            raise ResearchError(f"{s['id']}: declare outputs")
        if outputs.intersection(s["outputs"]):
            raise ResearchError("Version outputs; two stages cannot overwrite the same artifact")
        outputs.update(s["outputs"])
        cmd = s.get("command")
        if cmd is not None and (not isinstance(cmd, list) or not cmd or any(not isinstance(x, str) for x in cmd)):
            raise ResearchError("command must be a nonempty argv array")
        if s.get("effect", "local") not in {"local", "read_network", "external_write"}:
            raise ResearchError("Unknown effect")
        finite(s.get("timeout", 300), "timeout", 0.01)
        finite(s.get("cost_estimate", 0), "cost_estimate", 0)
        if type(s.get("retries", 0)) is not int or not 0 <= s.get("retries", 0) <= 2:
            raise ResearchError("retries must be 0..2; retries require idempotent=true")
        if s.get("retries", 0) and s.get("idempotent") is not True:
            raise ResearchError("Retries require an explicitly idempotent operation")
        if s.get('retries') and (s.get('effect') == 'external_write' or s.get('ssh')):
            raise ResearchError('Automatic retries of remote/external writes require provider reconciliation; use explicit recovery')
        codes = s.get('retry_exit_codes', [])
        if not isinstance(codes, list) or any(type(c) is not int or c == 0 for c in codes):
            raise ResearchError('retry_exit_codes must be an array of nonzero integer codes')
        finite(s.get('retry_backoff', .25), 'retry_backoff', 0)
        for key, default in (('max_log_bytes', 10_000_000), ('max_output_bytes', 100_000_000)):
            if type(s.get(key, default)) is not int or s.get(key, default) < 1:
                raise ResearchError(key + ' must be a positive integer')
        env = s.get('env_from', {})
        if not isinstance(env, dict) or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k) for k, v in env.items()):
            raise ResearchError('env_from must map variable names to source variable names')
        if 'seed' in s and (type(s['seed']) is not int or not 0 <= s['seed'] < 2**32):
            raise ResearchError('seed must be an integer in 0..2**32-1')
        if s.get('ssh'):
            from .ssh_runner import validate
            validate(s['ssh'])
        for check in s.get('checks', []):
            if not isinstance(check, dict) or check.get('path') not in s['outputs'] or 'equals' not in check:
                raise ResearchError('Acceptance checks require a declared output path and equals')
    while len(seen) < len(ids):
        ready = [s["id"] for s in stages if s["id"] not in seen and set(s.get("needs", [])).issubset(seen)]
        if not ready:
            raise ResearchError("Cyclic stage dependency")
        seen.update(ready)
    producers = {p: s['id'] for s in stages for p in s['outputs']}
    def ancestors(sid):
        direct = set(next(s for s in stages if s['id'] == sid).get('needs', []))
        return direct | {a for d in direct for a in ancestors(d)}
    for s in stages:
        if set(s.get('requires', [])) & set(s['outputs']):
            raise ResearchError('Inputs and outputs must have distinct versioned paths')
        for p in s.get('requires', []) + s.get('optional', []):
            if p in producers and producers[p] not in ancestors(s['id']):
                raise ResearchError(f"Undeclared dependency for {s['id']}: {p}")
    policy = m.get("authorization", {})
    if "local" not in policy.get("effects", []):
        raise ResearchError("Declare authorization.effects including local")
    finite(m.get("budget", {}).get("seconds", 3600), "budget.seconds", 0.01)
    finite(m.get("budget", {}).get("cost", 0), "budget.cost", 0)
    policy = m.get('reproducibility', {})
    if not isinstance(policy, dict) or policy.get('mode', 'record') not in {'record', 'strict'}:
        raise ResearchError('reproducibility.mode must be record or strict')
    if policy.get('mode') == 'strict' and not policy.get('lock'):
        raise ResearchError('Strict reproducibility requires an environment lock')
    from .hci import validate_policy
    validate_policy(m)
    return m


class Store:
    def __init__(self, root):
        self.root = native_path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects = self.root / "objects"
        self.objects.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / "state.sqlite3", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute('PRAGMA synchronous=FULL')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 1:
            self.db.close()
            raise ResearchError('Store schema is newer than this runtime; refusing to downgrade')
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, manifest TEXT NOT NULL, state TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT NOT NULL,
            kind TEXT NOT NULL, payload TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS values_store(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memory_graphs(project TEXT PRIMARY KEY, revision INTEGER NOT NULL, snapshot TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memory_versions(project TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
            PRIMARY KEY(project, revision));
        CREATE TABLE IF NOT EXISTS memory_nodes(project TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(project,id));
        CREATE TABLE IF NOT EXISTS memory_edges(project TEXT NOT NULL, id TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL,
            relation TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(project,id));
        CREATE INDEX IF NOT EXISTS memory_edge_source ON memory_edges(project,source);
        CREATE INDEX IF NOT EXISTS memory_edge_target ON memory_edges(project,target);
        CREATE TABLE IF NOT EXISTS memory_outbox(snapshot TEXT NOT NULL, destination TEXT NOT NULL, body TEXT NOT NULL,
            PRIMARY KEY(snapshot,destination));
        """)
        self.db.execute('PRAGMA user_version=1')

    def close(self):
        self.db.close()

    @contextmanager
    def tx(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def put(self, data):
        key = digest(data)
        p = self.objects / key
        if p.exists():
            if digest(p.read_bytes()) != key:
                raise ResearchError("Corrupt content-addressed object")
        else:
            # Only a complete fsynced object is published under its content hash.
            # Staging lives outside objects so crashes cannot poison a hash name.
            staging = self.root / 'staging'
            staging.mkdir(exist_ok=True)
            fd, name = tempfile.mkstemp(dir=staging, prefix='cas-')
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                # Concurrent publishers hold identical bytes for this hash.
                if p.exists():
                    if digest(p.read_bytes()) != key:
                        raise ResearchError('Corrupt content-addressed object')
                else:
                    os.replace(name, p)
                    sync_directory(self.objects)
            finally:
                Path(name).unlink(missing_ok=True)
        return key

    def blob(self, key):
        if not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ResearchError("Invalid object hash")
        try:
            data = (self.objects / key).read_bytes()
        except FileNotFoundError as exc:
            raise ResearchError(f'Object missing: {key}') from exc
        if digest(data) != key:
            raise ResearchError(f"Object corrupted: {key}")
        return data

    def event(self, run, kind, payload):
        previous = self.db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = previous[0] if previous else "0" * 64
        data = {"time": time.time(), "data": payload}
        h = fingerprint([run, kind, data, previous])
        self.db.execute("INSERT INTO events(run,kind,payload,previous,hash) VALUES(?,?,?,?,?)",
                        (run, kind, canonical(data), previous, h))
        return h

    def get_value(self, key, default=None):
        row = self.db.execute("SELECT value FROM values_store WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_value(self, key, value):
        self.db.execute("INSERT INTO values_store VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, canonical(value)))

    def get(self, run):
        row = self.db.execute("SELECT * FROM runs WHERE id=?", (valid_id(run),)).fetchone()
        if not row:
            raise ResearchError(f"Unknown run: {run}")
        return json.loads(row["manifest"]), json.loads(row["state"])

    def save(self, run, state):
        from .hci import refresh
        manifest, _ = self.get(run)
        refresh(self, run, manifest, state)
        self.db.execute("UPDATE runs SET state=? WHERE id=?", (canonical(state), run))

    def work(self, run):
        return self.root / "runs" / valid_id(run) / "work"

    def files(self, directory):
        directory = native_path(directory)
        result = {}
        for current, dirs, filenames in os.walk(directory, followlinks=False):
            for name in sorted(dirs + filenames):
                p = Path(current) / name
                reparse = getattr(p.lstat(), 'st_file_attributes', 0) & 0x400 if os.name == 'nt' else 0
                if p.is_symlink() or reparse:
                    raise ResearchError(f"Snapshots do not follow symlinks/reparse points: {p}")
            for name in sorted(filenames):
                p = Path(current) / name
                name = p.relative_to(directory).as_posix()
                safe_path(directory, name)
                result[name] = self.put(p.read_bytes())
        return result

    def restore(self, files, dest):
        for name, key in files.items():
            p = safe_path(dest, name)
            p.parent.mkdir(parents=True, exist_ok=True)
            atomic_bytes(p, self.blob(key))

    def create(self, manifest, run=None, inputs=None, *, _inherited_pins=None):
        manifest = validate_manifest(manifest)
        run = valid_id(run or "run-" + uuid.uuid4().hex[:12])
        if self.db.execute("SELECT 1 FROM runs WHERE id=?", (run,)).fetchone() or self.work(run).exists():
            raise ResearchError("Run already exists")
        # Validate every input before any filesystem mutation.
        seeds = {name: Path(path).read_bytes() for name, path in (inputs or {}).items()}
        for name in seeds:
            safe_path(self.work(run), name)
            from .hci import reserved
            if reserved(name):
                raise ResearchError('Reserved runtime input directory')
        from .capabilities import pins
        selected, bundled = pins(self, manifest, inherited=_inherited_pins)
        seeds.update(bundled)
        self.work(run).mkdir(parents=True)
        for name, data in seeds.items():
            p = safe_path(self.work(run), name)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        state = {"status": "ready", "seconds": 0, "reserved_cost": 0, "worker": None,
                 "stages": {s["id"]: {"status": "pending", "attempts": 0} for s in manifest["stages"]},
                 "artifacts": {}, "inputs": self.files(self.work(run)), "annotations": [], "breakpoints": manifest.get("breakpoints", [])}
        state['artifacts'].update(state['inputs'])
        for sid, selected_bundle in selected.items(): state['stages'][sid]['capability_pin'] = selected_bundle
        with self.tx():
            self.db.execute("INSERT INTO runs VALUES(?,?,?)", (run, canonical(manifest), canonical(state)))
            self.event(run, "created", {"manifest": manifest, "inputs": state["inputs"], "version": 2})
            self.save(run, state)
        return run

    def control(self, run, action, reason="human control", stage=None):
        with self.tx():
            m, s = self.get(run)
            if action == "pause":
                if s["status"] in {"completed", "cancelled"}:
                    raise ResearchError("Terminal run cannot pause")
                s["status"] = "pause_requested" if s.get("worker") else "paused"
            elif action in {"resume", "step"}:
                from .hci import pending
                if pending(s) or s.get('intervention_hold'):
                    raise ResearchError('Resolve researcher feedback and review the current report before resuming')
                if s["status"] in {"completed", "cancelled"}:
                    raise ResearchError("Fork a terminal run to continue")
                if any(v["status"] == "running" for v in s["stages"].values()):
                    raise ResearchError("Wait for the current stage to reach its pause boundary")
                s["status"] = "ready"
                s["single_step"] = action == "step"
                s["bypass_breakpoint"] = s.pop('stopped_at', None)
            elif action == "cancel":
                if s["status"] == "completed":
                    raise ResearchError("Completed run cannot cancel")
                s["status"] = "cancel_requested" if s.get("worker") else "cancelled"
            elif action == "breakpoint":
                if stage not in s["stages"]:
                    raise ResearchError("Unknown stage")
                s["breakpoints"] = sorted(set(s["breakpoints"]) | {stage})
            elif action == "retry":
                if s['status'] == 'cancelled':
                    raise ResearchError('Cancelled runs are terminal; fork to retry')
                if s.get("worker") or stage not in s["stages"] or s["stages"][stage]["status"] != "failed":
                    raise ResearchError("Retry requires an idle failed stage")
                if s['stages'][stage].get('cleanup_pending') or s['stages'][stage].get('active_attempt'):
                    raise ResearchError('Recover and verify job cleanup before retrying')
                history = s['stages'][stage].setdefault('history', [])
                item = s['stages'][stage]
                history.append({k: v for k, v in item.items() if k not in {'history', 'report_history', 'feedback', 'feedback_resolutions'}})
                retained = {k: item[k] for k in ('history', 'report_history', 'feedback', 'feedback_resolutions', 'capability_pin') if k in item}
                s['stages'][stage] = {**retained, 'cycle': item.get('cycle', 1) + 1, 'status': 'pending', 'attempts': 0}
                s["status"] = "ready"
            else:
                raise ResearchError("Unknown control action")
            self.event(run, "control", {"action": action, "reason": reason, "stage": stage})
            self.save(run, s)
        return s

    def annotate(self, run, target, text, actor="human"):
        if not target or not text or not actor:
            raise ResearchError('Annotation needs target, text and actor')
        with self.tx():
            _, s = self.get(run)
            note = {"target": target, "text": text, "actor": actor, "time": time.time()}
            s["annotations"].append(note)
            self.event(run, "annotation", note)
            self.save(run, s)
        return note

    def finish(self, run, stage, actor="host-agent"):
        with self.tx():
            m, s = self.get(run)
            spec = next((x for x in m["stages"] if x["id"] == stage), None)
            if not spec or s["stages"][stage]["status"] != "awaiting_artifact":
                raise ResearchError("Only awaiting_artifact stages can be completed manually")
            if s.get('worker') or s['status'] == 'cancelled':
                raise ResearchError('Cannot submit while a worker owns the run or after cancellation')
            from .hci import validate_inputs
            validate_inputs(self, run, spec, s['stages'][stage])
            for name in spec.get('requires', []) + spec.get('optional', []):
                p = safe_path(self.work(run), name)
                expected = s['stages'][stage]['checkpoint'].get(name)
                observed = digest(p.read_bytes()) if p.is_file() else None
                if observed != expected or (name in spec.get('requires', []) and observed is None):
                    raise ResearchError(f'Input changed during manual stage: {name}')
            hashes = self.output_hashes(run, spec)
            s["artifacts"].update(hashes)
            s["stages"][stage].update(status="completed", outputs=hashes, actor=actor)
            s["status"] = "ready"
            self.event(run, "artifact_submitted", {"stage": stage, "outputs": hashes, "actor": actor, "scientific_verification": "not_implied"})
            self.save(run, s)
        return s

    def output_hashes(self, run, spec):
        result = {}
        for name in spec["outputs"]:
            p = safe_path(self.work(run), name)
            if not p.is_file() or p.stat().st_size == 0:
                raise ResearchError(f"Missing or empty output: {name}")
            if p.stat().st_size > spec.get('max_output_bytes', 100_000_000):
                raise ResearchError(f'Output exceeds declared byte limit: {name}')
            if p.suffix == ".json":
                read_json(p)
            result[name] = self.put(p.read_bytes())
        for check in spec.get('checks', []):
            if check['path'] not in spec['outputs']:
                raise ResearchError('Acceptance checks must reference declared outputs')
            value = read_json(safe_path(self.work(run), check['path']))
            try:
                for key in check.get('field', '').split('.'):
                    if key: value = value[int(key)] if isinstance(value, list) else value[key]
            except (KeyError, IndexError, ValueError, TypeError) as exc:
                raise ResearchError('Acceptance field missing') from exc
            if type(value) is not type(check['equals']) or value != check['equals']:
                raise ResearchError(f"Acceptance check failed: {check['path']}:{check.get('field')}")
        return result

    def fork(self, run, stage, changes=None, child=None):
        from .locking import resource_lock
        with resource_lock(self, 'run', run):
            return self._fork(run, stage, changes, child)

    def _fork(self, run, stage, changes=None, child=None):
        m, s = self.get(run)
        if s.get("worker") or any(v.get('active_attempt') or v.get('cleanup_pending') for v in s['stages'].values()):
            raise ResearchError("Pause and wait before forking")
        if stage not in s["stages"]:
            raise ResearchError("Unknown fork stage")
        affected = {stage}
        while True:
            nxt = affected | {x["id"] for x in m["stages"] if set(x.get("needs", [])) & affected}
            if nxt == affected:
                break
            affected = nxt
        patches = changes or {}
        # Only stage configuration can change here. Authorization/budget amendments use a new manifest.
        if not set(patches).issubset(affected):
            raise ResearchError("Changes must target the affected branch")
        for spec in m["stages"]:
            if spec["id"] in patches:
                if set(patches[spec["id"]]) - {"command", "timeout", "requires", "optional", "outputs", "instructions", "milestone", "milestone_id", "rationale", "goal", "alternatives", "review_questions"}:
                    raise ResearchError("Unsupported fork patch key")
                spec.update(patches[spec["id"]])
        validate_manifest(m)
        inherited = {sid: item['capability_pin'] for sid, item in s['stages'].items() if item.get('capability_pin')}
        child = self.create(m, child, _inherited_pins=inherited)
        _, cs = self.get(child)
        # Start from the actual pre-intervention checkpoint, not the final mutated directory.
        base = s["stages"][stage].get("checkpoint", s["inputs"])
        self.restore(base, self.work(child))
        cs['artifacts'].update(base)
        for key, item in s["stages"].items():
            if key not in affected and item["status"] == "completed":
                self.restore(item["outputs"], self.work(child))
                cs["stages"][key] = item
                cs['stages'][key]['inherited_from'] = {'run': run, 'stage': key, 'outputs': item['outputs']}
                cs["artifacts"].update(item["outputs"])
        cs.update(parent=run, intervention={"stage": stage, "affected": sorted(affected), "changes": patches,
                  "state_fidelity": "workspace_files_only", "external_state": "not_restored"}, inputs=self.files(self.work(child)))
        with self.tx():
            self.save(child, cs)
            self.event(child, "fork", {"parent": run, "intervention": cs["intervention"], "input_hashes": cs["inputs"]})
        return child

    def import_archive(self, directory, run=None):
        checked = verify_archive(directory)
        if not checked['valid']:
            raise ResearchError('Archive verification failed: ' + ', '.join(checked['errors']))
        directory = native_path(directory)
        bundle = read_json(directory / 'archive.json')
        for h in bundle.get('objects', []):
            self.put((directory / 'objects' / h).read_bytes())
        inherited = {sid: item['capability_pin'] for sid, item in bundle['state']['stages'].items() if item.get('capability_pin')}
        run = self.create(bundle['manifest'], run, _inherited_pins=inherited)
        self.restore(bundle['files'], self.work(run))
        state = bundle['state']
        state.update(worker=None, imported_from=bundle['run'])
        for item in state['stages'].values():
            if item['status'] == 'running': item.update(status='failed', error='interrupted before archive import')
        if state['status'] in {'running', 'pause_requested', 'cancel_requested'}: state['status'] = 'blocked'
        with self.tx():
            self.save(run, state)
            self.event(run, 'archive_imported', {'source_run': bundle['run'], 'archive_hash': fingerprint(bundle),
                       'prior_events': bundle['events'], 'external_state_restored': False})
        return run

    def events(self, run=None):
        query = "SELECT * FROM events" + (" WHERE run=?" if run else "") + " ORDER BY seq"
        return [{**dict(r), "payload": json.loads(r["payload"])} for r in self.db.execute(query, (run,) if run else ())]

    def verify(self):
        previous, errors = "0" * 64, []
        integrity = [r[0] for r in self.db.execute('PRAGMA quick_check')]
        if integrity != ['ok']:
            errors.extend('sqlite:' + v for v in integrity)
        for e in self.events():
            h = fingerprint([e["run"], e["kind"], e["payload"], previous])
            if e["previous"] != previous or h != e["hash"]:
                errors.append(f"event:{e['seq']}")
            previous = e["hash"]
        for p in self.objects.iterdir():
            if not p.is_file() or digest(p.read_bytes()) != p.name:
                errors.append(f"object:{p.name}")
        for row in self.db.execute('SELECT id,state FROM runs'):
            state = json.loads(row['state'])
            maps = [state.get('inputs', {}), state.get('artifacts', {})]
            for stage in state['stages'].values():
                maps.extend(stage.get(k, {}) for k in ('checkpoint', 'outputs', 'log_hashes'))
                for receipt in stage.get('report_history', []):
                    maps.append({k: receipt[k] for k in ('json', 'markdown')})
                if stage.get('explanation'): maps.append({'explanation': stage['explanation']['object']})
            for hashes in maps:
                for key in hashes.values():
                    try: self.blob(key)
                    except (ResearchError, OSError): errors.append('missing_or_corrupt_reference:' + row['id'] + ':' + str(key))
        for row in self.db.execute('SELECT snapshot FROM memory_versions'):
            try: self.blob(row['snapshot'])
            except (ResearchError, OSError): errors.append('memory_snapshot:' + row['snapshot'])
        for row in self.db.execute("SELECT key,value FROM values_store WHERE key LIKE 'capability:%' OR key LIKE 'proposal:%'"):
            record = json.loads(row['value'])
            bundles = ([record['active']] + record['history']) if row['key'].startswith('capability:') else [record['candidate']]
            keys = {key for bundle in bundles for key in bundle['files'].values()}
            keys.update(source['report_hash'] for source in record.get('sources', []))
            for key in keys:
                try: self.blob(key)
                except (ResearchError, OSError): errors.append('capability_reference:' + row['key'] + ':' + key)
        return {"valid": not errors, "errors": errors, "integrity_only": True, "security_seal": False}

    def archive(self, run):
        from .locking import resource_lock
        with resource_lock(self, 'run', run):
            return self._archive(run)

    def _archive(self, run):
        m, s = self.get(run)
        if s.get("worker") or any(v.get('active_attempt') or v.get('cleanup_pending') for v in s['stages'].values()):
            raise ResearchError("Pause worker before archiving")
        files = self.files(self.work(run))
        # Archive bookkeeping does not change the scientific snapshot. Preserve historical CAS
        # objects as well, so checkpoints remain recoverable without the original store.
        events = [e for e in self.events(run) if e['kind'] != 'archive']
        referenced = set(files.values())
        def collect(value):
            if isinstance(value, dict):
                for v in value.values(): collect(v)
            elif isinstance(value, list):
                for v in value: collect(v)
            elif isinstance(value, str) and re.fullmatch(r'[a-f0-9]{64}', value) and (self.objects / value).is_file():
                referenced.add(value)
        collect(s)
        collect(events)
        bundle = {"version": 2, "run": run, "manifest": m, "state": s, "files": files, "events": events,
                  'objects': sorted(referenced), 'event_chain': 'global chain fragments; full chain verified in source store'}
        key = fingerprint(bundle)
        dest = self.root / "archives" / key
        if dest.exists():
            return {"archive": str(dest), "unchanged": True}
        temp = dest.with_name('.pending-' + uuid.uuid4().hex[:12])
        temp.mkdir(parents=True)
        self.restore(files, temp / "artifacts")
        (temp / 'objects').mkdir()
        for h in referenced:
            (temp / 'objects' / h).write_bytes(self.blob(h))
        write_json(temp / "archive.json", bundle)
        (temp / ".done").write_text(key, encoding="utf-8")
        os.replace(temp, dest)
        with self.tx():
            self.event(run, "archive", {"digest": key, "files": len(files)})
        return {"archive": str(dest), "digest": key}


def verify_archive(directory):
    directory = native_path(directory)
    bundle = read_json(directory / "archive.json")
    errors = []
    if (directory / ".done").read_text(encoding="utf-8") != fingerprint(bundle):
        errors.append("manifest digest mismatch")
    for name, h in bundle["files"].items():
        p = safe_path(directory / "artifacts", name)
        if not p.is_file() or digest(p.read_bytes()) != h:
            errors.append(name)
    for h in bundle.get('objects', []):
        p = safe_path(directory / 'objects', h)
        if not p.is_file() or digest(p.read_bytes()) != h:
            errors.append('object:' + h)
    return {"valid": not errors, "errors": errors, "files": len(bundle["files"])}


def compare_runs(store, left, right):
    lm, ls = store.get(left)
    rm, rs = store.get(right)
    def milestones(manifest):
        result = {}
        for stage in manifest['stages']:
            key = ('id', stage['milestone_id']) if stage.get('milestone_id') else ('label', stage['milestone']) if stage.get('milestone') else None
            if key: result.setdefault(key, []).append(stage['id'])
        return result
    la, ra = milestones(lm), milestones(rm)
    aligned, used_left, used_right, conflicts = [], set(), set(), []
    for key in sorted(set(la) & set(ra)):
        # Ambiguous repeated milestones remain separate; do not infer a pairing.
        if len(la[key]) == len(ra[key]) == 1:
            a, b = la[key][0], ra[key][0]
            aligned.append({'left_stage': a, 'right_stage': b, 'by': 'declared_milestone', 'milestone': {'kind': key[0], 'value': key[1]},
                            'left': ls['stages'][a], 'right': rs['stages'][b]})
            used_left.add(a); used_right.add(b)
    for key in sorted(set(ls['stages']) & set(rs['stages'])):
        if key not in used_left and key not in used_right:
            left_spec = next(x for x in lm['stages'] if x['id'] == key)
            right_spec = next(x for x in rm['stages'] if x['id'] == key)
            if left_spec.get('milestone_id') and right_spec.get('milestone_id') and left_spec['milestone_id'] != right_spec['milestone_id']:
                conflicts.append({'stage_id': key, 'left_milestone_id': left_spec['milestone_id'], 'right_milestone_id': right_spec['milestone_id'], 'action': 'left_unaligned'})
                continue
            aligned.append({'left_stage': key, 'right_stage': key, 'by': 'stage_id',
                            'left': ls['stages'][key], 'right': rs['stages'][key]})
            used_left.add(key); used_right.add(key)
    return {"same_objective": lm["objective"] == rm["objective"],
            'alignments': aligned, 'alignment_conflicts': conflicts, 'unmatched_left': sorted(set(ls['stages']) - used_left),
            'unmatched_right': sorted(set(rs['stages']) - used_right),
            'alignment_scope': 'exact human-declared milestone ID/label or stage ID; does not prove equivalent estimands or execution',
            "stages": [{"id": k, "left": ls["stages"].get(k), "right": rs["stages"].get(k)}
                       for k in sorted(set(ls["stages"]) | set(rs["stages"]))],
            "changed_artifacts": [k for k in sorted(set(ls["artifacts"]) | set(rs["artifacts"]))
                                  if ls["artifacts"].get(k) != rs["artifacts"].get(k)],
            "causal_conclusion": "requires matched repeated controls and intervention-fidelity checks"}
