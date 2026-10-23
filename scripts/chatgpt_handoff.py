#!/usr/bin/env python3
"""Offline ChatGPT-first evidence handoff; no OpenAI API, GH API or forecast calls.

The ChatGPT user/session prepares the source dossier, original claims, two
source-review perspectives, frozen forecast draft, full-report reviews and
receipt. GitHub CI independently reproduces structural, provenance and
arithmetic constraints; it CANNOT authenticate an editor's actual web-search
actions or the truth of a cited article from self-reported JSON alone.

Only data bearing the explicit chatgpt_first_no_api provenance opt in to
this new contract. Historical records/receipts are never reclassified.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re

from source_claim_reliability import (
    GRADES, apply_reviewed_reliability, reconcile_dual_reliability)
from source_metadata import url_key
from source_quality_audit import validate_source_review
from source_research_batches import CATEGORIES
from review_receipt import digest

MODE = "chatgpt_first_no_api"
PROVENANCE = "CHATGPT_RESEARCH_REPORTED_NOT_API_WEB_SEARCH_TRACE"
OUTCOMES = frozenset((
    "eligible_reporting_found", "searched_no_eligible_evidence",
    "inaccessible_or_incomplete",
))
IDS = re.compile(r"^[a-f0-9]{64}$")


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(value):
    return digest(value)


def _clock(value, label):
    require(isinstance(value, str), "Missing " + label)
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Malformed " + label) from None
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
            "Missing offset on " + label)
    return stamp


def validate_source_dossier(dossier, before, candidate):
    """Check deterministic provenance, coverage and V10 reliability linkage.

    This validates records provided by ChatGPT; claimed searches, source
    authenticity, separate editorial review execution and factual truth
    still require genuine scrutiny, not an invented API-verification claim.
    """
    require(isinstance(before, dict) and isinstance(candidate, dict)
            and isinstance(dossier, dict),
            "Malformed ChatGPT-first source dossier")
    require(dossier.get("version") == 1 and dossier.get("mode") == MODE
            and dossier.get("research_provenance") == PROVENANCE,
            "Unrecognized or falsely API-verified ChatGPT source dossier")
    require(dossier.get("baseline_sha256") == sha(before)
            and dossier.get("candidate_sha256") == sha(candidate),
            "ChatGPT source dossier does not bind exact historical baseline")
    require(len(candidate.get("updates", [])) == len(before.get("updates", [])) + 1
            and candidate["updates"][:-1] == before["updates"],
            "ChatGPT source dossier cannot change historical records")
    issued = candidate["updates"][-1]
    cutoff_str = (issued.get("assessment_evidence_cutoff")
                  or issued.get("evidence_cutoff"))
    cutoff = _clock(cutoff_str, "published assessment evidence cutoff")
    require(dossier.get("research_as_of") == cutoff_str,
            "Source dossier search cutoff differs from issued assessment")
    try:
        opening = min(_clock(f["forecast_open"], "forecast opening")
                      for f in issued["forecasts"] if f.get("scored") is True)
    except (TypeError, KeyError, ValueError):
        raise ValueError("Missing four scored forecast openings") from None
    require(sum(f.get("scored") is True for f in issued["forecasts"]) == 4
            and cutoff <= opening,
            "ChatGPT research must close before the four scored forecasts")
    completed = _clock(dossier.get("source_review_completed_at"),
                       "source review completion")
    require(cutoff <= completed <= opening,
            "Source review must follow the frozen evidence cutoff "
            "and precede the four forecast openings")
    limitations = dossier.get("provenance_limitations")
    require(isinstance(limitations, str) and len(limitations.strip()) >= 80,
            "Explain limits of ChatGPT search and original-source verification")
    require(dossier.get("post_snapshot_interval") == "NOT_SEARCHED",
            "Later processing is not proof of searching the post-cutoff period")
    categories = dossier.get("coverage")
    require(isinstance(categories, list) and len(categories) == len(CATEGORIES),
            "Require all six independent topical research categories")
    encountered, urls = set(), set()
    for row in categories:
        require(isinstance(row, dict)
                and row.get("category") in CATEGORIES
                and row["category"] not in encountered
                and row.get("outcome") in OUTCOMES
                and isinstance(row.get("queries"), list)
                and row["queries"]
                and len(row["queries"]) <= 50
                and all(isinstance(q, str) and len(q.strip()) >= 8
                        for q in row["queries"])
                and isinstance(row.get("limitations"), str)
                and len(row["limitations"].strip()) >= 30,
                "Invalid or missing ChatGPT research category coverage")
        encountered.add(row["category"])
        original_urls = row.get("original_urls")
        require(isinstance(original_urls, list)
                and len(original_urls) == len(set(original_urls))
                and all(url_key(u) == u for u in original_urls),
                "Coverage links must be distinct canonical public HTTPS URLs")
        if row["outcome"] == "eligible_reporting_found":
            require(bool(original_urls),
                    "Search claiming original evidence must cite original URLs")
        urls.update(original_urls)
    require(encountered == set(CATEGORIES), "Missing a required research class")
    packet = dossier.get("source_review_packet")
    require(isinstance(packet, dict)
            and packet.get("pre_review_admission_version") == 7
            and packet.get("research_as_of") == cutoff_str
            and packet.get("published_history_sha256") == sha(before),
            "ChatGPT-first must use V10 reliability on the exact closed "
            "original research cutoff and immutable prior history")
    quality = packet.get("source_quality_audit")
    rows = quality.get("sources") if isinstance(quality, dict) else None
    require(isinstance(rows, list) and len(rows) == len(urls),
            "Every cited original/context URL needs a unique source audit")
    by_url = {}
    for item in rows:
        require(isinstance(item, dict)
                and isinstance(item.get("url"), str)
                and url_key(item["url"]) == item["url"]
                and item["url"] not in by_url
                and item.get("classification") in (
                    "direct_observation", "attributed_claim", "analysis",
                    "unverified", "background_only")
                and item.get("origin") in (
                    "original_reporting", "syndicated_reprint",
                    "official_or_advocacy_claim", "analytical_secondary",
                    "unknown")
                and item.get("access_status") in (
                    "source_metadata_captured", "source_unavailable",
                    "source_not_retrieved")
                and item.get("first_publication_clock_status") in (
                    "publisher_supplied_metadata_not_independently_confirmed",
                    "publisher_reported_date_only_not_independently_confirmed",
                    "unknown")
                and isinstance(item.get("assessment"), str)
                and len(item["assessment"].strip()) >= 30
                and isinstance(item.get("limitations"), str)
                and len(item["limitations"].strip()) >= 30,
                "Incomplete per-source classification or justification")
        correlates = item.get("corroborating_urls")
        require(isinstance(correlates, list)
                and len(correlates) == len(set(correlates))
                and all(u != item["url"] and url_key(u) == u
                        and u in urls for u in correlates),
                "Unverified or repeated claimed corroborating URL")
        by_url[item["url"]] = item
    require(set(by_url) == urls,
            "Source audit must include every selected original/context URL")
    originally = packet.get("evidence")
    require(isinstance(originally, list),
            "ChatGPT source packet missing original model/author claims")
    decisions = packet.get("pre_review_claim_decisions")
    require(isinstance(decisions, list),
            "Missing original text-passages and claim-level decisions")
    ids = {e.get("id") for e in originally if isinstance(e, dict)}
    require(len(ids) == len(originally) and None not in ids,
            "Original claim IDs missing or repeated")
    original_by_id = {e["id"]: e for e in originally}
    require(len(decisions) >= len(ids), "Original passage decisions incomplete")
    decisions_by_id = {}
    for row in decisions:
        require(isinstance(row, dict)
                and isinstance(row.get("id"), str)
                and row["id"] not in decisions_by_id
                and row.get("original_url") in urls,
                "Original decision has duplicate ID or unlisted original source")
        decisions_by_id[row["id"]] = row
    require(ids.issubset(decisions_by_id),
            "Missing independent source/passage decisions for new claims")
    actual_new = [e for e in issued.get("evidence", [])
                  if e.get("evidence_status") == "new"]
    require({e["id"] for e in actual_new} == ids
            and len(actual_new) == len(ids),
            "Published new claims must exactly match the source-reviewed IDs")
    historical = {}
    for update in before["updates"]:
        for previous in update.get("evidence", []):
            historical[previous["id"]] = previous
    for carried in issued.get("evidence", []):
        if carried.get("evidence_status") != "carried_forward":
            continue
        original = historical.get(carried.get("id"))
        require(isinstance(original, dict)
                and carried == {**original, "evidence_status": "carried_forward"},
                "Carried-forward evidence must exactly retain original historical "
                "source, grade, incident, interpretation and identifier")
    for e in originally:
        require(e.get("evidence_status") == "new"
                and e.get("source") in urls
                and decisions_by_id[e["id"]]["original_url"] == e["source"],
                "A new claim lacks a traceable exact original source URL")
        witness = decisions_by_id[e["id"]]
        passage = witness.get("original_passage")
        body_hash = witness.get("source_body_sha256")
        # Hashes are shape-checked; an independent page capture must still
        # establish that the original body actually produced these bytes.
        require(witness.get("passage_status") ==
                    "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED"
                and isinstance(passage, str)
                and 4 <= len(passage.split()) <= 25
                and isinstance(body_hash, str)
                and IDS.fullmatch(body_hash) is not None
                and witness.get("decision") ==
                    "PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW",
                "Published new evidence lacks admitted original passage witness")
    affirmative = dossier.get("affirmative_source_review")
    critical = dossier.get("critical_source_review")
    require(isinstance(affirmative, dict)
            and isinstance(critical, dict),
            "Two substantive original-source reviews are mandatory")
    for role, response in (("affirmative", affirmative), ("critical", critical)):
        require(response.get("approved") is True and response.get("issues") == [],
                role + " source review has unresolved issues")
        validate_source_review(response, quality, role)
    cert = reconcile_dual_reliability(packet, affirmative, critical)
    adjusted = apply_reviewed_reliability(originally, originally, cert)
    require(adjusted == actual_new,
            "Published new factual grades or stability confidence differ "
            "from conservative dual-reviewed V10 source certificate")
    require(dossier.get("claim_reliability") == cert,
            "Factual reliability certificate differs from reviewed factors")
    # Research results are ChatGPT-authored; no OpenAI Responses API provenance
    # or directly authenticated fact is claimed by structural validation.
    return {"status": "CHATGPT_FIRST_DOSSIER_STRUCTURALLY_VALID_NOT_FACT_PROOF",
            "source_count": len(urls), "category_count": len(categories),
            "new_evidence_count": len(ids),
            "baseline_sha256": sha(before),
            "candidate_sha256": sha(candidate),
            "dossier_sha256": sha(dossier),
            "api_requests": 0,
            "review_provenance":
                "ONE_CHATGPT_SESSION_TWO_PERSPECTIVES_NOT_INDEPENDENT_MODELS",
            "publication": "NOT AUTHORIZED_BY_DOSSIER_ONLY"}


def validate_optional_dossier(before, candidate, receipt, dossier):
    """Require a bound source dossier for explicit ChatGPT-first receipts."""
    mode = receipt.get("research_mode")
    if mode is None:
        require(dossier is None,
                "Unbound ChatGPT-first evidence dossier in published receipt")
        return None
    require(mode == MODE and receipt.get("version") == 3,
            "ChatGPT-first submissions require prospective v3 two-role receipt")
    require(isinstance(dossier, dict)
            and receipt.get("source_dossier_sha256") == sha(dossier),
            "ChatGPT-first receipt must bind complete exact source dossier")
    return validate_source_dossier(dossier, before, candidate)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff", required=True,
                        help="External handoff folder; never a GitHub API endpoint")
    args = parser.parse_args(argv)
    from submit_reviewed_assessment import validate_handoff
    folder = Path(args.handoff)
    result = validate_handoff(folder)
    print("CHATGPT HANDOFF VERIFIED (NO API): " + result["date"])
    print("No GitHub submission, forecast generation or publication performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
