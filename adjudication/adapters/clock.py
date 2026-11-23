"""Clocks and trace-id factories, real and deterministic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

# Timestamp used by --deterministic runs. It is clearly labelled as fixed in the output.
DEMO_EPOCH = datetime(2026, 3, 1, tzinfo=timezone.utc)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock needs a timezone-aware datetime")
        self._instant = instant

    def now(self) -> datetime:
        return self._instant


class RandomTraceIds:
    def new_trace_id(self) -> str:
        return f"trc-{uuid.uuid4().hex}"


class SequentialTraceIds:
    def __init__(self, prefix: str = "trc-") -> None:
        self._prefix = prefix
        self._counter = 0

    def new_trace_id(self) -> str:
        self._counter += 1
        return f"{self._prefix}{self._counter:06d}"
