"""Forward-only accepted-evidence no-quota policy; old snapshots unchanged."""
import copy
import datetime as dt
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from assessment_pipeline import freeze_evidence
from source_directional_eligibility import eligibility
from source_research_batches import batch_prompt, CATEGORIES, sha
from source_review_cycles import _prompt, v4_required_interpretation_issues
from source_pre_review_admissibility import screen_original_packet
from test_source_semantic_v5 import packet_fixture, executed_queries


class AcceptedEvidenceNoQuotaTests(unittest.TestCase):
    def test_v7_accepts_zero_one_and_two_without_any_numeric_threshold(self):
        for n in (0, 1, 2, 3):
            observations = [
                {"id": "E-20261022-%02d" % (i + 1),
                 "publisher": "Only Original Publisher",
                 "direction": "raises",
                 "evidence_status": "new"}
                for i in range(n)]
            packet = {"pre_review_admission_version": 4,
                      "evidence": observations, "background_quotes": []}
            frozen = copy.deepcopy(packet)
            record = eligibility(packet)
            self.assertEqual(packet, frozen)
            self.assertEqual(record["failures"], [])
            self.assertEqual(record["version"], 3)
            self.assertEqual(record["directional_observations"], n)
            self.assertEqual(record["new_directional_observations"], n)
            self.assertEqual(record["distinct_directional_publishers"],
                             0 if n == 0 else 1)
            self.assertEqual(record["zero_admitted_observations"], n == 0)
            self.assertEqual(record["missing_directions"],
                             ["ambiguous", "lowers"] if n else
                             ["ambiguous", "lowers", "raises"])
            self.assertEqual(record["publication"], "NOT AUTHORIZED")
            self.assertFalse(
                record["irreversible_under_closed_source_corrections"])
            self.assertEqual(
                record["evidence_quantity_policy"],
                "NO_MINIMUM_OBSERVATIONS_NEW_OBSERVATIONS_OR_PUBLISHERS")

    def test_legacy_v6_still_fails_numerical_minima(self):
        for version in (1, 2, 3):
            packet = {"pre_review_admission_version": version,
                      "evidence": [{"id": "E-20261022-01",
                                    "publisher": "One publisher",
                                    "direction": "raises",
                                    "evidence_status": "new"}]}
            result = eligibility(packet)
            self.assertIn("fewer_than_six_source_observations",
                          result["failures"])
            self.assertIn("fewer_than_three_distinct_publishers",
                          result["failures"])
            self.assertIn("fewer_than_four_new_observations",
                          result["failures"])
            if version == 3:
                self.assertNotIn("missing_required_directional_balance",
                                 result["failures"])
            else:
                self.assertIn("missing_required_directional_balance",
                              result["failures"])

    def test_future_live_evidence_freeze_has_no_count_or_publisher_minimum(self):
        cutoff = dt.datetime(2026, 10, 22, 19, 20, tzinfo=dt.timezone.utc)
        day = cutoff.date().isoformat()
        empty = {"evidence": []}
        self.assertEqual(
            freeze_evidence(empty, set(), {"evidence": []}, day, cutoff,
                            no_accepted_evidence_quota=True), [])
        with self.assertRaisesRegex(ValueError, "Require 6-30 evidence items"):
            freeze_evidence(empty, set(), {"evidence": []}, day, cutoff)

        url = "https://example.org/original-one"
        single = {"evidence": [{
            "event_date": day, "category": "reported_event",
            "observation": "An original source reports a limited occurrence.",
            "source": url, "source_title": "Synthetic date-stamped report",
            "publisher": "Single independent publisher",
            "reliability": "Medium", "direction": "ambiguous",
            "impact_magnitude": "minor", "evidence_status": "new",
            "affects": [],
        }]}
        single_orig = copy.deepcopy(single)
        admitted = freeze_evidence(
            single, {url}, {"evidence": []}, day, cutoff,
            no_accepted_evidence_quota=True)
        self.assertEqual(single, single_orig)
        self.assertEqual(len(admitted), 1)
        self.assertEqual(admitted[0]["publisher"], "Single independent publisher")
        self.assertEqual(admitted[0]["direction"], "ambiguous")
        self.assertEqual(admitted[0]["evidence_status"], "new")
        self.assertEqual(admitted[0]["source"], url)
        with self.assertRaisesRegex(ValueError, "Source not verified"):
            freeze_evidence(single, set(), {"evidence": []}, day, cutoff,
                            no_accepted_evidence_quota=True)
        with self.assertRaisesRegex(ValueError, "Invalid evidence gate settings"):
            freeze_evidence(empty, set(), {"evidence": []}, day, cutoff,
                            no_accepted_evidence_quota=True,
                            provisional_source_only_v5=True)

    def test_v7_screen_preserves_original_claim_checks_without_quota(self):
        sample, original, snap = packet_fixture()
        snap = dict(snap, version=7)
        result = screen_original_packet(
            sample, original, baseline_sha="f" * 64,
            snapshot=snap, search_calls=executed_queries())
        self.assertEqual(result["version"], 4)
        self.assertEqual(result["screened_packet"]["pre_review_admission_version"], 4)
        self.assertEqual(result["directional_candidate_counts"]["failures"], [])
        self.assertEqual(result["source_review_requests"], "PERMITTED_AFTER_SCREEN")
        self.assertEqual(result["publication"], "NOT AUTHORIZED")
        self.assertEqual(
            len(result["screened_packet"]["pre_review_actual_search_queries"]), 6)
        self.assertIn("NO minimum count",
                      result["screened_packet"]["pre_review_limitations"])

    def test_old_prompts_preserved_new_v7_explicitly_overrides_quota(self):
        snapshot = {"date": "2026-10-22", "cutoff_at": "2026-10-22T19:20:00-04:00",
                    "prior_index": []}
        for category in CATEGORIES:
            v5 = batch_prompt(category, dict(snapshot, version=5))
            v6 = batch_prompt(category, dict(snapshot, version=6))
            v7 = batch_prompt(category, dict(snapshot, version=7))
            self.assertIn("V6 FORWARD-ONLY", v6)
            self.assertTrue(v6.startswith(v5))
            self.assertIn("V7 FORWARD-ONLY NO ACCEPTED-EVIDENCE QUOTA", v7)
            self.assertNotIn("downstream six-source", v7)
            self.assertIn("NO fixed minimum", v7)
            self.assertNotEqual(sha(v7), sha(v6))
            self.assertNotEqual(sha(v6), sha(v5))

    @staticmethod
    def review_response(packet, *, approved=True,
                        conclusion="supported_limited_inference"):
        ledger = packet["pre_review_actual_search_queries"]
        queries = ledger[0]["queries"]
        identifiers = [item["id"] for item in packet["evidence"]]
        return {
            "approved": approved,
            "source_query_balance_review": {
                "raises_queries": [queries[0]],
                "lowers_queries": [queries[1]],
                "ambiguous_queries": [],
                "assessment":
                    "The frozen search records cover separate plausible improving "
                    "and worsening developments; neither direction is proven by "
                    "the fact that a query was executed.",
            },
            "source_adequacy_review": {
                "admitted_evidence_ids": identifiers,
                "observation_count": len(identifiers),
                "assessment":
                    "The review distinguishes facts actually supported by "
                    "admitted original sources from the wider unresolved "
                    "question of national stability and contradictory reporting.",
                "limitations":
                    "Search results and article snippets cannot prove "
                    "uncorroborated material, and sparse or absent observations "
                    "cannot establish that a risk is absent or a forecast is true.",
                "conclusion": conclusion,
            },
        }

    def test_both_roles_must_explicitly_review_exact_sparse_evidence(self):
        ledger = [
            {"category": category,
             "queries": [
                 "Risk-increasing original source research for " + category,
                 "Stabilizing original source research for " + category]}
            for category in CATEGORIES
        ]
        for count in (0, 1):
            packet = {
                "pre_review_admission_version": 4,
                "evidence": ([{"id": "E-20261022-01",
                               "publisher": "First publisher",
                               "direction": "ambiguous", "evidence_status": "new"}]
                             if count else []),
                "pre_review_actual_search_queries": ledger,
                "pre_review_claim_decisions": [],
            }
            for role in ("affirmative", "critical"):
                response = self.review_response(packet)
                self.assertEqual(v4_required_interpretation_issues(
                    packet, role, [], response), [])
                message = _prompt(role, packet, sha(packet), "source-only check")
                self.assertIn("V7 NO EVIDENCE QUOTA", message)
                self.assertIn("source_adequacy_review", message)
                self.assertNotIn("Any incomplete minimum is a deterministic fail",
                                 message)
                missing = copy.deepcopy(response)
                del missing["source_adequacy_review"]
                kinds = [r["type"] for r in v4_required_interpretation_issues(
                    packet, role, [], missing)]
                self.assertIn("v7_source_adequacy_not_independently_reviewed",
                              kinds)
                wrong_ids = copy.deepcopy(response)
                wrong_ids["source_adequacy_review"]["admitted_evidence_ids"] = [
                    "INVENTED"]
                kinds = [r["type"] for r in v4_required_interpretation_issues(
                    packet, role, [], wrong_ids)]
                self.assertIn("v7_source_adequacy_not_independently_reviewed",
                              kinds)
                rejects_but_approves = self.review_response(
                    packet, approved=True,
                    conclusion="insufficient_for_inference")
                kinds = [r["type"] for r in v4_required_interpretation_issues(
                    packet, role, [], rejects_but_approves)]
                self.assertIn("v7_unsupported_approval_despite_evidence_limit",
                              kinds)
                rejection = self.review_response(
                    packet, approved=False,
                    conclusion="insufficient_for_inference")
                self.assertEqual(v4_required_interpretation_issues(
                    packet, role, [], rejection), [])


if __name__ == "__main__":
    unittest.main()
