"""Article-heading dates and v4 bilingual/source-semantic tests.

All page and translator examples are synthetic offline fixtures. In
particular, no scraped header date or machine-draft translation proves
first publication, satellite imagery truth or direction of regime stability.
"""
import copy
import datetime as dt
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from source_metadata import parse_metadata, headline_publication_dates
from source_research_batches import sha, batch_prompt
from source_pre_review_admissibility import (
    screen_original_packet, ADMISSION, REJECT)
from source_review_cycles import v4_required_interpretation_issues, _prompt
from test_source_pre_review_admissibility import fixture, SNAPSHOT

HEADING = "Operation Economic Outcast Targets Iranian International Financial Networks"
TREASURY_HTML = (f"<html><head><title>{HEADING} | Treasury</title></head>"
                 f"<body><nav>October 21, 2026</nav><main><h1>{HEADING}</h1>"
                 "<div class='field--name-field-date'>October 15, 2026</div>"
                 "<p>The bulletin names seven employees.</p>"
                 "<p>Other events occurred on October 20, 2026.</p>"
                 "</main></body></html>")

ARABIC = "أظهرت صور الأقمار الصناعية أعمال ترميم ملاجئ الطائرات في مطار شيراز"
ENGLISH = "Satellite imagery shows repair work in bombed aircraft shelters at Shiraz airport."
DRAFT = "Satellite images show repair work in bombed aircraft shelters at Shiraz airport."


class PublisherDateCaptureTests(unittest.TestCase):
    def test_treasury_style_visible_headline_date_is_publisher_only(self):
        metadata = parse_metadata(TREASURY_HTML)
        self.assertEqual(metadata["source_publication_time"], None)
        self.assertEqual(metadata["publication_dates"], ["2026-10-15"])
        self.assertEqual(metadata["publication_date_evidence"], [{
            "date": "2026-10-15",
            "origin": "article_headline_adjacent_visible_date",
            "original_text": "October 15, 2026",
            "first_publication_verified": False,
        }])
        self.assertIs(metadata["first_publication_verified"], False)
        self.assertIn("precise time unknown", metadata["metadata_status"])
        self.assertNotIn("2026-10-21", metadata["publication_dates"])
        self.assertNotIn("2026-10-20", metadata["publication_dates"])

    def test_no_navbar_body_or_unrelated_heading_date_is_promoted(self):
        html = (f"<html><head><title>{HEADING}</title></head><body>"
                "<nav><h2>Long unrelated subscription and market headline"
                "</h2><div>October 18, 2026</div></nav>"
                f"<h1>{HEADING}</h1><p>This is about other dates.</p>"
                "<p>October 15, 2026</p></body></html>")
        self.assertEqual(headline_publication_dates(html), [])
        result = parse_metadata(html)
        self.assertEqual(result["publication_dates"], [])
        self.assertNotIn("publication_date_evidence", result)

    def test_visible_date_with_precise_time_is_not_claimed_first_published(self):
        html = (f"<html><head><title>{HEADING}</title>"
                "<meta property='article:published_time' "
                "content='2026-10-15T18:15:00-04:00'></head>"
                f"<body><h1>{HEADING}</h1><time>October 15, 2026</time></body>")
        result = parse_metadata(html)
        self.assertEqual(result["publication_dates"], ["2026-10-15"])
        self.assertEqual(result["source_publication_time"],
                         "2026-10-15T22:15:00+00:00")
        self.assertIs(result["first_publication_verified"], False)
        self.assertEqual(result["publication_date_evidence"][0]["date"],
                         "2026-10-15")

    def test_invalid_or_ambiguous_dates_do_not_enter_publisher_evidence(self):
        for bad in ("October 33, 2026", "09/10/2026",
                    "October 15, 2027 future report",
                    "Reported in September and October 2026"):
            with self.subTest(bad=bad):
                html = (f"<html><head><title>{HEADING}</title></head>"
                        f"<body><h1>{HEADING}</h1><div>{bad}</div></body>")
                self.assertEqual(headline_publication_dates(html), [])


class V4CrossLanguageScreenTests(unittest.TestCase):
    def setUp(self):
        self.sample, self.research = fixture()
        self.snapshot = dict(SNAPSHOT, version=4)
        self.sample["evidence"][0]["observation"] = ENGLISH
        self.research["evidence"][0]["observation"] = ENGLISH
        self.research["evidence"][0]["effect_type"] = "measured_data"
        self.research["evidence"][0]["observational_method"] = (
            "original_satellite_imagery")
        self.research["evidence"][0]["direction_basis"] = (
            "A qualified tentative hypothesis connects this physical "
            "repair activity with limited recovery, without establishing "
            "military readiness or even a definite stability improvement.")
        self.research["evidence"][0]["original_quote_language"] = "ar"
        self.research["evidence"][0]["support_quote_translation"] = DRAFT
        self.research["evidence"][0]["translation_status"] = (
            "MODEL_DRAFT_UNVERIFIED")
        self.sample["source_quality_audit"]["sources"][0][
            "classification"] = "analysis"
        row = self.sample["claim_evidence_register"]["claims"][0]
        row["passage"] = ARABIC
        row["proposed_quote"] = ARABIC
        row["observation_sha256"] = hashlib.sha256(
            ENGLISH.encode("utf-8")).hexdigest()
        self.sample["claim_evidence_register"]["evidence_sha256"] = sha(
            self.sample["evidence"])

    def screening(self):
        return screen_original_packet(
            self.sample, self.research,
            baseline_sha="f"*64, snapshot=self.snapshot)

    def test_exact_arabic_stays_original_and_model_draft_is_provisional(self):
        original = copy.deepcopy(self.sample["claim_evidence_register"])
        result = self.screening()
        self.assertEqual(result["version"], 2)
        self.assertEqual(result["status"],
                         "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY")
        decision = result["per_claim"][0]
        self.assertEqual(decision["decision"], ADMISSION)
        self.assertEqual(decision["original_passage"], ARABIC)
        self.assertEqual(decision["model_draft_translation"], DRAFT)
        self.assertEqual(decision["translation_source_language"], "ar")
        self.assertEqual(decision["source_classification"], "analysis")
        self.assertTrue(decision["original_imagery_provisionally_admitted"])
        self.assertFalse(decision["translation_fidelity_verified"])
        self.assertIn("MODEL_TRANSLATION_UNVERIFIED_CHECK_BOTH_REVIEWS",
                      decision["semantic_review_flags"])
        self.assertIn("DIRECTIONAL_EFFECT_UNVERIFIED_CHECK_BOTH_REVIEWS",
                      decision["semantic_review_flags"])
        self.assertIn("ORIGINAL_IMAGERY_METHOD_UNVERIFIED_CHECK_BOTH_REVIEWS",
                      decision["semantic_review_flags"])
        self.assertEqual(result["screened_packet"]["pre_review_admission_version"], 2)
        self.assertEqual(self.sample["claim_evidence_register"], original)
        self.assertEqual(result["publication"], "NOT AUTHORIZED")

    def test_missing_or_unverifiable_translation_never_admitted(self):
        for change in (
            ("support_quote_translation", None),
            ("support_quote_translation", "Unrelated weather forecast from another nation."),
            ("translation_status", "INDEPENDENTLY_VERIFIED"),
            ("original_quote_language", None)
        ):
            with self.subTest(change=change):
                original = self.research["evidence"][0].get(change[0])
                self.research["evidence"][0][change[0]] = change[1]
                decision = self.screening()["per_claim"][0]
                self.assertEqual(decision["decision"], REJECT)
                self.assertIn("MISSING_GROUNDED_CROSS_LANGUAGE_TRANSLATION",
                              decision["reasons"])
                self.research["evidence"][0][change[0]] = original

    def test_original_commentary_stays_background_even_with_translation(self):
        original = self.research["evidence"][0]
        original["effect_type"] = "background_context"
        original["observational_method"] = "none"
        result = self.screening()
        self.assertEqual(result["per_claim"][0]["decision"], REJECT)
        self.assertIn("NO_SUBSTANTIVE_OBSERVED_DIRECTION_BASIS",
                      result["per_claim"][0]["reasons"])
        self.assertNotIn(self.sample["evidence"][0],
                         result["screened_packet"]["evidence"])
        self.assertEqual(result["screened_packet"]["background_source_analyses"][0]["id"],
                         self.sample["evidence"][0]["id"])

    def test_rationale_word_mismatch_is_review_flag_not_disqualification(self):
        self.research["evidence"][0]["direction_basis"] = (
            "A theoretical causal hypothesis describes possible vulnerability "
            "mitigation while withholding confidence in security-force loyalty "
            "or any measurable downstream geopolitical effect.")
        decision = self.screening()["per_claim"][0]
        self.assertEqual(decision["decision"], ADMISSION)
        self.assertIn("DIRECTIONAL_EFFECT_UNVERIFIED_CHECK_BOTH_REVIEWS",
                      decision["semantic_review_flags"])

    def test_v4_prompt_requires_fidelity_and_claim_sign_checks(self):
        screened = self.screening()["screened_packet"]
        prompt = _prompt("affirmative", screened, sha(screened),
                         "Closed source-only review.")
        self.assertIn("V4 DUAL SEMANTIC AND MULTILINGUAL REVIEW", prompt)
        self.assertIn("translation_checks", prompt)
        self.assertIn("direction_checks", prompt)
        self.assertIn("background_source_analyses", prompt.lower())
        self.assertEqual(screened["pre_review_admission_version"], 2)

    def test_two_reviewers_cannot_approve_unchecked_translation(self):
        packet = self.screening()["screened_packet"]
        url = packet["evidence"][0]["source"]
        row = {"url": url, "translation_checks": [], "direction_checks": []}
        for role in ("affirmative", "critical"):
            issues = v4_required_interpretation_issues(packet, role, [row])
            self.assertEqual({i["type"] for i in issues},
                             {"v4_translation_not_independently_reviewed",
                              "v4_claim_or_direction_not_substantively_reviewed"})
            verified = {
                "url": url,
                "translation_checks": [{
                    "evidence_id": packet["evidence"][0]["id"],
                    "fidelity": "supported_from_original_language",
                    "assessment": "The original Arabic phrase describes "
                                  "repair work, not verified operational readiness."}],
                "direction_checks": [{
                    "evidence_id": packet["evidence"][0]["id"],
                    "factual_event": "supported_as_qualified",
                    "direction_sign": "warranted_as_qualified",
                    "assessment": "Original image-based reporting is "
                                  "conditionally relevant but warrants cautious interpretation."}]
            }
            issues = v4_required_interpretation_issues(
                packet, role, [verified])
            self.assertEqual(issues, [])

    def test_old_v3_screen_fingerprint_and_prompt_are_unchanged(self):
        from source_pre_review_admissibility import screen_original_packet
        sample, research = fixture()
        v3 = screen_original_packet(
            sample, research, baseline_sha="f"*64, snapshot=SNAPSHOT)
        self.assertEqual(v3["version"], 1)
        self.assertNotIn("semantic_review_flags", v3["per_claim"][0])
        self.assertNotIn("background_source_analyses", v3["screened_packet"])
        from source_research_batches import batch_prompt
        v3p = batch_prompt("regional_multilingual_media",
                           {"version": 3, "date": "2026-10-21",
                            "cutoff_at": "2026-10-21T17:55:46-04:00",
                            "prior_index": []})
        v4p = batch_prompt("regional_multilingual_media",
                           {"version": 4, "date": "2026-10-21",
                            "cutoff_at": "2026-10-21T17:55:46-04:00",
                            "prior_index": []})
        self.assertTrue(v4p.startswith(v3p))
        self.assertNotIn("MANDATORY V4", v3p)
        self.assertIn("MODEL_DRAFT_UNVERIFIED", v4p)


if __name__ == "__main__":
    unittest.main()
