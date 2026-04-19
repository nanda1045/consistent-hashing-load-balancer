from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

from redis.asyncio import Redis

from src.ring import ConsistentHashRing

LOGGER = logging.getLogger(__name__)


class NodeManager:
    def __init__(
        self,
        redis_url: str,
        virtual_nodes: int = 150,
        heartbeat_ttl: int = 5,
        redis_client: Optional[Redis] = None,
    ) -> None:
        self.redis_url = redis_url
        self.virtual_nodes = virtual_nodes
        self.heartbeat_ttl = heartbeat_ttl
        self.ring = ConsistentHashRing(virtual_nodes=virtual_nodes)
        self.redis: Optional[Redis] = redis_client
        self._watcher_task: Optional[asyncio.Task[None]] = None
        self._watcher_stop = asyncio.Event()
        self._lock = asyncio.Lock()

        self.nodes_key = "cluster:nodes"
        self.heartbeat_prefix = "cluster:heartbeat"

    async def connect(self) -> None:
        if self.redis is None:
            self.redis = Redis.from_url(self.redis_url, decode_responses=True)
        await self.redis.ping()

    async def close(self) -> None:
        await self.stop_watcher()
        if self.redis is not None:
            await self.redis.aclose()
            self.redis = None

    def _require_redis(self) -> Redis:
        if self.redis is None:
            raise RuntimeError("Redis is not connected")
        return self.redis

    def _heartbeat_key(self, node_id: str) -> str:
        return f"{self.heartbeat_prefix}:{node_id}"

    async def register_node(self, node_id: str) -> bool:
        redis = self._require_redis()
        async with self._lock:
            await redis.sadd(self.nodes_key, node_id)
            await redis.set(self._heartbeat_key(node_id), "alive", ex=self.heartbeat_ttl)
            added = self.ring.add_node(node_id)
            return added

    async def deregister_node(self, node_id: str) -> bool:
        redis = self._require_redis()
        async with self._lock:
            await redis.srem(self.nodes_key, node_id)
            await redis.delete(self._heartbeat_key(node_id))
            removed = self.ring.remove_node(node_id)
            return removed

    async def heartbeat_once(self, node_id: str) -> None:
        redis = self._require_redis()
        await redis.set(self._heartbeat_key(node_id), "alive", ex=self.heartbeat_ttl)

    async def heartbeat_loop(
        self,
        node_id: str,
        interval_seconds: float = 2.0,
        stop_event: Optional[asyncio.Event] = None,
    ) -> None:
        event = stop_event or asyncio.Event()
        while not event.is_set():
            await self.heartbeat_once(node_id)
            await asyncio.sleep(interval_seconds)

    async def refresh_ring_from_redis(self) -> None:
        redis = self._require_redis()
        nodes = await redis.smembers(self.nodes_key)
        active_nodes = sorted(nodes)

        async with self._lock:
            current_nodes = set(self.ring.nodes)
            for node in current_nodes - set(active_nodes):
                self.ring.remove_node(node)
            for node in set(active_nodes) - current_nodes:
                self.ring.add_node(node)

    async def _find_dead_nodes(self) -> List[str]:
        redis = self._require_redis()
        nodes = await redis.smembers(self.nodes_key)
        dead_nodes: List[str] = []
        for node_id in nodes:
            exists = await redis.exists(self._heartbeat_key(node_id))
            if not exists:
                dead_nodes.append(node_id)
        return dead_nodes

    async def _handle_dead_nodes(self, dead_nodes: Sequence[str], sample_keys: Sequence[str]) -> None:
        if not dead_nodes:
            return

        redis = self._require_redis()
        async with self._lock:
            before = self.ring.route_keys(sample_keys) if self.ring.nodes else {}
            removed_nodes = []
            for node_id in dead_nodes:
                await redis.srem(self.nodes_key, node_id)
                if self.ring.remove_node(node_id):
                    removed_nodes.append(node_id)

            after = self.ring.route_keys(sample_keys) if self.ring.nodes else {}
            remapped = ConsistentHashRing.remapped_count(before, after)
            if removed_nodes:
                LOGGER.warning(
                    "Dead nodes removed: %s | remapped_keys=%d/%d",
                    ",".join(sorted(removed_nodes)),
                    remapped,
                    len(sample_keys),
                )

    async def watcher_loop(
        self,
        poll_seconds: float = 2.0,
        sample_keys: Optional[Sequence[str]] = None,
    ) -> None:
        keys = sample_keys or [f"rebalance-key-{i}" for i in range(10000)]
        while not self._watcher_stop.is_set():
            try:
                dead_nodes = await self._find_dead_nodes()
                await self._handle_dead_nodes(dead_nodes, keys)
            except Exception:
                LOGGER.exception("Watcher loop failed")
            await asyncio.sleep(poll_seconds)

    async def start_watcher(
        self,
        poll_seconds: float = 2.0,
        sample_keys: Optional[Sequence[str]] = None,
    ) -> None:
        if self._watcher_task and not self._watcher_task.done():
            return
        self._watcher_stop.clear()
        self._watcher_task = asyncio.create_task(
            self.watcher_loop(poll_seconds=poll_seconds, sample_keys=sample_keys)
        )

    async def stop_watcher(self) -> None:
        if self._watcher_task is None:
            return
        self._watcher_stop.set()
        self._watcher_task.cancel()
        try:
            await self._watcher_task
        except asyncio.CancelledError:
            pass
        finally:
            self._watcher_task = None

    def ring_state(self, sample_size: int = 5000) -> Dict[str, Any]:
        sample_keys = [f"status-key-{i}" for i in range(sample_size)]
        distribution = self.ring.distribution_for_keys(sample_keys)
        return {
            "nodes": self.ring.nodes,
            "virtual_nodes_per_node": self.virtual_nodes,
            "total_virtual_slots": self.ring.ring_size,
            "distribution": distribution,
        }

    def metrics(self, sample_size: int = 10000) -> Dict[str, Any]:
        sample_keys = [f"metrics-key-{i}" for i in range(sample_size)]
        distribution = self.ring.distribution_for_keys(sample_keys)
        stats = self.ring.load_stats(sample_keys)
        stats["distribution"] = distribution
        return stats


DEFAULT_REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DEFAULT_VIRTUAL_NODES = int(os.getenv("VIRTUAL_NODES", "150"))
DEFAULT_HEARTBEAT_TTL = int(os.getenv("HEARTBEAT_TTL_SECONDS", "5"))
DEFAULT_HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "2"))
DEFAULT_WATCHER_POLL = float(os.getenv("WATCHER_POLL_SECONDS", "2"))
