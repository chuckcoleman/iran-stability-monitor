"""Prospective ChatGPT critical-review receipt gate, without fictitious dual reviewers."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from automation_fixtures import fixture
import assessment_pipeline as pipeline
from review_receipt import checked_receipt, digest

class SingleCriticalTests(unittest.TestCase):
    def setUp(self):
        self.before,analysis,evidence,opened=fixture()
        cutoff=opened-dt.timedelta(seconds=10)
        ledger=pipeline.freeze_evidence({"evidence":evidence},{e["source"] for e in evidence},
                                        self.before["updates"][-1],opened.date().isoformat(),cutoff)
        self.draft=copy.deepcopy(self.before)
        self.draft["updates"].append(pipeline.assemble(
            self.before,analysis,ledger,cutoff,opened,opened+dt.timedelta(seconds=1)))
        self.issued=copy.deepcopy(self.draft)
        self.reviewed_at=opened+dt.timedelta(seconds=7)
        self.issued_at=opened+dt.timedelta(seconds=14)
        self.issued["updates"][-1]["publication_time"]=self.issued_at.isoformat()
        self.draft_hash=digest(self.draft)
        self.report=("# Review\nReviewed "+self.draft_hash+
            "\nApproved for final timestamping and complete deterministic revalidation: yes."
            "\n**Issues:** "+chr(96)+"[]"+chr(96)+"\n").encode()
        self.receipt={
            "version":2,"origin":"chatgpt_critical","review_mode":"single_critical_chat",
            "status":"CLEAN","date":opened.date().isoformat(),
            "baseline_sha256":digest(self.before),"candidate_sha256":digest(self.issued),
            "record_sha256":digest(self.issued["updates"][-1]),
            "review_completed_at":self.reviewed_at.isoformat(),
            "report_sha256":hashlib.sha256(self.report).hexdigest(),
            "approval":{"status":"CLEAN","round":1,"draft_sha256":self.draft_hash,
                "forecast_sha256":digest(analysis["forecasts"]),
                "locked_forecasts":copy.deepcopy(analysis["forecasts"]),
                "critical":{"approved":True,"issues":[],"draft_sha256":self.draft_hash}}}
    def check(self):
        return checked_receipt(self.before,self.issued,self.receipt,
            reviewed_draft=self.draft,report_bytes=self.report,
            now=self.issued_at+dt.timedelta(seconds=2))
    def test_clean_single_critical_passes(self):
        self.assertTrue(self.check())
    def test_missing_report_refused(self):
        with self.assertRaisesRegex(ValueError,"requires immutable"):
            checked_receipt(self.before,self.issued,self.receipt,
                now=self.issued_at+dt.timedelta(seconds=2))
    def test_negative_or_unresolved_critical_refused(self):
        for decision in (None,{"approved":False,"issues":[],"draft_sha256":self.draft_hash},
            {"approved":True,"issues":["unresolved"],"draft_sha256":self.draft_hash}):
            self.receipt["approval"]["critical"]=decision
            with self.assertRaisesRegex(ValueError,"critical"):
                self.check()
    def test_changing_report_fails(self):
        self.receipt["report_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"report digest"):
            self.check()
    def test_changing_non_timestamp_field_fails(self):
        self.issued["updates"][-1]["summary"]+=" altered"
        self.receipt["candidate_sha256"]=digest(self.issued)
        self.receipt["record_sha256"]=digest(self.issued["updates"][-1])
        with self.assertRaisesRegex(ValueError,"changed after approval"):
            self.check()
    def test_review_must_precede_issuance(self):
        self.issued["updates"][-1]["publication_time"]=(
            self.reviewed_at-dt.timedelta(seconds=1)).isoformat()
        self.receipt["candidate_sha256"]=digest(self.issued)
        self.receipt["record_sha256"]=digest(self.issued["updates"][-1])
        with self.assertRaisesRegex(ValueError,"must follow opening"):
            self.check()
    def test_no_fake_affirmative_review(self):
        self.receipt["approval"]["affirmative"]={"approved":True,"issues":[]}
        with self.assertRaisesRegex(ValueError,"cannot claim"):
            self.check()
    def test_pre_october_18_critical_only_not_eligible(self):
        self.receipt["date"]="2026-10-11"
        with self.assertRaisesRegex(ValueError,"Unknown or unauthorized"):
            self.check()

if __name__ == "__main__":
    unittest.main()
