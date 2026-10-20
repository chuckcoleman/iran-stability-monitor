"""Exact pre-freeze citation flags; never silently normalize or accept aliases."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
from source_citation_reconciliation import (
    reconcile_source_citations, save_reconciliation, require_supported_citations)
from assessment_pipeline import produce, SOURCE_SCAN_GROUPS
from automation_fixtures import fixture
from read_only_research_dry_run import research_rehearsal


A="https://apnews.com/article/actual-111111111111"
B="https://www.iranintl.com/en/202610205555"
C="https://news.example.org/report?utm_source=sample"
C_CITED="https://news.example.org/report"
BAD="https://apnews.com/article/guessed-similar-222222222222"


def trace(*urls):
    return [{"search_calls_real":True,
             "citation_sources_exposed_by_api":[{"url":url} for url in urls]}]


def sample():
    return {
      "coverage_audit":[
          {"category":"international_media",
           "original_urls":[A,BAD,C],
           "queries":["sample AP reporting"],
           "outcome":"eligible_reporting_found",
           "limitations":"This is a synthetic test and no source truth is implied."}],
      "evidence":[
          {"source":A,"evidence_status":"new"},
          {"source":BAD,"evidence_status":"new"},
          {"source":B,"evidence_status":"carried_forward","id":"E-ARCHIVED"}]}


class SourceCitationFlagsTests(unittest.TestCase):
    def test_original_unsupported_url_is_retained_and_flagged_in_both_places(self):
        out=reconcile_source_citations(sample(),{A,C_CITED},trace(A,C_CITED))
        self.assertEqual(out["counts"]["coverage_url_claims"],3)
        self.assertEqual(out["counts"]["unsupported_coverage_claims"],1)
        self.assertEqual(out["counts"]["unsupported_evidence_claims"],1)
        self.assertEqual(out["counts"]["unsupported_unique_urls"],1)
        self.assertEqual(out["unsupported_unique_urls"],[BAD])
        self.assertIn("not_in_response_citations",out["unsupported"][0]["flags"])
        self.assertIn("not_in_actual_web_search_sources",out["unsupported"][0]["flags"])
        self.assertEqual(out["unsupported"][0]["claimed_url"],BAD)
        self.assertEqual(out["status"],"UNSUPPORTED_CITATIONS_FLAGGED")
        with self.assertRaisesRegex(ValueError,"evidence freeze.*blocked"):
            require_supported_citations(out)

    def test_tracking_key_normalization_only_when_exact_content_url_matches(self):
        out=reconcile_source_citations(sample(),{A,C_CITED},trace(A,C_CITED))
        valid=[x for x in out["all_claims"] if x["claimed_url"]==C][0]
        self.assertEqual(valid["status"],"CITED_TOOL_MATCH")
        self.assertEqual(valid["normalized_claimed_url"],C_CITED)

    def test_annotation_without_actual_tool_exposure_is_flagged(self):
        out=reconcile_source_citations(sample(),{A,BAD,C_CITED},trace(A,C_CITED))
        rows=[x for x in out["unsupported"] if x["claimed_url"]==BAD]
        self.assertEqual(len(rows),2)
        for row in rows:
            self.assertTrue(row["in_response_citations"])
            self.assertFalse(row["in_actual_search_tool_sources"])
            self.assertEqual(row["flags"],["not_in_actual_web_search_sources"])

    def test_invalid_http_or_private_url_is_never_admitted(self):
        data=sample()
        data["coverage_audit"][0]["original_urls"]=["http://insecure.example.org/story"]
        data["evidence"]=[{"source":"http://insecure.example.org/story"}]
        out=reconcile_source_citations(data,set(),trace(A))
        self.assertEqual(out["counts"]["unsupported_claims"],2)
        self.assertIn("invalid_public_https_url",out["unsupported"][0]["flags"])

    def test_duplicate_within_category_flagged_without_replacing_claims(self):
        data=sample()
        data["coverage_audit"][0]["original_urls"]=[A,A]
        data["evidence"]=[{"source":A}]
        out=reconcile_source_citations(data,{A},trace(A))
        self.assertEqual(out["counts"]["unsupported_claims"],1)
        self.assertEqual(out["unsupported"][0]["flags"],
                         ["duplicate_url_within_research_category"])

    def test_clean_exact_matching_and_carried_forward_are_allowed(self):
        data={"coverage_audit":[{"original_urls":[A]}],
              "evidence":[{"source":A},{"source":BAD,
                           "id":"E-ARCHIVED","evidence_status":"carried_forward"}]}
        out=reconcile_source_citations(data,{A},trace(A))
        self.assertEqual(out["status"],"ALL_CLAIMED_LINKS_MATCH")
        self.assertTrue(require_supported_citations(out))
        self.assertEqual(out["counts"]["new_evidence_url_claims"],1)

    def test_synthetic_mode_records_tool_provenance_as_not_tested(self):
        out=reconcile_source_citations(
            {"coverage_audit":[{"original_urls":[A]}],"evidence":[{"source":A}]},
            {A},None)
        self.assertEqual(out["status"],"ALL_CLAIMED_LINKS_MATCH")
        self.assertEqual(out["all_claims"][0]["status"],
                         "CITED_TOOL_PROVENANCE_NOT_TESTED")
        self.assertIsNone(out["all_claims"][0]["in_actual_search_tool_sources"])

    def test_audit_preserves_exact_flags_and_refuses_overwrite(self):
        output=reconcile_source_citations(sample(),{A,C_CITED},trace(A,C_CITED))
        with tempfile.TemporaryDirectory() as temp:
            path=save_reconciliation(temp,output)
            self.assertEqual(json.loads(path.read_text()),output)
            with self.assertRaisesRegex(ValueError,"already exists"):
                save_reconciliation(temp,output)

    def test_production_research_fails_before_forecast_if_any_unsupported_url(self):
        history,analysis,evidence,opened=fixture()
        source_urls={item["source"] for item in evidence}
        extra="https://unverified.example.org/not-in-tools"
        audit_rows=[{"category":category,"original_urls":[],
                     "queries":["Synthetic narrow topic search"],
                     "outcome":"searched_no_eligible_evidence",
                     "limitations":"This is an artificial source test, not verified coverage."}
                    for category in SOURCE_SCAN_GROUPS]
        audit_rows[1]["original_urls"]=[extra]
        audit_rows[1]["outcome"]="eligible_reporting_found"
        seen=[]
        def researcher(prompt,search):
            seen.append("research")
            return {"evidence":copy.deepcopy(evidence),
                    "coverage_audit":audit_rows},source_urls
        def forbidden(*args):
            seen.append("FORBIDDEN")
            raise AssertionError("Model assessment must not be invoked")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ,{"IRAN_OFFLINE_REVIEW_DIR":tmp,
                                          "GITHUB_ACTIONS":"false"},clear=True):
                with self.assertRaisesRegex(ValueError,"Unsupported citations FLAGGED"):
                    produce(history,researcher=researcher,
                            assessor=forbidden,now=lambda:opened,
                            metadata_reader=forbidden,reviewer=forbidden)
            flagged=json.loads((Path(tmp)/"citation-reconciliation.json").read_text())
            self.assertEqual(flagged["counts"]["unsupported_coverage_claims"],1)
            self.assertEqual(flagged["unsupported"][0]["claimed_url"],extra)
            self.assertEqual(seen,["research"])
            self.assertFalse((Path(tmp)/"frozen-evidence.json").exists())

    def test_research_only_diagnostic_retains_flags_before_any_review_or_freeze(self):
        history,analysis,evidence,opened=fixture()
        original_data=json.dumps(history).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"checkout"
            (root/"data").mkdir(parents=True)
            (root/"data/history.json").write_bytes(original_data)
            output=Path(tmp)/"results"
            def research(prompt,search):
                return {"coverage_audit":[{
                        "category":"international_media","original_urls":[BAD]}],
                        "evidence":[{"source":A}]},{A}
            def review(*args):
                raise AssertionError("Review must not approve rejected citations")
            with patch.dict(os.environ,{"GITHUB_ACTIONS":"false"},clear=True):
                with self.assertRaisesRegex(ValueError,"Unsupported citations FLAGGED"):
                    research_rehearsal(root=root,output=output,
                                       researcher=research,reviewer=review,
                                       now=lambda:opened)
            diag=json.loads((output/"research-dry-run.json").read_text())
            self.assertEqual(diag["status"],
                             "UNSUPPORTED_CITATIONS_FLAGGED_NOT_PUBLISHABLE")
            self.assertIn("NOT REACHED",diag["affirmative_review"])
            self.assertEqual(diag["source_citation_reconciliation"]["counts"]
                             ["unsupported_claims"],1)
            self.assertEqual((root/"data/history.json").read_bytes(),original_data)


if __name__=="__main__":
    unittest.main()
