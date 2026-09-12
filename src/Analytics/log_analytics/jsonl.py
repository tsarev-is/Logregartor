"""Адаптер локального JSONL; правила не зависят от способа чтения событий."""

import json
from collections.abc import Iterator
from pathlib import Path

from .models import BuildEvent


def read_events(path: Path) -> Iterator[BuildEvent]:
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                yield BuildEvent.from_record(json.loads(line))
            except ValueError as exc:
                # Do not echo raw source records, which may contain sensitive fields.
                raise ValueError(f"{path}:{number}: {exc}") from exc
