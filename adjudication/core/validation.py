"""Validation engine: runs every rule and collects its results."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from adjudication.core.rules.base import Rule, ValidationContext
from adjudication.domain.models import RuleOutcome, RuleResult


class ValidationEngine:
    def __init__(self, rules: Sequence[Rule]) -> None:
        duplicated = sorted(rule_id for rule_id, n in Counter(rule.rule_id for rule in rules).items() if n > 1)
        if duplicated:
            raise ValueError(f"duplicate rule ids: {', '.join(duplicated)}")
        self._rules = tuple(rules)

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    def run(self, ctx: ValidationContext) -> tuple[RuleResult, ...]:
        results: list[RuleResult] = []
        for rule in self._rules:
            try:
                results.extend(rule.evaluate(ctx))
            except Exception as exc:  # noqa: BLE001 - a broken rule must never count as a pass
                results.append(
                    RuleResult(
                        rule_id=rule.rule_id,
                        outcome=RuleOutcome.SKIPPED,
                        severity=rule.severity,
                        message=f"Rule raised {type(exc).__name__}: {exc}",
                        evidence={"rule_error": type(exc).__name__},
                    )
                )
        return tuple(results)
