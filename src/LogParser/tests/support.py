import atexit
import functools
import os
import subprocess
import tempfile
from pathlib import Path

from pipeline.artifacts import ROOT
from pipeline.__main__ import parse_with_go
from pipeline.templates import fit, transform

HEADER = "nova-compute.log.1 2017-05-14 21:43:33.901 2931 INFO nova.compute.manager"
INSTANCE = "[instance: a445709b-6ad0-40ec-8860-bec60b6ca0c2]"
NORMAL = (f"{HEADER} [-] {INSTANCE} Took 19.05 seconds to build instance.\n"
          f"{HEADER} [-] {INSTANCE} Took 20.54 seconds to build instance.\n")


@functools.lru_cache
def binary():
    if os.getenv("LOGPARSER_BINARY"):
        return Path(os.environ["LOGPARSER_BINARY"]).resolve()
    directory = tempfile.TemporaryDirectory(prefix="logparser-tests-")
    atexit.register(directory.cleanup)
    path = Path(directory.name) / "logparser"
    env = os.environ.copy()
    env.setdefault("GOCACHE", str(Path(tempfile.gettempdir()) / "logparser-test-go-cache"))
    subprocess.run(["go", "build", "-o", str(path), "."], cwd=ROOT, env=env, check=True)
    return path


def parsed(directory, content=NORMAL, name="source", dataset="test"):
    directory = Path(directory)
    source = directory / f"{name}.log"
    source.write_text(content, encoding="utf-8", newline="")
    return parse_with_go(binary(), [source], dataset, "UTC", directory / f"{name}.jsonl")


def enriched(directory, content=NORMAL, dataset="test"):
    directory = Path(directory)
    reference, report = parsed(directory, dataset=dataset)
    state = directory / "state"
    fit(reference, report, state)
    events, event_report = reference, report
    if content != NORMAL:
        events, event_report = parsed(directory, content, name="target", dataset=dataset)
    output = directory / "enriched.jsonl"
    output_report = directory / "enriched.report.json"
    transform(events, event_report, output, output_report, state)
    return output, output_report, state
