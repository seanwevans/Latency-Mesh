import math
from unittest import mock

import pytest

nx = pytest.importorskip("networkx")

from latencymesh import graph_ops


class TestAddTrace:
    def test_adds_nodes_edges_and_updates_rtt(self):
        graph = nx.Graph()
        hops = [
            (graph_ops.IPAddress("203.0.113.1"), 10.0),
            (graph_ops.IPAddress("203.0.113.2"), 20.0),
        ]

        graph_ops.add_trace(graph, hops)

        assert set(graph.nodes) == {
            graph_ops.IPAddress("203.0.113.1"),
            graph_ops.IPAddress("203.0.113.2"),
        }
        assert graph.nodes[graph_ops.IPAddress("203.0.113.1")] == {
            "rtt": 10.0,
            "last_seen": mock.ANY,
        }
        assert graph.nodes[graph_ops.IPAddress("203.0.113.2")] == {
            "rtt": 20.0,
            "last_seen": mock.ANY,
        }

        edge_data = graph.get_edge_data(
            graph_ops.IPAddress("203.0.113.1"), graph_ops.IPAddress("203.0.113.2")
        )
        assert edge_data["weight"] == 10.0

        # Add a second trace to ensure RTT is updated with the minimum value.
        graph_ops.add_trace(graph, [(graph_ops.IPAddress("203.0.113.2"), 5.0)])
        assert graph.nodes[graph_ops.IPAddress("203.0.113.2")]["rtt"] == 5.0

    def test_edge_weight_has_minimum_value(self):
        graph = nx.Graph()
        hops = [
            (graph_ops.IPAddress("198.51.100.1"), 10.0),
            (graph_ops.IPAddress("198.51.100.2"), 9.5),
        ]

        graph_ops.add_trace(graph, hops)

        edge_data = graph.get_edge_data(
            graph_ops.IPAddress("198.51.100.1"), graph_ops.IPAddress("198.51.100.2")
        )
        assert edge_data["weight"] == 0.1


class TestComputePositions:
    def test_positions_use_ip_angle_and_rtt(self):
        graph = nx.Graph()
        graph.add_node(graph_ops.IPAddress("192.0.2.1"), rtt=2.0)
        graph.add_node(graph_ops.IPAddress("192.0.2.2"), rtt=3.0)

        fake_angles = {
            graph_ops.IPAddress("192.0.2.1"): 0.0,
            graph_ops.IPAddress("192.0.2.2"): math.pi / 2,
        }

        with mock.patch(
            "latencymesh.graph_ops.ip_angle", side_effect=lambda ip: fake_angles[ip]
        ):
            positions = graph_ops.compute_positions(graph)

        assert positions[graph_ops.IPAddress("192.0.2.1")] == (2.0, 0.0)
        x, y = positions[graph_ops.IPAddress("192.0.2.2")]
        assert pytest.approx(x, abs=1e-12) == 0.0
        assert y == 3.0
