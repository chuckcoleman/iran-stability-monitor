"""Offline protected-publication rehearsal using real Git baselines, no network.

This checks the same CLI gates used by pull-request CI on a synthetic
previously issued assessment, and tests that missing/contradictory review
receipts cannot be mistaken for successful approvals.

All changes occur in a disposable Git repository, never main or Pages.
"""
import copy
import datetime as dt
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
from review_receipt import digest

SCRIPTS=("review_receipt.py","candidate_checks.py",
         "source_metadata.py","validate_history.py")


@unittest.skipUnless(shutil.which("git"),"Git is required for the full PR-gate rehearsal")
class PublicationGateRehearsalTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory(prefix="iran-publication-gate-")
        self.addCleanup(self.work.cleanup)
        self.repo=Path(self.work.name)/"repo"
        (self.repo/"scripts").mkdir(parents=True)
        (self.repo/"data").mkdir()
        (self.repo/"schema").mkdir()
        for name in SCRIPTS:
            shutil.copyfile(ROOT/"scripts"/name,self.repo/"scripts"/name)
        shutil.copyfile(ROOT/"schema/history.schema.json",
                        self.repo/"schema/history.schema.json")
        history=json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(history["updates"]),4)
        # Rehearse the immutable 2026-10-11 issuance from its exact
        # 2026-10-04 baseline. Later synthetic or actual Sunday updates must
        # not turn a test receipt into a future-dated approval.
        # Never bypass the production validator's real-time cutoff.
        historical=next(i for i,r in enumerate(history["updates"])
                        if r["date"]=="2026-10-11")
        self.after=copy.deepcopy(history)
        self.after["updates"]=self.after["updates"][:historical+1]
        self.before=copy.deepcopy(self.after)
        self.before["updates"].pop()
        self.original=self.after["updates"][-1]
        self.date=self.original["date"]
        self.assertEqual((dt.date.fromisoformat(self.date)-
                          dt.date.fromisoformat(self.before["updates"][-1]["date"])).days,7)
        (self.repo/"data/history.json").write_text(
            json.dumps(self.before,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8")
        self.git("init","-q")
        self.git("config","user.name","Synthetic CI Test")
        self.git("config","user.email","synthetic@example.invalid")
        self.git("add","data/history.json")
        self.git("commit","-qm","Synthetic preceding Sunday baseline")
        self.base=self.git("rev-parse","HEAD").stdout.strip()
        self.write_handoff()

    def git(self,*args):
        p=subprocess.run(["git",*args],cwd=self.repo,text=True,
                         capture_output=True,check=False,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr)
        return p

    def clean_receipt(self):
        locked=[{key:value for key,value in f.items()
                 if key in ("event_id","p","range","confidence","raise","lower")}
                for f in self.original["forecasts"]]
        stamp=dt.datetime.fromisoformat(self.original["publication_time"])
        reviewed_at=stamp+dt.timedelta(minutes=1)
        # This is only a simulated consent record in an isolated local test.
        # No test fixture is ever delivered to the live publication tree.
        same_draft="a"*64
        return {
            "version":1,"origin":"off_github","status":"CLEAN",
            "date":self.date,
            "baseline_sha256":digest(self.before),
            "candidate_sha256":digest(self.after),
            "record_sha256":digest(self.original),
            "review_completed_at":reviewed_at.isoformat(timespec="seconds"),
            "approval":{
                "status":"CLEAN","round":1,
                "draft_sha256":same_draft,
                "forecast_sha256":digest(locked),
                "locked_forecasts":locked,
                "affirmative":{"approved":True,"issues":[],
                               "draft_sha256":same_draft},
                "critical":{"approved":True,"issues":[],
                            "draft_sha256":same_draft}}
        }

    def write_handoff(self,receipt=None):
        (self.repo/"data/history.json").write_text(
            json.dumps(self.after,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8")
        out=self.repo/"data/review-receipts"
        out.mkdir(exist_ok=True)
        (out/(self.date+".json")).write_text(
            json.dumps(receipt if receipt is not None else self.clean_receipt(),
                       ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

    def cli(self,script,*args):
        return subprocess.run([sys.executable,"scripts/"+script,*args],
                              cwd=self.repo,capture_output=True,text=True,
                              check=False,timeout=30)

    def test_all_required_history_gates_pass_with_complete_review_receipt(self):
        schema=subprocess.run([
            sys.executable,"-m","jsonschema","-i","data/history.json",
            "schema/history.schema.json"],
            cwd=self.repo,capture_output=True,text=True,
            check=False,timeout=30)
        self.assertEqual(schema.returncode,0,schema.stdout+schema.stderr)
        frozen=self.cli("validate_history.py","--baseline-ref",self.base)
        self.assertEqual(frozen.returncode,0,frozen.stdout+frozen.stderr)
        external=self.cli("review_receipt.py","--baseline-ref",self.base)
        self.assertEqual(external.returncode,0,external.stdout+external.stderr)
        self.assertIn("verified",external.stdout)

    def test_missing_receipt_rejects_entire_new_record(self):
        (self.repo/"data/review-receipts"/(self.date+".json")).unlink()
        gate=self.cli("review_receipt.py","--baseline-ref",self.base)
        self.assertNotEqual(gate.returncode,0)
        self.assertIn("no off-GitHub",gate.stderr)

    def test_critical_rejection_fails_regardless_of_affirmative_pass(self):
        record=self.clean_receipt()
        record["approval"]["critical"]["approved"]=False
        self.write_handoff(record)
        gate=self.cli("review_receipt.py","--baseline-ref",self.base)
        self.assertNotEqual(gate.returncode,0)
        self.assertIn("critical",gate.stderr)

    def test_report_edit_after_review_fails_digest_check(self):
        current=copy.deepcopy(self.after)
        current["updates"][-1]["summary"]+=" Changed after review."
        (self.repo/"data/history.json").write_text(
            json.dumps(current,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8")
        gate=self.cli("review_receipt.py","--baseline-ref",self.base)
        self.assertNotEqual(gate.returncode,0)
        self.assertIn("digest mismatch",gate.stderr)

    def test_unchanged_history_requires_no_new_review(self):
        (self.repo/"data/history.json").write_text(
            json.dumps(self.before,ensure_ascii=False,indent=2)+"\n",
            encoding="utf-8")
        (self.repo/"data/review-receipts"/(self.date+".json")).unlink()
        gate=self.cli("review_receipt.py","--baseline-ref",self.base)
        self.assertEqual(gate.returncode,0,gate.stdout+gate.stderr)
        self.assertIn("No assessment change",gate.stdout)


if __name__=="__main__":
    unittest.main()
