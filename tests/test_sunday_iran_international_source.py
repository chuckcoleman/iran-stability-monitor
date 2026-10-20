"""Offline checks for the prospective Iran International Sunday source scan.

This tests research guidance, not the truth of any external article and not a
requirement to force an Iran International item into the published ledger.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from assessment_pipeline import RESEARCH
from source_metadata import url_key


class SundayIranInternationalWatchTests(unittest.TestCase):
    def test_english_latest_feed_is_explicitly_scanned(self):
        self.assertIn("Every Sunday, also search ORIGINAL Iran International", RESEARCH)
        self.assertIn("https://www.iranintl.com/en/latest", RESEARCH)
        self.assertIn("site:iranintl.com", RESEARCH)
        self.assertIn("security-force loyalty/defections", RESEARCH)
        self.assertIn("rial/market stress", RESEARCH)

    def test_source_is_a_candidate_not_a_mandatory_citation(self):
        self.assertIn("not a\nrequired citation", RESEARCH)
        self.assertIn("Independently corroborate", RESEARCH)
        self.assertIn("unverified allegations", RESEARCH)
        self.assertIn("do not invent coverage", RESEARCH)

    def test_prompt_formats_without_interfering_with_prospective_stage(self):
        formatted = RESEARCH.format(date="2026-10-25", prior="[]")
        self.assertIn("2026-10-25", formatted)
        self.assertIn("Prior evidence for persistent carried-forward IDs: [].", formatted)
        self.assertIn("No forecasts in this first stage", formatted)

    def test_original_iran_international_links_are_valid_eligible_https_urls(self):
        self.assertEqual(url_key("https://www.iranintl.com/en/latest"),
                         "https://www.iranintl.com/en/latest")
        self.assertEqual(url_key("https://www.iranintl.com/en"),
                         "https://www.iranintl.com/en")

    def test_prospective_watchlist_requires_provenance_and_no_backfill(self):
        policy = (ROOT / "SOURCE_WATCHLIST.md").read_text(encoding="utf-8")
        self.assertIn("effective 2026-10-25", policy)
        self.assertIn("before the evidence cutoff", policy)
        self.assertIn("original publisher", policy)
        self.assertIn("independent original reporting", policy)
        self.assertIn("no eligible new evidence", policy)
        self.assertIn("Do not rewrite earlier forecasts", policy)


if __name__ == "__main__":
    unittest.main()
