import asyncio

import networkx as nx
import pytest
from httpx import ASGITransport, AsyncClient

from latencymesh.webapp import GraphBroadcast, create_app


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
async def test_stream_emits_updates():
    graph = nx.Graph()
    lock = asyncio.Lock()
    broadcast = GraphBroadcast()
    app = create_app(graph, lock, broadcast)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/api/stream") as response:
            assert response.status_code == 200
            lines = response.aiter_lines()
            first = await lines.__anext__()
            assert first.startswith("data: ")
            # consume blank separator if present
            try:
                while True:
                    separator = await lines.__anext__()
                    if not separator:
                        break
            except StopAsyncIteration:
                pass

            async with lock:
                graph.add_node("n1")
            broadcast.notify()

            second = await lines.__anext__()
            assert second.startswith("data: ")


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
