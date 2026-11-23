"""Pipeline orchestration.

    raw submission -> ingestion -> extraction (bounded retries) -> validation
    -> decision -> fingerprint registration

Every step is written to the audit trail. The pipeline depends on ports only;
concrete adapters are wired in ``adjudication.bootstrap``.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from adjudication.core.audit import AuditTrail
from adjudication.core.decision import DecisionEngine
from adjudication.core.fingerprint import receipt_fingerprint
from adjudication.core.ingestion import IngestionError, canonical_digest, decode_payload, parse_claim
from adjudication.core.rules.base import ValidationContext
from adjudication.core.validation import ValidationEngine
from adjudication.domain.models import (
    Claim,
    Decision,
    DocumentRef,
    ExtractionFailure,
    ExtractionResult,
    ProcessingResult,
    ProcessingStatus,
    RuleOutcome,
    RuleResult,
    Stage,
)
from adjudication.domain.policy import Policy
from adjudication.ports import AuditSink, Clock, DocumentExtractor, ExtractionError, FingerprintStore, TraceIdFactory

MISMATCHED_RESULT = "MISMATCHED_RESULT"


class AdjudicationPipeline:
    def __init__(
        self,
        *,
        extractor: DocumentExtractor,
        policy: Policy,
        validation: ValidationEngine,
        decision_engine: DecisionEngine,
        audit_sink: AuditSink,
        fingerprint_store: FingerprintStore,
        clock: Clock,
        trace_ids: TraceIdFactory,
        max_extraction_attempts: int = 3,
    ) -> None:
        if max_extraction_attempts < 1:
            raise ValueError("max_extraction_attempts must be at least 1")
        self._extractor = extractor
        self._policy = policy
        self._validation = validation
        self._decision = decision_engine
        self._sink = audit_sink
        self._fingerprints = fingerprint_store
        self._clock = clock
        self._trace_ids = trace_ids
        self._max_attempts = max_extraction_attempts

    @property
    def policy(self) -> Policy:
        return self._policy

    def process_raw(self, raw: bytes | str, source: str) -> ProcessingResult:
        """Adjudicate a serialized submission, such as the bytes of a JSON file."""
        try:
            payload = decode_payload(raw)
        except IngestionError as exc:
            data = raw.encode("utf-8") if isinstance(raw, str) else raw
            digest = hashlib.sha256(data).hexdigest()
            return self._reject_input(self._open_trail(source, digest), source, digest, exc)
        return self.process_payload(payload, source)

    def process_payload(self, payload: Any, source: str = "<memory>") -> ProcessingResult:
        """Adjudicate an already-decoded submission (a JSON-compatible mapping)."""
        digest = canonical_digest(payload)
        trail = self._open_trail(source, digest)
        try:
            claim = parse_claim(payload)
        except IngestionError as exc:
            return self._reject_input(trail, source, digest, exc)
        trail.bind_claim(claim.claim_id)
        trail.record(
            Stage.INGESTION,
            "ACCEPTED",
            category=claim.category,
            claimed_amount=claim.claimed_amount,
            currency=claim.currency,
            document_count=len(claim.documents),
        )

        extractions, failures = self._extract_documents(claim, trail)
        unavailable = [failure for failure in failures if failure.retryable]
        if unavailable:
            error = (
                f"{len(unavailable)} document(s) still unavailable after {self._max_attempts} attempt(s); "
                "no decision was made and the claim can be resubmitted."
            )
            trail.record(
                Stage.PIPELINE,
                "FAILED",
                status=ProcessingStatus.FAILED,
                retryable=True,
                documents=[failure.document_id for failure in unavailable],
            )
            return self._finish(
                trail, source, digest, ProcessingStatus.FAILED, claim.claim_id,
                extractions=extractions, failures=failures, errors=(error,),
            )

        context = ValidationContext(
            claim=claim,
            policy=self._policy,
            extractions=tuple(extractions),
            failures=tuple(failures),
            prior_submissions=self._prior_submissions(claim, extractions),
        )
        results = self._validation.run(context)
        self._record_validation(trail, results)
        decision = self._decision.decide(results)
        trail.record(
            Stage.DECISION,
            "DECIDED",
            outcome=decision.outcome,
            reason_rules=sorted({reason.rule_id for reason in decision.reasons}),
            policy_version=self._policy.version,
            policy_digest=self._policy.digest,
        )
        self._register_fingerprints(claim, extractions)
        trail.record(Stage.PIPELINE, "COMPLETED", status=ProcessingStatus.COMPLETED)
        return self._finish(
            trail, source, digest, ProcessingStatus.COMPLETED, claim.claim_id,
            decision=decision, results=results, extractions=extractions, failures=failures,
        )

    # -- extraction ---------------------------------------------------------

    def _extract_documents(
        self, claim: Claim, trail: AuditTrail
    ) -> tuple[list[ExtractionResult], list[ExtractionFailure]]:
        extractions: list[ExtractionResult] = []
        failures: list[ExtractionFailure] = []
        for document in claim.documents:
            outcome = self._extract_one(document, trail)
            if isinstance(outcome, ExtractionFailure):
                failures.append(outcome)
            else:
                extractions.append(outcome)
        return extractions, failures

    def _extract_one(self, document: DocumentRef, trail: AuditTrail) -> ExtractionResult | ExtractionFailure:
        doc_id = document.document_id
        for attempt in range(1, self._max_attempts + 1):
            try:
                result = self._extractor.extract(document)
                if result.document_id != doc_id:
                    raise ExtractionError(
                        MISMATCHED_RESULT,
                        f"extractor returned a result for {result.document_id!r}",
                        retryable=False,
                    )
            except ExtractionError as exc:
                if exc.retryable and attempt < self._max_attempts:
                    trail.record(
                        Stage.EXTRACTION, "ATTEMPT_FAILED",
                        document_id=doc_id, attempt=attempt, kind=exc.kind, retryable=True, message=str(exc),
                    )
                    continue
                trail.record(
                    Stage.EXTRACTION, "FAILED",
                    document_id=doc_id, attempt=attempt, kind=exc.kind, retryable=exc.retryable, message=str(exc),
                )
                return ExtractionFailure(doc_id, exc.kind, str(exc), exc.retryable, attempt)
            trail.record(
                Stage.EXTRACTION, "SUCCEEDED",
                document_id=doc_id,
                attempt=attempt,
                provider=result.provider,
                source_sha256=result.source_sha256,
                fields=sorted(result.fields),
                line_items=len(result.line_items),
            )
            return replace(result, attempts=attempt)
        raise AssertionError("unreachable: every attempt returns or continues")

    # -- duplicates ---------------------------------------------------------

    def _prior_submissions(self, claim: Claim, extractions: Sequence[ExtractionResult]) -> dict[str, str]:
        prior: dict[str, str] = {}
        for extraction in extractions:
            fingerprint = receipt_fingerprint(extraction)
            if fingerprint is None:
                continue
            earlier = self._fingerprints.find_other_claim(fingerprint, claim.claim_id)
            if earlier is not None:
                prior[extraction.document_id] = earlier
        return prior

    def _register_fingerprints(self, claim: Claim, extractions: Sequence[ExtractionResult]) -> None:
        for extraction in extractions:
            fingerprint = receipt_fingerprint(extraction)
            if fingerprint is not None:
                self._fingerprints.register(fingerprint, claim.claim_id)

    # -- audit and results --------------------------------------------------

    def _open_trail(self, source: str, digest: str) -> AuditTrail:
        trail = AuditTrail(self._trace_ids.new_trace_id(), self._clock, self._sink)
        trail.record(Stage.INGESTION, "RECEIVED", source=source, input_digest=digest)
        return trail

    def _record_validation(self, trail: AuditTrail, results: Sequence[RuleResult]) -> None:
        for result in results:
            if "rule_error" in result.evidence:
                trail.record(Stage.VALIDATION, "RULE_ERROR", rule_id=result.rule_id, error=result.evidence["rule_error"])
        counts = Counter(result.outcome for result in results)
        trail.record(
            Stage.VALIDATION,
            "COMPLETED",
            rules=len(self._validation.rules),
            results=len(results),
            outcomes={outcome.value: counts.get(outcome, 0) for outcome in RuleOutcome},
        )

    def _reject_input(self, trail: AuditTrail, source: str, digest: str, exc: IngestionError) -> ProcessingResult:
        if exc.claim_id:
            trail.bind_claim(exc.claim_id)
        trail.record(Stage.INGESTION, "REJECTED", errors=list(exc.errors))
        trail.record(Stage.PIPELINE, "COMPLETED", status=ProcessingStatus.INVALID_INPUT)
        return self._finish(trail, source, digest, ProcessingStatus.INVALID_INPUT, exc.claim_id, errors=exc.errors)

    def _finish(
        self,
        trail: AuditTrail,
        source: str,
        digest: str,
        status: ProcessingStatus,
        claim_id: str | None,
        *,
        decision: Decision | None = None,
        results: Sequence[RuleResult] = (),
        extractions: Sequence[ExtractionResult] = (),
        failures: Sequence[ExtractionFailure] = (),
        errors: Sequence[str] = (),
    ) -> ProcessingResult:
        return ProcessingResult(
            trace_id=trail.trace_id,
            source=source,
            input_digest=digest,
            status=status,
            claim_id=claim_id,
            decision=decision,
            rule_results=tuple(results),
            extractions=tuple(extractions),
            extraction_failures=tuple(failures),
            audit_trail=trail.events,
            errors=tuple(errors),
            policy_version=self._policy.version,
            policy_digest=self._policy.digest,
        )
