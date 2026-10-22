"""V4 test of distinct source facts, model direction and bilingual text.

The policy MUST NOT change the old, immutable V3 reviewer input on resume.
The tests contain invented pages / incidents; they never establish facts.
"""
import copy
import datetime as dt
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from source_pre_review_admissibility import screen_original_packet, screen_or_restore
from source_research_batches import sha, batch_prompt
from test_source_pre_review_admissibility import fixture, SNAPSHOT


def v4_fixture():
    packet, original = fixture()
    snap = dict(SNAPSHOT, version=4)
    for row in original["evidence"]:
        row["source_language"] = "en"
        row["event_basis"] = row["direction_basis"]
        row["support_quote_translation"] = None
        row["original_method"] = "none"
        # The directional explanation need not share the original prose:
        # a forecast is a separate, explicitly uncertain inference.
        row["direction_basis"] = (
            "This observation might affect regime risk, but the available "
            "passage does not establish its size, persistence or direction; "
            "independent review is required.")
    return packet, original, snap


def screened(packet, original, snap):
    return screen_original_packet(
        packet, original, baseline_sha="f"*64, snapshot=snap)


class SourceV4SemanticTests(unittest.TestCase):
    def test_old_v3_protocol_and_paid_research_prompt_unchanged(self):
        packet, original = fixture()
        original_v3 = screen_original_packet(
            packet, original, baseline_sha="f"*64, snapshot=SNAPSHOT)
        self.assertNotIn("pre_review_screen_protocol",
                         original_v3["screened_packet"])
        parameters = {
            "date": "2026-10-21",
            "cutoff_at": SNAPSHOT["cutoff_at"],
            "prior_index": [],
        }
        p3 = batch_prompt("regional_multilingual_media", dict(parameters,version=3))
        p4 = batch_prompt("regional_multilingual_media", dict(parameters,version=4))
        self.assertTrue(p4.startswith(p3))
        self.assertNotIn("V4 EVENT-VERSUS-DIRECTION", p3)
        self.assertIn("V4 EVENT-VERSUS-DIRECTION", p4)

    def test_factual_event_grounded_but_direction_lexically_unrelated_is_provisional(self):
        packet, original, snap = v4_fixture()
        results = screened(packet, original, snap)
        self.assertEqual(results["status"], "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY",
                         [(d["id"],d["reasons"]) for d in results["per_claim"]])
        self.assertEqual(len(results["admitted_original_ids"]), 9)
        self.assertTrue(all(not r["reasons"] for r in results["per_claim"]))
        detail = results["per_claim"][0]["v4_separate_factual_and_directional_checks"]
        self.assertGreaterEqual(len(detail["factual_event_basis_overlap"]), 2)
        self.assertEqual(detail["directional_effect_status"],
                         "MODEL_INTERPRETATION_NOT_SOURCE_VERIFIED")
        self.assertEqual(detail["factual_support_status"],
                         "PROVISIONAL_TEXTUAL_RELEVANCE_NOT_EVENT_VERIFICATION")
        self.assertEqual(results["screened_packet"]["pre_review_screen_protocol"],
                         "v4_separate_factual_direction_and_original_language")

    def test_cross_language_arabic_passage_and_model_translation_audited(self):
        packet, original, snap = v4_fixture()
        native = "أظهرت صور الأقمار الصناعية أعمال إصلاح ملاجئ الطائرات في شيراز خلال أكتوبر"
        english = ("Satellite images showed aircraft shelter repairs in Shiraz "
                   "during October, but not operational readiness.")
        item = packet["evidence"][0]
        item["observation"] = (
            "Satellite images showed repairs to aircraft shelters in Shiraz "
            "during October; this alone does not prove restored readiness.")
        witness = packet["claim_evidence_register"]["claims"][0]
        witness["passage"] = native
        witness["proposed_quote"] = native
        witness["observation_sha256"] = hashlib.sha256(
            item["observation"].encode("utf-8")).hexdigest()
        packet["claim_evidence_register"]["evidence_sha256"] = sha(packet["evidence"])
        original["evidence"][0].update({
            "effect_type": "reported_event",
            "source_language": "ar",
            "support_quote_translation": english,
            "event_basis": (
                "The translated satellite images showed aircraft shelter "
                "repairs in Shiraz during October."),
            "direction_basis": (
                "Physical repair might have a stabilizing effect, but "
                "whether aircraft became usable is unknown."),
        })
        result = screened(packet, original, snap)
        self.assertIn(item["id"], result["admitted_original_ids"],
                      result["per_claim"][0]["reasons"])
        report = result["per_claim"][0]["v4_separate_factual_and_directional_checks"]
        self.assertEqual(report["source_script"], "arabic")
        self.assertEqual(report["source_language_model_declaration"], "ar")
        self.assertEqual(report["model_translation"], english)
        self.assertEqual(report["original_quote"], native)
        self.assertEqual(report["translation_status"],
                         "MODEL_PROPOSED_UNVERIFIED_REQUIRES_BILINGUAL_CHECK")
        self.assertFalse(report["translation_independently_checked"])
        self.assertNotEqual(report["original_quote"], report["model_translation"])
        self.assertGreaterEqual(len(report["factual_event_basis_overlap"]), 2)
        self.assertEqual(result["publication"], "NOT AUTHORIZED")

        original["evidence"][0]["support_quote_translation"] = None
        failed = screened(packet, original, snap)
        self.assertNotIn(item["id"], failed["admitted_original_ids"])
        self.assertIn("UNVERIFIED_TRANSLATION_MISSING_OR_MALFORMED",
                      failed["per_claim"][0]["reasons"])

        original["evidence"][0]["support_quote_translation"] = english
        original["evidence"][0]["source_language"] = "en"
        invalid_script = screened(packet, original, snap)
        self.assertIn("SOURCE_LANGUAGE_CONTRADICTS_QUOTE_SCRIPT",
                      invalid_script["per_claim"][0]["reasons"])

    def test_original_imagery_analysis_can_be_provisional_but_opinion_cannot(self):
        packet, original, snap = v4_fixture()
        packet["source_quality_audit"]["sources"][0]["classification"] = "analysis"
        packet["source_quality_audit"]["sources"][0]["origin"] = "original_reporting"
        original["evidence"][0]["original_method"] = "direct_original_satellite_imagery"
        proposed = screened(packet, original, snap)
        self.assertIn("E-20261021-01", proposed["admitted_original_ids"],
                      proposed["per_claim"][0]["reasons"])
        self.assertTrue(proposed["per_claim"][0][
            "original_imagery_eligible_only_for_dual_review"])
        # A think-tank/secondary analytical interpretation remains excluded.
        packet["source_quality_audit"]["sources"][1]["classification"] = "analysis"
        packet["source_quality_audit"]["sources"][1]["origin"] = "analytical_secondary"
        original["evidence"][1]["effect_type"] = "background_context"
        original["evidence"][1]["original_method"] = "none"
        rejected = screened(packet, original, snap)
        self.assertIn("E-20261021-02", rejected["held_original_ids"])
        self.assertIn("ANALYSIS_SYNDICATION_OR_UNVERIFIED_CLASS",
                      rejected["per_claim"][1]["reasons"])
        self.assertIn("NO_SUBSTANTIVE_OBSERVED_DIRECTION_BASIS",
                      rejected["per_claim"][1]["reasons"])

    def test_missing_event_factual_basis_and_nongrounded_translation_rejected(self):
        packet, original, snap = v4_fixture()
        original["evidence"][0]["event_basis"] = None
        original["evidence"][1]["event_basis"] = (
            "There are insufficient words here related to the article "
            "body or any specific observed event.")
        result = screened(packet, original, snap)
        self.assertIn("MISSING_OR_MALFORMED_FACTUAL_EVENT_BASIS",
                      result["per_claim"][0]["reasons"])
        self.assertIn("FACTUAL_EVENT_BASIS_NOT_GROUNDED_IN_ORIGINAL_OR_TRANSLATION",
                      result["per_claim"][1]["reasons"])
        self.assertEqual(len(result["held_original_ids"]), 2)

    def test_v4_preserves_source_date_only_and_immutable_resume(self):
        packet, original, snap = v4_fixture()
        row = packet["source_quality_audit"]["sources"][0]
        row["publisher_heading_date_evidence"] = [{
            "kind": "publisher_displayed_heading_date",
            "location": "adjacent_to_first_article_h1",
            "raw": "October 20, 2026", "date": "2026-10-20"}]
        row["publisher_heading_admitted_day"] = "2026-10-20"
        with tempfile.TemporaryDirectory() as dirname:
            first = screen_or_restore(
                dirname, packet, original, baseline_sha="f"*64, snapshot=snap)
            path = Path(dirname)/"source-pre-review-admissibility.json"
            old_bytes = path.read_bytes()
            repeated = screen_or_restore(
                dirname, packet, original, baseline_sha="f"*64, snapshot=snap)
            self.assertEqual(first, repeated)
            self.assertEqual(path.read_bytes(), old_bytes)
            self.assertFalse(first["per_claim"][0]["first_publication_verified"])
            self.assertEqual(first["per_claim"][0]["publisher_heading_admitted_day"],
                             "2026-10-20")
            original["evidence"][0]["support_quote_translation"] = (
                "A fake altered translation must not change a saved review.")
            with self.assertRaisesRegex(ValueError, "screening differs"):
                screen_or_restore(
                    dirname, packet, original, baseline_sha="f"*64, snapshot=snap)

    def test_v4_does_not_waive_directional_diversity_or_new_observation_minimums(self):
        packet, original, snap = v4_fixture()
        for index in (0,3,6):
            original["evidence"][index]["effect_type"] = "background_context"
        result = screened(packet, original, snap)
        self.assertEqual(result["source_review_requests"], "NOT_PERMITTED")
        self.assertIn("missing_required_directional_balance",
                      result["directional_candidate_counts"]["failures"])
        self.assertEqual(result["publication"], "NOT AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
