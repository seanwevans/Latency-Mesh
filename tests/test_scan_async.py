import asyncio
from datetime import timedelta
from types import SimpleNamespace

import networkx as nx

from latencymesh import main


def _build_params():
    return SimpleNamespace(
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
        duration=None,
        max_traces=None,
    )


def test_scan_async_controls_workers(monkeypatch):
    params = _build_params()

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


def test_scan_async_signal_handler_fallback(monkeypatch):
    params = _build_params()

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

    monkeypatch.setattr(main, "log_worker", fake_log_worker)
    monkeypatch.setattr(main, "traceroute_worker", fake_traceroute_worker)
    monkeypatch.setattr(main, "ui_manager", fake_ui_manager)
    monkeypatch.setattr(main, "save_graph", lambda G, save_base: None)

    class FakeLoop:
        def add_signal_handler(self, signum, callback):
            raise NotImplementedError

    fake_loop = FakeLoop()
    monkeypatch.setattr(main.asyncio, "get_running_loop", lambda: fake_loop)

    manual_calls = []

    def fake_signal(sig, handler):
        manual_calls.append((sig, handler))
        handler_name = getattr(handler, "__name__", "")
        if handler_name == "_manual_stop_handler":
            if sig == main.signal.SIGINT:
                handler(sig, None)
                return object()
            raise ValueError("unsupported signal")
        raise ValueError("restore failed")

    monkeypatch.setattr(main.signal, "signal", fake_signal)
    monkeypatch.setattr(main.signal, "getsignal", lambda sig: f"prev-{sig}")

    asyncio.run(main.scan_async(params))

    assert manual_calls, "Fallback signal handler should be registered"
    assert any(call[0] == main.signal.SIGINT for call in manual_calls)


def test_scan_async_processes_full_pool(monkeypatch):
    params = _build_params()

    pool = [f"10.0.0.{i}" for i in range(1, 301)]

    monkeypatch.setattr(main, "generate_local_pool", lambda *a: pool)
    monkeypatch.setattr(main, "load_graph", lambda *_: nx.Graph())

    async def fake_log_worker(queue, stop_event, level=None):
        while not stop_event.is_set() or not queue.empty():
            try:
                await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            queue.task_done()

    processed = []

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
        while not stop_event.is_set():
            try:
                host = await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            processed.append(host)
            pending_ips.discard(host)
            queue.task_done()
            async with counter_lock:
                success_counter["since_last_draw"] = (
                    success_counter.get("since_last_draw", 0) + 1
                )
            if len(processed) == len(pool):
                stop_event.set()

    async def fake_ui_manager(
        G, save_base, ax, params, stop_event, success_counter, counter_lock
    ):
        await stop_event.wait()

    monkeypatch.setattr(main, "log_worker", fake_log_worker)
    monkeypatch.setattr(main, "traceroute_worker", fake_traceroute_worker)
    monkeypatch.setattr(main, "ui_manager", fake_ui_manager)
    monkeypatch.setattr(main, "save_graph", lambda G, save_base: None)

    asyncio.run(main.scan_async(params))

    assert sorted(processed) == sorted(pool)


def test_scan_async_honors_duration_limit(monkeypatch):
    params = _build_params()
    params.duration = timedelta(seconds=5)

    pool = ["1.1.1.1", "1.1.1.2"]

    monkeypatch.setattr(main, "generate_local_pool", lambda *a: pool)
    monkeypatch.setattr(main, "load_graph", lambda *_: nx.Graph())

    async def fake_log_worker(queue, stop_event, level=None):
        while not stop_event.is_set() or not queue.empty():
            try:
                await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            queue.task_done()

    class LoopProxy:
        def __init__(self, loop):
            self.loop = loop
            self.scheduled = []
            self.handles = []

        def call_later(self, delay, callback, *args):
            self.scheduled.append(delay)

            handle = self.loop.call_soon(callback, *args)

            class _Handle:
                def __init__(self, inner):
                    self._inner = inner
                    self.cancelled = False

                def cancel(self):
                    self.cancelled = True
                    try:
                        self._inner.cancel()
                    except Exception:
                        pass

            wrapper = _Handle(handle)
            self.handles.append(wrapper)
            return wrapper

        def __getattr__(self, name):
            return getattr(self.loop, name)

    proxy_holder = {}

    real_get_running_loop = asyncio.get_running_loop

    def fake_get_running_loop():
        loop = real_get_running_loop()
        proxy = LoopProxy(loop)
        proxy_holder["loop"] = proxy
        return proxy

    async def passive_worker(
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
        try:
            while not stop_event.is_set():
                try:
                    host = await asyncio.wait_for(queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                pending_ips.discard(host)
                queue.task_done()
        except asyncio.CancelledError:
            pass

    async def fake_ui_manager(
        G, save_base, ax, params, stop_event, success_counter, counter_lock
    ):
        await stop_event.wait()

    monkeypatch.setattr(main, "log_worker", fake_log_worker)
    monkeypatch.setattr(main, "traceroute_worker", passive_worker)
    monkeypatch.setattr(main, "ui_manager", fake_ui_manager)
    monkeypatch.setattr(main, "save_graph", lambda G, save_base: None)
    monkeypatch.setattr(main.asyncio, "get_running_loop", fake_get_running_loop)

    asyncio.run(main.scan_async(params))

    proxy = proxy_holder["loop"]
    assert proxy.scheduled == [5]
    assert proxy.handles and all(handle.cancelled for handle in proxy.handles)


def test_scan_async_honors_max_traces(monkeypatch):
    params = _build_params()
    params.max_traces = 2

    pool = [f"10.0.0.{i}" for i in range(1, 5)]

    monkeypatch.setattr(main, "generate_local_pool", lambda *a: pool)
    monkeypatch.setattr(main, "load_graph", lambda *_: nx.Graph())

    async def fake_log_worker(queue, stop_event, level=None):
        while not stop_event.is_set() or not queue.empty():
            try:
                await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            queue.task_done()

    processed = []

    async def fake_sleep(_delay):
        return None

    from latencymesh import traceroute as traceroute_mod

    async def stub_traceroute(host, *_args, **_kwargs):
        processed.append(host)
        return [(host, 1.0)]

    async def stop_event_waiter(
        G, save_base, ax, params, stop_event, success_counter, counter_lock
    ):
        await stop_event.wait()

    monkeypatch.setattr(traceroute_mod, "run_traceroute", stub_traceroute)
    monkeypatch.setattr(traceroute_mod.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(main, "log_worker", fake_log_worker)
    monkeypatch.setattr(main, "ui_manager", stop_event_waiter)
    monkeypatch.setattr(main, "save_graph", lambda G, save_base: None)

    asyncio.run(main.scan_async(params))

    assert processed == pool[: params.max_traces]
