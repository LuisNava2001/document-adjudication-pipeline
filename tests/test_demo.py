"""The static demo viewer: its data matches the pipeline and the page stays self-contained."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest

from support import REPO_ROOT, SAMPLES_DIR

DEMO_DIR = REPO_ROOT / "demo"
PREFIX = "window.ADJUDICATION_DEMO = "


def load_builder():
    spec = importlib.util.spec_from_file_location("build_demo_data", REPO_ROOT / "scripts" / "build_demo_data.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def committed_data_text() -> str:
    return (DEMO_DIR / "data.js").read_text(encoding="utf-8").replace("\r\n", "\n")


def parse_data(text: str) -> dict:
    start = text.index(PREFIX) + len(PREFIX)
    return json.loads(text[start:].rstrip().rstrip(";"))


class DemoDataTest(unittest.TestCase):
    def test_committed_data_matches_a_fresh_build(self):
        fresh = load_builder().build(
            SAMPLES_DIR / "claims",
            SAMPLES_DIR / "documents",
            SAMPLES_DIR / "extractions",
            SAMPLES_DIR / "expected_outcomes.json",
        )
        self.assertEqual(fresh, committed_data_text(), "demo/data.js drifted; run: python scripts/build_demo_data.py")

    def test_every_sample_appears_with_its_expected_outcome(self):
        data = parse_data(committed_data_text())
        expected = json.loads((SAMPLES_DIR / "expected_outcomes.json").read_text(encoding="utf-8"))["outcomes"]
        self.assertEqual({case["key"] + ".json" for case in data["cases"]}, set(expected))
        for case in data["cases"]:
            result, wanted = case["result"], expected[case["key"] + ".json"]
            with self.subTest(case=case["key"]):
                self.assertEqual(result["status"], wanted["status"])
                self.assertEqual(result["decision"]["outcome"] if result["decision"] else None, wanted["decision"])

    def test_synthetic_document_text_is_embedded(self):
        data = parse_data(committed_data_text())
        case = next(c for c in data["cases"] if c["key"] == "CLM-1003")
        self.assertIn("SYNTHETIC DEMO DOCUMENT", case["documents"]["DOC-1003-A"])
        self.assertEqual(len(data["rules"]), 14)


class DemoPageTest(unittest.TestCase):
    def test_page_loads_only_local_files(self):
        for name in ("index.html", "app.js", "styles.css"):
            with self.subTest(file=name):
                self.assertNotRegex((DEMO_DIR / name).read_text(encoding="utf-8"), r"https?://|//cdn|@import")
        html = (DEMO_DIR / "index.html").read_text(encoding="utf-8")
        for reference in re.findall(r'(?:src|href)="([^"]+)"', html):
            self.assertTrue((DEMO_DIR / reference).is_file(), reference)

    def test_viewer_never_parses_data_as_html(self):
        script = (DEMO_DIR / "app.js").read_text(encoding="utf-8")
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            self.assertNotIn(forbidden, script)


if __name__ == "__main__":
    unittest.main()
