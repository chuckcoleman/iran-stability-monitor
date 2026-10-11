"""No-network tests for safe Metricool announcement and deduplication."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
import metricool_publish as x

class MetricoolPublishTests(unittest.TestCase):
    def setUp(self):
        self.history=json.loads((ROOT/"data/history.json").read_text())

    def test_post_text_contains_date_prior_and_canonical(self):
        t=x.draft_text(self.history)
        self.assertLessEqual(len(t),280)
        self.assertIn("2026-10-11",t)
        self.assertIn("73% (prior Sunday 56%)",t)
        self.assertIn("16% (prior 14%)",t)
        self.assertIn("https://iranstabilitymonitor.org",t)
        self.assertNotIn("iranstabilitymonitor.com",t)

    def test_calendar_handles_published_or_scheduled(self):
        existing=[{"text":"Iran Stability Monitor — 2026-10-11: https://iranstabilitymonitor.org",
                   "providers":[{"network":"twitter","status":"PUBLISHED"}]}]
        with patch.object(x,"metricool",return_value={"data":existing}):
            self.assertTrue(x.existing_post("2026-10-11"))
        with patch.object(x,"metricool",return_value={"data":[]}):
            self.assertFalse(x.existing_post("2026-10-11"))
        with patch.object(x,"metricool",return_value={"unexpected":"shape"}):
            with self.assertRaisesRegex(RuntimeError,"Cannot inspect"):
                x.existing_post("2026-10-11")

    def test_persistent_claim_prevents_second_post(self):
        label=x.ledger_title("2026-10-11")
        with patch.object(x,"github",return_value=[{"title":label}]) as call:
            self.assertFalse(x.claim("2026-10-11"))
            self.assertEqual(call.call_count,1)

    def test_claim_written_before_nonidempotent_post(self):
        seen=[]
        def fake_github(relative,method="GET",data=None):
            seen.append((relative,method))
            if relative.startswith("issues?"):return []
            self.assertEqual(method,"POST")
            self.assertEqual(data["title"],x.ledger_title("2026-10-11"))
            return {"number":25}
        with patch.object(x,"github",side_effect=fake_github):
            self.assertTrue(x.claim("2026-10-11"))
        self.assertEqual([p[1] for p in seen],["GET","POST"])

if __name__=="__main__":
    unittest.main()
