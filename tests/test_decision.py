"""Decision precedence and the guarantees documented in core/decision.py."""

from __future__ import annotations

import unittest

from adjudication.core.decision import DecisionEngine
from adjudication.domain.models import DecisionOutcome, RuleOutcome, RuleResult, Severity


def result(rule_id: str, outcome: RuleOutcome, severity: Severity = Severity.REVIEW) -> RuleResult:
    return RuleResult(rule_id, outcome, severity, f"{rule_id} {outcome}")


PASS = result("R-PASS", RuleOutcome.PASS)
NA = result("R-NA", RuleOutcome.NOT_APPLICABLE)
REVIEW_FAIL = result("R-REVIEW", RuleOutcome.FAIL, Severity.REVIEW)
REJECT_FAIL = result("R-REJECT", RuleOutcome.FAIL, Severity.REJECT)
REJECT_SKIPPED = result("R-REJECT-SKIP", RuleOutcome.SKIPPED, Severity.REJECT)


class DecisionEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = DecisionEngine()

    def test_all_pass_is_approved_without_reasons(self):
        decision = self.engine.decide([PASS, PASS, NA])
        self.assertEqual(decision.outcome, DecisionOutcome.APPROVED)
        self.assertEqual(decision.reasons, ())
        self.assertIn("2", decision.summary)

    def test_reject_failure_rejects_and_lists_only_blocking_reasons(self):
        decision = self.engine.decide([PASS, REVIEW_FAIL, REJECT_FAIL])
        self.assertEqual(decision.outcome, DecisionOutcome.REJECTED)
        self.assertEqual(decision.reasons, (REJECT_FAIL,))

    def test_review_failure_routes_to_human(self):
        decision = self.engine.decide([PASS, REVIEW_FAIL])
        self.assertEqual(decision.outcome, DecisionOutcome.MANUAL_REVIEW)
        self.assertEqual(decision.reasons, (REVIEW_FAIL,))

    def test_missing_evidence_never_rejects(self):
        decision = self.engine.decide([PASS, REJECT_SKIPPED])
        self.assertEqual(decision.outcome, DecisionOutcome.MANUAL_REVIEW)

    def test_missing_evidence_never_approves(self):
        decision = self.engine.decide([PASS, result("R-SKIP", RuleOutcome.SKIPPED)])
        self.assertEqual(decision.outcome, DecisionOutcome.MANUAL_REVIEW)

    def test_only_not_applicable_is_not_an_approval(self):
        self.assertEqual(self.engine.decide([NA, NA]).outcome, DecisionOutcome.MANUAL_REVIEW)

    def test_empty_results_are_not_an_approval(self):
        self.assertEqual(self.engine.decide([]).outcome, DecisionOutcome.MANUAL_REVIEW)

    def test_summary_names_rules_once_in_order(self):
        decision = self.engine.decide([result("B-2", RuleOutcome.FAIL), result("A-1", RuleOutcome.FAIL), result("B-2", RuleOutcome.FAIL)])
        self.assertEqual(decision.summary, "Needs human review: A-1, B-2.")


if __name__ == "__main__":
    unittest.main()
