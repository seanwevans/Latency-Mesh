import asyncio
from types import SimpleNamespace

import networkx as nx

from latencymesh import traceroute


class _FlakyQueue:
    """Queue that raises QueueFull twice and QueueEmpty on get."""

    def __init__(self):
        self.put_calls: list[dict] = []

    def put_nowait(self, payload):
        self.put_calls.append({"payload": payload})
        if len(self.put_calls) <= 2:
            raise traceroute.QueueFull

    def get_nowait(self):
        raise traceroute.QueueEmpty


async def _run_worker_for_full_coverage(monkeypatch):
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    await queue.put("loop")
    await queue.put("trigger")

    params = SimpleNamespace(pps=200, timeout=0.1, max_hops=5, max_traces=2)
    seen_ips: set[str] = set()
    pending_ips: set[str] = set()
    stop_event = asyncio.Event()
    notifications: list[None] = []
    success_counter = {"since_last_draw": 0, "total": 0, "notify": lambda: notifications.append(None)}
    counter_lock = asyncio.Lock()
    graph = nx.Graph()
    graph_lock = asyncio.Lock()

    outputs: dict[str, list[tuple[str, float]] | None] = {
        "loop": [("loop", 1.0)],
        "trigger": [("loop", 2.0)],
    }

    async def fake_run(host, *_args):
        return outputs.get(host, [])

    monkeypatch.setattr(traceroute, "run_traceroute", fake_run)
    monkeypatch.setattr(traceroute.random, "random", lambda: 0.0)

    flaky_queue = _FlakyQueue()

    class Logger:
        def debug(self, *_a, **_k):
            pass

        def warning(self, *_a, **_k):
            raise AssertionError("warning not expected")

    worker = asyncio.create_task(
        traceroute.traceroute_worker(
            worker_id=0,
            G=graph,
            queue=queue,
            params=params,
            seen_ips=seen_ips,
            pending_ips=pending_ips,
            stop_event=stop_event,
            success_counter=success_counter,
            counter_lock=counter_lock,
            logger=Logger(),
            graph_lock=graph_lock,
            update_queue=flaky_queue,
        )
    )

    await asyncio.wait_for(stop_event.wait(), timeout=1.0)
    await worker

    return {
        "graph_nodes": list(graph.nodes),
        "notifications": notifications,
        "success_counter": success_counter,
        "put_calls": flaky_queue.put_calls,
    }


def test_traceroute_worker_graph_lock_and_limit(monkeypatch):
    results = asyncio.run(_run_worker_for_full_coverage(monkeypatch))

    # Graph updates happen inside the async graph lock branch.
    assert "loop" in results["graph_nodes"]

    # Success counter increments and limit triggers stop event, invoking notify.
    assert results["success_counter"]["since_last_draw"] == 2
    assert results["success_counter"]["total"] == 2
    assert results["notifications"]

    # Update queue experienced both QueueFull handling paths.
    assert len(results["put_calls"]) >= 3
