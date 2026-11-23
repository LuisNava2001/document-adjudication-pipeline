# Validation rules

Fourteen deterministic rules run on every accepted claim, in the order below. Each returns one result per
scope it judges: the claim, or each successfully extracted document.

## Outcomes and severity

| Outcome | Meaning |
|---|---|
| `PASS` | The rule evaluated and the check holds |
| `FAIL` | The rule evaluated and the check does not hold |
| `SKIPPED` | The rule applies, but the evidence it needs is unavailable |
| `NOT_APPLICABLE` | The rule does not apply to this claim or document |

| Severity | Effect of a `FAIL` |
|---|---|
| `REJECT` | Sufficient grounds to reject the claim |
| `REVIEW` | The claim needs a human decision |

A `SKIPPED` result always routes the claim to manual review, whatever the rule's severity.

## Catalogue

| ID | Severity | Scope | Fails when | Skipped when | Not applicable when | Policy parameter |
|---|---|---|---|---|---|---|
| `DOC-001` | REJECT | claim | no document is attached | - | - | - |
| `EXT-001` | REVIEW | each attached document | extraction failed permanently | no outcome recorded | no documents | - |
| `EXT-002` | REVIEW | each extracted document | a required field is missing or blank | - | - | `required_fields` |
| `EXT-003` | REVIEW | each extracted document | a required field's confidence is below the threshold | no required field present | - | `min_field_confidence` |
| `FMT-001` | REVIEW | each extracted document | a date, amount or line amount is malformed, or the currency is not allowed | nothing to check | - | `allowed_currencies` |
| `AMT-001` | REJECT | each extracted document | the total is zero or negative | total unreadable | - | - |
| `CON-001` | REVIEW | each extracted document | line items plus tax differ from the total | an amount is unreadable | no line items | `amount_tolerance` |
| `CON-002` | REVIEW | each extracted document | document currency differs from the claim currency | currency missing or invalid | - | - |
| `CON-003` | REJECT | claim | claimed amount exceeds the documented total | a document failed extraction, a total is unreadable, or a document is in another currency | no documents | `amount_tolerance` |
| `POL-001` | REJECT | each extracted document | the receipt is older than the submission window | date missing or invalid | receipt dated after submission | `submission_window_days` |
| `POL-002` | REVIEW | each extracted document | the receipt is dated after the submission | date missing or invalid | - | - |
| `POL-003` | REVIEW | claim | claimed amount exceeds the category limit | no limit for the category and currency | - | `category_limits` |
| `DUP-001` | REJECT | claim | two attached documents are the same receipt | a document lacks fingerprint fields | fewer than two extracted documents | - |
| `DUP-002` | REVIEW | each extracted document | the receipt was registered by an earlier claim | the receipt lacks fingerprint fields | - | - |

Missing tax counts as zero for `CON-001`. Receipt fingerprints combine the normalized merchant name,
transaction date, total and currency.

## Demo policy

`adjudication/data/default_policy.json` (version `demo-2026.1`):

| Parameter | Value |
|---|---|
| `min_field_confidence` | 0.85 |
| `amount_tolerance` | 0.01 |
| `submission_window_days` | 60 |
| `allowed_currencies` | USD, EUR, CAD |
| `required_fields` | merchant_name, transaction_date, currency, total_amount |
| `category_limits` | per category and currency, for example MEALS 75.00 USD, LODGING 300.00 USD |

The rules and limits model a fictional reimbursement domain. They are illustrative, not a real expense policy.
