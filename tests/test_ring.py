from src.ring import ConsistentHashRing


def test_same_key_routes_to_same_node() -> None:
    ring = ConsistentHashRing(virtual_nodes=150)
    ring.add_node("worker-1")
    ring.add_node("worker-2")
    ring.add_node("worker-3")

    key = "customer:42"
    first = ring.get_node(key)
    for _ in range(100):
        assert ring.get_node(key) == first


def test_virtual_node_distribution_is_balanced() -> None:
    ring = ConsistentHashRing(virtual_nodes=150)
    nodes = [f"worker-{i}" for i in range(1, 6)]
    for node in nodes:
        ring.add_node(node)

    keys = [f"key-{i}" for i in range(50000)]
    distribution = ring.distribution_for_keys(keys)

    avg = sum(distribution.values()) / len(distribution)
    max_allowed_deviation = 0.15

    for count in distribution.values():
        deviation = abs(count - avg) / avg
        assert deviation < max_allowed_deviation
