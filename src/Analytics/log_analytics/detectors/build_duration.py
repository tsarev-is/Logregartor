"""Пакетное обнаружение медленного создания VM по явной длительности."""

import hashlib
import json
from collections.abc import Iterable

from ..config import DetectorConfig
from ..models import BuildEvent, DetectionReport, Incident

NAME = "slow_vm_build"
VERSION = "0.1.0"


def detect(events: Iterable[BuildEvent], config: DetectorConfig) -> DetectionReport:
    observed: set[tuple[str, str]] = set()
    completed: dict[tuple[str, str], BuildEvent] = {}
    events_read = 0
    for event in events:
        events_read += 1
        if event.dataset_id != config.dataset_id or event.instance_id is None:
            continue
        key = (event.source_sha256, event.instance_id)
        observed.add(key)
        if event.build_duration_seconds is None:
            continue
        previous = completed.get(key)
        # A deterministic tie-break preserves the selected evidence on reordered input.
        if previous is None or (
            event.build_duration_seconds, event.event_id
        ) > (previous.build_duration_seconds, previous.event_id):
            completed[key] = event

    incidents = []
    for (source, instance), event in completed.items():
        duration = event.build_duration_seconds
        if duration <= config.threshold_seconds:
            continue
        # Identity belongs to the VM and anomaly class; a changed threshold updates it.
        identity = json.dumps([config.dataset_id, source, instance, NAME], separators=(",", ":"))
        incidents.append(Incident(
            incident_id=hashlib.sha256(identity.encode()).hexdigest(),
            dataset_id=config.dataset_id,
            source_sha256=source,
            instance_id=instance,
            detector=NAME,
            detector_version=VERSION,
            event_time=event.event_time,
            observed_seconds=duration,
            threshold_seconds=config.threshold_seconds,
            excess_seconds=duration - config.threshold_seconds,
            evidence_ids=(event.event_id,),
        ))
    incidents.sort(key=lambda incident: (-incident.excess_seconds, incident.incident_id))
    return DetectionReport(
        schema_version=1,
        dataset_id=config.dataset_id,
        detector=NAME,
        detector_version=VERSION,
        threshold_seconds=config.threshold_seconds,
        events_read=events_read,
        instances_observed=len(observed),
        completed_instances=len(completed),
        incomplete_instances=len(observed - completed.keys()),
        incidents=tuple(incidents),
    )
