"""Unit tests for every validation rule: PASS, FAIL, SKIPPED and NOT_APPLICABLE paths."""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from adjudication.core.rules import default_rules
from adjudication.core.rules.consistency_rules import (
    ClaimedWithinDocumented,
    CurrencyMatchesClaim,
    DuplicateReceiptsInClaim,
    LineItemsReconcile,
    NotPreviouslySubmitted,
)
from adjudication.core.rules.document_rules import (
    DocumentsAttached,
    ExtractionSucceeded,
    FieldConfidence,
    FieldFormats,
    PositiveTotal,
    RequiredFieldsPresent,
)
from adjudication.core.rules.policy_rules import CategoryLimit, NotFutureDated, WithinSubmissionWindow
from adjudication.domain.models import Category, RuleOutcome, Severity
from support import make_claim, make_context, make_extraction, make_failure, policy_with

PASS, FAIL, SKIPPED, NA = RuleOutcome.PASS, RuleOutcome.FAIL, RuleOutcome.SKIPPED, RuleOutcome.NOT_APPLICABLE


def outcomes(rule, ctx):
    return [result.outcome for result in rule.evaluate(ctx)]


def only(rule, ctx):
    results = rule.evaluate(ctx)
    assert len(results) == 1, results
    return results[0]


class DocumentsAttachedTest(unittest.TestCase):
    def test_passes_with_documents(self):
        self.assertEqual(outcomes(DocumentsAttached(), make_context()), [PASS])

    def test_rejects_claim_without_documents(self):
        result = only(DocumentsAttached(), make_context(make_claim(document_ids=())))
        self.assertEqual((result.outcome, result.severity), (FAIL, Severity.REJECT))


class ExtractionSucceededTest(unittest.TestCase):
    def test_passes_for_extracted_document(self):
        self.assertEqual(outcomes(ExtractionSucceeded(), make_context()), [PASS])

    def test_fails_for_failed_document_with_kind_as_evidence(self):
        ctx = make_context(extractions=(), failures=(make_failure(),))
        result = only(ExtractionSucceeded(), ctx)
        self.assertEqual(result.outcome, FAIL)
        self.assertEqual(result.evidence["kind"], "UNREADABLE_DOCUMENT")

    def test_not_applicable_without_documents(self):
        self.assertEqual(outcomes(ExtractionSucceeded(), make_context(make_claim(document_ids=()))), [NA])

    def test_results_follow_document_order(self):
        claim = make_claim(document_ids=("DOC-B", "DOC-A"))
        ctx = make_context(claim, extractions=(make_extraction("DOC-A"),), failures=(make_failure("DOC-B"),))
        self.assertEqual([r.document_id for r in ExtractionSucceeded().evaluate(ctx)], ["DOC-B", "DOC-A"])


class RequiredFieldsPresentTest(unittest.TestCase):
    def test_passes_when_all_present(self):
        self.assertEqual(outcomes(RequiredFieldsPresent(), make_context()), [PASS])

    def test_fails_on_missing_and_blank_fields(self):
        extraction = make_extraction(drop=("total_amount",), overrides={"merchant_name": "   "})
        result = only(RequiredFieldsPresent(), make_context(extractions=(extraction,)))
        self.assertEqual(result.outcome, FAIL)
        self.assertEqual(result.evidence["missing"], ["merchant_name", "total_amount"])


class FieldConfidenceTest(unittest.TestCase):
    def test_passes_above_threshold(self):
        self.assertEqual(outcomes(FieldConfidence(), make_context()), [PASS])

    def test_fails_below_threshold(self):
        extraction = make_extraction(confidence={"total_amount": 0.61})
        result = only(FieldConfidence(), make_context(extractions=(extraction,)))
        self.assertEqual(result.outcome, FAIL)
        self.assertEqual(result.evidence["low_confidence"], {"total_amount": 0.61})

    def test_threshold_is_inclusive(self):
        extraction = make_extraction(confidence={"total_amount": 0.85})
        self.assertEqual(outcomes(FieldConfidence(), make_context(extractions=(extraction,))), [PASS])

    def test_skipped_when_no_required_field_present(self):
        extraction = make_extraction(drop=("merchant_name", "transaction_date", "currency", "total_amount"))
        self.assertEqual(outcomes(FieldConfidence(), make_context(extractions=(extraction,))), [SKIPPED])


class FieldFormatsTest(unittest.TestCase):
    def test_passes_well_formed_values(self):
        self.assertEqual(outcomes(FieldFormats(), make_context()), [PASS])

    def test_fails_ambiguous_date(self):
        extraction = make_extraction(overrides={"transaction_date": "08/01/2026"})
        result = only(FieldFormats(), make_context(extractions=(extraction,)))
        self.assertEqual(result.evidence["invalid"], {"transaction_date": "08/01/2026"})

    def test_fails_misread_amount_and_unsupported_currency(self):
        extraction = make_extraction(overrides={"total_amount": "4O.50", "currency": "JPY"})
        result = only(FieldFormats(), make_context(extractions=(extraction,)))
        self.assertEqual(set(result.evidence["invalid"]), {"total_amount", "currency"})

    def test_fails_unreadable_line_item_amount(self):
        extraction = make_extraction(items=(("Item", "12,00"),))
        result = only(FieldFormats(), make_context(extractions=(extraction,)))
        self.assertIn("line_items[0].amount", result.evidence["invalid"])

    def test_skipped_when_nothing_to_check(self):
        extraction = make_extraction(drop=("transaction_date", "total_amount", "tax", "currency"), items=())
        self.assertEqual(outcomes(FieldFormats(), make_context(extractions=(extraction,))), [SKIPPED])


class PositiveTotalTest(unittest.TestCase):
    def test_passes_positive_total(self):
        self.assertEqual(outcomes(PositiveTotal(), make_context()), [PASS])

    def test_rejects_zero_total(self):
        extraction = make_extraction(overrides={"total_amount": "0.00"})
        result = only(PositiveTotal(), make_context(extractions=(extraction,)))
        self.assertEqual((result.outcome, result.severity), (FAIL, Severity.REJECT))

    def test_skipped_when_unreadable(self):
        extraction = make_extraction(overrides={"total_amount": "n/a"})
        self.assertEqual(outcomes(PositiveTotal(), make_context(extractions=(extraction,))), [SKIPPED])


class LineItemsReconcileTest(unittest.TestCase):
    def test_passes_when_items_plus_tax_equal_total(self):
        self.assertEqual(outcomes(LineItemsReconcile(), make_context()), [PASS])

    def test_fails_on_mismatch(self):
        extraction = make_extraction(overrides={"total_amount": "43.50"})
        result = only(LineItemsReconcile(), make_context(extractions=(extraction,)))
        self.assertEqual(result.outcome, FAIL)
        self.assertEqual(result.evidence["computed_total"], Decimal("42.50"))

    def test_missing_tax_counts_as_zero(self):
        extraction = make_extraction(drop=("tax",), overrides={"total_amount": "37.50"})
        self.assertEqual(outcomes(LineItemsReconcile(), make_context(extractions=(extraction,))), [PASS])

    def test_not_applicable_without_line_items(self):
        extraction = make_extraction(items=())
        self.assertEqual(outcomes(LineItemsReconcile(), make_context(extractions=(extraction,))), [NA])

    def test_skipped_when_an_item_is_unreadable(self):
        extraction = make_extraction(items=(("Item", None), ("Other", "20.00")))
        self.assertEqual(outcomes(LineItemsReconcile(), make_context(extractions=(extraction,))), [SKIPPED])


class CurrencyMatchesClaimTest(unittest.TestCase):
    def test_passes_matching_currency(self):
        self.assertEqual(outcomes(CurrencyMatchesClaim(), make_context()), [PASS])

    def test_fails_on_different_currency(self):
        extraction = make_extraction(overrides={"currency": "EUR"})
        result = only(CurrencyMatchesClaim(), make_context(extractions=(extraction,)))
        self.assertEqual(result.outcome, FAIL)
        self.assertEqual(result.evidence, {"document_currency": "EUR", "claim_currency": "USD"})

    def test_skipped_when_currency_missing(self):
        extraction = make_extraction(drop=("currency",))
        self.assertEqual(outcomes(CurrencyMatchesClaim(), make_context(extractions=(extraction,))), [SKIPPED])


class ClaimedWithinDocumentedTest(unittest.TestCase):
    def test_passes_when_claimed_equals_documented(self):
        self.assertEqual(outcomes(ClaimedWithinDocumented(), make_context()), [PASS])

    def test_passes_when_claimed_is_lower(self):
        ctx = make_context(make_claim(claimed_amount="30.00"))
        self.assertEqual(outcomes(ClaimedWithinDocumented(), ctx), [PASS])

    def test_tolerance_absorbs_rounding(self):
        ctx = make_context(make_claim(claimed_amount="42.51"))
        self.assertEqual(outcomes(ClaimedWithinDocumented(), ctx), [PASS])

    def test_rejects_when_claimed_exceeds_documented(self):
        result = only(ClaimedWithinDocumented(), make_context(make_claim(claimed_amount="50.00")))
        self.assertEqual((result.outcome, result.severity), (FAIL, Severity.REJECT))
        self.assertEqual(result.evidence["documented_total"], Decimal("42.50"))

    def test_sums_several_documents(self):
        claim = make_claim(claimed_amount="85.00", document_ids=("DOC-A", "DOC-B"))
        ctx = make_context(claim, extractions=(make_extraction("DOC-A"), make_extraction("DOC-B")))
        self.assertEqual(outcomes(ClaimedWithinDocumented(), ctx), [PASS])

    def test_skipped_not_rejected_when_a_document_failed(self):
        claim = make_claim(claimed_amount="999.00", document_ids=("DOC-A", "DOC-B"))
        ctx = make_context(claim, extractions=(make_extraction("DOC-A"),), failures=(make_failure("DOC-B"),))
        self.assertEqual(outcomes(ClaimedWithinDocumented(), ctx), [SKIPPED])

    def test_skipped_on_currency_mismatch(self):
        extraction = make_extraction(overrides={"currency": "EUR"})
        self.assertEqual(outcomes(ClaimedWithinDocumented(), make_context(extractions=(extraction,))), [SKIPPED])

    def test_not_applicable_without_documents(self):
        ctx = make_context(make_claim(document_ids=()))
        self.assertEqual(outcomes(ClaimedWithinDocumented(), ctx), [NA])


class WithinSubmissionWindowTest(unittest.TestCase):
    def ctx_for(self, transaction_date: str):
        return make_context(extractions=(make_extraction(overrides={"transaction_date": transaction_date}),))

    def test_passes_recent_receipt(self):
        self.assertEqual(outcomes(WithinSubmissionWindow(), self.ctx_for("2026-01-08")), [PASS])

    def test_window_boundary(self):
        # Submitted 2026-01-12; the window is 60 days.
        self.assertEqual(outcomes(WithinSubmissionWindow(), self.ctx_for("2025-11-13")), [PASS])
        self.assertEqual(outcomes(WithinSubmissionWindow(), self.ctx_for("2025-11-12")), [FAIL])

    def test_rejects_old_receipt(self):
        result = only(WithinSubmissionWindow(), self.ctx_for("2025-10-02"))
        self.assertEqual((result.outcome, result.severity), (FAIL, Severity.REJECT))
        self.assertEqual(result.evidence["age_days"], 102)

    def test_future_date_is_left_to_pol_002(self):
        self.assertEqual(outcomes(WithinSubmissionWindow(), self.ctx_for("2026-02-01")), [NA])

    def test_skipped_on_invalid_date(self):
        self.assertEqual(outcomes(WithinSubmissionWindow(), self.ctx_for("Jan 8")), [SKIPPED])


class NotFutureDatedTest(unittest.TestCase):
    def test_passes_past_date(self):
        self.assertEqual(outcomes(NotFutureDated(), make_context()), [PASS])

    def test_fails_future_date(self):
        extraction = make_extraction(overrides={"transaction_date": "2026-01-13"})
        self.assertEqual(outcomes(NotFutureDated(), make_context(extractions=(extraction,))), [FAIL])

    def test_skipped_on_missing_date(self):
        extraction = make_extraction(drop=("transaction_date",))
        self.assertEqual(outcomes(NotFutureDated(), make_context(extractions=(extraction,))), [SKIPPED])


class CategoryLimitTest(unittest.TestCase):
    def test_passes_within_limit(self):
        self.assertEqual(outcomes(CategoryLimit(), make_context()), [PASS])

    def test_fails_above_limit(self):
        ctx = make_context(make_claim(category=Category.LODGING, claimed_amount="480.00"))
        result = only(CategoryLimit(), ctx)
        self.assertEqual((result.outcome, result.severity), (FAIL, Severity.REVIEW))
        self.assertEqual(result.evidence["limit"], Decimal("300.00"))

    def test_skipped_when_no_limit_configured(self):
        policy = policy_with(category_limits={"MEALS": {"USD": "75.00"}})
        ctx = make_context(make_claim(currency="CAD"), policy=policy)
        self.assertEqual(outcomes(CategoryLimit(), ctx), [SKIPPED])


class DuplicateReceiptsInClaimTest(unittest.TestCase):
    def test_not_applicable_with_one_document(self):
        self.assertEqual(outcomes(DuplicateReceiptsInClaim(), make_context()), [NA])

    def test_passes_distinct_receipts(self):
        claim = make_claim(document_ids=("DOC-A", "DOC-B"))
        extractions = (make_extraction("DOC-A"), make_extraction("DOC-B", overrides={"total_amount": "10.00"}))
        self.assertEqual(outcomes(DuplicateReceiptsInClaim(), make_context(claim, extractions)), [PASS])

    def test_rejects_same_receipt_despite_formatting_differences(self):
        claim = make_claim(document_ids=("DOC-A", "DOC-B"))
        extractions = (
            make_extraction("DOC-A", overrides={"merchant_name": "Blue Fern Bistro"}),
            make_extraction("DOC-B", overrides={"merchant_name": "BLUE  FERN BISTRO."}),
        )
        result = only(DuplicateReceiptsInClaim(), make_context(claim, extractions))
        self.assertEqual((result.outcome, result.severity), (FAIL, Severity.REJECT))
        self.assertEqual(result.evidence["document_ids"], ["DOC-A", "DOC-B"])

    def test_skipped_when_a_receipt_cannot_be_fingerprinted(self):
        claim = make_claim(document_ids=("DOC-A", "DOC-B"))
        extractions = (make_extraction("DOC-A"), make_extraction("DOC-B", drop=("merchant_name",)))
        self.assertEqual(outcomes(DuplicateReceiptsInClaim(), make_context(claim, extractions)), [SKIPPED])


class NotPreviouslySubmittedTest(unittest.TestCase):
    def test_passes_new_receipt(self):
        self.assertEqual(outcomes(NotPreviouslySubmitted(), make_context()), [PASS])

    def test_fails_when_seen_in_earlier_claim(self):
        result = only(NotPreviouslySubmitted(), make_context(prior={"DOC-T1": "CLM-0001"}))
        self.assertEqual(result.outcome, FAIL)
        self.assertEqual(result.evidence["earlier_claim_id"], "CLM-0001")

    def test_skipped_without_fingerprint_fields(self):
        extraction = make_extraction(drop=("total_amount",))
        self.assertEqual(outcomes(NotPreviouslySubmitted(), make_context(extractions=(extraction,))), [SKIPPED])


class DefaultRuleSetTest(unittest.TestCase):
    def test_fourteen_rules_with_unique_ids_titles_and_severities(self):
        rules = default_rules()
        self.assertEqual(len(rules), 14)
        self.assertEqual(len({rule.rule_id for rule in rules}), 14)
        for rule in rules:
            self.assertTrue(rule.title)
            self.assertIsInstance(rule.severity, Severity)

    def test_happy_context_has_no_fail_or_skip(self):
        ctx = make_context(make_claim(submitted_on=date(2026, 1, 12)))
        for rule in default_rules():
            for result in rule.evaluate(ctx):
                self.assertIn(result.outcome, (PASS, NA), f"{rule.rule_id}: {result.message}")


if __name__ == "__main__":
    unittest.main()
