import asyncio
import csv
import csv
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import networkx as nx
import pytest

from latencymesh import main
from latencymesh.io_graph import load_graph, save_graph


def make_graph(tmp_path):
    graph = nx.Graph()
    graph.add_node("1.1.1.1", rtt=10.0, last_seen=datetime.utcnow().isoformat())
    graph.add_node(
        "8.8.8.8",
        rtt=25.0,
        last_seen=(datetime.utcnow() - timedelta(hours=1)).isoformat(),
    )
    graph.add_edge("1.1.1.1", "8.8.8.8", weight=5.0)
    save_graph(graph, str(tmp_path / "graph"))
    return graph


def test_render_graph_and_export(tmp_path):
    make_graph(tmp_path)
    target = main.render_graph(str(tmp_path / "graph.json"), "radial", None)
    assert target.endswith("radial.svg")
    assert os.path.exists(target)

    gexf_path = main.export_graph(
        str(tmp_path / "graph.json"), fmt="gexf", output=str(tmp_path / "out.gexf")
    )
    assert os.path.exists(gexf_path)

    csv_path = main.export_graph(
        str(tmp_path / "graph.json"), fmt="csv", output=str(tmp_path / "out.csv")
    )
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["source", "target", "weight"]
    assert rows[1] == ["1.1.1.1", "8.8.8.8", "5.0"]

    with pytest.raises(ValueError):
        main.export_graph(str(tmp_path / "graph.json"), fmt="yaml", output=None)


def test_graph_stats_and_parsing(tmp_path):
    graph = make_graph(tmp_path)
    graph.add_node("2.2.2.2", rtt=0.0, last_seen=datetime.utcnow().isoformat())
    save_graph(graph, str(tmp_path / "graph"))
    stats = main.graph_stats(str(tmp_path / "graph.json"))
    assert stats["nodes"] == 3
    assert stats["edges"] == 1
    assert stats["components"] == 2
    assert stats["avg_degree"] == pytest.approx(2 / 3)
    assert stats["avg_latency"] == pytest.approx(35 / 3)

    assert main.parse_duration("5m") == timedelta(minutes=5)
    assert main.parse_duration("10") == timedelta(seconds=10)
    with pytest.raises(ValueError):
        main.parse_duration("not-a-duration")


def test_parse_duration_empty_string():
    with pytest.raises(ValueError):
        main.parse_duration("   ")


def test_prune_and_merge(tmp_path):
    graph = make_graph(tmp_path)

    old_time = (datetime.utcnow() - timedelta(days=2)).isoformat()
    graph.nodes["8.8.8.8"]["last_seen"] = old_time
    save_graph(graph, str(tmp_path / "graph"))

    pruned_path = main.prune_graph(
        str(tmp_path / "graph.json"), older_than="1d", min_latency=20.0, output=None
    )
    pruned = load_graph(pruned_path)
    assert list(pruned.nodes()) == []

    graph_b = nx.Graph()
    graph_b.add_node("9.9.9.9", rtt=40.0, last_seen=datetime.utcnow().isoformat())
    graph_b.add_edge("1.1.1.1", "9.9.9.9", weight=7.0)
    save_graph(graph_b, str(tmp_path / "graph_b"))

    merged = main.merge_graphs(
        [str(tmp_path / "graph.json"), str(tmp_path / "graph_b.json")],
        str(tmp_path / "merged.json"),
    )
    assert merged == str(tmp_path / "merged.json")
    merged_graph = load_graph(merged)
    assert sorted(merged_graph.nodes()) == ["1.1.1.1", "9.9.9.9"]


def test_merge_graphs_ignores_missing_metrics(tmp_path, monkeypatch):
    timestamp = datetime.utcnow().isoformat()

    graph_a = nx.Graph()
    graph_a.add_node("1.1.1.1", rtt=10.0, last_seen=timestamp)
    graph_a.add_node("2.2.2.2")
    save_graph(graph_a, str(tmp_path / "graph_a"))

    monkeypatch.setattr("latencymesh.io_graph.nx.write_gexf", lambda *_a, **_k: None)

    graph_b = nx.Graph()
    graph_b.add_node("1.1.1.1", rtt=None, last_seen=None)
    graph_b.add_node("2.2.2.2", rtt=15.0)
    save_graph(graph_b, str(tmp_path / "graph_b"))

    merged_path = main.merge_graphs(
        [str(tmp_path / "graph_a.json"), str(tmp_path / "graph_b.json")],
        str(tmp_path / "merged_missing.json"),
    )

    merged_graph = load_graph(merged_path)

    first_node = merged_graph.nodes["1.1.1.1"]
    assert first_node["rtt"] == pytest.approx(10.0)
    assert first_node["last_seen"] == timestamp

    second_node = merged_graph.nodes["2.2.2.2"]
    assert second_node["rtt"] == pytest.approx(15.0)
    assert "last_seen" not in second_node


def test_detect_gateway_and_auto_seeds(monkeypatch):
    route_content = "Iface\tDestination\tGateway\neth0\t00000000\t0101A8C0\n"

    class FakeRouteFile:
        def __enter__(self):
            return iter(route_content.splitlines())

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("builtins.open", lambda *a, **k: FakeRouteFile())
    assert main.detect_default_gateway() == "192.168.1.1"

    def raise_not_found(*_a, **_k):
        raise FileNotFoundError

    monkeypatch.setattr("builtins.open", raise_not_found)
    assert main.detect_default_gateway() is None

    monkeypatch.setattr(main, "detect_default_gateway", lambda: "10.0.0.1")
    seeds = main.auto_seeds()
    assert seeds[0] == "10.0.0.1"
    assert sorted(seeds[1:]) == sorted(main.DEFAULT_SEEDS)


def test_serve_directory(monkeypatch, tmp_path):
    calls = []

    class DummyServer:
        def __init__(self, *_args, **_kwargs):
            calls.append("init")

        def serve_forever(self):
            calls.append("serve")
            raise KeyboardInterrupt

        def server_close(self):
            calls.append("close")

    monkeypatch.setattr(main, "ThreadingHTTPServer", lambda *_: DummyServer())
    monkeypatch.setattr(main, "SimpleHTTPRequestHandler", object)
    main.serve_directory(str(tmp_path), 8000)
    assert calls == ["init", "serve", "close"]


@pytest.mark.parametrize(
    "command, patched, expected",
    [
        ("show", "render_graph", "[show] wrote"),
        ("stats", "graph_stats", "nodes"),
        ("export", "export_graph", "[export] wrote"),
        ("prune", "prune_graph", "[prune] wrote"),
        ("merge", "merge_graphs", "[merge] wrote"),
        ("serve", "serve_directory", "[serve] stub"),
    ],
)
def test_main_dispatch(monkeypatch, tmp_path, command, patched, expected, capsys):
    graph = nx.Graph()
    save_graph(graph, str(tmp_path / "graph"))
    monkeypatch.setattr(
        main,
        "parse_args",
        lambda _argv: SimpleNamespace(
            command=command,
            graph=str(tmp_path / "graph.json"),
            layout="radial",
            output=None,
            format="csv",
            graphs=[str(tmp_path / "graph.json")],
            directory=str(tmp_path),
            port=8000,
            auto=False,
            seeds=None,
            older_than="1d",
            min_latency=10.0,
        ),
    )

    actions = {
        "render_graph": lambda *a, **k: tmp_path / "render.svg",
        "graph_stats": lambda *a, **k: {"nodes": 0},
        "export_graph": lambda *a, **k: str(tmp_path / "export.csv"),
        "prune_graph": lambda *a, **k: str(tmp_path / "pruned.json"),
        "merge_graphs": lambda *a, **k: str(tmp_path / "merged.json"),
        "serve_directory": lambda *_a, **_k: print("[serve] stub"),
    }
    monkeypatch.setattr(main, patched, actions[patched])
    main.main([command])
    captured = capsys.readouterr()
    assert expected in captured.out


def test_main_scan_and_errors(monkeypatch, capsys):
    params = SimpleNamespace(command="scan")
    monkeypatch.setattr(main, "parse_args", lambda _argv: params)

    def fake_run(coro):
        params.ran = coro
        coro.close()
        return None

    monkeypatch.setattr(main.asyncio, "run", fake_run)
    main.main(["scan"])
    assert hasattr(params, "ran")

    # Simulate an unknown command raising ValueError and ensure exit code is 1.
    params.command = "unknown"
    monkeypatch.setattr(main, "parse_args", lambda _argv: params)
    with pytest.raises(ValueError):
        main.main(["unknown"])


def test_main_seed_command(monkeypatch, capsys):
    params = SimpleNamespace(
        command="seed",
        auto=True,
        seeds=["1.1.1.1"],
    )
    monkeypatch.setattr(main, "parse_args", lambda _argv: params)
    monkeypatch.setattr(main, "auto_seeds", lambda: ["2.2.2.2"])
    main.main(["seed"])
    captured = capsys.readouterr()
    assert "2.2.2.2" in captured.out
    assert "1.1.1.1" in captured.out
