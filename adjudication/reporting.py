"""Plain-text rendering for the CLI. ASCII only, so output is safe on any console encoding."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from adjudication.domain.models import AuditEvent, ProcessingResult, RuleOutcome, RuleResult

_HINT_KEYS = ("document_id", "attempt", "kind", "outcome", "status")


def render_result(result: ProcessingResult, *, verbose: bool = False) -> str:
    lines = [
        f"Claim     : {result.claim_id or '(unknown)'}  [source: {result.source}]",
        f"Trace     : {result.trace_id}",
        f"Status    : {result.status}",
    ]
    if result.decision is not None:
        lines.append(f"Decision  : {result.decision.outcome} - {result.decision.summary}")
        if result.decision.reasons:
            lines.append("Reasons   :")
            lines.extend(f"  - {_describe(reason)}" for reason in result.decision.reasons)
    else:
        lines.append("Decision  : none")
    if result.errors:
        lines.append("Errors    :")
        lines.extend(f"  - {error}" for error in result.errors)
    if result.rule_results:
        counts = Counter(r.outcome for r in result.rule_results)
        lines.append("Checks    : " + ", ".join(f"{outcome} {counts.get(outcome, 0)}" for outcome in RuleOutcome))
    if verbose and result.rule_results:
        lines.append("Rule results:")
        for r in result.rule_results:
            lines.append(f"  {r.outcome:<14} {r.rule_id:<8} {r.document_id or 'claim':<11} {r.message}")
    lines.append(f"Policy    : {result.policy_version}")
    lines.append(f"Audit     : {len(result.audit_trail)} events")
    lines.extend(f"  {event.sequence:>2}. {event.stage}:{event.event}{_hint(event)}" for event in result.audit_trail)
    return "\n".join(lines)


def render_batch(results: Sequence[ProcessingResult]) -> str:
    header = f"{'SOURCE':<18}{'STATUS':<15}{'DECISION':<15}REASONS"
    rows = [header, "-" * len(header + " " * 20)]
    for result in results:
        decision = result.decision.outcome if result.decision else "-"
        reasons = ", ".join(sorted({r.rule_id for r in result.decision.reasons})) if result.decision else ""
        rows.append(f"{result.source:<18}{result.status:<15}{decision:<15}{reasons or '-'}")
    rows.append("")
    rows.append(summary_line(results))
    return "\n".join(rows)


def summary_line(results: Sequence[ProcessingResult]) -> str:
    statuses = Counter(result.status for result in results)
    decisions = Counter(result.decision.outcome for result in results if result.decision)
    parts = [f"{status} {count}" for status, count in sorted(statuses.items())]
    decided = ", ".join(f"{outcome} {count}" for outcome, count in sorted(decisions.items()))
    return f"{len(results)} submission(s): " + ", ".join(parts) + (f" | decisions: {decided}" if decided else "")


def _describe(reason: RuleResult) -> str:
    scope = f"{reason.document_id}: " if reason.document_id else ""
    return f"{reason.rule_id} [{reason.outcome}/{reason.severity}] {scope}{reason.message}"


def _hint(event: AuditEvent) -> str:
    parts = [f"{key}={event.detail[key]}" for key in _HINT_KEYS if key in event.detail]
    return f" ({', '.join(parts)})" if parts else ""
