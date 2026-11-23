"""Pipeline orchestration: stage ordering, retries, failure semantics and audit trail."""

from __future__ import annotations

import hashlib
import unittest

from adjudication.adapters.audit_sinks import InMemoryAuditSink
from adjudication.adapters.stores import InMemoryFingerprintStore
from adjudication.core.rules import Rule, default_rules
from adjudication.domain.models import DecisionOutcome, ProcessingStatus, RuleOutcome, Severity, Stage
from adjudication.ports import ExtractionError
from support import POLICY, ScriptedExtractor, build_pipeline, claim_payload, make_extraction

TRANSIENT = ExtractionError("SERVICE_UNAVAILABLE", "503", retryable=True)
PERMANENT = ExtractionError("UNREADABLE_DOCUMENT", "blurred", retryable=False)


def steps(result):
    return [(event.stage, event.event) for event in result.audit_trail]


def reason_ids(result):
    return sorted({reason.rule_id for reason in result.decision.reasons})


class HappyPathTest(unittest.TestCase):
    def setUp(self):
        self.sink = InMemoryAuditSink()
        self.pipeline = build_pipeline(ScriptedExtractor({"DOC-T1": [make_extraction()]}), sink=self.sink)
        self.result = self.pipeline.process_payload(claim_payload(), source="unit")

    def test_completes_with_approval(self):
        self.assertEqual(self.result.status, ProcessingStatus.COMPLETED)
        self.assertEqual(self.result.decision.outcome, DecisionOutcome.APPROVED)
        self.assertEqual(len(self.result.rule_results), 14)

    def test_audit_trail_covers_every_stage_in_order(self):
        self.assertEqual(
            steps(self.result),
            [
                (Stage.INGESTION, "RECEIVED"),
                (Stage.INGESTION, "ACCEPTED"),
                (Stage.EXTRACTION, "SUCCEEDED"),
                (Stage.VALIDATION, "COMPLETED"),
                (Stage.DECISION, "DECIDED"),
                (Stage.PIPELINE, "COMPLETED"),
            ],
        )

    def test_audit_events_are_sequenced_and_share_one_trace(self):
        events = self.result.audit_trail
        self.assertEqual([e.sequence for e in events], list(range(1, len(events) + 1)))
        self.assertEqual({e.trace_id for e in events}, {self.result.trace_id})
        self.assertIsNone(events[0].claim_id)
        self.assertTrue(all(e.claim_id == "CLM-T1" for e in events[1:]))

    def test_decision_event_records_the_policy(self):
        decided = next(e for e in self.result.audit_trail if e.stage == Stage.DECISION)
        self.assertEqual(decided.detail["policy_version"], POLICY.version)
        self.assertEqual(decided.detail["policy_digest"], POLICY.digest)

    def test_sink_receives_exactly_the_result_trail(self):
        self.assertEqual(tuple(self.sink.events), self.result.audit_trail)


class RetryAndFailureTest(unittest.TestCase):
    def test_transient_failure_is_retried_then_approved(self):
        extractor = ScriptedExtractor({"DOC-T1": [TRANSIENT, make_extraction()]})
        result = build_pipeline(extractor).process_payload(claim_payload())
        self.assertEqual(result.decision.outcome, DecisionOutcome.APPROVED)
        self.assertEqual(extractor.calls["DOC-T1"], 2)
        self.assertEqual(result.extractions[0].attempts, 2)
        self.assertIn((Stage.EXTRACTION, "ATTEMPT_FAILED"), steps(result))

    def test_exhausted_retries_fail_processing_without_a_decision(self):
        extractor = ScriptedExtractor({"DOC-T1": [TRANSIENT]})
        result = build_pipeline(extractor, max_attempts=3).process_payload(claim_payload())
        self.assertEqual(result.status, ProcessingStatus.FAILED)
        self.assertIsNone(result.decision)
        self.assertEqual(extractor.calls["DOC-T1"], 3)
        self.assertEqual(steps(result)[-1], (Stage.PIPELINE, "FAILED"))
        self.assertTrue(result.extraction_failures[0].retryable)

    def test_permanent_failure_is_not_retried_and_goes_to_review(self):
        extractor = ScriptedExtractor({"DOC-T1": [PERMANENT]})
        result = build_pipeline(extractor).process_payload(claim_payload())
        self.assertEqual(extractor.calls["DOC-T1"], 1)
        self.assertEqual(result.status, ProcessingStatus.COMPLETED)
        self.assertEqual(result.decision.outcome, DecisionOutcome.MANUAL_REVIEW)
        self.assertEqual(reason_ids(result), ["CON-003", "EXT-001"])

    def test_result_for_another_document_is_treated_as_failure(self):
        extractor = ScriptedExtractor({"DOC-T1": [make_extraction("DOC-OTHER")]})
        result = build_pipeline(extractor).process_payload(claim_payload())
        self.assertEqual(result.extraction_failures[0].kind, "MISMATCHED_RESULT")
        self.assertEqual(result.decision.outcome, DecisionOutcome.MANUAL_REVIEW)

    def test_attempt_limit_must_be_positive(self):
        with self.assertRaises(ValueError):
            build_pipeline(ScriptedExtractor({}), max_attempts=0)


class InvalidInputTest(unittest.TestCase):
    def test_invalid_payload_is_audited_and_not_decided(self):
        result = build_pipeline(ScriptedExtractor({})).process_payload(claim_payload(category="SNACKS"))
        self.assertEqual(result.status, ProcessingStatus.INVALID_INPUT)
        self.assertIsNone(result.decision)
        self.assertEqual(result.claim_id, "CLM-T1")
        self.assertEqual(
            steps(result),
            [(Stage.INGESTION, "RECEIVED"), (Stage.INGESTION, "REJECTED"), (Stage.PIPELINE, "COMPLETED")],
        )

    def test_undecodable_bytes_are_hashed_raw(self):
        raw = b"{this is not json"
        result = build_pipeline(ScriptedExtractor({})).process_raw(raw, source="broken.json")
        self.assertEqual(result.status, ProcessingStatus.INVALID_INPUT)
        self.assertEqual(result.input_digest, hashlib.sha256(raw).hexdigest())


class DuplicateDetectionTest(unittest.TestCase):
    def test_receipt_reused_by_another_claim_needs_review(self):
        script = {"DOC-T1": [make_extraction("DOC-T1")], "DOC-T2": [make_extraction("DOC-T2")]}
        pipeline = build_pipeline(ScriptedExtractor(script), store=InMemoryFingerprintStore())
        first = pipeline.process_payload(claim_payload())
        second = pipeline.process_payload(
            claim_payload(claim_id="CLM-T2", documents=[{"document_id": "DOC-T2", "file": "DOC-T2.txt", "media_type": "text/plain"}])
        )
        self.assertEqual(first.decision.outcome, DecisionOutcome.APPROVED)
        self.assertEqual(second.decision.outcome, DecisionOutcome.MANUAL_REVIEW)
        self.assertEqual(second.decision.reasons[0].evidence["earlier_claim_id"], "CLM-T1")

    def test_reprocessing_the_same_claim_is_idempotent(self):
        pipeline = build_pipeline(ScriptedExtractor({"DOC-T1": [make_extraction()]}))
        first = pipeline.process_payload(claim_payload())
        second = pipeline.process_payload(claim_payload())
        self.assertEqual(second.decision.outcome, DecisionOutcome.APPROVED)
        self.assertEqual(first.input_digest, second.input_digest)
        self.assertNotEqual(first.trace_id, second.trace_id)

    def test_failed_processing_does_not_register_receipts(self):
        script = {"DOC-T1": [TRANSIENT], "DOC-T2": [make_extraction("DOC-T2")]}
        pipeline = build_pipeline(ScriptedExtractor(script))
        pipeline.process_payload(claim_payload())
        later = pipeline.process_payload(
            claim_payload(claim_id="CLM-T2", documents=[{"document_id": "DOC-T2", "file": "DOC-T2.txt", "media_type": "text/plain"}])
        )
        self.assertEqual(later.decision.outcome, DecisionOutcome.APPROVED)


class BrokenRule(Rule):
    rule_id = "BRK-001"
    title = "Always raises"
    severity = Severity.REJECT

    def evaluate(self, ctx):
        raise RuntimeError("boom")


class RuleErrorTest(unittest.TestCase):
    def test_a_crashing_rule_is_skipped_and_forces_review(self):
        pipeline = build_pipeline(ScriptedExtractor({"DOC-T1": [make_extraction()]}), rules=[*default_rules(), BrokenRule()])
        result = pipeline.process_payload(claim_payload())
        broken = next(r for r in result.rule_results if r.rule_id == "BRK-001")
        self.assertEqual(broken.outcome, RuleOutcome.SKIPPED)
        self.assertEqual(result.decision.outcome, DecisionOutcome.MANUAL_REVIEW)
        self.assertIn((Stage.VALIDATION, "RULE_ERROR"), steps(result))


if __name__ == "__main__":
    unittest.main()
