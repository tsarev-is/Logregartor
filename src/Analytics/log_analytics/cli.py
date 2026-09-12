"""Local detection, published batch analysis, and a read-only API."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .baseline import RunConfig
from .clickhouse import ClickHouse, ClickHouseError
from .config import DetectorConfig
from .detectors.build_duration import detect
from .jsonl import read_events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic OpenStack anomaly detection")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("detect", help="Detect slow VM builds in LogParser JSONL")
    command.add_argument("--input", required=True, type=Path, help="LogParser v1 JSONL file")
    command.add_argument("--dataset-id", required=True, help="Dataset to analyze")
    command.add_argument("--threshold-seconds", required=True, type=float,
                         help="Flag durations strictly above this explicit threshold")
    command = commands.add_parser("run", help="Analyze published ClickHouse ingestions")
    command.add_argument("--dataset-id", required=True)
    threshold = command.add_mutually_exclusive_group(required=True)
    threshold.add_argument("--threshold-seconds", type=float)
    threshold.add_argument("--reference-source", action="append", help="Reference source_sha256; repeat for multiple sources")
    command.add_argument("--margin-seconds", type=float)
    command = commands.add_parser("serve", help="Serve published analysis through a read-only API")
    command.add_argument("--host", default="127.0.0.1")
    command.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    if args.command == "run":
        if args.reference_source and args.margin_seconds is None:
            parser.error("--reference-source requires --margin-seconds")
        if args.threshold_seconds is not None and args.margin_seconds is not None:
            parser.error("--margin-seconds cannot be combined with --threshold-seconds")
    if args.command == "serve" and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        if args.command == "detect":
            config = DetectorConfig(args.dataset_id, args.threshold_seconds)
            report = asdict(detect(read_events(args.input), config))
        elif args.command == "run":
            from .runner import run
            config = RunConfig(args.dataset_id, args.threshold_seconds,
                               tuple(args.reference_source or ()), args.margin_seconds)
            report = run(ClickHouse.from_env(), config)
        else:
            from .api import serve
            serve(ClickHouse.from_env(), args.host, args.port)
            return 0
        # Publish only after the entire input has been read successfully.
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, ClickHouseError) as exc:
        print(f"analytics: {exc}", file=sys.stderr)
        return 1
    return 0
