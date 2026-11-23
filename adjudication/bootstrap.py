"""Composition root: wires the local adapters into the pipeline.

This is the only module that knows which concrete adapters exist. Swapping in
a different extractor or audit store means changing this file, not the core.
"""

from __future__ import annotations

from pathlib import Path

from adjudication.adapters.audit_sinks import InMemoryAuditSink
from adjudication.adapters.clock import DEMO_EPOCH, FixedClock, RandomTraceIds, SequentialTraceIds, SystemClock
from adjudication.adapters.extraction import FixtureExtractor
from adjudication.adapters.stores import InMemoryFingerprintStore
from adjudication.core.decision import DecisionEngine
from adjudication.core.pipeline import AdjudicationPipeline
from adjudication.core.rules import default_rules
from adjudication.core.validation import ValidationEngine
from adjudication.domain.policy import Policy, load_policy
from adjudication.ports import AuditSink


def build_local_pipeline(
    *,
    documents_dir: str | Path,
    extractions_dir: str | Path,
    policy: Policy | None = None,
    audit_sink: AuditSink | None = None,
    deterministic: bool = False,
    max_extraction_attempts: int = 3,
) -> AdjudicationPipeline:
    """Build a fully offline pipeline backed by recorded extraction fixtures.

    ``deterministic`` swaps the system clock and random trace ids for fixed
    ones, so two runs over the same inputs produce byte-identical output.
    """
    return AdjudicationPipeline(
        extractor=FixtureExtractor(documents_dir, extractions_dir),
        policy=policy or load_policy(),
        validation=ValidationEngine(default_rules()),
        decision_engine=DecisionEngine(),
        audit_sink=audit_sink or InMemoryAuditSink(),
        fingerprint_store=InMemoryFingerprintStore(),
        clock=FixedClock(DEMO_EPOCH) if deterministic else SystemClock(),
        trace_ids=SequentialTraceIds() if deterministic else RandomTraceIds(),
        max_extraction_attempts=max_extraction_attempts,
    )
