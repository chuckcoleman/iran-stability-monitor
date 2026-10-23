"""V8: complete source audit may be inconclusive, never forecast approval.

All examples are synthetic. No OpenAI, web-search, GitHub, forecast, or
publication request is made by this suite.
"""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import read_only_research_dry_run as dryrun
import source_review_cycles as reviews
from source_directional_eligibility import eligibility
from source_metadata import parse_metadata
from source_pre_review_admissibility import screen_original_packet
from source_research_batches import CATEGORIES, batch_prompt, sha, read_json
from test_source_semantic_v5 import packet_fixture, executed_queries


AS_OF = "2026-10-23T11:25:00-04:00"
NOW = dt.datetime.fromisoformat("2026-10-23T12:15:00-04:00")


def synthetic_v8_screened_packet():
    quality = []
    coverage = []
    query_ledger = []
    for index, category in enumerate(CATEGORIES):
        url = f"https://sources.example.org/iran/original-{index}"
        quality.append({
            "url": url, "role": "coverage_context_only",
            "classification": "background_only", "origin": "original_reporting",
            "access_status": "source_metadata_captured",
            "source_retrieval_status": "retrieved",
            "metadata_status": "publisher-supplied date; not verified release",
            "v8_source_inspection_scope":
                "HTML_METADATA_ONLY_NOT_VERIFIED_FULL_ARTICLE",
            "v8_first_publication_verified": False,
            "v8_article_witness_status":
                "NO_EXACT_CLAIM_PASSAGE_IN_ORIGINAL_REGISTER",
            "v8_current_event_status":
                "CONTEXT_ONLY_NOT_CURRENT_ADMITTED_EVIDENCE",
            "source_publication_time": None,
            "flags": [], "corroborating_urls": [],
            "new_evidence_indices": [],
        })
        coverage.append({
            "category": category, "original_urls": [url],
            "outcome": "searched_no_eligible_evidence",
            "pre_review_original_outcome": "searched_no_eligible_evidence",
            "limitations": ("Original reporting may not be independently "
                            "authenticated from publisher metadata alone."),
            "v8_search_vs_admission": {
                "original_search_outcome": "searched_no_eligible_evidence",
                "admission_result": "NO_ORIGINAL_OBSERVATION_ADMITTED",
                "research_as_of": AS_OF, "post_asof_window": "NOT_SEARCHED",
                "historical_context_not_contemporaneous_measurement": True,
            },
        })
        query_ledger.append({
            "category": category,
            "queries": [
                f"Iran worsening-risk original records {category}",
                f"Iran improving-risk original records {category}",
            ],
        })
    return {
        "pre_review_admission_version": 5,
        "evidence": [],
        "background_quotes": [],
        "pre_review_original_evidence": [],
        "pre_review_held_original_evidence": [],
        "pre_review_claim_decisions": [],
        "pre_review_original_input_sha256": "a" * 64,
        "claim_evidence_register": {"claims": []},
        "pre_review_actual_search_queries": query_ledger,
        "pre_review_research_scope_v8": {
            "research_as_of": AS_OF,
            "post_research_window": "NOT_SEARCHED",
            "metadata_inspection": "LATER_PROCESSING_NOT_NEW_SOURCE_RESEARCH",
            "past_events": "HISTORICAL_CONTEXT_NOT_CURRENT_OBSERVATIONS",
            "publication": "NOT AUTHORIZED",
        },
        "source_quality_audit": {
            "sources": quality, "source_count": len(quality),
        },
        "coverage": coverage,
        "published_history_sha256": "f" * 64,
        "research_as_of": AS_OF,
        "cutoff": AS_OF,
        "post_asof_window": "NOT_SEARCHED",
        "mode": "RESEARCH_ONLY_NONPUBLISHING",
    }


def role_response(packet, *, complete=True, inference_only=True,
                  approve=False):
    quality = packet["source_quality_audit"]["sources"]
    query = packet["pre_review_actual_search_queries"][0]["queries"]
    response = {
        "approved": approve,
        "issues": [{
            "type": "insufficient_for_inference",
            "location": "source_adequacy_review",
            "reason": ("Original-search documentation is complete, but no "
                       "admissible current observations support a national "
                       "stability change or an evidence-grounded forecast."),
        }],
        "source_reviews": [{
            "url": row["url"],
            "disposition": "background_only",
            "assessment": ("The source is listed as background and its "
                           "original article and chronology are not proven."),
        } for row in quality],
        "source_query_balance_review": {
            "raises_queries": [query[0]],
            "lowers_queries": [query[1]],
            "ambiguous_queries": [],
            "assessment": ("Separate original-search queries investigated "
                           "worsening and improving conditions, without "
                           "automatically classifying results as events."),
        },
        "source_adequacy_review": {
            "admitted_evidence_ids": [],
            "observation_count": 0,
            "conclusion": "insufficient_for_inference",
            "assessment": ("No current observations passed the original "
                           "passage and date checks. That absence prevents "
                           "a national geopolitical inference, not a "
                           "documented report of search coverage."),
            "limitations": ("These original-source records do not prove "
                            "that instability increased, declined, or stayed "
                            "unchanged, or support any scored forecast."),
        },
        "audit_integrity_review": {
            "audit_status": ("complete_with_disclosed_limitations"
                             if complete else "incomplete"),
            "source_count": len(quality),
            "coverage_categories": sorted(CATEGORIES),
            "research_as_of": AS_OF,
            "metadata_access_scope": "metadata_only_not_full_article",
            "first_publication_verified": False,
            "historical_context_is_current_evidence": False,
            "post_snapshot_search": "NOT_SEARCHED",
            "assessment": ("The original six-category search and exact "
                           "source URL inventory are complete as a "
                           "documentation audit, with rejected evidence "
                           "excluded rather than promoted."),
            "limitations": ("Only publisher-reported dates and metadata "
                            "fetches were available for these source rows; "
                            "none proves complete article bodies, first "
                            "publication or contemporaneous events."),
        },
    }
    if not inference_only:
        response["issues"].append({
            "type": "misreported_original_access",
            "location": "source_quality_audit.sources",
            "reason": ("A source has been represented as verified full-text "
                       "access without an independent original passage."),
        })
    return response


class V8AuditedButInconclusiveTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="iran-audit-versus-inference-")
        self.addCleanup(d.cleanup)
        self.folder = Path(d.name)
        self.packet = synthetic_v8_screened_packet()
        self.calls = []

    def reviewer(self, prompt, search):
        self.assertFalse(search)
        role = "affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical"
        self.calls.append(role)
        self.assertIn("V8 TWO DISTINCT SOURCE-REVIEW VERDICTS", prompt)
        self.assertIn("NO EVIDENCE QUOTA", prompt)
        return role_response(self.packet), set()

    def run_review(self, *, reviewer=None, correction=True):
        # Structural provenance is separately covered by source-register
        # tests. This synthetic fixture isolates orchestration and statuses.
        (self.folder / "source-pre-review-admissibility.json").write_text(
            json.dumps({
                "screened_review_input_sha256": sha(self.packet),
                "screened_packet": self.packet,
                "source_review_requests": "PERMITTED_AFTER_SCREEN",
                "status": "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY",
            }))
        with patch("source_passage_audit.verify_register", return_value=True), \
             patch.object(reviews, "deterministic_review_issues", return_value=[]):
            return reviews.run_alternating_review_cycles(
                folder=self.folder, sample=self.packet,
                input_sha=sha(self.packet), reviewer=reviewer or self.reviewer,
                now=lambda: NOW, original_cutoff=AS_OF,
                common="Synthetic closed source audit only.",
                enable_corrections=correction, enforce_guards=True)

    def test_complete_inconclusive_stops_after_one_dual_review_and_replays(self):
        original = copy.deepcopy(self.packet)
        out = self.run_review()
        self.assertEqual(self.calls, ["affirmative", "critical"])
        self.assertEqual(out["status"],
                         "RESEARCH_AUDIT_COMPLETE_INCONCLUSIVE_NOT_PUBLISHABLE")
        self.assertEqual(out["rounds"], 1)
        self.assertEqual(out["source_audit_status"],
                         "COMPLETE_WITH_DISCLOSED_LIMITATIONS")
        self.assertEqual(out["forecast_inference_status"],
                         "INSUFFICIENT_FOR_GEOPOLITICAL_FORECAST")
        self.assertEqual(out["prospective_forecasts"], "NOT TESTED")
        self.assertEqual(out["publication"], "NOT AUTHORIZED")
        self.assertEqual(self.packet, original)
        record = read_json(self.folder / "source-review-round-01.json")
        self.assertFalse(record["both_clean"])
        self.assertEqual(record["status"],
                         "SOURCE_AUDIT_COMPLETE_INCONCLUSIVE_NOT_PUBLISHABLE")
        self.assertEqual(record["source_audit_status"],
                         "COMPLETE_WITH_DISCLOSED_LIMITATIONS")
        self.assertFalse(record["affirmative"]["approved"])
        self.assertFalse(record["critical"]["approved"])
        self.assertEqual(len(record["affirmative"]["issues"]), 1)
        self.assertEqual(len(record["critical"]["issues"]), 1)
        self.assertFalse(
            (self.folder / "source-review-round-02-input.json").exists())
        self.assertFalse(
            (self.folder / "source-review-round-02-affirmative.json").exists())
        self.calls.clear()
        replay = self.run_review(reviewer=lambda *args:
                                 self.fail("No second paid reviewer"))
        self.assertEqual(replay, out)
        self.assertEqual(self.calls, [])

    def test_audit_integrity_objection_prevents_complete_status(self):
        for why in ("missing_review", "false_access", "incomplete",
                    "wrong_source_count", "wrong_original_asof",
                    "wrong_historical_scope", "false_first_published",
                    "post_snapshot_search", "tampered_quality"):
            packet = copy.deepcopy(self.packet)
            res = role_response(packet)
            if why == "missing_review":
                res.pop("audit_integrity_review")
            elif why == "false_access":
                res["issues"].append({
                    "type": "false_full_text_access",
                    "location": "source_quality_audit.sources",
                    "reason": "Metadata retrieval was incorrectly called full text."})
            elif why == "incomplete":
                res["audit_integrity_review"]["audit_status"] = "incomplete"
            elif why == "wrong_source_count":
                res["audit_integrity_review"]["source_count"] += 1
            elif why == "wrong_original_asof":
                res["audit_integrity_review"]["research_as_of"] = (
                    "2026-10-23T13:00:00-04:00")
            elif why == "wrong_historical_scope":
                res["audit_integrity_review"]["historical_context_is_current_evidence"] = True
            elif why == "false_first_published":
                res["audit_integrity_review"]["first_publication_verified"] = True
            elif why == "post_snapshot_search":
                res["audit_integrity_review"]["post_snapshot_search"] = "SEARCHED"
            elif why == "tampered_quality":
                packet["source_quality_audit"]["sources"][0][
                    "v8_source_inspection_scope"] = "FULL_TEXT_VERIFIED"
            with self.subTest(why=why):
                issues = reviews.v4_required_interpretation_issues(
                    packet, "critical", res["source_reviews"], res)
                if why not in ("incomplete", "tampered_quality"):
                    self.assertTrue(issues, why)
                approved = role_response(packet)
                self.assertFalse(reviews.v8_complete_but_inconclusive(
                    packet, {"affirmative": approved, "critical": res},
                    issues, enforce_guards=True))
        approved = role_response(self.packet)
        approved["approved"] = True
        self.assertFalse(reviews.v8_complete_but_inconclusive(
            self.packet, {"affirmative": approved,
                          "critical": role_response(self.packet)}, [],
            enforce_guards=True))
        self.assertFalse(reviews.v8_complete_but_inconclusive(
            self.packet, {"affirmative": role_response(self.packet),
                          "critical": role_response(self.packet)}, [],
            enforce_guards=False))

    def test_v8_source_screen_keeps_search_and_later_inspection_distinct(self):
        sample, research, snapshot = packet_fixture()
        snapshot = dict(snapshot, version=8)
        result = screen_original_packet(
            sample, research, baseline_sha="f" * 64,
            snapshot=snapshot, search_calls=executed_queries())
        self.assertEqual(result["version"], 5)
        reviewed = result["screened_packet"]
        self.assertEqual(reviewed["pre_review_admission_version"], 5)
        self.assertEqual(result["source_review_requests"], "PERMITTED_AFTER_SCREEN")
        self.assertEqual(result["directional_candidate_counts"]["failures"], [])
        self.assertEqual(reviewed["pre_review_research_scope_v8"][
            "research_as_of"], snapshot["cutoff_at"])
        self.assertEqual(reviewed["pre_review_research_scope_v8"][
            "post_research_window"], "NOT_SEARCHED")
        for source in reviewed["source_quality_audit"]["sources"]:
            self.assertEqual(source["v8_source_inspection_scope"],
                             "HTML_METADATA_ONLY_NOT_VERIFIED_FULL_ARTICLE")
            self.assertFalse(source["v8_first_publication_verified"])
        for category in reviewed["coverage"]:
            self.assertEqual(category["v8_search_vs_admission"][
                "research_as_of"], snapshot["cutoff_at"])
            self.assertTrue(category["v8_search_vs_admission"][
                "historical_context_not_contemporaneous_measurement"])
            self.assertEqual(category["v8_search_vs_admission"][
                "post_asof_window"], "NOT_SEARCHED")
        self.assertEqual(result["publication"], "NOT AUTHORIZED")

    def test_publisher_timestamp_is_claim_not_verified_original_release(self):
        html = ('<html><head><title>Original synthetic report</title>'
                '<meta property="article:published_time" '
                'content="2026-10-22T15:35:00-04:00"></head>'
                '<body><h1>Original synthetic report</h1></body></html>')
        status = parse_metadata(html)
        self.assertEqual(status["source_publication_time"],
                         "2026-10-22T19:35:00+00:00")
        self.assertIn("publisher-reported", status["metadata_status"])
        self.assertIn("not independently verified", status["metadata_status"])
        self.assertFalse(status["first_publication_verified"])

    def test_v7_original_prompt_and_legacy_minima_unchanged(self):
        base = {"date": "2026-10-23", "cutoff_at": AS_OF,
                "prior_index": []}
        for category in CATEGORIES:
            v7 = batch_prompt(category, dict(base, version=7))
            v8 = batch_prompt(category, dict(base, version=8))
            self.assertTrue(v8.startswith(v7))
            self.assertIn("V8 TWO DISTINCT QUESTIONS", v8)
            self.assertNotIn("V8 TWO DISTINCT QUESTIONS", v7)
            self.assertNotEqual(sha(v7), sha(v8))
        self.assertEqual(eligibility({
            "pre_review_admission_version": 5,
            "evidence": []})["failures"], [])
        self.assertIn("fewer_than_six_source_observations", eligibility({
            "pre_review_admission_version": 3,
            "evidence": []})["failures"])

    def test_diagnostic_main_distinguishes_inconclusive_from_failure(self):
        with patch.object(dryrun, "research_rehearsal", return_value={
            "status": "RESEARCH_AUDIT_COMPLETE_INCONCLUSIVE_NOT_PUBLISHABLE"}):
            self.assertIsNone(dryrun.main([]))
        with patch.object(dryrun, "research_rehearsal", return_value={
            "status": "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE"}):
            with self.assertRaises(SystemExit) as caught:
                dryrun.main([])
            self.assertEqual(caught.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
