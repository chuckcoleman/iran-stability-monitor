"""Deterministic admission screen *before* any paid source-review requests.

This is a necessary-not-sufficient gate. Exact retrieved text, date assertions
and word overlap are not independent semantic verification, first publication
proof, independence of sources, or proof of causal direction. Both affirmative
and critical reviewers remain mandatory for every provisionally admitted item.
Unscreened claims are preserved only in the immutable original audit, never
treated as directionally admissible in the review input.
"""
import copy
import datetime as dt
import hashlib
from pathlib import Path
import re

from source_directional_eligibility import eligibility
from source_metadata import url_key
from source_passage_audit import verify_register
from source_research_batches import read_json, save_new, sha

GATE_VERSION = 1
ADMISSION = "PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW"
REJECT = "HELD_OUT_BEFORE_PAID_REVIEW"
ACCEPTED_EFFECTS = frozenset((
    "observed_policy_action", "reported_event", "measured_data"))
BACKGROUND_EFFECTS = frozenset((
    "attributed_claim", "analysis_or_forecast", "background_context"))
ALL_EFFECTS = ACCEPTED_EFFECTS | BACKGROUND_EFFECTS
STOP = frozenset((
    "about", "after", "before", "because", "being", "between", "could",
    "their", "there", "these", "those", "reported", "reporting",
    "reports", "source", "claims", "claimed", "other", "through",
    "would", "should", "which", "where", "while", "against", "within",
    "during", "overall", "according", "original", "iranian", "iran",
    "towards", "stability", "increased", "decreased", "under",
))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _words(text):
    require(isinstance(text, str), "Source-claim text is not a string")
    return set(re.findall(r"[^\\W\\d_]{4,}", text.casefold(), flags=re.UNICODE)) - STOP


def _event_date_status(entry, cutoff):
    try:
        observed = dt.date.fromisoformat(entry["event_date"])
    except (KeyError, TypeError, ValueError):
        return "MALFORMED_EVENT_DATE"
    if observed > cutoff.date():
        return "EVENT_AFTER_RESEARCH_CUTOFF"
    if observed < cutoff.date() - dt.timedelta(days=90):
        # A dated historic incident may be valuable context, but is not a
        # fresh directional observation without updated independent evidence.
        return "OLD_EVENT_CONTEXT_ONLY"
    return "EVENT_DATE_WITHIN_RESEARCH_WINDOW"


def _publisher_time_status(source, cutoff):
    """Only the original page's own publication metadata is admissible.

    A publisher date before the research day makes the observation worth
    reviewing but NEVER independently certifies the first release time.
    Same-day dates without an offset-aware time are too imprecise.
    """
    time = source.get("source_publication_time")
    dates = source.get("publication_dates_from_page", [])
    if not isinstance(dates, list):
        return "INVALID_PUBLISHER_DATE_METADATA"
    try:
        times = [dt.datetime.fromisoformat(time.replace("Z", "+00:00"))] if time else []
        days = [dt.date.fromisoformat(x) for x in dates]
    except (ValueError, TypeError, AttributeError):
        return "INVALID_PUBLISHER_DATE_METADATA"
    if any(t.utcoffset() is None for t in times):
        return "NAIVE_PUBLISHER_RELEASE_TIME"
    if any(t > cutoff for t in times):
        return "PUBLISHER_RELEASE_AFTER_RESEARCH_CUTOFF"
    if any(x > cutoff.date() for x in days):
        return "PUBLISHER_DATE_AFTER_RESEARCH_CUTOFF"
    if times:
        return "PUBLISHER_REPORTED_PRE_CUTOFF_TIME_NOT_FIRST_PUBLICATION_PROOF"
    if days and max(days) < cutoff.date():
        return "PUBLISHER_PRIOR_DATE_NOT_FIRST_PUBLICATION_PROOF"
    if days:
        return "SAME_DAY_PUBLISHER_DATE_NO_PRE_CUTOFF_TIME"
    return "NO_ORIGINAL_PUBLISHER_DATE"


def _corresponding_original(original, frozen):
    matches = [
        e for e in original.get("evidence", [])
        if e.get("evidence_status", "new") == frozen.get("evidence_status")
        and url_key(e.get("source")) == url_key(frozen.get("source"))
        and e.get("event_date") == frozen.get("event_date")
        and e.get("category") == frozen.get("category")
    ]
    return matches[0] if len(matches) == 1 else None


def screen_original_packet(packet, research, *, baseline_sha, snapshot):
    """Create an immutable source-by-source, claim-by-claim pre-review screen."""
    require(isinstance(packet, dict) and isinstance(snapshot, dict)
            and snapshot.get("version") == 3,
            "Pre-review admission requires new v3 research snapshot")
    require(packet.get("published_history_sha256") == baseline_sha
            and packet.get("research_as_of") == snapshot.get("cutoff_at"),
            "Admissibility cannot move the frozen search cutoff or history")
    cutoff = dt.datetime.fromisoformat(snapshot["cutoff_at"])
    require(cutoff.utcoffset() is not None, "Missing timezone-aware search cutoff")
    source_rows = packet["source_quality_audit"]["sources"]
    sources = {r["url"]: r for r in source_rows}
    require(len(sources) == len(source_rows),
            "Duplicate original source-quality URL")
    frozen = packet.get("evidence")
    require(isinstance(frozen, list), "No frozen evidence for source screening")
    register = packet.get("claim_evidence_register")
    require(isinstance(register, dict), "No original-page passage register")
    verify_register(register, frozen, history_sha=baseline_sha,
                    snapshot_sha=snapshot["snapshot_sha256"],
                    original_cutoff=snapshot["cutoff_at"])
    claims = {x["evidence_id"]: x for x in register["claims"]}
    require(len(claims) == len(register["claims"]),
            "Duplicate source-passage witness ID")
    decisions, admitted, held = [], [], []
    for entry in frozen:
        identifier = entry["id"]
        witness = claims[identifier]
        key = url_key(entry.get("source"))
        source = sources.get(key)
        original = _corresponding_original(research, entry)
        reasons = []
        if entry.get("evidence_status") != "new":
            reasons.append("HISTORICAL_CARRY_NOT_NEW_DIRECTIONAL_EVIDENCE")
        if not source:
            reasons.append("SOURCE_NOT_IN_QUALITY_AUDIT")
            source = {}
        if (source.get("access_status") != "source_metadata_captured" or
                source.get("source_retrieval_status") != "retrieved"):
            reasons.append("ORIGINAL_SOURCE_METADATA_UNAVAILABLE")
        if (source.get("classification") not in
                ("direct_observation", "attributed_claim") or
                source.get("origin") in
                ("analytical_secondary", "syndicated_reprint", "unknown")):
            reasons.append("ANALYSIS_SYNDICATION_OR_UNVERIFIED_CLASS")
        if witness.get("status") != "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED":
            reasons.append("NO_EXACT_RETRIEVED_ORIGINAL_BODY_PASSAGE")
        elif (witness.get("retrieved_url") != key or
              witness.get("content_type") not in
              ("text/html", "application/xhtml+xml") or
              witness.get("semantic_support") !=
              "NOT_INDEPENDENTLY_ESTABLISHED"):
            reasons.append("INVALID_ORIGINAL_PASSAGE_PROVENANCE")
        event_status = _event_date_status(entry, cutoff)
        if event_status != "EVENT_DATE_WITHIN_RESEARCH_WINDOW":
            reasons.append(event_status)
        pub_status = _publisher_time_status(source, cutoff)
        if pub_status not in (
                "PUBLISHER_REPORTED_PRE_CUTOFF_TIME_NOT_FIRST_PUBLICATION_PROOF",
                "PUBLISHER_PRIOR_DATE_NOT_FIRST_PUBLICATION_PROOF"):
            reasons.append(pub_status)
        if not original:
            reasons.append("NO_UNIQUE_ORIGINAL_MODEL_CLAIM")
            effect_type, basis = None, None
        else:
            effect_type = original.get("effect_type")
            basis = original.get("direction_basis")
        if effect_type not in ACCEPTED_EFFECTS:
            reasons.append("NO_SUBSTANTIVE_OBSERVED_DIRECTION_BASIS")
        if not isinstance(basis, str) or not 30 <= len(basis.strip()) <= 450:
            reasons.append("MISSING_OR_MALFORMED_DIRECTION_RATIONALE")
        quote = witness.get("passage") or ""
        overlap = sorted(_words(entry.get("observation", "")) & _words(quote))
        rationale_overlap = (
            sorted(_words(basis) & _words(quote)) if isinstance(basis, str)
            else [])
        if len(overlap) < 2:
            reasons.append("ORIGINAL_PASSAGE_NOT_RELEVANT_TO_CLAIM_TEXT")
        if len(rationale_overlap) < 2:
            reasons.append("DIRECTION_REASON_NOT_GROUNDED_IN_PASSAGE_TEXT")
        reasons = sorted(set(reasons))
        decision = {
            "id": identifier,
            "original_url": key,
            "source_body_sha256": witness.get("source_body_sha256"),
            "passage_status": witness.get("status"),
            "observed_event_date": entry.get("event_date"),
            "event_date_status": event_status,
            "source_publication_status": pub_status,
            "model_effect_type": effect_type,
            "original_direction": entry.get("direction"),
            "model_direction_basis": basis,
            "observation_passage_overlap": overlap,
            "direction_passage_overlap": rationale_overlap,
            "directional_semantic_verification": "NOT_ESTABLISHED_DUAL_REVIEW_REQUIRED",
            "first_publication_verified": False,
            "reasons": reasons,
            "decision": ADMISSION if not reasons else REJECT,
        }
        decisions.append(decision)
        if reasons:
            held.append(copy.deepcopy(entry))
        else:
            admitted.append(copy.deepcopy(entry))
    # No source or originally reported error disappears from the audit.
    amended = copy.deepcopy(packet)
    amended["evidence"] = admitted
    amended["pre_review_held_original_evidence"] = held
    amended["pre_review_original_evidence"] = copy.deepcopy(frozen)
    amended["pre_review_claim_decisions"] = decisions
    amended["pre_review_original_input_sha256"] = sha(packet)
    amended["pre_review_admission_version"] = GATE_VERSION
    amended["pre_review_limitations"] = (
        "Text overlap and page dates are necessary screening features only. "
        "No first-publication time, semantic direction, source independence "
        "or observed geopolitical consequence was thereby verified.")
    # Preserve every original URL; update only the reviewed packet's
    # classification of which sources support currently admitted evidence.
    quality = amended["source_quality_audit"]
    for row in quality["sources"]:
        if "pre_review_original_role" not in row:
            row["pre_review_original_role"] = row.get("role")
            row["pre_review_original_evidence_indices"] = row.get(
                "new_evidence_indices", [])
        row["new_evidence_indices"] = [
            n for n, e in enumerate(admitted)
            if url_key(e.get("source")) == row["url"] and
            e.get("evidence_status") == "new"]
        row["role"] = ("new_evidence" if row["new_evidence_indices"]
                       else "coverage_context_only")
    quality["evidence_source_count"] = sum(
        row["role"] == "new_evidence" for row in quality["sources"])
    quality["context_only_source_count"] = sum(
        row["role"] == "coverage_context_only" for row in quality["sources"])
    for row in amended["coverage"]:
        if "pre_review_original_outcome" not in row:
            row["pre_review_original_outcome"] = row.get("outcome")
        urls = {url_key(x) for x in row.get("original_urls", [])}
        retained = sorted(e["id"] for e in admitted
                          if url_key(e.get("source")) in urls)
        row["pre_review_admitted_evidence_ids"] = retained
        if not retained and row.get("outcome") == "eligible_reporting_found":
            row["outcome"] = "inaccessible_or_incomplete"
            row["limitations"] += (
                " Source-category links were searched but no original "
                "directional observation passed the pre-review screen.")
    count = eligibility(amended)
    outcome = {
        "version": GATE_VERSION,
        "status": ("PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY" if
                   not count["failures"] else
                   "PRE_REVIEW_ADMISSIBILITY_BLOCKED_NO_PAID_REVIEWS"),
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "history_sha256": baseline_sha,
        "original_review_input_sha256": sha(packet),
        "screened_review_input_sha256": sha(amended),
        "screened_packet": amended,
        "per_claim": decisions,
        "admitted_original_ids": [x["id"] for x in admitted],
        "held_original_ids": [x["id"] for x in held],
        "directional_candidate_counts": count,
        "source_review_requests": ("PERMITTED_AFTER_SCREEN" if
                                   not count["failures"] else "NOT_PERMITTED"),
        "required_next_action": (
            "AFFIRMATIVE_THEN_CRITICAL_ON_EXACT_SCREENED_PACKET"
            if not count["failures"] else
            "NEW_DATED_SOURCE_RESEARCH_SNAPSHOT_WITH_BETTER_ORIGINAL_EVIDENCE"),
        "publication": "NOT AUTHORIZED",
    }
    require(outcome["screened_review_input_sha256"] == sha(outcome["screened_packet"]),
            "Screened packet changed during eligibility certification")
    return outcome


def screen_or_restore(folder, packet, research, *, baseline_sha, snapshot):
    """Persist exact screened packet, refuse changed replay or paid POST."""
    folder = Path(folder)
    result = screen_original_packet(
        packet, research, baseline_sha=baseline_sha, snapshot=snapshot)
    path = folder / "source-pre-review-admissibility.json"
    if path.exists():
        require(read_json(path) == result,
                "Saved pre-review evidence screening differs; no paid reviewer retry")
    else:
        save_new(path, result)
    return result
