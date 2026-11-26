# Testing

```bash
python -m unittest discover -s tests -v
# or, if pytest is installed:
python -m pytest
```

The tests use only the standard library and need no network access or credentials. At the time of writing
the suite has 135 tests and finishes in a few seconds. It has been run locally on Windows with Python 3.11.9
under both runners.

## What is covered

| Module | Coverage |
|---|---|
| `test_rules.py` | Every rule's `PASS`, `FAIL`, `SKIPPED` and `NOT_APPLICABLE` paths, window boundaries, tolerances |
| `test_decision.py` | Decision precedence and the fail-safe guarantees |
| `test_ingestion.py` | Schema checks, error aggregation, path traversal, unknown fields, input digests |
| `test_fixture_extractor.py` | Recorded results, SHA-256 integrity, CRLF handling, replayed failures, path containment |
| `test_pipeline.py` | Stage order, retries, failure semantics, idempotent reprocessing, cross-claim duplicates, crashing rules |
| `test_cli.py` | Commands, exit codes and written artifacts |
| `test_samples.py` | Golden outcomes for all 15 samples, byte-identical deterministic runs, sample generator drift |
| `test_demo.py` | Demo data matches a fresh build, covers every sample, page loads only local files, no HTML injection |
| `test_policy_and_adapters.py` | Policy validation, clocks, trace ids, audit sinks, fingerprint store, serialization |

## Golden and drift tests

- `samples/expected_outcomes.json` states the outcome every sample claim must produce in a batch run.
  `test_samples.py` checks status, decision and reason rules for each one.
- The committed samples are regenerated into a temporary directory and compared byte for byte, so the
  dataset cannot be edited by hand without updating its generator.
- `demo/data.js` is rebuilt and compared the same way, so the visual demo always reflects current behavior.

## Verification limits

- The GitHub Actions workflow (`.github/workflows/ci.yml`) runs the unit, integration and golden tests and the
  demo batch in six jobs: Ubuntu and Windows, each with Python 3.11, 3.12 and 3.13.
- Locally, the suite has been run on Windows with Python 3.11.9; Python 3.12 and 3.13 run in CI only, and macOS
  has not been tested.
- The visual demo was checked by rendering it in headless Chrome (desktop light and dark, and a 390 px
  phone viewport). There are no automated browser tests.
