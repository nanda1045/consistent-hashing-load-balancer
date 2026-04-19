![CI](https://github.com/nanda1045/consistent-hashing-load-balancer/actions/workflows/ci.yml/badge.svg)

# consistent-hashing-load-balancer

Production-grade consistent hashing load balancer built with FastAPI + Redis, featuring dynamic node rebalancing, heartbeat-based failure detection, benchmark tooling, and pytest coverage.

## Architecture

```text
			    +------------------------+
			    |  Load Balancer API     |
Client ---> /route -->|  FastAPI (port 8000)   |
			    |  Hash Ring + Watcher   |
			    +-----------+------------+
					    |
				Redis Node Registry
					    |
			  +-------------+-------------+
			  |             |             |
		  +-----v-----+ +-----v-----+ +-----v-----+ +-----v-----+
		  | Worker-1  | | Worker-2  | | Worker-3  | | Worker-4  |
		  | FastAPI   | | FastAPI   | | FastAPI   | | FastAPI   |
		  | heartbeat | | heartbeat | | heartbeat | | heartbeat |
		  +-----------+ +-----------+ +-----------+ +-----------+
```

## Features

- MD5-based consistent hash ring with configurable virtual nodes (default 150)
- Virtual node format: `{node_id}:vnode:{i}`
- Redis-backed node registration + TTL heartbeats
- Async heartbeat watcher removes dead nodes and logs remapped key count
- Side-by-side remap comparison vs naive modulo sharding
- Load-balancer API for routing, ring status, dynamic node management, and metrics
- Worker API for startup registration and key processing simulation
- Docker Compose cluster with Redis + load balancer + 4 workers
- Rich benchmark tables for remapping and load distribution

## Project Structure

```text
consistent-hashing-load-balancer/
├── src/
│   ├── ring.py
│   ├── node_manager.py
│   ├── load_balancer.py
│   └── worker.py
├── scripts/
│   ├── benchmark.py
│   ├── demo_rebalance.sh
│   ├── exercise_api.py
│   └── load_test.py
├── tests/
│   ├── test_ring.py
│   ├── test_rebalancing.py
│   └── test_heartbeat.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

### 1. Run with Docker Compose

```bash
docker compose up -d --build
```

### 2. Verify services

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ring/status
curl -X POST "http://localhost:8000/route?key=user:1001"
```

### 3. Demo node failure + auto-rebalance

```bash
bash scripts/demo_rebalance.sh
```

### 4. Full API exercise (smoke + failover + recovery)

```bash
python scripts/exercise_api.py --with-failure-demo
```

Example output:

```text
Load Balancer API Exercise
- Health: {'status': 'ok'}
- Initial Nodes: worker-1, worker-2, worker-3, worker-4
- Route user:1001: worker-1
- Route user:1001 (repeat): worker-1
- Route user:2002: worker-4
- Temp Node Added: True
- Temp Node Removed: True
- Current Nodes: worker-1, worker-2, worker-3, worker-4
- Metrics Std Dev: 222.31

Failure/Recovery Check
- After worker-2 stop: worker-1, worker-3, worker-4
- After worker-2 restart: worker-1, worker-2, worker-3, worker-4

API exercise completed successfully.
```

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python scripts/benchmark.py
python scripts/exercise_api.py --with-failure-demo
python scripts/load_test.py --requests 3000 --concurrency 120
```

## API Endpoints

### Load Balancer (port 8000)

- `GET /health`
- `POST /route?key=<key>`
- `GET /ring/status`
- `POST /nodes/add?node_id=<id>`
- `DELETE /nodes/remove?node_id=<id>`
- `GET /metrics`

### Worker Node (port 8101-8104)

- `GET /health`
- `POST /process?key=<key>`

## Benchmark

Run:

```bash
python scripts/benchmark.py
```

It prints:

- before/after key remap table
- consistent hashing vs modulo remapped key counts
- load distribution std deviation, min, and max

### Example Result Snapshot

| Metric | Consistent Hashing | Naive Modulo |
|---|---:|---:|
| Keys remapped after 1 node failure (10,000 keys, 18->17 nodes) | ~550 | ~9,400 |
| Reduction in remapped keys | ~94% | baseline |
| Load balance std dev (lower is better) | low | moderate |

## Load Testing

Run a concurrent API load test against `POST /route`:

```bash
python scripts/load_test.py --requests 3000 --concurrency 120
```

Example measured output (local Docker run):

| Metric | Value |
|---|---:|
| Total Requests | 3000 |
| Concurrency | 120 |
| Success | 3000 |
| Failure | 0 |
| Duration (s) | 2.99 |
| Throughput (req/s) | 1004.91 |
| p50 Latency (ms) | 114.66 |
| p95 Latency (ms) | 135.62 |
| Min Latency (ms) | 31.69 |
| Max Latency (ms) | 164.56 |

## Tests

- `test_ring.py`: routing determinism + virtual-node balance
- `test_rebalancing.py`: add/remove remap behavior and threshold assertions
- `test_heartbeat.py`: dead node detection and ring update within 6 seconds

Run all tests:

```bash
pytest -q
```

## CI

GitHub Actions workflow runs on push and pull requests to main and executes:

- dependency install
- pytest suite
- benchmark smoke run
- docker compose config validation

Workflow file: .github/workflows/ci.yml

## Logging

Services emit JSON logs suitable for ingestion by log platforms.

- includes: timestamp, level, logger, message, service
- request logs include: request_id, method, path, status_code, duration_ms, client_ip
- request_id is returned as `x-request-id` response header



- Built a consistent-hashing load balancer in Python/FastAPI with Redis-backed service discovery, reducing key remapping by 94% versus naive modulo sharding on simulated node failure (10K keys, 18 to 17 nodes).
- Implemented a virtual-node hash ring (150 vnodes per node) with an async heartbeat watcher that auto-evicts dead nodes and rebalances within 6 seconds of failure detection.
- Load tested at 3,000 requests with 120 concurrent workers, sustaining 1,004 req/s with p95 latency of 135 ms and zero failures.
