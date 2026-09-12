"""An explicit reference snapshot, never inferred from source names or labels."""

import math
import re
from dataclasses import asdict, dataclass
from statistics import median

from .config import DetectorConfig
from .models import BuildEvent


@dataclass(frozen=True)
class RunConfig:
    dataset_id: str
    threshold_seconds: float | None = None
    reference_sources: tuple[str, ...] = ()
    margin_seconds: float | None = None

    def __post_init__(self):
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("dataset_id must be a nonempty string")
        if self.threshold_seconds is not None:
            DetectorConfig(self.dataset_id, self.threshold_seconds)
            if self.reference_sources or self.margin_seconds is not None:
                raise ValueError("threshold and reference/margin cannot be combined")
        else:
            if not self.reference_sources or self.margin_seconds is None:
                raise ValueError("provide threshold or reference sources with margin_seconds")
            if (type(self.margin_seconds) not in (int, float)
                    or not math.isfinite(self.margin_seconds) or self.margin_seconds < 0):
                raise ValueError("margin_seconds must be finite and nonnegative")
            for source in self.reference_sources:
                if not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{64}", source):
                    raise ValueError("reference-source must be a lowercase source_sha256")

    def identity(self):
        return {**asdict(self), "reference_sources": sorted(set(self.reference_sources)),
                "threshold_seconds": (float(self.threshold_seconds)
                                      if self.threshold_seconds is not None else None),
                "margin_seconds": (float(self.margin_seconds)
                                   if self.margin_seconds is not None else None)}


def resolve_threshold(events: list[BuildEvent], config: RunConfig, sources: set[str]):
    if config.threshold_seconds is not None:
        return float(config.threshold_seconds), None
    references = set(config.reference_sources)
    if not references <= sources:
        raise ValueError("reference source is not published in this dataset")
    observed, completed = set(), {}
    for event in events:
        if (event.dataset_id != config.dataset_id or event.source_sha256 not in references
                or event.instance_id is None):
            continue
        key = event.source_sha256, event.instance_id
        observed.add(key)
        if event.build_duration_seconds is not None:
            completed[key] = max(event.build_duration_seconds, completed.get(key, 0))
    if not completed:
        raise ValueError("reference has no completed VM builds")
    durations = list(completed.values())
    maximum = max(durations)
    threshold = maximum + config.margin_seconds
    DetectorConfig(config.dataset_id, threshold)
    baseline = {"reference_sources": sorted(references), "margin_seconds": config.margin_seconds,
                "threshold_seconds": threshold, "completed_instances": len(completed),
                "incomplete_instances": len(observed - completed.keys()),
                "median_seconds": median(durations), "max_seconds": maximum}
    return threshold, baseline
