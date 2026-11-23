"""Ingestion: structural validation of untrusted submissions."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from adjudication.core.ingestion import IngestionError, canonical_digest, decode_payload, parse_claim
from adjudication.domain.models import Category
from support import claim_payload


class ParseClaimTest(unittest.TestCase):
    def assert_rejected(self, payload, fragment):
        with self.assertRaises(IngestionError) as caught:
            parse_claim(payload)
        self.assertTrue(any(fragment in error for error in caught.exception.errors), caught.exception.errors)
        return caught.exception

    def test_valid_payload_becomes_typed_claim(self):
        claim = parse_claim(claim_payload())
        self.assertEqual(claim.category, Category.MEALS)
        self.assertEqual(claim.claimed_amount, Decimal("42.50"))
        self.assertEqual(claim.submitted_on, date(2026, 1, 12))
        self.assertEqual(claim.documents[0].file_name, "DOC-T1.txt")

    def test_empty_document_list_is_left_to_business_rules(self):
        self.assertEqual(parse_claim(claim_payload(documents=[])).documents, ())

    def test_all_errors_are_reported_together(self):
        error = self.assert_rejected(
            claim_payload(category="SNACKS", claimed_amount="-5.00", submitted_on="15/01/2026"), "category"
        )
        self.assertEqual(len(error.errors), 3)
        self.assertEqual(error.claim_id, "CLM-T1")

    def test_amount_must_be_a_string_with_two_decimals(self):
        self.assert_rejected(claim_payload(claimed_amount=42.5), "claimed_amount")
        self.assert_rejected(claim_payload(claimed_amount="42.505"), "claimed_amount")
        self.assert_rejected(claim_payload(claimed_amount="0.00"), "claimed_amount")

    def test_currency_and_date_formats(self):
        self.assert_rejected(claim_payload(currency="usd"), "currency")
        self.assert_rejected(claim_payload(submitted_on="2026-02-30"), "submitted_on")

    def test_document_file_cannot_contain_a_path(self):
        for bad in ("../secret.txt", "nested/DOC.txt", "..\\DOC.txt", ".hidden", ""):
            with self.subTest(file=bad):
                documents = [{"document_id": "DOC-1", "file": bad, "media_type": "text/plain"}]
                self.assert_rejected(claim_payload(documents=documents), "bare file name")

    def test_duplicate_document_ids_are_rejected(self):
        doc = {"document_id": "DOC-1", "file": "a.txt", "media_type": "text/plain"}
        self.assert_rejected(claim_payload(documents=[doc, dict(doc, file="b.txt")]), "duplicated")

    def test_unsupported_media_type(self):
        documents = [{"document_id": "DOC-1", "file": "a.exe", "media_type": "application/x-msdownload"}]
        self.assert_rejected(claim_payload(documents=documents), "media_type")

    def test_unknown_fields_are_rejected(self):
        self.assert_rejected(claim_payload(priority="high"), "unknown field")

    def test_non_object_payload(self):
        self.assert_rejected(["not", "an", "object"], "JSON object")

    def test_claim_id_is_none_when_invalid(self):
        error = self.assert_rejected(claim_payload(claim_id="bad id!"), "claim_id")
        self.assertIsNone(error.claim_id)


class DecodeAndDigestTest(unittest.TestCase):
    def test_invalid_json_raises_ingestion_error(self):
        with self.assertRaises(IngestionError):
            decode_payload(b"{not json")

    def test_utf8_bom_is_accepted(self):
        self.assertEqual(decode_payload(b'\xef\xbb\xbf{"a": 1}'), {"a": 1})

    def test_digest_ignores_key_order(self):
        self.assertEqual(canonical_digest({"a": 1, "b": 2}), canonical_digest({"b": 2, "a": 1}))
        self.assertNotEqual(canonical_digest({"a": 1}), canonical_digest({"a": 2}))


if __name__ == "__main__":
    unittest.main()
