"""Regression: only frozen Protocol v1 event definitions appear in the public thresholds card."""
import json
from html import unescape
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "assets" / "app.js"
HISTORY = ROOT / "data" / "history.json"
EXPECTED_IDS = (
    "regional_escalation_90d",
    "regime_end_12m",
    "currency_crisis_12m",
    "external_payments_crisis_12m",
)


class ThresholdDefinitionsOnlyTests(unittest.TestCase):
    def test_dashboard_does_not_render_weekly_narrative(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("<strong>Thresholds to watch</strong>", source)
        self.assertIn("renderThresholdDefinitions(d.protocol)", source)
        self.assertNotIn("nextThresholdSentences", source)
        self.assertNotIn("archivedThresholdStatements", source)
        self.assertNotIn("nextThresholdSentences(x.next_threshold)", source)
        self.assertEqual(source.count("renderThresholdDefinitions(d.protocol)"), 1)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for JavaScript presentation test")
    def test_exact_four_frozen_definitions_and_no_editorial_prose(self):
        source = APP.read_text(encoding="utf-8")
        marker = " fetch('data/history.json')"
        self.assertEqual(source.count(marker), 1)
        helpers = source.split(marker, 1)[0]
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
        latest = data["updates"][-1]
        rules = data["protocol"]["core_scored_set"]
        self.assertEqual(tuple(r["id"] for r in rules), EXPECTED_IDS)
        self.assertIn("Continue documenting", latest["next_threshold"])
        test_cases = {
            "protocol": data["protocol"],
            "published_narrative": latest["next_threshold"],
        }
        js = (
            helpers + "\n"
            + "const fixture=" + json.dumps(test_cases) + ";\n"
            + "const html=renderThresholdDefinitions(fixture.protocol);\n"
            + "console.log(JSON.stringify({html, published_narrative:fixture.published_narrative}));\n"
        )
        result = subprocess.run(
            ["node", "-e", js], cwd=ROOT, capture_output=True,
            text=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        html = output["html"]
        visible_text = unescape(html)
        self.assertEqual(html.count("<p>"), 4)
        self.assertEqual(html.count("</p>"), 4)
        for rule in rules:
            self.assertIn(rule["event"], visible_text)
            self.assertIn(rule["resolution"], visible_text)
        self.assertNotIn("Continue documenting", html)
        self.assertNotIn("Lower upon", html)
        self.assertNotIn("Seek actual", html)
        self.assertNotIn("next_threshold", html)
        self.assertNotIn(output["published_narrative"], html)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for JavaScript presentation test")
    def test_malformed_or_fifth_definition_fails_closed(self):
        source = APP.read_text(encoding="utf-8")
        helpers = source.split(" fetch('data/history.json')", 1)[0]
        protocol = json.loads(HISTORY.read_text(encoding="utf-8"))["protocol"]
        js = (
            helpers + "\n"
            + "const p=" + json.dumps(protocol) + ";\n"
            + "const invalid=[{...p,core_scored_set:p.core_scored_set.slice(0,3)},"
            + "{...p,core_scored_set:[...p.core_scored_set,{id:'misc',event:'Research',resolution:'Seek studies.'}]},"
            + "{...p,core_scored_set:[...p.core_scored_set].reverse()},"
            + "{...p,core_scored_set:p.core_scored_set.map((r,i)=>i? r : {...r,resolution:''})}];\n"
            + "console.log(JSON.stringify(invalid.map(obj=>{"
            + "try{renderThresholdDefinitions(obj);return false}"
            + "catch(e){return true}})));\n"
        )
        result = subprocess.run(
            ["node", "-e", js], cwd=ROOT, capture_output=True,
            text=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [True] * 4)

    def test_immutable_historical_narrative_remains_in_ledger(self):
        records = json.loads(HISTORY.read_text(encoding="utf-8"))["updates"]
        archived = next(x for x in records if x["date"] == "2026-10-11")
        self.assertTrue(archived["next_threshold"].startswith("Whether "))
        self.assertIn("; whether ", archived["next_threshold"])
        self.assertIn("Seek actual Hanke", next(x for x in records if x["date"] == "2026-11-08")["next_threshold"])


if __name__ == "__main__":
    unittest.main()
