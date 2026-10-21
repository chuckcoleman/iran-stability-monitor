"""Offline admissibility cases: page access, source dates, quote relevance,
direction basis, event chronology, recovery and quote-only separation.

No network request or model call is made by these tests.
"""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from source_pre_review_admissibility import (
    ADMISSION, REJECT, screen_original_packet, screen_or_restore,
)
from source_research_batches import sha, read_json
from source_review_cycles import run_alternating_review_cycles
from test_source_claim_narrowing import registered_packet
from test_source_review_cycles import ORIGINAL

STAMP = dt.datetime(2026, 10, 21, 15, tzinfo=dt.timezone.utc)
SNAPSHOT = {
    "version": 3, "cutoff_at": ORIGINAL,
    "snapshot_sha256": "c" * 64, "history_sha256": "f" * 64,
}


def fixture():
    sample = registered_packet()
    sample["research_as_of"] = ORIGINAL
    sample["published_history_sha256"] = "f" * 64
    original = []
    for i, entry in enumerate(sample["evidence"]):
        ident = entry["id"]
        quote = sample["claim_evidence_register"]["claims"][i]["passage"]
        entry["event_date"] = "2026-10-20"
        entry["category"] = "regional_multilingual_media"
        entry["observation"] = (
            "Original source records limited statement numbered " +
            str(i+1) + " about reported change.")
        entry["evidence_status"] = "new"
        source = sample["source_quality_audit"]["sources"][i]
        source.update({
            "source_retrieval_status": "retrieved",
            "access_status": "source_metadata_captured",
            "classification": "attributed_claim",
            "origin": "original_reporting",
            "publication_dates_from_page": ["2026-10-19"],
            "source_publication_time": None
        })
        row = sample["claim_evidence_register"]["claims"][i]
        row["observation_sha256"] = hashlib.sha256(
            entry["observation"].encode()).hexdigest()
        basis = (
            "The original source records limited statement numbered " +
            str(i+1) +
            "; the researcher proposes this direction provisionally, "
            "but independent fact and sign checks are required."
        )
        original.append(dict(copy.deepcopy(entry),
                             effect_type="reported_event",
                             direction_basis=basis,
                             support_quote=quote))
    sample["claim_evidence_register"]["evidence_sha256"] = sha(sample["evidence"])
    sample["claim_evidence_register"]["research_snapshot_sha256"] = (
        SNAPSHOT["snapshot_sha256"])
    return sample, {"evidence": original}


class PreReviewAdmissibilityTests(unittest.TestCase):
    def setUp(self):
        self.sample, self.research = fixture()
        self.work = tempfile.TemporaryDirectory(prefix="source-admissibility-")
        self.addCleanup(self.work.cleanup)
        self.folder = Path(self.work.name)

    def screen(self):
        return screen_original_packet(self.sample, self.research,
                                      baseline_sha="f"*64, snapshot=SNAPSHOT)

    def test_narrow_quote_grounded_event_becomes_provisional_not_verified(self):
        audit = self.screen()
        self.assertEqual(audit["status"], "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY",
                         [(x["id"], x["reasons"]) for x in audit["per_claim"]])
        self.assertEqual(len(audit["admitted_original_ids"]), 9)
        self.assertEqual(audit["held_original_ids"], [])
        self.assertEqual(audit["source_review_requests"], "PERMITTED_AFTER_SCREEN")
        self.assertEqual(audit["directional_candidate_counts"]["failures"], [])
        self.assertTrue(all(x["decision"] == ADMISSION for x in audit["per_claim"]))
        self.assertTrue(all(
            x["directional_semantic_verification"] ==
            "NOT_ESTABLISHED_DUAL_REVIEW_REQUIRED" and
            x["first_publication_verified"] is False
            for x in audit["per_claim"]))
        self.assertEqual(audit["screened_packet"]["evidence"],
                         self.sample["evidence"])
        self.assertEqual(audit["publication"], "NOT AUTHORIZED")

    def test_missing_original_and_questionable_quote_hold_out_before_review(self):
        witness = self.sample["claim_evidence_register"]["claims"][0]
        witness["status"] = "NO_RELEVANT_ORIGINAL_PASSAGE"
        witness["passage"] = None
        witness["passage_offset"] = None
        witness["source_body_sha256"] = None
        witness["visible_text_sha256"] = None
        self.sample["source_quality_audit"]["sources"][1][
            "access_status"] = "source_unavailable"
        self.sample["source_quality_audit"]["sources"][1][
            "source_retrieval_status"] = "unavailable"
        decision = self.screen()
        self.assertEqual(len(decision["held_original_ids"]), 2)
        self.assertEqual(len(decision["admitted_original_ids"]), 7)
        reasons = {x["id"]: x["reasons"] for x in decision["per_claim"]}
        self.assertIn("NO_EXACT_RETRIEVED_ORIGINAL_BODY_PASSAGE",
                      reasons["E-20261021-01"])
        self.assertIn("ORIGINAL_SOURCE_METADATA_UNAVAILABLE",
                      reasons["E-20261021-02"])
        self.assertEqual(decision["screened_packet"]["evidence"][0]["id"],
                         "E-20261021-03")
        self.assertEqual(
            decision["screened_packet"]["pre_review_held_original_evidence"],
            self.sample["evidence"][:2])

    def test_same_day_unproven_time_and_old_event_are_not_admitted(self):
        self.sample["source_quality_audit"]["sources"][0][
            "publication_dates_from_page"] = ["2026-10-21"]
        self.sample["evidence"][1]["event_date"] = "2026-05-01"
        self.research["evidence"][1]["event_date"] = "2026-05-01"
        self.sample["claim_evidence_register"]["evidence_sha256"] = sha(
            self.sample["evidence"])
        result = self.screen()
        status = {x["id"]: x for x in result["per_claim"]}
        self.assertIn("SAME_DAY_PUBLISHER_DATE_NO_PRE_CUTOFF_TIME",
                      status["E-20261021-01"]["reasons"])
        self.assertIn("OLD_EVENT_CONTEXT_ONLY",
                      status["E-20261021-02"]["reasons"])
        self.assertFalse(status["E-20261021-02"]["first_publication_verified"])

    def test_analytical_opinion_and_missing_direction_basis_do_not_count(self):
        self.research["evidence"][0]["effect_type"] = "analysis_or_forecast"
        self.research["evidence"][1]["direction_basis"] = (
            "A plausible opinion stated without sharing any specific "
            "language from the original quoted page.")
        self.sample["source_quality_audit"]["sources"][2]["classification"] = "analysis"
        audit = self.screen()
        self.assertEqual(len(audit["admitted_original_ids"]), 6)
        reasons = {x["id"]: x["reasons"] for x in audit["per_claim"]}
        self.assertIn("NO_SUBSTANTIVE_OBSERVED_DIRECTION_BASIS",
                      reasons["E-20261021-01"])
        self.assertIn("DIRECTION_REASON_NOT_GROUNDED_IN_PASSAGE_TEXT",
                      reasons["E-20261021-02"])
        self.assertIn("ANALYSIS_SYNDICATION_OR_UNVERIFIED_CLASS",
                      reasons["E-20261021-03"])
        # A held-out analytical quote remains visible in audit but never in
        # the review's counted observations.
        self.assertNotIn("E-20261021-03", [
            x["id"] for x in audit["screened_packet"]["evidence"]])

    def test_missing_direction_is_an_immediate_no_review_gate(self):
        for idx in (0, 3, 6):  # Three proposed raises observations
            self.research["evidence"][idx]["effect_type"] = "background_context"
        result = self.screen()
        self.assertEqual(result["status"],
                         "PRE_REVIEW_ADMISSIBILITY_BLOCKED_NO_PAID_REVIEWS")
        self.assertEqual(result["source_review_requests"], "NOT_PERMITTED")
        self.assertIn("missing_required_directional_balance",
                      result["directional_candidate_counts"]["failures"])
        self.assertEqual(result["directional_candidate_counts"]["missing_directions"],
                         ["raises"])
        self.assertFalse(result["screened_packet"]["background_quotes"]
                         if "background_quotes" in result["screened_packet"]
                         else False)
        self.assertEqual(len(result["held_original_ids"]), 3)
        self.assertEqual(result["required_next_action"],
                         "NEW_DATED_SOURCE_RESEARCH_SNAPSHOT_WITH_BETTER_ORIGINAL_EVIDENCE")

    def test_reconciles_coverage_and_preserves_original_quality_claims(self):
        self.sample["coverage"] = [
            {"category": "regional_multilingual_media",
             "original_urls": [x["source"] for x in
                               self.sample["evidence"][:2]],
             "queries": ["Real source search"], "outcome": "eligible_reporting_found",
             "limitations": "The category had originally claimed source evidence."}]
        for item in self.research["evidence"][:2]:
            item["effect_type"] = "background_context"
        result = self.screen()
        row = result["screened_packet"]["coverage"][0]
        self.assertEqual(row["pre_review_admitted_evidence_ids"], [])
        self.assertEqual(row["pre_review_original_outcome"],
                         "eligible_reporting_found")
        self.assertEqual(row["outcome"], "inaccessible_or_incomplete")
        self.assertEqual(row["original_urls"],
                         self.sample["coverage"][0]["original_urls"])
        sources = result["screened_packet"]["source_quality_audit"]["sources"]
        self.assertEqual([s["role"] for s in sources[:3]],
                         ["coverage_context_only", "coverage_context_only",
                          "new_evidence"])
        self.assertEqual(sources[0]["pre_review_original_role"], "new_evidence")
        self.assertEqual(self.sample["source_quality_audit"]["sources"][0][
                         "role"], "new_evidence")

    def test_preserved_checkpoint_reuses_no_model_or_network(self):
        first = screen_or_restore(
            self.folder, self.sample, self.research,
            baseline_sha="f"*64, snapshot=SNAPSHOT)
        checkpoint = self.folder / "source-pre-review-admissibility.json"
        original = checkpoint.read_bytes()
        second = screen_or_restore(
            self.folder, self.sample, self.research,
            baseline_sha="f"*64, snapshot=SNAPSHOT)
        self.assertEqual(first, second)
        self.assertEqual(checkpoint.read_bytes(), original)
        tampered = json.loads(original)
        tampered["screened_review_input_sha256"] = "0"*64
        checkpoint.write_text(json.dumps(tampered))
        with self.assertRaisesRegex(ValueError, "screening differs"):
            screen_or_restore(self.folder, self.sample, self.research,
                              baseline_sha="f"*64, snapshot=SNAPSHOT)

    def test_review_pair_runs_only_on_screened_version(self):
        result = screen_or_restore(self.folder, self.sample, self.research,
                                   baseline_sha="f"*64, snapshot=SNAPSHOT)
        self.assertEqual(result["status"],
                         "PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY")
        # Save the original closed input so the review can authenticate the
        # screened digest against the previous source provenance.
        calls = []
        def reviewer(prompt, search):
            role = ("affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical")
            calls.append((role, "V3 PRE-REVIEW ADMISSIBILITY" in prompt))
            return {"approved": True, "issues": []}, set()
        from source_research_batches import save_new
        save_new(self.folder / "source-review-input.json", {
            "sample": self.sample, "input_sha256": sha(self.sample),
            "publication": "NOT AUTHORIZED"})
        reviewed = run_alternating_review_cycles(
            folder=self.folder, sample=result["screened_packet"],
            input_sha=result["screened_review_input_sha256"],
            reviewer=reviewer, now=lambda: STAMP,
            common="Closed source-only evidence.", original_cutoff=ORIGINAL,
            max_rounds=2)
        self.assertEqual(calls, [("affirmative", True), ("critical", True)])
        self.assertEqual(reviewed["status"],
                         "RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE")
        self.assertEqual(reviewed["publication"], "NOT AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
