"""Policy loading and the small local adapters (clock, ids, sinks, store, serialization)."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from adjudication.adapters.audit_sinks import JsonlAuditSink
from adjudication.adapters.clock import FixedClock, SequentialTraceIds
from adjudication.adapters.stores import InMemoryFingerprintStore
from adjudication.domain.models import AuditEvent, Category, DecisionOutcome, Stage
from adjudication.domain.policy import PolicyError, load_policy
from adjudication.serialization import to_jsonable
from support import POLICY, policy_with


class PolicyTest(unittest.TestCase):
    def test_bundled_policy_loads(self):
        self.assertEqual(POLICY.version, "demo-2026.1")
        self.assertEqual(len(POLICY.digest), 64)
        self.assertEqual(POLICY.category_limit(Category.LODGING, "USD"), Decimal("300.00"))
        self.assertIsNone(POLICY.category_limit(Category.LODGING, "JPY"))

    def test_digest_changes_with_content(self):
        self.assertNotEqual(policy_with(submission_window_days=30).digest, POLICY.digest)

    def test_rejects_out_of_range_values(self):
        for changes, fragment in (
            ({"min_field_confidence": 1.5}, "min_field_confidence"),
            ({"amount_tolerance": 0.01}, "amount_tolerance"),
            ({"submission_window_days": 0}, "submission_window_days"),
            ({"allowed_currencies": ["usd"]}, "allowed_currencies"),
            ({"category_limits": {"PETS": {"USD": "1.00"}}}, "unknown category"),
            ({"category_limits": {"MEALS": {"JPY": "1.00"}}}, "not in allowed_currencies"),
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(PolicyError) as caught:
                    policy_with(**changes)
                self.assertIn(fragment, str(caught.exception))

    def test_unreadable_or_invalid_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PolicyError):
                load_policy(Path(tmp) / "missing.json")
            broken = Path(tmp) / "broken.json"
            broken.write_text("{", encoding="utf-8")
            with self.assertRaises(PolicyError):
                load_policy(broken)


class AdapterTest(unittest.TestCase):
    def test_fixed_clock_requires_timezone(self):
        with self.assertRaises(ValueError):
            FixedClock(datetime(2026, 1, 1))

    def test_sequential_trace_ids(self):
        ids = SequentialTraceIds()
        self.assertEqual([ids.new_trace_id(), ids.new_trace_id()], ["trc-000001", "trc-000002"])

    def test_fingerprint_store_ignores_own_claim_and_keeps_first_owner(self):
        store = InMemoryFingerprintStore()
        store.register("fp", "CLM-1")
        store.register("fp", "CLM-2")
        self.assertIsNone(store.find_other_claim("fp", "CLM-1"))
        self.assertEqual(store.find_other_claim("fp", "CLM-3"), "CLM-1")

    def test_jsonl_sink_appends_and_truncates(self):
        event = AuditEvent("trc-1", 1, "2026-03-01T00:00:00+00:00", Stage.PIPELINE, "COMPLETED", "CLM-1", {})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "audit.jsonl"
            sink = JsonlAuditSink(path)
            sink.append(event)
            sink.append(event)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 2)
            JsonlAuditSink(path, truncate=True)
            self.assertEqual(path.read_text(encoding="utf-8"), "")
            sink.append(event)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["stage"], "PIPELINE")

    def test_serialization_handles_domain_types(self):
        converted = to_jsonable({Category.MEALS: [Decimal("1.50"), date(2026, 1, 2), DecisionOutcome.APPROVED, {"b", "a"}]})
        self.assertEqual(converted, {"MEALS": ["1.50", "2026-01-02", "APPROVED", ["a", "b"]]})


if __name__ == "__main__":
    unittest.main()
