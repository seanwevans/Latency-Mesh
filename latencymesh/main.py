import asyncio
import csv
import os
import signal
import sys
from datetime import datetime, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterable, List, Optional

import matplotlib.pyplot as plt
import networkx as nx

from .cli import DEFAULT_SEEDS, parse_args
from .io_graph import load_graph, resolve_graph_path, save_graph
from .iptools import generate_local_pool
from .logging_async import get_logger, log_worker
from .traceroute import traceroute_worker
from .ui import ui_manager
from .viz import draw_map


async def scan_async(params):
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

    G = load_graph(params.save_base)
    if not params.no_display:
        plt.ion()
    ax = None
    if not params.no_display:
        _, ax = plt.subplots(figsize=(8, 8))

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
    manual_signal_handlers = []

    def _manual_stop_handler(signum, frame):
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
        for sig, previous in manual_signal_handlers:
            try:
                signal.signal(sig, previous)
            except (ValueError, AttributeError):
                pass
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
    latencies = [data.get("rtt") for _, data in G.nodes(data=True) if data.get("rtt")]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    return {
        "nodes": num_nodes,
        "edges": num_edges,
        "components": components,
        "avg_degree": avg_degree,
        "avg_latency": avg_latency,
    }


def parse_duration(expr: str) -> timedelta:
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    expr = expr.strip().lower()
    if not expr:
        raise ValueError("Duration expression cannot be empty")
    value = expr[:-1]
    unit = expr[-1]
    if unit not in units:
        value = expr
        unit = "s"
    try:
        amount = float(value)
    except ValueError as exc:
        raise ValueError(f"Invalid duration: {expr}") from exc
    return timedelta(seconds=amount * units[unit])


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
    return target


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
                    rtt_values = [value for value in (existing.get("rtt"), data.get("rtt")) if value is not None]
                    if rtt_values:
                        existing["rtt"] = min(rtt_values)
                if "last_seen" in data:
                    seen_values = [value for value in (existing.get("last_seen"), data.get("last_seen")) if value]
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
    return output


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
            serve_directory(params.directory, params.port)
        else:
            raise ValueError(f"Unknown command: {params.command}")
    except FileNotFoundError as exc:
        print(f"[error] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
