"""FixtureExtractor: recorded results, integrity checks and replayed provider failures."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from adjudication.adapters.extraction import (
    DOCUMENT_NOT_FOUND,
    INVALID_RECORDING,
    NO_RECORDING,
    STALE_RECORDING,
    FixtureExtractor,
    document_digest,
)
from adjudication.domain.models import DocumentRef
from adjudication.ports import ExtractionError

DOC = DocumentRef("DOC-X", "DOC-X.txt", "text/plain")
TEXT = "RECEIPT\nTOTAL USD 10.00\n"


class FixtureExtractorTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.documents = root / "documents"
        self.recordings = root / "extractions"
        self.documents.mkdir()
        self.recordings.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write_document(self, text: str = TEXT, name: str = "DOC-X.txt") -> None:
        (self.documents / name).write_bytes(text.encode("utf-8"))

    def write_recording(self, **overrides) -> None:
        recording = {
            "document_id": "DOC-X",
            "source_sha256": document_digest(TEXT.encode("utf-8"), "text/plain"),
            "page_count": 1,
            "fields": {"total_amount": {"value": "10.00", "confidence": 0.9}},
            "line_items": [{"description": "Thing", "amount": "10.00", "confidence": 0.8}],
        }
        recording.update(overrides)
        (self.recordings / "DOC-X.json").write_text(json.dumps(recording), encoding="utf-8")

    def extractor(self) -> FixtureExtractor:
        return FixtureExtractor(self.documents, self.recordings)

    def assert_error(self, extractor, kind, retryable=False):
        with self.assertRaises(ExtractionError) as caught:
            extractor.extract(DOC)
        self.assertEqual((caught.exception.kind, caught.exception.retryable), (kind, retryable))

    def test_returns_recorded_fields_and_document_digest(self):
        self.write_document()
        self.write_recording()
        result = self.extractor().extract(DOC)
        self.assertEqual(result.value("total_amount"), "10.00")
        self.assertEqual(result.fields["total_amount"].confidence, 0.9)
        self.assertEqual(result.line_items[0].amount, "10.00")
        self.assertEqual(result.source_sha256, document_digest(TEXT.encode("utf-8"), "text/plain"))
        self.assertEqual(result.provider, "fixture")

    def test_crlf_document_matches_lf_recording(self):
        self.write_document(TEXT.replace("\n", "\r\n"))
        self.write_recording()
        self.assertEqual(self.extractor().extract(DOC).value("total_amount"), "10.00")

    def test_missing_document(self):
        self.write_recording()
        self.assert_error(self.extractor(), DOCUMENT_NOT_FOUND)

    def test_missing_recording(self):
        self.write_document()
        self.assert_error(self.extractor(), NO_RECORDING)

    def test_unparseable_recording(self):
        self.write_document()
        (self.recordings / "DOC-X.json").write_text("{broken", encoding="utf-8")
        self.assert_error(self.extractor(), INVALID_RECORDING)

    def test_recording_for_other_content_is_stale(self):
        self.write_document("A DIFFERENT DOCUMENT\n")
        self.write_recording()
        self.assert_error(self.extractor(), STALE_RECORDING)

    def test_confidence_outside_unit_interval_is_invalid(self):
        self.write_document()
        self.write_recording(fields={"total_amount": {"value": "10.00", "confidence": 1.7}})
        self.assert_error(self.extractor(), INVALID_RECORDING)

    def test_transient_failure_recovers_after_configured_attempts(self):
        self.write_document()
        self.write_recording(simulated_failure={"kind": "SERVICE_UNAVAILABLE", "retryable": True, "fail_attempts": 2})
        extractor = self.extractor()
        self.assert_error(extractor, "SERVICE_UNAVAILABLE", retryable=True)
        self.assert_error(extractor, "SERVICE_UNAVAILABLE", retryable=True)
        self.assertEqual(extractor.extract(DOC).value("total_amount"), "10.00")

    def test_permanent_failure_never_recovers(self):
        self.write_document()
        self.write_recording(simulated_failure={"kind": "UNREADABLE_DOCUMENT", "retryable": False, "fail_attempts": None})
        extractor = self.extractor()
        for _ in range(3):
            self.assert_error(extractor, "UNREADABLE_DOCUMENT")

    def test_paths_outside_the_documents_directory_are_refused(self):
        outside = self.documents.parent / "outside.txt"
        outside.write_text(TEXT, encoding="utf-8")
        self.write_recording()
        with self.assertRaises(ExtractionError) as caught:
            self.extractor().extract(DocumentRef("DOC-X", "../outside.txt", "text/plain"))
        self.assertEqual(caught.exception.kind, DOCUMENT_NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
