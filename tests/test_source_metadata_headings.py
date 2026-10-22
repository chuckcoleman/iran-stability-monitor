"""Conservative publisher article-date provenance (offline, no HTTP)."""
import datetime as dt
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from source_metadata import parse_metadata
from source_pre_review_admissibility import _publisher_time_status
from source_quality_audit import source_quality_audit

TREASURY_HEADING = """<!doctype html><html><head><title>U.S. Treasury - news</title>
<meta name="description" content="The press office announced an action.">
</head><body>
<nav><span>Recent releases</span><span>October 25, 2026</span></nav>
<main><article>
<h1>Operation Economic Outcast Targets Iran's International Financial Networks</h1>
<div class="article-date"><span>October 15, 2026</span></div>
<div class="subhead">Treasury action disrupts some bank networks</div>
<p>WASHINGTON -- Seven employees were designated in today's policy announcement.</p>
<p>Other sanctions announced in August 2026 are discussed only as background.</p>
</article></main>
<footer>Last updated October 26, 2026</footer>
</body></html>"""


class ArticleHeadingDateTests(unittest.TestCase):
    def test_treasury_style_h1_date_is_accepted_only_as_publisher_date(self):
        record = parse_metadata(TREASURY_HEADING)
        self.assertEqual(record["publication_dates"], ["2026-10-15"])
        self.assertIsNone(record["source_publication_time"])
        self.assertEqual(record["publisher_heading_admitted_day"], "2026-10-15")
        self.assertEqual(record["publisher_heading_date_status"],
                         "publisher_reported_heading_date_not_first_publication_proof")
        self.assertEqual(len(record["publisher_heading_date_evidence"]), 1)
        witness = record["publisher_heading_date_evidence"][0]
        self.assertEqual(witness["raw"], "October 15, 2026")
        self.assertEqual(witness["date"], "2026-10-15")
        self.assertEqual(witness["location"], "adjacent_to_first_article_h1")
        cutoff = dt.datetime.fromisoformat("2026-10-21T17:55:46-04:00")
        self.assertEqual(
            _publisher_time_status({
                "source_publication_time": None,
                "publication_dates_from_page": record["publication_dates"]
            }, cutoff),
            "PUBLISHER_PRIOR_DATE_NOT_FIRST_PUBLICATION_PROOF")

    def test_heading_date_witness_survives_in_source_quality_record(self):
        metadata = parse_metadata(TREASURY_HEADING)
        metadata["retrieval_status"] = "retrieved"
        metadata["metadata_status"] = "publisher heading recorded"
        url = "https://home.treasury.gov/news/press-releases/sb0660"
        result = {
            "evidence": [{
                "source": url, "evidence_status": "new",
                "direction": "ambiguous"}],
            "coverage_audit": [{
                "category": "primary_data", "original_urls": [url]}],
            "source_quality": [{
                "url": url, "kind": "direct_observation",
                "origin": "official_or_advocacy_claim",
                "corroborating_urls": [],
                "assessment": "This first-party policy announcement records an attributed government decision.",
                "limitations": "A source heading date does not certify the first public release or the directional effect."
            }],
        }
        quality = source_quality_audit(result, {url: metadata})
        row = quality["sources"][0]
        self.assertEqual(row["publication_dates_from_page"], ["2026-10-15"])
        self.assertEqual(row["publisher_heading_date_evidence"],
                         metadata["publisher_heading_date_evidence"])
        self.assertEqual(row["publisher_heading_admitted_day"], "2026-10-15")
        self.assertIn("precise_first_publication_time_unverified", row["flags"])
        self.assertEqual(row["factual_verification"],
                         "not_automatically_established")

    def test_site_navigation_footer_and_script_dates_never_count(self):
        page = """<html><body><nav>October 17, 2026</nav>
        <h1>Example article heading</h1>
        <script>October 17, 2026</script>
        <p>Government spokespeople said the event happened October 17.</p>
        <footer>October 18, 2026</footer></body></html>"""
        metadata = parse_metadata(page)
        self.assertEqual(metadata["publication_dates"], [])
        self.assertEqual(metadata["publisher_heading_date_evidence"], [])
        self.assertIsNone(metadata["publisher_heading_admitted_day"])

    def test_labeled_publish_date_and_first_adjacent_time_element(self):
        page = """<html><body><h1>Policy notice headline</h1>
        <time class="published" datetime="2026-10-15">Published 15 Oct</time>
        <div>Published: October 15, 2026</div>
        <p>Original agency announcement.</p></body></html>"""
        row = parse_metadata(page)
        self.assertEqual(row["publication_dates"], ["2026-10-15"])
        self.assertEqual(len(row["publisher_heading_date_evidence"]), 2)
        self.assertIsNone(row["source_publication_time"])

    def test_updated_only_is_not_first_publication_provenance(self):
        page = """<html><body><h1>Article</h1>
        <div>Last updated October 15, 2026</div>
        <p>The report discusses another event.</p></body></html>"""
        record = parse_metadata(page)
        self.assertEqual(record["publication_dates"], [])

    def test_conflicting_heading_labels_fail_closed_not_pick_first(self):
        page = """<html><body><h1>Article</h1>
        <div>Published: October 15, 2026</div>
        <div>Published: October 16, 2026</div>
        <p>A factual statement here.</p></body></html>"""
        record = parse_metadata(page)
        self.assertEqual(len(record["publisher_heading_date_evidence"]), 2)
        self.assertEqual(record["publication_dates"], [])
        self.assertIsNone(record["publisher_heading_admitted_day"])
        self.assertEqual(record["publisher_heading_date_status"],
                         "conflicting_heading_dates_not_admitted")

    def test_existing_machine_readable_precise_timestamp_preserved(self):
        page = """<html><head>
        <meta property="article:published_time"
        content="2026-10-15T11:20:00-04:00">
        <script type="application/ld+json">
        {"@type":"NewsArticle","datePublished":"2026-10-15T11:20:00-04:00",
         "dateModified":"2026-10-25T14:00:00-04:00"}
        </script></head><body>
        <h1>Original policy headline</h1><div>October 15, 2026</div>
        <p>This is the official announcement.</p></body></html>"""
        row = parse_metadata(page)
        self.assertEqual(row["source_publication_time"],
                         "2026-10-15T15:20:00+00:00")
        self.assertEqual(row["publication_dates"], ["2026-10-15"])
        self.assertNotIn("2026-10-25", row["publication_dates"])

    def test_publisher_same_day_without_time_remains_blocked(self):
        row = parse_metadata(
            "<h1>Article</h1><div>October 21, 2026</div>")
        status = _publisher_time_status({
            "source_publication_time": None,
            "publication_dates_from_page": row["publication_dates"]
        }, dt.datetime.fromisoformat("2026-10-21T12:00:00-04:00"))
        self.assertEqual(status, "SAME_DAY_PUBLISHER_DATE_NO_PRE_CUTOFF_TIME")

    def test_headline_date_disagreeing_with_precise_time_does_not_replace(self):
        page = """<html><head><meta property="article:published_time"
        content="2026-10-15T12:00:00Z"></head>
        <body><h1>Article</h1><div>October 16, 2026</div></body></html>"""
        row = parse_metadata(page)
        self.assertEqual(row["publication_dates"], ["2026-10-15"])
        self.assertIsNone(row["publisher_heading_admitted_day"])


if __name__ == "__main__":
    unittest.main()
