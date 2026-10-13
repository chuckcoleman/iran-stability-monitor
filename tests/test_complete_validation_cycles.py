"""Full deterministic revalidation must loop with all reviews until clean.

These are synthetic tests only: they do not research, publish, contact
GitHub, or change the frozen history.
"""
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
from automation_fixtures import fixture
from validate_history import validate_history


class CompleteValidationCycleTests(unittest.TestCase):
    def setUp(self):
        self.history,self.analysis,self.evidence,self.opened=fixture()
        self.original=copy.deepcopy(self.history)
        self.cutoff=self.opened-dt.timedelta(seconds=10)
        self.sources={e["source"] for e in self.evidence}

    def clock(self,issued_times=None):
        stamps=[self.cutoff-dt.timedelta(seconds=5),self.cutoff,self.opened]
        stamps+=issued_times or [self.opened+dt.timedelta(seconds=4)]
        times=iter(stamps)
        return lambda: next(times)

    def research(self,prompt,search):
        return {"evidence":self.evidence},self.sources

    @staticmethod
    def clean_review(prompt,search):
        return {"approved":True,"issues":[]},set()

    def test_dashboard_failure_is_corrected_then_both_reviews_rerun(self):
        bad=copy.deepcopy(self.analysis)
        bad["regional"][0]["p"]+=1
        good=copy.deepcopy(self.analysis)
        seen=[]
        def assess(prompt,search):
            correction="locked_forecasts" in prompt
            seen.append("repair" if correction else "elicitation")
            if correction:
                self.assertIn("Descriptive scenario probabilities must total 100",prompt)
            return copy.deepcopy(good if correction else bad),set()
        def review(prompt,search):
            seen.append("affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical")
            return self.clean_review(prompt,search)
        out=pipeline.produce(
            self.history,self.research,assess,self.clock(),
            lambda url:{},review)
        self.assertEqual(seen,["elicitation","repair","affirmative","critical"])
        self.assertEqual(out["updates"][-1]["regional"],good["regional"])
        self.assertEqual(out["updates"][-1]["forecasts"][0]["p"],
                         self.original["updates"][-1]["forecasts"][0]["p"]+17)
        validate_history(out,self.original)
        self.assertEqual(self.history,self.original)

    def test_repeated_identical_validation_failure_never_passes(self):
        invalid=copy.deepcopy(self.analysis)
        invalid["regional"][0]["p"]+=1
        roles=[]
        def assess(prompt,search):
            return copy.deepcopy(invalid),set()
        def review(prompt,search):
            roles.append("unexpected")
            return self.clean_review(prompt,search)
        with self.assertRaisesRegex(ValueError,"cycles exhausted"):
            pipeline.produce(
                self.history,self.research,assess,
                self.clock(issued_times=[]),lambda url:{},review)
        self.assertEqual(roles,[])
        self.assertEqual(self.history,self.original)

    def test_final_validation_failure_forces_new_both_role_reviews(self):
        first=copy.deepcopy(self.analysis)
        good=copy.deepcopy(self.analysis)
        first["summary"]="An overstated but structurally valid synthetic claim requires final review correction."
        good["summary"]="The corrected synthetic summary clearly separates limited observations from judgment."
        reviews=[]
        assessments=[]
        orig=pipeline._fully_validated_candidate
        def validator(history,analysis,evidence,cutoff,opened,issued,schema):
            # Simulate a final-only independent content validator rejecting
            # a material error missed by the two initial review verdicts.
            out=orig(history,analysis,evidence,cutoff,opened,issued,schema)
            if issued!=opened and analysis["summary"]==first["summary"]:
                raise ValueError("Final content check rejected unsupported claim")
            return out
        def assessor(prompt,search):
            corrected="locked_forecasts" in prompt
            assessments.append(corrected)
            return copy.deepcopy(good if corrected else first),set()
        def reviewer(prompt,search):
            reviews.append("affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical")
            return self.clean_review(prompt,search)
        times=self.clock([self.opened+dt.timedelta(seconds=3),
                          self.opened+dt.timedelta(seconds=4)])
        with patch.object(pipeline,"_fully_validated_candidate",side_effect=validator) as validation:
            result=pipeline.produce(self.history,self.research,assessor,times,
                                    lambda url:{},reviewer)
        self.assertEqual(assessments,[False,True])
        self.assertEqual(reviews,["affirmative","critical"]*2)
        self.assertEqual(validation.call_count,4)
        self.assertEqual(result["updates"][-1]["summary"],good["summary"])
        self.assertEqual(result["updates"][-1]["forecasts"],
                         orig(self.history,good,self.evidence,self.cutoff,
                              self.opened,self.opened+dt.timedelta(seconds=4),
                              pipeline_validate_schema()).get("updates")[-1]["forecasts"])
        self.assertEqual(self.history,self.original)

    def test_validator_timeout_is_failure_and_no_clean_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            reviews=[]
            with patch.dict(os.environ,{"IRAN_OFFLINE_REVIEW_DIR":tmp}),\
                 patch.object(pipeline,"_fully_validated_candidate",
                              side_effect=TimeoutError("Synthetic validator timed out")):
                with self.assertRaisesRegex(TimeoutError,"timed out"):
                    pipeline.produce(self.history,self.research,
                                     lambda p,q:(self.analysis,set()),
                                     self.clock(),lambda url:{},
                                     lambda p,q:(reviews.append("review"),
                                                  self.clean_review(p,q)[0])[1])
            self.assertEqual(reviews,[])
            self.assertFalse((Path(tmp)/"review-approval.json").exists())
            self.assertEqual(self.history,self.original)

    def test_final_approval_requires_two_clean_review_licenses_and_validation_audits(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ,{"IRAN_OFFLINE_REVIEW_DIR":tmp}):
                output=pipeline.produce(self.history,self.research,
                    lambda p,q:(copy.deepcopy(self.analysis),set()),
                    self.clock(),lambda url:{},self.clean_review)
            root=Path(tmp)
            checks=["validation","affirmative","critical","final_validation"]
            for name in checks:
                p=root/f"review-01-{name}.json"
                self.assertTrue(p.exists(),name)
                row=json.loads(p.read_text())
                self.assertEqual(row["status"],"clean")
                self.assertEqual(row["issues"],[])
            approval=json.loads((root/"review-approval.json").read_text())
            self.assertEqual(approval["status"],"CLEAN")
            self.assertEqual(approval["round"],1)
            self.assertEqual(output["updates"][:-1],self.history["updates"])
            validate_history(output,self.history)


def pipeline_validate_schema():
    from jsonschema import Draft202012Validator
    return Draft202012Validator(json.loads(
        (ROOT/"schema/history.schema.json").read_text(encoding="utf-8")))


if __name__=="__main__":
    unittest.main()
