import asyncio
from types import SimpleNamespace

import networkx as nx

from latencymesh import main


def test_scan_async_controls_workers(monkeypatch):
    params = SimpleNamespace(
        seeds=["1.1.1.1"],
        extra_seeds=None,
        max_per_seed=1,
        prefix=24,
        no_display=True,
        layout="radial",
        workers=1,
        pps=1.0,
        timeout=1.0,
        max_hops=5,
        save_base="test_scan",
    )

    monkeypatch.setattr(main, "generate_local_pool", lambda *a: ["1.1.1.1"])
    monkeypatch.setattr(main, "load_graph", lambda *_: nx.Graph())

    async def fake_log_worker(queue, stop_event, level=None):
        while not stop_event.is_set() or not queue.empty():
            try:
                await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            queue.task_done()

    async def fake_traceroute_worker(
        worker_id,
        G,
        queue,
        params,
        seen_ips,
        pending_ips,
        stop_event,
        success_counter,
        counter_lock,
        logger,
    ):
        host = await queue.get()
        assert host == "1.1.1.1"
        queue.task_done()
        async with counter_lock:
            success_counter["since_last_draw"] = (
                success_counter.get("since_last_draw", 0) + 1
            )
        stop_event.set()

    async def fake_ui_manager(
        G, save_base, ax, params, stop_event, success_counter, counter_lock
    ):
        await stop_event.wait()

    calls = {}

    def fake_save_graph(G, save_base):
        calls["saved"] = save_base

    monkeypatch.setattr(main, "log_worker", fake_log_worker)
    monkeypatch.setattr(main, "traceroute_worker", fake_traceroute_worker)
    monkeypatch.setattr(main, "ui_manager", fake_ui_manager)
    monkeypatch.setattr(main, "save_graph", fake_save_graph)

    asyncio.run(main.scan_async(params))

    assert calls["saved"] == "test_scan"

    params.seeds = []
    params.extra_seeds = ["9.9.9.9"]
    if hasattr(params, "layout"):
        delattr(params, "layout")
    monkeypatch.setattr(main, "generate_local_pool", lambda *a: [])
    asyncio.run(main.scan_async(params))

    params.no_display = False
    monkeypatch.setattr(main, "generate_local_pool", lambda *a: ["1.1.1.1"])
    monkeypatch.setattr(main.plt, "ion", lambda: None)
    monkeypatch.setattr(main.plt, "ioff", lambda: None)
    monkeypatch.setattr(main.plt, "close", lambda *_: None)
    monkeypatch.setattr(main.plt, "subplots", lambda *a, **k: (None, object()))
    asyncio.run(main.scan_async(params))
