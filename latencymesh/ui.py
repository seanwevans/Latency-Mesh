import asyncio
from .viz import draw_map


async def ui_manager(
    G, save_base, ax, params, stop_event, success_counter, counter_lock
):
    event = asyncio.Event()

    def notify():
        event.set()

    success_counter.setdefault("since_last_draw", 0)
    success_counter["notify"] = notify
    try:
        while not stop_event.is_set():
            if params.update_mode == "fixed":
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=params.update_interval
                    )
                    break
                except asyncio.TimeoutError:
                    draw_map(
                        G,
                        save_base,
                        ax,
                        layout=getattr(params, "layout", "radial"),
                    )
                    async with counter_lock:
                        success_counter["since_last_draw"] = 0
            else:
                await event.wait()
                event.clear()
                async with counter_lock:
                    count = success_counter.get("since_last_draw", 0)
                if count >= max(1, int(params.update_count)):
                    draw_map(
                        G,
                        save_base,
                        ax,
                        layout=getattr(params, "layout", "radial"),
                    )
                    async with counter_lock:
                        success_counter["since_last_draw"] = 0
    finally:
        draw_map(
            G,
            save_base,
            ax,
            layout=getattr(params, "layout", "radial"),
        )
