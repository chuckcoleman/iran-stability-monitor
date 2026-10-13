"""Offline integration and fail-closed pre-GitHub publication-receipt tests."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))

import assessment_pipeline as pipeline
import pre_github_review as prepare
import review_receipt as receipt
from automation_fixtures import fixture


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.history,self.analysis,self.evidence,self.opened=fixture()
        cutoff=self.opened-dt.timedelta(seconds=10)
        source_set={e["source"] for e in self.evidence}
        ledger=pipeline.freeze_evidence(
            {"evidence":self.evidence},source_set,self.history["updates"][-1],
            self.opened.date().isoformat(),cutoff)
        self.candidate=copy.deepcopy(self.history)
        self.candidate["updates"].append(pipeline.assemble(
            self.history,self.analysis,ledger,cutoff,self.opened,
            self.opened+dt.timedelta(seconds=1)))
        self.forecasts=copy.deepcopy(self.analysis["forecasts"])
        draft_hash="a"*64
        self.approval={"status":"CLEAN","round":2,
            "draft_sha256":draft_hash,
            "forecast_sha256":receipt.digest(self.forecasts),
            "locked_forecasts":self.forecasts,
            "affirmative":{"approved":True,"issues":[],"draft_sha256":draft_hash},
            "critical":{"approved":True,"issues":[],"draft_sha256":draft_hash}}
        self.receipt={
            "version":1,"origin":"off_github","status":"CLEAN",
            "date":self.opened.date().isoformat(),
            "baseline_sha256":receipt.digest(self.history),
            "record_sha256":receipt.digest(self.candidate["updates"][-1]),
            "candidate_sha256":receipt.digest(self.candidate),
            "review_completed_at":(self.opened+dt.timedelta(seconds=8)).isoformat(),
            "approval":copy.deepcopy(self.approval)}
        self.after=self.opened+dt.timedelta(seconds=12)

    def test_two_clean_reviews_of_same_draft_pass(self):
        self.assertTrue(receipt.checked_receipt(
            self.history,self.candidate,self.receipt,now=self.after))

    def test_missing_reviewer_is_never_a_pass(self):
        for role in ("affirmative","critical"):
            with self.subTest(role=role):
                row=copy.deepcopy(self.receipt)
                del row["approval"][role]
                with self.assertRaisesRegex(ValueError,role):
                    receipt.checked_receipt(self.history,self.candidate,row,now=self.after)

    def test_disagreement_and_different_draft_fail(self):
        for change in ("approved","issues","draft_sha256"):
            row=copy.deepcopy(self.receipt)
            if change=="approved":
                row["approval"]["critical"]["approved"]=False
            elif change=="issues":
                row["approval"]["critical"]["issues"]=[{"reason":"Missing evidence"}]
            else:
                row["approval"]["critical"]["draft_sha256"]="b"*64
            with self.subTest(change=change):
                with self.assertRaisesRegex(ValueError,"critical"):
                    receipt.checked_receipt(self.history,self.candidate,row,now=self.after)

    def test_tampering_with_report_or_forecast_blocks_submission(self):
        altered=copy.deepcopy(self.candidate)
        altered["updates"][-1]["summary"]="Changed after both reviews."
        with self.assertRaisesRegex(ValueError,"digest"):
            receipt.checked_receipt(self.history,altered,self.receipt,now=self.after)
        row=copy.deepcopy(self.receipt)
        row["approval"]["locked_forecasts"][0]["p"]+=1
        with self.assertRaisesRegex(ValueError,"Scored forecasts"):
            receipt.checked_receipt(self.history,self.candidate,row,now=self.after)

    def test_review_time_and_source_baseline_must_match(self):
        row=copy.deepcopy(self.receipt)
        row["review_completed_at"]=(self.opened-dt.timedelta(seconds=5)).isoformat()
        with self.assertRaisesRegex(ValueError,"Review must complete"):
            receipt.checked_receipt(self.history,self.candidate,row,now=self.after)
        row=copy.deepcopy(self.receipt)
        row["review_completed_at"]=(self.opened+dt.timedelta(hours=3)).isoformat()
        with self.assertRaisesRegex(ValueError,"future"):
            receipt.checked_receipt(self.history,self.candidate,row,now=self.after)
        row=copy.deepcopy(self.receipt)
        row["baseline_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"digest"):
            receipt.checked_receipt(self.history,self.candidate,row,now=self.after)

    def test_submitting_new_assessment_without_review_receipt_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); (root/"data").mkdir()
            (root/"data/history.json").write_text(json.dumps(self.candidate))
            with patch.object(receipt.subprocess,"check_output",
                              return_value=json.dumps(self.history).encode()):
                with self.assertRaisesRegex(ValueError,"no off-GitHub"):
                    receipt.verify_repository_change("base",root)
                p=root/"data/review-receipts";p.mkdir()
                (p/(self.receipt["date"]+".json")).write_text(json.dumps(self.receipt))
                result=receipt.verify_repository_change("base",root,now=self.after)
                self.assertIn("verified",result)

    def test_code_only_change_does_not_require_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/"data").mkdir()
            (root/"data/history.json").write_text(json.dumps(self.history))
            with patch.object(receipt.subprocess,"check_output",
                              return_value=json.dumps(self.history).encode()):
                self.assertIn("No assessment change",
                              receipt.verify_repository_change("base",root))


class OfflinePreparationTests(ReceiptTests):
    def test_offline_review_refuses_github_actions_or_missing_local_key(self):
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"true",
                                    "OPENAI_API_KEY":"local-fake"},clear=True):
            with self.assertRaisesRegex(RuntimeError,"outside GitHub Actions"):
                prepare.check_offline_environment()
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,"separately configured"):
                prepare.check_offline_environment()

    def test_prepare_creates_only_external_reviewed_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"handoff"
            def synthetic_producer(original,reviewer=None):
                self.assertEqual(original,self.history)
                assert reviewer is not None
                Path(os.environ["IRAN_OFFLINE_REVIEW_DIR"]).joinpath(
                    "review-approval.json").write_text(json.dumps(self.approval))
                return copy.deepcopy(self.candidate)
            with patch.dict(os.environ,{"OPENAI_API_KEY":"synthetic-unused"},clear=True):
                output=prepare.prepare(
                    target,now=self.opened,producer=synthetic_producer,
                    review_finished_at=self.opened+dt.timedelta(seconds=8))
            self.assertEqual(output,target)
            self.assertTrue((target/"data/history.json").is_file())
            self.assertTrue((target/"data/review-receipts"/
                             (self.receipt["date"]+".json")).is_file())
            self.assertTrue((target/"history-before.json").is_file())
            self.assertTrue((target/"review-audit/review-approval.json").is_file())
            self.assertEqual(json.loads((target/"data/history.json").read_text()),
                             self.candidate)
            self.assertNotIn("GH_TOKEN",os.environ)

    def test_offline_handoff_is_rejected_without_clean_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"handoff"
            def fake(original,reviewer=None):
                return copy.deepcopy(self.candidate)
            with patch.dict(os.environ,{"OPENAI_API_KEY":"synthetic-unused"},clear=True):
                with self.assertRaisesRegex(RuntimeError,
                                            "Both external reviews have not"):
                    prepare.prepare(target,now=self.opened,producer=fake,
                                    review_finished_at=self.after)
            self.assertFalse(target.exists())


if __name__=="__main__":
    unittest.main()
