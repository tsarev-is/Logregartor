"""Явная конфигурация первого правила; порог не подбирается на входных данных."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DetectorConfig:
    dataset_id: str
    threshold_seconds: float

    def __post_init__(self):
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("dataset_id must be a nonempty string")
        if (
            type(self.threshold_seconds) not in (int, float)
            or not math.isfinite(self.threshold_seconds)
            or self.threshold_seconds <= 0
        ):
            raise ValueError("threshold_seconds must be finite and positive")
