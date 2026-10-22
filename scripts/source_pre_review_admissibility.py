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
    return set(re.findall(r"[^\W\d_]{4,}", text.casefold(), flags=re.UNICODE)) - STOP


def _source_script(text):
    """A transparent script indicator, NOT a model-determined language ID."""
    if not isinstance(text, str):
        return "unknown"
    arabic = sum("\u0600" <= ch <= "\u06ff" or "\u0750" <= ch <= "\u077f"
                 for ch in text)
    cyrillic = sum("\u0400" <= ch <= "\u052f" for ch in text)
    latin = sum("a" <= ch.casefold() <= "z" for ch in text)
    counts = {"arabic": arabic, "cyrillic": cyrillic, "latin": latin}
    maximum = max(counts.values())
    leaders = [k for k, value in counts.items() if value == maximum]
    return leaders[0] if maximum >= 4 and len(leaders) == 1 else "undetermined"


def _v4_event_grounding(entry, original, quote):
    """Separate limited factual quote grounding from *interpretive* direction.

    An explicit model translation can make a cross-script claim reviewable,
    but it cannot certify source semantics and cannot replace the exact
    original-language passage. Rationale for direction is deliberately NOT
    scored by overlapping causal words: source documents rarely contain
    the political effect implied by a researcher.
    """
    event_basis = original.get("event_basis") if original else None
    direction_basis = original.get("direction_basis") if original else None
    language = original.get("source_language") if original else None
    translation = original.get("support_quote_translation") if original else None
    method = original.get("original_method") if original else None
    original_script = _source_script(quote)
    observation_script = _source_script(entry.get("observation", ""))
    reasons = []
    if not isinstance(language, str) or not re.fullmatch(
            r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", language):
        reasons.append("MISSING_OR_MALFORMED_ORIGINAL_LANGUAGE")
    if original_script == "arabic" and language not in ("ar", "fa", "ur", "ps"):
        reasons.append("SOURCE_LANGUAGE_CONTRADICTS_QUOTE_SCRIPT")
    if original_script == "cyrillic" and language in ("en", "ar", "fa"):
        reasons.append("SOURCE_LANGUAGE_CONTRADICTS_QUOTE_SCRIPT")
    if original_script == "latin" and language in ("ar", "fa", "ur", "ps"):
        reasons.append("SOURCE_LANGUAGE_CONTRADICTS_QUOTE_SCRIPT")
    translated = (isinstance(language, str) and language != "en") or (
        original_script not in ("latin", "undetermined") and
        observation_script == "latin")
    if translated:
        if (not isinstance(translation, str)
                or not 30 <= len(translation.strip()) <= 900
                or not re.search(r"[a-z]{4,}", translation.casefold())):
            reasons.append("UNVERIFIED_TRANSLATION_MISSING_OR_MALFORMED")
            comparison_text = ""
        else:
            comparison_text = translation
    else:
        comparison_text = quote
        if translation not in (None, ""):
            reasons.append("ENGLISH_ORIGINAL_MUST_NOT_USE_EXTRA_TRANSLATION")
    if not isinstance(event_basis, str) or not 30 <= len(event_basis.strip()) <= 450:
        reasons.append("MISSING_OR_MALFORMED_FACTUAL_EVENT_BASIS")
        event_basis = ""
    if not isinstance(direction_basis, str) or not 30 <= len(direction_basis.strip()) <= 450:
        reasons.append("MISSING_OR_MALFORMED_DIRECTION_RATIONALE")
    event_overlap = sorted(_words(event_basis) & _words(comparison_text))
    observation_overlap = sorted(_words(entry.get("observation", "")) &
                                 _words(comparison_text))
    if len(event_overlap) < 2:
        reasons.append("FACTUAL_EVENT_BASIS_NOT_GROUNDED_IN_ORIGINAL_OR_TRANSLATION")
    if len(observation_overlap) < 2:
        reasons.append("OBSERVATION_NOT_GROUNDED_IN_ORIGINAL_OR_TRANSLATION")
    return {
        "reasons": reasons,
        "original_quote": quote,
        "original_quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        "source_script": original_script,
        "observation_script": observation_script,
        "source_language_model_declaration": language,
        "model_translation": translation if translated else None,
        "translation_status": ("MODEL_PROPOSED_UNVERIFIED_REQUIRES_BILINGUAL_CHECK"
                               if translated else "ORIGINAL_QUOTE_USED_NO_TRANSLATION"),
        "translation_independently_checked": False,
        "factual_event_basis": event_basis,
        "factual_event_basis_overlap": event_overlap,
        "observation_quote_or_translation_overlap": observation_overlap,
        "direction_basis": direction_basis,
        "directional_effect_status": "MODEL_INTERPRETATION_NOT_SOURCE_VERIFIED",
        "original_method_declaration": method,
        "factual_support_status": "PROVISIONAL_TEXTUAL_RELEVANCE_NOT_EVENT_VERIFICATION",
    }


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
            and snapshot.get("version") in (3, 4),
            "Pre-review admission requires new v3 research snapshot")
    require(packet.get("published_history_sha256") == baseline_sha
            and packet.get("research_as_of") == snapshot.get("cutoff_at"),
            "Admissibility cannot move the frozen search cutoff or history")
    protocol_v4 = snapshot["version"] == 4
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
        imagery_observation = (
            protocol_v4 and source.get("classification") == "analysis"
            and source.get("origin") == "original_reporting"
            and isinstance(original, dict)
            and original.get("original_method") ==
                "direct_original_satellite_imagery"
            and original.get("effect_type") in ("reported_event", "measured_data"))
        if (not imagery_observation
                and source.get("classification") not in
                    ("direct_observation", "attributed_claim")
                or source.get("origin") in
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
        # A source cannot report a completed incident that had not yet
        # happened on the publication date appearing on that very page.
        # Publisher clocks are unverified but may still disprove impossible
        # chronology. For a range of metadata candidates, use the latest.
        try:
            published_days = [
                dt.date.fromisoformat(x)
                for x in source.get("publication_dates_from_page", [])]
            if source.get("source_publication_time"):
                reported = dt.datetime.fromisoformat(
                    source["source_publication_time"].replace("Z", "+00:00"))
                published_days.append(reported.date())
            event_day = dt.date.fromisoformat(entry["event_date"])
            if published_days and event_day > max(published_days):
                reasons.append("MODEL_EVENT_OCCURS_AFTER_ORIGINAL_REPORT_DATE")
        except (ValueError, TypeError, AttributeError, KeyError):
            reasons.append("INVALID_ORIGINAL_SOURCE_EVENT_CHRONOLOGY")
        if not original:
            reasons.append("NO_UNIQUE_ORIGINAL_MODEL_CLAIM")
            effect_type, basis = None, None
        else:
            effect_type = original.get("effect_type")
            basis = original.get("direction_basis")
        if not isinstance(effect_type, str) or effect_type not in ACCEPTED_EFFECTS:
            reasons.append("NO_SUBSTANTIVE_OBSERVED_DIRECTION_BASIS")
        if not isinstance(basis, str) or not 30 <= len(basis.strip()) <= 450:
            reasons.append("MISSING_OR_MALFORMED_DIRECTION_RATIONALE")
        quote = witness.get("passage") or ""
        overlap = sorted(_words(entry.get("observation", "")) & _words(quote))
        rationale_overlap = (
            sorted(_words(basis) & _words(quote)) if isinstance(basis, str)
            else [])
        semantic_screen = None
        if protocol_v4:
            semantic_screen = _v4_event_grounding(entry, original, quote)
            reasons.extend(semantic_screen["reasons"])
        else:
            # Historical v3 rules and saved decisions are preserved exactly.
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
        if protocol_v4:
            decision["v4_separate_factual_and_directional_checks"] = semantic_screen
            decision["publisher_heading_date_evidence"] = source.get(
                "publisher_heading_date_evidence", [])
            decision["publisher_heading_admitted_day"] = source.get(
                "publisher_heading_admitted_day")
            decision["publisher_report_date_not_first_publication_proof"] = True
            decision["original_imagery_eligible_only_for_dual_review"] = (
                imagery_observation and not reasons)
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
    if protocol_v4:
        amended["pre_review_screen_protocol"] = (
            "v4_separate_factual_direction_and_original_language")
        amended["pre_review_v4_source_claim_language_warning"] = (
            "Exact original-page passages and any model translations are "
            "distinct. Translation is NOT independently checked; reviewers "
            "must examine original-language meaning, factual event support "
            "and causal-direction inference separately.")
    amended["pre_review_limitations"] = (
        ("Event-word overlap or unverified model translation offers only "
         "provisional factual relevance. The direction rationale is a "
         "separate analytical claim with NO automatic semantic approval. "
         if protocol_v4 else
         "Text overlap and page dates are necessary screening features only. ")
        + "No first-publication time, semantic direction, source independence "
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
