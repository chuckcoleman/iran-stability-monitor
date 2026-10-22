"""Publisher heading-date extraction with no fabricated first-publication time."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_metadata import parse_metadata, visible_publisher_dates

TREASURY = """
<html><head><title>Operation Economic Outcast | US Treasury</title></head>
<body>
<nav><span class="date">October 10, 2026</span></nav>
<main><article>
<h1>Operation Economic Outcast Targets Financial Networks</h1>
<div class="field field--name-field-news-publication-date">
 <div>October 15, 2026</div>
</div>
<div class="body">Today, OFAC designates seven named employees.</div>
</article></main>
<footer><div class="published">October 25, 2026</div></footer>
</body></html>
"""


class PublisherDateTests(unittest.TestCase):
    def test_treasury_heading_date_captured_without_first_publication_clock(self):
        metadata = parse_metadata(TREASURY)
        self.assertEqual(metadata["publication_dates"], ["2026-10-15"])
        self.assertIsNone(metadata["source_publication_time"])
        self.assertEqual(len(metadata["publisher_date_evidence"]), 1)
        witness = metadata["publisher_date_evidence"][0]
        self.assertEqual(witness["date"], "2026-10-15")
        self.assertEqual(witness["method"], "article_visible_date")
        self.assertIn("October 15, 2026", witness["publisher_visible_excerpt"])
        self.assertIn("publisher-reported article date", metadata["metadata_status"])

    def test_no_date_in_navigational_unmarked_text(self):
        page = """<nav><time datetime="2026-10-21">21 Oct 2026</time></nav>
<main><article><h1>Regional news roundup</h1>
<p>The words October 10, 2026 appear in unrelated body text.</p>
</article></main>"""
        self.assertEqual(parse_metadata(page)["publication_dates"], [])
        self.assertNotIn("publisher_date_evidence", parse_metadata(page))

    def test_timezone_aware_time_preserves_true_precision(self):
        page = """<main><article><h1>Case</h1>
<time datetime="2026-10-18T19:36:32+00:00">October 18, 2026</time>
</article></main><meta property="article:published_time"
 content="2026-10-18T19:36:32+00:00">"""
        meta = parse_metadata(page)
        self.assertIn("2026-10-18", meta["publication_dates"])
        self.assertEqual(meta["source_publication_time"],
                         "2026-10-18T19:36:32+00:00")
        self.assertTrue(meta.get("publisher_date_evidence"))

    def test_conflicting_and_postdated_visible_dates_are_retained_not_chosen(self):
        page = """<main><article>
<span class="publication-date">October 15, 2026</span>
<span class="published">October 22, 2026</span>
</article></main>"""
        meta = parse_metadata(page)
        self.assertEqual(meta["publication_dates"],
                         ["2026-10-15", "2026-10-22"])
        self.assertIsNone(meta["source_publication_time"])
        self.assertEqual(len(meta["publisher_date_evidence"]), 2)

    def test_no_global_page_date_guessing(self):
        page = """<html><head><title>News October 15, 2026</title></head>
<body><main><article><h1>Oct 21 Update</h1>
<p>Oct 15, 2026 is an event date, not the publication date.</p>
</article></main></body></html>"""
        self.assertNotIn("publisher_date_evidence", parse_metadata(page))
        self.assertEqual(parse_metadata(page)["publication_dates"], [])

    def test_invalid_heading_date_is_not_a_publication_candidate(self):
        page = """<main><article><span class="date">February 31, 2026</span>
</article></main>"""
        self.assertEqual(visible_publisher_dates(page), [])


if __name__ == "__main__":
    unittest.main()
