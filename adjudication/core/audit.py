"""Audit trail: an ordered, append-only record of what happened to one submission."""

from __future__ import annotations

from typing import Any

from adjudication.domain.models import AuditEvent, Stage
from adjudication.ports import AuditSink, Clock
from adjudication.serialization import to_jsonable


class AuditTrail:
    def __init__(self, trace_id: str, clock: Clock, sink: AuditSink) -> None:
        self._trace_id = trace_id
        self._clock = clock
        self._sink = sink
        self._claim_id: str | None = None
        self._events: list[AuditEvent] = []

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def bind_claim(self, claim_id: str) -> None:
        """Tag every subsequent event with the claim it belongs to."""
        self._claim_id = claim_id

    def record(self, stage: Stage, event: str, **detail: Any) -> AuditEvent:
        entry = AuditEvent(
            trace_id=self._trace_id,
            sequence=len(self._events) + 1,
            timestamp=self._clock.now().isoformat(),
            stage=stage,
            event=event,
            claim_id=self._claim_id,
            # Snapshot the detail as plain JSON values so later mutation cannot alter history.
            detail=to_jsonable(detail),
        )
        self._events.append(entry)
        self._sink.append(entry)
        return entry
