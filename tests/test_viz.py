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


def test_planar_layout_falls_back_to_spring(monkeypatch):
    graph = nx.complete_graph(5)

    def broken_planar_layout(_graph):
        raise nx.NetworkXException("not planar")

    def sentinel_spring_layout(G, seed):
        # Ensure the fallback path uses spring_layout.
        return {node: (idx, idx) for idx, node in enumerate(G)}

    monkeypatch.setattr(viz.nx, "planar_layout", broken_planar_layout)
    monkeypatch.setattr(viz.nx, "spring_layout", sentinel_spring_layout)

    positions = viz._layout_positions(graph, "planar")
    assert set(positions) == set(graph.nodes())


def test_draw_map_creates_parent_directory(tmp_path):
    graph = nx.Graph()
    graph.add_node("1.1.1.1", rtt=5.0)

    target = tmp_path / "nested" / "subdir" / "map.png"
    assert not target.parent.exists()

    viz.draw_map(graph, None, None, output_path=str(target))

    assert target.exists()
