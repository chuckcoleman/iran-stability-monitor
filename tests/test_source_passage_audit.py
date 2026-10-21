"""No-network tests for claim-level original-page witnesses and audit integrity."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from source_passage_audit import (
    capture_claim_passage, build_claim_register, verify_register,
    visible_text,
)
from source_review_cycles import (
    conservative_revision, deterministic_review_issues,
)
from source_research_batches import sha
from source_review_resume import load_or_create_review_input

OBS = "The national maritime organization issued a warning to shipping companies."
URL = "https://example.org/iran/maritime-notice"
QUOTE = "The organization issued a warning to shipping companies."
PAGE = (
    "<html><head><title>Wrong metadata title</title>"
    "<script>const fake = 'The organization issued a warning to shipping companies.';</script>"
    "</head><body><nav>Home search</nav><article><p>The organization "
    "issued a warning to <em>shipping</em> companies.</p>"
    "<p>It described its concern as an official statement.</p></article>"
    "<footer>Cookie page content</footer></body></html>"
)
NOW = dt.datetime(2026, 10, 21, 17, 30, tzinfo=dt.timezone.utc)
AS_OF = "2026-10-21T12:30:00+00:00"


def get_html(url):
    return PAGE.encode(), url, "text/html", "utf-8"


def frozen():
    return [{
        "id": "E-20261021-01", "observation": OBS, "source": URL,
        "event_date": "2026-10-20", "category": "shipping",
        "publisher": "Example Organization", "direction": "ambiguous",
        "evidence_status": "new"
    }]


def research():
    return {"evidence": [{
        "source": URL, "event_date": "2026-10-20",
        "category": "shipping", "support_quote": QUOTE,
        "observation": OBS, "evidence_status": "new"
    }]}


def inspector(url, quote, *, observation, original_cutoff=None):
    return capture_claim_passage(
        url, quote, observation=observation, original_cutoff=original_cutoff,
        fetcher=get_html, now=lambda: NOW)


def source_quality():
    return {"status": "SOURCE_BY_SOURCE_REVIEW_REQUIRED",
            "sources": [{
                "url": URL, "origin": "official_or_advocacy_claim",
                "classification": "direct_observation",
                "metadata_status": "publisher-supplied metadata",
                "access_status": "source_metadata_captured",
                "new_evidence_indices": [0], "role": "new_evidence",
                "coverage_categories": ["primary_data"],
                "flags": [], "limitations": "Source is an official claim",
                "source_publication_time": None
            }],
            "source_count": 1, "evidence_source_count": 1,
            "context_only_source_count": 0}


class PassageWitnessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="claim-passages-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def test_exact_page_text_and_digest_but_not_semantic_approval(self):
        self.assertNotIn("Wrong metadata title", visible_text(PAGE.encode()))
        self.assertNotIn("const fake", visible_text(PAGE.encode()))
        self.assertIn(QUOTE, visible_text(PAGE.encode()))
        result = inspector(URL, QUOTE, observation=OBS, original_cutoff=AS_OF)
        self.assertEqual(result["status"],
                         "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED")
        self.assertEqual(result["passage"], QUOTE)
        self.assertEqual(result["retrieved_url"], URL)
        self.assertEqual(result["source_body_sha256"],
                         hashlib.sha256(PAGE.encode()).hexdigest())
        self.assertEqual(result["semantic_support"],
                         "NOT_INDEPENDENTLY_ESTABLISHED")
        self.assertFalse(result["first_publication_verified"])
        self.assertTrue(result["inspection_after_original_cutoff"])

    def test_metadata_only_or_no_quote_never_counts_as_source_witness(self):
        no_quote = capture_claim_passage(
            URL, None, observation=OBS,
            fetcher=lambda u: (
                b"<html><body><article><p>A page about gardening and flowers.</p>"
                b"</article></body></html>", u, "text/html", "utf-8"))
        self.assertEqual(no_quote["status"], "NO_RELEVANT_ORIGINAL_PASSAGE")
        independent = capture_claim_passage(
            URL, None, observation=OBS, fetcher=get_html, now=lambda: NOW)
        self.assertEqual(independent["status"],
                         "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED")
        self.assertEqual(independent["selection_method"],
                         "independent_keyword_candidate")
        self.assertIn("shipping", independent["passage"])
        self.assertEqual(independent["semantic_support"],
                         "NOT_INDEPENDENTLY_ESTABLISHED")
        bogus = capture_claim_passage(
            URL, "A made up statement from the website.",
            observation=OBS, fetcher=get_html)
        self.assertEqual(bogus["status"], "QUOTE_NOT_FOUND_IN_ORIGINAL")
        self.assertIsNone(bogus["passage"])
        navigation = capture_claim_passage(
            URL, "Home search in top navigation links", observation=OBS,
            fetcher=get_html)
        self.assertNotEqual(navigation["status"],
                            "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED")

    def test_redirect_and_unavailable_page_fail_closed(self):
        redirect = capture_claim_passage(
            URL, QUOTE, observation=OBS,
            fetcher=lambda u: (PAGE.encode(), "https://example.org/",
                               "text/html", "utf-8"))
        self.assertEqual(redirect["status"],
                         "REDIRECTED_TO_DIFFERENT_ORIGINAL")
        error = capture_claim_passage(
            URL, QUOTE, observation=OBS,
            fetcher=lambda u: (_ for _ in ()).throw(OSError("connection")))
        self.assertEqual(error["status"], "ORIGINAL_TEXT_UNAVAILABLE")
        pdf = capture_claim_passage(
            URL, QUOTE, observation=OBS,
            fetcher=lambda u: (b"%PDF", u, "application/pdf", "utf-8"))
        self.assertEqual(pdf["status"], "NOT_INSPECTABLE_HTML")

    def test_archive_claims_have_bound_identifiers_and_fingerprint(self):
        snapshot = {"snapshot_sha256": "a" * 64, "cutoff_at": AS_OF}
        register = build_claim_register(
            self.folder, research=research(), frozen=frozen(),
            baseline_sha="b"*64, snapshot=snapshot, inspector=inspector)
        self.assertEqual(register["evidence_sha256"], sha(frozen()))
        self.assertEqual(register["claims"][0]["evidence_id"],
                         "E-20261021-01")
        self.assertEqual(register["claims"][0]["status"],
                         "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED")
        self.assertTrue(verify_register(
            register, frozen(), snapshot_sha="a"*64, history_sha="b"*64))
        original = (self.folder/"claim-evidence-register.json").read_bytes()
        replay = build_claim_register(
            self.folder, research=research(), frozen=frozen(),
            baseline_sha="b"*64, snapshot=snapshot,
            inspector=lambda *x, **kw: self.fail("Network must not repeat"))
        self.assertEqual(replay, register)
        self.assertEqual((self.folder/"claim-evidence-register.json").read_bytes(),
                         original)
        modified = copy.deepcopy(frozen())
        modified[0]["observation"] = "A new unsupported observation"
        with self.assertRaisesRegex(ValueError, "evidence list changed"):
            verify_register(register, modified)
        bad = copy.deepcopy(register)
        bad["claims"][0]["first_publication_verified"] = True
        with self.assertRaisesRegex(ValueError, "promoted"):
            verify_register(bad, frozen())
        bad_clock = copy.deepcopy(register)
        bad_clock["claims"][0]["inspection_after_original_cutoff"] = False
        with self.assertRaisesRegex(ValueError, "contradicts"):
            verify_register(bad_clock, frozen(), original_cutoff=AS_OF)

    def test_new_review_input_binds_register_without_changing_legacy(self):
        snapshot = {"snapshot_sha256": "a"*64, "cutoff_at": AS_OF}
        callbacks = []
        def capture_claims(records):
            callbacks.append("captured")
            return build_claim_register(
                self.folder, research=research(), frozen=records,
                baseline_sha="b"*64, snapshot=snapshot, inspector=inspector)
        options = dict(
            result=research(), citations={URL},
            coverage=[{"category": "primary_data",
                       "original_urls": [URL],
                       "limitations": "Source search was limited.",
                       "outcome": "eligible_reporting_found"}],
            quality=source_quality(), baseline_sha="b"*64,
            snapshot=snapshot, archive={"evidence": []},
            date="2026-10-21", now=lambda: NOW,
            freeze=lambda *args: copy.deepcopy(frozen()),
            claim_register_builder=capture_claims)
        first, digest, _ = load_or_create_review_input(self.folder, **options)
        self.assertIn("claim_evidence_register", first)
        self.assertEqual(callbacks, ["captured"])
        second, _, _ = load_or_create_review_input(self.folder, **options)
        self.assertEqual(first, second)
        self.assertEqual(callbacks, ["captured"])
        record = json.loads((self.folder/"claim-evidence-register.json").read_text())
        record["claims"][0]["status"] = "INVALID_QUOTE_LENGTH_OR_CONTENT"
        (self.folder/"claim-evidence-register.json").write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "Missing/unmatched page|Saved review evidence differs"):
            load_or_create_review_input(self.folder, **options)

    def test_unsupported_claims_are_excluded_and_official_source_downgraded(self):
        selected = frozen()
        qualified = source_quality()
        no_quote = capture_claim_passage(
            URL, None, observation=OBS,
            fetcher=lambda u: (
                b"<html><p>Completely unrelated sports coverage.</p></html>",
                u, "text/html", "utf-8"))
        register = {
            "claims": [dict(no_quote, evidence_id=selected[0]["id"])],
            "status": "PASSAGES_ONLY_NOT_APPROVED"}
        packet = {
            "evidence": selected,
            "source_quality_audit": qualified,
            "claim_evidence_register": register,
            "coverage": [{
                "category": "primary_data",
                "original_urls": [URL],
                "outcome": "eligible_reporting_found",
                "limitations": "Synthetic incomplete coverage."
            }],
            "cutoff": NOW.isoformat()
        }
        issues = deterministic_review_issues(packet, AS_OF)
        self.assertTrue(any(x["type"] == "claim_passage_not_demonstrated"
                            for x in issues))
        self.assertTrue(any(x["type"] == "official_claim_misclassified"
                            for x in issues))
        revised, blocked = conservative_revision(
            packet, issues, AS_OF)
        # A quote-register diagnostic may checkpoint an empty provisional
        # version for both reviewers, but it remains deterministically blocked
        # from approval and never becomes a forecast-eligible source set.
        self.assertIsNotNone(revised)
        self.assertEqual(revised["evidence"], [])
        self.assertEqual(revised["source_diversity_guard"]["status"],
                         "BLOCKED_NOT_PUBLISHABLE")
        self.assertIn("fewer_than_six_source_observations",
                      revised["source_diversity_guard"]["failures"])
        self.assertEqual(len(blocked["excluded_evidence"]), 1)
        # With enough independently recorded publishers, correcting one
        # official classification cannot silently upgrade it to measured data.


if __name__ == "__main__":
    unittest.main()
