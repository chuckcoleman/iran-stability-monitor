"""Forward-only v5 regression: precise publisher dates, search effort, and
binding BOTH source reviews to the actual short article-body witnesses.

These are synthetic original-page and tool-search fixtures. A passing example
is never a claim that an actual event, translation or effect is verified.
"""
import copy
import datetime as dt
import hashlib
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from assessment_pipeline import freeze_evidence
from source_directional_eligibility import eligibility
from source_metadata import parse_metadata, headline_publication_dates
from source_pre_review_admissibility import (
    screen_original_packet, actual_search_query_ledger)
from source_research_batches import CATEGORIES, sha, batch_prompt
from source_review_cycles import (
    v4_required_interpretation_issues, _prompt, deterministic_review_issues)
from test_source_pre_review_admissibility import fixture, SNAPSHOT
from test_source_semantic_v4 import ARABIC, ENGLISH, DRAFT, HEADING


def executed_queries():
    return [
        {"search_calls_real": True, "research_category": category,
         "queries_exposed_by_api": [
             f"Original sources {category} Iranian protest risks October 2026",
             f"Original sources {category} Iranian economic recovery stabilization October 2026"
         ]}
        for category in CATEGORIES
    ]


def packet_fixture():
    sample, research = fixture()
    sample["evidence"][0]["observation"] = ENGLISH
    research["evidence"][0]["observation"] = ENGLISH
    research["evidence"][0].update({
        "effect_type": "measured_data",
        "observational_method": "original_satellite_imagery",
        "direction_basis": (
            "This observational claim describes repaired structures, but "
            "the geopolitical effect remains a hypothesis requiring "
            "independent adverse review."),
        "original_quote_language": "ar",
        "support_quote_translation": DRAFT,
        "translation_status": "MODEL_DRAFT_UNVERIFIED",
    })
    sample["source_quality_audit"]["sources"][0]["classification"] = "analysis"
    claim = sample["claim_evidence_register"]["claims"][0]
    claim["passage"] = ARABIC
    claim["proposed_quote"] = ARABIC
    claim["observation_sha256"] = hashlib.sha256(ENGLISH.encode()).hexdigest()
    sample["claim_evidence_register"]["evidence_sha256"] = sha(sample["evidence"])
    snapshot = dict(SNAPSHOT, version=5)
    return sample, research, snapshot


def reviewed_claim(result, *, source_url=None):
    decision = result["per_claim"][0]
    query_ledger = result["screened_packet"]["pre_review_actual_search_queries"]
    source_url = source_url or decision["original_url"]
    text = ("The original published body provides a qualified observation "
            "but neither demonstrates complete restoration nor a certain "
            "effect on the stability of any political institution.")
    return [{
        "url": source_url,
        "translation_checks": [{
            "evidence_id": decision["id"],
            "original_passage": decision["original_passage"],
            "source_body_sha256": decision["source_body_sha256"],
            "fidelity": "supported_from_original_language",
            "assessment": ("This bilingual reviewer asserts that the "
                           "draft matches the literal visible text, "
                           "without inferring political effects.")}],
        "direction_checks": [{
            "evidence_id": decision["id"],
            "original_passage": decision["original_passage"],
            "source_body_sha256": decision["source_body_sha256"],
            "factual_event": "supported_as_qualified",
            "direction_sign": "warranted_as_qualified",
            "assessment": text
        }],
    }], {
        "source_query_balance_review": {
            "raises_queries": [query_ledger[0]["queries"][1]],
            "lowers_queries": [query_ledger[0]["queries"][0]],
            "ambiguous_queries": [],
            "assessment": (
                "Both risk-increasing and potentially stabilizing factors "
                "were queried separately in the original search, and "
                "failure to identify a particular type of event remains "
                "a source-coverage limitation rather than proof of one."
            ),
        }
    }


class PublisherDatelineV5Tests(unittest.TestCase):
    def test_unlabeled_date_inside_generic_div_is_not_article_publication(self):
        html = (f"<html><head><title>{HEADING}</title></head>"
                f"<body><h1>{HEADING}</h1>"
                "<div><span>October 15, 2026</span></div>"
                "<div class='latest-stories'>Related publications</div></body>")
        self.assertEqual(headline_publication_dates(html), [])
        self.assertEqual(parse_metadata(html)["publication_dates"], [])

    def test_heading_date_requires_explicit_context_but_nested_dated_span_passes(self):
        html = (f"<html><head><title>{HEADING}</title></head>"
                f"<body><h1>{HEADING}</h1>"
                "<div class='post__meta'><span class='published-date'>"
                "October 15, 2026</span></div></body>")
        result = parse_metadata(html)
        self.assertEqual(result["publication_dates"], ["2026-10-15"])
        self.assertFalse(result["first_publication_verified"])

    def test_navigation_after_headline_does_not_count_as_publisher_date(self):
        html = (f"<html><head><title>{HEADING}</title></head><body>"
                f"<h1>{HEADING}</h1><nav><time>October 15, 2026"
                "</time></nav></body>")
        self.assertEqual(headline_publication_dates(html), [])


class SearchAndReviewV5Tests(unittest.TestCase):
    def setUp(self):
        self.sample, self.research, self.snapshot = packet_fixture()
        self.calls = executed_queries()

    def screen(self):
        return screen_original_packet(self.sample, self.research,
                                      baseline_sha="f"*64,
                                      snapshot=self.snapshot,
                                      search_calls=self.calls)

    def test_v5_requires_six_actual_query_ledgers_with_provenance(self):
        result = self.screen()
        self.assertEqual(result["version"], 3)
        self.assertEqual(result["status"], "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY")
        self.assertEqual(result["screened_packet"]["pre_review_admission_version"], 3)
        self.assertEqual(len(result["screened_packet"]["pre_review_actual_search_queries"]), 6)
        self.assertEqual([x["category"] for x in
                          result["screened_packet"]["pre_review_actual_search_queries"]],
                         list(CATEGORIES))
        with self.assertRaisesRegex(ValueError, "six source categories"):
            self.calls = self.calls[:-1]
            self.screen()

    def test_v5_freeze_defers_directional_outcome_quota_to_review_gate(self):
        cutoff = dt.datetime.fromisoformat(self.snapshot["cutoff_at"])
        entries = []
        for n in range(6):
            entries.append({
                "event_date": cutoff.date().isoformat(),
                "category": "original_observation",
                "observation": "Synthetic original observation number %d" % n,
                "source": "https://example.org/original/%d" % n,
                "source_title": "Independent synthetic original source %d" % n,
                "publisher": "Independent Publisher %d" % (n % 3),
                "reliability": "Medium", "affects": [],
                "evidence_status": "new",
                "impact_magnitude": "minor",
                "direction": "raises",
            })
        result = {"evidence": entries}
        original = copy.deepcopy(result)
        cites = {e["source"] for e in entries}
        archive = {"evidence": []}
        with self.assertRaisesRegex(ValueError,
                                    "Require raising, lowering, ambiguous"):
            freeze_evidence(result, cites, archive, cutoff.date().isoformat(),
                            cutoff)
        pending = freeze_evidence(
            result, cites, archive, cutoff.date().isoformat(), cutoff,
            provisional_source_only_v5=True)
        self.assertEqual(result, original)
        self.assertEqual(len(pending), 6)
        self.assertEqual({e["direction"] for e in pending}, {"raises"})
        eligibility_record = eligibility({
            "pre_review_admission_version": 3, "evidence": pending})
        self.assertEqual(eligibility_record["failures"], [])
        self.assertEqual(eligibility_record["missing_directions"],
                         ["ambiguous", "lowers"])
        self.assertTrue(eligibility_record[
            "missing_directions_are_coverage_disclosures_not_failures"])

    def test_v5_zero_and_underfilled_evidence_reach_explicit_gate(self):
        cutoff = dt.datetime.fromisoformat(self.snapshot["cutoff_at"])
        with self.assertRaisesRegex(ValueError, "Require 6-30 evidence"):
            freeze_evidence({"evidence": []}, set(), {"evidence": []},
                            cutoff.date().isoformat(), cutoff)
        empty = freeze_evidence({"evidence": []}, set(), {"evidence": []},
            cutoff.date().isoformat(), cutoff,
            provisional_source_only_v5=True)
        self.assertEqual(empty, [])
        record = eligibility({"pre_review_admission_version": 3,
                              "evidence": empty})
        self.assertIn("fewer_than_six_source_observations", record["failures"])
        self.assertIn("fewer_than_three_distinct_publishers", record["failures"])
        self.assertIn("fewer_than_four_new_observations", record["failures"])
        self.assertNotIn("missing_required_directional_balance", record["failures"])
        # The provisional mode NEVER waives individual source provenance.
        row = {"evidence": [{
            "event_date": cutoff.date().isoformat(),
            "category": "synthetic",
            "observation": "A cited-event observation without an actual citation.",
            "source": "https://example.org/uncited-original",
            "source_title": "Synthetic article",
            "publisher": "Synthetic publisher", "reliability": "Medium",
            "evidence_status": "new", "impact_magnitude": "minor",
            "direction": "raises"}]}
        with self.assertRaisesRegex(ValueError, "Research source citations missing"):
            freeze_evidence(row, set(), {"evidence":[]},
                            cutoff.date().isoformat(), cutoff,
                            provisional_source_only_v5=True)
        with self.assertRaisesRegex(ValueError, "Source not verified"):
            freeze_evidence(row, {"https://example.org/unrelated"},
                            {"evidence":[]}, cutoff.date().isoformat(), cutoff,
                            provisional_source_only_v5=True)

    def test_v5_official_policy_action_remains_provisional_not_verified_impact(self):
        """The issuing authority may document its own action, not its results."""
        sample = self.sample
        original = self.research["evidence"][0]
        item = sample["evidence"][0]
        passage = (
            "The agency announced sanctions designating seven named "
            "employees under its authority.")
        observation = (
            "The agency announced sanctions designating seven employees.")
        item["observation"] = observation
        original["observation"] = observation
        original["effect_type"] = "observed_policy_action"
        original["observational_method"] = "none"
        original["support_quote"] = passage
        original["direction_basis"] = (
            "The official declaration establishes the announced designation "
            "only. It does not independently demonstrate economic pressure "
            "or political consequences, which remain hypotheses.")
        source = sample["source_quality_audit"]["sources"][0]
        source["classification"] = "direct_observation"
        source["origin"] = "official_or_advocacy_claim"
        witness = sample["claim_evidence_register"]["claims"][0]
        witness["passage"] = passage
        witness["proposed_quote"] = passage
        witness["observation_sha256"] = hashlib.sha256(
            observation.encode()).hexdigest()
        sample["claim_evidence_register"]["evidence_sha256"] = sha(
            sample["evidence"])

        screened = self.screen()["screened_packet"]
        self.assertEqual(screened["pre_review_admission_version"], 3)
        self.assertIn(item["id"], [
            x["id"] for x in screened["evidence"]])
        self.assertEqual(
            screened["pre_review_claim_decisions"][0]["model_effect_type"],
            "observed_policy_action")
        invariant_issues = deterministic_review_issues(
            screened, self.snapshot["cutoff_at"])
        self.assertNotIn(
            "official_claim_misclassified",
            [x["type"] for x in invariant_issues])
        # Merely being admitted is NOT substantive review or permission
        # to publish: both reviewer roles still have independent duties.
        source_row = [{
            "url": source["url"],
            "direction_checks": [],
            "translation_checks": [],
        }]
        for role in ("affirmative", "critical"):
            issues = v4_required_interpretation_issues(
                screened, role, source_row, None)
            self.assertIn(
                "v4_claim_or_direction_not_substantively_reviewed",
                [x["type"] for x in issues])

        # Claimed consequences/conditions are not the issuer's recorded
        # policy act, so they retain the prior fail-closed classification.
        screened["pre_review_claim_decisions"][0][
            "model_effect_type"] = "reported_event"
        invariant_issues = deterministic_review_issues(
            screened, self.snapshot["cutoff_at"])
        self.assertIn(
            "official_claim_misclassified",
            [x["type"] for x in invariant_issues])

    def test_v5_no_longer_requires_observed_event_in_all_three_directions(self):
        for index, row in enumerate(self.sample["evidence"]):
            row["direction"] = "raises"
            self.research["evidence"][index]["direction"] = "raises"
        self.sample["claim_evidence_register"]["evidence_sha256"] = sha(
            self.sample["evidence"])
        result = self.screen()
        count = result["directional_candidate_counts"]
        self.assertEqual(count["version"], 2)
        self.assertEqual(count["present_directions"], ["raises"])
        self.assertEqual(count["missing_directions"], ["ambiguous", "lowers"])
        self.assertEqual(count["failures"], [])
        self.assertEqual(
            count["direction_observation_policy"],
            "TWO_SIDED_SEARCH_REQUIRED_NO_OBSERVED_DIRECTION_QUOTA")
        legacy = copy.deepcopy(result["screened_packet"])
        legacy["pre_review_admission_version"] = 2
        self.assertIn("missing_required_directional_balance",
                      eligibility(legacy)["failures"])

    def test_v5_prompt_additions_leave_actual_v4_prompt_prefix_unchanged(self):
        template = {"prior_index": [], "date": "2026-10-21",
                    "cutoff_at": "2026-10-21T17:55:46-04:00"}
        old = batch_prompt(CATEGORIES[0], dict(template, version=4))
        current = batch_prompt(CATEGORIES[0], dict(template, version=5))
        self.assertTrue(current.startswith(old))
        self.assertIn("MANDATORY V4", old)
        self.assertNotIn("V5 DIRECTIONAL SEARCH", old)
        self.assertIn("V5 DIRECTIONAL SEARCH", current)
        packet = self.screen()["screened_packet"]
        prompt = _prompt("critical", packet, sha(packet), "Source-only audit.")
        self.assertIn("V5 SOURCE-BALANCE", prompt)
        self.assertIn("source_body_sha256", prompt)
        self.assertIn("source_query_balance_review", prompt)

    def test_both_reviewers_must_bind_exact_page_quote_hash_and_real_queries(self):
        result = self.screen()
        packet = result["screened_packet"]
        # Focus on one source to exercise reviewer-specific source fields;
        # the whole packet is retained in the real paid review.
        packet["evidence"] = packet["evidence"][:1]
        rows, response = reviewed_claim(result)
        for role in ("affirmative", "critical"):
            self.assertEqual(
                v4_required_interpretation_issues(packet, role, rows, response),
                [])
        forged = copy.deepcopy(rows)
        forged[0]["direction_checks"][0]["source_body_sha256"] = "0"*64
        issues = v4_required_interpretation_issues(
            packet, "affirmative", forged, response)
        self.assertIn("v4_claim_or_direction_not_substantively_reviewed",
                      [issue["type"] for issue in issues])
        forged = copy.deepcopy(rows)
        forged[0]["translation_checks"][0]["original_passage"] = (
            "A fabricated passage in the wrong source language.")
        issues = v4_required_interpretation_issues(
            packet, "critical", forged, response)
        self.assertIn("v4_translation_not_independently_reviewed",
                      [issue["type"] for issue in issues])

    def test_fake_or_reused_search_queries_cannot_approve(self):
        result = self.screen()
        packet = result["screened_packet"]
        packet["evidence"] = packet["evidence"][:1]
        rows, response = reviewed_claim(result)
        fake = copy.deepcopy(response)
        fake["source_query_balance_review"]["raises_queries"] = [
            "Invented query that the web-search API did not execute"]
        issues = v4_required_interpretation_issues(
            packet, "critical", rows, fake)
        self.assertIn("v5_two_sided_search_not_independently_reviewed",
                      [issue["type"] for issue in issues])
        reused = copy.deepcopy(response)
        reused["source_query_balance_review"]["raises_queries"] = (
            reused["source_query_balance_review"]["lowers_queries"])
        issues = v4_required_interpretation_issues(
            packet, "affirmative", rows, reused)
        self.assertIn("v5_two_sided_search_not_independently_reviewed",
                      [issue["type"] for issue in issues])

    def test_conflicting_publisher_dates_require_explicit_review(self):
        self.sample["source_quality_audit"]["sources"][0][
            "publication_dates_from_page"] = ["2026-10-18", "2026-10-20"]
        result = self.screen()
        packet = result["screened_packet"]
        decision = result["per_claim"][0]
        self.assertTrue(decision["publisher_date_conflict"])
        self.assertIn("CONFLICTING_PUBLISHER_DATES_REVIEW_REQUIRED",
                      decision["semantic_review_flags"])
        packet["evidence"] = packet["evidence"][:1]
        rows, response = reviewed_claim(result)
        issues = v4_required_interpretation_issues(
            packet, "affirmative", rows, response)
        self.assertIn("v5_publisher_date_conflict_unresolved",
                      [issue["type"] for issue in issues])
        rows[0]["date_checks"] = [{
            "evidence_id": decision["id"],
            "disposition": "reconciled_or_qualified",
            "assessment": ("The conflicting publisher dates were assessed "
                           "as possible revision vs original issuance; "
                           "the uncertainty is explicitly retained.")
        }]
        self.assertEqual(
            v4_required_interpretation_issues(packet, "critical", rows, response),
            [])


if __name__ == "__main__":
    unittest.main()
