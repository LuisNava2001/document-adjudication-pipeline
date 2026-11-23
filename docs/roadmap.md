# Limitations and roadmap

## Limitations

- **No real OCR or document analysis.** Extraction results are pre-recorded fixtures for synthetic
  documents. The extraction port exists; no adapter for a real service does.
- **Single process, in-memory state.** The fingerprint store lives for one pipeline instance, so cross-claim
  duplicate detection depends on processing order within a run (`CLM-1014` is approved if processed alone).
- **Retries are immediate and in-process.** There is no backoff, dead-letter handling or queue.
- **No currency conversion.** A receipt in a different currency than the claim goes to manual review.
- **Illustrative rules.** The rules and limits model a fictional domain; they are not a real expense policy.
- **No authentication or multi-user access.** It is a local command-line tool with a static viewer.
- **Results are files.** No database and no concurrency control.
- **Verified environment.** Tests have been run locally on Windows with Python 3.11 only; the CI workflow has
  not run yet. The visual demo has no automated browser tests.

## Roadmap

None of the following is implemented. The ports described in [architecture.md](architecture.md) are the
intended integration points. Any cloud integration would be optional and disabled by default, so the offline
demo keeps working without credentials.

1. **Durable local state.** SQLite adapters for the fingerprint store and the audit trail, and an idempotency
   key derived from the input digest.
2. **Reliability patterns.** A transactional outbox for decisions, optimistic concurrency control, and retries
   with backoff plus a dead-letter path.
3. **Cloud adapters.** A `DocumentExtractor` backed by Azure AI Document Intelligence, Azure Functions
   triggers (HTTP and Storage Queue), and a Cosmos DB store for results and audit events.
4. **LLM-assisted review.** An Azure OpenAI advisor for `MANUAL_REVIEW` cases that drafts an explanation for
   the human reviewer and never overrides the deterministic decision.
5. **Observability.** Extending the static viewer into a dashboard over persisted results and audit trails.
6. **Decision evaluation.** Sealed evaluation datasets with a held-out split, label isolation and degenerate
   baselines, to measure decision quality before changing rules.
