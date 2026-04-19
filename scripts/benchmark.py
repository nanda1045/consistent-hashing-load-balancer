from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ring import ConsistentHashRing


def run_benchmark() -> None:
    console = Console()

    keys = [f"benchmark-key-{i}" for i in range(10000)]
    old_nodes = [f"worker-{i}" for i in range(1, 19)]
    failed_node = "worker-2"
    new_nodes = [node for node in old_nodes if node != failed_node]

    comparison = ConsistentHashRing.compare_with_modulo(
        keys=keys,
        old_nodes=old_nodes,
        new_nodes=new_nodes,
        virtual_nodes=150,
    )

    ring_before = ConsistentHashRing(virtual_nodes=150)
    ring_after = ConsistentHashRing(virtual_nodes=150)
    for node in old_nodes:
        ring_before.add_node(node)
    for node in new_nodes:
        ring_after.add_node(node)

    consistent_stats_before = ring_before.load_stats(keys)
    consistent_stats_after = ring_after.load_stats(keys)

    modulo_before = ConsistentHashRing.naive_modulo_route(keys, old_nodes)
    modulo_after = ConsistentHashRing.naive_modulo_route(keys, new_nodes)

    modulo_distribution_after = {node: 0 for node in sorted(new_nodes)}
    for _, node in modulo_after.items():
        modulo_distribution_after[node] += 1

    modulo_values = list(modulo_distribution_after.values())
    modulo_avg = sum(modulo_values) / len(modulo_values)
    modulo_std = (
        sum((v - modulo_avg) ** 2 for v in modulo_values) / len(modulo_values)
    ) ** 0.5

    remap_table = Table(title="Key Remapping Comparison (10,000 keys)")
    remap_table.add_column("Strategy", style="cyan")
    remap_table.add_column("Before Nodes", justify="right")
    remap_table.add_column("After Nodes", justify="right")
    remap_table.add_column("Remapped Keys", justify="right")
    remap_table.add_row("Consistent Hashing", str(len(old_nodes)), str(len(new_nodes)), str(comparison.consistent_remapped))
    remap_table.add_row("Naive Modulo", str(len(old_nodes)), str(len(new_nodes)), str(comparison.modulo_remapped))

    load_table = Table(title="Load Distribution (After Failure)")
    load_table.add_column("Strategy", style="green")
    load_table.add_column("Std Dev", justify="right")
    load_table.add_column("Min Load", justify="right")
    load_table.add_column("Max Load", justify="right")
    load_table.add_row(
        "Consistent Hashing",
        f"{consistent_stats_after['std_dev']:.2f}",
        str(int(consistent_stats_after["min_load"])),
        str(int(consistent_stats_after["max_load"])),
    )
    load_table.add_row(
        "Naive Modulo",
        f"{modulo_std:.2f}",
        str(min(modulo_values)),
        str(max(modulo_values)),
    )

    before_after = Table(title="Before/After Snapshot")
    before_after.add_column("Metric", style="magenta")
    before_after.add_column("Before Failure", justify="right")
    before_after.add_column("After Failure", justify="right")
    before_after.add_row(
        "Consistent Std Dev",
        f"{consistent_stats_before['std_dev']:.2f}",
        f"{consistent_stats_after['std_dev']:.2f}",
    )
    before_after.add_row("Consistent Remapped", "0", str(comparison.consistent_remapped))
    before_after.add_row("Modulo Remapped", "0", str(comparison.modulo_remapped))
    before_after.add_row(
        "Remap Reduction",
        "-",
        f"{comparison.reduction_percent:.2f}%",
    )

    console.print(remap_table)
    console.print(load_table)
    console.print(before_after)


if __name__ == "__main__":
    run_benchmark()
