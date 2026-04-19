from __future__ import annotations

import argparse
import subprocess
import time
from typing import Any

import httpx
from rich.console import Console
from rich.table import Table


def call_json(client: httpx.Client, method: str, path: str) -> dict[str, Any]:
    response = client.request(method, path, timeout=10)
    response.raise_for_status()
    return response.json()


def run_api_exercise(base_url: str, with_failure_demo: bool) -> None:
    console = Console()

    with httpx.Client(base_url=base_url) as client:
        health = call_json(client, "GET", "/health")
        status_before = call_json(client, "GET", "/ring/status")

        route_a = call_json(client, "POST", "/route?key=user:1001")
        route_b = call_json(client, "POST", "/route?key=user:1001")
        route_c = call_json(client, "POST", "/route?key=user:2002")
        metrics = call_json(client, "GET", "/metrics")

        add_temp = call_json(client, "POST", "/nodes/add?node_id=worker-temp")
        remove_temp = call_json(client, "DELETE", "/nodes/remove?node_id=worker-temp")
        status_after_temp = call_json(client, "GET", "/ring/status")

        if route_a["node_id"] != route_b["node_id"]:
            raise AssertionError("Routing is not deterministic for same key")

        if "std_dev" not in metrics:
            raise AssertionError("Metrics payload missing std_dev")

        if not add_temp.get("added", False):
            raise AssertionError("Expected worker-temp to be added")

        if not remove_temp.get("removed", False):
            raise AssertionError("Expected worker-temp to be removed")

        summary = Table(title="Load Balancer API Exercise")
        summary.add_column("Check")
        summary.add_column("Result")
        summary.add_row("Health", str(health))
        summary.add_row("Initial Nodes", ", ".join(status_before["nodes"]))
        summary.add_row("Route user:1001", route_a["node_id"])
        summary.add_row("Route user:1001 (repeat)", route_b["node_id"])
        summary.add_row("Route user:2002", route_c["node_id"])
        summary.add_row("Temp Node Added", str(add_temp["added"]))
        summary.add_row("Temp Node Removed", str(remove_temp["removed"]))
        summary.add_row("Current Nodes", ", ".join(status_after_temp["nodes"]))
        summary.add_row("Metrics Std Dev", f"{metrics['std_dev']:.2f}")
        console.print(summary)

        if with_failure_demo:
            console.print("\n[bold]Running worker-2 failure simulation...[/bold]")
            subprocess.run(["docker", "compose", "stop", "worker-2"], check=True)
            time.sleep(7)
            status_after_fail = call_json(client, "GET", "/ring/status")
            if "worker-2" in status_after_fail["nodes"]:
                raise AssertionError("worker-2 should be removed after heartbeat timeout")

            fail_table = Table(title="Failure/Recovery Check")
            fail_table.add_column("Stage")
            fail_table.add_column("Nodes")
            fail_table.add_row("After worker-2 stop", ", ".join(status_after_fail["nodes"]))

            subprocess.run(["docker", "compose", "up", "-d", "worker-2"], check=True)
            time.sleep(5)
            status_after_recover = call_json(client, "GET", "/ring/status")
            if "worker-2" not in status_after_recover["nodes"]:
                raise AssertionError("worker-2 should be re-added after restart")

            fail_table.add_row("After worker-2 restart", ", ".join(status_after_recover["nodes"]))
            console.print(fail_table)

    console.print("\n[green]API exercise completed successfully.[/green]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Exercise load balancer APIs.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--with-failure-demo", action="store_true")
    args = parser.parse_args()

    run_api_exercise(base_url=args.base_url, with_failure_demo=args.with_failure_demo)


if __name__ == "__main__":
    main()
