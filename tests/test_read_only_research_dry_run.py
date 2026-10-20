"""Synthetic read-only rehearsal and actual search-trace provenance tests."""
import copy
import datetime as dt
import json
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
from automation_fixtures import fixture
from assessment_pipeline import SOURCE_SCAN_GROUPS
from read_only_research_dry_run import research_rehearsal
from source_search_trace import observed_search_calls, verify_search_trace


class SearchToolTraceTests(unittest.TestCase):
    def test_real_tool_call_parsed_without_faking_its_queries(self):
        result=observed_search_calls([
            {"type":"message","content":[{"type":"output_text","text":"Do not trust!"}]},
            {"type":"web_search_call","action":{
                "type":"search","queries":["Iran economy October"],
                "sources":[{"url":"https://www.reuters.com/world/middle-east/situation",
                            "title":"A real search-result reference"},
                           {"url":"http://insecure.example/skip","title":"Bad"}]}}
        ])
        self.assertTrue(verify_search_trace(result))
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["queries_exposed_by_api"],["Iran economy October"])
        self.assertEqual(len(result[0]["citation_sources_exposed_by_api"]),1)
        self.assertNotIn("Do not trust",json.dumps(result))

    def test_no_actual_web_search_call_fails(self):
        result=observed_search_calls([{"type":"message","content":[]}])
        with self.assertRaisesRegex(ValueError,"execution not evidenced"):
            verify_search_trace(result)

    def test_missing_exposed_queries_is_not_invented(self):
        calls=observed_search_calls([
            {"type":"web_search_call","action":{"sources":[]}}
        ])
        self.assertEqual(calls[0]["queries_exposed_by_api"],[])


class ReadOnlySourceDryRunTests(unittest.TestCase):
    def setUp(self):
        self.history,self.analysis,self.evidence,self.opened=fixture()
        self.home=tempfile.TemporaryDirectory(prefix="iran-synthetic-dryrun-")
        self.addCleanup(self.home.cleanup)
        self.root=Path(self.home.name)/"source"
        (self.root/"data").mkdir(parents=True)
        (self.root/"data/history.json").write_text(
            json.dumps(self.history,ensure_ascii=False))
        self.original=(self.root/"data/history.json").read_bytes()
        self.audit=Path(self.home.name)/"results"
        self.review_order=[]

    def research(self,prompt,search):
        self.assertTrue(search)
        self.assertIn("BROAD, ADAPTIVE",prompt)
        rows=[{"category":category,
               "queries":["Synthetic source search in "+category],
               "outcome":"searched_no_eligible_evidence",
               "original_urls":[],
               "limitations":"Synthetic scope limited; this is not genuine reporting."}
              for category in SOURCE_SCAN_GROUPS]
        rows[1]["outcome"]="eligible_reporting_found"
        rows[1]["original_urls"]=[self.evidence[0]["source"]]
        return {"evidence":copy.deepcopy(self.evidence),"coverage_audit":rows},{
            x["source"] for x in self.evidence}

    def review(self,prompt,search):
        self.assertFalse(search)
        role=("affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical")
        self.review_order.append(role)
        return {"approved":True,"issues":[]},set()

    def execute(self,reviewer=None):
        clock=lambda:self.opened
        return research_rehearsal(
            root=self.root,output=self.audit,researcher=self.research,
            reviewer=reviewer or self.review,
            metadata_reader=lambda url:{},now=clock)

    def test_complete_two_role_research_only_nonpublishing_rehearsal(self):
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"false"},clear=True):
            result=self.execute()
        self.assertEqual(self.review_order,["affirmative","critical"])
        self.assertEqual(result["mode"],"RESEARCH_ONLY_NONPUBLISHING")
        self.assertEqual(result["prospective_forecasts"],"NOT TESTED")
        self.assertEqual(result["full_15_section_report_review"],"NOT TESTED")
        self.assertFalse(result["actual_live_model_used"])
        self.assertEqual(len(result["frozen_test_evidence"]),len(self.evidence))
        self.assertTrue((self.audit/"research-dry-run.json").exists())
        self.assertEqual((self.root/"data/history.json").read_bytes(),self.original)

    def test_critical_objection_is_explicit_unpublishable_failure(self):
        def critical(prompt,search):
            role=("affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical")
            self.review_order.append(role)
            if role=="critical":
                return {"approved":False,"issues":[{"type":"evidence",
                    "location":"source_search_and_provenance",
                    "reason":"Synthetic provenance is insufficient."}]},set()
            return {"approved":True,"issues":[]},set()
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"false"},clear=True):
            result=self.execute(reviewer=critical)
        self.assertEqual(result["status"],"RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE")
        self.assertFalse(result["reviewers"]["critical"]["approved"])
        self.assertEqual((self.root/"data/history.json").read_bytes(),self.original)

    def test_no_github_or_metricool_token_accepted(self):
        with patch.dict(os.environ,{"GH_TOKEN":"synthetic-secret"},clear=True):
            with self.assertRaisesRegex(ValueError,"must not hold GitHub write"):
                self.execute()
        self.assertEqual((self.root/"data/history.json").read_bytes(),self.original)

    def test_missing_six_category_audit_fails_closed(self):
        def incomplete(prompt,search):
            data,sources=self.research(prompt,search)
            del data["coverage_audit"][-1]
            return data,sources
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"false"},clear=True):
            with self.assertRaisesRegex(ValueError,"Missing or incomplete"):
                research_rehearsal(root=self.root,output=self.audit,
                    researcher=incomplete,reviewer=self.review,
                    metadata_reader=lambda url:{},now=lambda:self.opened)
        self.assertEqual((self.root/"data/history.json").read_bytes(),self.original)

    def test_github_actions_requires_manual_workflow_dispatch(self):
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"true",
                                     "GITHUB_EVENT_NAME":"schedule"},clear=True):
            with self.assertRaisesRegex(ValueError,"manually invoked"):
                self.execute()
        self.assertEqual((self.root/"data/history.json").read_bytes(),self.original)


if __name__=="__main__":
    unittest.main()
