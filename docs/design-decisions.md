# Technical design decisions

Short records of the choices that shape this codebase, with the reasoning and the trade-off accepted.

## 1. Ports and adapters

The core imports only domain types and `Protocol` interfaces. `bootstrap.py` is the single composition root,
so an OCR service, a durable store or a queue trigger can be added as an adapter without touching rules,
decisions or orchestration. *Trade-off:* a few more modules than a script would need.

## 2. Processing status is not a decision

A dependency outage (`FAILED`, retryable) and a business doubt (`MANUAL_REVIEW`) need different handling:
one should be retried, the other needs a person. Mixing them hides outages and overloads reviewers. Permanent
document problems (for example, an unreadable scan) are business outcomes and do produce a decision.

## 3. Fail-safe decision semantics

`SKIPPED` means "the rule applies, but its evidence is unavailable". It can never reject, because there is no
rejection without evidence, and never approve, because there is no approval by default. Approval requires at
least one `PASS` and no `FAIL` or `SKIPPED`; an empty or all-`NOT_APPLICABLE` result set goes to review.
A claim with no document attached is a different case: `DOC-001` evaluates fully, fails with `REJECT` severity
and rejects the claim, because the absence of any document is itself the evidence.
An exception inside a rule is converted into a `SKIPPED` result and recorded as a `RULE_ERROR` audit event,
so a bug can only make the system more cautious.

## 4. Extracted values stay as text

Extraction output is untrusted. Rules parse values with strict parsers (ISO dates only, plain decimals only)
and report what they could not parse, instead of coercing `08/01/2026` or `4O.50` into something plausible.
Money is `Decimal` end to end and serialized as strings, never as binary floating point.

## 5. Policy as versioned data

Thresholds and category limits live in JSON and are validated on load. Each decision event records the
policy version and a SHA-256 digest of the policy content, so a decision can be tied to the exact policy
in force when it was made.

## 6. Content-addressed fixtures

Each recorded extraction stores the SHA-256 of the document it describes, and the extractor refuses a
recording that no longer matches its document. Fixtures therefore cannot drift silently. Text documents
are hashed with normalized line endings and `.gitattributes` keeps LF, so Windows checkouts behave the same.

## 7. Determinism by injection

The clock and the trace-id factory are ports. Tests and `--deterministic` runs use fixed implementations,
which makes golden tests and byte-for-byte comparisons possible. Rules compare dates with the claim's
submission date, never with "today", so outcomes do not change as time passes.

## 8. Strict ingestion

Unknown fields are rejected, all problems are reported in one response, and document references must be
bare file names. The extractor additionally checks that resolved paths stay inside the documents directory
(defense in depth against path traversal). "No documents attached" is deliberately left to a business rule,
so it yields an explained rejection rather than a parse error.

## 9. Idempotent duplicate detection

Receipts are fingerprinted from normalized merchant, date, total and currency; incomplete fingerprints are
never compared. The store keeps the first claim that registered each fingerprint, so reprocessing a claim
never flags its own receipts, while a different claim that reuses a receipt is sent to review.

## 10. Standard library only

No installation step, a small dependency surface and reproducible runs on any Python 3.11+ interpreter.
*Trade-off:* hand-written validation instead of a schema library, and a CLI instead of an HTTP API. Both are
reasonable at this scope and can be revisited when a web or cloud adapter is added.

## 11. A static, data-driven demo

The visual demo is plain HTML, CSS and JavaScript reading a generated `data.js`. A classic script include
works from `file://`, so the viewer opens from disk with no server, build step or network access. All data
is inserted with `textContent`; a test fails if the viewer ever uses HTML injection APIs or external URLs.
