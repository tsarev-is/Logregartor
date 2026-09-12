import argparse
import logging
import subprocess
import sys
from pathlib import Path

from .artifacts import ROOT, canonical, load_json, read_report, write_json
from .evaluate import evaluate
from .prepare import prepare
from .storage import ClickHouse, ClickHouseError, load
from .templates import fit, load_state, transform


def parse_with_go(binary, inputs, dataset, timezone, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(Path(binary).resolve()), "parse", "--dataset-id", dataset,
               "--timezone", timezone, "--output", str(output)]
    for path in inputs:
        command.extend(["--input", str(path)])
    subprocess.run(command, check=True)
    return output, Path(str(output) + ".report.json")


def run(args):
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    reference, reference_report = parse_with_go(args.parser, [args.reference], args.dataset_id,
                                                args.timezone, work / "reference.jsonl")
    state = Path(args.state_dir)
    if not state.exists():
        fit(reference, reference_report, state, args.config)
    else:
        _, manifest, _ = load_state(state)
        report = read_report(reference, reference_report)
        identity = manifest["identity"]
        expected_sources = sorted(f["source_sha256"] for f in report["files"])
        if identity["reference_sources"] != expected_sources or any(identity[k] != report[k] for k in ("parser_version", "timezone_assumption")):
            raise ValueError("existing vocabulary belongs to a different reference/configuration; use a new --state-dir")
        if identity["settings"] != load_json(args.config or ROOT / "config/drain.json"):
            raise ValueError("existing vocabulary uses different masks/settings; use a new --state-dir")
    events, report = parse_with_go(args.parser, args.input, args.dataset_id, args.timezone, work / "normalized.jsonl")
    enriched, enriched_report = work / "events.jsonl", work / "events.jsonl.report.json"
    transform(events, report, enriched, enriched_report, state)
    result = load(enriched, enriched_report, state, ClickHouse.from_env(), args.batch_size)
    write_json(work / "ingestion.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="OpenStack: Go JSONL → frozen Drain3 vocabulary → ClickHouse")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="download/verify the pinned OpenStack dataset")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--cache-dir")
    for name in ("fit", "transform", "load", "evaluate"):
        p = sub.add_parser(name)
        p.add_argument("--input", required=True)
        p.add_argument("--report", help="default: INPUT.report.json")
        if name != "evaluate":
            p.add_argument("--state-dir", required=True)
        if name == "fit":
            p.add_argument("--config")
        if name == "transform":
            p.add_argument("--output", required=True)
            p.add_argument("--output-report", help="default: OUTPUT.report.json")
        if name == "load":
            p.add_argument("--batch-size", type=int, default=5000)
        if name == "evaluate":
            p.add_argument("--reference-csv", required=True)
    p = sub.add_parser("run")
    p.add_argument("--input", action="append", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--timezone", default="UTC")
    p.add_argument("--parser", default=str(ROOT / "bin/logparser"))
    p.add_argument("--work-dir", required=True)
    p.add_argument("--state-dir", required=True)
    p.add_argument("--config")
    p.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    try:
        if args.command == "prepare":
            result = prepare(args.output_dir, args.cache_dir)
        elif args.command == "run":
            result = run(args)
        else:
            report = args.report or args.input + ".report.json"
            if args.command == "fit":
                result = fit(args.input, report, args.state_dir, args.config)
            elif args.command == "transform":
                result = transform(args.input, report, args.output, args.output_report or args.output + ".report.json", args.state_dir)
            elif args.command == "load":
                result = load(args.input, report, args.state_dir, ClickHouse.from_env(), args.batch_size)
            else:
                result = evaluate(args.input, report, args.reference_csv)
        print(canonical(result))
    except (ValueError, OSError, KeyError, ClickHouseError, subprocess.CalledProcessError) as exc:
        print(f"pipeline: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
