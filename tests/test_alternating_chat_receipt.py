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
        self.report = (
            "# Two-perspective ChatGPT review\n"
            "Both review perspectives are from one ChatGPT session.\n"
            "Affirmative verdict: approved=true; issues=[]; draft_sha256=" + self.hash + "\n"
            "Critical verdict: approved=true; issues=[]; draft_sha256=" + self.hash + "\n"
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

    def test_refuse_recycling_same_failing_draft(self):
        self.receipt["approval"]["round"] = 2
        self.receipt["approval"]["rounds"] = [
            copy.deepcopy(self.round), dict(self.round, round_=2)]
        self.receipt["approval"]["rounds"][1]["round"] = 2
        with self.assertRaisesRegex(ValueError, "new 64-character"):
            self.check()

if __name__ == "__main__":
    unittest.main()
