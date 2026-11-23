"""Audit sinks: where audit events go once recorded."""

from __future__ import annotations

import json
from pathlib import Path

from adjudication.domain.models import AuditEvent
from adjudication.serialization import to_jsonable


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)


class JsonlAuditSink:
    """Appends one JSON object per line: easy to grep, diff or ship to a log store."""

    def __init__(self, path: str | Path, *, truncate: bool = False) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if truncate:
            self._path.write_text("", encoding="utf-8")

    @property
    def path(self) -> Path:
        return self._path

    def append(self, event: AuditEvent) -> None:
        line = json.dumps(to_jsonable(event), sort_keys=True)
        with self._path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
