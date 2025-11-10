import argparse
from typing import List


DEFAULT_SEEDS: List[str] = ["192.168.1.1", "1.1.1.1", "8.8.8.8"]


def add_scan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--save-base", default="internet_map", help="Base filename for output"
    )
    parser.add_argument(
        "--workers", type=int, default=5, help="Concurrent traceroute workers"
    )
    parser.add_argument(
        "--pps", type=float, default=1.0, help="Rate limit (traceroutes/sec per worker)"
    )
    parser.add_argument("--prefix", type=int, default=16, help="Local prefix length")
    parser.add_argument(
        "--max-per-seed", type=int, default=4096, help="Max addresses per seed"
    )
    parser.add_argument(
        "--timeout", type=float, default=1.0, help="Per-hop timeout (seconds)"
    )
    parser.add_argument(
        "--max-hops", type=int, default=30, help="Max hops per traceroute"
    )
    parser.add_argument(
        "--update-mode",
        choices=["fixed", "dynamic"],
        default="fixed",
        help="UI update mode",
    )
    parser.add_argument(
        "--update-interval",
        type=float,
        default=1.0,
        help="Seconds between redraws (fixed mode)",
    )
    parser.add_argument(
        "--update-count",
        type=int,
        default=5,
        help="Traceroutes per redraw (dynamic mode)",
    )
    parser.add_argument(
        "--no-display", action="store_true", help="Run headless (no live plot)"
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        metavar="IP",
        help="Seed IPs to bootstrap the scan",
    )
    parser.add_argument(
        "extra_seeds",
        nargs="*",
        metavar="IP",
        help="Additional positional seed IPs",
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lm", description="LatencyMesh command-line interface"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Perform an asynchronous traceroute scan")
    add_scan_arguments(scan)

    show = subparsers.add_parser("show", help="Render a stored internet map")
    show.add_argument("graph", help="Path to a JSON graph file")
    show.add_argument(
        "--layout",
        choices=["radial", "spring", "planar"],
        default="radial",
        help="Layout algorithm for rendering",
    )
    show.add_argument(
        "--output", help="Optional output image path (default: <graph>_<layout>.svg)"
    )

    export = subparsers.add_parser("export", help="Export a map to an alternate format")
    export.add_argument("graph", help="Path to a JSON graph file")
    export.add_argument(
        "--format",
        choices=["gexf", "csv"],
        required=True,
        help="Export format",
    )
    export.add_argument(
        "--output", help="Optional output path (default derived from input)"
    )

    stats = subparsers.add_parser("stats", help="Show statistics for a graph")
    stats.add_argument("graph", help="Path to a JSON graph file")

    prune = subparsers.add_parser("prune", help="Remove stale or low-quality nodes")
    prune.add_argument("graph", help="Path to a JSON graph file")
    prune.add_argument(
        "--older-than",
        help="Remove nodes older than the provided duration (e.g. 7d, 12h)",
    )
    prune.add_argument(
        "--min-latency",
        type=float,
        help="Remove nodes whose RTT is below this threshold (ms)",
    )
    prune.add_argument(
        "--output", help="Optional output path (default overwrites the input)"
    )

    merge = subparsers.add_parser("merge", help="Combine multiple graph files")
    merge.add_argument("graphs", nargs="+", help="Graph files to merge")
    merge.add_argument(
        "--output",
        default="merged.json",
        help="Output filename for the merged graph",
    )

    seed = subparsers.add_parser("seed", help="List or derive seed IPs")
    seed.add_argument(
        "--auto",
        action="store_true",
        help="Include automatically detected local/default seed addresses",
    )
    seed.add_argument("seeds", nargs="*", help="Additional manual seed addresses")

    serve = subparsers.add_parser("serve", help="Run the LatencyMesh web interface")
    serve.add_argument("--host", default="0.0.0.0", help="Host interface for the API")
    serve.add_argument(
        "--port", type=int, default=8000, help="Port to bind the HTTP server"
    )
    serve.add_argument(
        "--directory",
        dest="legacy_directory",
        help=argparse.SUPPRESS,
    )
    add_scan_arguments(serve)

    return parser


def parse_args(argv):
    parser = create_parser()
    return parser.parse_args(argv)
