"""Presentation-copy regression tests. No network, forecasts, or file mutations."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "assets" / "app.js"
HISTORY = ROOT / "data" / "history.json"


class NextThresholdCopyTests(unittest.TestCase):
    def test_heading_is_plural_and_nonconversational(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("<strong>Thresholds to watch</strong>", source)
        self.assertNotIn("<strong>What should we watch next?</strong>", source)
        self.assertNotIn("We are watching whether", source)
        self.assertIn("nextThresholdSentences(x.next_threshold).map(sentence=>", source)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for JavaScript presentation test")
    def test_each_archived_event_is_one_simple_declarative_sentence(self):
        source = APP.read_text(encoding="utf-8")
        marker = "fetch('data/history.json')"
        self.assertEqual(source.count(marker), 1)
        helpers = source.split(marker, 1)[0]
        records = json.loads(HISTORY.read_text(encoding="utf-8"))["updates"]
        historical = [r["next_threshold"] for r in records if r.get("next_threshold")]
        self.assertEqual(len(historical), 3)
        future = "Sustained interstate strikes would raise escalation risk. A currency shock could follow."
        scenarios = historical + [future, "", "U.S. officials may intervene. Currency stress may increase."]
        js = (
            helpers + "\n"
            + "const cases = " + json.dumps(scenarios) + ";\n"
            + "console.log(JSON.stringify(cases.map(nextThresholdSentences)));\n"
        )
        result = subprocess.run(
            ["node", "-e", js], cwd=ROOT,
            capture_output=True, text=True, timeout=20, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(result.stdout.strip())
        self.assertEqual(actual[0], [
            "Economic and energy stress could disrupt priority state allocations.",
            "Economic and energy stress could disrupt compensation for security personnel."
        ])
        self.assertEqual(actual[1], [
            "Major interstate strikes connected to Yemen could meet the escalation threshold if they lasted 72 hours.",
            "A sustained 25% fall in the parallel-market rial over 30 days would meet the currency-crisis threshold."
        ])
        self.assertEqual(actual[2], [
            "Major interstate strikes lasting 72 hours would meet the regional-escalation duration threshold.",
            "Settlement failures lasting 14 days in two essential-import categories would signal a possible external-payments crisis.",
            "A sustained 25% fall in the parallel-market rial over 30 days would meet the currency-crisis threshold."
        ])
        self.assertEqual(actual[3], [
            "Sustained interstate strikes would raise escalation risk.",
            "A currency shock could follow."
        ])
        self.assertEqual(actual[4], ["—"])
        self.assertEqual(actual[5], [
            "U.S. officials may intervene.", "Currency stress may increase."
        ])
        for group in actual[:-2]:
            for sentence in group:
                self.assertTrue(sentence.endswith("."))
                self.assertFalse(sentence.startswith("Whether "))
                self.assertNotIn("We are watching", sentence)
                self.assertNotIn(";", sentence)

    def test_historical_records_are_still_raw_unmodified_prose(self):
        records = json.loads(HISTORY.read_text(encoding="utf-8"))["updates"]
        self.assertTrue(records[-1]["next_threshold"].startswith("Whether "))
        self.assertIn("; whether ", records[-1]["next_threshold"])


if __name__ == "__main__":
    unittest.main()
