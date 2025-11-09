import asyncio
from types import SimpleNamespace

import networkx as nx

from latencymesh import traceroute, ui


def test_run_traceroute_parses_output(monkeypatch):
    lines = [
        b" 1 10.0.0.1 12.3 ms\n",
        b" 2 * 99.9 ms\n",
        b" 3 999.999.999.999 34.5 ms\n",
        b" 4 8.8.8.8 34.5 ms\n",
        b" 5 2001:4860:4860::8888 56.7 ms\n",
    ]

    class DummyStream:
        def __init__(self, payload):
            self._payload = payload

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._payload:
                raise StopAsyncIteration
            return self._payload.pop(0)

    class DummyProcess:
        def __init__(self):
            self.stdout = DummyStream(lines)

        async def wait(self):
            return 0

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return DummyProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    class DummyLogger:
        def debug(self, *_a, **_k):
            pass

    result = asyncio.run(traceroute.run_traceroute("example", 1.0, 5, DummyLogger()))
    assert result == [
        ("10.0.0.1", 12.3),
        ("8.8.8.8", 34.5),
        ("2001:4860:4860::8888", 56.7),
    ]


def test_traceroute_worker_timeout_and_notify(monkeypatch):
    graph = nx.Graph()

    async def runner():
        queue: asyncio.Queue = asyncio.Queue()
        params = SimpleNamespace(pps=50, timeout=1.0, max_hops=30)
        seen_ips: set[str] = set()
        pending_ips: set[str] = set()
        stop_event = asyncio.Event()
        notify_calls: list[None] = []
        success_counter = {"since_last_draw": 0, "notify": lambda: notify_calls.append(None)}
        counter_lock = asyncio.Lock()

        real_wait_for = asyncio.wait_for

        async def fake_wait_for(awaitable, timeout):
            fake_wait_for.calls += 1
            adjusted = 1e-5 if fake_wait_for.calls == 1 else min(timeout, 0.05)
            return await real_wait_for(awaitable, adjusted)

        fake_wait_for.calls = 0
        monkeypatch.setattr(traceroute.asyncio, "wait_for", fake_wait_for)

        async def fake_run(host, *_args):
            return [(host, 5.0)]

        monkeypatch.setattr(traceroute, "run_traceroute", fake_run)
        monkeypatch.setattr(traceroute.random, "random", lambda: 1.0)

        class Logger:
            def warning(self, *_a, **_k):
                pass

            def debug(self, *_a, **_k):
                pass

        worker = asyncio.create_task(
            traceroute.traceroute_worker(
                worker_id=2,
                G=graph,
                queue=queue,
                params=params,
                seen_ips=seen_ips,
                pending_ips=pending_ips,
                stop_event=stop_event,
                success_counter=success_counter,
                counter_lock=counter_lock,
                logger=Logger(),
            )
        )

        # First loop iteration should hit the timeout branch before any hosts arrive.
        await asyncio.sleep(0.01)
        await queue.put("1.1.1.1")
        await asyncio.sleep(0.05)
        await queue.put(None)

        await worker

        return notify_calls, success_counter, seen_ips

    notify_calls, success_counter, seen_ips = asyncio.run(runner())
    assert notify_calls
    assert success_counter["since_last_draw"] >= 2
    assert "1.1.1.1" in seen_ips


def test_traceroute_worker_handles_success_and_errors(monkeypatch):
    graph = nx.Graph()
    queue: asyncio.Queue = asyncio.Queue()

    async def runner():
        await queue.put("1.1.1.1")
        await queue.put("bad-host")
        await queue.put("repeat")

        params = SimpleNamespace(pps=10, timeout=1.0, max_hops=30)
        seen_ips = set()
        pending_ips = set()
        stop_event = asyncio.Event()
        success_counter = {}
        counter_lock = asyncio.Lock()
        error_event = asyncio.Event()

        async def fake_run_traceroute(host, *_args):
            if host == "bad-host":
                raise RuntimeError("boom")
            if host == "1.1.1.1":
                return [("2.2.2.2", 5.0), ("3.3.3.3", 10.0)]
            return [(host, 6.0)]

        messages = []

        class Logger:
            def warning(self, msg):
                messages.append(msg)
                error_event.set()

            def debug(self, *_a, **_k):
                pass

            def info(self, *_a, **_k):
                pass

        monkeypatch.setattr(traceroute, "run_traceroute", fake_run_traceroute)
        monkeypatch.setattr(traceroute.random, "random", lambda: 0.0)

        worker = asyncio.create_task(
            traceroute.traceroute_worker(
                worker_id=1,
                G=graph,
                queue=queue,
                params=params,
                seen_ips=seen_ips,
                pending_ips=pending_ips,
                stop_event=stop_event,
                success_counter=success_counter,
                counter_lock=counter_lock,
                logger=Logger(),
            )
        )

        await asyncio.wait_for(error_event.wait(), timeout=1.0)
        await asyncio.sleep(0.2)
        await asyncio.sleep(1.1)
        stop_event.set()
        await queue.put(None)
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass

        assert "bad-host" in "".join(messages)
        assert "2.2.2.2" in graph
        assert success_counter["since_last_draw"] >= 1

    asyncio.run(runner())


def test_ui_manager_fixed_and_dynamic(monkeypatch):
    graph = nx.Graph()
    graph.add_node("1.1.1.1", rtt=1.0)
    params = SimpleNamespace(
        update_mode="fixed", update_interval=0.01, update_count=1, layout="radial"
    )
    counter_lock = asyncio.Lock()
    calls = []
    monkeypatch.setattr(ui, "draw_map", lambda *a, **k: calls.append(k.get("layout")))

    async def runner():
        stop_event = asyncio.Event()
        success_counter = {"since_last_draw": 0}

        task = asyncio.create_task(
            ui.ui_manager(
                graph, "graph", None, params, stop_event, success_counter, counter_lock
            )
        )

        await asyncio.sleep(0.05)
        stop_event.set()
        await task
        assert calls

        # Dynamic mode triggers redraws based on notify callback.
        params.update_mode = "dynamic"
        stop_event = asyncio.Event()
        success_counter = {"since_last_draw": 0}
        task = asyncio.create_task(
            ui.ui_manager(
                graph, "graph", None, params, stop_event, success_counter, counter_lock
            )
        )
        await asyncio.sleep(0.02)
        success_counter["notify"]()
        success_counter["since_last_draw"] = 2
        await asyncio.sleep(0.05)
        stop_event.set()
        success_counter["notify"]()
        await asyncio.sleep(0.02)
        await task
        assert len(calls) >= 2

    asyncio.run(runner())


def test_ui_manager_stops_without_timeout(monkeypatch):
    graph = nx.Graph()
    params = SimpleNamespace(
        update_mode="fixed", update_interval=5.0, update_count=1, layout="radial"
    )
    counter_lock = asyncio.Lock()
    calls = []
    monkeypatch.setattr(ui, "draw_map", lambda *a, **k: calls.append("draw"))

    async def runner():
        stop_event = asyncio.Event()
        success_counter = {"since_last_draw": 0}

        task = asyncio.create_task(
            ui.ui_manager(
                graph, None, None, params, stop_event, success_counter, counter_lock
            )
        )

        await asyncio.sleep(0)
        stop_event.set()
        await task

    asyncio.run(runner())
    assert calls  # Final redraw occurs in the finally clause.
