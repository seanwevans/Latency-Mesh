import json
from pathlib import Path

import networkx as nx
import pytest

from latencymesh.io_graph import load_graph, resolve_graph_path, save_graph


def test_resolve_graph_path(tmp_path):
    file = tmp_path / "graph.json"
    file.write_text("{}", encoding="utf-8")

    # Existing path is returned verbatim.
    assert resolve_graph_path(str(file)) == str(file)

    # Adding the extension when only a base name is provided.
    assert resolve_graph_path(str(tmp_path / "missing")) == str(
        tmp_path / "missing.json"
    )

    # Expands user directories and keeps json suffixes intact.
    home_graph = Path("~/custom_graph.json")
    assert resolve_graph_path(str(home_graph)) == str(home_graph.expanduser())

    # Directories should raise to avoid ambiguous input.
    with pytest.raises(IsADirectoryError):
        resolve_graph_path(str(tmp_path))


def test_load_and_save_graph_roundtrip(tmp_path):
    graph = nx.Graph()
    graph.add_node("1.1.1.1", rtt=10.0)
    graph.add_edge("1.1.1.1", "8.8.8.8", weight=5.0)

    save_graph(graph, str(tmp_path / "internet_map"))

    loaded = load_graph(str(tmp_path / "internet_map.json"))
    assert sorted(loaded.nodes()) == ["1.1.1.1", "8.8.8.8"]
    assert loaded.nodes["1.1.1.1"]["rtt"] == 10.0
    assert loaded.edges["1.1.1.1", "8.8.8.8"]["weight"] == 5.0

    # Ensure the auxiliary GEXF file was written alongside the JSON.
    assert (tmp_path / "internet_map.gexf").exists()

    with open(tmp_path / "internet_map.json", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["directed"] is False


def test_save_graph_creates_nested_directories(tmp_path):
    graph = nx.Graph()
    graph.add_node("node")

    nested_base = tmp_path / "nested" / "path" / "graph"
    save_graph(graph, str(nested_base))

    json_file = nested_base.with_suffix(".json")
    gexf_file = nested_base.with_suffix(".gexf")

    assert json_file.exists()
    assert gexf_file.exists()

    with open(json_file, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["nodes"], "JSON file should contain node data"
