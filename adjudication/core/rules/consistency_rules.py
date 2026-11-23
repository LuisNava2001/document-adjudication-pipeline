"""Rules that cross-check amounts, currencies and receipts against each other."""

from __future__ import annotations

from decimal import Decimal

from adjudication.core.fingerprint import receipt_fingerprint
from adjudication.core.parsing import format_amount, is_currency_code, parse_amount, present
from adjudication.core.rules.base import DocumentRule, Rule, ValidationContext
from adjudication.domain.models import ExtractionResult, RuleResult, Severity

ZERO = Decimal("0")


class LineItemsReconcile(DocumentRule):
    rule_id = "CON-001"
    title = "Line items plus tax add up to the document total"
    severity = Severity.REVIEW

    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult:
        doc_id = extraction.document_id
        if not extraction.line_items:
            return self.not_applicable("No line items extracted.", doc_id)
        total = parse_amount(extraction.value("total_amount"))
        amounts = [parse_amount(item.amount) for item in extraction.line_items]
        tax_raw = extraction.value("tax")
        tax = parse_amount(tax_raw) if present(tax_raw) else ZERO
        if total is None or tax is None or any(amount is None for amount in amounts):
            return self.skipped("Line items, tax or total unreadable; cannot reconcile.", doc_id)
        items_sum = sum(amounts, ZERO)
        computed = items_sum + tax
        evidence = {
            "line_items_sum": items_sum,
            "tax": tax,
            "computed_total": computed,
            "document_total": total,
            "tolerance": ctx.policy.amount_tolerance,
        }
        if abs(computed - total) > ctx.policy.amount_tolerance:
            return self.failed(
                f"Line items {format_amount(items_sum)} + tax {format_amount(tax)} = {format_amount(computed)}, "
                f"but the document total is {format_amount(total)}.",
                doc_id,
                **evidence,
            )
        return self.passed(f"Line items plus tax reconcile with total {format_amount(total)}.", doc_id, **evidence)


class CurrencyMatchesClaim(DocumentRule):
    rule_id = "CON-002"
    title = "Document currency matches the claim currency"
    severity = Severity.REVIEW

    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult:
        currency = extraction.value("currency")
        if not is_currency_code(currency):
            return self.skipped("Document currency unavailable or invalid.", extraction.document_id)
        currency = currency.strip()
        evidence = {"document_currency": currency, "claim_currency": ctx.claim.currency}
        if currency != ctx.claim.currency:
            return self.failed(
                f"Document currency {currency} differs from claim currency {ctx.claim.currency}; "
                "currency conversion is not supported.",
                extraction.document_id,
                **evidence,
            )
        return self.passed(f"Document currency {currency} matches the claim.", extraction.document_id, **evidence)


class ClaimedWithinDocumented(Rule):
    rule_id = "CON-003"
    title = "Claimed amount does not exceed the documented total"
    severity = Severity.REJECT

    def evaluate(self, ctx: ValidationContext) -> list[RuleResult]:
        claim = ctx.claim
        if not claim.documents:
            return [self.not_applicable("No documents attached.")]
        if ctx.failures:
            unextracted = [failure.document_id for failure in ctx.failures]
            return [
                self.skipped(
                    f"Documented total unknown: {len(unextracted)} document(s) could not be extracted.",
                    unextracted=unextracted,
                )
            ]
        totals: dict[str, Decimal] = {}
        for extraction in ctx.extractions:
            total = parse_amount(extraction.value("total_amount"))
            currency = extraction.value("currency")
            if total is None:
                return [self.skipped(f"Documented total unknown: total unreadable on {extraction.document_id}.")]
            if currency is None or currency.strip() != claim.currency:
                return [
                    self.skipped(
                        f"Documented total unknown: {extraction.document_id} is not in the claim currency {claim.currency}."
                    )
                ]
            totals[extraction.document_id] = total
        documented = sum(totals.values(), ZERO)
        claimed = claim.claimed_amount
        evidence = {
            "claimed_amount": claimed,
            "documented_total": documented,
            "currency": claim.currency,
            "tolerance": ctx.policy.amount_tolerance,
            "document_totals": totals,
        }
        if claimed > documented + ctx.policy.amount_tolerance:
            return [
                self.failed(
                    f"Claimed {format_amount(claimed)} {claim.currency} exceeds the documented total "
                    f"{format_amount(documented)} {claim.currency}.",
                    **evidence,
                )
            ]
        return [
            self.passed(
                f"Claimed {format_amount(claimed)} {claim.currency} is covered by the documented total "
                f"{format_amount(documented)} {claim.currency}.",
                **evidence,
            )
        ]


class DuplicateReceiptsInClaim(Rule):
    rule_id = "DUP-001"
    title = "The same receipt is not attached twice"
    severity = Severity.REJECT

    def evaluate(self, ctx: ValidationContext) -> list[RuleResult]:
        if len(ctx.extractions) < 2:
            return [self.not_applicable("Fewer than two extracted documents.")]
        groups: dict[str, list[str]] = {}
        unfingerprinted = []
        for extraction in ctx.extractions:
            fingerprint = receipt_fingerprint(extraction)
            if fingerprint is None:
                unfingerprinted.append(extraction.document_id)
            else:
                groups.setdefault(fingerprint, []).append(extraction.document_id)
        duplicates = [
            self.failed(
                f"Documents {', '.join(ids)} are the same receipt (same merchant, date, total and currency).",
                fingerprint=fingerprint,
                document_ids=ids,
            )
            for fingerprint, ids in groups.items()
            if len(ids) > 1
        ]
        if duplicates:
            return duplicates
        if unfingerprinted:
            return [
                self.skipped(
                    f"{len(unfingerprinted)} document(s) lack the fields needed for duplicate detection.",
                    documents=unfingerprinted,
                )
            ]
        return [self.passed(f"No duplicates among {len(ctx.extractions)} receipts.")]


class NotPreviouslySubmitted(DocumentRule):
    rule_id = "DUP-002"
    title = "The receipt was not submitted in an earlier claim"
    severity = Severity.REVIEW

    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult:
        fingerprint = receipt_fingerprint(extraction)
        if fingerprint is None:
            return self.skipped("Receipt lacks the fields needed for duplicate detection.", extraction.document_id)
        earlier = ctx.prior_submissions.get(extraction.document_id)
        if earlier:
            return self.failed(
                f"Receipt matches one already submitted in claim {earlier}.",
                extraction.document_id,
                fingerprint=fingerprint,
                earlier_claim_id=earlier,
            )
        return self.passed("Receipt not seen in earlier claims.", extraction.document_id, fingerprint=fingerprint)
