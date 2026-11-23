"""Strict parsers for extracted text. They return None rather than guess."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

_AMOUNT = re.compile(r"-?\d{1,9}(\.\d{1,2})?")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CURRENCY = re.compile(r"[A-Z]{3}")


def present(value: str | None) -> bool:
    return value is not None and value.strip() != ""


def parse_amount(raw: str | None) -> Decimal | None:
    """Parse '42.50' or '-3.00'. Thousands separators and symbols are rejected."""
    if raw is None or not _AMOUNT.fullmatch(raw.strip()):
        return None
    return Decimal(raw.strip())


def parse_iso_date(raw: str | None) -> date | None:
    """Parse YYYY-MM-DD only; ambiguous formats such as 03/04/2026 are rejected."""
    if raw is None or not _ISO_DATE.fullmatch(raw.strip()):
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def is_currency_code(raw: str | None) -> bool:
    return raw is not None and _CURRENCY.fullmatch(raw.strip()) is not None


def format_amount(value: Decimal) -> str:
    return f"{value:.2f}"
