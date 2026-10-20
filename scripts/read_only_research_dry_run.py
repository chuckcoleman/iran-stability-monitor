#!/usr/bin/env python3
"""Explicit unpublishable LIVE-source + dual-review test (never forecast issuance).

For the actual Sunday forecast pipeline, use the separately governed
ChatGPT-first process. This diagnostic never elicits scored forecasts, writes
data/history.json, opens a PR, touches Pages, or posts to Metricool/X.
It is safe to run on any day, including Tuesdays. For full end-to-end
Sunday issuance certification the result must say NOT TESTED.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys

from assessment_pipeline import (
    ROOT, RESEARCH, check, clock, llm, freeze_evidence,
    validate_source_coverage_audit, _review_issues,
)
from source_metadata import capture_metadata, url_key
from source_quality_audit import (
    source_inventory, source_quality_audit, save_quality_audit,
    validate_source_review)
from source_citation_resolution import resolve_source_citations
from source_search_trace import load_matching_search_trace, verify_claimed_source_links
from source_citation_reconciliation import (
    reconcile_source_citations, save_reconciliation, require_supported_citations)


SOURCE_REVIEW_COMMON = """
No new web search: inspect the EXACT closed test-only evidence, SIX
source-category rows, and EVERY entry in source_quality_audit.sources.
Return source_reviews for each original URL (even background-only):
url, specific assessment at least 30 characters, disposition of
supported_as_qualified / background_only / unverified_reject.
If material claims are unverified, global approval MUST be false with
a specific issue. Unknown original release instants must be disclosed,
not fabricated; cited links never prove observed events. Check
first-publication time status, citation provenance, independent corroboration,
reporting versus opinion, shared wire/official claims, and limits of any
conclusion. Review what the snapshot actually demonstrates. Distinguish
searched-but-empty from inaccessible. The test is not a Sunday forecast.
Return ONLY JSON {"approved": boolean, "issues": [
{"type": "specific issue type", "location": "source ID/coverage category",
 "reason": "actual actionable defect"}]}.
Approve only for zero substantive unresolved issues.
"""


def _audit_folder(root, output):
    root=Path(root).resolve()
    folder=Path(output).resolve()
    check(folder != root and root not in folder.parents
          or folder == root / ".automation-audit",
          "Nonpublishing audit must be outside checkout or the ignored audit directory")
    folder.mkdir(parents=True,exist_ok=True)
    return folder


def research_rehearsal(*, root=ROOT, output=None, researcher=llm, reviewer=llm,
                       metadata_reader=capture_metadata, now=clock):
    """Research + two genuine source-only editorial reviews without publication.

    Injecting synthetic researcher/reviewer in tests is always flagged as
    synthetic. Even genuine API research does not produce a scored assessment.
    """
    root=Path(root).resolve()
    folder=_audit_folder(root, output or root / ".automation-audit")
    check(os.environ.get("GH_TOKEN") is None and
          os.environ.get("METRICOOL_API_TOKEN") is None,
          "Read-only research diagnostic must not hold GitHub write or X tokens")
    if os.getenv("GITHUB_ACTIONS")=="true":
        check(os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch",
              "Live research diagnostics must be manually invoked, never scheduled")
    before=(root/"data/history.json").read_bytes()
    baseline_sha=hashlib.sha256(before).hexdigest()
    history=json.loads(before)
    stamp=now()
    check(stamp.tzinfo is not None, "Test time needs a timezone")
    day=stamp.date().isoformat()
    check(day>=history["updates"][-1]["date"], "Research test cannot use past cutoff")
    saved=[]
    for u in history["updates"]:
        saved.extend(u.get("evidence",[]))
    # Gather real or synthetic source results once; no forecast prompt anywhere.
    previous_audit=os.environ.get("IRAN_OFFLINE_REVIEW_DIR")
    os.environ["IRAN_OFFLINE_REVIEW_DIR"]=str(folder)
    try:
        result, citations=researcher(
            RESEARCH.format(date=day, prior=json.dumps(saved,ensure_ascii=False)), True)
    finally:
        if previous_audit is None:
            os.environ.pop("IRAN_OFFLINE_REVIEW_DIR",None)
        else:
            os.environ["IRAN_OFFLINE_REVIEW_DIR"]=previous_audit
    check(isinstance(result,dict), "Source model returned no structured evidence")
    actual_calls=None
    if researcher is llm:
        actual_calls=load_matching_search_trace(folder,result)
        result,citations,actual_calls=resolve_source_citations(
            result,citations,actual_calls,researcher=researcher,audit_dir=folder)
    reconciliation=reconcile_source_citations(result,citations,actual_calls)
    save_reconciliation(folder,reconciliation)
    if reconciliation["unsupported"]:
        # Preserve ALL claimed URLs and precisely why they cannot be admitted.
        # This is a rejected test-only diagnostic, NOT reviewed evidence.
        blocked={
            "status":"UNSUPPORTED_CITATIONS_FLAGGED_NOT_PUBLISHABLE",
            "source_citation_reconciliation":reconciliation,
            "baseline_history_sha256":baseline_sha,
            "prospective_forecasts":"NOT TESTED",
            "affirmative_review":"NOT REACHED; PREFREEZE REJECTED",
            "critical_review":"NOT REACHED; PREFREEZE REJECTED",
            "freeze_evidence":"BLOCKED",
            "GitHub_PR_or_Pages_or_X":"NOT INVOKED",
            "limitations":"Uncited or unsupported URLs are kept as flagged claims, "
                          "never silently dropped, rewritten or promoted to evidence."}
        (folder/"research-dry-run.json").write_text(
            json.dumps(blocked,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        check((root/"data/history.json").read_bytes()==before,
              "Flagged source dry-run changed published history")
        require_supported_citations(reconciliation)
    coverage=validate_source_coverage_audit(result.get("coverage_audit"),citations)
    if researcher is llm:
        verify_claimed_source_links(coverage,actual_calls)
    metadata={}
    for url in source_inventory(result):
        check(url_key(url) in {url_key(u) for u in citations},
              "Source quality audit URL missing from citations")
        metadata[url]=metadata_reader(url)
    cutoff=now()
    quality=source_quality_audit(result,metadata,strict=(researcher is llm),
                                 cutoff=cutoff)
    save_quality_audit(folder,quality)
    archive={"evidence": saved}
    frozen=freeze_evidence(result,citations,archive,day,cutoff,metadata)
    reviewers={}
    sample={"evidence":frozen,"coverage":coverage,"source_quality_audit":quality,
            "cutoff":cutoff.isoformat(),
            "published_history_sha256":baseline_sha,
            "mode":"RESEARCH_ONLY_TEST_NO_SCORED_FORECASTS"}
    canonical=json.dumps(sample,ensure_ascii=False,sort_keys=True,
                         separators=(",",":"),allow_nan=False)
    frozen_sha=hashlib.sha256(canonical.encode()).hexdigest()
    try:
        for role in ("affirmative","critical"):
            prompt=("ROLE: "+role.upper()+" SOURCE QUALITY REVIEW. " +
                    ("Seek verifiable supporting and disconfirming context. "
                     if role=="affirmative" else
                     "Adversarially challenge all substantive claims and source gaps. ") +
                    SOURCE_REVIEW_COMMON + "\nIdentical input SHA-256: " +
                    frozen_sha + "\nInput: " + canonical)
            previous_audit=os.environ.get("IRAN_OFFLINE_REVIEW_DIR")
            os.environ["IRAN_OFFLINE_REVIEW_DIR"]=str(folder)
            try:
                response,_=reviewer(prompt,False)
            finally:
                if previous_audit is None:
                    os.environ.pop("IRAN_OFFLINE_REVIEW_DIR",None)
                else:
                    os.environ["IRAN_OFFLINE_REVIEW_DIR"]=previous_audit
            issues=_review_issues(response,role)
            if reviewer is llm:
                validate_source_review(response,quality,role)
            reviewers[role]={"approved":not bool(issues),"issues":issues,
                             "source_reviews":response.get("source_reviews",[]),
                             "completed_at":now().isoformat(),"draft_sha256":frozen_sha}
        approved=all(x["approved"] for x in reviewers.values())
        status=("RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE" if approved
                else "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE")
    finally:
        check((root/"data/history.json").read_bytes()==before,
              "Source dry-run altered the immutable published history")
    report={"status":status,"reviewers":reviewers,
            "source_citation_reconciliation":reconciliation,
            "research_input_sha256":frozen_sha,
            "baseline_history_sha256":baseline_sha,
            "actual_cutoff":cutoff.isoformat(),"source_coverage":coverage,
            "source_metadata":metadata,"source_quality_audit":quality,
            "frozen_test_evidence":frozen,
            "source_citations":sorted(citations),
            "actual_search_tool_calls":actual_calls or [],
            "actual_live_model_used":researcher is llm and reviewer is llm,
            "mode":"RESEARCH_ONLY_NONPUBLISHING",
            "prospective_forecasts":"NOT TESTED",
            "full_15_section_report_review":"NOT TESTED",
            "Sunday_publication_receipt":"NOT CREATED",
            "GitHub_PR_or_Pages_or_X":"NOT INVOKED",
            "limitations":"No Sunday forecasts, actual issuance, dashboard browser render, "
                          "public deployment or social posting were tested. "
                          "A model-reported category audit does not prove every query ran."}
    dest=folder/"research-dry-run.json"
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    check((root/"data/history.json").read_bytes()==before,
          "Source dry-run changed published history after audit")
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",default=None,
                        help="External audit output folder (default: ignored .automation-audit)")
    args=parser.parse_args(argv)
    summary=research_rehearsal(output=args.output_dir)
    print("SOURCE-ONLY LIVE TEST (NEVER PUBLISHABLE): "+summary["status"])
    if not all(v["approved"] for v in summary["reviewers"].values()):
        raise SystemExit(1)


if __name__=="__main__":
    main()

