"""Process-local fingerprint store. State lives for the lifetime of one pipeline."""

from __future__ import annotations


class InMemoryFingerprintStore:
    def __init__(self) -> None:
        self._first_claim: dict[str, str] = {}

    def find_other_claim(self, fingerprint: str, claim_id: str) -> str | None:
        owner = self._first_claim.get(fingerprint)
        return owner if owner is not None and owner != claim_id else None

    def register(self, fingerprint: str, claim_id: str) -> None:
        # First submission wins, so reprocessing a claim never flags its own receipts.
        self._first_claim.setdefault(fingerprint, claim_id)
