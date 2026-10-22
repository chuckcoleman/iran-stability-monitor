"""Fresh v4 original date, multilingual, semantic, and search-balance regressions.

Old v3 audit fixtures stay unchanged; these tests never spend API credits.
"""
import copy
import datetime as dt
import hashlib
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from source_directional_eligibility import eligibility
from source_pre_review_admissibility import screen_original_packet, screen_or_restore
from source_research_batches import CATEGORIES, sha, save_new
from source_review_cycles import run_alternating_review_cycles
from test_source_pre_review_admissibility import fixture, SNAPSHOT, STAMP
from test_source_review_cycles import ORIGINAL


class V4SourceReviewTests(unittest.TestCase):
    def setUp(self):
        self.packet, self.raw = fixture()
        self.snapshot = dict(SNAPSHOT, version=4)
        self.packet["coverage"] = [
            {"category": category,
             "original_urls": [], "queries": [
                 "Actual multi-outlet research against both strengthening and weakening claims"],
             "outcome": "searched_no_eligible_evidence",
             "limitations": "No original directional signal passed screening."
            } for category in CATEGORIES]
        context = tempfile.TemporaryDirectory(prefix="source-v4-review-")
        self.addCleanup(context.cleanup)
        self.folder = Path(context.name)

    def screen(self):
        return screen_original_packet(self.packet, self.raw,
                                      baseline_sha="f"*64,
                                      snapshot=self.snapshot)

    def rebuild_quote(self, index, *, quote, observation):
        entry = self.packet["evidence"][index]
        raw = self.raw["evidence"][index]
        witness = self.packet["claim_evidence_register"]["claims"][index]
        entry["observation"] = observation
        witness["proposed_quote"] = quote
        witness["passage"] = quote
        witness["observation_sha256"] = hashlib.sha256(
            observation.encode("utf-8")).hexdigest()
        raw.update(observation=observation, support_quote=quote)
        self.packet["claim_evidence_register"]["evidence_sha256"] = sha(
            self.packet["evidence"])

    def test_new_policy_requires_six_searches_but_not_three_observed_outcomes(self):
        for entry in self.packet["evidence"]:
            entry["direction"] = "raises"
        self.packet["claim_evidence_register"]["evidence_sha256"] = sha(
            self.packet["evidence"])
        audit = self.screen()
        self.assertEqual(audit["status"], "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY")
        self.assertEqual(audit["admitted_original_ids"],
                         [row["id"] for row in self.packet["evidence"]])
        info = audit["directional_candidate_counts"]
        self.assertEqual(info["version"], 2)
        self.assertEqual(info["missing_directions"], ["ambiguous", "lowers"])
        self.assertEqual(info["failures"], [])
        self.assertEqual(info["directional_outcome_quota"], "NONE")
        self.assertEqual(info["searched_categories"], sorted(CATEGORIES))
        self.assertEqual(audit["screened_packet"]["source_balance_policy_version"], 2)

    def test_missing_search_category_fails_even_with_many_observations(self):
        self.packet["coverage"].pop()
        audit = self.screen()
        self.assertIn("incomplete_six_category_counterevidence_search",
                      audit["directional_candidate_counts"]["failures"])
        self.assertEqual(audit["source_review_requests"], "NOT_PERMITTED")

    def test_publisher_visible_date_without_time_qualifies_for_review_not_truth(self):
        source = self.packet["source_quality_audit"]["sources"][0]
        source["source_publication_time"] = None
        source["publication_dates_from_page"] = ["2026-10-15"]
        source["publisher_date_evidence"] = [{
            "date": "2026-10-15",
            "method": "article_visible_date",
            "tag": "div",
            "publisher_visible_excerpt": "October 15, 2026"
        }]
        self.packet["evidence"][0]["event_date"] = "2026-10-15"
        self.raw["evidence"][0]["event_date"] = "2026-10-15"
        self.packet["claim_evidence_register"]["evidence_sha256"] = sha(
            self.packet["evidence"])
        audit = self.screen()
        record = audit["per_claim"][0]
        self.assertEqual(record["reasons"], [])
        self.assertEqual(record["source_publication_status"],
                         "PUBLISHER_PRIOR_DATE_NOT_FIRST_PUBLICATION_PROOF")
        self.assertFalse(record["first_publication_verified"])

    def test_retiree_quote_passes_event_screen_with_direction_rationale_flagged(self):
        self.raw["evidence"][1]["direction_basis"] = (
            "The repeated gatherings are reported as possible increased "
            "protest pressure; the quoted text names actual cities but does "
            "not establish unusual scale or a regime-defection effect.")
        audit = self.screen()
        row = audit["per_claim"][1]
        self.assertEqual(row["reasons"], [])
        self.assertEqual(row["decision"],
                         "PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW")
        self.assertIn("VERIFY_DIRECTIONAL_RATIONALE_SEMANTICALLY",
                      row["semantic_reviewer_flags"])

    def test_arabic_original_with_later_untrusted_translation_never_becomes_original(self):
        quote = "إلى جانب أعمال ترميم في ملاجئ للطائرات تعرضت للقصف خلال الحرب"
        observation = "Satellite image report describes aircraft shelter repair work after bombing"
        self.rebuild_quote(3, quote=quote, observation=observation)
        self.raw["evidence"][3]["original_method"] = "firsthand_imagery_comparison"
        self.raw["evidence"][3]["support_translation_en"] = (
            "Alongside repair work in aircraft shelters that suffered bombing "
            "during the war")
        source = self.packet["source_quality_audit"]["sources"][3]
        source["classification"] = "analysis"
        source["origin"] = "original_reporting"
        audit = self.screen()
        row = audit["per_claim"][3]
        self.assertEqual(row["reasons"], [])
        self.assertIn("CHECK_ORIGINAL_LANGUAGE_TRANSLATION_AND_MEANING",
                      row["semantic_reviewer_flags"])
        self.assertIn("VERIFY_ORIGINAL_IMAGERY_COMPARISONS",
                      row["semantic_reviewer_flags"])
        tr = row["cross_language_translation_audit"]
        self.assertEqual(tr["original_passage"], quote)
        self.assertEqual(tr["original_passage_sha256"],
                         hashlib.sha256(quote.encode()).hexdigest())
        self.assertEqual(tr["proposed_translation_en"],
                         self.raw["evidence"][3]["support_translation_en"])
        self.assertEqual(tr["status"],
                         "TRANSLATION_MEANING_UNVERIFIED_DUAL_REVIEW_REQUIRED")
        self.assertEqual(tr["original_body_sha256"],
                         self.packet["claim_evidence_register"]["claims"][3][
                             "source_body_sha256"])
        self.assertNotIn("SATELLITE_IMAGES_VERIFIED",
                         str(audit["screened_packet"]))
        self.assertEqual(len(audit["screened_packet"]["pre_review_translation_audits"]),1)
        self.assertEqual(
            audit["screened_packet"]["evidence"][3]["observation"], observation)

    def test_missing_or_invalid_translation_is_held_out_not_fabricated(self):
        quote = "إلى جانب أعمال ترميم في ملاجئ للطائرات تعرضت للقصف خلال الحرب"
        self.rebuild_quote(3, quote=quote, observation=(
            "Satellite report describes repairs in damaged aircraft shelters"))
        self.raw["evidence"][3]["original_method"] = "firsthand_imagery_comparison"
        self.packet["source_quality_audit"]["sources"][3]["classification"] = "analysis"
        for value in (None, "", "Very short"):
            if value is None:
                self.raw["evidence"][3].pop("support_translation_en", None)
            else:
                self.raw["evidence"][3]["support_translation_en"] = value
            audit = self.screen()
            self.assertIn("MISSING_AUDITABLE_CROSS_LANGUAGE_TRANSLATION",
                          audit["per_claim"][3]["reasons"])
            self.assertIn(self.packet["evidence"][3]["id"],
                          audit["held_original_ids"])

    def test_contradictory_publisher_dates_block_but_do_not_rewrite_original(self):
        source = self.packet["source_quality_audit"]["sources"][0]
        source["publication_dates_from_page"] = ["2026-10-15", "2026-10-22"]
        source["publisher_date_evidence"] = [
            {"date": "2026-10-15", "method": "article_visible_date",
             "publisher_visible_excerpt": "October 15, 2026"},
            {"date": "2026-10-22", "method": "article_visible_date",
             "publisher_visible_excerpt": "October 22, 2026"}]
        result = self.screen()
        reasons = result["per_claim"][0]["reasons"]
        self.assertTrue("CONFLICTING_PUBLISHER_DATE_PROVENANCE" in reasons or
                        "PUBLISHER_DATE_AFTER_RESEARCH_CUTOFF" in reasons)

    def test_source_screen_replay_is_immutable_and_v3_policy_unchanged(self):
        initial = screen_or_restore(self.folder, self.packet, self.raw,
                                    baseline_sha="f"*64, snapshot=self.snapshot)
        original = (self.folder/"source-pre-review-admissibility.json").read_bytes()
        self.assertEqual(initial["version"], 2)
        again = screen_or_restore(self.folder, self.packet, self.raw,
                                  baseline_sha="f"*64, snapshot=self.snapshot)
        self.assertEqual(initial, again)
        self.assertEqual((self.folder/"source-pre-review-admissibility.json").read_bytes(),
                         original)
        v3 = dict(self.snapshot, version=3)
        v3_result = screen_original_packet(self.packet, self.raw,
                                           baseline_sha="f"*64, snapshot=v3)
        self.assertEqual(v3_result["version"], 1)
        self.assertNotIn("source_balance_policy_version",
                         v3_result["screened_packet"])

    def test_semantic_review_prompts_are_dual_and_never_approve_translation_automatically(self):
        screened = screen_or_restore(self.folder, self.packet, self.raw,
                                     baseline_sha="f"*64, snapshot=self.snapshot)
        self.assertEqual(screened["status"], "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY")
        save_new(self.folder/"source-review-input.json", {
            "sample": self.packet, "input_sha256": sha(self.packet),
            "publication": "NOT AUTHORIZED"})
        calls = []
        def reviewer(prompt, search):
            role = "affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical"
            self.assertIn("V4 ORIGINAL-LANGUAGE AND SUBSTANTIVE REVIEW", prompt)
            self.assertIn("six independent source categories", prompt)
            calls.append(role)
            return {"approved": True, "issues": []}, set()
        reviewed = run_alternating_review_cycles(
            folder=self.folder, sample=screened["screened_packet"],
            input_sha=screened["screened_review_input_sha256"],
            reviewer=reviewer, now=lambda: STAMP,
            common="Review original qualified evidence only",
            original_cutoff=ORIGINAL, max_rounds=2)
        self.assertEqual(calls, ["affirmative", "critical"])
        self.assertEqual(reviewed["status"], "RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE")


if __name__ == "__main__":
    unittest.main()
