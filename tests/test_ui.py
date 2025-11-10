import asyncio
from types import SimpleNamespace

import pytest

from latencymesh import ui


async def _set_event_after_yield(event: asyncio.Event):
    await asyncio.sleep(0)
    event.set()


@pytest.mark.asyncio
async def test_ui_manager_fixed_mode_breaks_on_stop_event(monkeypatch):
    draw_calls = []

    def fake_draw(G, save_base, ax, layout):
        draw_calls.append((G, save_base, ax, layout))

    monkeypatch.setattr(ui, "draw_map", fake_draw)

    params = type(
        "Params",
        (),
        {
            "update_mode": "fixed",
            "update_interval": 0.01,
        },
    )()
    stop_event = asyncio.Event()
    success_counter = {}
    counter_lock = asyncio.Lock()

    task = asyncio.create_task(
        ui.ui_manager(
            G="graph",
            save_base="base",
            ax="axes",
            params=params,
            stop_event=stop_event,
            success_counter=success_counter,
            counter_lock=counter_lock,
            graph_lock=None,
        )
    )

    for _ in range(50):
        if draw_calls:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("ui_manager did not trigger draw_map in fixed mode")

    stop_task = asyncio.create_task(_set_event_after_yield(stop_event))

    await task
    await stop_task

    assert len(draw_calls) >= 2
    assert draw_calls[0] == ("graph", "base", "axes", "radial")
    assert draw_calls[-1] == ("graph", "base", "axes", "radial")
    assert success_counter["since_last_draw"] == 0
    assert callable(success_counter["notify"])


@pytest.mark.asyncio
async def test_ui_manager_fixed_mode_uses_graph_lock(monkeypatch):
    graph_lock = asyncio.Lock()
    stop_event = asyncio.Event()
    success_counter = {}
    counter_lock = asyncio.Lock()
    lock_states = []

    def fake_draw(G, save_base, ax, layout):
        lock_states.append(graph_lock.locked())

    monkeypatch.setattr(ui, "draw_map", fake_draw)

    params = SimpleNamespace(update_mode="fixed", update_interval=0.01, layout="spring")

    task = asyncio.create_task(
        ui.ui_manager(
            G="graph",
            save_base="base",
            ax="axes",
            params=params,
            stop_event=stop_event,
            success_counter=success_counter,
            counter_lock=counter_lock,
            graph_lock=graph_lock,
        )
    )

    for _ in range(50):
        if lock_states:
            break
        await asyncio.sleep(0.01)
    else:
        pytest.fail("ui_manager did not draw while graph_lock was present")

    stop_task = asyncio.create_task(_set_event_after_yield(stop_event))

    await task
    await stop_task

    assert len(lock_states) >= 2
    assert all(lock_states)
    assert success_counter["since_last_draw"] == 0


@pytest.mark.asyncio
async def test_ui_manager_event_mode_with_graph_lock(monkeypatch):
    graph_lock = asyncio.Lock()
    stop_event = asyncio.Event()
    success_counter = {}
    counter_lock = asyncio.Lock()
    lock_states = []

    def fake_draw(G, save_base, ax, layout):
        lock_states.append((graph_lock.locked(), layout))
        if len(lock_states) == 1:
            stop_event.set()

    monkeypatch.setattr(ui, "draw_map", fake_draw)

    params = SimpleNamespace(update_mode="event", update_count=2, layout="spring")

    task = asyncio.create_task(
        ui.ui_manager(
            G="graph",
            save_base="base",
            ax="axes",
            params=params,
            stop_event=stop_event,
            success_counter=success_counter,
            counter_lock=counter_lock,
            graph_lock=graph_lock,
        )
    )

    for _ in range(50):
        if "notify" in success_counter:
            break
        await asyncio.sleep(0)
    else:
        pytest.fail("ui_manager did not register notify callback")

    success_counter["since_last_draw"] = 2
    success_counter["notify"]()

    await task

    assert len(lock_states) == 2
    assert all(locked for locked, _ in lock_states)
    assert all(layout == "spring" for _, layout in lock_states)
    assert success_counter["since_last_draw"] == 0


@pytest.mark.asyncio
async def test_ui_manager_event_mode_without_graph_lock(monkeypatch):
    stop_event = asyncio.Event()
    success_counter = {}
    counter_lock = asyncio.Lock()
    draw_calls = []

    def fake_draw(G, save_base, ax, layout):
        draw_calls.append(layout)
        if len(draw_calls) == 1:
            stop_event.set()

    monkeypatch.setattr(ui, "draw_map", fake_draw)

    params = SimpleNamespace(update_mode="event", update_count=1, layout="planar")

    task = asyncio.create_task(
        ui.ui_manager(
            G="graph",
            save_base="base",
            ax="axes",
            params=params,
            stop_event=stop_event,
            success_counter=success_counter,
            counter_lock=counter_lock,
            graph_lock=None,
        )
    )

    for _ in range(50):
        if "notify" in success_counter:
            break
        await asyncio.sleep(0)
    else:
        pytest.fail("ui_manager did not register notify callback")

    success_counter["since_last_draw"] = 1
    success_counter["notify"]()

    await task

    assert len(draw_calls) == 2
    assert all(layout == "planar" for layout in draw_calls)
    assert success_counter["since_last_draw"] == 0
