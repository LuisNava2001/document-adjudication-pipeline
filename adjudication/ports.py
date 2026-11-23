"""Ports: the interfaces the application core depends on.

The adapters in ``adjudication.adapters`` implement these contracts for local,
offline use. A cloud-backed implementation (an OCR service, a durable audit
store, a shared fingerprint index) would implement the same contracts; none is
included in this release.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from adjudication.domain.models import AuditEvent, DocumentRef, ExtractionResult


class ExtractionError(Exception):
    """Raised by a DocumentExtractor when a document cannot be processed.

    ``retryable`` separates transient dependency failures (try again later)
    from permanent document problems (route the claim to a human).
    """

    def __init__(self, kind: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class DocumentExtractor(Protocol):
    name: str

    def extract(self, document: DocumentRef) -> ExtractionResult:
        """Return structured fields for one document or raise ExtractionError."""
        ...


class AuditSink(Protocol):
    def append(self, event: AuditEvent) -> None: ...


class FingerprintStore(Protocol):
    """Remembers which claim first submitted each receipt fingerprint."""

    def find_other_claim(self, fingerprint: str, claim_id: str) -> str | None:
        """Return the claim that registered ``fingerprint``, unless it is ``claim_id`` itself."""
        ...

    def register(self, fingerprint: str, claim_id: str) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime:
        """Return a timezone-aware UTC timestamp."""
        ...


class TraceIdFactory(Protocol):
    def new_trace_id(self) -> str: ...
