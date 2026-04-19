from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from src.node_manager import (
    DEFAULT_HEARTBEAT_TTL,
    DEFAULT_REDIS_URL,
    DEFAULT_VIRTUAL_NODES,
    DEFAULT_WATCHER_POLL,
    NodeManager,
)

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

manager = NodeManager(
    redis_url=DEFAULT_REDIS_URL,
    virtual_nodes=DEFAULT_VIRTUAL_NODES,
    heartbeat_ttl=DEFAULT_HEARTBEAT_TTL,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await manager.connect()
    await manager.refresh_ring_from_redis()
    await manager.start_watcher(poll_seconds=DEFAULT_WATCHER_POLL)
    LOGGER.info("Load balancer started with %d nodes", len(manager.ring.nodes))
    try:
        yield
    finally:
        await manager.close()


app = FastAPI(title="Consistent Hashing Load Balancer", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/route")
async def route_key(key: str = Query(..., min_length=1)) -> dict[str, str]:
    if not manager.ring.nodes:
        raise HTTPException(status_code=503, detail="No available worker nodes")
    node_id = manager.ring.get_node(key)
    return {"key": key, "node_id": node_id}


@app.get("/ring/status")
async def ring_status() -> dict:
    return manager.ring_state()


@app.post("/nodes/add")
async def add_node(node_id: str = Query(..., min_length=1)) -> dict:
    sample_keys = [f"add-key-{i}" for i in range(10000)]
    before = manager.ring.route_keys(sample_keys) if manager.ring.nodes else {}
    added = await manager.register_node(node_id)
    after = manager.ring.route_keys(sample_keys) if manager.ring.nodes else {}
    remapped = manager.ring.remapped_count(before, after)
    return {
        "added": added,
        "node_id": node_id,
        "remapped_keys": remapped,
        "sample_size": len(sample_keys),
    }


@app.delete("/nodes/remove")
async def remove_node(node_id: str = Query(..., min_length=1)) -> dict:
    sample_keys = [f"remove-key-{i}" for i in range(10000)]
    before = manager.ring.route_keys(sample_keys) if manager.ring.nodes else {}
    removed = await manager.deregister_node(node_id)
    after = manager.ring.route_keys(sample_keys) if manager.ring.nodes else {}
    remapped = manager.ring.remapped_count(before, after)
    return {
        "removed": removed,
        "node_id": node_id,
        "remapped_keys": remapped,
        "sample_size": len(sample_keys),
    }


@app.get("/metrics")
async def metrics() -> dict:
    return manager.metrics()
