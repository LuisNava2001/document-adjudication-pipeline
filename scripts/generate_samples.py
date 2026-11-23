"""Generate the synthetic sample set used by the demo and the golden tests.

Every merchant, person identifier, amount and date below is fictional. The
script writes, from one specification:

    samples/claims/*.json        claim submissions (the pipeline input)
    samples/documents/*.txt      plain-text renderings of synthetic receipts
    samples/extractions/*.json   recorded extraction results for each document
    samples/expected_outcomes.json
    samples/README.md

Usage, from the repository root:

    python scripts/generate_samples.py            # rewrite ./samples
    python scripts/generate_samples.py --out DIR  # write elsewhere (used by tests)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Allow running as a plain script from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adjudication.adapters.extraction import document_digest  # noqa: E402

FIELD_CONFIDENCE = 0.97
ITEM_CONFIDENCE = 0.95
WIDTH = 40
SYNTHETIC_MARKER = "SYNTHETIC DEMO DOCUMENT - NOT A REAL RECEIPT"


@dataclass(frozen=True)
class Receipt:
    merchant: str
    number: str
    date: str
    currency: str
    items: tuple[tuple[str, str], ...]
    tax: str
    total: str


@dataclass(frozen=True)
class Document:
    receipt: Receipt | None
    confidence: dict[str, float] = field(default_factory=dict)
    failure: dict[str, Any] | None = None


@dataclass(frozen=True)
class Scenario:
    file: str
    summary: str
    claim: dict[str, Any]
    status: str
    decision: str | None
    reason_rules: tuple[str, ...] = ()
    note: str | None = None


BLUE_FERN = Receipt(
    "BLUE FERN BISTRO", "R-0108-0117", "2026-01-08", "USD",
    (("Lentil soup", "9.50"), ("Grilled vegetables", "24.00"), ("Sparkling water", "4.00")), "5.00", "42.50",
)
OLIVE_COURT = Receipt(
    "OLIVE COURT DINER", "R-0204-0033", "2026-02-04", "USD",
    (("Lunch special", "18.00"), ("Fresh juice", "12.00")), "5.00", "35.00",
)

DOCUMENTS: dict[str, Document] = {
    "DOC-1001-A": Document(BLUE_FERN),
    "DOC-1002-A": Document(Receipt("QUICKSTEP CABS", "T-0120-5521", "2026-01-20", "USD", (("City fare", "21.00"),), "3.40", "24.40")),
    "DOC-1002-B": Document(Receipt("CEDAR LINE RAIL", "CL-0121-0098", "2026-01-21", "USD", (("Regional ticket", "62.00"),), "0.00", "62.00")),
    "DOC-1003-A": Document(Receipt("SAFFRON LANE KITCHEN", "R-0114-0410", "2026-01-14", "USD", (("Set menu", "18.00"), ("Set menu, large", "22.00")), "8.00", "48.00")),
    "DOC-1004-A": Document(Receipt("PAPER LANTERN STATIONERY", "S-1002-0007", "2025-10-02", "USD", (("Printer paper", "18.99"), ("Gel pens", "10.00")), "3.00", "31.99")),
    "DOC-1005-A": Document(
        Receipt("JUNIPER NOODLE HOUSE", "R-0119-0222", "2026-01-19", "USD", (("Noodle bowl", "15.50"), ("Dumplings", "16.70")), "6.00", "38.20"),
        confidence={"total_amount": 0.61},
    ),
    "DOC-1006-A": Document(Receipt("HARBOR VIEW INN", "H-0126-1180", "2026-01-26", "USD", (("Room, night 1", "210.00"), ("Room, night 2", "210.00")), "60.00", "480.00")),
    "DOC-1007-A": Document(
        None,
        failure={"kind": "UNREADABLE_DOCUMENT", "retryable": False, "fail_attempts": None, "message": "image too blurred to read"},
    ),
    "DOC-1008-A": Document(Receipt("CAFE LUMEN", "CL-0127-0301", "2026-01-27", "EUR", (("Lunch menu", "25.00"), ("Dessert and coffee", "22.00")), "8.00", "55.00")),
    "DOC-1009-A": Document(
        Receipt("MAPLE RIDGE SHUTTLE", "MR-0203-0044", "2026-02-03", "CAD", (("Airport shuttle", "56.00"),), "8.00", "64.00"),
        failure={"kind": "SERVICE_UNAVAILABLE", "retryable": True, "fail_attempts": 1, "message": "HTTP 503 from the extraction service"},
    ),
    "DOC-1010-A": Document(
        Receipt("CORNER DESK DEPOT", "CD-0204-0815", "2026-02-04", "USD", (("Stapler", "17.99"),), "2.00", "19.99"),
        failure={"kind": "SERVICE_UNAVAILABLE", "retryable": True, "fail_attempts": None, "message": "HTTP 503 from the extraction service"},
    ),
    "DOC-1011-A": Document(OLIVE_COURT),
    "DOC-1011-B": Document(OLIVE_COURT),
    "DOC-1012-A": Document(Receipt("BRIGHTDESK SUPPLY CO.", "B-0206-0612", "2026-02-06", "USD", (("Notebook pack", "12.00"), ("Desk organizer", "13.00")), "1.50", "27.50")),
    "DOC-1014-A": Document(BLUE_FERN),
}


def _claim(claim_id, category, amount, currency, submitted, description, documents, claimant="CLMT-0042"):
    return {
        "claim_id": claim_id,
        "claimant_id": claimant,
        "category": category,
        "claimed_amount": amount,
        "currency": currency,
        "submitted_on": submitted,
        "description": description,
        "documents": [{"document_id": doc, "file": f"{doc}.txt", "media_type": "text/plain"} for doc in documents],
    }


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("CLM-1001.json", "Clean meal receipt; every check passes.",
             _claim("CLM-1001", "MEALS", "42.50", "USD", "2026-01-12", "Lunch with a visiting partner", ["DOC-1001-A"]),
             "COMPLETED", "APPROVED"),
    Scenario("CLM-1002.json", "Two travel receipts that add up to the claimed amount.",
             _claim("CLM-1002", "TRAVEL", "86.40", "USD", "2026-01-23", "Taxi and train to a workshop", ["DOC-1002-A", "DOC-1002-B"], "CLMT-0107"),
             "COMPLETED", "APPROVED"),
    Scenario("CLM-1003.json", "Claimed amount exceeds the receipt total.",
             _claim("CLM-1003", "MEALS", "65.00", "USD", "2026-01-16", "Working dinner", ["DOC-1003-A"], "CLMT-0213"),
             "COMPLETED", "REJECTED", ("CON-003",)),
    Scenario("CLM-1004.json", "Receipt is older than the 60-day submission window.",
             _claim("CLM-1004", "OFFICE_SUPPLIES", "31.99", "USD", "2026-01-15", "Printer paper and pens", ["DOC-1004-A"], "CLMT-0107"),
             "COMPLETED", "REJECTED", ("POL-001",)),
    Scenario("CLM-1005.json", "Total amount extracted with low confidence.",
             _claim("CLM-1005", "MEALS", "38.20", "USD", "2026-01-21", "Team lunch", ["DOC-1005-A"], "CLMT-0318"),
             "COMPLETED", "MANUAL_REVIEW", ("EXT-003",)),
    Scenario("CLM-1006.json", "Lodging claim above the category limit.",
             _claim("CLM-1006", "LODGING", "480.00", "USD", "2026-01-28", "Two nights for an onsite visit", ["DOC-1006-A"], "CLMT-0213"),
             "COMPLETED", "MANUAL_REVIEW", ("POL-003",)),
    Scenario("CLM-1007.json", "The only document is unreadable (permanent extraction failure).",
             _claim("CLM-1007", "TRAINING", "150.00", "EUR", "2026-02-02", "Workshop registration", ["DOC-1007-A"], "CLMT-0420"),
             "COMPLETED", "MANUAL_REVIEW", ("CON-003", "EXT-001")),
    Scenario("CLM-1008.json", "Receipt currency differs from the claim currency.",
             _claim("CLM-1008", "MEALS", "55.00", "USD", "2026-01-30", "Lunch during a trip abroad", ["DOC-1008-A"], "CLMT-0318"),
             "COMPLETED", "MANUAL_REVIEW", ("CON-002", "CON-003")),
    Scenario("CLM-1009.json", "Extraction service fails once, the retry succeeds.",
             _claim("CLM-1009", "TRAVEL", "64.00", "CAD", "2026-02-05", "Airport shuttle", ["DOC-1009-A"], "CLMT-0420"),
             "COMPLETED", "APPROVED"),
    Scenario("CLM-1010.json", "Extraction service stays unavailable; retries are exhausted.",
             _claim("CLM-1010", "OFFICE_SUPPLIES", "19.99", "USD", "2026-02-06", "Stapler", ["DOC-1010-A"]),
             "FAILED", None),
    Scenario("CLM-1011.json", "The same receipt is attached twice.",
             _claim("CLM-1011", "MEALS", "70.00", "USD", "2026-02-06", "Lunch, two receipts", ["DOC-1011-A", "DOC-1011-B"], "CLMT-0525"),
             "COMPLETED", "REJECTED", ("DUP-001",)),
    Scenario("CLM-1012.json", "Line items and tax do not add up to the printed total.",
             _claim("CLM-1012", "OFFICE_SUPPLIES", "27.50", "USD", "2026-02-09", "Notebooks and organizer", ["DOC-1012-A"], "CLMT-0525"),
             "COMPLETED", "MANUAL_REVIEW", ("CON-001",)),
    Scenario("CLM-1013.json", "No supporting document attached.",
             _claim("CLM-1013", "TRAVEL", "40.00", "USD", "2026-02-10", "Parking", [], "CLMT-0630"),
             "COMPLETED", "REJECTED", ("DOC-001",)),
    Scenario("CLM-1014.json", "Re-submits the receipt already claimed in CLM-1001.",
             _claim("CLM-1014", "MEALS", "42.50", "USD", "2026-01-29", "Lunch with a visiting partner", ["DOC-1014-A"], "CLMT-0630"),
             "COMPLETED", "MANUAL_REVIEW", ("DUP-002",),
             note="Batch-order dependent: flagged only when CLM-1001 was processed earlier by the same pipeline."),
    Scenario("CLM-1015.json", "Malformed submission rejected at ingestion.",
             {"claim_id": "CLM-1015", "claimant_id": "CLMT-0630", "category": "SNACKS", "claimed_amount": "-5.00",
              "currency": "USD", "submitted_on": "15/01/2026", "description": "Invalid on purpose", "documents": []},
             "INVALID_INPUT", None),
)


def render_receipt(receipt: Receipt) -> str:
    def row(label: str, amount: str) -> str:
        return f"{label:<{WIDTH - 12}}{amount:>12}"

    lines = [
        "=" * WIDTH,
        receipt.merchant.center(WIDTH).rstrip(),
        "(fictional merchant)".center(WIDTH).rstrip(),
        "=" * WIDTH,
        f"Receipt   {receipt.number}",
        f"Date      {receipt.date}",
        "-" * WIDTH,
        *(row(description, amount) for description, amount in receipt.items),
        "-" * WIDTH,
        row("Tax", receipt.tax),
        row(f"TOTAL {receipt.currency}", receipt.total),
        "=" * WIDTH,
        SYNTHETIC_MARKER,
    ]
    return "\n".join(lines) + "\n"


def render_unreadable() -> str:
    noise = ["  ~#%  .:  ##@  ..  %&*  ~~  .#  ;;", "  ..  ~~%  #  .:.  @@  ~  %#  ..  :", "  #  ..  ~%%  ;  .#.  ~~  @  :  %"]
    return "\n".join(["[SCAN - IMAGE QUALITY TOO LOW TO READ]", *noise, SYNTHETIC_MARKER]) + "\n"


def build_recording(document_id: str, document: Document, digest: str) -> dict[str, Any]:
    recording: dict[str, Any] = {
        "document_id": document_id,
        "provider": "synthetic-recording",
        "note": "Pre-recorded extraction result for a synthetic document. No OCR was performed.",
        "source_sha256": digest,
        "page_count": 1,
        "fields": {},
        "line_items": [],
    }
    receipt = document.receipt
    if receipt is not None:
        values = {
            "merchant_name": receipt.merchant,
            "receipt_number": receipt.number,
            "transaction_date": receipt.date,
            "currency": receipt.currency,
            "tax": receipt.tax,
            "total_amount": receipt.total,
        }
        recording["fields"] = {
            name: {"value": value, "confidence": document.confidence.get(name, FIELD_CONFIDENCE)}
            for name, value in values.items()
        }
        recording["line_items"] = [
            {"description": description, "amount": amount, "confidence": ITEM_CONFIDENCE}
            for description, amount in receipt.items
        ]
    if document.failure is not None:
        recording["simulated_failure"] = document.failure
    return recording


def samples_readme() -> str:
    rows = "\n".join(
        f"| `{s.file}` | {s.summary} | {s.status} | {s.decision or '-'} | {', '.join(s.reason_rules) or '-'} |"
        for s in SCENARIOS
    )
    return (
        "# Synthetic samples\n\n"
        "Everything in this directory is fictional and generated by `scripts/generate_samples.py`.\n"
        "Do not edit by hand: change the generator and re-run it. `tests/test_samples.py` fails if the\n"
        "committed files drift from the generator output.\n\n"
        "- `claims/`: claim submissions, the pipeline input.\n"
        "- `documents/`: plain-text renderings of synthetic receipts.\n"
        "- `extractions/`: recorded extraction results, one per document. They simulate the output of a\n"
        "  document-analysis service; no OCR is performed anywhere in this repository.\n"
        "- `expected_outcomes.json`: the outcome each claim must produce in a batch run.\n\n"
        "| File | Scenario | Status | Decision | Reason rules |\n"
        "|---|---|---|---|---|\n"
        f"{rows}\n"
    )


def generate(out_dir: Path) -> list[Path]:
    """Write the full sample set under ``out_dir`` and return the written paths."""
    written: list[Path] = []

    def write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)

    for document_id, document in DOCUMENTS.items():
        text = render_receipt(document.receipt) if document.receipt else render_unreadable()
        write(out_dir / "documents" / f"{document_id}.txt", text)
        digest = document_digest(text.encode("utf-8"), "text/plain")
        recording = build_recording(document_id, document, digest)
        write(out_dir / "extractions" / f"{document_id}.json", json.dumps(recording, indent=2) + "\n")

    for scenario in SCENARIOS:
        write(out_dir / "claims" / scenario.file, json.dumps(scenario.claim, indent=2) + "\n")

    expected = {
        "description": "Outcome each claim must produce when samples/claims is processed as one batch, in file-name order.",
        "outcomes": {
            s.file: {
                "scenario": s.summary,
                "status": s.status,
                "decision": s.decision,
                "reason_rules": list(s.reason_rules),
                **({"note": s.note} if s.note else {}),
            }
            for s in SCENARIOS
        },
    }
    write(out_dir / "expected_outcomes.json", json.dumps(expected, indent=2) + "\n")
    write(out_dir / "README.md", samples_readme())
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="samples", help="output directory (default: %(default)s)")
    args = parser.parse_args(argv)
    written = generate(Path(args.out))
    print(f"Wrote {len(written)} files under {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
