"""Golden tests over the committed synthetic sample set."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from adjudication.bootstrap import build_local_pipeline
from adjudication.serialization import to_jsonable
from support import REPO_ROOT, SAMPLES_DIR

CLAIMS_DIR = SAMPLES_DIR / "claims"
EXPECTED = json.loads((SAMPLES_DIR / "expected_outcomes.json").read_text(encoding="utf-8"))["outcomes"]


def run_batch():
    pipeline = build_local_pipeline(
        documents_dir=SAMPLES_DIR / "documents",
        extractions_dir=SAMPLES_DIR / "extractions",
        deterministic=True,
    )
    return {path.name: pipeline.process_raw(path.read_bytes(), source=path.name) for path in sorted(CLAIMS_DIR.glob("*.json"))}


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_samples", REPO_ROOT / "scripts" / "generate_samples.py")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves string annotations through sys.modules, so register before executing.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GoldenOutcomesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_batch()

    def test_every_claim_has_an_expected_outcome(self):
        self.assertEqual(set(self.results), set(EXPECTED))

    def test_outcomes_match_expectations(self):
        for name, expected in EXPECTED.items():
            with self.subTest(claim=name, scenario=expected["scenario"]):
                result = self.results[name]
                self.assertEqual(result.status, expected["status"])
                actual_decision = result.decision.outcome if result.decision else None
                self.assertEqual(actual_decision, expected["decision"])
                actual_reasons = sorted({r.rule_id for r in result.decision.reasons}) if result.decision else []
                self.assertEqual(actual_reasons, expected["reason_rules"])

    def test_deterministic_runs_are_byte_identical(self):
        again = run_batch()
        for name in self.results:
            self.assertEqual(
                json.dumps(to_jsonable(self.results[name]), sort_keys=True),
                json.dumps(to_jsonable(again[name]), sort_keys=True),
                name,
            )


class SampleIntegrityTest(unittest.TestCase):
    def test_committed_samples_match_the_generator(self):
        generator = load_generator()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            generator.generate(out)
            generated = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
            committed = {p.relative_to(SAMPLES_DIR).as_posix() for p in SAMPLES_DIR.rglob("*") if p.is_file()}
            self.assertEqual(generated, committed, "run: python scripts/generate_samples.py")
            for relative in sorted(generated):
                fresh = (out / relative).read_bytes()
                stored = (SAMPLES_DIR / relative).read_bytes().replace(b"\r\n", b"\n")
                self.assertEqual(fresh, stored, f"{relative} drifted; run: python scripts/generate_samples.py")

    def test_every_document_is_marked_synthetic(self):
        for path in (SAMPLES_DIR / "documents").glob("*.txt"):
            self.assertIn("SYNTHETIC DEMO DOCUMENT", path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
