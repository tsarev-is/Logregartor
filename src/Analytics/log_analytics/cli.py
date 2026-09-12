"""CLI начального модуля: JSONL событий → JSON отчёта с инцидентами."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__
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
    args = parser.parse_args(argv)
    try:
        config = DetectorConfig(args.dataset_id, args.threshold_seconds)
        report = detect(read_events(args.input), config)
        # Publish only after the entire input has been read successfully.
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError) as exc:
        print(f"analytics: {exc}", file=sys.stderr)
        return 1
    return 0
