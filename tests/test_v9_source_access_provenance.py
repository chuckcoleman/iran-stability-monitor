"""V9 separate-stage source access provenance and fail-closed reviews.

Synthetic fixtures only: never repeat paid API POST, publish, or edit history.
"""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from source_research_batches import CATEGORIES, batch_prompt, sha
from source_directional_eligibility import eligibility
from source_pre_review_admissibility import screen_original_packet
from source_review_cycles import (
    _prompt, deterministic_review_issues, v4_required_interpretation_issues,
    v8_complete_but_inconclusive, v9_access_channel_integrity_issues)
from test_source_semantic_v5 import packet_fixture, executed_queries
from test_v8_inconclusive_source_audit import (
    AS_OF, synthetic_v8_screened_packet, role_response)


MODEL_REPORT = ("The search-stage model reported HTTP 403 when opening "
                "the article body, but this model statement is not a "
                "directly verifiable Python HTTP transport log.")
MODEL_LIMIT = ("A web-search citation and an HTTP error account do not "
               "prove original body availability or first publication.")


def v9_packet():
    packet = synthetic_v8_screened_packet()
    packet["pre_review_admission_version"] = 6
    packet["v9_access_reconciliation_policy"] = {
        "version": 1,
        "model_search_channel":
            "MODEL_REPORTED_SOURCE_ACCESS_NOT_INDEPENDENT_HTTP_LOG",
        "metadata_probe_channel":
            "SEPARATE_LATER_PYTHON_HTTP_HTML_METADATA_REQUEST",
        "claim_passage_channel":
            "SEPARATELY_RETRIEVED_EXACT_ORIGINAL_PASSAGE_REGISTER",
        "cross_channel_disagreement":
            "NOT_INHERENT_CONTRADICTION_OR_VERIFIED_RECONCILIATION",
        "research_as_of": AS_OF,
        "post_asof_window": "NOT_SEARCHED",
        "publication": "NOT AUTHORIZED",
    }
    for row in packet["source_quality_audit"]["sources"]:
        # Deliberately report earlier 403 and later metadata-only HTTP
        # success: that alone is NOT a claim that either stage is false.
        row["v9_access_channels"] = {
            "model_search_stage": {
                "provenance": "MODEL_REPORTED_NOT_INDEPENDENTLY_VERIFIED",
                "original_access_statement": MODEL_REPORT,
                "original_limitations": MODEL_LIMIT,
                "original_annotation_sha256": sha({
                    "assessment": MODEL_REPORT, "limitations": MODEL_LIMIT,
                }),
                "network_access_verification": "NOT_ESTABLISHED",
            },
            "later_python_metadata_probe": {
                "provenance": "INDEPENDENT_LATER_HTTP_METADATA_PROBE",
                "request_scope": "HTML_METADATA_ONLY_NOT_ARTICLE_BODY",
                "recorded_retrieval_status": "retrieved",
                "recorded_access_status": "source_metadata_captured",
                "recorded_metadata_status": row["metadata_status"],
                "recorded_publisher_time": row["source_publication_time"],
                "first_publication_verified": False,
            },
            "claim_body_witness": {
                "provenance": "SEPARATE_CLAIM_PASSAGE_REGISTER",
                "status": row["v8_article_witness_status"],
            },
            "comparison":
                "DISTINCT_OPERATIONS_NOT_AUTOMATIC_DISAGREEMENT"
                "_AND_NOT_AUTOMATIC_RECONCILIATION",
        }
    return packet


def v9_review(packet, *, complete=True, reconciled=True):
    result = role_response(packet, complete=complete)
    result["audit_integrity_review"].update({
        "access_channels_reconciled": reconciled,
        "access_channel_assessment": (
            "The original search-stage model asserted HTTP 403 for the "
            "article body while the separately executed Python GET later "
            "retrieved an HTML metadata page. These are different "
            "operations and neither proves complete original article-body "
            "access, original first publication, or an authenticated event. "
            "No independent body claim is promoted by this comparison."),
        "unresolved_access_conflicts": ([] if reconciled else
                                         [packet["source_quality_audit"]["sources"][0]["url"]]),
    })
    return result


class SourceAccessProvenanceV9Tests(unittest.TestCase):
    def test_future_v9_search_prompt_does_not_rewrite_paid_v8(self):
        frozen = {"date": "2026-10-23", "cutoff_at": AS_OF,
                  "prior_index": []}
        for category in CATEGORIES:
            old = batch_prompt(category, dict(frozen, version=8))
            new = batch_prompt(category, dict(frozen, version=9))
            self.assertTrue(new.startswith(old))
            self.assertNotIn("V9 ACCESS PROVENANCE", old)
            self.assertIn("V9 ACCESS PROVENANCE", new)
            self.assertNotEqual(sha(old), sha(new))

    def test_v9_no_count_quota_and_legacy_failures_stay_versioned(self):
        v9 = eligibility({"pre_review_admission_version": 6,
                          "evidence": []})
        self.assertEqual(v9["failures"], [])
        self.assertEqual(v9["version"], 5)
        self.assertTrue(v9["source_audit_complete_not_forecast_approval"])
        self.assertIn("DISTINCT_SEARCH_MODEL", v9["access_provenance_policy"])
        old = eligibility({"pre_review_admission_version": 3,
                           "evidence": []})
        self.assertIn("fewer_than_six_source_observations", old["failures"])

    def test_earlier_model_403_and_later_metadata_http_success_are_separate(self):
        packet = v9_packet()
        original = copy.deepcopy(packet)
        self.assertEqual(v9_access_channel_integrity_issues(packet), [])
        self.assertEqual(deterministic_review_issues(packet, AS_OF), [])
        reviewers = {"affirmative": v9_review(packet),
                     "critical": v9_review(packet)}
        for role, reply in reviewers.items():
            issues = v4_required_interpretation_issues(
                packet, role, reply["source_reviews"], reply)
            self.assertEqual(issues, [])
            prompt = _prompt(role, packet, sha(packet),
                             "Closed source-only synthetic review.")
            self.assertIn("V9 EXPLICIT ACCESS-CHANNEL RECONCILIATION", prompt)
            self.assertIn("metadata", prompt)
        self.assertTrue(v8_complete_but_inconclusive(
            packet, reviewers, [], enforce_guards=True))
        self.assertEqual(packet, original)

    def test_unresolved_real_access_discrepancy_blocks_complete_audit(self):
        packet = v9_packet()
        roles = {"affirmative": v9_review(packet),
                 "critical": v9_review(packet, complete=False,
                                       reconciled=False)}
        self.assertFalse(v8_complete_but_inconclusive(
            packet, roles, [], enforce_guards=True))
        roles["critical"]["audit_integrity_review"]["audit_status"] = (
            "complete_with_disclosed_limitations")
        issues = v4_required_interpretation_issues(
            packet, "critical", roles["critical"]["source_reviews"],
            roles["critical"])
        self.assertIn("v9_unresolved_source_access_conflict_in_audit",
                      [row["type"] for row in issues])
        self.assertFalse(v8_complete_but_inconclusive(
            packet, roles, issues, enforce_guards=True))

    def test_unreviewed_channels_or_invented_conflicts_fail_closed(self):
        packet = v9_packet()
        for action in ("missing_fields", "unknown_url", "missing_assessment",
                       "missing_comparison", "false_reconciliation"):
            reply = v9_review(packet)
            row = reply["audit_integrity_review"]
            if action == "missing_fields":
                row.pop("access_channels_reconciled")
            elif action == "unknown_url":
                row["unresolved_access_conflicts"] = [
                    "https://unknown.example.org/invented"]
                row["access_channels_reconciled"] = False
            elif action == "missing_assessment":
                row["access_channel_assessment"] = "No review"
            elif action == "missing_comparison":
                row["unresolved_access_conflicts"] = [packet[
                    "source_quality_audit"]["sources"][0]["url"]]
            elif action == "false_reconciliation":
                row["access_channels_reconciled"] = False
            with self.subTest(action=action):
                issues = v4_required_interpretation_issues(
                    packet, "affirmative", reply["source_reviews"], reply)
                self.assertIn("v9_access_channels_not_explicitly_reconciled",
                              [a["type"] for a in issues])
                self.assertFalse(v8_complete_but_inconclusive(
                    packet, {"affirmative": reply,
                             "critical": v9_review(packet)}, issues,
                    enforce_guards=True))

    def test_tampered_model_and_metadata_channels_block_audit(self):
        for change in ("model_statement", "model_hash",
                       "metadata_status", "metadata_access",
                       "probe_scope", "body_witness", "lost_policy",
                       "rewritten_metadata_after_review"):
            p = v9_packet()
            if change == "model_statement":
                p["source_quality_audit"]["sources"][0][
                    "v9_access_channels"]["model_search_stage"][
                        "original_access_statement"] = "Edited model"
            elif change == "model_hash":
                p["source_quality_audit"]["sources"][0][
                    "v9_access_channels"]["model_search_stage"][
                        "original_annotation_sha256"] = "0" * 64
            elif change == "metadata_status":
                p["source_quality_audit"]["sources"][0][
                    "v9_access_channels"]["later_python_metadata_probe"][
                        "recorded_metadata_status"] = "verified complete article"
            elif change == "metadata_access":
                p["source_quality_audit"]["sources"][0][
                    "v9_access_channels"]["later_python_metadata_probe"][
                        "recorded_access_status"] = "source_unavailable"
            elif change == "probe_scope":
                p["source_quality_audit"]["sources"][0][
                    "v9_access_channels"]["later_python_metadata_probe"][
                        "request_scope"] = "FULL_ARTICLE_VERIFIED"
            elif change == "body_witness":
                p["source_quality_audit"]["sources"][0][
                    "v9_access_channels"]["claim_body_witness"][
                        "status"] = "FULL_BODY_PROVEN"
            elif change == "lost_policy":
                del p["v9_access_reconciliation_policy"]
            elif change == "rewritten_metadata_after_review":
                p["source_quality_audit"]["sources"][0]["metadata_status"] = (
                    "Publisher/site metadata only; original first-publication "
                    "clock is not independently authenticated")
                p["source_quality_audit"]["sources"][0][
                    "editorial_original_metadata_status"] = "changed"
            with self.subTest(change=change):
                self.assertTrue(v9_access_channel_integrity_issues(p))
                self.assertFalse(v8_complete_but_inconclusive(
                    p, {"affirmative": v9_review(p),
                        "critical": v9_review(p)}, [], enforce_guards=True))

    def test_v9_pre_review_binds_original_model_access_and_later_metadata(self):
        packet, original, snap = packet_fixture()
        snap = dict(snap, version=9)
        original["source_quality"] = [{
            "url": row["url"],
            "assessment": row["assessment"],
            "limitations": row["limitations"],
        } for row in packet["source_quality_audit"]["sources"]]
        before = copy.deepcopy(original)
        result = screen_original_packet(
            packet, original, baseline_sha="f" * 64,
            snapshot=snap, search_calls=executed_queries())
        screened = result["screened_packet"]
        self.assertEqual(result["version"], 6)
        self.assertEqual(screened["pre_review_admission_version"], 6)
        self.assertEqual(result["publication"], "NOT AUTHORIZED")
        self.assertEqual(result["directional_candidate_counts"]["failures"], [])
        self.assertEqual(result["source_review_requests"],
                         "PERMITTED_AFTER_SCREEN")
        self.assertEqual(original, before)
        self.assertEqual(
            len(screened["source_quality_audit"]["sources"]),
            len(original["source_quality"]))
        for row in screened["source_quality_audit"]["sources"]:
            channels = row["v9_access_channels"]
            model = channels["model_search_stage"]
            self.assertEqual(model["network_access_verification"],
                             "NOT_ESTABLISHED")
            self.assertEqual(channels["later_python_metadata_probe"][
                "request_scope"], "HTML_METADATA_ONLY_NOT_ARTICLE_BODY")
            self.assertEqual(channels["claim_body_witness"]["status"],
                             row["v8_article_witness_status"])
        self.assertFalse(any("RESEARCH_ONLY" in x for x in
                             result["admitted_original_ids"]))

        tampered = copy.deepcopy(original)
        tampered["source_quality"][0]["assessment"] = (
            "A changed, unverified search-stage access description "
            "must never silently revise the already frozen source audit.")
        with self.assertRaisesRegex(ValueError, "differs from original model"):
            screen_original_packet(packet, tampered, baseline_sha="f"*64,
                                   snapshot=snap,
                                   search_calls=executed_queries())


if __name__ == "__main__":
    unittest.main()
