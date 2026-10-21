"""Synthetic quote-limited revisions preserve evidence while blocking fabrication.

All tests run without live sources, OpenAI or publication.
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

from source_claim_narrowing import (
    LIMITED_STATUS, narrow_to_passage, validate_narrowings,
)
from source_research_batches import read_json, sha
from source_review_cycles import (
    conservative_revision, deterministic_review_issues,
    run_alternating_review_cycles,
)
from source_directional_eligibility import eligibility
from test_source_review_cycles import ORIGINAL, REVIEW, packet

NOW = dt.datetime(2026, 10, 21, 16, 0, tzinfo=dt.timezone.utc)


def registered_packet():
    sample = packet()
    claims = []
    for idx, item in enumerate(sample["evidence"]):
        quote = "The original source records a limited statement numbered " + str(idx + 1) + "."
        claims.append({
            "evidence_id": item["id"], "url": item["source"],
            "observation_sha256": hashlib.sha256(
                item["observation"].encode()).hexdigest(),
            "status": "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED",
            "selection_method": "model_supplied_verbatim",
            "proposed_quote": quote, "passage": quote,
            "passage_offset": 12,
            "source_body_sha256": "a" * 64,
            "visible_text_sha256": "b" * 64,
            "retrieved_url": item["source"],
            "semantic_support": "NOT_INDEPENDENTLY_ESTABLISHED",
            "first_publication_verified": False,
            "inspected_at": NOW.isoformat(),
            "original_cutoff": ORIGINAL,
            "inspection_after_original_cutoff": True,
        })
    sample["claim_evidence_register"] = {
        "version": 1, "status": "PASSAGES_ONLY_NOT_APPROVED",
        "baseline_history_sha256": sample["published_history_sha256"],
        "research_snapshot_sha256": "c" * 64,
        "evidence_sha256": sha(sample["evidence"]),
        "claims": claims, "publication": "NOT AUTHORIZED",
    }
    return sample


class PartialClaimCorrectionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="iran-quote-narrow-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.sample = registered_packet()

    def test_partially_supported_claim_is_narrowed_not_excluded(self):
        original = copy.deepcopy(self.sample)
        issues = [
            {"type": "unsupported_observation_details",
             "location": "E-20261021-02; E-20261021-03",
             "reason": "Only the short original statements can be attributed."},
            {"type": "caveat_mistaken_for_substantive_support",
             "location": "E-20261021-04",
             "reason": "The passage is merely a methodological disclaimer."},
        ]
        revised, detail = conservative_revision(self.sample, issues, ORIGINAL)
        self.assertIsNotNone(revised)
        self.assertEqual(original, self.sample)
        evidence = {e["id"]: e for e in revised["evidence"]}
        self.assertNotIn("E-20261021-02", evidence)
        self.assertNotIn("E-20261021-03", evidence)
        self.assertNotIn("E-20261021-01", evidence)  # original source inaccessible
        self.assertNotIn("E-20261021-04", evidence)  # methodological caveat
        quotes = {e["id"]: e for e in revised["background_quotes"]}
        self.assertEqual(set(quotes), {"E-20261021-02", "E-20261021-03"})
        self.assertEqual(quotes["E-20261021-02"]["direction"], "ambiguous")
        self.assertEqual(quotes["E-20261021-02"]["reliability"], "Low")
        self.assertEqual(quotes["E-20261021-02"]["affects"], [])
        self.assertEqual(quotes["E-20261021-02"]["editorial_support_status"],
                         LIMITED_STATUS)
        self.assertFalse(quotes["E-20261021-02"]["editorial_directional_admissible"])
        self.assertIn("limited statement numbered 2",
                      quotes["E-20261021-02"]["observation"])
        self.assertEqual(len(detail["narrowed_evidence_ids"]), 2)
        self.assertTrue(validate_narrowings(revised))
        self.assertFalse(any(
            x["type"] == "claim_passage_not_demonstrated"
            for x in deterministic_review_issues(revised, ORIGINAL)))
        self.assertEqual(revised["source_diversity_guard"]["failures"],
                         ["fewer_than_six_source_observations"])
        self.assertEqual(eligibility(revised)["directional_observations"], 5)
        self.assertEqual(eligibility(revised)["background_quote_ids"],
                         ["E-20261021-02", "E-20261021-03"])
        changes = {r["evidence_id"]: r for r in revised["editorial_narrowings"]}
        self.assertEqual(changes["E-20261021-02"]["original_evidence"],
                         original["evidence"][1])
        self.assertEqual(changes["E-20261021-02"]["revised_evidence"],
                         quotes["E-20261021-02"])

    def test_forged_quote_limited_observation_is_rejected(self):
        revised, _ = conservative_revision(self.sample, [{
            "type": "unsupported_observation_details", "location": "E-20261021-02",
            "reason": "The source only supports a narrower quotation."
        }], ORIGINAL)
        self.assertIsNotNone(revised)
        with self.assertRaisesRegex(ValueError, "unsupported new interpretation"):
            tampered = copy.deepcopy(revised)
            tampered["editorial_narrowings"][0]["revised_evidence"]["observation"] = (
                "A fabricated new fact that is not in the original article")
            validate_narrowings(tampered)
        with self.assertRaisesRegex(ValueError, "differs"):
            tampered = copy.deepcopy(revised)
            tampered["background_quotes"][0]["observation"] = "Invented substantive claim"
            validate_narrowings(tampered)
        with self.assertRaisesRegex(ValueError, "passage"):
            tampered = copy.deepcopy(revised)
            tampered["claim_evidence_register"]["claims"][1]["passage"] = (
                "The model invented this different passage about conditions")
            validate_narrowings(tampered)

    def test_quote_only_evidence_rejected_again_is_excluded_not_rewritten(self):
        first, _ = conservative_revision(self.sample, [{
            "type": "unsupported_observation_details", "location": "E-20261021-02",
            "reason": "Original described facts not supported by excerpt"
        }], ORIGINAL)
        self.assertIsNotNone(first)
        second, _ = conservative_revision(first, [{
            "type": "insufficient_semantic_support", "location": "E-20261021-02",
            "reason": "Even the limited quote lacks any relevance to the event"
        }], ORIGINAL)
        self.assertIsNotNone(second)
        self.assertNotIn("E-20261021-02", [e["id"] for e in second["background_quotes"]])
        self.assertIn("E-20261021-02",
                      [e["id"] for e in second["excluded_evidence"]])
        self.assertEqual(len(second["editorial_narrowings"]), 1)
        self.assertTrue(validate_narrowings(second))

    def test_both_reviews_repeated_on_immutable_narrowed_packet(self):
        calls = []
        def review(prompt, search):
            role = "affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical"
            calls.append((role, "EDITORIAL QUOTE-ONLY" in prompt))
            if len(calls) <= 2:
                return {"approved": False, "issues": [{
                    "type": "unsupported_observation_details",
                    "location": "E-20261021-02; E-20261021-03",
                    "reason": "Claim details beyond the original page quote are not supported"
                }]}, set()
            return {"approved": True, "issues": []}, set()
        result = run_alternating_review_cycles(
            folder=self.folder, sample=self.sample, input_sha=sha(self.sample),
            reviewer=review, now=lambda: NOW,
            common="Closed original sources only.", original_cutoff=ORIGINAL,
            max_rounds=4)
        self.assertEqual([r for r, _ in calls],
                         ["affirmative", "critical", "affirmative", "critical"])
        self.assertEqual([r for _, r in calls], [False, False, True, True])
        self.assertEqual(result["status"], "RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE")
        self.assertEqual(result["rounds"], 2)
        self.assertTrue((self.folder / "source-review-round-01.json").exists())
        self.assertTrue((self.folder / "source-review-round-02-input.json").exists())
        self.assertEqual(result["publication"], "NOT AUTHORIZED")

    def test_preserve_old_failed_outcome_when_resuming_with_narrowed_evidence(self):
        calls = []
        def reviewer(prompt, search):
            role = "affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical"
            calls.append(role)
            if len(calls) <= 2:
                return {"approved": False, "issues": [{
                    "type": "unsupported_observation_details",
                    "location": "E-20261021-02",
                    "reason": "The original observation claimed more than the source said"
                }]}, set()
            return {"approved": True, "issues": []}, set()
        options = dict(
            folder=self.folder, sample=self.sample, input_sha=sha(self.sample),
            reviewer=reviewer, now=lambda: NOW,
            common="Original closed source snapshot only.",
            original_cutoff=ORIGINAL, max_rounds=4)
        previous = run_alternating_review_cycles(
            **options, enable_corrections=False)
        self.assertEqual(previous["rounds"], 1)
        old_file = self.folder / "source-review-cycles-outcome.json"
        original_bytes = old_file.read_bytes()
        # A legacy workflow also preserved why whole-record deletion was blocked.
        (self.folder / "source-review-round-01-blocked.json").write_text(
            json.dumps({"reason": "Prior whole-record deletion was blocked"}))
        completed = run_alternating_review_cycles(**options)
        self.assertEqual(completed["rounds"], 2)
        self.assertEqual(calls,
                         ["affirmative", "critical", "affirmative", "critical"])
        self.assertEqual(old_file.read_bytes(), original_bytes)
        self.assertTrue((self.folder /
                         "source-review-cycles-outcome-revised.json").exists())
        self.assertEqual(
            completed["original_rejected_outcome_sha256"], sha(previous))
        self.assertEqual(
            read_json(self.folder /
                      "source-review-cycles-outcome-revised.json"), completed)
        replay = run_alternating_review_cycles(
            **dict(options, reviewer=lambda *args:
                    self.fail("Resuming must not repeat completed reviews")))
        self.assertEqual(replay, completed)
        self.assertEqual(old_file.read_bytes(), original_bytes)

    def test_insufficient_directions_cannot_pass_even_after_dual_model_approval(self):
        sample = registered_packet()
        for entry in sample["source_quality_audit"]["sources"][1:]:
            entry["access_status"] = "source_unavailable"
        seen = []
        def accept_everything(prompt, search):
            seen.append("affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical")
            return {"approved": True, "issues": []}, set()
        result = run_alternating_review_cycles(
            folder=self.folder, sample=sample, input_sha=sha(sample),
            reviewer=accept_everything, now=lambda: NOW,
            common="Closed original sources only.", original_cutoff=ORIGINAL)
        self.assertEqual(result["status"], "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE")
        self.assertEqual(seen, ["affirmative", "critical"])
        self.assertEqual(result["rounds"], 1)
        self.assertFalse((self.folder / "source-review-round-02-input.json").exists())
        self.assertFalse((self.folder / "source-review-round-02.json").exists())
        terminal = read_json(self.folder / "source-review-round-01-terminal-gate.json")
        self.assertEqual(terminal["status"],
                         "IRREVERSIBLE_EVIDENCE_DEFICIENCY_NO_MORE_PAID_REVIEWS")
        self.assertEqual(terminal["directional_eligibility"]["directional_observations"], 0)
        self.assertIn("missing_required_directional_balance",
                      terminal["directional_eligibility"]["failures"])
        self.assertEqual(result["terminal_evidence_gate"]["blocked_next_review_round"], 2)
        self.assertTrue(result["terminal_evidence_gate"]["new_research_required"])
        self.assertEqual(terminal["publication"], "NOT AUTHORIZED")
        first = self.folder / "source-review-round-01.json"
        self.assertTrue(first.exists())
        self.assertFalse(read_json(first)["both_clean"])
        # Resume must reconstruct existing results without new paid review.
        repeat = run_alternating_review_cycles(
            folder=self.folder, sample=sample, input_sha=sha(sample),
            reviewer=lambda *args: self.fail("No repeat review on terminal gate"),
            now=lambda: NOW, common="Closed original sources only.",
            original_cutoff=ORIGINAL)
        self.assertEqual(result, repeat)

    def test_no_legacy_quote_only_insertion_without_register(self):
        previous = packet()
        previous["editorial_narrowings"] = [{"evidence_id": "E-20261021-02"}]
        with self.assertRaisesRegex(ValueError, "Legacy packet"):
            validate_narrowings(previous)


if __name__ == "__main__":
    unittest.main()
