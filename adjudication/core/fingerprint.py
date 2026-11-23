"""Content fingerprints used to detect receipts submitted more than once."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from adjudication.core.parsing import format_amount, is_currency_code, parse_amount, parse_iso_date
from adjudication.domain.models import ExtractionResult


def receipt_fingerprint(extraction: ExtractionResult) -> str | None:
    """Fingerprint a receipt by merchant, date, total and currency.

    Returns None when any component is missing or unreadable: an incomplete
    fingerprint would produce false duplicate matches.
    """
    merchant = _normalize_merchant(extraction.value("merchant_name") or "")
    transaction_date = parse_iso_date(extraction.value("transaction_date"))
    total = parse_amount(extraction.value("total_amount"))
    currency = extraction.value("currency")
    if not merchant or transaction_date is None or total is None or not is_currency_code(currency):
        return None
    material = "|".join((merchant, transaction_date.isoformat(), format_amount(total), currency.strip()))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _normalize_merchant(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", without_accents.casefold()).strip()
