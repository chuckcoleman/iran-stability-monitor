"""Offline ChatGPT-first source handoff, V10 and publication fail-closed.

All evidence is synthetic; no web, OpenAI API, gh CLI or paid POST is used.
"""
import copy
import datetime as dt
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))

from chatgpt_handoff import validate_source_dossier, validate_optional_dossier
from review_receipt import digest
from source_research_batches import CATEGORIES
from source_claim_reliability import (
    apply_reviewed_reliability, reconcile_dual_reliability)
from test_v10_claim_reliability import sample_claims, reviewer_rows
from test_alternating_chat_receipt import AlternatingReviewTests
import submit_reviewed_assessment
from review_receipt import verify_all_chatgpt_source_dossiers

CUTOFF="2026-10-25T08:45:00-04:00"
REVIEW="2026-10-25T08:52:00-04:00"
OPEN="2026-10-25T09:00:00-04:00"


def bundle():
    before={"protocol":{"version":"1.0"},"updates":[{"date":"2026-10-18","evidence":[]}]}
    packet=sample_claims(1)
    packet["research_as_of"]=CUTOFF
    packet["published_history_sha256"]=digest(before)
    source=packet["source_quality_audit"]["sources"][0]
    source.update({
        "access_status":"source_metadata_captured",
        "first_publication_clock_status":
            "publisher_supplied_metadata_not_independently_confirmed",
        "assessment":"Synthetic original inspected primary measurement, not proof of event truth.",
        "limitations":"The original site's release clock and independent confirmation remain unknown.",
    })
    coverage=[]
    for idx,cat in enumerate(CATEGORIES):
        if idx==0:
            url=source["url"]
        else:
            url=f"https://context.example.org/{cat}/report"
            packet["source_quality_audit"]["sources"].append({
                "url":url, "origin":"analytical_secondary",
                "classification":"background_only",
                "role":"coverage_context_only",
                "new_evidence_indices":[],
                "access_status":"source_unavailable",
                "first_publication_clock_status":"unknown",
                "assessment":"Separate synthetic source context that is not admitted as an observed event.",
                "limitations":"This source was not independently verified and is contextual only.",
                "corroborating_urls":[],
            })
        coverage.append({
            "category":cat,
            "queries":[f"Iran {cat} independent improving and worsening news"],
            "outcome":"eligible_reporting_found",
            "original_urls":[url],
            "limitations":"Relevant original access and publisher release are not independently proven.",
        })
    packet["source_quality_audit"]["source_count"]=len(coverage)
    affirm=reviewer_rows(packet)
    critical=reviewer_rows(packet)
    for response in (affirm,critical):
        response["source_reviews"]=[{
            "url":s["url"],
            "assessment":"Reviewed distinct reported source material and its material provenance limits.",
            "disposition":("supported_as_qualified" if s["role"]=="new_evidence"
                           else "background_only"),
        } for s in packet["source_quality_audit"]["sources"]]
    result=reconcile_dual_reliability(packet,affirm,critical)
    issued_new=apply_reviewed_reliability(
        packet["evidence"],packet["evidence"],result)
    after=copy.deepcopy(before)
    after["updates"].append({
        "date":"2026-10-25",
        "assessment_evidence_cutoff":CUTOFF,
        "forecasts":[{"event_id":f"synthetic{i}","scored":True,
                      "forecast_open":OPEN} for i in range(4)],
        "evidence":issued_new,
    })
    dossier={
        "version":1,"mode":"chatgpt_first_no_api",
        "research_provenance":
            "CHATGPT_RESEARCH_REPORTED_NOT_API_WEB_SEARCH_TRACE",
        "baseline_sha256":digest(before),
        "candidate_sha256":digest(after),
        "research_as_of":CUTOFF,
        "source_review_completed_at":REVIEW,
        "post_snapshot_interval":"NOT_SEARCHED",
        "provenance_limitations":(
            "ChatGPT-reported web research is not a provider-authenticated "
            "OpenAI Responses tool trace. The cited original text and "
            "publisher chronology require additional independent checking."),
        "coverage":coverage,
        "source_review_packet":packet,
        "affirmative_source_review":affirm,
        "critical_source_review":critical,
        "claim_reliability":result,
    }
    return before,after,dossier


class ChatGPTFirstNoAPITests(unittest.TestCase):
    def test_v10_six_categories_and_dual_grades_with_zero_api_calls(self):
        before,after,dossier=bundle()
        original=copy.deepcopy(dossier)
        verdict=validate_source_dossier(dossier,before,after)
        self.assertEqual(verdict["api_requests"],0)
        self.assertEqual(verdict["category_count"],6)
        self.assertEqual(verdict["source_count"],6)
        self.assertEqual(verdict["new_evidence_count"],1)
        self.assertEqual(dossier,original)
        self.assertEqual(after["updates"][-1]["evidence"][0]["reliability"],
                         "Medium-high")
        self.assertEqual(after["updates"][-1]["evidence"][0][
            "geopolitical_direction_confidence"],"unverified")
        receipt={"version":3,"research_mode":"chatgpt_first_no_api",
                 "source_dossier_sha256":digest(dossier)}
        self.assertEqual(validate_optional_dossier(
            before,after,receipt,dossier),verdict)

    def test_missing_categories_and_fabricated_urls_fail(self):
        for why in ("omit_category","repeat_category","unlisted_url",
                    "add_unreviewed_url","short_search","fake_api_trace"):
            before,after,dossier=bundle()
            if why=="omit_category":
                dossier["coverage"].pop()
            elif why=="repeat_category":
                dossier["coverage"][1]["category"]=dossier["coverage"][0]["category"]
            elif why=="unlisted_url":
                dossier["source_review_packet"]["evidence"][0][
                    "source"]="https://outside.example.org/fabricated"
            elif why=="add_unreviewed_url":
                dossier["coverage"][0]["original_urls"].append(
                    "https://missing.example.org/invented")
            elif why=="short_search":
                dossier["coverage"][0]["queries"]=["X"]
            else:
                dossier["research_provenance"]="OPENAI_API_VERIFIED"
            with self.subTest(why=why),self.assertRaises(ValueError):
                validate_source_dossier(dossier,before,after)

    def test_reviewer_verdict_or_reliability_tampering_fails(self):
        for why in ("critical_missing","critical_reject","fake_grade",
                    "fake_corroboration","mismatched_certificate",
                    "passage_missing","lost_historical_cutoff"):
            before,after,dossier=bundle()
            if why=="critical_missing":
                dossier.pop("critical_source_review")
            elif why=="critical_reject":
                dossier["critical_source_review"]["approved"]=False
                dossier["critical_source_review"]["issues"]=[{"type":"bad"}]
            elif why=="fake_grade":
                after["updates"][-1]["evidence"][0]["reliability"]="High"
                dossier["candidate_sha256"]=digest(after)
            elif why=="fake_corroboration":
                dossier["affirmative_source_review"][
                    "claim_reliability_reviews"][0]["independent_confirmation_ids"]=[
                        "E-UNKNOWN"]
            elif why=="mismatched_certificate":
                dossier["claim_reliability"][0]["factual_reliability"]="High"
            elif why=="passage_missing":
                dossier["source_review_packet"][
                    "pre_review_claim_decisions"][0]["original_passage"]=None
            else:
                dossier["research_as_of"]="2026-10-26T10:00:00-04:00"
            with self.subTest(why=why),self.assertRaises(ValueError):
                validate_source_dossier(dossier,before,after)

    def test_historical_grade_and_cutoff_cannot_be_rewritten(self):
        before,after,dossier=bundle()
        historical={
            "id":"E-20261018-01","evidence_status":"new",
            "source":"https://historic.example.org/report",
            "observation":"Old observation","reliability":"High",
            "direction":"ambiguous","publisher":"Archive publisher",
        }
        before["updates"][-1]["evidence"].append(copy.deepcopy(historical))
        after["updates"][0]=copy.deepcopy(before["updates"][0])
        after["updates"][-1]["evidence"].append({
            **historical,"evidence_status":"carried_forward"})
        dossier["baseline_sha256"]=digest(before)
        dossier["candidate_sha256"]=digest(after)
        dossier["source_review_packet"]["published_history_sha256"]=digest(before)
        validate_source_dossier(dossier,before,after)
        after["updates"][-1]["evidence"][-1]["reliability"]="Medium"
        dossier["candidate_sha256"]=digest(after)
        with self.assertRaisesRegex(ValueError,"Carried-forward"):
            validate_source_dossier(dossier,before,after)

    def test_time_window_and_receipt_digest_fail_closed(self):
        for why in ("wrong_base","future_review","stale_review",
                    "wrong_research_asof","wrong_receipt","wrong_mode"):
            before,after,dossier=bundle()
            receipt={"version":3,"research_mode":"chatgpt_first_no_api",
                     "source_dossier_sha256":digest(dossier)}
            if why=="wrong_base":
                dossier["baseline_sha256"]="0"*64
            elif why=="future_review":
                dossier["source_review_completed_at"]="2026-10-25T11:00:00-04:00"
            elif why=="stale_review":
                dossier["source_review_completed_at"]="2026-10-25T06:00:00-04:00"
            elif why=="wrong_research_asof":
                dossier["research_as_of"]="2026-10-25T00:00:00-04:00"
            elif why=="wrong_receipt":
                receipt["source_dossier_sha256"]="0"*64
            else:
                receipt["research_mode"]="openai_api"
            with self.subTest(why=why),self.assertRaises(ValueError):
                validate_optional_dossier(before,after,receipt,dossier)

    def test_code_only_changes_cannot_silently_rewrite_old_dossier(self):
        before,after,dossier=bundle()
        date=after["updates"][-1]["date"]
        receipt={"version":3,"research_mode":"chatgpt_first_no_api",
                 "source_dossier_sha256":digest(dossier)}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/"data/source-dossiers").mkdir(parents=True)
            (root/"data/review-receipts").mkdir()
            path=root/"data/source-dossiers"/(date+".json")
            review=root/"data/review-receipts"/(date+".json")
            path.write_text(json.dumps(dossier))
            review.write_text(json.dumps(receipt))
            self.assertEqual(
                verify_all_chatgpt_source_dossiers(root,after),1)
            damaged=copy.deepcopy(dossier)
            damaged["coverage"][0]["limitations"] += (
                " Unreviewed attempted source-status change.")
            path.write_text(json.dumps(damaged))
            with self.assertRaisesRegex(ValueError,
                                        "source dossier|dossier"):
                verify_all_chatgpt_source_dossiers(root,after)
            path.write_text(json.dumps(dossier))
            review.unlink()
            with self.assertRaisesRegex(ValueError,
                                        "matching review receipt"):
                verify_all_chatgpt_source_dossiers(root,after)
            review.write_text(json.dumps({
                "version":3,"research_mode":"different_handoff",
                "source_dossier_sha256":digest(dossier),
            }))
            with self.assertRaisesRegex(ValueError,
                                        "detached"):
                verify_all_chatgpt_source_dossiers(root,after)
            path.unlink()
            review.write_text(json.dumps(receipt))
            with self.assertRaisesRegex(ValueError,
                                        "Missing bound"):
                verify_all_chatgpt_source_dossiers(root,after)

    def test_modern_v3_chat_handoff_validates_without_api_and_needs_draft(self):
        case=AlternatingReviewTests("test_one_clean_cycle_accepted")
        case.setUp()
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);root=work/"checkout";folder=work/"reviewed"
            (root/"data").mkdir(parents=True)
            (root/"schema").mkdir()
            (folder/"data/review-receipts").mkdir(parents=True)
            (folder/"data/review-drafts").mkdir()
            (folder/"data/review-reports").mkdir()
            shutil.copyfile(ROOT/"schema/history.schema.json",
                            root/"schema/history.schema.json")
            (root/"data/history.json").write_text(json.dumps(case.before))
            (folder/"history-before.json").write_text(json.dumps(case.before))
            (folder/"data/history.json").write_text(json.dumps(case.after))
            date=case.opened.date().isoformat()
            (folder/"data/review-receipts"/(date+".json")).write_text(
                json.dumps(case.receipt))
            (folder/"data/review-drafts"/(date+".json")).write_text(
                json.dumps(case.draft))
            (folder/"data/review-reports"/(date+".md")).write_bytes(case.report)
            t=case.opened+dt.timedelta(minutes=6)
            result=submit_reviewed_assessment.validate_handoff(
                folder,root=root,now=t)
            self.assertEqual(result["date"],date)
            self.assertIn("draft_file",result)
            self.assertIn("report_file",result)
            (folder/"data/review-drafts"/(date+".json")).unlink()
            with self.assertRaisesRegex(RuntimeError,"frozen draft"):
                submit_reviewed_assessment.validate_handoff(
                    folder,root=root,now=t)
            self.assertFalse((root/"data/review-receipts").exists())


if __name__=="__main__":
    unittest.main()
