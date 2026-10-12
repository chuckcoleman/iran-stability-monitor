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
    def test_heading_is_a_complete_question(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("<strong>What should we watch next?</strong>", source)
        self.assertNotIn("<strong>Next threshold</strong>", source)
        self.assertIn("nextThresholdSentences(x.next_threshold)", source)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for JavaScript presentation test")
    def test_historical_fragments_display_as_grammatical_sentences(self):
        source = APP.read_text(encoding="utf-8")
        marker = "fetch('data/history.json')"
        self.assertEqual(source.count(marker), 1)
        # Execute only the pure helpers that precede the site's fetch(), not
        # the DOM or network code. No historical JSON is written.
        helpers = source.split(marker, 1)[0]
        scenarios = [
            "Whether an allocation fails for fourteen days.",
            "Whether escalation persists for 72 hours; whether payment settlement fails for 14 days; whether the rial falls 25% in 30 days.",
            "We are monitoring whether an allocation fails for fourteen days.",
            "",
        ]
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
        self.assertEqual(actual, [
            "We are watching whether an allocation fails for fourteen days.",
            "We are watching whether escalation persists for 72 hours. We are also watching whether payment settlement fails for 14 days. We are also watching whether the rial falls 25% in 30 days.",
            scenarios[2],
            "—",
        ])

    def test_historical_records_are_still_raw_unmodified_prose(self):
        records = json.loads(HISTORY.read_text(encoding="utf-8"))["updates"]
        self.assertTrue(records[-1]["next_threshold"].startswith("Whether "))
        self.assertIn("; whether ", records[-1]["next_threshold"])


if __name__ == "__main__":
    unittest.main()
