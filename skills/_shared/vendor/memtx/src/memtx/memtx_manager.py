"""
MemTX MemoryManager: full transactional belief commit protocol.
Implements staged write, lifecycle, visibility control, semantic conflict detection,
commit/abort, snapshot read, and cascading rollback/repair.
"""
from __future__ import annotations
import time
import uuid
from datetime import date, datetime
from dataclasses import dataclass, field
from typing import Any, Optional

from schema import MemoryRecord, MemoryState, IsolationLevel, ISOLATION_VISIBLE_STATES
from memory_manager import MemoryManager
from memtx.state_machine import transition, MemoryStateError
from memtx.conflict_detector import ConflictResult, SemanticConflictDetector
from memtx.dependency_graph import DependencyGraph


RISK_TO_ISOLATION = {
    "low": IsolationLevel.COMMITTED_READ,
    "medium": IsolationLevel.VERIFIED_READ,
    "high": IsolationLevel.CAUSALLY_STABLE_READ,
    "external_action": IsolationLevel.ACTION_SAFE_READ,
}


@dataclass
class Transaction:
    tx_id: str
    task_id: str
    agent_id: str
    risk_level: str
    isolation: IsolationLevel
    snapshot_ids: list[str] = field(default_factory=list)  # memory_ids read at tx start
    staged: list[str] = field(default_factory=list)        # memory_ids staged in this tx
    tool_effects: list[dict] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    status: str = "open"   # "open" | "committed" | "aborted"


class MemTXManager(MemoryManager):
    """Full MemTX implementation."""

    def __init__(self, evidence_threshold: float = 0.6,
                 authority_bypass: float = 0.9,
                 isolation_override: Optional[IsolationLevel] = None):
        self._store: dict[str, MemoryRecord] = {}     # memory_id -> record
        self._txns: dict[str, Transaction] = {}
        self._dep_graph = DependencyGraph()
        self._conflict_detector = SemanticConflictDetector()
        self._revoked_ids: set[str] = set()
        # Both evidence-check cuts are constructor-level config so the
        # sensitivity sweep (scripts/run_threshold_sweep.py) can exercise them;
        # every experiment column uses the defaults. Survives reset().
        self._evidence_threshold = evidence_threshold
        self._authority_bypass = authority_bypass
        # Pins every transaction's isolation level regardless of risk_level —
        # used only by the isolation-level sweep (spec Table 3, Raw→Action-Safe
        # tradeoff). None => the normal risk mapping applies. Survives reset()
        # like every other constructor-level config.
        self._isolation_override = isolation_override
        self._verifier_calls: int = 0
        # Logical "now" for a scenario (ISO 8601). None => validity checking is
        # disabled so cases that don't opt in behave exactly as before. Set by the
        # runner from the case's optional top-level `sim_now`, never wall-clock, so
        # scripted runs stay deterministic.
        self._sim_now: Optional[str] = None

    def set_sim_now(self, sim_now: Optional[str]) -> None:
        self._sim_now = sim_now

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def begin_tx(self, task_id: str, agent_id: str, risk_level: str) -> str:
        tx_id = f"tx_{uuid.uuid4().hex[:8]}"
        isolation = self._isolation_override or RISK_TO_ISOLATION.get(
            risk_level, IsolationLevel.COMMITTED_READ)
        tx = Transaction(
            tx_id=tx_id,
            task_id=task_id,
            agent_id=agent_id,
            risk_level=risk_level,
            isolation=isolation,
        )
        # Capture snapshot ids at tx start
        tx.snapshot_ids = [
            mid for mid, rec in self._store.items()
            if rec.is_visible_at(isolation)
        ]
        self._txns[tx_id] = tx
        return tx_id

    def action_safe_check(self, tx_id: str, tool_name: str) -> dict:
        """
        Check whether an irreversible tool call can proceed.
        Blocks if: unresolved TENTATIVE memories exist outside this tx's snapshot
        (dirty tentative data in flight that the agent cannot see at committed-read
        isolation, but that might affect the action).
        Returns {"allow": bool, "reason": str}.
        """
        from mock_tools import IRREVERSIBLE_TOOLS
        if tool_name not in IRREVERSIBLE_TOOLS:
            return {"allow": True, "reason": "not_irreversible"}
        tx = self._txns.get(tx_id)
        if not tx:
            return {"allow": False, "reason": "no_active_transaction"}

        snapshot_set = set(tx.snapshot_ids)

        # Block if any TENTATIVE memory exists outside this tx's snapshot.
        # These are dirty writes from other agents that are unresolved.
        unresolved_tentative = [
            mid for mid, rec in self._store.items()
            if rec.state == MemoryState.TENTATIVE
            and mid not in snapshot_set
        ]
        if unresolved_tentative:
            return {
                "allow": False,
                "reason": "dirty_tentative_memory_in_flight_blocks_irreversible_action",
            }

        # For external_action risk, require at least ACTION_SAFE support
        retrieved_safe = [
            mid for mid in snapshot_set
            if self._store.get(mid) and self._store[mid].state == MemoryState.ACTION_SAFE
        ]
        if tx.risk_level == "external_action" and not retrieved_safe:
            return {"allow": False, "reason": "no_action_safe_memory_to_support_irreversible_tool"}

        return {"allow": True, "reason": "ok"}

    def retrieve(
        self,
        tx_id: str,
        query: str,
        requester: dict,
        purpose: str,
        top_k: int = 8,
    ) -> list[dict]:
        tx = self._txns.get(tx_id)
        if not tx:
            return []
        isolation = tx.isolation
        agent_roles = requester.get("permissions", []) + [requester.get("role", "")]

        results = []
        for mid, rec in self._store.items():
            if not rec.is_visible_at(isolation):
                continue
            if mid in self._revoked_ids:
                continue
            # Permission check
            if rec.permission:
                allowed = set(rec.permission.read_roles)
                if allowed and not any(r in allowed for r in agent_roles):
                    continue
            # Causally stable read: exclude if any ancestor is invalidated
            if isolation == IsolationLevel.CAUSALLY_STABLE_READ:
                if self._dep_graph.has_pending_invalidation([mid], self._revoked_ids):
                    continue
            results.append(rec.to_dict())
        return results[:top_k]

    def stage_write(
        self,
        tx_id: str,
        observation: dict,
        extracted_memory: list[dict],
    ) -> list[str]:
        tx = self._txns.get(tx_id)
        if not tx:
            return []
        staged_ids = []
        for m_dict in extracted_memory:
            rec = MemoryRecord.from_dict(m_dict)
            # All writes start as RAW then move to TENTATIVE
            rec.state = MemoryState.RAW
            rec.tx_id = tx_id
            transition(rec, MemoryState.TENTATIVE)
            rec.version = 0
            self._store[rec.memory_id] = rec
            tx.staged.append(rec.memory_id)
            staged_ids.append(rec.memory_id)
            if rec.derived_from:
                self._dep_graph.add_edges_for_record(rec.memory_id, rec.derived_from)
        return staged_ids

    def validate_and_commit(self, tx_id: str) -> dict:
        tx = self._txns.get(tx_id)
        if not tx or tx.status != "open":
            return {"status": "error", "reason": "tx not found or not open"}

        committed_ids = []
        aborted_ids = []
        violations = []

        for mid in list(tx.staged):
            rec = self._store.get(mid)
            if not rec:
                continue
            # Recomputed per record: a commit earlier in this same batch is an
            # active belief for the records after it, so two contradictory
            # records staged in one tx cannot both slip through.
            active_beliefs = self._active_beliefs()

            # 0. A staged record can be retracted before its tx commits (e.g. a
            # cascade from an aborted ancestor revoked it). Nothing to promote.
            if rec.state != MemoryState.TENTATIVE:
                aborted_ids.append(mid)
                violations.append(f"already_retracted_before_commit:{mid}")
                continue

            # 1. Evidence support check
            if not self._check_evidence(rec):
                transition(rec, MemoryState.QUARANTINED)
                aborted_ids.append(mid)
                violations.append(f"insufficient_evidence:{mid}")
                continue

            # 2. Validity interval check: a fact that is expired or not-yet-valid at
            # the scenario's logical `now` must not enter the belief store.
            valid, why = self._check_validity_interval(rec)
            if not valid:
                transition(rec, MemoryState.QUARANTINED)
                aborted_ids.append(mid)
                violations.append(f"{why}:{mid}")
                continue

            # 3. Semantic conflict detection (passes tx snapshot for stale-write
            # detection). Kept behind a hook so ablation variants can swap
            # exactly this step without copying the surrounding commit protocol.
            conflict = self._detect_conflict(rec, active_beliefs, tx)
            if conflict.conflict:
                if conflict.recommended == "abort":
                    transition(rec, MemoryState.QUARANTINED)
                    aborted_ids.append(mid)
                    violations.append(f"{conflict.conflict_type}:{mid}")
                    continue
                elif conflict.recommended == "supersede_old":
                    for old_id in conflict.conflicting_ids:
                        old = self._store.get(old_id)
                        if old and old.state in (MemoryState.COMMITTED, MemoryState.ACTION_SAFE):
                            try:
                                transition(old, MemoryState.SUPERSEDED)
                            except MemoryStateError:
                                pass
                elif conflict.recommended == "ask_user":
                    transition(rec, MemoryState.QUARANTINED)
                    aborted_ids.append(mid)
                    violations.append(f"conflict_needs_user_review:{mid}")
                    continue

            # 4. Dependency stability check
            if not self._check_dependency_stability(mid):
                transition(rec, MemoryState.QUARANTINED)
                aborted_ids.append(mid)
                violations.append(f"unstable_dependency:{mid}")
                continue

            # 5. Commit
            transition(rec, MemoryState.VALIDATED)
            if tx.risk_level == "external_action":
                transition(rec, MemoryState.COMMITTED)
                transition(rec, MemoryState.ACTION_SAFE)
            else:
                transition(rec, MemoryState.COMMITTED)
            rec.version += 1
            committed_ids.append(mid)

        tx.status = "committed" if not aborted_ids else ("partial" if committed_ids else "aborted")
        status = "committed" if not aborted_ids else ("partial" if committed_ids else "aborted")
        return {
            "status": status,
            "committed_ids": committed_ids,
            "aborted_ids": aborted_ids,
            "violations": violations,
        }

    def _detect_conflict(self, rec: MemoryRecord, active_beliefs: list[MemoryRecord],
                         tx: "Transaction") -> ConflictResult:
        """Commit-step conflict check — the single override point for ablation
        variants (ablation_manager), so removing one feature never requires
        copying the surrounding commit protocol."""
        self._verifier_calls += 1
        return self._conflict_detector.detect(
            rec, active_beliefs, self._revoked_ids, tx.snapshot_ids
        )

    def _check_dependency_stability(self, mid: str) -> bool:
        """Commit-step ancestry check, behind a hook like `_detect_conflict` so an
        ablation variant can remove exactly this gate. Read-time causal stability
        (CAUSALLY_STABLE_READ in `retrieve`) deliberately does not route through
        here: an ablation of the commit gate must not weaken the read path."""
        return not self._dep_graph.has_pending_invalidation([mid], self._revoked_ids)

    def abort_or_rollback(self, tx_id: str, reason: str) -> dict:
        """Revoke a transaction's staged records and cascade-repair their dependents.

        Cascading here (not just in abort_memory) keeps the repair invariant
        path-independent: a record that committed on the strength of a staged
        parent must not stay active when that parent is retracted by tx abort.
        """
        tx = self._txns.get(tx_id)
        rolled_back: list[str] = []
        rollback_log: list[dict] = []
        if tx:
            for mid in tx.staged:
                rec = self._store.get(mid)
                if rec and rec.state not in (MemoryState.REVOKED, MemoryState.SUPERSEDED):
                    try:
                        transition(rec, MemoryState.REVOKED)
                    except MemoryStateError:
                        continue
                    self._revoked_ids.add(mid)
                    rolled_back.append(mid)
                    rollback_log.append({"memory_id": mid, "node_type": rec.node_type,
                                         "action": "revoked", "root": True})
                    self._cascade_descendants(mid, rolled_back, rollback_log)
            tx.status = "aborted"
        return {"status": "aborted", "rolled_back_ids": rolled_back, "rollback_log": rollback_log}

    # Derived views/copies are invalidated (must be rebuilt), not semantically revoked.
    _INVALIDATE_NODE_TYPES = {"summary", "profile", "index_entry", "shared_copy"}

    def abort_memory(self, memory_id: str, reason: str) -> dict:
        """Revoke a committed memory and cascade repair to its dependents by node type.

        Unlike a uniform revoke, each descendant is repaired according to its node type:
        derived views (summary/profile/index/shared_copy) are *invalidated* (need rebuild),
        beliefs are *revoked*, and executed tool effects are *compensated* if reversible or
        flagged as an irreversible leak if not. A rollback_log records the (node, action)
        edges so the repair is auditable. Regardless of the terminal state, every cascaded
        id is added to the revoked set and rolled_back list, so downstream visibility and
        rollback accounting are unchanged from a uniform revoke.
        """
        rec = self._store.get(memory_id)
        if not rec:
            return {"status": "not_found"}
        rolled_back: list[str] = []
        rollback_log: list[dict] = []
        try:
            transition(rec, MemoryState.REVOKED)
            self._revoked_ids.add(memory_id)
            rolled_back.append(memory_id)
            rollback_log.append({"memory_id": memory_id, "node_type": rec.node_type,
                                 "action": "revoked", "root": True})
        except MemoryStateError:
            return {"status": "illegal_transition", "memory_id": memory_id}

        self._cascade_descendants(memory_id, rolled_back, rollback_log)
        return {"status": "revoked", "rolled_back_ids": rolled_back, "rollback_log": rollback_log}

    def _cascade_descendants(self, root_id: str,
                             rolled_back: list[str], rollback_log: list[dict]) -> None:
        """Typed cascade repair over all transitive dependents of root_id.

        Shared by both revocation paths (abort_memory and tx-level
        abort_or_rollback) so the cascade-repair invariant holds regardless of
        how a record was retracted.
        """
        for desc_id in self._dep_graph.descendants(root_id):
            desc = self._store.get(desc_id)
            if not desc or desc.state in (MemoryState.REVOKED, MemoryState.SUPERSEDED):
                continue
            entry = self._repair_descendant(desc)
            if entry is not None:
                self._revoked_ids.add(desc_id)
                rolled_back.append(desc_id)
                rollback_log.append(entry)

    def _repair_descendant(self, desc: MemoryRecord) -> Optional[dict]:
        """Repair one cascaded descendant according to its node type.

        Returns a rollback_log entry, or None if the node could not be transitioned to a
        terminal state at all (left untouched, not counted as rolled back).
        """
        entry = {"memory_id": desc.memory_id, "node_type": desc.node_type}
        if desc.node_type == "tool_action":
            comp = self.compensate(desc)
            entry.update(comp)
            target = MemoryState.REVOKED
        elif desc.node_type in self._INVALIDATE_NODE_TYPES:
            entry["action"] = "invalidated"
            target = MemoryState.QUARANTINED
        else:  # belief (default)
            entry["action"] = "revoked"
            target = MemoryState.REVOKED
        try:
            transition(desc, target)
        except MemoryStateError:
            # e.g. ACTION_SAFE cannot go QUARANTINED — fall back to REVOKED so the
            # invalidated view is still removed from the belief store.
            try:
                transition(desc, MemoryState.REVOKED)
            except MemoryStateError:
                return None
        return entry

    def compensate(self, desc: MemoryRecord) -> dict:
        """Decide the compensating action for a rolled-back tool-effect node.

        Reversible effects get a logged compensation; irreversible ones cannot be undone
        and are flagged as a leak (a real harm the benchmark should surface). This records
        the decision; actually replaying the compensating tool call is out of scope here
        (it would require the tool environment) and is left to the runner layer.
        """
        from mock_tools import IRREVERSIBLE_TOOLS
        tool = desc.source.tool_name if desc.source else None
        if tool and tool in IRREVERSIBLE_TOOLS:
            return {"action": "irreversible_effect_leaked", "tool": tool}
        return {"action": "compensated", "tool": tool}

    def record_tool_effect(self, tx_id: str, tool_name: str, args: dict, result: dict) -> None:
        tx = self._txns.get(tx_id)
        if tx:
            tx.tool_effects.append({"tool": tool_name, "args": args, "result": result})

    def current_belief_view(self, requester: dict, purpose: str) -> list[dict]:
        agent_roles = requester.get("permissions", []) + [requester.get("role", "")]
        result = []
        for mid, rec in self._store.items():
            if rec.state not in (MemoryState.COMMITTED, MemoryState.ACTION_SAFE):
                continue
            if mid in self._revoked_ids:
                continue
            if rec.permission:
                allowed = set(rec.permission.read_roles)
                if allowed and not any(r in allowed for r in agent_roles):
                    continue
            result.append(rec.to_dict())
        return result

    def reset(self) -> None:
        self._store.clear()
        self._txns.clear()
        self._dep_graph.reset()
        self._revoked_ids.clear()
        self._verifier_calls = 0
        self._sim_now = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _active_beliefs(self) -> list[MemoryRecord]:
        return [
            rec for mid, rec in self._store.items()
            if rec.state in (MemoryState.COMMITTED, MemoryState.ACTION_SAFE,
                             MemoryState.VALIDATED)
            and mid not in self._revoked_ids
        ]

    @staticmethod
    def _parse_iso(value: Optional[str]) -> Optional[date]:
        """Parse an ISO 8601 date or datetime into a comparable date.

        Returns None on missing/unparseable input so a malformed bound is treated as
        'no bound' rather than silently blocking a write. Comparison is at date
        granularity, which is what the scenario validity windows use.
        """
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None

    def _check_validity_interval(self, rec: MemoryRecord) -> tuple[bool, str]:
        """Reject records whose validity window does not contain the scenario's `now`.

        No-op (always valid) when the case did not set `sim_now`, so cases that don't
        opt in are unaffected. A record with no validity bounds is always valid.
        """
        now = self._parse_iso(self._sim_now)
        if now is None or rec.validity is None:
            return True, ""
        valid_from = self._parse_iso(rec.validity.valid_from)
        valid_until = self._parse_iso(rec.validity.valid_until)
        if valid_until is not None and now > valid_until:
            return False, "validity_expired"
        if valid_from is not None and now < valid_from:
            return False, "validity_not_yet_valid"
        return True, ""

    def _check_evidence(self, rec: MemoryRecord) -> bool:
        """
        Low-authority writers must self-report confidence at or above the
        evidence threshold; sources at or above the authority-bypass level are
        exempt (user and system input, and high-trust tools such as the tau2
        middleware's extractions). Both cuts are inclusive. The check is the
        cheap first line of defense-in-depth: records it rejects are
        quarantined before any metered conflict adjudication runs.
        """
        if rec.source and rec.source.authority >= self._authority_bypass:
            return True
        return rec.confidence >= self._evidence_threshold

    def pre_load_memory(self, records: list[MemoryRecord]) -> None:
        """Load initial scenario memory directly (used by scenario runner)."""
        for rec in records:
            self._store[rec.memory_id] = rec
            if rec.derived_from:
                self._dep_graph.add_edges_for_record(rec.memory_id, rec.derived_from)
            if rec.state == MemoryState.REVOKED:
                self._revoked_ids.add(rec.memory_id)
