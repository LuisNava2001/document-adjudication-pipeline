"""Rules about the presence and quality of extracted document data."""

from __future__ import annotations

from adjudication.core.parsing import format_amount, is_currency_code, parse_amount, parse_iso_date, present
from adjudication.core.rules.base import DocumentRule, Rule, ValidationContext
from adjudication.domain.models import ExtractionResult, RuleResult, Severity


class DocumentsAttached(Rule):
    rule_id = "DOC-001"
    title = "At least one supporting document is attached"
    severity = Severity.REJECT

    def evaluate(self, ctx: ValidationContext) -> list[RuleResult]:
        count = len(ctx.claim.documents)
        if count == 0:
            return [self.failed("Claim has no supporting documents.", document_count=0)]
        return [self.passed(f"{count} supporting document(s) attached.", document_count=count)]


class ExtractionSucceeded(Rule):
    rule_id = "EXT-001"
    title = "Every attached document was extracted"
    severity = Severity.REVIEW

    def evaluate(self, ctx: ValidationContext) -> list[RuleResult]:
        if not ctx.claim.documents:
            return [self.not_applicable("No documents attached.")]
        extracted = {e.document_id: e for e in ctx.extractions}
        failed = {f.document_id: f for f in ctx.failures}
        results = []
        for document in ctx.claim.documents:
            doc_id = document.document_id
            if doc_id in extracted:
                attempts = extracted[doc_id].attempts
                results.append(self.passed(f"Extracted on attempt {attempts}.", doc_id, attempts=attempts))
            elif doc_id in failed:
                failure = failed[doc_id]
                results.append(
                    self.failed(
                        f"Extraction failed ({failure.kind}): {failure.message}",
                        doc_id,
                        kind=failure.kind,
                        retryable=failure.retryable,
                        attempts=failure.attempts,
                    )
                )
            else:
                results.append(self.skipped("No extraction outcome was recorded.", doc_id))
        return results


class RequiredFieldsPresent(DocumentRule):
    rule_id = "EXT-002"
    title = "Required fields were extracted"
    severity = Severity.REVIEW

    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult:
        required = ctx.policy.required_fields
        missing = [name for name in required if not present(extraction.value(name))]
        if missing:
            return self.failed(f"Missing required field(s): {', '.join(missing)}.", extraction.document_id, missing=missing)
        return self.passed("All required fields present.", extraction.document_id, required=list(required))


class FieldConfidence(DocumentRule):
    rule_id = "EXT-003"
    title = "Required fields meet the confidence threshold"
    severity = Severity.REVIEW

    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult:
        threshold = ctx.policy.min_field_confidence
        assessed = {
            name: extraction.fields[name].confidence
            for name in ctx.policy.required_fields
            if name in extraction.fields and present(extraction.fields[name].value)
        }
        if not assessed:
            return self.skipped("No required field available to assess.", extraction.document_id)
        low = {name: score for name, score in assessed.items() if score < threshold}
        if low:
            listing = ", ".join(f"{name}={score:.2f}" for name, score in low.items())
            return self.failed(
                f"Confidence below {threshold:.2f}: {listing}.",
                extraction.document_id,
                threshold=threshold,
                low_confidence=low,
            )
        return self.passed(
            f"{len(assessed)} required field(s) at or above {threshold:.2f}.",
            extraction.document_id,
            threshold=threshold,
        )


class FieldFormats(DocumentRule):
    rule_id = "FMT-001"
    title = "Dates, amounts and currency codes are well formed"
    severity = Severity.REVIEW

    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult:
        invalid: dict[str, str] = {}
        checked = 0
        for name, parser in (("transaction_date", parse_iso_date), ("total_amount", parse_amount), ("tax", parse_amount)):
            raw = extraction.value(name)
            if present(raw):
                checked += 1
                if parser(raw) is None:
                    invalid[name] = raw
        currency = extraction.value("currency")
        if present(currency):
            checked += 1
            if not is_currency_code(currency) or currency.strip() not in ctx.policy.allowed_currencies:
                invalid["currency"] = currency
        for index, item in enumerate(extraction.line_items):
            if present(item.amount):
                checked += 1
                if parse_amount(item.amount) is None:
                    invalid[f"line_items[{index}].amount"] = item.amount
        if checked == 0:
            return self.skipped("No formatted field available to check.", extraction.document_id)
        if invalid:
            listing = ", ".join(f"{name}={raw!r}" for name, raw in invalid.items())
            return self.failed(
                f"Malformed or unsupported value(s): {listing}.",
                extraction.document_id,
                invalid=invalid,
                allowed_currencies=sorted(ctx.policy.allowed_currencies),
            )
        return self.passed(f"{checked} value(s) well formed.", extraction.document_id)


class PositiveTotal(DocumentRule):
    rule_id = "AMT-001"
    title = "Document total is a positive amount"
    severity = Severity.REJECT

    def check(self, ctx: ValidationContext, extraction: ExtractionResult) -> RuleResult:
        total = parse_amount(extraction.value("total_amount"))
        if total is None:
            return self.skipped("Total amount unavailable or unreadable.", extraction.document_id)
        if total <= 0:
            return self.failed(f"Document total {format_amount(total)} is not positive.", extraction.document_id, total=total)
        return self.passed(f"Document total {format_amount(total)} is positive.", extraction.document_id, total=total)
