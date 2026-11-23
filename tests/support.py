"""Shared builders and test doubles."""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from adjudication.adapters.audit_sinks import InMemoryAuditSink
from adjudication.adapters.clock import DEMO_EPOCH, FixedClock, SequentialTraceIds
from adjudication.adapters.stores import InMemoryFingerprintStore
from adjudication.core.decision import DecisionEngine
from adjudication.core.pipeline import AdjudicationPipeline
from adjudication.core.rules import Rule, default_rules
from adjudication.core.rules.base import ValidationContext
from adjudication.core.validation import ValidationEngine
from adjudication.domain.models import (
    Category,
    Claim,
    DocumentRef,
    ExtractedField,
    ExtractionFailure,
    ExtractionResult,
    LineItem,
)
from adjudication.domain.policy import Policy, load_policy

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLES_DIR = REPO_ROOT / "samples"
POLICY = load_policy()

DEFAULT_FIELDS = {
    "merchant_name": "TEST MERCHANT",
    "transaction_date": "2026-01-08",
    "currency": "USD",
    "tax": "5.00",
    "total_amount": "42.50",
}
DEFAULT_ITEMS = (("Item one", "17.50"), ("Item two", "20.00"))


def make_claim(
    *,
    claim_id: str = "CLM-T1",
    category: Category = Category.MEALS,
    claimed_amount: str = "42.50",
    currency: str = "USD",
    submitted_on: date = date(2026, 1, 12),
    document_ids: tuple[str, ...] = ("DOC-T1",),
) -> Claim:
    return Claim(
        claim_id=claim_id,
        claimant_id="CLMT-T",
        category=category,
        claimed_amount=Decimal(claimed_amount),
        currency=currency,
        submitted_on=submitted_on,
        description="test claim",
        documents=tuple(DocumentRef(doc, f"{doc}.txt", "text/plain") for doc in document_ids),
    )


def make_extraction(
    document_id: str = "DOC-T1",
    *,
    overrides: dict[str, str | None] | None = None,
    drop: tuple[str, ...] = (),
    confidence: dict[str, float] | None = None,
    items: tuple[tuple[str, str | None], ...] = DEFAULT_ITEMS,
    attempts: int = 1,
) -> ExtractionResult:
    values = {**DEFAULT_FIELDS, **(overrides or {})}
    for name in drop:
        values.pop(name, None)
    scores = confidence or {}
    return ExtractionResult(
        document_id=document_id,
        provider="test",
        page_count=1,
        fields={name: ExtractedField(value, scores.get(name, 0.97)) for name, value in values.items()},
        line_items=tuple(LineItem(description, amount, 0.95) for description, amount in items),
        source_sha256="0" * 64,
        attempts=attempts,
    )


def make_failure(document_id: str = "DOC-T1", *, kind: str = "UNREADABLE_DOCUMENT", retryable: bool = False) -> ExtractionFailure:
    return ExtractionFailure(document_id, kind, "test failure", retryable, 1)


def make_context(
    claim: Claim | None = None,
    extractions: tuple[ExtractionResult, ...] | None = None,
    failures: tuple[ExtractionFailure, ...] = (),
    prior: dict[str, str] | None = None,
    policy: Policy | None = None,
) -> ValidationContext:
    claim = claim or make_claim()
    if extractions is None:
        extractions = tuple(make_extraction(doc.document_id) for doc in claim.documents)
    return ValidationContext(
        claim=claim,
        policy=policy or POLICY,
        extractions=tuple(extractions),
        failures=tuple(failures),
        prior_submissions=dict(prior or {}),
    )


def policy_with(**changes: Any) -> Policy:
    """Default policy document with top-level keys replaced."""
    import json

    data = json.loads((REPO_ROOT / "adjudication" / "data" / "default_policy.json").read_text(encoding="utf-8"))
    data.update(changes)
    return Policy.from_dict(data)


def claim_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "claim_id": "CLM-T1",
        "claimant_id": "CLMT-T",
        "category": "MEALS",
        "claimed_amount": "42.50",
        "currency": "USD",
        "submitted_on": "2026-01-12",
        "description": "test claim",
        "documents": [{"document_id": "DOC-T1", "file": "DOC-T1.txt", "media_type": "text/plain"}],
    }
    payload.update(overrides)
    return payload


class ScriptedExtractor:
    """Test double that replays a scripted outcome per attempt; the last outcome repeats."""

    name = "scripted"

    def __init__(self, script: dict[str, list[Any]]) -> None:
        self._script = {doc: list(outcomes) for doc, outcomes in script.items()}
        self.calls: Counter[str] = Counter()

    def extract(self, document: DocumentRef) -> ExtractionResult:
        self.calls[document.document_id] += 1
        outcomes = self._script[document.document_id]
        outcome = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def build_pipeline(
    extractor: Any,
    *,
    rules: list[Rule] | None = None,
    store: InMemoryFingerprintStore | None = None,
    sink: InMemoryAuditSink | None = None,
    max_attempts: int = 3,
) -> AdjudicationPipeline:
    return AdjudicationPipeline(
        extractor=extractor,
        policy=POLICY,
        validation=ValidationEngine(rules if rules is not None else default_rules()),
        decision_engine=DecisionEngine(),
        audit_sink=sink or InMemoryAuditSink(),
        fingerprint_store=store or InMemoryFingerprintStore(),
        clock=FixedClock(DEMO_EPOCH),
        trace_ids=SequentialTraceIds(),
        max_extraction_attempts=max_attempts,
    )
