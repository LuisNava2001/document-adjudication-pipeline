"""Domain model shared by every pipeline stage.

Value objects are immutable. Amounts on a Claim are Decimal. Values recovered
from documents stay as extracted text until a rule parses them, so a malformed
value is reported as a finding instead of being silently coerced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Category(StrEnum):
    """Expense categories of the fictional reimbursement domain."""

    MEALS = "MEALS"
    TRAVEL = "TRAVEL"
    LODGING = "LODGING"
    OFFICE_SUPPLIES = "OFFICE_SUPPLIES"
    TRAINING = "TRAINING"


class RuleOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    # The rule applies, but the evidence it needs is unavailable.
    SKIPPED = "SKIPPED"
    # The rule does not apply to this claim or document.
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Severity(StrEnum):
    # A failure is sufficient grounds to reject the claim.
    REJECT = "REJECT"
    # A failure requires a human decision.
    REVIEW = "REVIEW"


class DecisionOutcome(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ProcessingStatus(StrEnum):
    # A decision was produced.
    COMPLETED = "COMPLETED"
    # A retryable dependency failed; no decision, the claim can be resubmitted.
    FAILED = "FAILED"
    # The submission could not be parsed into a claim.
    INVALID_INPUT = "INVALID_INPUT"


class Stage(StrEnum):
    INGESTION = "INGESTION"
    EXTRACTION = "EXTRACTION"
    VALIDATION = "VALIDATION"
    DECISION = "DECISION"
    PIPELINE = "PIPELINE"


@dataclass(frozen=True)
class DocumentRef:
    document_id: str
    file_name: str
    media_type: str


@dataclass(frozen=True)
class Claim:
    claim_id: str
    claimant_id: str
    category: Category
    claimed_amount: Decimal
    currency: str
    submitted_on: date
    description: str
    documents: tuple[DocumentRef, ...]


@dataclass(frozen=True)
class ExtractedField:
    value: str | None
    confidence: float


@dataclass(frozen=True)
class LineItem:
    description: str
    amount: str | None
    confidence: float


@dataclass(frozen=True)
class ExtractionResult:
    """Fields recovered from one document, as text, with per-field confidence."""

    document_id: str
    provider: str
    page_count: int
    fields: dict[str, ExtractedField]
    line_items: tuple[LineItem, ...]
    source_sha256: str
    attempts: int = 1

    def value(self, name: str) -> str | None:
        extracted = self.fields.get(name)
        return extracted.value if extracted else None


@dataclass(frozen=True)
class ExtractionFailure:
    document_id: str
    kind: str
    message: str
    retryable: bool
    attempts: int


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    outcome: RuleOutcome
    severity: Severity
    message: str
    document_id: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    outcome: DecisionOutcome
    summary: str
    reasons: tuple[RuleResult, ...]


@dataclass(frozen=True)
class AuditEvent:
    trace_id: str
    sequence: int
    timestamp: str
    stage: Stage
    event: str
    claim_id: str | None
    detail: dict[str, Any]


@dataclass(frozen=True)
class ProcessingResult:
    trace_id: str
    source: str
    input_digest: str
    status: ProcessingStatus
    claim_id: str | None
    decision: Decision | None
    rule_results: tuple[RuleResult, ...]
    extractions: tuple[ExtractionResult, ...]
    extraction_failures: tuple[ExtractionFailure, ...]
    audit_trail: tuple[AuditEvent, ...]
    errors: tuple[str, ...]
    policy_version: str
    policy_digest: str
    schema_version: str = "1.0"
