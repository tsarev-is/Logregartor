"""Batch orchestration: freeze inputs, detect, stage, verify, publish once."""

import fcntl
import hashlib
import json
import os
import tempfile
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from . import stages
from .baseline import RunConfig, resolve_threshold
from .clickhouse import canonical
from .config import DetectorConfig
from .detectors.build_duration import NAME, VERSION, detect
from .storage import Store

RUN_VERSION = "1.0.0"


@contextmanager
def writer_lock(client):
    key = hashlib.sha256(canonical([client.url, client.database]).encode()).hexdigest()
    path = Path(tempfile.gettempdir()) / f"analytics-{os.getuid()}-{key}.lock"
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another local Analytics writer is using this database") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def run(client, config: RunConfig):
    with writer_lock(client):
        client.migrate()
        store = Store(client)
        snapshot = store.snapshot(config.dataset_id)
        if not snapshot:
            raise ValueError("dataset has no published LogParser ingestions")
        version = hashlib.sha256(canonical({"inputs": snapshot, "config": config.identity(),
                                           "detector": NAME, "detector_version": VERSION,
                                           "stage_rules_version": stages.VERSION,
                                           "run_version": RUN_VERSION}).encode()).hexdigest()
        previous = store.completed(config.dataset_id, version)
        if previous:
            store.assert_snapshot(config.dataset_id, snapshot)
            # Re-select an older completed result when a user returns to its configuration.
            if store.current_report(config.dataset_id)["analysis_run_id"] != previous["analysis_run_id"]:
                client.insert("analysis_runs", [{**previous, "status": "completed"}])
            return json.loads(previous["report_json"])
        attempt = {"analysis_run_id": str(uuid.uuid4()), "dataset_id": config.dataset_id,
                   "analysis_version": version, "input_snapshot_json": canonical(snapshot),
                   "configuration_json": canonical(config.identity()), "report_json": ""}
        client.insert("analysis_runs", [{**attempt, "status": "started"}])
        events = store.read_events(config.dataset_id, snapshot)
        store.assert_snapshot(config.dataset_id, snapshot)
        builds = [event.build for event in events]
        threshold, baseline = resolve_threshold(builds, config, {row["source_sha256"] for row in snapshot})
        detection = detect(builds, DetectorConfig(config.dataset_id, threshold))
        report = {**asdict(detection), "analysis_run_id": attempt["analysis_run_id"],
                  "analysis_version": version, "input_ingestions": snapshot, "baseline": baseline,
                  "stage_rules_version": stages.VERSION, "incidents": []}
        by_vm = defaultdict(list)
        for event in events:
            if event.build.instance_id is not None:
                by_vm[event.build.source_sha256, event.build.instance_id].append(event)
        timelines = {}
        for incident in detection.incidents:
            vm = by_vm[incident.source_sha256, incident.instance_id]
            observations, completeness, timeline = stages.episode(vm, incident)
            report["incidents"].append({**asdict(incident), "analysis_run_id": attempt["analysis_run_id"],
                                        "baseline": baseline, "stages": observations,
                                        "stage_rules_version": stages.VERSION, "completeness": completeness})
            timelines[incident.incident_id] = {**timeline, "analysis_run_id": attempt["analysis_run_id"],
                                              "incident_id": incident.incident_id,
                                              "evidence_ids": list(incident.evidence_ids)}
        # Normalize tuple/list serialization so a repeat has exactly the same return contract.
        report = json.loads(canonical(report))
        store.stage(report, timelines)
        store.assert_snapshot(config.dataset_id, snapshot)
        client.insert("analysis_runs", [{**attempt, "report_json": canonical(report), "status": "completed"}])
        return report
