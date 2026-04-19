from src.ring import ConsistentHashRing


def test_remove_node_remaps_less_than_15_percent() -> None:
    keys = [f"order-{i}" for i in range(100000)]
    old_nodes = [f"worker-{i}" for i in range(1, 9)]
    new_nodes = [node for node in old_nodes if node != "worker-8"]

    comparison = ConsistentHashRing.compare_with_modulo(
        keys=keys,
        old_nodes=old_nodes,
        new_nodes=new_nodes,
        virtual_nodes=150,
    )

    remap_ratio = comparison.consistent_remapped / len(keys)
    assert remap_ratio < 0.15
    assert comparison.modulo_remapped > comparison.consistent_remapped


def test_add_node_remaps_less_than_15_percent() -> None:
    keys = [f"session-{i}" for i in range(100000)]
    old_nodes = [f"worker-{i}" for i in range(1, 9)]
    new_nodes = old_nodes + ["worker-9"]

    comparison = ConsistentHashRing.compare_with_modulo(
        keys=keys,
        old_nodes=old_nodes,
        new_nodes=new_nodes,
        virtual_nodes=150,
    )

    remap_ratio = comparison.consistent_remapped / len(keys)
    assert remap_ratio < 0.15
    assert comparison.modulo_remapped > comparison.consistent_remapped
