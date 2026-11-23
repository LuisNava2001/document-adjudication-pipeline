# Walkthrough

All commands run from the repository root. Output was produced with `--deterministic`, which fixes the clock
and uses sequential trace ids; without the flag, real UTC time and random trace ids are used.

## CLI reference

| Command | Purpose |
|---|---|
| `process CLAIM.json [--json] [--verbose] [--audit-log FILE]` | Adjudicate one claim |
| `batch DIR [--out DIR]` | Adjudicate every `*.json` claim in a directory, in file-name order |
| `rules` | Print the rule catalogue |

Common options: `--documents-dir` (default `samples/documents`), `--extractions-dir` (default
`samples/extractions`), `--policy FILE`, `--deterministic`, `--max-attempts N` (default 3).

Exit codes: `0` processing completed (any decision), `1` processing failed on a retryable dependency,
`2` usage or configuration error, `3` invalid input.

## 1. A retried extraction

In `CLM-1009` the recorded extraction service returns HTTP 503 once. The pipeline retries, succeeds on the
second attempt and approves; the audit trail shows both attempts.

```text
$ python -m adjudication process samples/claims/CLM-1009.json --deterministic
Claim     : CLM-1009  [source: CLM-1009.json]
Trace     : trc-000001
Status    : COMPLETED
Decision  : APPROVED - All 13 applicable checks passed.
Checks    : PASS 13, FAIL 0, SKIPPED 0, NOT_APPLICABLE 1
Policy    : demo-2026.1
Audit     : 7 events
   1. INGESTION:RECEIVED
   2. INGESTION:ACCEPTED
   3. EXTRACTION:ATTEMPT_FAILED (document_id=DOC-1009-A, attempt=1, kind=SERVICE_UNAVAILABLE)
   4. EXTRACTION:SUCCEEDED (document_id=DOC-1009-A, attempt=2)
   5. VALIDATION:COMPLETED
   6. DECISION:DECIDED (outcome=APPROVED)
   7. PIPELINE:COMPLETED (status=COMPLETED)
```

When the service never recovers (`CLM-1010`), processing ends as `FAILED` with exit code `1` and no decision.

## 2. Every rule result

`--verbose` lists all rule results for the claim:

```text
$ python -m adjudication process samples/claims/CLM-1003.json --deterministic --verbose
...
Rule results:
  PASS           DOC-001  claim       1 supporting document(s) attached.
  PASS           EXT-001  DOC-1003-A  Extracted on attempt 1.
  PASS           EXT-002  DOC-1003-A  All required fields present.
  PASS           EXT-003  DOC-1003-A  4 required field(s) at or above 0.85.
  PASS           FMT-001  DOC-1003-A  6 value(s) well formed.
  PASS           AMT-001  DOC-1003-A  Document total 48.00 is positive.
  PASS           CON-001  DOC-1003-A  Line items plus tax reconcile with total 48.00.
  PASS           CON-002  DOC-1003-A  Document currency USD matches the claim.
  FAIL           CON-003  claim       Claimed 65.00 USD exceeds the documented total 48.00 USD.
  PASS           POL-001  DOC-1003-A  Receipt is 2 day(s) old, within the 60-day window.
  PASS           POL-002  DOC-1003-A  Receipt is not future-dated.
  PASS           POL-003  claim       Claimed 65.00 USD is within the MEALS limit of 75.00 USD.
  NOT_APPLICABLE DUP-001  claim       Fewer than two extracted documents.
  PASS           DUP-002  DOC-1003-A  Receipt not seen in earlier claims.
```

`--json` prints the complete `ProcessingResult`, including each rule's evidence, the extraction results
and the audit trail.

## 3. The full sample batch

```text
$ python -m adjudication batch samples/claims --deterministic
SOURCE            STATUS         DECISION       REASONS
---------------------------------------------------------------------------
CLM-1001.json     COMPLETED      APPROVED       -
CLM-1002.json     COMPLETED      APPROVED       -
CLM-1003.json     COMPLETED      REJECTED       CON-003
CLM-1004.json     COMPLETED      REJECTED       POL-001
CLM-1005.json     COMPLETED      MANUAL_REVIEW  EXT-003
CLM-1006.json     COMPLETED      MANUAL_REVIEW  POL-003
CLM-1007.json     COMPLETED      MANUAL_REVIEW  CON-003, EXT-001
CLM-1008.json     COMPLETED      MANUAL_REVIEW  CON-002, CON-003
CLM-1009.json     COMPLETED      APPROVED       -
CLM-1010.json     FAILED         -              -
CLM-1011.json     COMPLETED      REJECTED       DUP-001
CLM-1012.json     COMPLETED      MANUAL_REVIEW  CON-001
CLM-1013.json     COMPLETED      REJECTED       DOC-001
CLM-1014.json     COMPLETED      MANUAL_REVIEW  DUP-002
CLM-1015.json     INVALID_INPUT  -              -

15 submission(s): COMPLETED 13, FAILED 1, INVALID_INPUT 1 | decisions: APPROVED 3, MANUAL_REVIEW 6, REJECTED 4

Wrote 15 result file(s), summary.json and audit.jsonl to demo-output
```

The batch writes `demo-output/results/<claim>.json` (one full result per claim), `demo-output/summary.json`
(counts and one row per claim) and `demo-output/audit.jsonl` (one event per line):

```json
{"claim_id": null, "detail": {"input_digest": "d3731f779490547c5f83e32e6fa9b95ed7679599a068d85e8fa4bd937ba85044", "source": "CLM-1001.json"}, "event": "RECEIVED", "sequence": 1, "stage": "INGESTION", "timestamp": "2026-03-01T00:00:00+00:00", "trace_id": "trc-000001"}
```

Each scenario is described in [`samples/README.md`](../samples/README.md). Two are worth noting:

- `CLM-1007`: the only document is unreadable, so `CON-003` cannot compute a documented total and is
  `SKIPPED`. The claim goes to review instead of being rejected for missing evidence.
- `CLM-1014` re-submits the receipt already claimed in `CLM-1001`. It is flagged only because both claims
  run through the same pipeline instance in that order; processed alone, it is approved.

## 4. The visual demo

Open `demo/index.html` in a browser. No server is needed: the page reads `demo/data.js` through a plain
script include and makes no network requests.

- The left panel lists the claims; the chips filter them by outcome. Arrow keys move through the list.
- The detail view shows the pipeline stages, the decision basis with its evidence, the claim and processing
  metadata, each synthetic receipt next to its recorded extraction (with confidence and the policy
  threshold), all rule results, the audit timeline and the raw result JSON.
- Each claim has its own URL fragment, for example `demo/index.html#CLM-1007`.
- The theme button cycles between automatic, light and dark.

`demo/data.js` is generated, not hand-written. After changing samples, rules or policy, rebuild it:

```bash
python scripts/build_demo_data.py
```

To view a different set of claims, point the script at it:

```bash
python scripts/build_demo_data.py --claims-dir my-claims --documents-dir my-documents \
    --extractions-dir my-extractions --out demo/data.js
```

## 5. Experiment

- Copy a claim, change `claimed_amount` or a document reference, and run `process` on it.
- Change thresholds: copy `adjudication/data/default_policy.json` and pass `--policy your-policy.json`.
- Change the dataset: edit `scripts/generate_samples.py`, run `python scripts/generate_samples.py`, then
  `python scripts/build_demo_data.py`. The tests fail if either generated set drifts from its generator.
