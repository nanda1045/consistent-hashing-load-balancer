import asyncio

import fakeredis.aioredis
import pytest

from src.node_manager import NodeManager


@pytest.mark.asyncio
async def test_dead_node_removed_within_6_seconds() -> None:
    redis_client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    manager = NodeManager(
        redis_url="redis://unused",
        virtual_nodes=150,
        heartbeat_ttl=2,
        redis_client=redis_client,
    )

    await manager.connect()
    await manager.register_node("worker-1")
    await manager.register_node("worker-2")

    stop_1 = asyncio.Event()
    stop_2 = asyncio.Event()
    hb1 = asyncio.create_task(manager.heartbeat_loop("worker-1", 1.0, stop_1))
    hb2 = asyncio.create_task(manager.heartbeat_loop("worker-2", 1.0, stop_2))

    await manager.start_watcher(poll_seconds=1.0, sample_keys=[f"k-{i}" for i in range(5000)])
    await asyncio.sleep(1.5)

    stop_2.set()
    hb2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await hb2

    deadline = asyncio.get_running_loop().time() + 6.0
    removed = False
    while asyncio.get_running_loop().time() < deadline:
        if "worker-2" not in manager.ring.nodes:
            removed = True
            break
        await asyncio.sleep(0.3)

    stop_1.set()
    hb1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await hb1

    await manager.close()

    assert removed, "worker-2 should be removed from ring within 6 seconds"
