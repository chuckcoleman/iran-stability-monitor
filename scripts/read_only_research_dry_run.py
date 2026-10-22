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
    ROOT, RESEARCH, check, clock, llm, LIVE_RESEARCHER, freeze_evidence,
    validate_source_coverage_audit, _review_issues,
)
from source_metadata import capture_metadata, url_key
from source_research_batches import batched_research, CATEGORIES, require_pre_snapshot_publication, _resume_get_only
from source_quality_audit import (
    source_inventory, source_quality_audit, save_quality_audit,
    validate_source_review)
from source_citation_resolution import resolve_source_citations
from source_review_resume import (
    load_or_save_reconciliation, load_or_capture_quality,
    load_or_create_review_input)
from source_review_cycles import run_alternating_review_cycles
from source_passage_audit import build_claim_register
from source_evidence_status import reconcile_before_freeze
from source_pre_review_admissibility import screen_or_restore

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
 "reason": "actual actionable defect"}],
"source_reviews": [{"url": "exact source URL", "assessment":
"specific >=30-character finding", "disposition":
"supported_as_qualified|background_only|unverified_reject"}]}.
No missing/extra source reviews; the global verdict must agree.
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


def admission_deficiency_report(preflight, snapshot):
    """Explain a failed V6 closed-source screen without approving any claim.

    This is a deterministic projection of the original saved source gate. It
    neither reclassifies an observation nor schedules/retries paid research.
    """
    if (not isinstance(preflight, dict) or not isinstance(snapshot, dict)
            or snapshot.get("version") != 6):
        raise ValueError("Deficiency report requires a V6 original source audit")
    if preflight.get("status") != "PRE_REVIEW_ADMISSIBILITY_BLOCKED_NO_PAID_REVIEWS":
        raise ValueError("Deficiency report cannot certify approved research")
    entries = preflight.get("per_claim")
    counts = preflight.get("directional_candidate_counts")
    if (not isinstance(entries, list) or not isinstance(counts, dict)
            or not isinstance(counts.get("failures"), list)):
        raise ValueError("Missing saved claim-level or aggregate gate reasons")
    reported = []
    reason_counts = {}
    ids = set()
    for row in entries:
        if (not isinstance(row, dict) or
                not isinstance(row.get("id"), str) or not row["id"] or
                not isinstance(row.get("reasons"), list) or
                not all(isinstance(reason, str) and reason for reason in row["reasons"]) or
                row["id"] in ids):
            raise ValueError("Malformed original claim rejection evidence")
        ids.add(row["id"])
        reasons = sorted(set(row["reasons"]))
        for reason in reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        reported.append({
            "evidence_id": row["id"],
            "original_decision": row.get("decision"),
            "original_rejection_reasons": reasons,
        })
    if len(ids) != (len(preflight.get("admitted_original_ids", [])) +
                    len(preflight.get("held_original_ids", []))):
        raise ValueError("Saved claim gate identifier counts are inconsistent")
    return {
        "version": 1,
        "status": "SOURCE_ADMISSION_GAPS_ONLY_NOT_PUBLISHABLE",
        "source_snapshot_sha256": snapshot["snapshot_sha256"],
        "source_pre_review_sha256": sha(preflight),
        "total_original_candidates": len(entries),
        "admitted_original_count": len(preflight["admitted_original_ids"]),
        "held_original_count": len(preflight["held_original_ids"]),
        "rejection_reasons_counted_by_claim": dict(sorted(reason_counts.items())),
        "per_claim": reported,
        "unmet_original_eligibility_requirements": list(counts["failures"]),
        "next_action": "NEW_DATED_SOURCE_RESEARCH_SNAPSHOT_ONLY",
        "limitations": "Each rejection code describes an original closed-source "
                       "screen; no new data, date, quotation or direction was "
                       "inferred. A publisher page or its date is not independently "
                       "verified truth or proof of the original release instant. "
                       "The count minima and dual-source reviews remain mandatory.",
        "publication": "NOT AUTHORIZED",
    }


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
    # Only the real OpenAI researcher uses staged source searches. Synthetic
    # fixtures retain the original one-call contract for deterministic tests.
    previous_audit=os.environ.get("IRAN_OFFLINE_REVIEW_DIR")
    os.environ["IRAN_OFFLINE_REVIEW_DIR"]=str(folder)
    actual_calls=None
    snapshot=None
    try:
        if researcher is LIVE_RESEARCHER:
            result,citations,actual_calls,snapshot=batched_research(
                researcher=researcher,folder=folder,prior=saved,
                day=day,baseline_sha=baseline_sha,started_at=stamp,
                resume=bool(os.getenv("IRAN_STAGED_RESUME")))
            day=snapshot["date"]  # Do not backdate or change the original scope.
            check(day>=history["updates"][-1]["date"],
                  "Original snapshot predates the latest historical assessment")
        else:
            result,citations=researcher(
                RESEARCH.format(date=day, prior=json.dumps(saved,ensure_ascii=False)), True)
            if researcher is llm:
                actual_calls=load_matching_search_trace(folder,result)
        check(isinstance(result,dict), "Source model returned no structured evidence")
        if researcher is llm:
            result,citations,actual_calls=resolve_source_citations(
                result,citations,actual_calls,researcher=researcher,audit_dir=folder)
    finally:
        if previous_audit is None:
            os.environ.pop("IRAN_OFFLINE_REVIEW_DIR",None)
        else:
            os.environ["IRAN_OFFLINE_REVIEW_DIR"]=previous_audit
    reconciliation = load_or_save_reconciliation(
        folder, result, citations, actual_calls)
    if reconciliation["unsupported"]:
        blocked = {
            "status": "UNSUPPORTED_CITATIONS_FLAGGED_NOT_PUBLISHABLE",
            "source_citation_reconciliation": reconciliation,
            "baseline_history_sha256": baseline_sha,
            "prospective_forecasts": "NOT TESTED",
            "affirmative_review": "NOT REACHED; PREFREEZE REJECTED",
            "critical_review": "NOT REACHED; PREFREEZE REJECTED",
            "freeze_evidence": "BLOCKED",
            "GitHub_PR_or_Pages_or_X": "NOT INVOKED",
            "limitations": "Unsupported claimed URLs remain flagged; no publication."
        }
        blocked_path = folder / "research-dry-run.json"
        if blocked_path.exists():
            check(json.loads(blocked_path.read_text()) == blocked,
                  "Existing rejected audit differs; no overwrite")
        else:
            from source_research_batches import save_new
            save_new(blocked_path, blocked)
        check((root / "data/history.json").read_bytes() == before,
              "Flagged source dry-run changed published history")
        require_supported_citations(reconciliation)

    coverage = validate_source_coverage_audit(
        result.get("coverage_audit"), citations)
    if researcher is llm:
        verify_claimed_source_links(coverage, actual_calls)
    quality, metadata = load_or_capture_quality(
        folder, result, citations, metadata_reader, now, snapshot,
        baseline_sha, strict=(researcher is llm))
    # Do not mutate or reserialize any paid research, citation, quality or
    # history checkpoint. Strict status validation occurred at the source
    # stage boundary. Only a verified OLD completed stage may restore a
    # malformed historical carry-forward from the original archive.
    effective_research, status_audit = reconcile_before_freeze(
        result, saved, folder, snapshot,
        verified_legacy_resume=(
            researcher is LIVE_RESEARCHER and
            os.getenv("IRAN_STAGED_RESUME") == "1" and
            snapshot is not None and snapshot["version"] == 1))
    archive = {"evidence": saved}
    sample, frozen_sha, cutoff = load_or_create_review_input(
        folder, result=result, citations=citations, coverage=coverage,
        quality=quality, baseline_sha=baseline_sha, snapshot=snapshot,
        archive=archive, date=day, now=now,
        status_reconciliation=status_audit,
        freeze=lambda obj, urls, old, date, stamp: freeze_evidence(
            effective_research, urls, old, date, stamp, metadata,
            provisional_source_only_v5=(
                researcher is LIVE_RESEARCHER and
                isinstance(snapshot, dict) and snapshot.get("version") >= 5)),
        claim_register_builder=(
            (lambda frozen: build_claim_register(
                folder, research=result, frozen=frozen,
                baseline_sha=baseline_sha, snapshot=snapshot))
            if researcher is LIVE_RESEARCHER else None))
    # STRICT LIVE V3: perform exact original-text, publication chronology,
    # event-date, source-quality and directional-rationale screening BEFORE
    # ANY paid affirmative/critical review. The original immutable source
    # snapshot stays untouched; only a separately hashed screened input may
    # enter review. Synthetic and pre-v3 recovery remain on their original
    # already-checkpointed contract and cannot gain retroactive certification.
    preflight = None
    if researcher is LIVE_RESEARCHER and snapshot and snapshot["version"] >= 3:
        preflight = screen_or_restore(
            folder, sample, result, baseline_sha=baseline_sha,
            snapshot=snapshot, search_calls=actual_calls)
        if preflight["status"] == "PRE_REVIEW_ADMISSIBILITY_BLOCKED_NO_PAID_REVIEWS":
            blocked = {
                "status": "PRE_REVIEW_EVIDENCE_INSUFFICIENT_NOT_PUBLISHABLE",
                "source_pre_review_status": preflight["status"],
                "source_pre_review_admissibility_sha256":
                    hashlib.sha256(json.dumps(preflight, ensure_ascii=False,
                        sort_keys=True, separators=(",", ":"),
                        allow_nan=False).encode()).hexdigest(),
                "source_pre_review_admitted_ids": preflight["admitted_original_ids"],
                "source_pre_review_held_ids": preflight["held_original_ids"],
                "source_pre_review_directional_counts":
                    preflight["directional_candidate_counts"],
                "original_source_review_input_sha256": frozen_sha,
                "original_research_snapshot_sha256": snapshot["snapshot_sha256"],
                "baseline_history_sha256": baseline_sha,
                "source_review_rounds": "NOT STARTED",
                "affirmative_review": "NOT INVOKED",
                "critical_review": "NOT INVOKED",
                "publication": "NOT AUTHORIZED",
                "mode": "RESEARCH_ONLY_NONPUBLISHING",
                "required_next_action": preflight["required_next_action"],
                "limitations": "No forecasts or publication tested. Screening is "
                    "necessary, not sufficient proof of claim or direction. "
                    "New source evidence with a new dated cutoff is required."}
            blocked_path = folder / "research-pre-review-dry-run.json"
            from source_research_batches import save_new, read_json
            if blocked_path.exists():
                check(read_json(blocked_path) == blocked,
                      "Saved pre-review failure differs; never overwrite")
            else:
                save_new(blocked_path, blocked)
            if snapshot["version"] == 6:
                gap_report = admission_deficiency_report(preflight, snapshot)
                gap_path = folder / "source-admission-deficiency.json"
                if gap_path.exists():
                    check(read_json(gap_path) == gap_report,
                          "Saved source admission deficiency changed on resume")
                else:
                    save_new(gap_path, gap_report)
            check((root/"data/history.json").read_bytes() == before,
                  "Source screening changed immutable published history")
            return blocked
        # A passing screen is not review approval. The independently selected
        # packet alone becomes the exact input for both paid review roles.
        sample = preflight["screened_packet"]
        frozen_sha = preflight["screened_review_input_sha256"]
    frozen = sample["evidence"]
    research_as_of = (snapshot["cutoff_at"] if snapshot is not None
                      else sample.get("research_as_of", cutoff.isoformat()))
    research_scope = {
        "research_as_of": research_as_of,
        "metadata_processing_cutoff": cutoff.isoformat(),
        "post_snapshot_interval": "NOT_SEARCHED",
        "notice": ("Research covers the original snapshot as-of time; "
                   "metadata capture and later reviews do not extend the "
                   "observational search window.")
    }
    canonical = json.dumps(sample, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"), allow_nan=False)
    check(hashlib.sha256(canonical.encode()).hexdigest() == frozen_sha,
          "Frozen source-review input digest mismatch")
    try:
        # In every source-review version, require AFFIRMATIVE then CRITICAL.
        # A rejection causes a strictly conservative revised packet, followed
        # by BOTH reviews again. Every version retains independent checkpoints.
        cycles = run_alternating_review_cycles(
            folder=folder, sample=sample, input_sha=frozen_sha,
            reviewer=reviewer, now=now, common=SOURCE_REVIEW_COMMON,
            original_cutoff=(snapshot["cutoff_at"] if snapshot else None),
            allow_new_after_unknown=(
                os.getenv("IRAN_ALLOW_NEW_REVIEW_AFTER_UNKNOWN") == "1"),
            enable_corrections=(researcher is LIVE_RESEARCHER),
            enforce_guards=(researcher is LIVE_RESEARCHER))
        status = cycles["status"]
        reviewers = cycles["final_reviewers"]
    finally:
        check((root/"data/history.json").read_bytes()==before,
              "Source dry-run altered the immutable published history")
    report={"status":status,"reviewers":reviewers,
            "review_rounds":cycles["review_rounds"],
            "pre_review_admissibility_sha256": (
                hashlib.sha256(json.dumps(preflight, sort_keys=True,
                    ensure_ascii=False, separators=(",", ":"),
                    allow_nan=False).encode()).hexdigest()
                if preflight else None),
            "pre_review_admitted_evidence_ids": (
                preflight["admitted_original_ids"] if preflight else None),
            "pre_review_held_evidence_ids": (
                preflight["held_original_ids"] if preflight else None),
            "terminal_evidence_gate":cycles.get("terminal_evidence_gate"),
            "final_review_input_sha256":cycles["final_review_input_sha256"],
            "original_claim_evidence_register_sha256": (
                hashlib.sha256(json.dumps(
                    sample["claim_evidence_register"], sort_keys=True,
                    ensure_ascii=False, separators=(",", ":"),
                    allow_nan=False).encode()).hexdigest()
                if "claim_evidence_register" in sample else None),
            "source_stage_snapshot_sha256": (
                snapshot["snapshot_sha256"] if snapshot else None),
            "evidence_status_reconciliation_sha256": (
                status_audit["effective_research_sha256"] if status_audit else None),
            "completed_source_categories": (
                list(CATEGORIES) if snapshot else []),
            "source_citation_reconciliation":reconciliation,
            "research_input_sha256":frozen_sha,
            "baseline_history_sha256":baseline_sha,
            "actual_cutoff":cutoff.isoformat(),
            "original_research_cutoff": (snapshot["cutoff_at"] if snapshot else None),
            "source_scope":research_scope,
            "source_coverage":coverage,
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
    if dest.exists():
        original_report = json.loads(dest.read_text(encoding="utf-8"))
        check(isinstance(original_report, dict)
              and original_report.get("baseline_history_sha256") == baseline_sha
              and original_report.get("research_input_sha256") == frozen_sha
              and original_report.get("source_stage_snapshot_sha256") ==
                  (snapshot["snapshot_sha256"] if snapshot else None),
              "Existing original diagnostic belongs to a different research snapshot")
        # Never overwrite the formerly rejected review report. The complete
        # corrected review outcome is kept under its own immutable filename.
        from source_research_batches import save_new
        final_path = folder / "research-dry-run-revised.json"
        if final_path.exists():
            check(json.loads(final_path.read_text(encoding="utf-8")) == report,
                  "Revised source diagnostic differs from saved round history")
        else:
            save_new(final_path, report)
    else:
        from source_research_batches import save_new
        save_new(dest, report)
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
    terminal = summary.get("terminal_evidence_gate")
    if terminal:
        gate = terminal.get("directional_eligibility", {})
        missing = gate.get("failures", []) if isinstance(gate, dict) else []
        print("TERMINAL CLOSED-SOURCE DEFICIENCY; NO FURTHER PAID REVIEWS: "
              + (", ".join(missing) if missing else "incomplete eligibility")
              + ". A NEW DATED SOURCE-RESEARCH SNAPSHOT IS REQUIRED.",
              flush=True)
    # A reviewer approval is necessary but never sufficient. Terminal
    # evidence gates, missing directions, insufficient source counts,
    # incomplete corrections and other invariant failures MUST produce a
    # nonzero Actions exit status even if both reviewers said approved.
    if summary["status"] != "RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE":
        raise SystemExit(1)


if __name__=="__main__":
    main()

