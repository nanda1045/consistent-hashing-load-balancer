from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query

from src.node_manager import (
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_HEARTBEAT_TTL,
    DEFAULT_REDIS_URL,
    DEFAULT_VIRTUAL_NODES,
    NodeManager,
)

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

NODE_ID = os.getenv("NODE_ID", "worker-unknown")

manager = NodeManager(
    redis_url=DEFAULT_REDIS_URL,
    virtual_nodes=DEFAULT_VIRTUAL_NODES,
    heartbeat_ttl=DEFAULT_HEARTBEAT_TTL,
)
heartbeat_stop = asyncio.Event()
heartbeat_task: asyncio.Task[None] | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global heartbeat_task

    await manager.connect()
    await manager.register_node(NODE_ID)
    heartbeat_task = asyncio.create_task(
        manager.heartbeat_loop(
            node_id=NODE_ID,
            interval_seconds=DEFAULT_HEARTBEAT_INTERVAL,
            stop_event=heartbeat_stop,
        )
    )
    LOGGER.info("Worker %s started", NODE_ID)

    try:
        yield
    finally:
        heartbeat_stop.set()
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        await manager.deregister_node(NODE_ID)
        await manager.close()


app = FastAPI(title=f"Worker Node: {NODE_ID}", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "node_id": NODE_ID}


@app.post("/process")
async def process(key: str = Query(..., min_length=1)) -> dict[str, str]:
    return {
        "node_id": NODE_ID,
        "key": key,
        "result": f"processed:{key}",
    }
