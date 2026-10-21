"""Alternating affirmative/critical review of conservatively corrected evidence.

Never interpret the original search citations as proof. Source corrections
may *only* exclude unsupported evidence and downgrade source assertions.
All original files, both reviewers' objections and exact packet hashes survive.
A rejection or time limit is never approval and never publishes an assessment.
"""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re

from assessment_pipeline import _review_issues
from source_metadata import url_key
from source_research_batches import canonical, sha, save_new, read_json
from source_review_resume import review_with_checkpoint
from source_claim_narrowing import (
    LIMITED_STATUS, narrow_to_passage, narrowing_record,
    permitted_narrowing, validate_narrowings,
)
from source_directional_eligibility import eligibility
from source_quality_audit import validate_source_review

MAX_REVIEW_ROUNDS = 4
ADDITIONAL_CAVEAT = (
    "Editorial qualification: an original URL or publisher-provided timestamp "
    "does not establish original full-text inspection, independent verification, "
    "or the first time information became publicly available. Search snippets, "
    "metadata extraction, opinion and duplicated reports are not independent "
    "observations. Claims must be treated only to their documented access level."
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _prompt(role, packet, digest, common):
    """Exact first-round prompt retained for previous paid response recovery."""
    if packet.get("pre_review_admission_version") == 1:
        common += (
            "\nV3 PRE-REVIEW ADMISSIBILITY: Only observations provisionally "
            "screened for independent original-page passage availability, "
            "publisher-reported pre-cutoff date, event date, claim-word "
            "relevance and explicit model reasoning enter evidence. "
            "The screening is NOT semantic verification, first-publication "
            "proof or a demonstrated geopolitical direction. Evaluate each "
            "surviving claim against the actual passage and its stated "
            "direction, and reject unsupported model reasoning. "
            "Held-out entries and originals remain in the closed audit "
            "but must never be counted as directional observations. ")
    if packet.get("claim_evidence_register"):
        common += (
            "\nCLAIM-LEVEL VERIFICATION: For each retained evidence ID, examine "
            "the independently retrieved exact passage and its source-body hash. "
            "A passage match does NOT establish semantic support, original "
            "publication time, corroboration or impact direction. Reject any "
            "missing or unmatched original-body passage; scrutinize whether "
            "a matched quote actually warrants its observation. "
            "A source metadata hit is not full-text inspection. "
            "Do not infer that the interval after research_as_of was searched. ")
    if packet.get("quote_separation_version") == 2:
        common += (
            "\nSOURCE CONTEXT IS NOT DIRECTIONAL EVIDENCE: "
            "background_quotes are short, unverified textual context, "
            "not observed improvements, worsening, independent publishers "
            "or eligible new directional observations. Only the unchanged "
            "substantive items in evidence can be evaluated for a directional "
            "claim. Any incomplete minimum is a deterministic fail, and "
            "neither review can waive it. ")
    if packet.get("editorial_narrowings"):
        common += (
            "\nEDITORIAL QUOTE-ONLY CORRECTION: The original claims and "
            "every changed field are recorded in editorial_narrowings. "
            "The new observation ONLY asserts that the original page "
            "contained the specified exact quote; this does not validate "
            "event truth, causal direction or probability. Challenge "
            "semantic relevance, original source access, independence and "
            "research cutoff. A rejected narrowed quotation must be "
            "excluded, not rewritten repeatedly. Missing directional "
            "balance is a deterministic blocker, never a passing review. ")
    return (
        "ROLE: " + role.upper() + " SOURCE QUALITY REVIEW. " +
        ("Seek verifiable supporting and disconfirming context. "
         if role == "affirmative" else
         "Adversarially challenge all substantive claims and source gaps. ") +
        common + "\nIdentical input SHA-256: " + digest +
        "\nInput: " + canonical(packet))


def _reviewed_issues(roles):
    return [issue for role in ("affirmative", "critical")
            for issue in roles[role]["issues"]]


def conservative_revision(previous, issues, original_cutoff):
    """Withdraw unsupported claims; never change a surviving observation.

    Every evidence removal and source-quality downgrade is explicit in the
    amended packet. Raw research, citations, original cutoff and all reviewer
    objections remain in earlier immutable checkpoints.
    """
    require(isinstance(previous, dict) and isinstance(issues, list)
            and len(issues) > 0, "Correction requires substantive review issues")
    revised = copy.deepcopy(previous)
    evidence = revised.get("evidence")
    quality = revised.get("source_quality_audit")
    require(isinstance(evidence, list) and isinstance(quality, dict)
            and isinstance(quality.get("sources"), list),
            "Closed review input is malformed")
    sources = {r["url"]: r for r in quality["sources"]}
    register = previous.get("claim_evidence_register")
    claim_map = ({r["evidence_id"]: r for r in register["claims"]}
                 if isinstance(register, dict) else None)
    issues_by_id = {}
    for issue in issues:
        require(isinstance(issue, dict)
                and all(isinstance(issue.get(key), str) and issue[key].strip()
                        for key in ("type", "location", "reason")),
                "Malformed original reviewer issue")
        for ident in set(re.findall(r"E-\d{8}-\d{2}", issue["location"])):
            issues_by_id.setdefault(ident, []).append(issue)
    dropped, kept = [], []
    narrowed = copy.deepcopy(previous.get("editorial_narrowings", []))
    narrowed_ids = {entry["evidence_id"] for entry in narrowed}
    background = []
    for context in previous.get("background_quotes", []):
        if context["id"] in issues_by_id:
            dropped.append({
                "id": context["id"], "url": url_key(context["source"]),
                "reasons": ["Both reviews must reconsider source context; "
                            "a renewed objection excludes previously narrowed "
                            "quoted background"],
                "disposition": "EXCLUDED_QUOTATION_FROM_BACKGROUND"})
        else:
            background.append(copy.deepcopy(context))
    for entry in evidence:
        identifier = entry["id"]
        url = url_key(entry.get("source"))
        src = sources.get(url)
        require(src is not None, "Evidence has no original source audit")
        witness = claim_map.get(identifier) if claim_map is not None else None
        relevant_issues = issues_by_id.get(identifier, [])
        reasons = []
        if src.get("access_status") != "source_metadata_captured":
            reasons.append("Original source metadata could not be retrieved")
        if src.get("classification") == "unverified":
            reasons.append("Unverified original source cannot support evidence")
        if claim_map is not None and (
                not isinstance(witness, dict)
                or witness.get("status") !=
                   "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED"):
            reasons.append("Original page lacks a matched short passage")
        if identifier in narrowed_ids and relevant_issues:
            reasons.append("Independent reviewer rejected previously narrowed passage")
        if reasons:
            dropped.append({"id": identifier, "url": url, "reasons": reasons,
                            "disposition": "EXCLUDED_NOT_EVIDENCE"})
        elif relevant_issues and permitted_narrowing(entry, witness, relevant_issues):
            changed = narrow_to_passage(entry, witness)
            # Quotations have ZERO directional admissibility. They are not
            # part of the retained observations used by any forecast,
            # publisher-diversity count or directional balance test.
            background.append(changed)
            narrowed.append(narrowing_record(
                entry, changed, witness, relevant_issues))
        elif relevant_issues:
            # A named objection with no defensible narrowing must not survive
            # as an apparently unchallenged source observation.
            dropped.append({
                "id": identifier, "url": url,
                "reasons": ["Substantive source objection not resolved by "
                            "an attributable original-page passage"] +
                           [x["type"] for x in relevant_issues],
                "disposition": "EXCLUDED_NOT_EVIDENCE"})
        else:
            kept.append(entry)
    revised["evidence"] = kept
    if claim_map is not None:
        revised["editorial_narrowings"] = narrowed
        revised["background_quotes"] = background
        revised["quote_separation_version"] = 2
    # Conservatively corrected text is not directionally informative.
    # Every minimum must be recomputed from the UNALTERED directional
    # observations, never from background quotes or their old categories.
    eligibility_report = eligibility(revised)
    guard_failures = eligibility_report["failures"]
    # Unscored source diagnostics may assess a provisional quote-only revision
    # even when it fails diversity checks; that version can NEVER be approved
    # or used for forecasts. Legacy source-only fixtures keep the old block.
    if guard_failures and claim_map is None:
        return None, {"reason": "Not enough independently qualified evidence "
                      "remains after conservative exclusions; new verified research "
                      "would be necessary; never fabricate replacements",
                      "guard_failures": guard_failures,
                      "excluded_evidence": dropped}
    if claim_map is not None:
        revised["source_diversity_guard"] = {
            "status": ("BLOCKED_NOT_PUBLISHABLE" if guard_failures
                       else "MINIMUM_COUNTS_PRESENT_UNVERIFIED"),
            "failures": guard_failures,
            "eligibility": eligibility_report,
            "scope": "SOURCE_DIAGNOSTIC_ONLY_NO_SCORED_FORECASTS"}
    effective_sources = {url_key(e["source"]) for e in kept}
    for src in quality["sources"]:
        # Retain the TRUE original metadata status across all later rounds.
        # Repeated correction cannot overwrite this provenance with an
        # editorial label and falsely register a changed evidence version.
        if "editorial_original_metadata_status" not in src:
            src["editorial_original_metadata_status"] = src["metadata_status"]
        src["metadata_status"] = (
            "Publisher/site metadata only; original first-publication clock "
            "is not independently authenticated")
        if claim_map is not None:
            if "editorial_original_assessment" not in src:
                src["editorial_original_assessment"] = src.get("assessment")
            src["assessment"] = (
                "A public source URL was returned in the original web search. "
                "Original-page passage access and its observed limits appear "
                "in the separately retained claim evidence register; factual "
                "claims, first-publication time and corroboration remain "
                "independently unestablished.")
        if ADDITIONAL_CAVEAT not in src.get("limitations", ""):
            src["limitations"] = src.get("limitations", "") + " " + ADDITIONAL_CAVEAT
        # Metadata availability is not a proxy for full article availability.
        src["editorial_full_text_access_status"] = (
            "short_original_passage_observed_not_full_text_or_semantic_proof"
            if claim_map is not None and any(
                row.get("url") == src["url"] and
                row.get("status") == "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED"
                for row in claim_map.values()) else
            "not_demonstrated_by_saved_metadata_or_search_snippet")
        # Official statements report what the institution asserts; they are
        # not direct measurements merely because the original page is reachable.
        if (src.get("origin") == "official_or_advocacy_claim"
                and src.get("classification") == "direct_observation"):
            src["classification"] = "attributed_claim"
            src["flags"] = sorted(set(src.get("flags", []) + [
                "official_statement_downgraded_to_attributed_claim"]))
        if src["url"] not in effective_sources:
            src["role"] = "coverage_context_only"
            src["new_evidence_indices"] = []
            if src["classification"] == "direct_observation":
                src["classification"] = "unverified"
                src["origin"] = "unknown"
        if src.get("access_status") != "source_metadata_captured":
            src["classification"] = "unverified"
            src["origin"] = "unknown"
        src["flags"] = sorted(set(src.get("flags", []) + [
            "editorially_qualified_without_new_source_inspection"]))
        src["new_evidence_indices"] = [
            i for i, e in enumerate(kept) if url_key(e["source"]) == src["url"]]
        src["role"] = (
            "new_evidence" if src["new_evidence_indices"]
            else "coverage_context_only")
    quality["evidence_source_count"] = sum(
        r["role"] == "new_evidence" for r in quality["sources"])
    quality["context_only_source_count"] = sum(
        r["role"] == "coverage_context_only" for r in quality["sources"])
    for category in revised.get("coverage", []):
        if ADDITIONAL_CAVEAT not in category.get("limitations", ""):
            category["limitations"] = (
                str(category.get("limitations", "")) + " " + ADDITIONAL_CAVEAT)
        # Original research links remain preserved for audit, but rejected
        # claims must never leave a category described as eligible evidence.
        prior_outcome = category.get("original_outcome", category.get("outcome"))
        if "original_outcome" not in category:
            category["original_outcome"] = prior_outcome
        group = category.get("category")
        admitted = [item["id"] for item in kept if
                    (url_key(item.get("source")) in
                     {url_key(u) for u in category.get("original_urls", [])}
                     or group in sources[url_key(item["source"])].get(
                         "coverage_categories", []))]
        category["retained_evidence_ids"] = sorted(admitted)
        if not admitted and prior_outcome == "eligible_reporting_found":
            category["outcome"] = "inaccessible_or_incomplete"
            qualifier = (" Original links retained for audit only; no "
                         "qualified new evidence survives the exclusions.")
            if qualifier not in category["limitations"]:
                category["limitations"] += qualifier
    initial_cutoff = revised.get("review_prepared_at", revised["cutoff"])
    if original_cutoff:
        original_time = dt.datetime.fromisoformat(original_cutoff)
        review_time = dt.datetime.fromisoformat(initial_cutoff)
        require(original_time.tzinfo and review_time.tzinfo and
                original_time <= review_time,
                "Original research cutoff cannot exceed review preparation")
        revised["cutoff"] = original_cutoff
        revised["review_prepared_at"] = initial_cutoff
        revised["unsearched_interval"] = {
            "start": original_cutoff,
            "end": initial_cutoff,
            "status": "NOT_SEARCHED_OR_CLAIMED_AS_COVERED"}
    revised["excluded_evidence"] = sorted(
        (previous.get("excluded_evidence", []) + dropped),
        key=lambda x: x["id"])
    revised["editorial_provenance"] = (
        "Verbatim quotations appear solely in background_quotes, not in "
        "directional evidence. The original cited claims are either "
        "preserved unchanged or excluded; sources are never manufactured. "
        "Quoted context contributes to no measured stability direction, "
        "publisher minimum, forecast, or publication approval. Original "
        "first-publication times and source credibility remain unverified.")
    if claim_map is not None:
        validate_narrowings(revised)
    # An unchanged correction cannot be used to purchase repeated approvals.
    if sha(revised) == sha(previous):
        return None, {"reason": "No further safe evidence correction is possible"}
    return revised, {
        "excluded_evidence": dropped,
        "narrowed_evidence_ids": [r["evidence_id"] for r in narrowed],
        "background_quote_ids": [r["id"] for r in background],
        "directional_evidence_ids": eligibility_report["directional_evidence_ids"],
        "source_diversity_failures": guard_failures,
        "cutoff_gap_disclosed": bool(original_cutoff)}


def validate_archived_conservative_revision(previous, revised, original_cutoff):
    """Replay a pre-register rejected review packet without rewriting history.

    This compatibility path is ONLY for an already-saved amendment, never a
    reason to create fresh evidence or bypass review. Rejected historical
    packets are immutable, and new audits must use current claim controls.
    """
    require(isinstance(previous, dict) and isinstance(revised, dict)
            and not previous.get("claim_evidence_register")
            and not revised.get("claim_evidence_register"),
            "Historical replay cannot acquire fabricated claim witnesses")
    parent_evidence = {r["id"]: r for r in previous["evidence"]}
    candidate_evidence = revised.get("evidence")
    require(isinstance(candidate_evidence, list)
            and len({r["id"] for r in candidate_evidence}) ==
                len(candidate_evidence)
            and all(parent_evidence.get(r["id"]) == r
                    for r in candidate_evidence),
            "Historical amendment changed or invented evidence observations")
    old_sources = {
        row["url"]: row for row in previous["source_quality_audit"]["sources"]}
    new_sources = revised["source_quality_audit"]["sources"]
    require(len(old_sources) == len(new_sources)
            and {r["url"] for r in new_sources} == set(old_sources),
            "Historical amendment added or dropped original source records")
    allowed = {
        "direct_observation": {
            "direct_observation", "attributed_claim", "unverified",
            "background_only"},
        "attributed_claim": {
            "attributed_claim", "unverified", "background_only"},
        "analysis": {"analysis", "unverified", "background_only"},
        "unverified": {"unverified", "background_only"},
        "background_only": {"background_only"}
    }
    for row in new_sources:
        original = old_sources[row["url"]]
        require(row.get("classification") in
                allowed.get(original.get("classification"), set()),
                "Historical amendment upgraded source factual status")
        for field in ("source_publication_time", "access_status",
                      "source_retrieval_status"):
            require(row.get(field) == original.get(field),
                    "Historical amendment fabricated source access or dates")
        require(set(row.get("corroborating_urls", []))
                <= set(original.get("corroborating_urls", [])),
                "Historical amendment invented source corroboration")
    old_coverage = {
        r["category"]: r for r in previous.get("coverage", [])}
    new_coverage = {
        r["category"]: r for r in revised.get("coverage", [])}
    require(set(old_coverage) == set(new_coverage),
            "Historical amendment invented new source categories")
    for name, row in new_coverage.items():
        old = old_coverage[name]
        require(row.get("original_urls") == old.get("original_urls"),
                "Historical amendment added or changed original source URLs")
        if old.get("outcome") in (
                "searched_no_eligible_evidence", "inaccessible_or_incomplete"):
            require(row.get("outcome") in (
                    old.get("outcome"), "inaccessible_or_incomplete"),
                    "Historical amendment upgraded source coverage")
    require(revised.get("published_history_sha256") ==
            previous.get("published_history_sha256"),
            "Historical review packet changed published history")
    require(revised.get("research_as_of") ==
            previous.get("research_as_of"),
            "Historical review packet changed original source-search as-of")
    require(revised.get("cutoff") in (
            previous.get("cutoff"), original_cutoff),
            "Historical packet changed the research cutoff")
    removed = set(parent_evidence) - {r["id"] for r in candidate_evidence}
    exclusions = revised.get("excluded_evidence", [])
    require(isinstance(exclusions, list) and removed <= {
        r.get("id") for r in exclusions if isinstance(r, dict)},
        "Historical exclusions do not explain removed evidence")
    return True


def deterministic_review_issues(packet, original_cutoff):
    """Independent fail-closed controls cannot be overridden by model approval."""
    issues = []
    register = packet.get("claim_evidence_register")
    claim_map = None
    if register is not None:
        require(isinstance(register, dict) and
                isinstance(register.get("claims"), list),
                "Malformed source-passage register")
        claim_map = {item["evidence_id"]: item for item in register["claims"]}
        require(len(claim_map) == len(register["claims"]),
                "Duplicate claim-passage evidence identifier")
    if claim_map is not None:
        validate_narrowings(packet)
    narrowed_ids = {row["evidence_id"] for row in
                    packet.get("editorial_narrowings", [])}
    source_map = {entry["url"]: entry
                  for entry in packet["source_quality_audit"]["sources"]}
    for item in packet["evidence"]:
        source = source_map.get(url_key(item.get("source")))
        if not source or source.get("access_status") != "source_metadata_captured":
            issues.append({"type": "uninspected_original",
                           "location": item.get("id", "unknown"),
                           "reason": "Source inspection not demonstrated in frozen metadata"})
        elif source.get("classification") == "unverified":
            issues.append({"type": "unverified_evidence",
                           "location": item.get("id", "unknown"),
                           "reason": "Unverified source cannot support a scored directional claim"})
        if (claim_map is not None and source
                and source.get("origin") == "official_or_advocacy_claim"
                and source.get("classification") == "direct_observation"):
            issues.append({"type": "official_claim_misclassified",
                           "location": item.get("id", "unknown"),
                           "reason": "Official assertion is not itself a direct observation"})
        if claim_map is not None:
            witness = claim_map.get(item.get("id"))
            if (not isinstance(witness, dict) or
                    witness.get("url") != url_key(item.get("source")) or
                    (item.get("id") not in narrowed_ids and
                     witness.get("observation_sha256") !=
                        hashlib.sha256(item["observation"].encode()).hexdigest()) or
                    witness.get("status") != "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED"):
                issues.append({"type": "claim_passage_not_demonstrated",
                               "location": item.get("id", "unknown"),
                               "reason": "Exact short original-page quotation absent "
                                         "or does not match the frozen claim"})
    for category in (packet.get("coverage", []) if claim_map is not None else []):
        if (category.get("original_outcome") == "eligible_reporting_found"
                and not category.get("retained_evidence_ids")
                and category.get("outcome") == "eligible_reporting_found"):
            issues.append({"type": "coverage_not_reconciled",
                           "location": category.get("category", "unknown"),
                           "reason": "No retained evidence in category after exclusions"})
    if claim_map is not None and packet.get("source_diversity_guard"):
        guard = packet["source_diversity_guard"]
        require(isinstance(guard, dict)
                and isinstance(guard.get("failures"), list),
                "Malformed source evidence-diversity gate")
        if packet.get("quote_separation_version") == 2:
            counts = eligibility(packet)
            require(guard.get("eligibility") == counts
                    and guard.get("failures") == counts["failures"]
                    and guard.get("status") == (
                        "BLOCKED_NOT_PUBLISHABLE" if counts["failures"]
                        else "MINIMUM_COUNTS_PRESENT_UNVERIFIED"),
                    "Saved evidence-diversity safeguard contradicts revised evidence")
            failures = counts["failures"]
        else:
            # Historical packets from before independent background storage
            # stay immutable. Their old reviewers are not silently rewritten.
            evidence = packet["evidence"]
            publishers = {entry.get("publisher") for entry in evidence
                          if entry.get("publisher")}
            directions = {entry.get("direction") for entry in evidence}
            failures = []
            if len(evidence) < 6:
                failures.append("fewer_than_six_source_observations")
            if len(publishers) < 3:
                failures.append("fewer_than_three_distinct_publishers")
            if not {"raises", "lowers", "ambiguous"}.issubset(directions):
                failures.append("missing_required_directional_balance")
            if sum(e.get("evidence_status") == "new" for e in evidence) < 4:
                failures.append("fewer_than_four_new_observations")
            require(guard["failures"] == failures,
                    "Saved evidence-diversity safeguard contradicts revised evidence")
        if failures:
            issues.append({
                "type": "insufficient_qualified_evidence_diversity",
                "location": "corrected evidence set / source_diversity_guard",
                "reason": "Background quotations cannot substitute for "
                          "independent directional observations, publisher "
                          "diversity or four new observations: "
                          + ", ".join(failures)})
    if original_cutoff and packet.get("cutoff") != original_cutoff:
        explicit_asof = (
            packet.get("research_as_of") == original_cutoff and
            packet.get("post_asof_window") == "NOT_SEARCHED")
        archived_interval = (
            isinstance(packet.get("unsearched_interval"), dict) and
            packet["unsearched_interval"].get("start") == original_cutoff and
            packet["unsearched_interval"].get("status") ==
                "NOT_SEARCHED_OR_CLAIMED_AS_COVERED")
        if not (explicit_asof or archived_interval):
            issues.append({"type": "cutoff_scope_mismatch",
                           "location": "coverage / all six research categories",
                           "reason": "Later review preparation was not part of "
                                     "the original source-research search window"})
    return issues


def save_terminal_evidence_gate(folder, round_number, parent_sha,
                                corrected, correction):
    """Checkpoint a correction that can NEVER satisfy a closed-snapshot gate.

    No corrected review-input checkpoint and NO new paid review is created.
    The full proposed correction is preserved separately from approved
    evidence and the original reviewer round is immutable.
    """
    counts = eligibility(corrected)
    require(counts["failures"] and
            counts["irreversible_under_closed_source_corrections"],
            "Terminal evidence gate requires an actual irreversible deficiency")
    guard = corrected.get("source_diversity_guard")
    require(isinstance(guard, dict)
            and guard.get("status") == "BLOCKED_NOT_PUBLISHABLE"
            and guard.get("eligibility") == counts,
            "Source diversity gate does not match proposed corrected evidence")
    record = {
        "version": 1,
        "status": "IRREVERSIBLE_EVIDENCE_DEFICIENCY_NO_MORE_PAID_REVIEWS",
        "completed_review_round": round_number,
        "blocked_next_review_round": round_number+1,
        "parent_review_input_sha256": parent_sha,
        "proposed_correction_sha256": sha(corrected),
        "proposed_correction": corrected,
        "correction_actions": correction,
        "directional_eligibility": counts,
        "research_needed": "NEW_DATED_SIX_CATEGORY_SOURCE_SNAPSHOT",
        "reviewer_requests_after_block": "NOT PERMITTED",
        "publication": "NOT AUTHORIZED",
    }
    path = Path(folder) / f"source-review-round-{round_number:02d}-terminal-gate.json"
    if path.exists():
        require(read_json(path) == record,
                "Saved terminal source gate differs from frozen evidence")
    else:
        save_new(path, record)
    return {
        "status": record["status"],
        "completed_review_round": round_number,
        "blocked_next_review_round": round_number+1,
        "parent_review_input_sha256": parent_sha,
        "proposed_correction_sha256": record["proposed_correction_sha256"],
        "directional_eligibility": counts,
        "new_research_required": True,
        "publication": "NOT AUTHORIZED",
    }


def run_alternating_review_cycles(*, folder, sample, input_sha, reviewer,
                                  now, common, original_cutoff=None,
                                  allow_new_after_unknown=False,
                                  enable_corrections=True,
                                  enforce_guards=True,
                                  max_rounds=MAX_REVIEW_ROUNDS):
    """Both reviews of every immutable version, alternating until clean/capped.

    The exact first-round prompt/checkpoint is backward-compatible with
    diagnostic #39629051453. Corrections only reduce unsupported claims.
    The saved source input is frozen; every revision is a separate artifact.
    """
    require(type(max_rounds) is int and 1 <= max_rounds <= 6,
            "Invalid review-cycle bound")
    folder = Path(folder)
    initial_digest = sha(sample)
    require(initial_digest == input_sha, "Initial closed review input changed")
    packet = copy.deepcopy(sample)
    # Old completed quote-only review packets cannot be retroactively
    # recertified under today's stronger directional standard. Fail BEFORE
    # requesting another review and retain all of their original artifacts.
    already_staged = folder / "source-review-round-02-input.json"
    if sample.get("claim_evidence_register") and already_staged.exists():
        old = read_json(already_staged)
        require(isinstance(old, dict) and
                isinstance(old.get("sample"), dict),
                "Malformed previously staged source review")
        require(old["sample"].get("quote_separation_version") == 2,
                "Prior quote-only review packet is historical and already "
                "incompatible with directional eligibility. No new reviewer "
                "request is permitted; start a new dated research snapshot.")
    original_register = sample.get("claim_evidence_register")
    screened = sample.get("pre_review_admission_version") == 1
    original_evidence_for_witnesses = (
        sample.get("pre_review_original_evidence") if screened else
        sample.get("evidence"))
    if original_register is not None:
        from source_passage_audit import verify_register
        verify_register(original_register, original_evidence_for_witnesses,
                        history_sha=sample.get("published_history_sha256"),
                        original_cutoff=sample.get("research_as_of"))
    if screened:
        require(isinstance(sample.get("pre_review_claim_decisions"), list)
                and isinstance(sample.get("pre_review_held_original_evidence"), list),
                "Screened review lacks an immutable original claim audit")
        allowed_ids = [
            x["id"] for x in sample["pre_review_claim_decisions"]
            if x["decision"] ==
               "PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW"]
        held_ids = [
            x["id"] for x in sample["pre_review_claim_decisions"]
            if x["decision"] == "HELD_OUT_BEFORE_PAID_REVIEW"]
        require(allowed_ids == [e["id"] for e in sample["evidence"]]
                and held_ids == [e["id"] for e in
                                  sample["pre_review_held_original_evidence"]],
                "Screened review changed admission decisions or directional entries")
        archived_screen = read_json(folder / "source-pre-review-admissibility.json")
        require(archived_screen["screened_review_input_sha256"] == initial_digest
                and archived_screen["screened_packet"] == sample
                and archived_screen["source_review_requests"] ==
                    "PERMITTED_AFTER_SCREEN",
                "Pre-review evidence was not admitted by original saved audit")
    rounds = []
    terminal_gate = None
    known_unknown = set()
    for number in range(1, max_rounds + 1):
        if number > 1:
            item = read_json(folder / f"source-review-round-{number:02d}-input.json")
            require(item["input_sha256"] == sha(item["sample"]) and
                    item["parent_sha256"] == rounds[-1]["input_sha256"],
                    "Saved revised source packet has invalid parent or hash")
            packet = item["sample"]
        if original_register is not None:
            require(packet.get("claim_evidence_register") == original_register,
                    "Revised evidence cannot alter original claim witness register")
        if screened:
            require(packet.get("pre_review_original_evidence") ==
                        original_evidence_for_witnesses
                    and packet.get("pre_review_claim_decisions") ==
                        sample["pre_review_claim_decisions"],
                    "Revised packet altered original admission and source provenance")
        digest = sha(packet)
        result = {}
        for role in ("affirmative", "critical"):
            prompt = _prompt(role, packet, digest, common)
            response = review_with_checkpoint(
                folder, role=role, prompt=prompt, input_sha=digest,
                quality=packet["source_quality_audit"],
                reviewer=reviewer, now=now,
                round_number=number,
                allow_new_after_unknown=allow_new_after_unknown,
                superseded_unknown_requests=known_unknown)
            known_unknown.update(response.pop("superseded_unknown_requests"))
            result[role] = response
        invariant_issues = (deterministic_review_issues(packet, original_cutoff)
                            if enforce_guards else [])
        clean = (all(r["approved"] and not r["issues"] for r in result.values())
                 and not invariant_issues)
        record = {"round": number, "input_sha256": digest,
                  "deterministic_issues": invariant_issues,
                  "affirmative": result["affirmative"],
                  "critical": result["critical"], "both_clean": clean,
                  "status": "DUAL_REVIEW_CLEAN_NOT_PUBLISHABLE" if clean
                            else "REJECTED_NOT_PUBLISHABLE",
                  "publication": "NOT AUTHORIZED"}
        path = folder / f"source-review-round-{number:02d}.json"
        if path.exists():
            require(read_json(path) == record,
                    "Saved review round differs from original reviewer verdicts")
        else:
            save_new(path, record)
        rounds.append(record)
        if clean:
            status = "RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE"
            break
        if not enable_corrections or number == max_rounds:
            status = "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE"
            break
        amended, details = conservative_revision(
            packet, _reviewed_issues(result) + invariant_issues, original_cutoff)
        if amended is None:
            status = "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE"
            record["correction_blocker"] = details
            # Persist the reason separately; never overwrite signed old rounds.
            reason_path = folder / f"source-review-round-{number:02d}-blocked.json"
            if reason_path.exists():
                require(read_json(reason_path) == details,
                        "Saved correction failure reason changed")
            else:
                save_new(reason_path, details)
            break
        next_path = folder / f"source-review-round-{number+1:02d}-input.json"
        if (original_register is not None and enforce_guards
                and amended.get("quote_separation_version") == 2):
            allowed = eligibility(amended)
            if allowed["failures"]:
                require(not next_path.exists(),
                        "An unreviewable corrected packet was already staged; "
                        "do not rewrite or repeat historical paid reviews")
                terminal_gate = save_terminal_evidence_gate(
                    folder, number, digest, amended, details)
                status = "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE"
                break
        expected = {"round": number+1, "parent_sha256": digest,
                    "input_sha256": sha(amended), "sample": amended,
                    "correction": details,
                    "publication": "NOT AUTHORIZED"}
        if next_path.exists():
            archived = read_json(next_path)
            if archived != expected:
                require(original_register is None
                        and archived.get("round") == number+1
                        and archived.get("parent_sha256") == digest
                        and archived.get("input_sha256") ==
                            sha(archived.get("sample"))
                        and archived.get("publication") == "NOT AUTHORIZED",
                        "Saved corrected packet differs from frozen reviewer issues")
                validate_archived_conservative_revision(
                    packet, archived["sample"], original_cutoff)
                # Only an existing, genuinely preserved legacy input may use
                # this compatibility check; no new review packet is generated.
        else:
            save_new(next_path, expected)
    else:
        status = "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE"
    outcome = {"status": status,
               "rounds": len(rounds),
               "review_rounds": [{k: r[k] for k in
                                  ("round", "input_sha256", "both_clean", "status")}
                                 for r in rounds],
               "final_review_input_sha256": rounds[-1]["input_sha256"],
               "final_reviewers": {
                   role: rounds[-1][role]
                   for role in ("affirmative", "critical")},
               "original_review_input_sha256": input_sha,
               "original_research_cutoff": original_cutoff,
               "publication": "NOT AUTHORIZED",
               "limitations": "All rejected review versions are preserved. "
                   "Only conservative exclusions and qualifications, not new "
                   "research verification, were permitted."}
    if terminal_gate is not None:
        outcome["terminal_evidence_gate"] = terminal_gate
        outcome["limitations"] += (
            " A monotone source-diversity failure blocked additional paid "
            "affirmative/critical review before the next round. "
            "New dated source research is required.")
    out = folder / "source-review-cycles-outcome.json"
    if out.exists():
        historical = read_json(out)
        if historical != outcome:
            # A previously rejected diagnostic may have stopped at the old
            # whole-record-exclusion rule. Its failure report and rejected
            # source versions MUST remain unchanged; only the original,
            # fully matching rejected rounds may be followed by this revision.
            require(historical.get("status") ==
                        "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE"
                    and historical.get("original_review_input_sha256") == input_sha
                    and historical.get("original_research_cutoff") == original_cutoff
                    and len(historical.get("review_rounds", [])) <= len(rounds)
                    and historical["review_rounds"] ==
                        outcome["review_rounds"][:len(historical["review_rounds"])]
                    and (len(historical["review_rounds"]) < len(rounds)
                         or terminal_gate is not None)
                    and (folder / "source-review-round-01-blocked.json").exists(),
                    "Prior alternating-review outcome differs from saved review record")
            # The compatibility file is an ADDITION, never a replacement.
            outcome["original_rejected_outcome_sha256"] = sha(historical)
            outcome["original_rejected_blocker_sha256"] = sha(
                read_json(folder / "source-review-round-01-blocked.json"))
            new_out = folder / "source-review-cycles-outcome-revised.json"
            if new_out.exists():
                require(read_json(new_out) == outcome,
                        "Corrected review outcome differs from prior immutable revisions")
            else:
                save_new(new_out, outcome)
    else:
        save_new(out, outcome)
    return outcome
