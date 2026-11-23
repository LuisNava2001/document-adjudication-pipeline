"""Command-line entry point.

Exit codes: 0 processing completed (whatever the decision), 1 processing failed
on a retryable dependency, 2 usage or configuration error, 3 invalid input.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from adjudication import __version__
from adjudication.adapters.audit_sinks import InMemoryAuditSink, JsonlAuditSink
from adjudication.bootstrap import build_local_pipeline
from adjudication.core.pipeline import AdjudicationPipeline
from adjudication.core.rules import default_rules
from adjudication.domain.models import ProcessingResult, ProcessingStatus
from adjudication.domain.policy import PolicyError, load_policy
from adjudication.ports import AuditSink
from adjudication.reporting import render_batch, render_result
from adjudication.serialization import to_jsonable

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_INVALID_INPUT = 3

_STATUS_EXIT = {
    ProcessingStatus.COMPLETED: EXIT_OK,
    ProcessingStatus.FAILED: EXIT_FAILED,
    ProcessingStatus.INVALID_INPUT: EXIT_INVALID_INPUT,
}


class CliError(Exception):
    """A usage or configuration problem reported to the user without a traceback."""


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (CliError, PolicyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _cmd_process(args: argparse.Namespace) -> int:
    claim_path = Path(args.claim_file)
    if not claim_path.is_file():
        raise CliError(f"claim file not found: {args.claim_file}")
    sink = JsonlAuditSink(args.audit_log) if args.audit_log else InMemoryAuditSink()
    pipeline = _pipeline(args, sink)
    result = pipeline.process_raw(claim_path.read_bytes(), source=claim_path.name)
    if args.json:
        print(_to_json(result))
    else:
        print(render_result(result, verbose=args.verbose))
    return _STATUS_EXIT[result.status]


def _cmd_batch(args: argparse.Namespace) -> int:
    claims_dir = Path(args.claims_dir)
    if not claims_dir.is_dir():
        raise CliError(f"claims directory not found: {args.claims_dir}")
    claim_files = sorted(path for path in claims_dir.glob("*.json") if path.is_file())
    if not claim_files:
        raise CliError(f"no *.json claim files in {args.claims_dir}")
    out_dir = Path(args.out)
    results_dir = out_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    sink = JsonlAuditSink(out_dir / "audit.jsonl", truncate=True)
    pipeline = _pipeline(args, sink)

    results: list[ProcessingResult] = []
    for path in claim_files:
        result = pipeline.process_raw(path.read_bytes(), source=path.name)
        (results_dir / f"{path.stem}.json").write_text(_to_json(result) + "\n", encoding="utf-8", newline="\n")
        results.append(result)

    summary = _summary(results, pipeline)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(render_batch(results))
    print(f"\nWrote {len(results)} result file(s), summary.json and audit.jsonl to {out_dir}")
    return EXIT_OK


def _cmd_rules(args: argparse.Namespace) -> int:
    for rule in default_rules():
        print(f"{rule.rule_id:<9}{rule.severity:<8}{rule.title}")
    return EXIT_OK


def _pipeline(args: argparse.Namespace, sink: AuditSink) -> AdjudicationPipeline:
    for label, directory in (("documents", args.documents_dir), ("extractions", args.extractions_dir)):
        if not Path(directory).is_dir():
            raise CliError(f"{label} directory not found: {directory} (run from the repository root or pass --{label}-dir)")
    return build_local_pipeline(
        documents_dir=args.documents_dir,
        extractions_dir=args.extractions_dir,
        policy=load_policy(args.policy),
        audit_sink=sink,
        deterministic=args.deterministic,
        max_extraction_attempts=args.max_attempts,
    )


def _summary(results: Sequence[ProcessingResult], pipeline: AdjudicationPipeline) -> dict:
    return {
        "policy_version": pipeline.policy.version,
        "policy_digest": pipeline.policy.digest,
        "submissions": len(results),
        "by_status": dict(sorted(Counter(str(r.status) for r in results).items())),
        "by_decision": dict(sorted(Counter(str(r.decision.outcome) for r in results if r.decision).items())),
        "results": [
            {
                "source": r.source,
                "claim_id": r.claim_id,
                "trace_id": r.trace_id,
                "status": str(r.status),
                "decision": str(r.decision.outcome) if r.decision else None,
                "reason_rules": sorted({reason.rule_id for reason in r.decision.reasons}) if r.decision else [],
            }
            for r in results
        ],
    }


def _to_json(result: ProcessingResult) -> str:
    return json.dumps(to_jsonable(result), indent=2)


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--documents-dir", default="samples/documents", help="synthetic source documents (default: %(default)s)")
    common.add_argument("--extractions-dir", default="samples/extractions", help="recorded extraction results (default: %(default)s)")
    common.add_argument("--policy", default=None, help="policy JSON file (default: bundled demo policy)")
    common.add_argument("--deterministic", action="store_true", help="fixed clock and sequential trace ids for reproducible output")
    common.add_argument("--max-attempts", type=_positive_int, default=3, help="extraction attempts for retryable failures (default: %(default)s)")

    parser = argparse.ArgumentParser(
        prog="adjudication",
        description="Adjudicate synthetic reimbursement claims: extraction -> validation -> decision -> audit trace.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    process = commands.add_parser("process", parents=[common], help="adjudicate one claim file")
    process.add_argument("claim_file", help="path to a claim JSON file")
    process.add_argument("--json", action="store_true", help="print the full result as JSON")
    process.add_argument("--verbose", action="store_true", help="list every rule result")
    process.add_argument("--audit-log", help="append audit events to this JSONL file")
    process.set_defaults(handler=_cmd_process)

    batch = commands.add_parser("batch", parents=[common], help="adjudicate every *.json claim in a directory, in name order")
    batch.add_argument("claims_dir", help="directory of claim JSON files")
    batch.add_argument("--out", default="demo-output", help="output directory; existing result files are overwritten (default: %(default)s)")
    batch.set_defaults(handler=_cmd_batch)

    rules = commands.add_parser("rules", help="list the validation rules")
    rules.set_defaults(handler=_cmd_rules)
    return parser
