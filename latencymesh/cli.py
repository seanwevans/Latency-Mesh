import argparse


def parse_args(argv):
    argp = argparse.ArgumentParser(description="Local Async Internet Latency Mapper")
    
    argp.add_argument(
        "-s", "--save-base", default="internet_map", help="Base filename for output"
    )
    argp.add_argument(
        "-w", "--workers", type=int, default=5, help="Concurrent traceroute workers"
    )
    argp.add_argument(
        "--pps", type=float, default=1.0, help="Rate limit (traceroutes/sec per worker)"
    )
    argp.add_argument("--prefix", type=int, default=16, help="Local prefix length")
    argp.add_argument(
        "--max-per-seed", type=int, default=4096, help="Max addresses per seed"
    )
    argp.add_argument(
        "--timeout", type=float, default=1.0, help="Per-hop timeout (seconds)"
    )
    argp.add_argument(
        "--max-hops", type=int, default=30, help="Max hops per traceroute"
    )
    argp.add_argument(
        "--no-display", action="store_true", help="Run headless (no live plot)"
    )
    argp.add_argument(
        "--update-mode",
        choices=["fixed", "dynamic"],
        default="fixed",
        help="UI update mode",
    )
    argp.add_argument(
        "--update-interval",
        type=float,
        default=1.0,
        help="Seconds between redraws (fixed mode)",
    )
    argp.add_argument(
        "--update-count",
        type=int,
        default=5,
        help="Traceroutes per redraw (dynamic mode)",
    )
    argp.add_argument("seeds", nargs="*", help="Seed IPs")
    
    return argp.parse_args(argv)
