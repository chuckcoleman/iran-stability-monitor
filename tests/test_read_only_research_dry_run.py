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
import read_only_research_dry_run as diagnostic
from read_only_research_dry_run import research_rehearsal
from source_search_trace import (observed_search_calls, verify_search_trace,
                                 verify_claimed_source_links, load_matching_search_trace)


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

    def test_uncorroborated_coverage_url_not_in_actual_tool_sources_rejected(self):
        calls=observed_search_calls([{"type":"web_search_call",
                 "action":{"sources":[{"url":"https://www.reuters.com/world/iran-original",
                                       "title":"Original link"}]}}])
        rows=[{"original_urls":["https://www.iranintl.com/en/202610209999"]}]
        with self.assertRaisesRegex(ValueError,"never exposed"):
            verify_claimed_source_links(rows,calls)

    def test_exact_research_result_must_match_logged_tool_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"response-1.json"
            calls=observed_search_calls([{"type":"web_search_call",
                     "action":{"sources":[{"url":"https://www.reuters.com/world/iran-original"}]}}])
            path.write_text(json.dumps({"search":True,"result":{"evidence":[1]},
                                         "tool_search_calls":calls}))
            self.assertEqual(load_matching_search_trace(tmp,{"evidence":[1]}),calls)
            with self.assertRaisesRegex(ValueError,"No actual web-search tool trace"):
                load_matching_search_trace(tmp,{"evidence":[2]})

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

    def test_terminal_guard_fails_actions_even_with_both_reviewers_approving(self):
        # An unpublishable evidence set is never a successful diagnostic simply
        # because the two model reviewers returned affirmative verdicts.
        summary = {
            "status": "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE",
            "reviewers": {
                "affirmative": {"approved": True, "issues": []},
                "critical": {"approved": True, "issues": []},
            },
            "terminal_evidence_gate": {
                "new_research_required": True,
                "reason": "Missing directional balance after conservative correction",
            },
        }
        with patch.object(diagnostic, "research_rehearsal", return_value=summary):
            with self.assertRaises(SystemExit) as failure:
                diagnostic.main(["--output-dir", str(self.audit)])
        self.assertEqual(failure.exception.code, 1)

    def test_fresh_v3_failing_admissibility_never_invokes_paid_review(self):
        """A new saved source snapshot can fail before the first reviewer POST."""
        from source_research_batches import sha
        first_source = self.evidence[0]["source"]
        research = {"evidence": copy.deepcopy(self.evidence),
                    "coverage_audit": [], "source_quality": []}
        original_review = {
            "evidence": copy.deepcopy(self.evidence),
            "research_as_of": self.opened.isoformat(),
            "published_history_sha256": "placeholder-original-history",
        }
        snapshot = {"version": 3, "date": self.opened.date().isoformat(),
                    "cutoff_at": self.opened.isoformat(),
                    "snapshot_sha256": "a"*64}
        screened = {
            "status": "PRE_REVIEW_ADMISSIBILITY_BLOCKED_NO_PAID_REVIEWS",
            "admitted_original_ids": [self.evidence[0]["id"]]
                if self.evidence[0].get("id") else [],
            "held_original_ids": [],
            "directional_candidate_counts": {
                "failures": ["missing_required_directional_balance"],
                "missing_directions": ["lowers"]},
            "required_next_action":
                "NEW_DATED_SOURCE_RESEARCH_SNAPSHOT_WITH_BETTER_ORIGINAL_EVIDENCE",
        }
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}, clear=True):
            with patch.object(diagnostic, "batched_research",
                    return_value=(research, {first_source}, [], snapshot)), \
                 patch.object(diagnostic, "resolve_source_citations",
                    return_value=(research, {first_source}, [])), \
                 patch.object(diagnostic, "load_or_save_reconciliation",
                    return_value={"unsupported": []}), \
                 patch.object(diagnostic, "validate_source_coverage_audit",
                    return_value=[]), \
                 patch.object(diagnostic, "verify_claimed_source_links"), \
                 patch.object(diagnostic, "load_or_capture_quality",
                    return_value=({"sources": []}, {})), \
                 patch.object(diagnostic, "reconcile_before_freeze",
                    return_value=(research, None)), \
                 patch.object(diagnostic, "load_or_create_review_input",
                    return_value=(original_review, sha(original_review), self.opened)), \
                 patch.object(diagnostic, "screen_or_restore",
                    return_value=screened) as screen_call, \
                 patch.object(diagnostic, "run_alternating_review_cycles",
                    side_effect=AssertionError("No reviewer may be called")):
                result = research_rehearsal(
                    root=self.root, output=self.audit,
                    researcher=diagnostic.LIVE_RESEARCHER,
                    reviewer=lambda *args: self.fail("No paid reviewer call"),
                    metadata_reader=lambda *args: self.fail("No page retrieval"),
                    now=lambda: self.opened)
        self.assertEqual(screen_call.call_count, 1)
        self.assertEqual(result["status"],
                         "PRE_REVIEW_EVIDENCE_INSUFFICIENT_NOT_PUBLISHABLE")
        self.assertEqual(result["affirmative_review"], "NOT INVOKED")
        self.assertEqual(result["critical_review"], "NOT INVOKED")
        self.assertEqual(result["publication"], "NOT AUTHORIZED")
        self.assertIn("missing_required_directional_balance",
                      result["source_pre_review_directional_counts"]["failures"])
        self.assertTrue((self.audit/"research-pre-review-dry-run.json").exists())
        self.assertFalse((self.audit/"source-review-round-01.json").exists())
        self.assertEqual((self.root/"data/history.json").read_bytes(),
                         self.original)

    def test_live_v5_diagnostic_uses_provisional_freeze_before_review(self):
        """Do not abort on one-sided source research before source eligibility."""
        from source_research_batches import sha
        research = {"evidence": copy.deepcopy(self.evidence),
                    "coverage_audit": [], "source_quality": []}
        first_source = self.evidence[0]["source"]
        snapshot = {"version": 5, "date": self.opened.date().isoformat(),
                    "cutoff_at": self.opened.isoformat(),
                    "snapshot_sha256": "c"*64}
        original_review = {
            "evidence": [], "research_as_of": self.opened.isoformat(),
            "published_history_sha256": "original-historical-source-record",
        }
        seen_freeze_flags = []
        def fake_freeze(*args, **kwargs):
            seen_freeze_flags.append(kwargs)
            self.assertEqual(kwargs, {"provisional_source_only_v5": True})
            return []
        def fake_input(*, freeze, result, citations, archive, date, now, **unused):
            self.assertEqual(
                freeze(result, citations, archive, date, now()), [])
            return original_review, sha(original_review), self.opened
        blocked = {
            "status": "PRE_REVIEW_ADMISSIBILITY_BLOCKED_NO_PAID_REVIEWS",
            "admitted_original_ids": [], "held_original_ids": [],
            "directional_candidate_counts": {
                "failures": [
                    "fewer_than_six_source_observations",
                    "fewer_than_three_distinct_publishers",
                    "fewer_than_four_new_observations"],
                "missing_directions": ["ambiguous", "lowers"]},
            "required_next_action":
                "NEW_DATED_SOURCE_RESEARCH_SNAPSHOT_WITH_BETTER_ORIGINAL_EVIDENCE",
        }
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}, clear=True):
            with patch.object(diagnostic, "batched_research",
                    return_value=(research, {first_source}, [], snapshot)), \
                 patch.object(diagnostic, "resolve_source_citations",
                    return_value=(research, {first_source}, [])), \
                 patch.object(diagnostic, "load_or_save_reconciliation",
                    return_value={"unsupported": []}), \
                 patch.object(diagnostic, "validate_source_coverage_audit",
                    return_value=[]), \
                 patch.object(diagnostic, "verify_claimed_source_links"), \
                 patch.object(diagnostic, "load_or_capture_quality",
                    return_value=({"sources": []}, {})), \
                 patch.object(diagnostic, "reconcile_before_freeze",
                    return_value=(research, None)), \
                 patch.object(diagnostic, "freeze_evidence",
                    side_effect=fake_freeze), \
                 patch.object(diagnostic, "load_or_create_review_input",
                    side_effect=fake_input), \
                 patch.object(diagnostic, "screen_or_restore",
                    return_value=blocked) as screen_call, \
                 patch.object(diagnostic, "run_alternating_review_cycles",
                    side_effect=AssertionError("No reviewer may be called")):
                result = research_rehearsal(
                    root=self.root, output=self.audit,
                    researcher=diagnostic.LIVE_RESEARCHER,
                    reviewer=lambda *args: self.fail("Paid review not permitted"),
                    metadata_reader=lambda *args: self.fail("Unexpected page fetch"),
                    now=lambda: self.opened)
        self.assertEqual(len(seen_freeze_flags), 1)
        self.assertEqual(screen_call.call_count, 1)
        self.assertEqual(result["status"],
                         "PRE_REVIEW_EVIDENCE_INSUFFICIENT_NOT_PUBLISHABLE")
        self.assertEqual(result["affirmative_review"], "NOT INVOKED")
        self.assertEqual(result["critical_review"], "NOT INVOKED")
        self.assertEqual(result["publication"], "NOT AUTHORIZED")
        self.assertNotIn("missing_required_directional_balance",
                         result["source_pre_review_directional_counts"]["failures"])
        self.assertEqual((self.root/"data/history.json").read_bytes(),
                         self.original)

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
