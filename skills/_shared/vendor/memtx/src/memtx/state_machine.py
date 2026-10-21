"""
MemTX memory state machine.
Valid transitions are defined here; any attempt to make an illegal
transition raises MemoryStateError.
"""
from __future__ import annotations
from schema import MemoryState

# Allowed transitions: from_state -> {to_states}
TRANSITIONS: dict[MemoryState, set[MemoryState]] = {
    MemoryState.RAW: {
        MemoryState.TENTATIVE,
        MemoryState.REVOKED,
    },
    MemoryState.TENTATIVE: {
        MemoryState.VALIDATED,
        MemoryState.QUARANTINED,
        MemoryState.REVOKED,
    },
    MemoryState.VALIDATED: {
        MemoryState.COMMITTED,
        MemoryState.QUARANTINED,
        MemoryState.REVOKED,
    },
    MemoryState.COMMITTED: {
        MemoryState.ACTION_SAFE,
        MemoryState.SUPERSEDED,
        MemoryState.QUARANTINED,
        MemoryState.REVOKED,
    },
    MemoryState.ACTION_SAFE: {
        MemoryState.SUPERSEDED,
        MemoryState.REVOKED,
    },
    MemoryState.QUARANTINED: {
        MemoryState.VALIDATED,
        MemoryState.REVOKED,
    },
    MemoryState.SUPERSEDED: {
        MemoryState.REVOKED,
    },
    MemoryState.REVOKED: set(),  # terminal
}


class MemoryStateError(Exception):
    pass


def transition(record, to_state: MemoryState) -> None:
    """Mutate record.state in-place, enforcing valid transitions."""
    allowed = TRANSITIONS.get(record.state, set())
    if to_state not in allowed:
        raise MemoryStateError(
            f"Illegal transition {record.state} -> {to_state} "
            f"for memory {record.memory_id}"
        )
    record.state = to_state
