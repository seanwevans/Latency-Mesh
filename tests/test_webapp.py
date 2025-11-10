import asyncio
import json
from typing import List

import networkx as nx
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from latencymesh import webapp
from latencymesh.webapp import (
    GraphBroadcast,
    _format_sse,
    _graph_snapshot,
    _graph_stats,
    _safe_value,
    create_app,
)


@pytest.mark.asyncio
async def test_api_graph_returns_snapshot():
    graph = nx.Graph()
    graph.add_node("1.1.1.1", rtt=12.3)
    graph.add_node("8.8.8.8", rtt=22.1)
    graph.add_edge("1.1.1.1", "8.8.8.8", weight=1)
    lock = asyncio.Lock()
    broadcast = GraphBroadcast()
    app = create_app(graph, lock, broadcast)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/graph")
        assert response.status_code == 200
        data = response.json()
        assert any(node["id"] == "1.1.1.1" for node in data["nodes"])
        assert data["links"]


@pytest.mark.asyncio
async def test_api_stats_reports_metrics():
    graph = nx.Graph()
    graph.add_node("a", rtt=10.0)
    graph.add_node("b", rtt=20.0)
    graph.add_edge("a", "b")
    lock = asyncio.Lock()
    broadcast = GraphBroadcast()
    app = create_app(graph, lock, broadcast)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/stats")
        assert response.status_code == 200
        stats = response.json()
        assert stats["nodes"] == 2
        assert stats["edges"] == 1
        assert stats["avg_latency"] == pytest.approx(15.0)


@pytest.mark.asyncio
async def test_index_serves_html():
    graph = nx.Graph()
    lock = asyncio.Lock()
    broadcast = GraphBroadcast()
    app = create_app(graph, lock, broadcast)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "<html" in response.text.lower()


@pytest.mark.asyncio
async def test_graph_broadcast_waits_for_notifications():
    broadcast = GraphBroadcast()

    async def wait_for_update() -> int | None:
        return await broadcast.wait_for(0)

    waiter = asyncio.create_task(wait_for_update())
    await asyncio.sleep(0)
    broadcast.notify()
    result = await asyncio.wait_for(waiter, timeout=0.5)
    assert result == 1
    assert broadcast.version == 1


@pytest.mark.asyncio
async def test_graph_broadcast_close_wakes_waiters():
    broadcast = GraphBroadcast()
    task = asyncio.create_task(broadcast.wait_for(broadcast.version))
    await asyncio.sleep(0)
    broadcast.close()
    assert await asyncio.wait_for(task, timeout=0.5) is None


def test_safe_value_serializes_unknown_types():
    class Sample:
        def __str__(self) -> str:  # pragma: no cover - simple helper
            return "custom"

    assert _safe_value(Sample()) == "custom"
    assert _safe_value(10) == 10
    assert _safe_value(None) is None


@pytest.mark.asyncio
async def test_graph_snapshot_serializes_attributes():
    graph = nx.Graph()
    odd_value = complex(1, 2)
    graph.add_node("alpha", weird=odd_value)
    graph.add_node("beta")
    graph.add_edge("alpha", "beta", flag={"nested": "value"})
    lock = asyncio.Lock()
    snapshot = await _graph_snapshot(graph, lock, version=3)
    assert snapshot["version"] == 3
    assert any(node["weird"] == str(odd_value) for node in snapshot["nodes"])
    assert snapshot["links"][0]["flag"] == str({"nested": "value"})
    assert snapshot["generated_at"].endswith("Z")


@pytest.mark.asyncio
async def test_graph_stats_handles_empty_graph():
    graph = nx.Graph()
    lock = asyncio.Lock()
    stats = await _graph_stats(graph, lock)
    assert stats == {"nodes": 0, "edges": 0, "avg_degree": 0.0, "avg_latency": 0.0}


def test_format_sse_wraps_payload_in_event():
    payload = {"foo": "bar"}
    assert _format_sse(payload) == f"data: {json.dumps(payload)}\n\n"


def test_create_app_requires_static_assets(monkeypatch, tmp_path):
    missing = tmp_path / "nope"
    monkeypatch.setattr(webapp, "STATIC_DIR", missing)
    graph = nx.Graph()
    lock = asyncio.Lock()
    broadcast = GraphBroadcast()
    with pytest.raises(RuntimeError):
        create_app(graph, lock, broadcast)


@pytest.mark.asyncio
async def test_index_missing_raises_http_error(monkeypatch, tmp_path):
    static_root = tmp_path / "static"
    static_root.mkdir()
    monkeypatch.setattr(webapp, "STATIC_DIR", static_root)
    graph = nx.Graph()
    lock = asyncio.Lock()
    broadcast = GraphBroadcast()
    app = create_app(graph, lock, broadcast)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == HTTPException(status_code=500).status_code
    assert response.json()["detail"] == "index.html missing"


class StubBroadcast:
    def __init__(self, responses: List[object]):
        self._version = 0
        self._responses = responses

    @property
    def version(self) -> int:
        return self._version

    async def wait_for(self, last_version: int) -> int | None:
        if not self._responses:
            raise AssertionError("No responses left for wait_for call")
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        if result is not None:
            self._version = int(result)
        return result


@pytest.mark.asyncio
async def test_stream_generator_emits_heartbeat_and_shutdown(monkeypatch):
    graph = nx.Graph()
    graph.add_node("a", rtt=1.0)
    graph.add_node("b")
    graph.add_edge("a", "b")
    lock = asyncio.Lock()
    broadcast = StubBroadcast(
        [
            asyncio.TimeoutError(),
            1,
            None,
        ]
    )
    app = create_app(graph, lock, broadcast)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/api/stream") as response:
            assert response.status_code == 200
            lines = response.aiter_lines()

            async def next_nonempty() -> str:
                while True:
                    line = await lines.__anext__()
                    if line:
                        return line

            first_event = await next_nonempty()
            assert first_event.startswith("data: ")

            heartbeat = await next_nonempty()
            assert heartbeat == ": heartbeat"

            update_event = await next_nonempty()
            assert update_event.startswith("data: ")

            shutdown = await next_nonempty()
            assert shutdown == "event: shutdown"
