"""
Unified memory candidate schema for MemTX and all baselines.
All methods share this schema so comparisons are fair.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import uuid
import time


class MemoryState(str, Enum):
    RAW = "raw"
    TENTATIVE = "tentative"
    VALIDATED = "validated"
    COMMITTED = "committed"
    ACTION_SAFE = "action_safe"
    QUARANTINED = "quarantined"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class IsolationLevel(str, Enum):
    RAW_READ = "raw_read"
    COMMITTED_READ = "committed_read"
    VERIFIED_READ = "verified_read"
    CAUSALLY_STABLE_READ = "causally_stable_read"
    ACTION_SAFE_READ = "action_safe_read"


# States visible at each isolation level
ISOLATION_VISIBLE_STATES: dict[IsolationLevel, set[MemoryState]] = {
    IsolationLevel.RAW_READ: {MemoryState.RAW, MemoryState.TENTATIVE, MemoryState.VALIDATED,
                               MemoryState.COMMITTED, MemoryState.ACTION_SAFE},
    IsolationLevel.COMMITTED_READ: {MemoryState.COMMITTED, MemoryState.ACTION_SAFE},
    IsolationLevel.VERIFIED_READ: {MemoryState.VALIDATED, MemoryState.COMMITTED, MemoryState.ACTION_SAFE},
    IsolationLevel.CAUSALLY_STABLE_READ: {MemoryState.COMMITTED, MemoryState.ACTION_SAFE},
    IsolationLevel.ACTION_SAFE_READ: {MemoryState.ACTION_SAFE},
}


@dataclass
class SourceInfo:
    type: str           # "user" | "tool" | "agent" | "system"
    id: str
    authority: float = 1.0   # 0.0-1.0
    tool_name: Optional[str] = None
    tool_result_id: Optional[str] = None


@dataclass
class PermissionInfo:
    owner: str
    read_roles: list[str] = field(default_factory=list)
    write_roles: list[str] = field(default_factory=list)
    share_scope: str = "private"   # "private" | "shared" | "public"


@dataclass
class ValidityInterval:
    valid_from: Optional[str] = None   # ISO 8601
    valid_until: Optional[str] = None  # ISO 8601


@dataclass
class MemoryRecord:
    entity: str
    attribute: str
    value: Any
    state: MemoryState = MemoryState.RAW

    memory_id: str = field(default_factory=lambda: f"m_{uuid.uuid4().hex[:8]}")
    created_at: float = field(default_factory=time.time)

    scope: Optional[str] = None
    # "belief" (default) | "summary" | "profile" | "index_entry" | "shared_copy" | "tool_action".
    # Governs how cascading rollback repairs this node (see MemTXManager.abort_memory).
    node_type: str = "belief"
    validity: ValidityInterval = field(default_factory=ValidityInterval)
    source: Optional[SourceInfo] = None
    permission: Optional[PermissionInfo] = None

    confidence: float = 1.0
    evidence_ids: list[str] = field(default_factory=list)
    derived_from: list[str] = field(default_factory=list)   # memory_ids this depends on

    # Internal tracking
    tx_id: Optional[str] = None
    snapshot_id: Optional[str] = None
    version: int = 0

    def is_visible_at(self, level: IsolationLevel) -> bool:
        return self.state in ISOLATION_VISIBLE_STATES[level]

    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "entity": self.entity,
            "attribute": self.attribute,
            "value": self.value,
            "state": self.state.value,
            "scope": self.scope,
            "node_type": self.node_type,
            "validity": {
                "valid_from": self.validity.valid_from,
                "valid_until": self.validity.valid_until,
            } if (self.validity and (self.validity.valid_from or self.validity.valid_until)) else None,
            "confidence": self.confidence,
            "source": {
                "type": self.source.type,
                "id": self.source.id,
                "authority": self.source.authority,
            } if self.source else None,
            "permission": {
                "owner": self.permission.owner,
                "read_roles": self.permission.read_roles,
                "share_scope": self.permission.share_scope,
            } if self.permission else None,
            "derived_from": self.derived_from,
            "evidence_ids": self.evidence_ids,
            "tx_id": self.tx_id,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryRecord":
        src = d.get("source")
        perm = d.get("permission")
        # Case JSON uses the "validity" key; "validity_interval" kept as a fallback.
        validity = d.get("validity", d.get("validity_interval", {}))
        return cls(
            memory_id=d.get("memory_id", f"m_{uuid.uuid4().hex[:8]}"),
            entity=d["entity"],
            attribute=d.get("attribute", d.get("slot", "")),
            value=d["value"],
            state=MemoryState(d.get("state", "raw")),
            scope=d.get("scope"),
            node_type=d.get("node_type", "belief"),
            validity=ValidityInterval(
                valid_from=validity.get("valid_from") if isinstance(validity, dict) else None,
                valid_until=validity.get("valid_until") if isinstance(validity, dict) else None,
            ),
            source=SourceInfo(
                type=src["type"], id=src["id"],
                authority=src.get("authority", 1.0),
                tool_name=src.get("tool_name"),
                tool_result_id=src.get("tool_result_id"),
            ) if src else None,
            permission=PermissionInfo(
                owner=perm["owner"],
                read_roles=perm.get("read_roles", []),
                write_roles=perm.get("write_roles", []),
                share_scope=perm.get("share_scope", "private"),
            ) if perm else None,
            confidence=d.get("confidence", 1.0),
            evidence_ids=d.get("evidence_ids", []),
            derived_from=d.get("derived_from", []),
            tx_id=d.get("tx_id"),
            version=d.get("version", 0),
        )
