"""End-to-end nonpublishing V10 original-body/review/receipt rehearsal.

No external requests, real publisher content, forecasts, PR, deployment or X.
The synthetic bundle MUST fail any attempted production submission.
"""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/"scripts"))
sys.path.insert(0, str(ROOT/"tests"))
import test_alternating_chat_receipt
from test_v10_claim_reliability import reviewer_rows
from report_section_review import report_inventory
from review_receipt import digest, checked_receipt
from source_research_batches import CATEGORIES
from source_claim_reliability import reconcile_dual_reliability, apply_reviewed_reliability
from source_passage_audit import visible_text
from chatgpt_handoff import validate_source_dossier
from submit_reviewed_assessment import validate_handoff
from followup_fixtures import attach_followup


def synthetic_complete_bundle():
    case=test_alternating_chat_receipt.AlternatingReviewTests("test_one_clean_cycle_accepted")
    case.setUp()
    start=case.opened
    cutoff=(start-dt.timedelta(seconds=10)).isoformat()
    completed=(start-dt.timedelta(seconds=3)).isoformat()
    retrieval=(start-dt.timedelta(seconds=15)).isoformat()
    originally=copy.deepcopy([e for e in case.after["updates"][-1]["evidence"]
                               if e.get("evidence_status")=="new"])
    by_url={}
    for idx,e in enumerate(originally):
        by_url.setdefault(e["source"], []).append((idx,e))
    original_html={}
    decisions=[]
    sources=[]
    for url,rows in by_url.items():
        passages={}
        chunks=[]
        for index, e in rows:
            passage=("This original synthetic demonstration paragraph describes "
                     f"the documented fictional item number {index} for the test.")
            passages[e["id"]]=passage
            chunks.append("<p>"+passage+"</p>")
        raw=("<html><body>"+"".join(chunks)+"</body></html>").encode()
        original_html[url]=raw
        visible=visible_text(raw)
        for index,e in rows:
            passage=passages[e["id"]]
            cap={
                "original_url":url,"final_url":url,"retrieved_at":retrieval,
                "content_type":"text/html","charset":"utf-8",
                "source_body_sha256":hashlib.sha256(raw).hexdigest(),
                "visible_text_sha256":hashlib.sha256(visible.encode()).hexdigest(),
                "passage_offset":visible.index(passage),"passage":passage,
            }
            decisions.append({
                "id":e["id"],"original_url":url,
                "original_passage":passage,
                "passage_status":"EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED",
                "source_body_sha256":cap["source_body_sha256"],
                "capture_verification":cap,
                "capture_verification_sha256":digest(cap),
                "decision":"PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW",
            })
        sources.append({
            "url":url,"classification":"direct_observation",
            "origin":"original_reporting","role":"new_evidence",
            "new_evidence_indices":[i for i,_ in rows],
            "corroborating_urls":[],
            "access_status":"source_metadata_captured",
            "first_publication_clock_status":"publisher_supplied_metadata_not_independently_confirmed",
            "assessment":"Synthetic original article used for test-only validation; no real geopolitical claim.",
            "limitations":"The synthetic document was locally generated and cannot establish a genuine first publication clock.",
            "access_channels":{
                "search":{"status":"accessible_reported", "checked_at":retrieval,
                          "limitations":"A synthetic search-stage claim is not authenticated evidence."},
                "metadata":{"status":"captured","http_status":200,
                            "limitations":"Synthetic HTTP metadata does not prove a publisher released the document."},
                "body":{"status":"captured","captured_claim_ids":[e["id"] for _,e in rows],
                        "limitations":"Raw synthetic page bytes are held outside the mock repository."},
                "same_stage_conflicts":[],
            },
        })
    packet={
        "pre_review_admission_version":7,
        "research_as_of":cutoff,
        "published_history_sha256":digest(case.before),
        "evidence":originally,
        "pre_review_claim_decisions":decisions,
        "source_quality_audit":{"sources":sources,"source_count":len(sources)},
    }
    affirm=reviewer_rows(packet,quality="attributed_edited_original",
                        direct="firsthand_original_reporting")
    critical=copy.deepcopy(affirm)
    coverage=[]
    for i,cat in enumerate(CATEGORIES):
        coverage.append({
            "category":cat,
            "queries":["Iran "+cat+" worsening reports synthetic search",
                       "Iran "+cat+" stabilizing reports synthetic search"],
            "outcome":"eligible_reporting_found",
            "original_urls":[list(by_url)[i%len(by_url)]],
            "limitations":"This deliberately synthetic source category cannot provide authentic current evidence.",
        })
    for role in (affirm,critical):
        role["source_reviews"]=[{
            "url":s["url"],
            "assessment":"Reviewed the source as fictional test data, separating provenance from inference.",
            "disposition":"supported_as_qualified",
            "access_stage_assessment":"Compared fictional search, metadata and original body stages separately for the test.",
            "same_stage_conflicts_resolved":True,
        } for s in sources]
        role["audit_integrity_review"]={
            "audit_status":"complete_with_disclosed_limitations",
            "source_count":len(sources),
            "coverage_categories":sorted(CATEGORIES),
            "research_as_of":cutoff,
            "metadata_access_scope":"metadata_only_not_full_article",
            "first_publication_verified":False,
            "historical_context_is_current_evidence":False,
            "post_snapshot_search":"NOT_SEARCHED",
            "assessment":"This simulated audit covers six constructed classes, including separate source access streams for each locally generated article.",
            "limitations":"These are synthetic input pages, not a public publisher site; no actual media collection, source authenticity or real inference was verified.",
        }
        role["source_adequacy_review"]={
            "admitted_evidence_ids":[e["id"] for e in originally],
            "observation_count":len(originally),
            "conclusion":"supported_limited_inference",
            "assessment":"This is a synthetic evaluator fixture whose artificially stipulated observations are logically sufficient within the synthetic model only.",
            "limitations":"This artificial adequacy decision must never be interpreted as sufficient evidence for a live Iranian stability assessment.",
        }
        role["source_query_balance_review"]={
            "raises_queries":[coverage[0]["queries"][0]],
            "lowers_queries":[coverage[0]["queries"][1]],
            "ambiguous_queries":[],
            "assessment":"The fixture has disjoint worsening and stabilizing synthetic queries but none are evidence of an actual web search.",
        }
    attach_followup(packet, cutoff, affirm, critical)
    cert=reconcile_dual_reliability(packet,affirm,critical)
    amended=apply_reviewed_reliability(originally,originally,cert)
    for obj in (case.draft, case.after):
        rows=obj["updates"][-1]["evidence"]
        new={e["id"]:e for e in amended}
        obj["updates"][-1]["evidence"]=[new.get(e["id"],e) for e in rows]
    newhash=digest(case.draft)
    originalhash=case.hash
    matrix=case.receipt["approval"]["rounds"][0]["section_reviews"]
    for section in matrix.values():
        for role in ("affirmative","critical"):
            section[role]["draft_sha256"]=newhash
        for v in section["item_reviews"].values():
            for role in ("affirmative","critical"):
                v[role]["draft_sha256"]=newhash
    matrix_sha=digest(matrix)
    case.receipt["approval"]["draft_sha256"]=newhash
    for role in ("affirmative","critical"):
        case.receipt["approval"][role]["draft_sha256"]=newhash
        case.receipt["approval"]["rounds"][0][role]["draft_sha256"]=newhash
    case.receipt["approval"]["rounds"][0]["draft_sha256"]=newhash
    case.receipt["report_section_review_sha256"]=matrix_sha
    text=case.report.decode().replace(originalhash,newhash).replace(case.section_sha,matrix_sha)
    case.report=text.encode()
    case.receipt["report_sha256"]=hashlib.sha256(case.report).hexdigest()
    case.receipt["candidate_sha256"]=digest(case.after)
    case.receipt["record_sha256"]=digest(case.after["updates"][-1])
    dossier={
        "version":1,"mode":"chatgpt_first_no_api",
        "research_provenance":"CHATGPT_RESEARCH_REPORTED_NOT_API_WEB_SEARCH_TRACE",
        "baseline_sha256":digest(case.before),
        "candidate_sha256":digest(case.after),
        "research_as_of":cutoff,
        "source_review_completed_at":completed,
        "post_snapshot_interval":"NOT_SEARCHED",
        "provenance_limitations":(
            "This synthetic ChatGPT demonstration does not prove that real searches, "
            "source authentication, publication times, or editorial reviews occurred."),
        "coverage":coverage,
        "source_review_packet":packet,
        "affirmative_source_review":affirm,
        "critical_source_review":critical,
        "claim_reliability":cert,
        "preforecast_certificate":{
            "version":1,"status":"DUAL_SOURCE_REVIEW_CLEAN_LIMITED_INFERENCE",
            "research_as_of":cutoff,"source_review_completed_at":completed,
            "baseline_sha256":digest(case.before),
            "source_packet_sha256":digest(packet),
            "affirmative_source_review_sha256":digest(affirm),
            "critical_source_review_sha256":digest(critical),
            "claim_reliability_sha256":digest(cert),
        },
    }
    case.receipt["research_mode"]="chatgpt_first_no_api"
    case.receipt["source_dossier_sha256"]=digest(dossier)
    case.receipt["preforecast_certificate_sha256"]=digest(dossier["preforecast_certificate"])
    return case,dossier,original_html


class CompleteBundleTests(unittest.TestCase):
    def test_complete_v10_with_real_synthetic_body_bytes_and_no_publication(self):
        case,dossier,bodies=synthetic_complete_bundle()
        self.assertTrue(checked_receipt(case.before,case.after,case.receipt,
                                        reviewed_draft=case.draft,
                                        report_bytes=case.report,
                                        now=case.opened+dt.timedelta(minutes=6)))
        self.assertEqual(validate_source_dossier(dossier,case.before,case.after)["source_count"],len(bodies))
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            root=work/"checkout"
            bundle=work/"test-only-handoff"
            (root/"data").mkdir(parents=True)
            (root/"schema").mkdir()
            (bundle/"data/review-receipts").mkdir(parents=True)
            (bundle/"data/review-drafts").mkdir()
            (bundle/"data/review-reports").mkdir()
            (bundle/"data/source-dossiers").mkdir()
            (bundle/"source-captures").mkdir()
            shutil.copyfile(ROOT/"schema/history.schema.json",
                            root/"schema/history.schema.json")
            (root/"data/history.json").write_text(json.dumps(case.before))
            (bundle/"history-before.json").write_text(json.dumps(case.before))
            (bundle/"data/history.json").write_text(json.dumps(case.after))
            day=case.opened.date().isoformat()
            (bundle/"data/review-receipts"/(day+".json")).write_text(json.dumps(case.receipt))
            (bundle/"data/review-drafts"/(day+".json")).write_text(json.dumps(case.draft))
            (bundle/"data/review-reports"/(day+".md")).write_bytes(case.report)
            (bundle/"data/source-dossiers"/(day+".json")).write_text(json.dumps(dossier))
            for e in dossier["source_review_packet"]["evidence"]:
                path=bundle/"source-captures"/(e["id"]+".html")
                path.write_bytes(bodies[e["source"]])
            (bundle/"DO_NOT_PUBLISH.txt").write_text(
                "Synthetic pages and reviewers. NEVER submit to GitHub.")
            result=validate_handoff(bundle,root=root,now=case.opened+dt.timedelta(minutes=6),test_only=True)
            self.assertEqual(result["date"],day)
            self.assertIn("dossier_file",result)
            with self.assertRaises((RuntimeError,ValueError)):
                validate_handoff(bundle,root=root,now=case.opened+dt.timedelta(minutes=6))
            e=dossier["source_review_packet"]["evidence"][0]
            path=bundle/"source-captures"/(e["id"]+".html")
            path.write_bytes(path.read_bytes()+b"tampered")
            with self.assertRaisesRegex(ValueError,"source-body SHA-256"):
                validate_handoff(bundle,root=root,now=case.opened+dt.timedelta(minutes=6),test_only=True)

if __name__=="__main__":
    unittest.main()
