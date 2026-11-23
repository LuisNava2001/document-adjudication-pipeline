"""Decision engine: maps rule results to APPROVED, REJECTED or MANUAL_REVIEW.

Precedence is REJECTED > MANUAL_REVIEW > APPROVED, with three guarantees:

* Only a rule that fully evaluated and failed with REJECT severity can reject.
* Missing evidence (SKIPPED) never rejects and never approves; it routes the
  claim to a human.
* Approval requires positive evidence: at least one PASS, and no FAIL or
  SKIPPED. Approval is never the fall-through of an empty result set.
"""

from __future__ import annotations

from collections.abc import Sequence

from adjudication.domain.models import Decision, DecisionOutcome, RuleOutcome, RuleResult, Severity


class DecisionEngine:
    def decide(self, results: Sequence[RuleResult]) -> Decision:
        blocking = tuple(r for r in results if r.outcome is RuleOutcome.FAIL and r.severity is Severity.REJECT)
        if blocking:
            return Decision(DecisionOutcome.REJECTED, f"Rejected by {_ids(blocking)}.", blocking)

        needs_review = tuple(r for r in results if r.outcome in (RuleOutcome.FAIL, RuleOutcome.SKIPPED))
        if needs_review:
            return Decision(DecisionOutcome.MANUAL_REVIEW, f"Needs human review: {_ids(needs_review)}.", needs_review)

        passed = sum(1 for r in results if r.outcome is RuleOutcome.PASS)
        if passed == 0:
            return Decision(DecisionOutcome.MANUAL_REVIEW, "No check produced positive evidence.", ())
        return Decision(DecisionOutcome.APPROVED, f"All {passed} applicable checks passed.", ())


def _ids(results: Sequence[RuleResult]) -> str:
    return ", ".join(sorted({r.rule_id for r in results}))
