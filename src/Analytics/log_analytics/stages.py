"""Versioned observations of a single VM episode, without causal claims."""

import re

from .events import AnalysisEvent
from .models import Incident

VERSION = "1.0.0"
STAGES = ("allocate", "image", "spawn", "build")
TEXT_RULES = {
    "allocate": (re.compile(r"^nova\.compute\.(claims|resource_tracker)$"),
                 re.compile(r"\b(Claim successful|Attempting claim:)")),
    "image": (re.compile(r"^nova\.virt\.libvirt\.(driver|imagebackend|imagecache)$"),
              re.compile(r"\b(Creating image|Preparing image|Fetching image|Downloading image)\b", re.I)),
    "spawn": (re.compile(r"^nova\.(virt\.libvirt\.driver|compute\.manager)$"),
              re.compile(r"\b(Instance spawned successfully|Instance running successfully)\b")),
}


def episode(events: list[AnalysisEvent], incident: Incident):
    vm = [event for event in events if (event.build.source_sha256, event.build.instance_id)
          == (incident.source_sha256, incident.instance_id)
          and event.build.dataset_id == incident.dataset_id]
    marker = next(event for event in vm if event.build.event_id == incident.evidence_ids[0])
    dated = sorted((event for event in vm if event.time_ns is not None), key=lambda e: e.order)
    # Undated records can only be assigned using physical source boundaries.
    previous_line = max((event.line for event in vm if event.line < marker.line
                         and event.build.build_duration_seconds is not None), default=0)
    if marker.time_ns is None:
        selected = [event for event in dated if previous_line < event.line <= marker.line]
    else:
        before = [event for event in dated if event.order <= marker.order]
        previous = max((index for index, event in enumerate(before[:-1])
                        if event.build.build_duration_seconds is not None), default=-1)
        selected = before[previous + 1:]
        undated_completions = [event.line for event in vm if event.time_ns is None
                              and event.build.build_duration_seconds is not None
                              and event.line < marker.line]
        if undated_completions:
            selected = [event for event in selected if event.line > max(undated_completions)]
    undated = sorted((event for event in vm if event.time_ns is None
                      and previous_line < event.line <= marker.line),
                     key=lambda e: (e.line, e.build.event_id))
    rows = selected + undated
    stages = []
    for name in STAGES:
        evidence = []
        measured = []
        for event in rows:
            record = event.record
            duration = record.get(f"{name}_duration_seconds") if name in {"build", "spawn"} else None
            matched = name == "build" and event.build.event_id == marker.build.event_id
            if name == "spawn" and duration is not None:
                matched = True
            if name in TEXT_RULES:
                component, message = TEXT_RULES[name]
                matched |= bool(component.search(record["component"] or "")
                                and message.search(record["message"]))
            if matched:
                evidence.append(event.build.event_id)
                if duration is not None:
                    measured.append(duration)
        stages.append({"name": name, "found": bool(evidence),
                       "duration_seconds": max(measured) if measured else None,
                       "evidence_ids": evidence})
    missing = [stage["name"] for stage in stages if not stage["found"]]
    parse_ids = [event.build.event_id for event in rows if event.record["parse_status"] != "ok"]
    completeness = {"status": "incomplete" if missing or undated or parse_ids else "complete",
                    "missing_stages": missing,
                    "undated_event_ids": [event.build.event_id for event in undated],
                    "parse_issue_event_ids": parse_ids}
    timeline = {"events": [event.record for event in selected],
                "undated_events": [event.record for event in undated], "stages": stages,
                "stage_rules_version": VERSION, "completeness": completeness}
    return stages, completeness, timeline
