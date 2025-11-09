import asyncio, signal, sys, matplotlib.pyplot as plt
from .cli import parse_args
from .logging_async import log_worker, get_logger
from .io_graph import load_graph, save_graph
from .iptools import generate_local_pool
from .traceroute import traceroute_worker
from .ui import ui_manager


async def main_async(params):
    seeds = params.seeds or ["192.168.1.1", "1.1.1.1", "8.8.8.8"]
    pool = generate_local_pool(seeds, params.prefix, params.max_per_seed or None)
    if not pool:
        print("[error] no addresses in pool; check seeds/prefix")
        return

    log_queue = asyncio.Queue()
    stop_event = asyncio.Event()
    log_task = asyncio.create_task(log_worker(log_queue, stop_event))
    logger = get_logger(log_queue)

    G = load_graph(params.save_base)
    plt.ion() if not params.no_display else None
    _, ax = plt.subplots(figsize=(8, 8)) if not params.no_display else (None, None)

    queue = asyncio.Queue()
    seen_ips, pending_ips = set(G.nodes()), set()

    for ip in pool[: min(256, len(pool))]:
        await queue.put(ip)
        pending_ips.add(ip)

    success_counter, counter_lock = {"since_last_draw": 0}, asyncio.Lock()

    workers = [
        asyncio.create_task(
            traceroute_worker(
                i,
                G,
                queue,
                params,
                seen_ips,
                pending_ips,
                stop_event,
                success_counter,
                counter_lock,
                logger,
            )
        )
        for i in range(params.workers)
    ]
    ui_task = asyncio.create_task(
        ui_manager(
            G,
            params.save_base,
            None if params.no_display else ax,
            params,
            stop_event,
            success_counter,
            counter_lock,
        )
    )

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, lambda s=s: stop_event.set())

    logger.info(
        f"[start] mapping local neighborhood — {params.workers} workers, prefix /{params.prefix}"
    )

    try:
        await stop_event.wait()
    finally:
        for t in [*workers, ui_task]:
            t.cancel()
        await asyncio.gather(*workers, ui_task, return_exceptions=True)
        save_graph(G, params.save_base)
        if ax:
            plt.ioff()
            plt.close("all")
        stop_event.set()
        await log_queue.join()
        log_task.cancel()
        print("[exit] done.")


def main(argv):
    params = parse_args(argv)
    try:
        asyncio.run(main_async(params))
    except KeyboardInterrupt:
        print("\n[interrupt] exiting…")


if __name__ == "__main__":
    main(sys.argv[1:])
