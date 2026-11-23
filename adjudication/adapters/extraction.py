"""Fixture-backed extraction adapter.

No OCR happens here. Each synthetic document has a pre-recorded extraction
result (JSON) shaped like the output of a document-analysis service: fields
with confidence scores, line items and a page count. The adapter

* checks that the recording was made for the exact document content (SHA-256),
* replays recorded provider failures, so retry and error handling can be
  exercised offline, and
* refuses document paths that escape the configured documents directory.

A real OCR adapter would implement the same ``DocumentExtractor`` port.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from adjudication.domain.models import DocumentRef, ExtractedField, ExtractionResult, LineItem
from adjudication.ports import ExtractionError

DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
NO_RECORDING = "NO_RECORDING"
INVALID_RECORDING = "INVALID_RECORDING"
STALE_RECORDING = "STALE_RECORDING"


def document_digest(data: bytes, media_type: str) -> str:
    """SHA-256 of a document. Text line endings are normalized so CRLF checkouts hash like LF."""
    if media_type.startswith("text/"):
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


class FixtureExtractor:
    name = "fixture"

    def __init__(self, documents_dir: str | Path, recordings_dir: str | Path) -> None:
        self._documents_dir = Path(documents_dir).resolve()
        self._recordings_dir = Path(recordings_dir).resolve()
        self._attempts: Counter[str] = Counter()

    def extract(self, document: DocumentRef) -> ExtractionResult:
        source = self._locate(document.file_name)
        if source is None:
            raise ExtractionError(DOCUMENT_NOT_FOUND, f"source document {document.file_name!r} not found", retryable=False)
        digest = document_digest(source.read_bytes(), document.media_type)
        recording = self._load_recording(document.document_id)
        if recording.get("source_sha256") != digest:
            raise ExtractionError(
                STALE_RECORDING, "the recorded extraction was made for different document content", retryable=False
            )
        self._attempts[document.document_id] += 1
        failure = recording.get("simulated_failure")
        if failure is not None:
            self._replay_failure(document.document_id, failure)
        return self._to_result(document, recording, digest)

    def _locate(self, file_name: str) -> Path | None:
        candidate = (self._documents_dir / file_name).resolve()
        if candidate.parent != self._documents_dir or not candidate.is_file():
            return None
        return candidate

    def _load_recording(self, document_id: str) -> dict[str, Any]:
        path = self._recordings_dir / f"{document_id}.json"
        if not path.is_file():
            raise ExtractionError(NO_RECORDING, f"no recorded extraction for {document_id}", retryable=False)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExtractionError(INVALID_RECORDING, f"recording for {document_id} is unreadable: {exc}", retryable=False) from exc
        if not isinstance(data, dict) or data.get("document_id") != document_id:
            raise ExtractionError(INVALID_RECORDING, f"recording for {document_id} has the wrong shape", retryable=False)
        return data

    def _replay_failure(self, document_id: str, failure: dict[str, Any]) -> None:
        # fail_attempts: fail this many attempts, then succeed. None means every attempt fails.
        fail_attempts = failure.get("fail_attempts")
        if fail_attempts is None or self._attempts[document_id] <= int(fail_attempts):
            raise ExtractionError(
                str(failure.get("kind", "PROVIDER_ERROR")),
                f"replayed provider failure: {failure.get('message', 'unspecified')}",
                retryable=bool(failure.get("retryable", False)),
            )

    def _to_result(self, document: DocumentRef, recording: dict[str, Any], digest: str) -> ExtractionResult:
        try:
            fields = {
                str(name): ExtractedField(_optional_text(spec.get("value")), _confidence(spec["confidence"]))
                for name, spec in recording["fields"].items()
            }
            line_items = tuple(
                LineItem(str(item["description"]), _optional_text(item.get("amount")), _confidence(item["confidence"]))
                for item in recording.get("line_items", [])
            )
            page_count = int(recording.get("page_count", 1))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ExtractionError(
                INVALID_RECORDING, f"recording for {document.document_id} is malformed: {exc}", retryable=False
            ) from exc
        return ExtractionResult(
            document_id=document.document_id,
            provider=self.name,
            page_count=page_count,
            fields=fields,
            line_items=line_items,
            source_sha256=digest,
        )


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _confidence(value: Any) -> float:
    score = float(value)
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"confidence {score} is outside [0, 1]")
    return score
