"""
Semantic conflict detector: checks candidate memory against active beliefs.
Returns conflict type and severity without calling an LLM (rule-based).
LLM-based detection can be plugged in via the llm_judge parameter.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from schema import MemoryRecord, MemoryState


def _parse_iso(value: Optional[str]) -> Optional[date]:
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


def _validity_disjoint(a: MemoryRecord, b: MemoryRecord) -> bool:
    """True if a and b both carry a validity window and those windows do not overlap.

    An open bound (None) extends to infinity on that side. Two facts about the same
    slot with disjoint validity describe different time windows and can coexist —
    they are not in conflict, analogous to different scopes.
    """
    av = a.validity
    bv = b.validity
    if av is None or bv is None:
        return False
    a_from, a_until = _parse_iso(av.valid_from), _parse_iso(av.valid_until)
    b_from, b_until = _parse_iso(bv.valid_from), _parse_iso(bv.valid_until)
    # Require at least one real bound on each side; otherwise "disjoint" is meaningless.
    if (a_from is None and a_until is None) or (b_from is None and b_until is None):
        return False
    # Overlap iff a starts before b ends AND b starts before a ends (open = infinity).
    a_before_b_ends = (b_until is None) or (a_from is None) or (a_from <= b_until)
    b_before_a_ends = (a_until is None) or (b_from is None) or (b_from <= a_until)
    overlap = a_before_b_ends and b_before_a_ends
    return not overlap


@dataclass
class ConflictResult:
    conflict: bool
    conflict_type: str   # see below
    conflicting_ids: list[str]
    severity: str        # "none" | "low" | "medium" | "high"
    recommended: str     # "commit" | "supersede_old" | "quarantine" | "ask_user" | "abort"


CONFLICT_NONE = "none"
CONFLICT_ENTITY_ATTR = "entity_attribute"
CONFLICT_TEMPORAL = "temporal_override"
CONFLICT_SCOPE = "scope_conflict"
CONFLICT_PERMISSION = "permission"
CONFLICT_AUTHORITY = "source_authority"
CONFLICT_DERIVED_REVOKED = "derived_revoked"


class SemanticConflictDetector:

    def detect(
        self,
        candidate: MemoryRecord,
        active_beliefs: list[MemoryRecord],
        revoked_ids: set[str],
        tx_snapshot_ids: list[str] | None = None,
    ) -> ConflictResult:
        # 1. Check if candidate derives from a revoked source
        for parent in candidate.derived_from:
            if parent in revoked_ids:
                return ConflictResult(
                    conflict=True,
                    conflict_type=CONFLICT_DERIVED_REVOKED,
                    conflicting_ids=[parent],
                    severity="high",
                    recommended="abort",
                )

        # 2. Permission laundering: private source -> any broader target (shared or public).
        # Boundary: the parent is looked up among ACTIVE beliefs only — laundering from a
        # still-TENTATIVE private parent inside the same tx is not caught here (it is
        # caught later: the parent either commits, making the next derivation detectable,
        # or is retracted, cascading the child). Widening this lookup would change
        # committed results and needs a full rerun — keep the boundary explicit instead.
        if (candidate.permission and candidate.permission.share_scope != "private"
                and candidate.derived_from):
            for parent_id in candidate.derived_from:
                parent = self._find_belief(parent_id, active_beliefs)
                if parent and parent.permission and parent.permission.share_scope == "private":
                    return ConflictResult(
                        conflict=True,
                        conflict_type=CONFLICT_PERMISSION,
                        conflicting_ids=[parent_id],
                        severity="high",
                        recommended="abort",
                    )

        # 3. Find same entity+attribute beliefs
        same_slot = [
            b for b in active_beliefs
            if (b.entity == candidate.entity
                and b.attribute == candidate.attribute
                and b.state in (MemoryState.COMMITTED, MemoryState.ACTION_SAFE,
                                MemoryState.VALIDATED))
        ]
        if not same_slot:
            return ConflictResult(False, CONFLICT_NONE, [], "none", "commit")

        # 4. Scoped override — different scopes coexist
        if candidate.scope and all(b.scope != candidate.scope for b in same_slot):
            return ConflictResult(False, CONFLICT_SCOPE, [], "none", "commit")

        # 4b. Temporal coexistence — same slot but disjoint validity windows describe
        # different time periods, so they are not in conflict (like different scopes).
        if all(_validity_disjoint(candidate, b) for b in same_slot):
            return ConflictResult(False, CONFLICT_NONE, [], "none", "commit")

        snapshot_set = set(tx_snapshot_ids) if tx_snapshot_ids else set()

        # 5. Temporal supersession — higher authority / newer source wins
        for existing in same_slot:
            if str(existing.value) == str(candidate.value):
                # Same value — idempotent update
                return ConflictResult(False, CONFLICT_NONE, [], "none", "commit")

            cand_auth = (candidate.source.authority if candidate.source else 0.5)
            exist_auth = (existing.source.authority if existing.source else 0.5)
            cand_src = (candidate.source.id if candidate.source else "")
            exist_src = (existing.source.id if existing.source else "")

            # Stale-late-write: existing belief was committed AFTER this tx started
            # (not in the tx's original snapshot) -> candidate is stale
            if snapshot_set and existing.memory_id not in snapshot_set:
                return ConflictResult(
                    conflict=True,
                    conflict_type=CONFLICT_TEMPORAL,
                    conflicting_ids=[existing.memory_id],
                    severity="high",
                    recommended="abort",
                )

            if cand_auth > exist_auth:
                return ConflictResult(
                    conflict=True,
                    conflict_type=CONFLICT_TEMPORAL,
                    conflicting_ids=[existing.memory_id],
                    severity="medium",
                    recommended="supersede_old",
                )
            elif cand_auth < exist_auth:
                return ConflictResult(
                    conflict=True,
                    conflict_type=CONFLICT_AUTHORITY,
                    conflicting_ids=[existing.memory_id],
                    severity="high",
                    recommended="abort",
                )
            else:
                # Equal authority — same source is a user correction (supersede)
                # Different source with equal authority is ambiguous (ask_user)
                if cand_src == exist_src:
                    return ConflictResult(
                        conflict=True,
                        conflict_type=CONFLICT_TEMPORAL,
                        conflicting_ids=[existing.memory_id],
                        severity="low",
                        recommended="supersede_old",
                    )
                return ConflictResult(
                    conflict=True,
                    conflict_type=CONFLICT_ENTITY_ATTR,
                    conflicting_ids=[existing.memory_id],
                    severity="medium",
                    recommended="ask_user",
                )

        return ConflictResult(False, CONFLICT_NONE, [], "none", "commit")

    def _find_belief(self, memory_id: str, beliefs: list[MemoryRecord]) -> Optional[MemoryRecord]:
        for b in beliefs:
            if b.memory_id == memory_id:
                return b
        return None
