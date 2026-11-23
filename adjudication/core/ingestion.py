"""Ingestion: turn an untrusted submission into a validated Claim.

Ingestion checks structure and format only. Business judgements, including
"no documents attached", belong to the validation rules, so they produce an
explained decision rather than a parse error.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from adjudication.domain.models import Category, Claim, DocumentRef

MAX_DOCUMENTS = 20
MAX_DESCRIPTION = 500
MEDIA_TYPES = frozenset({"text/plain", "application/pdf", "image/png", "image/jpeg"})

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
# A bare file name: no directory separators, no "..", at most one extension.
_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}(\.[A-Za-z0-9]{1,8})?")
_CURRENCY = re.compile(r"[A-Z]{3}")
_AMOUNT = re.compile(r"\d{1,9}(\.\d{1,2})?")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CLAIM_FIELDS = frozenset(
    {"claim_id", "claimant_id", "category", "claimed_amount", "currency", "submitted_on", "description", "documents"}
)
_DOCUMENT_FIELDS = frozenset({"document_id", "file", "media_type"})


class IngestionError(ValueError):
    """The submission cannot become a Claim. ``errors`` lists every problem found."""

    def __init__(self, errors: list[str], claim_id: str | None = None) -> None:
        super().__init__("; ".join(errors))
        self.errors = tuple(errors)
        self.claim_id = claim_id


def canonical_digest(payload: Any) -> str:
    """SHA-256 of the canonical JSON form, so key order and whitespace do not matter."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decode_payload(raw: bytes | str) -> Any:
    try:
        text = raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw
        return json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IngestionError([f"payload is not valid UTF-8 JSON ({exc})"]) from exc


def parse_claim(payload: Any) -> Claim:
    if not isinstance(payload, Mapping):
        raise IngestionError(["payload must be a JSON object"])
    errors: list[str] = []
    claim_id = _identifier(payload.get("claim_id"), "claim_id", errors)
    claimant_id = _identifier(payload.get("claimant_id"), "claimant_id", errors)
    category = _category(payload.get("category"), errors)
    claimed_amount = _amount(payload.get("claimed_amount"), "claimed_amount", errors)
    currency = _currency(payload.get("currency"), errors)
    submitted_on = _date(payload.get("submitted_on"), "submitted_on", errors)
    description = payload.get("description", "")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION:
        errors.append(f"description must be a string of at most {MAX_DESCRIPTION} characters")
    documents = _documents(payload.get("documents"), errors)
    unknown = sorted(str(key) for key in set(payload) - _CLAIM_FIELDS)
    if unknown:
        errors.append(f"unknown field(s): {', '.join(unknown)}")
    if errors:
        raise IngestionError(errors, claim_id)
    return Claim(
        claim_id=claim_id,
        claimant_id=claimant_id,
        category=category,
        claimed_amount=claimed_amount,
        currency=currency,
        submitted_on=submitted_on,
        description=description,
        documents=documents,
    )


def _identifier(value: Any, name: str, errors: list[str]) -> str | None:
    if isinstance(value, str) and _IDENTIFIER.fullmatch(value):
        return value
    errors.append(f"{name} must be 1-64 letters, digits, '-' or '_' (got {value!r})")
    return None


def _category(value: Any, errors: list[str]) -> Category | None:
    try:
        return Category(value)
    except (ValueError, TypeError):
        allowed = ", ".join(category.value for category in Category)
        errors.append(f"category must be one of {allowed} (got {value!r})")
        return None


def _amount(value: Any, name: str, errors: list[str]) -> Decimal | None:
    if isinstance(value, str) and _AMOUNT.fullmatch(value) and Decimal(value) > 0:
        return Decimal(value)
    errors.append(f"{name} must be a positive decimal string with up to 2 decimals, e.g. '42.50' (got {value!r})")
    return None


def _currency(value: Any, errors: list[str]) -> str | None:
    if isinstance(value, str) and _CURRENCY.fullmatch(value):
        return value
    errors.append(f"currency must be a 3-letter ISO 4217 code (got {value!r})")
    return None


def _date(value: Any, name: str, errors: list[str]) -> date | None:
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    errors.append(f"{name} must be an ISO date YYYY-MM-DD (got {value!r})")
    return None


def _documents(value: Any, errors: list[str]) -> tuple[DocumentRef, ...]:
    if not isinstance(value, list):
        errors.append("documents must be a list (it may be empty)")
        return ()
    if len(value) > MAX_DOCUMENTS:
        errors.append(f"at most {MAX_DOCUMENTS} documents are accepted")
        return ()
    refs: list[DocumentRef] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        where = f"documents[{index}]"
        if not isinstance(item, Mapping):
            errors.append(f"{where} must be an object")
            continue
        unknown = sorted(str(key) for key in set(item) - _DOCUMENT_FIELDS)
        if unknown:
            errors.append(f"{where}: unknown field(s): {', '.join(unknown)}")
        document_id = _identifier(item.get("document_id"), f"{where}.document_id", errors)
        file_name = item.get("file")
        if not (isinstance(file_name, str) and _FILE_NAME.fullmatch(file_name)):
            errors.append(f"{where}.file must be a bare file name without directories (got {file_name!r})")
            file_name = None
        media_type = item.get("media_type")
        if not (isinstance(media_type, str) and media_type in MEDIA_TYPES):
            errors.append(f"{where}.media_type must be one of {', '.join(sorted(MEDIA_TYPES))} (got {media_type!r})")
            media_type = None
        if document_id is not None:
            if document_id in seen:
                errors.append(f"{where}.document_id {document_id!r} is duplicated")
            seen.add(document_id)
        if document_id and file_name and media_type:
            refs.append(DocumentRef(document_id=document_id, file_name=file_name, media_type=media_type))
    return tuple(refs)
