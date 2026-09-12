"""Проверяемые JSONL-артефакты и атомарная запись локальных результатов."""

import hashlib
import json
import math
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import fastjsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schema/log-event.v1.json").read_text())
VALIDATE = fastjsonschema.compile(SCHEMA)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid_constant)


def invalid_constant(value):
    raise ValueError(f"non-finite JSON number: {value}")


@contextmanager
def atomic_writer(path, mode="w"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".logparser-", dir=path.parent)
    try:
        kwargs = {} if "b" in mode else {"encoding": "utf-8", "newline": "\n"}
        with os.fdopen(fd, mode, **kwargs) as out:
            yield out
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    with atomic_writer(path) as out:
        out.write(canonical(value) + "\n")


def distinct_paths(*paths):
    resolved = [Path(p).resolve() for p in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("input, output and report paths must be distinct")
    for i, path in enumerate(resolved):
        for other in resolved[:i]:
            if path.exists() and other.exists() and path.samefile(other):
                raise ValueError("input/output paths alias the same file")


def read_report(events, report_path):
    report = load_json(report_path)
    if report.get("schema_version") != 1:
        raise ValueError("unsupported report schema_version")
    if sha256(events) != report.get("events_sha256"):
        raise ValueError("JSONL hash differs from report (incomplete or changed artifact)")
    files = report.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("report must identify its input files, including empty files")
    seen = set()
    total = 0
    for item in files:
        source = item["source_sha256"]
        count = item["physical_lines"]
        if source in seen or not isinstance(count, int) or count < 0:
            raise ValueError("duplicate source or invalid source line count")
        seen.add(source)
        total += count
    if total != report["physical_lines"]:
        raise ValueError("report line counts do not add up")
    return report


def read_events(path, report):
    """Validate shape, identity, order and byte-exact source coverage while streaming.

    Callers must consume the iterator fully before publishing their output.
    """
    manifests = report["files"]
    hashes = {f["source_sha256"]: hashlib.sha256() for f in manifests}
    counts = dict.fromkeys(hashes, 0)
    positions = {f["source_sha256"]: i for i, f in enumerate(manifests)}
    last_position = -1
    artifact_hash = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            artifact_hash.update(raw)
            try:
                event = json.loads(raw, parse_constant=invalid_constant)
                VALIDATE(event)
                source = event["source_sha256"]
                position = positions[source]
                if position < last_position:
                    raise ValueError("sources must be contiguous and in manifest order")
                last_position = position
                counts[source] += 1
                line = counts[source]
                expected = hashlib.sha256(f"{source}:{line}".encode()).hexdigest()
                if event["event_id"] != expected or event["line_start"] != line or event["line_end"] != line:
                    raise ValueError("invalid event identity or non-contiguous physical lines")
                for key in ("dataset_id", "schema_version", "parser_version", "timezone_assumption"):
                    if event[key] != report[key]:
                        raise ValueError(f"event differs from report: {key}")
                if event["source_file"] != manifests[position]["source_file"]:
                    raise ValueError("event source filename differs from report")
                if event["line_ending"] == "" and line != manifests[position]["physical_lines"]:
                    raise ValueError("only the final physical line may lack a terminator")
                for key, value in event.items():
                    if isinstance(value, float) and not math.isfinite(value):
                        raise ValueError(f"non-finite value: {key}")
                if any(not math.isfinite(v) for v in event["parameters"].values()):
                    raise ValueError("non-finite resource value")
                hashes[source].update((event["raw_text"] + event["line_ending"]).encode("utf-8"))
                yield event
            except (ValueError, KeyError, TypeError, fastjsonschema.JsonSchemaException) as exc:
                raise ValueError(f"{path}:{number}: {exc}") from exc
    if artifact_hash.hexdigest() != report["events_sha256"]:
        raise ValueError("artifact changed while reading")
    for item in manifests:
        source = item["source_sha256"]
        if counts[source] != item["physical_lines"] or hashes[source].hexdigest() != source:
            raise ValueError(f"source coverage/hash mismatch: {item['source_file']}")
