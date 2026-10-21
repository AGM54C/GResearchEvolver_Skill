"""
Base MemoryManager interface that all baselines and MemTX must implement.
No baseline may add extra arguments to these methods.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class MemoryManager(ABC):

    @abstractmethod
    def begin_tx(self, task_id: str, agent_id: str, risk_level: str) -> str:
        """
        Start a new transaction. Returns a tx_id string.
        risk_level: "low" | "medium" | "high" | "external_action"
        """

    @abstractmethod
    def retrieve(
        self,
        tx_id: str,
        query: str,
        requester: dict,
        purpose: str,
        top_k: int = 8,
    ) -> list[dict]:
        """
        Retrieve memory records visible to this transaction.
        requester: {"agent_id": ..., "role": ..., "permissions": [...]}
        purpose: "plan" | "verification" | "action" (mirrors the read_memory tool enum)
        Returns list of memory record dicts.
        """

    @abstractmethod
    def stage_write(
        self,
        tx_id: str,
        observation: dict,
        extracted_memory: list[dict],
    ) -> list[str]:
        """
        Stage candidate memory writes for this transaction (not yet committed).
        Returns list of staged memory_ids.
        """

    @abstractmethod
    def validate_and_commit(self, tx_id: str) -> dict:
        """
        Run validation checks and commit valid memory writes.
        Returns: {"status": "committed"|"aborted"|"partial", "committed_ids": [...],
                  "aborted_ids": [...], "violations": [...]}
        """

    @abstractmethod
    def abort_or_rollback(self, tx_id: str, reason: str) -> dict:
        """
        Abort this transaction and optionally trigger cascading rollback.
        Returns: {"status": "aborted", "rolled_back_ids": [...]}
        """

    @abstractmethod
    def record_tool_effect(
        self,
        tx_id: str,
        tool_name: str,
        args: dict,
        result: dict,
    ) -> None:
        """
        Record a tool call and its result so it can be linked to memory writes.
        """

    @abstractmethod
    def current_belief_view(self, requester: dict, purpose: str) -> list[dict]:
        """
        Return the current committed belief state visible to a requester.
        Used by evaluator — not tied to any specific transaction.
        """

    def reset(self) -> None:
        """Reset manager state between scenario runs. Override if needed."""
