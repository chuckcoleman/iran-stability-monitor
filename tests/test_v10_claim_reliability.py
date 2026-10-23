"""Prospective V10 reliability: source-specific, ordinal and not a forecast.

Synthetic fixtures only. No paid API request, actual news access or
publication is performed by these tests. Historical data stay immutable.
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

from source_claim_reliability import (
    apply_reviewed_reliability, assess_review_claims,
    reconcile_dual_reliability, reliability_from_factors,
)
from source_directional_eligibility import eligibility
from source_pre_review_admissibility import screen_original_packet
from source_research_batches import CATEGORIES, batch_prompt, sha
from test_source_semantic_v5 import packet_fixture, executed_queries
import assessment_pipeline as pipeline

NOW = dt.datetime.fromisoformat("2026-10-23T13:10:00-04:00")


def sample_claims(n=2):
    rows, decisions, sources = [], [], []
    for i in range(1, n + 1):
        ident = f"E-20261023-{i:02d}"
        url = f"https://primary.example.org/iran/source-{i}"
        rows.append({
            "id": ident, "date": "2026-10-23",
            "event_date": "2026-10-22", "publisher": f"Independent {i}",
            "source": url, "evidence_status": "new",
            "observation": f"Measured synthetic indicator {i}",
            "direction": "raises", "reliability": "High",
            "impact_magnitude": "moderate",
        })
        decisions.append({
            "id": ident, "original_url": url,
            "passage_status": "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED",
            "source_body_sha256": str(i) * 64,
            "original_passage": ("The original synthetic measurement "
                                 "reported a documented independent indicator."),
            "decision": "PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW",
        })
        sources.append({
            "url": url, "classification": "direct_observation",
            "origin": "original_reporting", "role": "new_evidence",
            "new_evidence_indices": [i - 1],
            "corroborating_urls": [],
        })
    return {
        "pre_review_admission_version": 7,
        "evidence": rows,
        "pre_review_claim_decisions": decisions,
        "source_quality_audit": {"sources": sources},
    }


def reviewer_rows(packet, *, role="affirmative", confirmations=None,
                  direction="unverified", conflict="none_identified",
                  quality="documented_original_method",
                  direct="primary_measurement_or_document"):
    confirmations = confirmations or {}
    out = []
    for row in packet["evidence"]:
        ids = confirmations.get(row["id"], [])
        grade = reliability_from_factors(
            quality, direct, confirmed_independent=bool(ids),
            contradiction=conflict, exact_original_passage=True)
        out.append({
            "evidence_id": row["id"],
            "original_url": row["source"],
            "source_quality": quality,
            "directness": direct,
            "independent_confirmation_ids": ids,
            "claim_match_independently_reviewed": bool(ids),
            "contradiction_status": conflict,
            "source_quality_assessment": (
                "This is a synthetic original primary measurement with "
                "documented methods, not automatically a reliable institution."),
            "corroboration_assessment": (
                "The submitted original reporting chain is explicitly "
                "checked for genuinely independent source content, not URL count."),
            "contradiction_assessment": (
                "The reviewer separately considers adverse testimony and "
                "does not mistake a model narrative for authenticated evidence."),
            "exact_passage_witness": True,
            "factual_reliability": grade,
            "direction_confidence": direction,
        })
    return {"approved": True, "issues": [], "claim_reliability_reviews": out}


class ClaimReliabilityV10Tests(unittest.TestCase):
    def test_unconfirmed_primary_can_be_medium_high_without_quota(self):
        packet = sample_claims(1)
        response = reviewer_rows(packet)
        grades = assess_review_claims(packet, "affirmative", response)
        self.assertEqual(grades[0]["factual_reliability"], "Medium-high")
        self.assertEqual(grades[0]["independent_confirmation_ids"], [])
        self.assertEqual(grades[0]["stability_direction_confidence"], "unverified")
        self.assertEqual(reconcile_dual_reliability(
            packet, response, response)[0]["factual_reliability"], "Medium-high")

    def test_high_needs_original_claim_specific_confirmed_chain_from_both(self):
        packet = sample_claims(2)
        a, b = [e["id"] for e in packet["evidence"]]
        matches = {a: [b], b: [a]}
        response = reviewer_rows(packet, confirmations=matches)
        original = copy.deepcopy(packet)
        certified = reconcile_dual_reliability(packet, response, response)
        self.assertEqual([r["factual_reliability"] for r in certified],
                         ["High", "High"])
        self.assertEqual(certified[0]["independently_confirmed_claim_ids"], [b])
        self.assertEqual(certified[0]["stability_direction_confidence"],
                         "unverified")
        self.assertEqual(packet, original)

    def test_different_confirmers_do_not_agree_and_cannot_give_high(self):
        packet = sample_claims(3)
        x, y, z = [row["id"] for row in packet["evidence"]]
        affirm = reviewer_rows(packet, confirmations={x: [y]})
        critic = reviewer_rows(packet, confirmations={x: [z]})
        reconciled = reconcile_dual_reliability(packet, affirm, critic)
        self.assertEqual(reconciled[0]["factual_reliability"], "Medium-high")
        self.assertEqual(reconciled[0]["independently_confirmed_claim_ids"], [])

    def test_same_publisher_or_syndicated_reprint_never_corroborates(self):
        packet = sample_claims(2)
        ids = [x["id"] for x in packet["evidence"]]
        reply = reviewer_rows(packet, confirmations={ids[0]: [ids[1]]})
        same_publisher = copy.deepcopy(packet)
        same_publisher["evidence"][1]["publisher"] = same_publisher[
            "evidence"][0]["publisher"]
        with self.assertRaisesRegex(ValueError, "independent confirmation"):
            assess_review_claims(same_publisher, "critical", reply)
        syndicated = copy.deepcopy(packet)
        syndicated["source_quality_audit"]["sources"][1]["origin"] = (
            "syndicated_reprint")
        with self.assertRaisesRegex(ValueError, "independent confirmation"):
            assess_review_claims(syndicated, "critical", reply)
        self_confirm = copy.deepcopy(reply)
        self_confirm["claim_reliability_reviews"][0][
            "independent_confirmation_ids"] = [ids[0]]
        with self.assertRaises(ValueError):
            assess_review_claims(packet, "critical", self_confirm)

    def test_missing_original_passage_material_conflict_and_weak_source(self):
        for reason in ("missing_passage", "material_conflict",
                       "unknown_source", "unsupported_quality", "inflated_grade",
                       "missing_reviews", "invented_confirm", "changed_url"):
            packet = sample_claims(1)
            response = reviewer_rows(packet)
            row = response["claim_reliability_reviews"][0]
            if reason == "missing_passage":
                packet["pre_review_claim_decisions"][0]["passage_status"] = (
                    "ORIGINAL_TEXT_UNAVAILABLE")
            elif reason == "material_conflict":
                row["contradiction_status"] = "material_unresolved"
                row["factual_reliability"] = "Low"
            elif reason == "unknown_source":
                row["source_quality"] = "weak_or_unknown_source"
                row["factual_reliability"] = "Low"
            elif reason == "unsupported_quality":
                packet["source_quality_audit"]["sources"][0][
                    "classification"] = "analysis"
            elif reason == "inflated_grade":
                row["factual_reliability"] = "High"
            elif reason == "missing_reviews":
                response["claim_reliability_reviews"] = []
            elif reason == "invented_confirm":
                row["independent_confirmation_ids"] = ["INVENTED"]
            elif reason == "changed_url":
                row["original_url"] = "https://wrong.example.net/article"
            with self.subTest(reason=reason):
                if reason in ("material_conflict", "unknown_source"):
                    got = assess_review_claims(packet, "affirmative", response)
                    self.assertEqual(got[0]["factual_reliability"], "Low")
                else:
                    with self.assertRaises(ValueError):
                        assess_review_claims(packet, "affirmative", response)

    def test_qualified_material_conflict_caps_fact_not_direction(self):
        self.assertEqual(reliability_from_factors(
            "documented_original_method", "primary_measurement_or_document",
            confirmed_independent=True,
            contradiction="addressed_with_qualification",
            exact_original_passage=True), "Medium")
        self.assertEqual(reliability_from_factors(
            "attributed_edited_original", "firsthand_original_reporting",
            confirmed_independent=False, exact_original_passage=True), "Medium")
        self.assertEqual(reliability_from_factors(
            "documented_original_method", "primary_measurement_or_document",
            confirmed_independent=True, exact_original_passage=False), "Low")

    def test_apply_only_reviewed_new_grade_historical_carry_unchanged(self):
        packet = sample_claims(1)
        new = packet["evidence"][0]
        carried = {
            "id": "E-20261004-01", "publisher": "Historical original",
            "source": "https://old.example.org/article",
            "evidence_status": "carried_forward", "reliability": "High",
            "direction": "ambiguous",
        }
        frozen = [copy.deepcopy(carried), copy.deepcopy(new)]
        both = reviewer_rows(packet)
        certificate = reconcile_dual_reliability(packet, both, both)
        original = copy.deepcopy(frozen)
        current = [copy.deepcopy(e) for e in frozen]
        result = apply_reviewed_reliability(current, frozen, certificate)
        self.assertEqual(result[0], carried)
        self.assertEqual(result[1]["reliability"], "Medium-high")
        self.assertEqual(result[1]["geopolitical_direction_confidence"], "unverified")
        self.assertEqual(result[1]["direction"], "raises")
        self.assertEqual(frozen, original)
        self.assertEqual(current, original)
        with self.assertRaises(ValueError):
            apply_reviewed_reliability(frozen, frozen, [])
        tampered = copy.deepcopy(current)
        tampered[1]["direction"] = "lowers"
        with self.assertRaises(ValueError):
            apply_reviewed_reliability(tampered, frozen, certificate)

    def test_v10_forward_only_prompt_and_no_minima(self):
        snapshot = {"date": "2026-10-23",
                    "cutoff_at": "2026-10-23T13:02:00-04:00",
                    "prior_index": []}
        for category in CATEGORIES:
            prev = batch_prompt(category, dict(snapshot, version=9))
            now = batch_prompt(category, dict(snapshot, version=10))
            self.assertTrue(now.startswith(prev))
            self.assertIn("V10 CLAIM-SPECIFIC FACTUAL RELIABILITY", now)
            self.assertNotIn("V10 CLAIM-SPECIFIC", prev)
        count = eligibility({"pre_review_admission_version": 7,
                             "evidence": []})
        self.assertEqual(count["failures"], [])
        self.assertTrue(count["no_assumed_independent_corroboration"])
        self.assertIn("claim_reliability_policy", count)

    def test_v10_original_source_pre_review_uses_provisional_grades(self):
        sample, research, snapshot = packet_fixture()
        snapshot = dict(snapshot, version=10)
        for index, row in enumerate(sample["source_quality_audit"]["sources"]):
            row.setdefault(
                "assessment",
                "Original independent-source research for synthetic test %d "
                "is not independently verified by the URL alone." % index)
            row.setdefault(
                "limitations",
                "No independently authenticated publisher release instant "
                "or causal effect on national stability has been established.")
        research["source_quality"] = [{
            "url": row["url"], "assessment": row["assessment"],
            "limitations": row["limitations"],
        } for row in sample["source_quality_audit"]["sources"]]
        outcome = screen_original_packet(
            sample, research, baseline_sha="f" * 64,
            snapshot=snapshot, search_calls=executed_queries())
        screened = outcome["screened_packet"]
        self.assertEqual(outcome["version"], 7)
        self.assertEqual(screened["pre_review_admission_version"], 7)
        self.assertTrue(screened["pre_review_reliability_policy_v10"][
            "publisher_reputation_alone_not_a_grade"])
        self.assertEqual(outcome["directional_candidate_counts"]["failures"], [])
        self.assertEqual(outcome["publication"], "NOT AUTHORIZED")

    def test_live_preforecast_substitutes_only_dual_verified_grades(self):
        packet = sample_claims(1)
        proposal = copy.deepcopy(packet["evidence"][0])
        historical = {
            "id": "E-20261004-01", "publisher": "Old publisher",
            "source": "https://historic.example.org/story",
            "evidence_status": "carried_forward", "reliability": "High",
            "direction": "ambiguous",
        }
        frozen = [copy.deepcopy(historical), copy.deepcopy(proposal)]
        saved_before = copy.deepcopy(frozen)
        snapshot = {
            "version": 10, "snapshot_sha256": "f" * 64,
            "cutoff_at": "2026-10-23T12:55:00-04:00",
        }
        original_review = reviewer_rows(packet)
        graded = reconcile_dual_reliability(
            packet, original_review, original_review)
        result = {
            "status": "RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE",
            "rounds": 1,
            "final_review_input_sha256": sha(packet),
            "claim_reliability": graded,
            "final_reviewers": {
                "affirmative": original_review,
                "critical": original_review,
            },
        }
        screened = {
            "screened_packet": packet,
            "status": "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY",
            "screened_review_input_sha256": sha(packet),
            "source_review_requests": "PERMITTED_AFTER_SCREEN",
        }
        def run(**kwargs):
            self.assertIs(kwargs["reviewer"], pipeline.LIVE_RESEARCHER)
            self.assertFalse(kwargs["common"].startswith("SCORE A FORECAST"))
            return copy.deepcopy(result)
        with tempfile.TemporaryDirectory() as folder:
            opts = dict(
                research={}, frozen=frozen, citations=set(),
                search_calls=[], coverage=[], quality={},
                historical_evidence=[historical],
                history_sha="a" * 64, snapshot=snapshot,
                date="2026-10-23", now=lambda: NOW,
                reviewer=pipeline.LIVE_RESEARCHER,
                audit_dir=Path(folder),
            )
            with patch("source_review_resume.load_or_create_review_input",
                       return_value=(packet, sha(packet), NOW)), \
                 patch("source_pre_review_admissibility.screen_or_restore",
                       return_value=screened), \
                 patch("source_review_cycles.run_alternating_review_cycles",
                       side_effect=run):
                amended = pipeline._certify_v10_factual_reliability_before_forecast(
                    **opts)
                again = pipeline._certify_v10_factual_reliability_before_forecast(
                    **opts)
                self.assertEqual(amended, again)
            self.assertEqual(amended[0], historical)
            self.assertEqual(amended[1]["reliability"], "Medium-high")
            self.assertEqual(amended[1]["geopolitical_direction_confidence"],
                             "unverified")
            self.assertEqual(frozen, saved_before)
            certificate = json.loads((Path(folder) /
                "claim-reliability-preforecast-certificate.json").read_text())
            self.assertEqual(certificate["claim_reliability"], graded)
            self.assertEqual(certificate["publication"], "NOT AUTHORIZED")
            self.assertTrue(
                certificate["historical_carry_forward_unchanged"])
            # A falsified higher grade must not be allowed through simply
            # because a JSON certificate claims reviewer approval.
            result["claim_reliability"][0]["factual_reliability"] = "High"
            with patch("source_review_resume.load_or_create_review_input",
                       return_value=(packet, sha(packet), NOW)), \
                 patch("source_pre_review_admissibility.screen_or_restore",
                       return_value=screened), \
                 patch("source_review_cycles.run_alternating_review_cycles",
                       side_effect=run):
                with self.assertRaisesRegex(
                        ValueError, "do not reproduce from"):
                    pipeline._certify_v10_factual_reliability_before_forecast(
                        **opts)

    def test_live_preforecast_rejected_audit_never_elicits_probability(self):
        packet = sample_claims(1)
        frozen = copy.deepcopy(packet["evidence"])
        snap = {"version": 10, "snapshot_sha256": "f" * 64,
                "cutoff_at": "2026-10-23T12:55:00-04:00"}
        screened = {"screened_packet": packet,
                    "status": "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY",
                    "screened_review_input_sha256": sha(packet),
                    "source_review_requests": "PERMITTED_AFTER_SCREEN"}
        with tempfile.TemporaryDirectory() as folder:
            with patch("source_review_resume.load_or_create_review_input",
                       return_value=(packet, sha(packet), NOW)), \
                 patch("source_pre_review_admissibility.screen_or_restore",
                       return_value=screened), \
                 patch("source_review_cycles.run_alternating_review_cycles",
                       return_value={
                           "status": "RESEARCH_AUDIT_COMPLETE_INCONCLUSIVE_NOT_PUBLISHABLE",
                           "rounds": 1,
                           "final_review_input_sha256": sha(packet),
                           "claim_reliability": []}):
                with self.assertRaisesRegex(ValueError,
                                            "no geopolitical forecast elicited"):
                    pipeline._certify_v10_factual_reliability_before_forecast(
                        research={}, frozen=frozen, citations=set(),
                        search_calls=[], coverage=[], quality={},
                        historical_evidence=[], history_sha="a" * 64,
                        snapshot=snap, date="2026-10-23",
                        now=lambda: NOW, reviewer=pipeline.LIVE_RESEARCHER,
                        audit_dir=Path(folder))


if __name__ == "__main__":
    unittest.main()
