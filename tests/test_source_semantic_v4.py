"""New-only publisher date witnesses and bilingual, semantically cautious v4 evidence.

These are offline tests: no publication, no paid model use, no source HTTP.
The exact original v3 review and research snapshots remain immutable.
"""
import copy
import hashlib
import tempfile
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from source_metadata import parse_metadata, heading_date_witnesses
from source_pre_review_admissibility import screen_original_packet, screen_or_restore, ADMISSION, REJECT
from source_review_cycles import run_alternating_review_cycles
from source_research_batches import sha
from test_source_pre_review_admissibility import fixture, SNAPSHOT


V4 = dict(SNAPSHOT, version=4)


def screened():
    original, research = fixture()
    return original, research


class PublisherDateV4Tests(unittest.TestCase):
    def test_treasury_heading_date_is_publisher_reported_not_verified(self):
        page = """<html><head><title>Operation Economic Outcast | Treasury</title></head>
          <body><nav>October 12, 2026</nav><main>
          <h1>Operation Economic Outcast Targets Banking Architecture</h1>
          <div class="date">October 15, 2026</div>
          <p>Today OFAC designated seven employees. Older action was on June 4, 2026.</p>
          <footer><p>October 25, 2026</p></footer>
          </main></body></html>"""
        old = parse_metadata(page)
        self.assertEqual(old["publication_dates"], [])
        self.assertNotIn("publication_date_witnesses", old)
        new = parse_metadata(page, include_visible_heading_date=True)
        self.assertEqual(new["publication_dates"], ["2026-10-15"])
        self.assertEqual(new["source_publication_time"], None)
        self.assertFalse(new["publication_date_conflict"])
        self.assertEqual(new["publication_date_status"],
                         "VISIBLE_ARTICLE_HEADING_DATE_PUBLISHER_REPORTED_ONLY")
        self.assertEqual(len(new["publication_date_witnesses"]), 1)
        witness = new["publication_date_witnesses"][0]
        self.assertEqual(witness["visible_text"], "October 15, 2026")
        self.assertTrue(witness["publisher_reported_only"])
        self.assertFalse(witness["first_publication_independently_verified"])

    def test_conflict_and_body_dates_cannot_supply_publisher_provenance(self):
        conflict = """<meta property="article:published_time"
                            content="2026-10-18T12:00:00Z">
          <h1>Article title</h1><div>October 15, 2026</div>
          <p>Story report mentions October 15.</p>"""
        result = parse_metadata(conflict, include_visible_heading_date=True)
        self.assertTrue(result["publication_date_conflict"])
        self.assertEqual(result["publication_dates"], ["2026-10-18"])
        self.assertEqual(result["publication_date_status"],
                         "CONFLICTING_PUBLISHER_DATE_WITNESSES")
        body_date = """<h1>Government article title</h1>
            <p>October 15, 2026</p><p>Body event October 10, 2026</p>"""
        result = parse_metadata(body_date, include_visible_heading_date=True)
        self.assertEqual(result["publication_dates"], [])
        self.assertEqual(result["publication_date_witnesses"], [])

    def test_heading_markup_datetime_keeps_only_day_not_fake_clock(self):
        text = """<h1>Real news article</h1>
          <time datetime="2026-10-15">October 15, 2026</time>
          <p>The actual report begins here.</p>"""
        record = parse_metadata(text, include_visible_heading_date=True)
        self.assertEqual(record["publication_dates"], ["2026-10-15"])
        self.assertIsNone(record["source_publication_time"])
        self.assertEqual({x["date"] for x in record["publication_date_witnesses"]},
                         {"2026-10-15"})

    def test_multiple_visible_heading_days_not_silently_resolved(self):
        text = """<h1>Article</h1><div>October 15, 2026</div>
          <time datetime="2026-10-16">October 16, 2026</time>
          <p>Article text starts.</p>"""
        row = parse_metadata(text, include_visible_heading_date=True)
        self.assertTrue(row["publication_date_conflict"])
        self.assertEqual(row["publication_dates"], [])


class BilingualV4ScreenTests(unittest.TestCase):
    def setUp(self):
        self.packet, self.research = screened()

    def screen(self):
        return screen_original_packet(self.packet, self.research,
                                      baseline_sha="f"*64, snapshot=V4)

    def test_valid_factual_quote_does_not_require_shared_directional_words(self):
        # Historical v3 kept this lexical mismatch out. V4 identifies it as
        # an explicit unverified reasoning obligation for both reviewers.
        self.research["evidence"][0]["direction_basis"] = (
            "An event occurred but the political consequence remains "
            "an interpretation not demonstrated by the quoted factual assertion.")
        out = self.screen()
        self.assertEqual(out["status"], "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY")
        self.assertEqual(out["version"], 2)
        self.assertIn("E-20261021-01",
                      out["screened_packet"]["pre_review_rationale_review_required"])
        self.assertEqual(out["per_claim"][0]["reasons"], [])
        self.assertIn("DIRECTIONAL_RATIONALE_REQUIRES_SEMANTIC_REVIEW",
                      out["per_claim"][0]["review_flags"])
        self.assertEqual(out["per_claim"][0]["directional_semantic_verification"],
                         "NOT_ESTABLISHED_DUAL_REVIEW_REQUIRED")

    def make_arabic(self):
        quote = "إلى جانب أعمال ترميم في ملاجئ للطائرات تعرضت للقصف خلال الحرب"
        claim = ("Al Jazeera reported restoration of bombed aircraft shelters "
                 "visible in satellite imagery.")
        self.packet["evidence"][0]["observation"] = claim
        witness = self.packet["claim_evidence_register"]["claims"][0]
        witness["passage"] = quote
        witness["proposed_quote"] = quote
        witness["observation_sha256"] = hashlib.sha256(claim.encode()).hexdigest()
        self.packet["claim_evidence_register"]["evidence_sha256"] = sha(
            self.packet["evidence"])
        row = self.packet["source_quality_audit"]["sources"][0]
        row["classification"] = "analysis"
        row["origin"] = "original_reporting"
        original = self.research["evidence"][0]
        original["observation"] = claim
        original["effect_type"] = "reported_event"
        original["original_reporting_method"] = "satellite_imagery"
        original["methodology_description"] = (
            "Publisher used original satellite-image comparisons to identify "
            "physical work at airport structures, not operational readiness.")
        original["passage_language"] = "ar"
        original["passage_translation"] = (
            "Alongside restoration works in aircraft shelters damaged by bombing "
            "during the war.")
        return quote

    def test_arabic_original_and_translation_are_provisional_not_certified(self):
        quote = self.make_arabic()
        out = self.screen()
        first = out["per_claim"][0]
        self.assertEqual(first["decision"], ADMISSION, first["reasons"])
        self.assertIn("BILINGUAL_SEMANTIC_REVIEW_REQUIRED", first["review_flags"])
        self.assertIn("ANALYTICAL_SOURCE_ORIGINAL_IMAGERY_METHOD_REVIEW_REQUIRED",
                      first["review_flags"])
        self.assertEqual(
            first["translation_annotation"]["original_quote_sha256"],
            hashlib.sha256(quote.encode()).hexdigest())
        self.assertEqual(first["translation_annotation"][
            "translation_provenance"], "UNVERIFIED_MODEL_PROPOSAL")
        self.assertFalse(first["translation_annotation"][
            "factual_translation_certified"])
        self.assertIn("E-20261021-01",
                      out["screened_packet"]["pre_review_translation_review_required"])

    def test_missing_translation_or_unsourced_analytical_context_still_blocked(self):
        self.make_arabic()
        self.research["evidence"][0]["passage_translation"] = None
        out = self.screen()
        self.assertEqual(out["per_claim"][0]["decision"], REJECT)
        self.assertIn("ORIGINAL_LANGUAGE_TRANSLATION_NOT_AUDITABLE",
                      out["per_claim"][0]["reasons"])
        self.research["evidence"][0]["passage_translation"] = (
            "Al Jazeera reported restoration in aircraft shelters.")
        self.research["evidence"][0]["original_reporting_method"] = "none"
        out = self.screen()
        self.assertIn("ANALYSIS_SYNDICATION_OR_UNVERIFIED_CLASS",
                      out["per_claim"][0]["reasons"])

    def test_official_action_reclassified_only_in_screened_review_copy(self):
        item = self.research["evidence"][0]
        item["effect_type"] = "observed_policy_action"
        src = self.packet["source_quality_audit"]["sources"][0]
        src["origin"] = "official_or_advocacy_claim"
        src["classification"] = "direct_observation"
        out = self.screen()
        self.assertIn("E-20261021-01",
                      out["screened_packet"][
                          "pre_review_official_action_review_required"])
        screened_source = out["screened_packet"][
            "source_quality_audit"]["sources"][0]
        self.assertEqual(screened_source["classification"], "attributed_claim")
        self.assertEqual(screened_source["pre_review_original_classification"],
                         "direct_observation")
        self.assertEqual(src["classification"], "direct_observation")

    def test_existing_v3_packet_remains_exactly_legacy_semantics(self):
        self.research["evidence"][0]["direction_basis"] = (
            "An abstract interpretation about political consequences without "
            "any of the distinguishing terminology used by the quoted source.")
        result = screen_original_packet(
            self.packet, self.research, baseline_sha="f"*64,
            snapshot=SNAPSHOT)
        self.assertEqual(result["version"], 1)
        self.assertIn("DIRECTION_REASON_NOT_GROUNDED_IN_PASSAGE_TEXT",
                      result["per_claim"][0]["reasons"])
        self.assertNotIn("review_flags", result["per_claim"][0])


class MandatorySemanticReviewerTests(unittest.TestCase):
    def setUp(self):
        self.packet, self.research = screened()
        # Ensure all nine source candidates pass ordinary factual checks but
        # the first one's political-direction inference requires reviewers.
        self.research["evidence"][0]["direction_basis"] = (
            "A political consequence may be inferred but does not directly "
            "follow from the short published factual event description.")
        self.folder_owner = tempfile.TemporaryDirectory(prefix="iran-v4-review-")
        self.addCleanup(self.folder_owner.cleanup)
        self.folder = Path(self.folder_owner.name)
        self.screen = screen_or_restore(
            self.folder, self.packet, self.research, baseline_sha="f"*64,
            snapshot=V4)
        self.assertEqual(self.screen["status"],
                         "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY")

    def run_reviews(self, *, with_explanation):
        seen = []
        def reviewer(prompt, search):
            self.assertFalse(search)
            role = ("affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical")
            seen.append(role)
            self.assertIn("V4 FACTUAL/SEMANTIC REVIEW", prompt)
            reviews = [{
                "id": "E-20261021-01",
                "observation_supported": True,
                "direction_supported": True,
                "assessment": (
                    "The exact source passage supports the factual event; "
                    "its directional implication remains a separate inference "
                    "evaluated here explicitly by this independent reviewer.")
            }] if with_explanation else []
            return {"approved": True, "issues": [],
                    "source_reviews": [],
                    "directional_reviews": reviews}, set()
        outcome = run_alternating_review_cycles(
            folder=self.folder,
            sample=self.screen["screened_packet"],
            input_sha=self.screen["screened_review_input_sha256"],
            reviewer=reviewer,
            now=lambda: __import__("datetime").datetime(
                2026, 10, 21, 15, tzinfo=__import__("datetime").timezone.utc),
            common="No scored forecasts, only source review.",
            original_cutoff=V4["cutoff_at"], max_rounds=1,
            enforce_guards=True, enable_corrections=False)
        self.assertEqual(seen, ["affirmative", "critical"])
        return outcome

    def test_two_explicit_directional_reviews_are_required(self):
        result = self.run_reviews(with_explanation=True)
        self.assertEqual(result["status"],
                         "RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE")
        self.assertEqual(result["review_rounds"][0]["both_clean"], True)

    def test_model_global_approval_cannot_waive_semantic_review(self):
        result = self.run_reviews(with_explanation=False)
        self.assertEqual(result["status"],
                         "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE")
        self.assertEqual(result["review_rounds"][0]["both_clean"], False)
        with (self.folder/"source-review-round-01.json").open() as f:
            reviewed = __import__("json").load(f)
        self.assertTrue(any(x["type"] == "missing_independent_semantic_review"
                            for x in reviewed["deterministic_issues"]))
