"""Offline preflight and GitHub-ordering tests; no actual network or publication."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
from automation_fixtures import fixture
import assessment_pipeline as a
import review_receipt as receipts
import submit_reviewed_assessment as submission
import run_off_github_sunday as coordinator


class ExternalHandoffTests(unittest.TestCase):
    def setUp(self):
        self.history,self.analysis,self.evidence,self.opened=fixture()
        cutoff=self.opened-dt.timedelta(seconds=10)
        ledger=a.freeze_evidence({"evidence":self.evidence},
            {e["source"] for e in self.evidence},
            self.history["updates"][-1],self.opened.date().isoformat(),cutoff)
        self.candidate=copy.deepcopy(self.history)
        self.candidate["updates"].append(a.assemble(
            self.history,self.analysis,ledger,cutoff,self.opened,
            self.opened+dt.timedelta(seconds=1)))
        drafthash="a"*64
        forecasts=copy.deepcopy(self.analysis["forecasts"])
        self.approval={
            "status":"CLEAN","round":1,"draft_sha256":drafthash,
            "forecast_sha256":receipts.digest(forecasts),
            "locked_forecasts":forecasts,
            "affirmative":{"approved":True,"issues":[],"draft_sha256":drafthash},
            "critical":{"approved":True,"issues":[],"draft_sha256":drafthash}}
        self.receipt={
            "version":1,"origin":"off_github","status":"CLEAN",
            "date":self.opened.date().isoformat(),
            "baseline_sha256":receipts.digest(self.history),
            "candidate_sha256":receipts.digest(self.candidate),
            "record_sha256":receipts.digest(self.candidate["updates"][-1]),
            "review_completed_at":(self.opened+dt.timedelta(seconds=2)).isoformat(),
            "approval":self.approval}

    def create_synthetic_handoff(self,work):
        root=work/"checkout"
        handoff=work/"approved"
        (root/"data").mkdir(parents=True)
        (root/"schema").mkdir()
        shutil.copyfile(ROOT/"schema/history.schema.json",root/"schema/history.schema.json")
        (root/"data/history.json").write_text(json.dumps(self.history))
        (handoff/"data/review-receipts").mkdir(parents=True)
        (handoff/"review-audit").mkdir()
        (handoff/"history-before.json").write_text(json.dumps(self.history))
        (handoff/"data/history.json").write_text(json.dumps(self.candidate))
        (handoff/"data/review-receipts"/(self.receipt["date"]+".json")).write_text(
            json.dumps(self.receipt))
        for role in ("affirmative","critical"):
            p=handoff/"review-audit"/("review-01-"+role+".json")
            p.write_text(json.dumps({
                "round":1,"role":role,"draft_sha256":self.approval["draft_sha256"],
                "status":"clean","issues":[]}))
        return root,handoff

    def test_full_handoff_is_validated_before_github_contact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,handoff=self.create_synthetic_handoff(Path(tmp))
            with patch.object(submission,"gh") as gh,\
                 patch.object(submission,"gh_json") as api:
                result=submission.validate_handoff(
                    handoff,root=root,now=self.opened+dt.timedelta(seconds=3))
                gh.assert_not_called()
                api.assert_not_called()
            self.assertEqual(result["date"],self.receipt["date"])

    def test_missing_critical_review_blocks_before_github(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,handoff=self.create_synthetic_handoff(Path(tmp))
            (handoff/"review-audit/review-01-critical.json").unlink()
            with patch.object(submission,"gh") as gh,\
                 patch.object(submission,"gh_json") as api:
                with self.assertRaisesRegex(RuntimeError,"critical review audit"):
                    submission.validate_handoff(
                        handoff,root=root,now=self.opened+dt.timedelta(seconds=3))
                gh.assert_not_called()
                api.assert_not_called()

    def test_stale_baseline_and_tampering_fail_without_github(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,handoff=self.create_synthetic_handoff(Path(tmp))
            (root/"data/history.json").write_text(json.dumps({"updates":[]}))
            with self.assertRaisesRegex(RuntimeError,"does not match"):
                submission.validate_handoff(
                    handoff,root=root,now=self.opened+dt.timedelta(seconds=3))
            (root/"data/history.json").write_text(json.dumps(self.history))
            bad=copy.deepcopy(self.candidate)
            bad["updates"][-1]["summary"]="Edited after review"
            (handoff/"data/history.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError,"digest mismatch"):
                submission.validate_handoff(
                    handoff,root=root,now=self.opened+dt.timedelta(seconds=3))

    def test_reviewed_sunday_cannot_be_submitted_on_another_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,handoff=self.create_synthetic_handoff(Path(tmp))
            with self.assertRaisesRegex(RuntimeError,"stale"):
                submission.validate_handoff(
                    handoff,root=root,now=self.opened+dt.timedelta(days=1))

    def test_orchestrator_does_not_touch_github_after_review_failure(self):
        with patch.object(coordinator.pre_github_review,"prepare",
                          side_effect=TimeoutError("critical review timeout")) as p,\
             patch.object(coordinator.submit_reviewed_assessment,"submit") as publish:
            with self.assertRaisesRegex(TimeoutError,"timeout"):
                coordinator.main(["--output-dir","/tmp/example","--submit","--merge"])
            p.assert_called_once()
            publish.assert_not_called()

    def test_orchestrator_submits_only_after_review_success(self):
        state=[]
        with patch.object(coordinator.pre_github_review,"prepare",
                          side_effect=lambda folder: state.append("review") or folder),\
             patch.object(coordinator.submit_reviewed_assessment,"submit",
                          side_effect=lambda folder,merge: state.append("publish")):
            self.assertEqual(coordinator.main(
                ["--output-dir","/tmp/example","--submit","--merge"]),0)
            self.assertEqual(state,["review","publish"])

    def test_orchestrator_requires_explicit_merge_permission(self):
        with self.assertRaises(SystemExit):
            coordinator.main(["--output-dir","/tmp/example","--merge"])


if __name__=="__main__":
    unittest.main()
