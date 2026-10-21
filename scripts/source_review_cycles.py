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
    flagged = set()
    for issue in issues:
        require(isinstance(issue, dict), "Malformed original reviewer issue")
        location = str(issue.get("location") or "")
        flagged.update(re.findall(r"E-\d{8}-\d{2}", location))
    dropped = []
    kept = []
    for entry in evidence:
        identifier = entry["id"]
        url = url_key(entry.get("source"))
        src = sources.get(url)
        require(src is not None, "Evidence has no original source audit")
        reasons = []
        if identifier in flagged:
            reasons.append("Named by affirmative or critical reviewer objection")
        if src.get("access_status") != "source_metadata_captured":
            reasons.append("Original source access not demonstrated")
        if src.get("classification") == "unverified":
            reasons.append("Unverified source not admissible as substantive observation")
        if claim_map is not None and (
                not isinstance(claim_map.get(identifier), dict)
                or claim_map[identifier].get("status") !=
                    "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED"):
            reasons.append("No exact passage captured from the original public article")
        if reasons:
            dropped.append({"id": identifier, "url": url, "reasons": reasons,
                            "disposition": "EXCLUDED_NOT_EVIDENCE"})
        else:
            kept.append(entry)
    revised["evidence"] = kept
    # An editorial correction may NOT evade the original substantive evidence
    # diversity requirements by declaring a small sample clean.
    publishers = {r.get("publisher") for r in kept if r.get("publisher")}
    directions = {r.get("direction") for r in kept}
    if (len(kept) < 6 or len(publishers) < 3 or
            not {"raises", "lowers", "ambiguous"}.issubset(directions) or
            sum(r.get("evidence_status") == "new" for r in kept) < 4):
        return None, {"reason": "Not enough independently qualified evidence "
                      "remains after conservative exclusions; new verified research "
                      "would be necessary; never fabricate replacements",
                      "excluded_evidence": dropped}
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
        "This corrected source-only diagnostic excludes original evidence "
        "whose claims or source access were rejected. It creates no new "
        "citations, independent corroboration, original publication times, "
        "verified observations, forecasts or permission to publish.")
    # An unchanged correction cannot be used to purchase repeated approvals.
    if sha(revised) == sha(previous):
        return None, {"reason": "No further safe evidence correction is possible"}
    return revised, {"excluded_evidence": dropped,
                     "cutoff_gap_disclosed": bool(original_cutoff)}


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
        if (source and source.get("origin") == "official_or_advocacy_claim"
                and source.get("classification") == "direct_observation"):
            issues.append({"type": "official_claim_misclassified",
                           "location": item.get("id", "unknown"),
                           "reason": "Official assertion is not itself a direct observation"})
        if claim_map is not None:
            witness = claim_map.get(item.get("id"))
            if (not isinstance(witness, dict) or
                    witness.get("url") != url_key(item.get("source")) or
                    witness.get("observation_sha256") !=
                        hashlib.sha256(item["observation"].encode()).hexdigest() or
                    witness.get("status") != "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED"):
                issues.append({"type": "claim_passage_not_demonstrated",
                               "location": item.get("id", "unknown"),
                               "reason": "Exact short original-page quotation absent "
                                         "or does not match the frozen claim"})
    for category in packet.get("coverage", []):
        if (category.get("original_outcome") == "eligible_reporting_found"
                and not category.get("retained_evidence_ids")
                and category.get("outcome") == "eligible_reporting_found"):
            issues.append({"type": "coverage_not_reconciled",
                           "location": category.get("category", "unknown"),
                           "reason": "No retained evidence in category after exclusions"})
    if (original_cutoff and packet.get("cutoff") != original_cutoff
            and not packet.get("unsearched_interval")):
        issues.append({"type": "cutoff_scope_mismatch",
                       "location": "coverage / all six research categories",
                       "reason": "Later review preparation was not part of the original search"})
    return issues


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
    original_register = sample.get("claim_evidence_register")
    if original_register is not None:
        from source_passage_audit import verify_register
        verify_register(original_register, sample["evidence"],
                        history_sha=sample.get("published_history_sha256"))
    rounds = []
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
        expected = {"round": number+1, "parent_sha256": digest,
                    "input_sha256": sha(amended), "sample": amended,
                    "correction": details,
                    "publication": "NOT AUTHORIZED"}
        if next_path.exists():
            require(read_json(next_path) == expected,
                    "Saved corrected packet differs from frozen reviewer issues")
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
    out = folder / "source-review-cycles-outcome.json"
    if out.exists():
        require(read_json(out) == outcome,
                "Prior alternating-review outcome differs from saved review record")
    else:
        save_new(out, outcome)
    return outcome
