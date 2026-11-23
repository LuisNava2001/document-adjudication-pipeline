"""Rules that apply the configurable reimbursement policy."""

from __future__ import annotations

from adjudication.core.parsing import format_amount, parse_iso_date
from adjudication.core.rules.base import DocumentRule, Rule, ValidationContext
from adjudication.domain.models import ExtractionResult, RuleResult, Severity


class WithinSubmissionWindow(DocumentRule):
    rule_id = "POL-001"
    title = "Receipt is dated within the submission window"
    severity = Severity.REJECT

    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult:
        transaction_date = parse_iso_date(extraction.value("transaction_date"))
        if transaction_date is None:
            return self.skipped("Transaction date unavailable or invalid.", extraction.document_id)
        age = (ctx.claim.submitted_on - transaction_date).days
        window = ctx.policy.submission_window_days
        evidence = {
            "transaction_date": transaction_date,
            "submitted_on": ctx.claim.submitted_on,
            "age_days": age,
            "window_days": window,
        }
        if age < 0:
            return self.not_applicable("Receipt is dated after submission (see POL-002).", extraction.document_id, **evidence)
        if age > window:
            return self.failed(
                f"Receipt dated {transaction_date} is {age} days older than the submission; the limit is {window} days.",
                extraction.document_id,
                **evidence,
            )
        return self.passed(f"Receipt is {age} day(s) old, within the {window}-day window.", extraction.document_id, **evidence)


class NotFutureDated(DocumentRule):
    rule_id = "POL-002"
    title = "Receipt is not dated after the submission"
    severity = Severity.REVIEW

    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult:
        transaction_date = parse_iso_date(extraction.value("transaction_date"))
        if transaction_date is None:
            return self.skipped("Transaction date unavailable or invalid.", extraction.document_id)
        submitted_on = ctx.claim.submitted_on
        if transaction_date > submitted_on:
            return self.failed(
                f"Receipt dated {transaction_date} is after the submission date {submitted_on}.",
                extraction.document_id,
                transaction_date=transaction_date,
                submitted_on=submitted_on,
            )
        return self.passed("Receipt is not future-dated.", extraction.document_id, transaction_date=transaction_date)


class CategoryLimit(Rule):
    rule_id = "POL-003"
    title = "Claimed amount is within the category limit"
    severity = Severity.REVIEW

    def evaluate(self, ctx: ValidationContext) -> list[RuleResult]:
        claim = ctx.claim
        limit = ctx.policy.category_limit(claim.category, claim.currency)
        if limit is None:
            return [self.skipped(f"No {claim.category} limit is configured for {claim.currency}.")]
        evidence = {
            "category": claim.category,
            "claimed_amount": claim.claimed_amount,
            "limit": limit,
            "currency": claim.currency,
        }
        if claim.claimed_amount > limit:
            return [
                self.failed(
                    f"Claimed {format_amount(claim.claimed_amount)} {claim.currency} exceeds the {claim.category} "
                    f"limit of {format_amount(limit)} {claim.currency}.",
                    **evidence,
                )
            ]
        return [
            self.passed(
                f"Claimed {format_amount(claim.claimed_amount)} {claim.currency} is within the {claim.category} "
                f"limit of {format_amount(limit)} {claim.currency}.",
                **evidence,
            )
        ]
