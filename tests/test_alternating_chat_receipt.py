"""Fail-closed prospective affirmative -> critical review-cycle receipt tests."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from automation_fixtures import fixture
from assessment_pipeline import freeze_evidence, assemble
from review_receipt import checked_receipt, digest
from report_section_review import report_inventory

class AlternatingReviewTests(unittest.TestCase):
    def setUp(self):
        self.before, analysis, evidence, self.opened = fixture()
        cutoff = self.opened - dt.timedelta(seconds=10)
        ledger = freeze_evidence({"evidence": evidence},
                                 {e["source"] for e in evidence},
                                 self.before["updates"][-1],
                                 self.opened.date().isoformat(), cutoff)
        self.draft = copy.deepcopy(self.before)
        self.draft["updates"].append(assemble(
            self.before, analysis, ledger, cutoff, self.opened,
            self.opened + dt.timedelta(seconds=1)))
        self.after = copy.deepcopy(self.draft)
        self.after["updates"][-1]["publication_time"] = (
            self.opened + dt.timedelta(minutes=5)).isoformat()
        self.hash = digest(self.draft)
        self.locked = copy.deepcopy(analysis["forecasts"])
        self.lock_hash = digest(self.locked)
        self.times = [
            (self.opened + dt.timedelta(seconds=i)).isoformat()
            for i in (3, 4, 5, 6)
        ]
        self.round = {
            "round": 1, "draft_sha256": self.hash,
            "forecast_sha256": self.lock_hash,
            "validation": {"passed": True, "completed_at": self.times[0]},
            "affirmative": {
                "approved": True, "issues": [], "draft_sha256": self.hash,
                "completed_at": self.times[1]},
            "critical": {
                "approved": True, "issues": [], "draft_sha256": self.hash,
                "completed_at": self.times[2]},
            "post_review_validation": {
                "passed": True, "completed_at": self.times[3]}
        }
        inv = report_inventory(self.draft["updates"][-1])
        self.section_reviews = {
            section: {
                "items": list(items),
                "affirmative": {
                    "draft_sha256": self.hash, "approved": True, "issues": [],
                    "test_note": "Synthetic affirmative test checks the supporting details for " + section},
                "critical": {
                    "draft_sha256": self.hash, "approved": True, "issues": [],
                    "test_note": "Synthetic adversarial test challenges unsupported conclusions in " + section}
            } for section, items in inv.items()
        }
        self.round["section_reviews"] = copy.deepcopy(self.section_reviews)
        self.section_sha = digest(self.section_reviews)
        self.report = (
            "# Two-perspective ChatGPT review\n"
            "Both review perspectives are from one ChatGPT session.\n"
            "Affirmative verdict: approved=true; issues=[]; draft_sha256=" + self.hash + "\n"
            "Critical verdict: approved=true; issues=[]; draft_sha256=" + self.hash + "\n"
            "Section review matrix SHA-256: " + self.section_sha + "\n"
            + "".join("### " + section + "\n" for section in inv)
        ).encode()
        self.receipt = {
            "version": 3,
            "origin": "chatgpt_alternating",
            "review_mode": "affirmative_then_critical_chat",
            "reviewer_provenance": "one_chatgpt_session_two_perspectives",
            "status": "CLEAN",
            "date": self.opened.date().isoformat(),
            "baseline_sha256": digest(self.before),
            "candidate_sha256": digest(self.after),
            "record_sha256": digest(self.after["updates"][-1]),
            "report_sha256": hashlib.sha256(self.report).hexdigest(),
            "report_section_review_sha256": self.section_sha,
            "review_completed_at": self.times[2],
            "approval": {
                "status": "CLEAN", "round": 1,
                "draft_sha256": self.hash,
                "forecast_sha256": self.lock_hash,
                "locked_forecasts": self.locked,
                "affirmative": {
                    "approved": True, "issues": [], "draft_sha256": self.hash},
                "critical": {
                    "approved": True, "issues": [], "draft_sha256": self.hash},
                "rounds": [copy.deepcopy(self.round)]
            }
        }

    def check(self):
        return checked_receipt(self.before, self.after, self.receipt,
                               now=self.opened + dt.timedelta(minutes=6),
                               reviewed_draft=self.draft, report_bytes=self.report)

    def test_one_clean_cycle_accepted(self):
        self.assertTrue(self.check())

    def test_critical_rejection_blocks(self):
        self.receipt["approval"]["critical"]["approved"] = False
        with self.assertRaisesRegex(ValueError, "critical"):
            self.check()

    def test_affirmative_rejection_blocks(self):
        self.receipt["approval"]["affirmative"]["approved"] = False
        with self.assertRaisesRegex(ValueError, "affirmative"):
            self.check()

    def test_any_pending_issues_block_approval(self):
        self.receipt["approval"]["rounds"][0]["critical"]["issues"] = ["source conflict"]
        with self.assertRaisesRegex(ValueError, "issues"):
            self.check()

    def test_wrong_critical_draft_hash_blocks(self):
        self.receipt["approval"]["rounds"][0]["critical"]["draft_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "same exact draft"):
            self.check()

    def test_critical_before_affirmative_blocks(self):
        self.receipt["approval"]["rounds"][0]["critical"]["completed_at"] = self.times[0]
        with self.assertRaisesRegex(ValueError, "order"):
            self.check()

    def test_missing_full_validation_blocks(self):
        self.receipt["approval"]["rounds"][0]["validation"]["passed"] = False
        with self.assertRaisesRegex(ValueError, "pre-review validation"):
            self.check()

    def test_missing_post_review_validation_blocks(self):
        self.receipt["approval"]["rounds"][0].pop("post_review_validation")
        with self.assertRaisesRegex(ValueError, "post-review validation"):
            self.check()

    def test_review_report_must_contain_both_verdicts(self):
        self.report = self.report.replace(b"Critical verdict:", b"Missing verdict:")
        self.receipt["report_sha256"] = hashlib.sha256(self.report).hexdigest()
        with self.assertRaisesRegex(ValueError, "Critical review report"):
            self.check()

    def test_no_false_independence_provenance(self):
        self.receipt["reviewer_provenance"] = "independent_reviewers"
        with self.assertRaisesRegex(ValueError, "Unknown or unauthorized"):
            self.check()

    def test_60_minute_ceiling_is_failure(self):
        r = self.receipt["approval"]["rounds"][0]
        later = self.opened + dt.timedelta(minutes=61)
        r["critical"]["completed_at"] = later.isoformat()
        r["post_review_validation"]["completed_at"] = (later + dt.timedelta(seconds=1)).isoformat()
        self.receipt["review_completed_at"] = later.isoformat()
        with self.assertRaisesRegex(ValueError, "sixty minutes"):
            self.check()

    def test_post_review_validation_after_issuance_fails(self):
        self.receipt["approval"]["rounds"][0]["post_review_validation"]["completed_at"] = (
            self.opened + dt.timedelta(minutes=6)).isoformat()
        with self.assertRaisesRegex(ValueError, "must precede issuance"):
            self.check()

    def test_missing_report_section_is_rejected(self):
        self.receipt["approval"]["rounds"][0]["section_reviews"].pop(
            "houthi_support_and_independent_capability")
        with self.assertRaisesRegex(ValueError, "Every report section"):
            self.check()

    def test_missing_warning_item_is_rejected(self):
        items = self.receipt["approval"]["rounds"][0]["section_reviews"][
            "nine_warning_indicators"]["items"]
        items.pop()
        with self.assertRaisesRegex(ValueError, "Unreviewed or mismatched"):
            self.check()

    def test_missing_evidence_item_is_rejected(self):
        items = self.receipt["approval"]["rounds"][0]["section_reviews"][
            "source_search_and_provenance"]["items"]
        items.pop()
        with self.assertRaisesRegex(ValueError, "Unreviewed or mismatched"):
            self.check()

    def test_missing_critical_section_verdict_is_rejected(self):
        detail = self.receipt["approval"]["rounds"][0]["section_reviews"][
            "oil_credit_sanctions_and_payment_mechanisms"]
        detail.pop("critical")
        with self.assertRaisesRegex(ValueError, "Malformed report section"):
            self.check()

    def test_missing_critical_test_note_is_rejected(self):
        detail = self.receipt["approval"]["rounds"][0]["section_reviews"][
            "dashboard_metrics_tables_and_statuses"]["critical"]
        detail["test_note"] = ""
        with self.assertRaisesRegex(ValueError, "critical report section test incomplete"):
            self.check()

    def test_missing_full_report_section_heading_is_rejected(self):
        self.report = self.report.replace(b"### hanke_inflation_and_humanitarian_diagnostics",
                                          b"### missing_review")
        self.receipt["report_sha256"] = hashlib.sha256(self.report).hexdigest()
        with self.assertRaisesRegex(ValueError, "Full report lacks"):
            self.check()

    def test_unbound_section_matrix_is_rejected(self):
        self.receipt["report_section_review_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "section-review matrix"):
            self.check()

    def test_false_affirmative_pass_with_section_failure_is_rejected(self):
        detail = self.receipt["approval"]["rounds"][0]["section_reviews"][
            "four_scored_forecasts"]["affirmative"]
        detail["approved"], detail["issues"] = False, ["calibration error"]
        with self.assertRaisesRegex(ValueError, "global/section"):
            self.check()

    def test_v2_single_review_not_authorized_for_future(self):
        self.receipt["version"] = 2
        self.receipt["origin"] = "chatgpt_critical"
        self.receipt["review_mode"] = "single_critical_chat"
        with self.assertRaisesRegex(ValueError, "Unknown or unauthorized"):
            self.check()

    def test_another_draft_requires_new_round_with_new_hash(self):
        approval = self.receipt["approval"]
        prior = copy.deepcopy(approval["rounds"][0])
        prior["affirmative"]["approved"] = False
        prior["affirmative"]["issues"] = ["specific concern"]
        prior["draft_sha256"] = "1" * 64
        prior["affirmative"]["draft_sha256"] = "1" * 64
        prior["critical"]["draft_sha256"] = "1" * 64
        for detail in prior["section_reviews"].values():
            detail["affirmative"]["draft_sha256"] = "1" * 64
            detail["critical"]["draft_sha256"] = "1" * 64
        failed = prior["section_reviews"]["new_events_and_news"]["affirmative"]
        failed["approved"], failed["issues"] = False, ["Synthetic unsupported claim"]
        prior["post_review_validation"] = None
        prior["forecast_sha256"] = self.lock_hash
        prior["critical"]["completed_at"] = (
            self.opened + dt.timedelta(seconds=2)).isoformat()
        prior["affirmative"]["completed_at"] = (
            self.opened + dt.timedelta(seconds=1)).isoformat()
        prior["validation"]["completed_at"] = self.opened.isoformat()
        last = copy.deepcopy(self.round)
        last["round"] = 2
        approval["round"] = 2
        approval["rounds"] = [prior, last]
        self.assertTrue(self.check())

    def test_refuse_repetition_after_clean_approval(self):
        self.receipt["approval"]["round"] = 2
        self.receipt["approval"]["rounds"] = [
            copy.deepcopy(self.round), dict(self.round, round=2)]
        with self.assertRaisesRegex(ValueError, "Cannot revise after an already clean approval"):
            self.check()

    def test_recycled_failing_draft_is_not_a_correction(self):
        prior = copy.deepcopy(self.round)
        prior["affirmative"]["approved"] = False
        prior["affirmative"]["issues"] = ["Contradiction requiring correction"]
        failed = prior["section_reviews"]["new_events_and_news"]["affirmative"]
        failed["approved"], failed["issues"] = False, ["Synthetic contradiction"]
        prior["post_review_validation"] = None
        prior["validation"]["completed_at"] = self.opened.isoformat()
        prior["affirmative"]["completed_at"] = (
            self.opened + dt.timedelta(seconds=1)).isoformat()
        prior["critical"]["completed_at"] = (
            self.opened + dt.timedelta(seconds=2)).isoformat()
        following = copy.deepcopy(self.round)
        following["round"] = 2
        self.receipt["approval"]["round"] = 2
        self.receipt["approval"]["rounds"] = [prior, following]
        with self.assertRaisesRegex(ValueError, "new 64-character"):
            self.check()

if __name__ == "__main__":
    unittest.main()
