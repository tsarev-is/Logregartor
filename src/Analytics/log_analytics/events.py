"""Validated timeline projection; timestamps retain nanoseconds in UTC."""

import calendar
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .models import BuildEvent

TIME = re.compile(r"(\d{4}-\d\d-\d\d)[T ](\d\d:\d\d:\d\d)(\.\d{1,9})?(Z|[+-]\d\d:\d\d)?")


def utc_time(value: str) -> tuple[str, int]:
    match = TIME.fullmatch(value)
    if not match:
        raise ValueError("invalid event_time")
    day, clock, fraction, zone = match.groups()
    moment = datetime.fromisoformat(f"{day}T{clock}{zone or '+00:00'}").astimezone(timezone.utc)
    fraction = fraction or ""
    nanos = calendar.timegm(moment.utctimetuple()) * 1_000_000_000
    nanos += int(fraction[1:].ljust(9, "0") or "0")
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + fraction + "Z", nanos


@dataclass(frozen=True)
class AnalysisEvent:
    build: BuildEvent
    record: dict[str, Any]
    time_ns: int | None

    @property
    def line(self) -> int:
        return self.record["line_start"]

    @property
    def order(self) -> tuple[int, int, str]:
        if self.time_ns is None:
            raise ValueError("undated event has no chronological position")
        return self.time_ns, self.line, self.build.event_id

    @classmethod
    def from_record(cls, record: Any) -> "AnalysisEvent":
        build = BuildEvent.from_record(record)
        for name in ("line_start", "line_end"):
            if type(record.get(name)) is not int or record[name] < 1:
                raise ValueError(f"{name} must be a positive integer")
        if record["line_end"] < record["line_start"]:
            raise ValueError("invalid event line range")
        for name in ("message", "raw_text", "line_ending", "parse_status"):
            if not isinstance(record.get(name), str):
                raise ValueError(f"{name} must be a string")
        if record["parse_status"] not in {"ok", "partial", "unparsed", "empty"}:
            raise ValueError("invalid parse_status")
        if "component" not in record or (record["component"] is not None
                                          and not isinstance(record["component"], str)):
            raise ValueError("component must be a string or null")
        if "spawn_duration_seconds" not in record:
            raise ValueError("missing field: spawn_duration_seconds")
        duration = record["spawn_duration_seconds"]
        if duration is not None and (type(duration) not in (int, float)
                                    or not math.isfinite(duration) or duration < 0):
            raise ValueError("invalid spawn_duration_seconds")
        try:
            uuid.UUID(record["ingestion_run_id"])
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise ValueError("invalid ingestion_run_id") from exc
        snapshot = dict(record)
        time_ns = None
        if build.event_time is not None:
            snapshot["event_time"], time_ns = utc_time(build.event_time)
            build = BuildEvent.from_record(snapshot)
        return cls(build, snapshot, time_ns)
