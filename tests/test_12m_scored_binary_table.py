"""12-month scored binary dashboard table must show all three frozen core events.

The legacy binary_political field remains archived unchanged. All rendered
probabilities originate from the scored Protocol v1 forecast objects.
"""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "assets" / "app.js"
INDEX = ROOT / "index.html"
HISTORY = ROOT / "data" / "history.json"
IDS = ("regime_end_12m", "currency_crisis_12m", "external_payments_crisis_12m")


class TwelveMonthBinaryTableTests(unittest.TestCase):
    @staticmethod
    def data():
        return json.loads(HISTORY.read_text(encoding="utf-8"))

    @staticmethod
    def run_js(cases):
        source = APP.read_text(encoding="utf-8")
        marker = " fetch('data/history.json')"
        assert source.count(marker) == 1
        prefix = source.split(marker, 1)[0]
        code = (
            prefix + "\n"
            + "const cases=" + json.dumps(cases) + ";\n"
            + "console.log(JSON.stringify(cases.map(c=>{"
            + "try{return {rows:scored12MonthBinaryRows(c.update,c.protocol)}}"
            + "catch(e){return {error:e.message}}})));\n"
        )
        return subprocess.run(
            ["node", "-e", code], cwd=ROOT, capture_output=True,
            text=True, timeout=20, check=False,
        )

    def test_public_heading_and_core_source(self):
        html = INDEX.read_text(encoding="utf-8")
        source = APP.read_text(encoding="utf-8")
        self.assertIn("<h3>12-month scored binary forecasts</h3>", html)
        self.assertIn("scored12MonthBinaryRows(x,d.protocol)", source)
        self.assertNotIn("Scored binary political forecasts", source)
        self.assertNotIn("x.binary_political||[]", source)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for JS presentation regression")
    def test_exact_three_scored_forecasts_using_current_or_future_append(self):
        data = self.data()
        update = data["updates"][-1]
        records = update["forecasts"]
        self.assertEqual(tuple(r["event_id"] for r in records if
                               r["scored"] is True and r["event_id"] in IDS), IDS)
        result = self.run_js([{"update": update, "protocol": data["protocol"]}])
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(result.stdout)[0]
        self.assertNotIn("error", actual)
        rows = actual["rows"]
        self.assertEqual(len(rows), 3)
        expected_by_id = {r["event_id"]: r for r in records}
        rule_by_id = {r["id"]: r for r in data["protocol"]["core_scored_set"]}
        for i, event_id in enumerate(IDS):
            self.assertEqual(rows[i], [
                rule_by_id[event_id]["event"],
                str(expected_by_id[event_id]["p"]) + "%",
                "Scored",
            ])
        self.assertNotIn("fx_crisis_12m", json.dumps(rows))
        self.assertNotIn("Hanke", json.dumps(rows))

    @unittest.skipUnless(shutil.which("node"), "Node.js required for JS presentation regression")
    def test_missing_duplicate_noncore_or_bad_probability_fails_closed(self):
        data = self.data()
        record = data["updates"][-1]
        base = record["forecasts"]
        protocol = data["protocol"]
        import copy
        missing = {**record, "forecasts": [f for f in base if f["event_id"] != IDS[1]]}
        duplicate = {**record, "forecasts": base + [copy.deepcopy(next(f for f in base if f["event_id"] == IDS[2]))]}
        unscored = copy.deepcopy(record)
        next(f for f in unscored["forecasts"] if f["event_id"] == IDS[1])["scored"] = False
        out_of_range = copy.deepcopy(record)
        next(f for f in out_of_range["forecasts"] if f["event_id"] == IDS[1])["p"] = 101
        extra = copy.deepcopy(protocol)
        extra["core_scored_set"].append({"event": "Unscored extra", "id": "extra_12m", "horizon_days": 365})
        cases = [
            {"update": missing, "protocol": protocol},
            {"update": duplicate, "protocol": protocol},
            {"update": unscored, "protocol": protocol},
            {"update": out_of_range, "protocol": protocol},
            {"update": record, "protocol": extra},
        ]
        result = self.run_js(cases)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertTrue(all("error" in r for r in rows), rows)

    def test_history_remains_legacy_compatible(self):
        data = self.data()
        november_15 = next(r for r in data["updates"] if r["date"] == "2026-11-15")
        self.assertEqual(len(november_15["binary_political"]), 1)
        self.assertEqual(november_15["binary_political"][0]["event_id"], IDS[0])
        self.assertEqual({f["event_id"] for f in november_15["forecasts"]
                          if f["scored"] is True},
                         {"regional_escalation_90d", *IDS})


if __name__ == "__main__":
    unittest.main()
