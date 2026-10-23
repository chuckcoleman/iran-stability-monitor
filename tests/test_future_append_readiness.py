"""Rehearse the WHOLE offline test suite against a fifth Sunday record.

This catches fixed historical-record counts that would otherwise make
protected publication CI fail as soon as the next reviewed record is appended.
Nothing changes in the source checkout; all data is synthetic and temporary.
"""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
from automation_fixtures import fixture
from assessment_pipeline import assemble,freeze_evidence
from validate_history import validate_history


class FutureAppendReadinessTests(unittest.TestCase):
    def test_full_suite_after_one_synthetic_sunday_append(self):
        if os.getenv("IRAN_RUN_FUTURE_APPEND") != "1":
            self.skipTest("Dedicated future-append CI job runs this expensive nested test")
        if os.getenv("IRAN_NESTED_FUTURE_APPEND")=="1":
            self.skipTest("Nested run already uses one new synthetic Sunday")
        before,assessment,evidence,opened=fixture()
        cutoff=opened-dt.timedelta(seconds=10)
        ledger=freeze_evidence(
            {"evidence":evidence},{e["source"] for e in evidence},
            before["updates"][-1],opened.date().isoformat(),cutoff)
        candidate=copy.deepcopy(before)
        candidate["updates"].append(assemble(
            before,assessment,ledger,cutoff,opened,
            opened+dt.timedelta(seconds=1)))
        validate_history(candidate,before)

        with tempfile.TemporaryDirectory(prefix="iran-future-suite-") as tmp:
            root=Path(tmp)/"repo"
            shutil.copytree(
                ROOT,root,
                ignore=shutil.ignore_patterns(
                    ".git","__pycache__", ".automation-audit","_site",".pytest_cache"))
            (root/"data/history.json").write_text(
                json.dumps(candidate,ensure_ascii=False,indent=2)+"\n",
                encoding="utf-8")
            env=dict(os.environ,IRAN_NESTED_FUTURE_APPEND="1", IRAN_RUN_FUTURE_APPEND="0")
            result=subprocess.run(
                [sys.executable,"-m","unittest","discover","-s","tests","-q"],
                cwd=root,env=env,text=True,capture_output=True,
                check=False,timeout=120)
            self.assertEqual(result.returncode,0,
                             "A new Sunday append breaks an offline test:\n"
                             +result.stdout[-4000:]+"\n"+result.stderr[-8000:])


if __name__=="__main__":
    unittest.main()
