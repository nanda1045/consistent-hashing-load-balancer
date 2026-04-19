from __future__ import annotations

import hashlib
import math
from bisect import bisect
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class RemapComparison:
    consistent_remapped: int
    modulo_remapped: int

    @property
    def reduction_percent(self) -> float:
        if self.modulo_remapped == 0:
            return 0.0
        return (1 - (self.consistent_remapped / self.modulo_remapped)) * 100


class ConsistentHashRing:
    def __init__(self, virtual_nodes: int = 150) -> None:
        if virtual_nodes <= 0:
            raise ValueError("virtual_nodes must be > 0")
        self.virtual_nodes = virtual_nodes
        self._ring_keys: List[int] = []
        self._hash_to_node: Dict[int, str] = {}
        self._nodes: set[str] = set()

    @staticmethod
    def _hash(value: str) -> int:
        return int(hashlib.md5(value.encode("utf-8")).hexdigest(), 16)

    @property
    def nodes(self) -> List[str]:
        return sorted(self._nodes)

    @property
    def ring_size(self) -> int:
        return len(self._ring_keys)

    def add_node(self, node_id: str) -> bool:
        if node_id in self._nodes:
            return False

        self._nodes.add(node_id)
        for i in range(self.virtual_nodes):
            vnode_key = f"{node_id}:vnode:{i}"
            vnode_hash = self._hash(vnode_key)
            self._hash_to_node[vnode_hash] = node_id
            self._ring_keys.append(vnode_hash)

        self._ring_keys.sort()
        return True

    def remove_node(self, node_id: str) -> bool:
        if node_id not in self._nodes:
            return False

        self._nodes.remove(node_id)
        to_remove = []
        for i in range(self.virtual_nodes):
            vnode_key = f"{node_id}:vnode:{i}"
            vnode_hash = self._hash(vnode_key)
            to_remove.append(vnode_hash)

        for vnode_hash in to_remove:
            self._hash_to_node.pop(vnode_hash, None)

        remove_set = set(to_remove)
        self._ring_keys = [h for h in self._ring_keys if h not in remove_set]
        return True

    def get_node(self, key: str) -> str:
        if not self._ring_keys:
            raise LookupError("No nodes available in ring")

        key_hash = self._hash(key)
        idx = bisect(self._ring_keys, key_hash)
        if idx == len(self._ring_keys):
            idx = 0
        return self._hash_to_node[self._ring_keys[idx]]

    def route_keys(self, keys: Sequence[str]) -> Dict[str, str]:
        return {k: self.get_node(k) for k in keys}

    def distribution_for_keys(self, keys: Sequence[str]) -> Dict[str, int]:
        distribution = {node: 0 for node in self.nodes}
        if not distribution:
            return distribution

        for key in keys:
            node = self.get_node(key)
            distribution[node] += 1
        return distribution

    def load_stats(self, keys: Sequence[str]) -> Dict[str, float | int]:
        distribution = self.distribution_for_keys(keys)
        if not distribution:
            return {
                "node_count": 0,
                "min_load": 0,
                "max_load": 0,
                "avg_load": 0.0,
                "std_dev": 0.0,
            }

        values = list(distribution.values())
        avg = sum(values) / len(values)
        variance = sum((x - avg) ** 2 for x in values) / len(values)
        return {
            "node_count": len(values),
            "min_load": min(values),
            "max_load": max(values),
            "avg_load": avg,
            "std_dev": math.sqrt(variance),
        }

    @staticmethod
    def naive_modulo_route(keys: Sequence[str], nodes: Sequence[str]) -> Dict[str, str]:
        ordered_nodes = sorted(nodes)
        if not ordered_nodes:
            raise LookupError("No nodes provided")

        assignments: Dict[str, str] = {}
        n = len(ordered_nodes)
        for key in keys:
            key_hash = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16)
            assignments[key] = ordered_nodes[key_hash % n]
        return assignments

    @staticmethod
    def remapped_count(before: Dict[str, str], after: Dict[str, str]) -> int:
        return sum(1 for key, old_node in before.items() if after.get(key) != old_node)

    @classmethod
    def compare_with_modulo(
        cls,
        keys: Sequence[str],
        old_nodes: Iterable[str],
        new_nodes: Iterable[str],
        virtual_nodes: int = 150,
    ) -> RemapComparison:
        old_nodes_list = sorted(set(old_nodes))
        new_nodes_list = sorted(set(new_nodes))

        old_ring = cls(virtual_nodes=virtual_nodes)
        new_ring = cls(virtual_nodes=virtual_nodes)
        for node in old_nodes_list:
            old_ring.add_node(node)
        for node in new_nodes_list:
            new_ring.add_node(node)

        consistent_before = old_ring.route_keys(keys)
        consistent_after = new_ring.route_keys(keys)
        consistent_remapped = cls.remapped_count(consistent_before, consistent_after)

        modulo_before = cls.naive_modulo_route(keys, old_nodes_list)
        modulo_after = cls.naive_modulo_route(keys, new_nodes_list)
        modulo_remapped = cls.remapped_count(modulo_before, modulo_after)

        return RemapComparison(
            consistent_remapped=consistent_remapped,
            modulo_remapped=modulo_remapped,
        )
