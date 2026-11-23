"""Adjudication policy: every business threshold, loaded from a JSON document.

Rules read thresholds from the Policy instead of hard-coding them, and every
decision records the version and digest of the policy it was made under.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib import resources
from pathlib import Path
from typing import Any

from adjudication.domain.models import Category

_CURRENCY = re.compile(r"[A-Z]{3}")
_REQUIRED_KEYS = (
    "policy_version",
    "min_field_confidence",
    "amount_tolerance",
    "submission_window_days",
    "allowed_currencies",
    "required_fields",
    "category_limits",
)


class PolicyError(ValueError):
    """The policy document is incomplete or inconsistent."""


@dataclass(frozen=True)
class Policy:
    version: str
    digest: str
    min_field_confidence: float
    amount_tolerance: Decimal
    submission_window_days: int
    allowed_currencies: frozenset[str]
    required_fields: tuple[str, ...]
    category_limits: dict[Category, dict[str, Decimal]]

    def category_limit(self, category: Category, currency: str) -> Decimal | None:
        return self.category_limits.get(category, {}).get(currency)

    @classmethod
    def from_dict(cls, data: Any) -> Policy:
        if not isinstance(data, Mapping):
            raise PolicyError("policy must be a JSON object")
        missing = [key for key in _REQUIRED_KEYS if key not in data]
        if missing:
            raise PolicyError(f"missing keys: {', '.join(missing)}")
        errors: list[str] = []

        version = data["policy_version"]
        if not isinstance(version, str) or not version.strip():
            errors.append("policy_version must be a non-empty string")

        confidence = data["min_field_confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append("min_field_confidence must be a number between 0 and 1")

        tolerance = _decimal(data["amount_tolerance"])
        if tolerance is None or tolerance < 0:
            errors.append("amount_tolerance must be a non-negative decimal string")

        window = data["submission_window_days"]
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            errors.append("submission_window_days must be a positive integer")

        currencies = data["allowed_currencies"]
        if (
            not isinstance(currencies, list)
            or not currencies
            or not all(isinstance(code, str) and _CURRENCY.fullmatch(code) for code in currencies)
        ):
            errors.append("allowed_currencies must be a non-empty list of ISO 4217 codes")
            currencies = []

        required = data["required_fields"]
        if not isinstance(required, list) or not required or not all(isinstance(name, str) and name for name in required):
            errors.append("required_fields must be a non-empty list of field names")

        limits = _category_limits(data["category_limits"], set(currencies), errors)

        if errors:
            raise PolicyError("; ".join(errors))
        return cls(
            version=version,
            digest=_digest(data),
            min_field_confidence=float(confidence),
            amount_tolerance=tolerance,
            submission_window_days=window,
            allowed_currencies=frozenset(currencies),
            required_fields=tuple(required),
            category_limits=limits,
        )


def load_policy(path: str | Path | None = None) -> Policy:
    """Load a policy file, or the bundled demo policy when no path is given."""
    if path is None:
        text = resources.files("adjudication").joinpath("data/default_policy.json").read_text(encoding="utf-8")
    else:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise PolicyError(f"cannot read policy file: {exc.strerror}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PolicyError(f"policy is not valid JSON: {exc}") from exc
    return Policy.from_dict(data)


def _decimal(raw: Any) -> Decimal | None:
    if not isinstance(raw, str):
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _category_limits(raw: Any, currencies: set[str], errors: list[str]) -> dict[Category, dict[str, Decimal]]:
    if not isinstance(raw, Mapping):
        errors.append("category_limits must be an object")
        return {}
    limits: dict[Category, dict[str, Decimal]] = {}
    for name, per_currency in raw.items():
        try:
            category = Category(name)
        except ValueError:
            errors.append(f"category_limits: unknown category {name!r}")
            continue
        if not isinstance(per_currency, Mapping):
            errors.append(f"category_limits.{name} must be an object")
            continue
        parsed: dict[str, Decimal] = {}
        for currency, amount in per_currency.items():
            value = _decimal(amount)
            if currency not in currencies:
                errors.append(f"category_limits.{name}: currency {currency!r} is not in allowed_currencies")
            elif value is None or value <= 0:
                errors.append(f"category_limits.{name}.{currency} must be a positive decimal string")
            else:
                parsed[currency] = value
        limits[category] = parsed
    return limits


def _digest(data: Mapping[str, Any]) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
