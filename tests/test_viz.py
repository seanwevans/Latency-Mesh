import networkx as nx

from latencymesh import viz


def test_layout_selection_and_draw(tmp_path):
    graph = nx.Graph()
    graph.add_node("1.1.1.1", rtt=5.0)
    graph.add_edge("1.1.1.1", "2.2.2.2")

    viz.draw_map(graph, str(tmp_path / "map"), None, layout="spring")
    assert (tmp_path / "map.svg").exists()

    viz.draw_map(graph, str(tmp_path / "map"), None, layout="planar")
    assert (tmp_path / "map.svg").exists()

    positions = viz._layout_positions(graph, "radial")
    assert "1.1.1.1" in {str(ip) for ip in positions.keys()}
