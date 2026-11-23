"""CLI behaviour: commands, exit codes and written artifacts."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from adjudication.cli import EXIT_FAILED, EXIT_INVALID_INPUT, EXIT_OK, EXIT_USAGE, main
from support import SAMPLES_DIR

DIRS = ["--documents-dir", str(SAMPLES_DIR / "documents"), "--extractions-dir", str(SAMPLES_DIR / "extractions")]


def run(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


def claim(name: str) -> str:
    return str(SAMPLES_DIR / "claims" / name)


class ProcessCommandTest(unittest.TestCase):
    def test_approved_claim(self):
        code, out, _ = run("process", claim("CLM-1001.json"), *DIRS, "--deterministic")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("Decision  : APPROVED", out)

    def test_rejected_claim_still_exits_zero_and_explains(self):
        code, out, _ = run("process", claim("CLM-1003.json"), *DIRS, "--verbose")
        self.assertEqual(code, EXIT_OK)
        self.assertIn("CON-003 [FAIL/REJECT]", out)
        self.assertIn("Rule results:", out)

    def test_json_output_is_complete(self):
        code, out, _ = run("process", claim("CLM-1009.json"), *DIRS, "--json")
        payload = json.loads(out)
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["decision"]["outcome"], "APPROVED")
        self.assertEqual(payload["extractions"][0]["attempts"], 2)

    def test_failed_processing_exit_code(self):
        self.assertEqual(run("process", claim("CLM-1010.json"), *DIRS)[0], EXIT_FAILED)

    def test_invalid_input_exit_code(self):
        self.assertEqual(run("process", claim("CLM-1015.json"), *DIRS)[0], EXIT_INVALID_INPUT)

    def test_missing_claim_file_is_a_usage_error(self):
        code, _, err = run("process", "does-not-exist.json", *DIRS)
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("claim file not found", err)

    def test_missing_documents_directory_is_a_usage_error(self):
        code, _, err = run("process", claim("CLM-1001.json"), "--documents-dir", "nowhere", "--extractions-dir", "nowhere")
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("documents directory not found", err)

    def test_invalid_policy_file_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.json"
            policy.write_text('{"policy_version": "x"}', encoding="utf-8")
            code, _, err = run("process", claim("CLM-1001.json"), *DIRS, "--policy", str(policy))
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("missing keys", err)

    def test_audit_log_is_written_as_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "audit.jsonl"
            run("process", claim("CLM-1001.json"), *DIRS, "--audit-log", str(log))
            events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[0]["event"], "RECEIVED")
        self.assertEqual(events[-1]["event"], "COMPLETED")


class BatchCommandTest(unittest.TestCase):
    def test_batch_writes_results_summary_and_audit_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            code, stdout, _ = run("batch", str(SAMPLES_DIR / "claims"), *DIRS, "--out", str(out), "--deterministic")
            summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            result_files = sorted(p.name for p in (out / "results").glob("*.json"))
            audit_lines = (out / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(summary["submissions"], 15)
        self.assertEqual(summary["by_status"], {"COMPLETED": 13, "FAILED": 1, "INVALID_INPUT": 1})
        self.assertEqual(summary["by_decision"], {"APPROVED": 3, "MANUAL_REVIEW": 6, "REJECTED": 4})
        self.assertEqual(len(result_files), 15)
        self.assertEqual(len({json.loads(line)["trace_id"] for line in audit_lines}), 15)
        self.assertIn("CLM-1014.json", stdout)

    def test_batch_on_empty_directory_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run("batch", tmp, *DIRS)
        self.assertEqual(code, EXIT_USAGE)
        self.assertIn("no *.json claim files", err)


class RulesCommandTest(unittest.TestCase):
    def test_lists_all_rules(self):
        code, out, _ = run("rules")
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(len(out.strip().splitlines()), 14)
        self.assertTrue(out.startswith("DOC-001"))


if __name__ == "__main__":
    unittest.main()
