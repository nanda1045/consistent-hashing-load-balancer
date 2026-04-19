from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass

import httpx
from rich.console import Console
from rich.table import Table


@dataclass
class LoadResult:
    total_requests: int
    success_count: int
    failure_count: int
    total_duration_s: float
    throughput_rps: float
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]

    ordered = sorted(values)
    rank = (len(ordered) - 1) * p
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


async def request_once(client: httpx.AsyncClient, key: str) -> tuple[bool, float]:
    start = time.perf_counter()
    try:
        response = await client.post("/route", params={"key": key}, timeout=10.0)
        elapsed_ms = (time.perf_counter() - start) * 1000
        ok = response.status_code == 200
        return ok, elapsed_ms
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return False, elapsed_ms


async def run_load_test(base_url: str, total_requests: int, concurrency: int) -> LoadResult:
    semaphore = asyncio.Semaphore(concurrency)
    latencies_ms: list[float] = []
    success_count = 0

    async with httpx.AsyncClient(base_url=base_url) as client:
        async def bounded(i: int) -> tuple[bool, float]:
            async with semaphore:
                return await request_once(client, f"load-key-{i}")

        start = time.perf_counter()
        results = await asyncio.gather(*[bounded(i) for i in range(total_requests)])
        duration = time.perf_counter() - start

    for ok, elapsed in results:
        latencies_ms.append(elapsed)
        if ok:
            success_count += 1

    failure_count = total_requests - success_count
    throughput_rps = total_requests / duration if duration else 0.0

    return LoadResult(
        total_requests=total_requests,
        success_count=success_count,
        failure_count=failure_count,
        total_duration_s=duration,
        throughput_rps=throughput_rps,
        p50_ms=percentile(latencies_ms, 0.50),
        p95_ms=percentile(latencies_ms, 0.95),
        min_ms=min(latencies_ms) if latencies_ms else 0.0,
        max_ms=max(latencies_ms) if latencies_ms else 0.0,
    )


def print_results(console: Console, result: LoadResult, concurrency: int) -> None:
    table = Table(title="Load Test Results")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Total Requests", str(result.total_requests))
    table.add_row("Concurrency", str(concurrency))
    table.add_row("Success", str(result.success_count))
    table.add_row("Failure", str(result.failure_count))
    table.add_row("Duration (s)", f"{result.total_duration_s:.2f}")
    table.add_row("Throughput (req/s)", f"{result.throughput_rps:.2f}")
    table.add_row("p50 Latency (ms)", f"{result.p50_ms:.2f}")
    table.add_row("p95 Latency (ms)", f"{result.p95_ms:.2f}")
    table.add_row("Min Latency (ms)", f"{result.min_ms:.2f}")
    table.add_row("Max Latency (ms)", f"{result.max_ms:.2f}")
    console.print(table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Concurrent load test for /route endpoint")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=3000)
    parser.add_argument("--concurrency", type=int, default=100)
    args = parser.parse_args()

    if args.requests <= 0:
        raise ValueError("--requests must be > 0")
    if args.concurrency <= 0:
        raise ValueError("--concurrency must be > 0")

    console = Console()
    result = asyncio.run(
        run_load_test(
            base_url=args.base_url,
            total_requests=args.requests,
            concurrency=args.concurrency,
        )
    )
    print_results(console, result, concurrency=args.concurrency)

    if result.failure_count > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
