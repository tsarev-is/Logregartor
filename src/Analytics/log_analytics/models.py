"""Минимальная проекция события LogParser v1 и выходной контракт детектора."""

import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BuildEvent:
    event_id: str
    dataset_id: str
    source_sha256: str
    instance_id: str | None
    event_time: str | None
    build_duration_seconds: float | None

    @classmethod
    def from_record(cls, record: Any) -> "BuildEvent":
        if not isinstance(record, dict):
            raise ValueError("event must be a JSON object")
        if type(record.get("schema_version")) is not int or record["schema_version"] != 1:
            raise ValueError("expected LogParser schema_version 1")
        required = (
            "event_id", "dataset_id", "source_sha256", "instance_id",
            "event_time", "build_duration_seconds",
        )
        for name in required:
            if name not in record:
                raise ValueError(f"missing field: {name}")
        for name in ("event_id", "source_sha256"):
            value = record[name]
            if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex string")
        if not isinstance(record["dataset_id"], str) or not record["dataset_id"].strip():
            raise ValueError("dataset_id must be a nonempty string")
        for name in ("instance_id", "event_time"):
            value = record[name]
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a nonempty string or null")
        duration = record["build_duration_seconds"]
        if duration is not None and (
            type(duration) not in (int, float)
            or not math.isfinite(duration)
            or duration < 0
        ):
            raise ValueError("build_duration_seconds must be finite, nonnegative or null")
        return cls(**{name: record[name] for name in required})


@dataclass(frozen=True)
class Incident:
    incident_id: str
    dataset_id: str
    source_sha256: str
    instance_id: str
    detector: str
    detector_version: str
    event_time: str | None
    observed_seconds: float
    threshold_seconds: float
    excess_seconds: float
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class DetectionReport:
    schema_version: int
    dataset_id: str
    detector: str
    detector_version: str
    threshold_seconds: float
    events_read: int
    instances_observed: int
    completed_instances: int
    incomplete_instances: int
    incidents: tuple[Incident, ...]
