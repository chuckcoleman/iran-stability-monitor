"""Prospective V10 promising-lead enforcement: synthetic, zero external I/O."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from chatgpt_handoff import validate_source_dossier
from promising_evidence_followup import (
    validate_followup_register, validate_followup_reviews)
from review_receipt import digest
from test_chatgpt_handoff import bundle, CUTOFF


def reseal(dossier):
    """Allow controlled fixture mutation without generating invented hashes."""
    cert = dossier["preforecast_certificate"]
    packet = dossier["source_review_packet"]
    cert["source_packet_sha256"] = digest(packet)
    cert["affirmative_source_review_sha256"] = digest(
        dossier["affirmative_source_review"])
    cert["critical_source_review_sha256"] = digest(
        dossier["critical_source_review"])


def apply_decision_changes(dossier):
    """Bind both synthetic perspectives to modified trial leads."""
    packet = dossier["source_review_packet"]
    leads = packet["promising_evidence_followup"]["leads"]
    for role in ("affirmative", "critical"):
        rows = dossier[role + "_source_review"]["promising_followup_reviews"]
        for i, lead in enumerate(leads):
            rows[i]["triage"] = lead["triage"]
            rows[i]["disposition"] = (
                lead["followup"].get("disposition", "missing") if lead["followup"] else lead["triage"])
            rows[i]["lead_sha256"] = digest(lead)
    reseal(dossier)


class PromisingFollowupTests(unittest.TestCase):
    def test_all_sources_triaged_and_both_reviewed(self):
        before, after, dossier = bundle()
        verdict = validate_source_dossier(dossier, before, after)
        self.assertEqual(verdict["promising_lead_count"], 1)
        self.assertEqual(verdict["triaged_source_count"], 6)
        reg = dossier["source_review_packet"]["promising_evidence_followup"]
        self.assertEqual(len(reg["leads"]), 6)
        self.assertEqual(sum(l["triage"] == "context_only" for l in reg["leads"]), 5)
        self.assertEqual(sum(bool(l["admitted_evidence_ids"]) for l in reg["leads"]), 1)

    def test_missing_or_untracked_followup_always_rejected(self):
        for name in ("missing", "empty", "wrong_asof", "missing_lead",
                     "duplicate", "unknown_url", "blank_rationale", "bad_priority",
                     "unknown_field", "missing_triage", "context_admits_claim"):
            before, after, dossier = bundle()
            p = dossier["source_review_packet"]
            register = p["promising_evidence_followup"]
            leads = register["leads"]
            if name == "missing":
                p.pop("promising_evidence_followup")
            elif name == "empty":
                register["leads"] = []
            elif name == "wrong_asof":
                register["research_as_of"] = "2026-10-24T08:45:00-04:00"
            elif name == "missing_lead":
                leads.pop(2)
            elif name == "duplicate":
                leads[2]["source_url"] = leads[1]["source_url"]
            elif name == "unknown_url":
                leads[2]["source_url"] = "https://unknown.example.org/report"
            elif name == "blank_rationale":
                leads[0]["relevance"] = "Unexplained"
            elif name == "bad_priority":
                leads[0]["priority"] = "highest-risk"
            elif name == "unknown_field":
                leads[0]["waive_followup"] = True
            elif name == "missing_triage":
                leads[0].pop("triage")
            else:
                leads[0]["triage"] = "context_only"
                leads[0]["followup"] = None
            reseal(dossier)
            with self.subTest(case=name), self.assertRaises(ValueError):
                validate_source_dossier(dossier, before, after)

    def test_promising_investigation_cannot_be_missing_or_inadequate(self):
        for name in ("missing_followup", "missing_disposition", "unqualified",
                     "missing_upstream_query", "missing_contrary_query",
                     "duplicated_queries", "same_query", "missing_checked_source",
                     "invented_checked_url", "unregistered_upstream", "unregistered_contrary",
                     "missing_original_source", "post_cutoff", "timezone_missing",
                     "period_missing", "denominator_missing", "method_missing",
                     "reporting_chain_short", "support_short", "counter_short",
                     "limitations_short", "no_final_ids", "held_with_admitted_claim"):
            before, after, dossier = bundle()
            lead = dossier["source_review_packet"]["promising_evidence_followup"]["leads"][0]
            f = lead["followup"]
            if name == "missing_followup":
                lead["followup"] = None
            elif name == "missing_disposition":
                f.pop("disposition")
            elif name == "unqualified":
                f["disposition"] = "automatically_admitted"
            elif name == "missing_upstream_query":
                f["upstream_queries"] = []
            elif name == "missing_contrary_query":
                f["counter_queries"] = []
            elif name == "duplicated_queries":
                f["counter_queries"] *= 2
            elif name == "same_query":
                f["counter_queries"] = list(f["upstream_queries"])
            elif name == "missing_checked_source":
                f["checked_urls"] = []
            elif name == "invented_checked_url":
                f["checked_urls"].append("https://extra.example.org/unregistered")
            elif name == "unregistered_upstream":
                f["upstream_source_urls"] = ["https://extra.example.org/unregistered"]
            elif name == "unregistered_contrary":
                f["contrary_source_urls"] = ["https://extra.example.org/unregistered"]
            elif name == "missing_original_source":
                f["upstream_source_urls"] = []
            elif name == "post_cutoff":
                f["performed_at"] = "2026-10-25T08:46:00-04:00"
            elif name == "timezone_missing":
                f["performed_at"] = "2026-10-25T08:44:00"
            elif name == "period_missing":
                f["scope"]["time_window"] = "Unknown"
            elif name == "denominator_missing":
                f["scope"]["population_or_denominator"] = "?"
            elif name == "method_missing":
                f["scope"]["method_and_inclusions"] = "Not known"
            elif name == "reporting_chain_short":
                f["reporting_chain"] = "Unknown"
            elif name == "support_short":
                f["supporting_findings"] = "Supported"
            elif name == "counter_short":
                f["counterevidence_findings"] = "No contrary data"
            elif name == "limitations_short":
                f["limitations"] = "No limitations"
            elif name == "no_final_ids":
                lead["admitted_evidence_ids"] = []
            else:
                f["disposition"] = "held_unverified"
            apply_decision_changes(dossier)
            with self.subTest(case=name), self.assertRaises(ValueError):
                validate_source_dossier(dossier, before, after)

    def test_both_roles_must_review_every_triage_and_disposition(self):
        for name in ("missing_affirmative", "missing_critical", "one_missing",
                     "duplicate", "unlisted", "missing_field", "wrong_triage",
                     "wrong_disposition", "wrong_lead_hash", "no_decision",
                     "critical_rejects", "issues", "shallow_notes", "no_limitations",
                     "same_perspective_text"):
            before, after, dossier = bundle()
            affirm = dossier["affirmative_source_review"]
            critical = dossier["critical_source_review"]
            if name == "missing_affirmative":
                affirm.pop("promising_followup_reviews")
            elif name == "missing_critical":
                critical.pop("promising_followup_reviews")
            elif name == "one_missing":
                critical["promising_followup_reviews"].pop(3)
            elif name == "duplicate":
                critical["promising_followup_reviews"][2] = copy.deepcopy(
                    critical["promising_followup_reviews"][1])
            elif name == "unlisted":
                critical["promising_followup_reviews"][1]["source_url"] = (
                    "https://extra.example.org/unregistered")
            elif name == "missing_field":
                critical["promising_followup_reviews"][0].pop("lead_sha256")
            elif name == "wrong_triage":
                critical["promising_followup_reviews"][0]["triage"] = "context_only"
            elif name == "wrong_disposition":
                critical["promising_followup_reviews"][0]["disposition"] = "contradicted"
            elif name == "wrong_lead_hash":
                critical["promising_followup_reviews"][0]["lead_sha256"] = "f" * 64
            elif name == "no_decision":
                critical["promising_followup_reviews"][0]["approved"] = None
            elif name == "critical_rejects":
                critical["promising_followup_reviews"][0]["approved"] = False
            elif name == "issues":
                critical["promising_followup_reviews"][0]["issues"] = ["Unresolved issue"]
            elif name == "shallow_notes":
                critical["promising_followup_reviews"][0]["assessment"] = "looks fine"
            elif name == "no_limitations":
                critical["promising_followup_reviews"][0]["limitations"] = "none"
            else:
                critical["promising_followup_reviews"][0]["assessment"] = (
                    affirm["promising_followup_reviews"][0]["assessment"])
            reseal(dossier)
            with self.subTest(case=name), self.assertRaises(ValueError):
                validate_source_dossier(dossier, before, after)

    def test_mutation_of_followup_after_preforecast_seal_fails(self):
        b, a, dossier = bundle()
        dossier["source_review_packet"]["promising_evidence_followup"]["leads"][0][
            "followup"]["counterevidence_findings"] += (
                " A newly inserted claim after the source review was sealed.")
        with self.assertRaisesRegex(ValueError,
                                    "Preforecast source packet|review detached"):
            validate_source_dossier(dossier, b, a)

    def test_context_only_without_new_claims_does_not_impose_evidence_quota(self):
        before, after, dossier = bundle()
        packet = dossier["source_review_packet"]
        register = packet["promising_evidence_followup"]
        by_url = {s["url"] for s in packet["source_quality_audit"]["sources"]}
        self.assertTrue(validate_followup_register(
            register, by_url, packet["evidence"], CUTOFF))
        # The standalone register must accept no promising leads when no new
        # claims are proposed; geopolitical adequacy remains a separate gate.
        empty = copy.deepcopy(register)
        for lead in empty["leads"]:
            lead["triage"] = "context_only"
            lead["followup"] = None
            lead["admitted_evidence_ids"] = []
        self.assertEqual(len(validate_followup_register(empty, by_url, [], CUTOFF)), 6)

    def test_held_promising_lead_can_be_reviewed_without_admitting_it(self):
        b, a, dossier = bundle()
        packet = dossier["source_review_packet"]
        leads = packet["promising_evidence_followup"]["leads"]
        extra = leads[1]
        extra["triage"] = "promising"
        extra["followup"] = copy.deepcopy(leads[0]["followup"])
        extra["followup"]["disposition"] = "held_unverified"
        extra["followup"]["checked_urls"] = [extra["source_url"]]
        extra["followup"]["upstream_source_urls"] = []
        extra["followup"]["contrary_source_urls"] = []
        extra["admitted_evidence_ids"] = []
        apply_decision_changes(dossier)
        self.assertEqual(validate_source_dossier(dossier, b, a)["promising_lead_count"], 2)

    def test_cannot_hide_admitted_claim_in_unreviewed_context(self):
        b, a, dossier = bundle()
        lead = dossier["source_review_packet"]["promising_evidence_followup"]["leads"][0]
        lead["triage"] = "context_only"
        lead["admitted_evidence_ids"] = []
        lead["followup"] = None
        apply_decision_changes(dossier)
        with self.assertRaisesRegex(ValueError, "Every admitted new claim"):
            validate_source_dossier(dossier, b, a)


if __name__ == "__main__":
    unittest.main()
