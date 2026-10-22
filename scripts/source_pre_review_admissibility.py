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


def _quote_language_mismatch(original_quote, observation):
    """Identify a non-Latin original cited with a Latin-script observation.

    This only triggers a translation review, never supplies a translation.
    Do not identify language by source domain, nationality or guesswork.
    """
    if not isinstance(original_quote, str) or not isinstance(observation, str):
        return False
    has_non_latin = any(
        (0x0600 <= ord(c) <= 0x06FF or
         0x0400 <= ord(c) <= 0x052F or
         0x4E00 <= ord(c) <= 0x9FFF)
        for c in original_quote)
    has_latin_observation = bool(re.search(r"[A-Za-z]{4,}", observation))
    return has_non_latin and has_latin_observation


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


def actual_search_query_ledger(calls):
    """Bind the compact full research query ledger to actual captured API calls.

    Exact queries are facts about searches attempted, not proof that those
    searches were balanced or returned independently verified observations.
    Both reviewers must independently evaluate balance; no successful
    'raises' or 'lowers' event may be fabricated to meet a quota.
    """
    from source_research_batches import CATEGORIES
    require(isinstance(calls, list) and bool(calls),
            "Missing real web-search calls for v5 source review")
    queries = {category: set() for category in CATEGORIES}
    for call in calls:
        require(isinstance(call, dict) and
                call.get("search_calls_real") is True,
                "Malformed actual source-research search trace")
        category = call.get("research_category")
        if category not in queries:
            continue  # A separate citation-correction call is not research.
        values = call.get("queries_exposed_by_api")
        require(isinstance(values, list),
                "Source search trace lacks actual executed query text")
        for value in values:
            require(isinstance(value, str) and
                    3 <= len(value.strip()) <= 500,
                    "Unusable query in actual source-search trace")
            queries[category].add(value.strip())
            require(len(queries[category]) <= 96,
                    "V5 source research exposes too many distinct executed queries")
    require(all(queries.values()),
            "Each of six source categories needs an actual query record")
    return [{"category": category, "queries": sorted(queries[category]),
             "query_count": len(queries[category])}
            for category in CATEGORIES]


def screen_original_packet(packet, research, *, baseline_sha, snapshot,
                           search_calls=None):
    """Create an immutable source-by-source, claim-by-claim pre-review screen."""
    require(isinstance(packet, dict) and isinstance(snapshot, dict)
            and snapshot.get("version") in (3, 4, 5, 6, 7),
            "Pre-review admission requires new v3 research snapshot")
    require(packet.get("published_history_sha256") == baseline_sha
            and packet.get("research_as_of") == snapshot.get("cutoff_at"),
            "Admissibility cannot move the frozen search cutoff or history")
    version = snapshot["version"]
    query_ledger = (actual_search_query_ledger(search_calls)
                    if version >= 5 else None)
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
        # Original satellite-image reporting can be labelled "analysis" by
        # the researcher even though it contains primary observational
        # comparisons. V4 permits it only *provisionally*, when the original
        # publisher and model explicitly identify the measurement method.
        # This does not authenticate the imagery or the stability direction.
        original_imagery = (
            version >= 4 and
            source.get("classification") == "analysis" and
            source.get("origin") == "original_reporting" and
            isinstance(original, dict) and
            original.get("effect_type") == "measured_data" and
            original.get("observational_method") ==
                "original_satellite_imagery")
        if ((source.get("classification") not in
                 ("direct_observation", "attributed_claim")
                and not original_imagery) or
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
        semantic_flags = []
        translation = None
        source_language = None
        translation_overlap = []
        if version >= 4:
            # Every v4 candidate's event and stability direction must be
            # evaluated separately by BOTH source reviewers; a word
            # overlap never establishes the model's causal sign.
            semantic_flags.append(
                "DIRECTIONAL_EFFECT_REQUIRES_DUAL_REVIEW")
            # The original-language quote remains unchanged and byte-hashed
            # in the source witness. An unverified model-draft translation is
            # accepted for lexical TRIAGE only, and both later reviewers must
            # check its fidelity and whether the observation is actually in
            # that passage. It cannot establish event truth or effect sign.
            if _quote_language_mismatch(quote, entry.get("observation", "")):
                source_language = (
                    original.get("original_quote_language")
                    if isinstance(original, dict) else None)
                candidate = (
                    original.get("support_quote_translation")
                    if isinstance(original, dict) else None)
                status = (
                    original.get("translation_status")
                    if isinstance(original, dict) else None)
                if (isinstance(candidate, str) and
                        15 <= len(candidate.strip()) <= 1200 and
                        isinstance(source_language, str) and
                        re.fullmatch(r"[a-z]{2,3}(?:-[a-z]{2,4})?",
                                     source_language) and
                        status == "MODEL_DRAFT_UNVERIFIED"):
                    translation = candidate.strip()
                    translation_overlap = sorted(
                        _words(entry.get("observation", "")) &
                        _words(translation))
                if len(translation_overlap) < 2:
                    reasons.append("MISSING_GROUNDED_CROSS_LANGUAGE_TRANSLATION")
                else:
                    semantic_flags.append(
                        "MODEL_TRANSLATION_UNVERIFIED_CHECK_BOTH_REVIEWS")
            elif len(overlap) < 2:
                reasons.append("ORIGINAL_PASSAGE_NOT_RELEVANT_TO_CLAIM_TEXT")
            if len(rationale_overlap) < 2:
                semantic_flags.append(
                    "DIRECTIONAL_EFFECT_UNVERIFIED_CHECK_BOTH_REVIEWS")
            if original_imagery:
                semantic_flags.append(
                    "ORIGINAL_IMAGERY_METHOD_UNVERIFIED_CHECK_BOTH_REVIEWS")
        else:
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
        if version >= 4:
            decision.update({
                "semantic_review_flags": semantic_flags,
                "translation_source_language": source_language,
                "original_passage": quote if translation is not None else None,
                "model_draft_translation": translation,
                "translation_observation_overlap": translation_overlap,
                "translation_fidelity_verified": False,
                "original_observational_method": (
                    original.get("observational_method")
                    if isinstance(original, dict) else None),
                "source_classification": source.get("classification"),
                "original_imagery_provisionally_admitted": bool(original_imagery),
                "publisher_date_evidence": source.get(
                    "publication_date_evidence", []),
            })
        if version >= 5:
            # Publisher timestamps and visible headline dates are publisher
            # assertions, not an independently proven release instant.
            # If source metadata differ by more than one day, record the
            # ambiguity and require both reviewers to address it.
            try:
                pub_days = sorted({
                    dt.date.fromisoformat(x)
                    for x in source.get("publication_dates_from_page", [])
                    if isinstance(x, str)
                })
            except (ValueError, TypeError):
                pub_days = []  # Invalid metadata was already held out above.
            date_disagreement = (
                len(pub_days) > 1 and
                (pub_days[-1] - pub_days[0]).days > 1)
            if date_disagreement:
                decision["semantic_review_flags"].append(
                    "CONFLICTING_PUBLISHER_DATES_REVIEW_REQUIRED")
            decision["publisher_date_conflict"] = date_disagreement
            decision["original_passage"] = quote
            decision["review_passage_sha256"] = hashlib.sha256(
                quote.encode("utf-8")).hexdigest()
            decision["source_body_sha256"] = witness.get("source_body_sha256")
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
    amended["pre_review_admission_version"] = (
        4 if version >= 7 else 3 if version >= 5
        else 2 if version >= 4 else GATE_VERSION)
    amended["pre_review_limitations"] = (
        "Text overlap and page dates are necessary screening features only. "
        "No first-publication time, semantic direction, source independence "
        "or observed geopolitical consequence was thereby verified.")
    if version >= 4:
        amended["background_source_analyses"] = [
            {"id": item["id"], "original_url": url_key(item.get("source")),
             "event_date": item.get("event_date"),
             "original_observation": item.get("observation"),
             "classification": "BACKGROUND_ANALYSIS_NOT_DIRECTIONAL_EVIDENCE",
             "source_access_not_guaranteed": True}
            for item in held
            if any(x.get("id") == item["id"] and
                   x.get("model_effect_type") in (
                       "analysis_or_forecast", "background_context")
                   for x in decisions)]
        amended["pre_review_limitations"] += (
            " V4 draft translations and original imagery interpretations "
            "are unresolved interpretive claims. Each must be examined "
            "by affirmative AND critical reviewers against the original "
            "language and physical source; a model draft is not certified "
            "translation or corroboration. Background analysis never "
            "counts toward directional observation minima.")
    if version >= 5:
        amended["pre_review_actual_search_queries"] = query_ledger
        amended["pre_review_limitations"] += (
            " V5 discloses executed queries in every source category and "
            "does not demand observed events in all three directions. "
            "Both reviewers must judge whether positive, negative and "
            "ambiguous possibilities were sought and whether any event "
            "or stability-effect claim was selected merely for balance. "
            "Quote hashes bind reviewer checks to the exact original body.")
    if version >= 7:
        amended["pre_review_limitations"] += (
            " V7 has NO minimum count for admitted observations, publishers, "
            "genuinely new observations or observed directions. Zero eligible "
            "observations must be disclosed, not substituted or interpreted "
            "as proof of stability or instability. Both independent source "
            "reviewers must judge the adequacy of what survived source "
            "admission and may reject unsupported inferences. Screening "
            "approval never authorizes publication.")
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
        "version": (4 if version >= 7 else 3 if version >= 5
                    else 2 if version >= 4 else GATE_VERSION),
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


def screen_or_restore(folder, packet, research, *, baseline_sha, snapshot,
                      search_calls=None):
    """Persist exact screened packet, refuse changed replay or paid POST."""
    folder = Path(folder)
    result = screen_original_packet(
        packet, research, baseline_sha=baseline_sha, snapshot=snapshot,
        search_calls=search_calls)
    path = folder / "source-pre-review-admissibility.json"
    if path.exists():
        require(read_json(path) == result,
                "Saved pre-review evidence screening differs; no paid reviewer retry")
    else:
        save_new(path, result)
    return result
