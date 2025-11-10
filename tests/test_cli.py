from datetime import timedelta

from latencymesh import cli


def test_parse_args_scan_mode():
    args = cli.parse_args(
        [
            "scan",
            "--save-base",
            "map",
            "--workers",
            "2",
            "--seeds",
            "1.1.1.1",
            "8.8.8.8",
            "--duration",
            "5m",
            "--max-traces",
            "42",
        ]
    )
    assert args.command == "scan"
    assert args.workers == 2
    assert args.seeds == ["1.1.1.1", "8.8.8.8"]
    assert isinstance(args.duration, timedelta)
    assert args.duration.total_seconds() == 300
    assert args.max_traces == 42

    args = cli.parse_args(["scan", "extra1", "extra2"])
    assert args.extra_seeds == ["extra1", "extra2"]


def test_parse_args_other_commands():
    args = cli.parse_args(["export", "graph.json", "--format", "csv"])
    assert args.command == "export"
    assert args.format == "csv"

    args = cli.parse_args(["serve", "--port", "9000", "--directory", "."])
    assert args.command == "serve"
    assert args.port == 9000
