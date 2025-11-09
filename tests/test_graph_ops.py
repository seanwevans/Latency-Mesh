import math

import networkx as nx

from latencymesh.graph_ops import add_trace, compute_positions


def test_add_trace_updates_graph():
    graph = nx.Graph()
    hops = [("1.1.1.1", 10.0), ("2.2.2.2", 20.0), ("3.3.3.3", 30.0)]

    add_trace(graph, hops)

    assert graph.has_edge("1.1.1.1", "2.2.2.2")
    assert graph.nodes["2.2.2.2"]["rtt"] == 20.0

    # Running the same trace with better RTT updates the stored value.
    improved_hops = [("2.2.2.2", 15.0)]
    add_trace(graph, improved_hops)
    assert graph.nodes["2.2.2.2"]["rtt"] == 15.0


def test_compute_positions_returns_cartesian_coordinates():
    graph = nx.Graph()
    graph.add_node("1.1.1.1", rtt=10.0)
    positions = compute_positions(graph)
    coord = positions[next(iter(positions))]
    assert math.isfinite(coord[0]) and math.isfinite(coord[1])
