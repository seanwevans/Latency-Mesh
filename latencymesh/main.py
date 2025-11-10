import asyncio
from asyncio import QueueEmpty, QueueFull
import csv
import inspect
import os
import signal
import sys
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterable, List, Optional

import matplotlib.pyplot as plt
import networkx as nx
import uvicorn

from .cli import DEFAULT_SEEDS, parse_args
from .durations import parse_duration
from .io_graph import load_graph, resolve_graph_path, save_graph
from .iptools import generate_local_pool
from .logging_async import get_logger, log_worker
from .traceroute import traceroute_worker
from .ui import ui_manager
from .viz import draw_map
from .webapp import GraphBroadcast, create_app


async def scan_async(params, graph=None, update_queue=None, graph_lock=None):
    seeds = list(params.seeds or [])
    if params.extra_seeds:
        seeds.extend(params.extra_seeds)
    params.seeds = seeds or DEFAULT_SEEDS
    if not hasattr(params, "layout"):
        params.layout = "radial"

    pool = generate_local_pool(params.seeds, params.prefix, params.max_per_seed or None)
    if not pool:
        print("[error] no addresses in pool; check seeds/prefix")
        return

    log_queue = asyncio.Queue()
    stop_event = asyncio.Event()
    log_task = asyncio.create_task(log_worker(log_queue, stop_event))
    logger = get_logger(log_queue)

    G = graph if graph is not None else load_graph(params.save_base)
    graph_lock = graph_lock or asyncio.Lock()
    if not params.no_display:
        plt.ion()
    ax = None
    if not params.no_display:
        _, ax = plt.subplots(figsize=(8, 8))

    queue = asyncio.Queue()
    seen_ips, pending_ips = set(G.nodes()), set()

    for ip in pool:
        await queue.put(ip)
        pending_ips.add(ip)

    success_counter, counter_lock = {"since_last_draw": 0, "total": 0}, asyncio.Lock()

    try:
        worker_signature = inspect.signature(traceroute_worker)
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        worker_signature = None

    worker_kwargs = {}
    if worker_signature:
        if "graph_lock" in worker_signature.parameters:
            worker_kwargs["graph_lock"] = graph_lock
        if "update_queue" in worker_signature.parameters:
            worker_kwargs["update_queue"] = update_queue

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
                **worker_kwargs,
            )
        )
        for i in range(params.workers)
    ]
    ui_task = None
    if not params.no_display:
        try:
            ui_signature = inspect.signature(ui_manager)
        except (TypeError, ValueError):  # pragma: no cover - defensive fallback
            ui_signature = None
        ui_kwargs = {}
        if ui_signature and "graph_lock" in ui_signature.parameters:
            ui_kwargs["graph_lock"] = graph_lock
        ui_task = asyncio.create_task(
            ui_manager(
                G,
                params.save_base,
                ax,
                params,
                stop_event,
                success_counter,
                counter_lock,
                **ui_kwargs,
            )
        )

    loop = asyncio.get_running_loop()
    timer_handles = []
    manual_signal_handlers = []

    def _manual_stop_handler(signum, frame):
        stop_event.set()

    duration_value = getattr(params, "duration", None)
    if isinstance(duration_value, str) and duration_value:
        duration_value = parse_duration(duration_value)
        params.duration = duration_value
    if duration_value is not None:
        seconds = max(duration_value.total_seconds(), 0)
        timer_handles.append(loop.call_later(seconds, stop_event.set))

    max_traces_value = getattr(params, "max_traces", None)
    if max_traces_value is None:
        params.max_traces = None
    else:
        try:
            max_traces_value = int(max_traces_value)
        except (TypeError, ValueError):
            params.max_traces = None
        else:
            params.max_traces = max_traces_value
            if max_traces_value <= 0:
                stop_event.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, lambda s=s: stop_event.set())
        except (NotImplementedError, AttributeError):
            try:
                manual_signal_handlers.append((s, signal.getsignal(s)))
                signal.signal(s, _manual_stop_handler)
            except (ValueError, AttributeError):
                continue

    logger.info(
        f"[start] mapping local neighborhood — {params.workers} workers, prefix /{params.prefix}"
    )

    try:
        await stop_event.wait()
    finally:
        for handle in timer_handles:
            try:
                handle.cancel()
            except Exception:
                pass
        for sig, previous in manual_signal_handlers:
            try:
                signal.signal(sig, previous)
            except (ValueError, AttributeError):
                pass
        tasks = [*workers]
        if ui_task:
            tasks.append(ui_task)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            async with graph_lock:
                save_graph(G, params.save_base)
        except RuntimeError:
            # If the event loop is closing, fall back to an unlocked save
            save_graph(G, params.save_base)
        if ax:
            plt.ioff()
            plt.close("all")
        stop_event.set()
        await log_queue.join()
        log_task.cancel()
        if update_queue is not None:
            sentinel = {"type": "shutdown"}
            try:
                update_queue.put_nowait(sentinel)
            except QueueFull:
                try:
                    update_queue.get_nowait()
                except QueueEmpty:
                    pass
                try:
                    update_queue.put_nowait(sentinel)
                except QueueFull:
                    pass
        print("[exit] done.")


async def _forward_graph_updates(
    update_queue: asyncio.Queue, broadcast: GraphBroadcast
):
    try:
        while True:
            message = await update_queue.get()
            if isinstance(message, dict) and message.get("type") == "shutdown":
                broadcast.close()
                break
            broadcast.notify()
    except asyncio.CancelledError:  # pragma: no cover - cooperative cancellation
        raise


async def serve_async(params):
    params.no_display = True
    host = getattr(params, "host", "0.0.0.0")
    port = getattr(params, "port", 8000)

    G = load_graph(params.save_base)
    graph_lock = asyncio.Lock()
    update_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    broadcast = GraphBroadcast()

    app = create_app(G, graph_lock, broadcast)
    config = uvicorn.Config(app, host=host, port=port, loop="asyncio", log_level="info")
    server = uvicorn.Server(config)

    forwarder = asyncio.create_task(_forward_graph_updates(update_queue, broadcast))
    scan_task = asyncio.create_task(
        scan_async(params, graph=G, update_queue=update_queue, graph_lock=graph_lock)
    )

    try:
        await server.serve()
    finally:
        if not scan_task.done():
            scan_task.cancel()
        await asyncio.gather(scan_task, return_exceptions=True)
        sentinel = {"type": "shutdown"}
        try:
            update_queue.put_nowait(sentinel)
        except QueueFull:
            try:
                update_queue.get_nowait()
            except QueueEmpty:
                pass
            try:
                update_queue.put_nowait(sentinel)
            except QueueFull:
                pass
        await forwarder


def serve_directory(directory: str, port: int) -> None:
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")
    handler = partial(SimpleHTTPRequestHandler, directory=directory)
    httpd = ThreadingHTTPServer(("", port), handler)
    print(f"[serve] Serving {os.path.abspath(directory)} on http://0.0.0.0:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve] shutting down")
    finally:
        httpd.server_close()


def render_graph(graph_path: str, layout: str, output: Optional[str]) -> str:
    resolved = resolve_graph_path(graph_path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Graph not found: {graph_path}")
    base, _ = os.path.splitext(resolved)
    G = load_graph(resolved)
    target = output or f"{base}_{layout}.svg"
    draw_map(G, base, None, layout=layout, output_path=target)
    plt.close("all")
    return target


def export_graph(graph_path: str, fmt: str, output: Optional[str]) -> str:
    resolved = resolve_graph_path(graph_path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Graph not found: {graph_path}")
    base, _ = os.path.splitext(resolved)
    G = load_graph(resolved)

    if fmt == "gexf":
        target = output or f"{base}.gexf"
        nx.write_gexf(G, target)
    elif fmt == "csv":
        target = output or f"{base}.csv"
        with open(target, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["source", "target", "weight"])
            for u, v, data in G.edges(data=True):
                writer.writerow([u, v, data.get("weight", "")])
    else:
        raise ValueError(f"Unsupported export format: {fmt}")
    return target


def graph_stats(graph_path: str) -> dict:
    resolved = resolve_graph_path(graph_path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Graph not found: {graph_path}")
    G = load_graph(resolved)
    num_nodes = G.number_of_nodes()
    num_edges = G.number_of_edges()
    components = nx.number_connected_components(G) if num_nodes else 0
    avg_degree = sum(dict(G.degree()).values()) / num_nodes if num_nodes else 0
    latencies = [
        data.get("rtt") for _, data in G.nodes(data=True) if data.get("rtt") is not None
    ]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    return {
        "nodes": num_nodes,
        "edges": num_edges,
        "components": components,
        "avg_degree": avg_degree,
        "avg_latency": avg_latency,
    }


def prune_graph(
    graph_path: str,
    older_than: Optional[str],
    min_latency: Optional[float],
    output: Optional[str],
) -> str:
    resolved = resolve_graph_path(graph_path)
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Graph not found: {graph_path}")
    G = load_graph(resolved)

    threshold_time: Optional[datetime] = None
    if older_than:
        threshold_time = datetime.utcnow() - parse_duration(older_than)

    to_remove = []
    for node, data in G.nodes(data=True):
        remove = False
        if min_latency is not None:
            rtt = data.get("rtt")
            if rtt is None or rtt < min_latency:
                remove = True
        if not remove and threshold_time is not None:
            last_seen = data.get("last_seen")
            if last_seen:
                try:
                    seen_time = datetime.fromisoformat(last_seen)
                except ValueError:
                    seen_time = None
                if seen_time and seen_time < threshold_time:
                    remove = True
            else:
                remove = True
        if remove:
            to_remove.append(node)

    if to_remove:
        G.remove_nodes_from(to_remove)

    target = output or resolved
    save_graph(G, os.path.splitext(target)[0])
    return resolve_graph_path(target)


def merge_graphs(graphs: Iterable[str], output: str) -> str:
    merged = nx.Graph()
    for graph_path in graphs:
        resolved = resolve_graph_path(graph_path)
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Graph not found: {graph_path}")
        G = load_graph(resolved)
        for node, data in G.nodes(data=True):
            if merged.has_node(node):
                existing = merged.nodes[node]
                if "rtt" in data:
                    rtt_values = [
                        value
                        for value in (existing.get("rtt"), data.get("rtt"))
                        if value is not None
                    ]
                    if rtt_values:
                        existing["rtt"] = min(rtt_values)
                if "last_seen" in data:
                    seen_values = [
                        value
                        for value in (existing.get("last_seen"), data.get("last_seen"))
                        if value
                    ]
                    if seen_values:
                        existing["last_seen"] = max(seen_values)
            else:
                merged.add_node(node, **data)
        for u, v, data in G.edges(data=True):
            if merged.has_edge(u, v):
                existing = merged.edges[u, v]
                if "weight" in data:
                    existing["weight"] = min(
                        existing.get("weight", data["weight"]), data["weight"]
                    )
            else:
                merged.add_edge(u, v, **data)

    save_graph(merged, os.path.splitext(output)[0])
    return resolve_graph_path(output)


def detect_default_gateway() -> Optional[str]:
    try:
        with open("/proc/net/route", encoding="utf-8") as route_file:
            next(route_file, None)  # header
            for line in route_file:
                fields = line.strip().split()
                if len(fields) >= 3 and fields[1] == "00000000":
                    gateway = fields[2]
                    octets = [str(int(gateway[i : i + 2], 16)) for i in range(0, 8, 2)]
                    return ".".join(reversed(octets))
    except FileNotFoundError:
        return None
    return None


def auto_seeds() -> List[str]:
    seeds = []
    gw = detect_default_gateway()
    if gw:
        seeds.append(gw)
    for default in DEFAULT_SEEDS:
        if default not in seeds:
            seeds.append(default)
    return seeds


def main(argv: Optional[List[str]] = None):
    params = parse_args(argv or sys.argv[1:])
    try:
        if params.command == "scan":
            try:
                asyncio.run(scan_async(params))
            except KeyboardInterrupt:
                print("\n[interrupt] exiting…")
        elif params.command == "show":
            target = render_graph(params.graph, params.layout, params.output)
            print(f"[show] wrote {target}")
        elif params.command == "export":
            target = export_graph(params.graph, params.format, params.output)
            print(f"[export] wrote {target}")
        elif params.command == "stats":
            stats = graph_stats(params.graph)
            for key, value in stats.items():
                display = f"{value:.2f}" if isinstance(value, float) else value
                print(f"{key:>12}: {display}")
        elif params.command == "prune":
            target = prune_graph(
                params.graph, params.older_than, params.min_latency, params.output
            )
            print(f"[prune] wrote {target}")
        elif params.command == "merge":
            target = merge_graphs(params.graphs, params.output)
            print(f"[merge] wrote {target}")
        elif params.command == "seed":
            seeds = []
            if params.auto:
                seeds.extend(auto_seeds())
            seeds.extend(params.seeds or [])
            seen = set()
            for seed in seeds:
                if seed not in seen:
                    print(seed)
                    seen.add(seed)
        elif params.command == "serve":
            legacy_directory = getattr(params, "directory", None)
            if legacy_directory is None:
                legacy_directory = getattr(params, "legacy_directory", None)
            if legacy_directory is not None:
                serve_directory(legacy_directory, params.port)
            else:
                try:
                    asyncio.run(serve_async(params))
                except KeyboardInterrupt:
                    print("\n[interrupt] server exiting…")
        else:
            raise ValueError(f"Unknown command: {params.command}")
    except FileNotFoundError as exc:
        print(f"[error] {exc}")
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover - exercised via CLI invocation
    main(sys.argv[1:])
