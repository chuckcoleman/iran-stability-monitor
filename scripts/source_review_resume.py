"""Fail-closed checkpoints for nonpublishing Iran research source reviews.

Saved audit JSON is untrusted on resume. Recompute every deterministic gate;
reuse paid model replies only if the exact prompt, model, ID, and acknowledged
completed transport agree. Never overwrite an earlier audit.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from assessment_pipeline import LIVE_RESEARCHER, _review_issues, responses_payload
from responses_transport import _valid_id
from source_metadata import url_key
from source_quality_audit import (source_inventory, source_quality_audit,
                                  validate_source_review)
from source_citation_reconciliation import reconcile_source_citations
from source_research_batches import (canonical, read_json, save_new, sha,
                                     require_pre_snapshot_publication)


def digest_prompt(prompt):
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _check(ok, msg):
    if not ok:
        raise ValueError(msg)


def load_or_save_reconciliation(folder, result, citations, calls):
    expected = reconcile_source_citations(result, citations, calls)
    path = Path(folder) / "citation-reconciliation.json"
    if path.exists():
        _check(read_json(path) == expected,
               "Preserved citation reconciliation differs from current source/tool trace")
    else:
        save_new(path, expected)
    return expected


def _metadata_from_quality(prior, result):
    """Reconstruct only fields explicitly recorded by the earlier source audit.

    Missing original retrieval timestamps remain missing, never backdated.
    Every recovered field must deterministically reproduce the old audit.
    """
    _check(isinstance(prior, dict)
           and prior.get("status") == "SOURCE_BY_SOURCE_REVIEW_REQUIRED"
           and isinstance(prior.get("sources"), list),
           "Invalid prior source-quality checkpoint")
    expected = set(source_inventory(result))
    rows = prior["sources"]
    _check(len(rows) == len(expected), "Preserved source-quality inventory changed")
    metadata = {}
    for item in rows:
        _check(isinstance(item, dict), "Malformed preserved source-quality row")
        url = item.get("url")
        _check(url in expected and url not in metadata,
               "Preserved source-quality URL changed or repeated")
        retrieval = item.get("source_retrieval_status")
        metadata[url] = {
            "retrieval_status": None if retrieval == "unrecorded" else retrieval,
            "source_publication_time": item.get("source_publication_time"),
            "publication_dates": item.get("publication_dates_from_page", []),
            "metadata_status": item.get("metadata_status")
        }
    _check(set(metadata) == expected, "Incomplete preserved source-quality inventory")
    return metadata


def load_or_capture_quality(folder, result, citations, metadata_reader, now,
                            snapshot, baseline_sha, *, strict=True):
    folder = Path(folder)
    metadata_file = folder / "source-metadata-checkpoint.json"
    quality_file = folder / "source-quality-audit.json"
    result_sha = sha(result)
    snap_sha = snapshot["snapshot_sha256"] if snapshot else None
    inventory = source_inventory(result)
    for key in inventory:
        _check(url_key(key) in {url_key(u) for u in citations},
               "Source-quality URL has no original citation")
    if metadata_file.exists():
        saved = read_json(metadata_file)
        _check(saved.get("research_sha256") == result_sha
               and saved.get("baseline_history_sha256") == baseline_sha
               and saved.get("snapshot_sha256") == snap_sha,
               "Source metadata checkpoint belongs to different evidence/history")
        metadata = saved.get("metadata")
        _check(isinstance(metadata, dict)
               and set(metadata) == set(inventory),
               "Saved source metadata is incomplete or contains extra URLs")
    elif quality_file.exists():
        # Migration path for diagnostic #39608218460, whose old code saved
        # the complete quality audit but did not save the raw metadata mapping.
        prior = read_json(quality_file)
        metadata = _metadata_from_quality(prior, result)
        save_new(metadata_file, {
            "research_sha256": result_sha,
            "baseline_history_sha256": baseline_sha,
            "snapshot_sha256": snap_sha,
            "provenance": "reconstructed_from_saved_quality_audit",
            "limitations": ("No original source retrieval instant was stored; "
                            "unknown times are not invented or backdated."),
            "metadata": metadata})
    else:
        metadata = {url: metadata_reader(url) for url in inventory}
        _check(all(isinstance(v, dict) for v in metadata.values()),
               "Source metadata reader returned malformed result")
        save_new(metadata_file, {
            "research_sha256": result_sha,
            "baseline_history_sha256": baseline_sha,
            "snapshot_sha256": snap_sha,
            "provenance": "original_metadata_capture",
            "metadata": metadata})
    if snapshot:
        require_pre_snapshot_publication(result, metadata, snapshot)
    # Quality is recomputed; previous review assertions are not self-certifying.
    quality = source_quality_audit(result, metadata, strict=strict, cutoff=now())
    if quality_file.exists():
        _check(read_json(quality_file) == quality,
               "Preserved source-quality audit does not reproduce from source annotations")
    else:
        save_new(quality_file, quality)
    # Preserve the exact original spelling of evidence source links for freeze.
    for item in result.get("evidence", []):
        if item.get("evidence_status", "new") == "new":
            key = url_key(item.get("source"))
            if key in metadata:
                metadata[item["source"]] = metadata[key]
    return quality, metadata


def load_or_create_review_input(folder, *, result, citations, coverage, quality,
                                baseline_sha, snapshot, archive, date, now,
                                freeze):
    folder = Path(folder)
    path = folder / "source-review-input.json"
    snap_sha = snapshot["snapshot_sha256"] if snapshot else None
    source_sha = sha(result)
    quality_sha = sha(quality)
    if path.exists():
        stored = read_json(path)
        _check(stored.get("baseline_history_sha256") == baseline_sha
               and stored.get("snapshot_sha256") == snap_sha
               and stored.get("research_sha256") == source_sha
               and stored.get("source_quality_sha256") == quality_sha,
               "Preserved review-input snapshot differs from research or history")
        sample = stored.get("sample")
        _check(isinstance(sample, dict)
               and sample.get("published_history_sha256") == baseline_sha
               and sample.get("source_quality_audit") == quality
               and sample.get("coverage") == coverage
               and sample.get("mode") == "RESEARCH_ONLY_TEST_NO_SCORED_FORECASTS"
               and stored.get("input_sha256") == sha(sample),
               "Preserved closed review input was modified")
        cutoff = dt.datetime.fromisoformat(sample["cutoff"])
        _check(cutoff.tzinfo is not None and cutoff.utcoffset() is not None
               and cutoff.date() >= dt.date.fromisoformat(date)
               and cutoff <= now(),
               "Invalid stored review cutoff")
        if snapshot:
            _check(cutoff >= dt.datetime.fromisoformat(snapshot["cutoff_at"]),
                   "Review cutoff predates the original source snapshot")
        return sample, stored["input_sha256"], cutoff

    cutoff = now()
    frozen = freeze(result, citations, archive, date, cutoff)
    sample = {"evidence": frozen, "coverage": coverage,
              "source_quality_audit": quality, "cutoff": cutoff.isoformat(),
              "published_history_sha256": baseline_sha,
              "mode": "RESEARCH_ONLY_TEST_NO_SCORED_FORECASTS"}
    checkpoint = {
        "status": "CLOSED_SOURCE_REVIEW_INPUT_NOT_APPROVED",
        "baseline_history_sha256": baseline_sha,
        "snapshot_sha256": snap_sha,
        "research_sha256": source_sha,
        "source_quality_sha256": quality_sha,
        "input_sha256": sha(sample),
        "sample": sample,
        "publication": "NOT AUTHORIZED"}
    save_new(path, checkpoint)
    return sample, checkpoint["input_sha256"], cutoff


def _matching_completed_response(folder, prompt, model):
    """A response audit is trusted only with its matching completed API journal."""
    fingerprint = digest_prompt(prompt)
    expected = responses_payload(prompt, False)
    request_sha = sha(expected)
    matches = []
    for file in Path(folder).glob("response-*.json"):
        row = read_json(file)
        if row.get("prompt_sha256") != fingerprint or row.get("search") is not False:
            continue
        _check(row.get("model") == model and _valid_id(row.get("response_id")),
               "Saved source-review response has invalid model or ID")
        journals = [read_json(p) for p in Path(folder).glob("api-request-*.json")]
        _check(any(j.get("request_sha256") == request_sha
                   and j.get("response_id") == row["response_id"]
                   and j.get("post_attempts") == 1
                   and j.get("status") == "api_completed_output_not_yet_validated"
                   and j.get("phase") == "non-search assessment/review"
                   for j in journals),
               "Saved source-review response lacks completed OpenAI transport journal")
        matches.append(row)
    _check(len(matches) <= 1, "Ambiguous completed source review for exact prompt")
    return matches[0]["result"] if matches else None


def _unacknowledged_reviews(folder):
    """Return potentially accepted, unconfirmed foreground review POSTs."""
    unresolved = []
    for file in Path(folder).glob("api-request-*.json"):
        row = read_json(file)
        if (row.get("phase") == "non-search assessment/review"
                and row.get("post_attempts") == 1
                and row.get("status") in (
                    "create_sent_acknowledgement_pending",
                    "create_acknowledgement_unknown_no_replay",
                    "nonsearch_not_completed")):
            unresolved.append(row)
    return unresolved


def review_with_checkpoint(folder, *, role, prompt, input_sha, quality,
                           reviewer, now, allow_new_after_unknown=False,
                           superseded_unknown_requests=(), round_number=1):
    """Check a review once or reuse its verified result without another POST.

    A lost acknowledgement is never replayed automatically. Explicit opt-in
    permits an additional review only, not new research, citation search or
    a declaration of approval.
    """
    _check(role in ("affirmative", "critical"), "Unknown source review role")
    folder = Path(folder)
    _check(type(round_number) is int and 1 <= round_number <= 6,
           "Invalid bounded source-review round")
    filename = ("source-review-" + role + ".json" if round_number == 1 else
                f"source-review-round-{round_number:02d}-{role}.json")
    path = folder / filename
    prompt_sha = digest_prompt(prompt)
    model = os.getenv("IRAN_FORECAST_MODEL") or "gpt-6.1-sol"
    live = reviewer is LIVE_RESEARCHER
    prior = read_json(path) if path.exists() else None
    superseded = set(superseded_unknown_requests)
    _check(all(isinstance(item, str) and len(item) == 64
               for item in superseded),
           "Invalid previously authorized uncertain-review reference")
    if prior is not None:
        _check(prior.get("status") == "COMPLETED_NOT_PUBLISHABLE"
               and prior.get("role") == role
               and prior.get("input_sha256") == input_sha
               and prior.get("prompt_sha256") == prompt_sha
               and prior.get("model") == model,
               "Existing source-review checkpoint has mismatched input/model")
        response = prior.get("response")
        if live:
            _check(response == _matching_completed_response(folder, prompt, model),
                   "Preserved source-review verdict has no matching completed API response")
    elif live:
        response = _matching_completed_response(folder, prompt, model)
    else:
        response = None
    new_superseded = set(prior.get("superseded_unknown_requests", [])) if prior else set()
    if response is None:
        if live:
            unknown = [item for item in _unacknowledged_reviews(folder)
                       if item.get("request_sha256") not in superseded]
            if unknown:
                _check(allow_new_after_unknown
                       and all(item.get("status") in (
                           "create_sent_acknowledgement_pending",
                           "create_acknowledgement_unknown_no_replay")
                           for item in unknown),
                       "OpenAI review POST acceptance unknown; no automatic paid retry. "
                       "Explicit new-review opt-in required.")
                new_superseded.update(item["request_sha256"] for item in unknown
                                      if isinstance(item.get("request_sha256"), str))
                _check(len(new_superseded) == len(unknown),
                       "Unknown review request identity is missing; no paid retry")
        response, _ = reviewer(prompt, False)
    issues = _review_issues(response, role)
    if live:
        validate_source_review(response, quality, role)
        _check(response == _matching_completed_response(folder, prompt, model),
               "Completed review lacks identical response and transport journals")
    result = {
        "status": "COMPLETED_NOT_PUBLISHABLE", "role": role,
        "approved": not bool(issues), "issues": issues,
        "response": response,
        "source_reviews": response.get("source_reviews", []),
        "model": model, "input_sha256": input_sha,
        "prompt_sha256": prompt_sha,
        "completed_at": (prior.get("completed_at") if prior is not None
                         else now().isoformat()),
        "superseded_unknown_requests": sorted(new_superseded),
        "publication": "NOT AUTHORIZED"}
    if prior is not None:
        _check(prior == result,
               "Saved source-review checkpoint differs from validated result")
    else:
        save_new(path, result)
    return {"approved": result["approved"], "issues": issues,
            "source_reviews": result["source_reviews"],
            "completed_at": result["completed_at"], "draft_sha256": input_sha,
            "superseded_unknown_requests": result["superseded_unknown_requests"]}
