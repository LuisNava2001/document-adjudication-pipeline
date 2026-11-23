"""Conversion of domain objects to JSON-compatible structures."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Recursively convert dataclasses, enums, Decimals and dates for ``json.dumps``.

    Decimals become strings so amounts never pass through binary floating point.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(_key(k)): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted(to_jsonable(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def _key(key: Any) -> Any:
    return key.value if isinstance(key, Enum) else key
