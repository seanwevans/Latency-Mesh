"""Web application server for LatencyMesh."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import networkx as nx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).with_name("webapp").joinpath("static")


class GraphBroadcast:
    """Coordinate streaming updates for graph subscribers."""

    def __init__(self) -> None:
        self._version = 0
        self._event = asyncio.Event()
        self._closed = False

    @property
    def version(self) -> int:
        return self._version

    def notify(self) -> None:
        self._version += 1
        self._event.set()

    async def wait_for(self, last_version: int) -> Optional[int]:
        while True:
            if self._closed:
                return None
            current = self._version
            if current != last_version:
                return current
            await self._event.wait()
            self._event.clear()

    def close(self) -> None:
        self._closed = True
        self._event.set()


def _safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


async def _graph_snapshot(
    graph: nx.Graph, graph_lock: asyncio.Lock, version: int
) -> Dict[str, Any]:
    async with graph_lock:
        nodes = [
            {"id": str(node), **{k: _safe_value(v) for k, v in data.items()}}
            for node, data in graph.nodes(data=True)
        ]
        edges = [
            {
                "source": str(u),
                "target": str(v),
                **{k: _safe_value(val) for k, val in attributes.items()},
            }
            for u, v, attributes in graph.edges(data=True)
        ]
    return {
        "version": version,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "nodes": nodes,
        "links": edges,
    }


async def _graph_stats(graph: nx.Graph, graph_lock: asyncio.Lock) -> Dict[str, Any]:
    async with graph_lock:
        num_nodes = graph.number_of_nodes()
        num_edges = graph.number_of_edges()
        degrees = list(dict(graph.degree()).values()) if num_nodes else []
        latencies = [
            data.get("rtt")
            for _, data in graph.nodes(data=True)
            if data.get("rtt") is not None
        ]
    return {
        "nodes": num_nodes,
        "edges": num_edges,
        "avg_degree": sum(degrees) / len(degrees) if degrees else 0.0,
        "avg_latency": sum(latencies) / len(latencies) if latencies else 0.0,
    }


def _format_sse(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def create_app(
    graph: nx.Graph, graph_lock: asyncio.Lock, broadcast: GraphBroadcast
) -> FastAPI:
    if not STATIC_DIR.exists():
        raise RuntimeError(
            "Static assets missing. Expected directory at "
            f"{STATIC_DIR}"  # pragma: no cover
        )

    app = FastAPI(title="LatencyMesh Web API")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.state.graph = graph
    app.state.graph_lock = graph_lock
    app.state.broadcast = broadcast

    @app.get("/", response_class=FileResponse)
    async def index() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=500, detail="index.html missing")
        return FileResponse(index_path)

    @app.get("/api/graph")
    async def api_graph() -> JSONResponse:
        snapshot = await _graph_snapshot(
            app.state.graph, app.state.graph_lock, broadcast.version
        )
        return JSONResponse(snapshot)

    @app.get("/api/stats")
    async def api_stats() -> JSONResponse:
        stats = await _graph_stats(app.state.graph, app.state.graph_lock)
        stats["version"] = broadcast.version
        return JSONResponse(stats)

    @app.get("/api/stream")
    async def api_stream() -> StreamingResponse:
        async def event_generator():
            version = broadcast.version
            snapshot = await _graph_snapshot(
                app.state.graph, app.state.graph_lock, version
            )
            yield _format_sse(snapshot)
            heartbeat = 15.0
            while True:
                try:
                    next_version = await asyncio.wait_for(
                        broadcast.wait_for(version), timeout=heartbeat
                    )
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if next_version is None:
                    yield "event: shutdown\n\n"
                    break
                version = next_version
                snapshot = await _graph_snapshot(
                    app.state.graph, app.state.graph_lock, version
                )
                yield _format_sse(snapshot)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return app
