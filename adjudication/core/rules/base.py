"""Rule contract and shared helpers.

A rule returns one RuleResult per scope it judges: the claim, or each extracted
document. Rules are pure functions of the ValidationContext. They never call
services or read stores, which keeps them unit-testable and makes every
decision reproducible from its recorded inputs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from adjudication.domain.models import Claim, ExtractionFailure, ExtractionResult, RuleOutcome, RuleResult, Severity
from adjudication.domain.policy import Policy


@dataclass(frozen=True)
class ValidationContext:
    claim: Claim
    policy: Policy
    extractions: tuple[ExtractionResult, ...]
    failures: tuple[ExtractionFailure, ...] = ()
    # document_id -> id of an earlier claim that submitted the same receipt
    prior_submissions: dict[str, str] = field(default_factory=dict)


class Rule(ABC):
    rule_id: ClassVar[str]
    title: ClassVar[str]
    severity: ClassVar[Severity]

    @abstractmethod
    def evaluate(self, ctx: ValidationContext) -> list[RuleResult]: ...

    def passed(self, message: str, document_id: str | None = None, **evidence: Any) -> RuleResult:
        return self._result(RuleOutcome.PASS, message, document_id, evidence)

    def failed(self, message: str, document_id: str | None = None, **evidence: Any) -> RuleResult:
        return self._result(RuleOutcome.FAIL, message, document_id, evidence)

    def skipped(self, message: str, document_id: str | None = None, **evidence: Any) -> RuleResult:
        return self._result(RuleOutcome.SKIPPED, message, document_id, evidence)

    def not_applicable(self, message: str, document_id: str | None = None, **evidence: Any) -> RuleResult:
        return self._result(RuleOutcome.NOT_APPLICABLE, message, document_id, evidence)

    def _result(self, outcome: RuleOutcome, message: str, document_id: str | None, evidence: dict[str, Any]) -> RuleResult:
        return RuleResult(
            rule_id=self.rule_id,
            outcome=outcome,
            severity=self.severity,
            message=message,
            document_id=document_id,
            evidence=evidence,
        )


class DocumentRule(Rule):
    """A rule judged once for every successfully extracted document."""

    def evaluate(self, ctx: ValidationContext) -> list[RuleResult]:
        return [self.check(ctx, extraction) for extraction in ctx.extractions]

    @abstractmethod
    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult: ...
