"""
Dependency graph: tracks which memory records derive from which others.
Used by the cascading rollback manager.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Set


class DependencyGraph:
    def __init__(self):
        # parent -> set of children (derived memories)
        self._children: dict[str, set[str]] = defaultdict(set)
        # child -> set of parents
        self._parents: dict[str, set[str]] = defaultdict(set)

    def add_dependency(self, parent_id: str, child_id: str) -> None:
        """child_id derives from parent_id."""
        self._children[parent_id].add(child_id)
        self._parents[child_id].add(parent_id)

    def add_edges_for_record(self, memory_id: str, derived_from: list[str]) -> None:
        for parent in derived_from:
            self.add_dependency(parent, memory_id)

    def descendants(self, memory_id: str) -> list[str]:
        """Return all transitive descendants of memory_id (BFS)."""
        visited: set[str] = set()
        queue = list(self._children.get(memory_id, []))
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            queue.extend(self._children.get(node, []))
        return list(visited)

    def parents(self, memory_id: str) -> set[str]:
        return set(self._parents.get(memory_id, set()))

    def has_pending_invalidation(self, memory_ids: list[str], invalidated: set[str]) -> bool:
        """Return True if any memory in memory_ids has an invalidated ancestor.

        Walks ancestors transitively: a record whose parent survived but whose
        grandparent was revoked is still built on retracted ground and must not
        commit (a direct-parent-only check misses this when the intermediate
        node was quarantined rather than revoked).
        """
        seen: set[str] = set()
        queue: list[str] = []
        for mid in memory_ids:
            queue.extend(self._parents.get(mid, ()))
        while queue:
            node = queue.pop()
            if node in seen:
                continue
            seen.add(node)
            if node in invalidated:
                return True
            queue.extend(self._parents.get(node, ()))
        return False

    def remove_node(self, memory_id: str) -> None:
        """Remove a node and all its edges."""
        for child in list(self._children.get(memory_id, [])):
            self._parents[child].discard(memory_id)
        self._children.pop(memory_id, None)
        for parent in list(self._parents.get(memory_id, [])):
            self._children[parent].discard(memory_id)
        self._parents.pop(memory_id, None)

    def reset(self) -> None:
        self._children.clear()
        self._parents.clear()
