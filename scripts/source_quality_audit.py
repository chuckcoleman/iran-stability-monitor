"""Per-original-source evidence quality audit, separate from frozen forecasts.

A fetched URL, publisher metadata, model commentary and matching news citations
NEVER prove that an event happened. These records expose those limitations
to the affirmative and critical reviewers and document every consulted URL.
"""
import hashlib
import json
from pathlib import Path

from source_metadata import url_key

SOURCE_KINDS=frozenset(("direct_observation", "attributed_claim", "analysis",
                       "unverified", "background_only"))
SOURCE_ORIGINS=frozenset(("original_reporting", "syndicated_reprint",
                         "official_or_advocacy_claim", "analytical_secondary",
                         "unknown"))
STATUS_TYPES=frozenset(("source_metadata_captured", "source_unavailable",
                         "source_not_retrieved"))


def _check(ok, reason):
    if not ok:
        raise ValueError(reason)


def source_inventory(research):
    """Canonical URLs used in new evidence OR the six category source lists."""
    _check(isinstance(research,dict),"Missing research object")
    inventory={}
    for i,category in enumerate(research.get("coverage_audit",[])):
        _check(isinstance(category,dict) and isinstance(category.get("original_urls"),list),
               "Malformed source category inventory")
        for u in category["original_urls"]:
            key=url_key(u)
            _check(key is not None,"Nonpublic source URL in quality inventory")
            entry=inventory.setdefault(key,{"url":key,"claims":[],
                        "coverage_categories":[],"evidence_indices":[]})
            entry["claims"].append(u)
            if category.get("category") not in entry["coverage_categories"]:
                entry["coverage_categories"].append(category.get("category"))
    for i,item in enumerate(research.get("evidence",[])):
        _check(isinstance(item,dict),"Malformed evidence item in source quality audit")
        if item.get("evidence_status","new") != "new":
            continue  # Historic carried-forward evidence has immutable old provenance.
        key=url_key(item.get("source"))
        _check(key is not None,"Nonpublic new evidence source URL")
        entry=inventory.setdefault(key,{"url":key,"claims":[],
                    "coverage_categories":[],"evidence_indices":[]})
        entry["claims"].append(item["source"])
        entry["evidence_indices"].append(i)
    return {key:inventory[key] for key in sorted(inventory)}


def source_quality_audit(research, metadata, *, strict=True, cutoff=None):
    """Build complete, reviewable per-source records without promoting claims.

    Requires explicitly authored quality annotations for EVERY unique source
    in live mode; incomplete/inaccessible reporting must say UNKNOWN rather
    than fabricate its date, original content or independent corroboration.
    """
    expected=source_inventory(research)
    _check(isinstance(metadata,dict),"Source metadata mapping is absent")
    annotations=research.get("source_quality")
    if not strict and annotations is None:
        annotations=[{"url":u,"kind":"unverified","origin":"unknown",
                      "corroborating_urls":[],
                      "assessment":"No independently inspected source-quality classification exists in this synthetic test.",
                      "limitations":"No original article content or publication timing verified by this synthetic test."}
                     for u in expected]
    _check(isinstance(annotations,list),"Missing required source-by-source quality audit")
    mapped={}
    for row in annotations:
        _check(isinstance(row,dict),"Malformed source quality annotation")
        key=url_key(row.get("url"))
        _check(key in expected and key not in mapped,"Missing, unknown or repeated source quality URL")
        _check(row.get("kind") in SOURCE_KINDS,"Unknown source claim/evidence class")
        _check(row.get("origin") in SOURCE_ORIGINS,"Unknown original/syndicated source classification")
        for field in ("assessment","limitations"):
            _check(isinstance(row.get(field),str) and len(row[field].strip())>=30,
                   "Each source needs an explicit justification and disclosure: "+str(key))
        supporting=row.get("corroborating_urls")
        _check(isinstance(supporting,list) and len(supporting)==len(set(supporting)),
               "Malformed source corroboration URLs")
        normalized=[]
        for url in supporting:
            other=url_key(url)
            _check(other in expected and other!=key and other not in normalized,
                   "Corroboration must refer to a distinct cited source in the same research set")
            normalized.append(other)
        mapped[key]={"kind":row["kind"],"origin":row["origin"],
                     "assessment":row["assessment"].strip(),
                     "limitations":row["limitations"].strip(),
                     "corroborating_urls":normalized}
    _check(set(mapped)==set(expected),"Quality audit omits source URLs")

    audit=[]
    for url,item in expected.items():
        annotation=mapped[url]
        candidates=[metadata.get(u) for u in item["claims"] if isinstance(metadata.get(u),dict)]
        candidates+=([metadata.get(url)] if isinstance(metadata.get(url),dict) else [])
        status=next((m for m in candidates if m.get("retrieval_status")=="retrieved"),None)
        if status is None:
            status=next(iter(candidates),{})
        public_time=status.get("source_publication_time")
        if public_time is not None:
            import datetime as dt
            try:
                stamp=dt.datetime.fromisoformat(public_time.replace("Z","+00:00"))
                _check(stamp.tzinfo is not None and stamp.utcoffset() is not None,
                       "Source publication metadata has no timezone")
            except (ValueError,TypeError,AttributeError):
                raise ValueError("Malformed precise source publication metadata") from None
            if cutoff is not None:
                _check(stamp<=cutoff,"Source metadata publication time after research cutoff")
        retrieval=status.get("retrieval_status")
        access=("source_metadata_captured" if retrieval=="retrieved"
                else "source_unavailable" if retrieval and retrieval!="retrieved"
                else "source_not_retrieved")
        flags=[]
        if public_time is None:flags.append("precise_first_publication_time_unverified")
        if access!="source_metadata_captured":flags.append("direct_article_metadata_unavailable")
        if annotation["origin"] in ("syndicated_reprint","unknown"):
            flags.append("original_or_syndication_uncertain")
        if not annotation["corroborating_urls"]:
            flags.append("no_independent_corroboration_identified")
        if annotation["kind"] in ("attributed_claim","analysis","unverified","background_only"):
            flags.append("not_an_independently_verified_observation")
        evidence_rows=[research["evidence"][i] for i in item["evidence_indices"]]
        if annotation["kind"] in ("analysis","unverified") and any(
            row.get("direction") in ("raises","lowers") for row in evidence_rows):
            flags.append("directional_claim_needs_explicit_review")
        details = {}
        if "publication_date_evidence" in status:
            witnesses = status["publication_date_evidence"]
            _check(isinstance(witnesses, list)
                   and all(isinstance(w, dict)
                           and w.get("origin") ==
                              "article_headline_adjacent_visible_date"
                           and isinstance(w.get("date"), str)
                           and w.get("first_publication_verified") is False
                           for w in witnesses),
                   "Malformed claimed visible article-date provenance")
            details = {
                "publication_date_evidence": witnesses,
                "publisher_date_not_first_publication_proof": True}
        audit.append({
            **details,
            "url":url, "coverage_categories":sorted(item["coverage_categories"]),
            "new_evidence_indices":sorted(item["evidence_indices"]),
            "role":"new_evidence" if item["evidence_indices"] else "coverage_context_only",
            "classification":annotation["kind"],"origin":annotation["origin"],
            "corroborating_urls":annotation["corroborating_urls"],
            "assessment":annotation["assessment"],"limitations":annotation["limitations"],
            "access_status":access,"source_retrieval_status":retrieval or "unrecorded",
            "source_publication_time":public_time,
            "first_publication_clock_status":(
                "publisher_supplied_metadata_not_independently_confirmed"
                if public_time is not None else "unknown"),
            "publication_dates_from_page":status.get("publication_dates",[]),
            "metadata_status":status.get("metadata_status","not independently retrieved"),
            "flags":flags,
            "factual_verification":"not_automatically_established",
        })
    return {
        "status":"SOURCE_BY_SOURCE_REVIEW_REQUIRED",
        "sources":audit,"source_count":len(audit),
        "evidence_source_count":sum(r["role"]=="new_evidence" for r in audit),
        "context_only_source_count":sum(r["role"]=="coverage_context_only" for r in audit),
        "unverified_clock_count":sum(r["source_publication_time"] is None for r in audit),
        "limitations":"A cited URL, page date or model annotation is not independent confirmation. "
                      "The two reviewers must examine each source and its claim-level limitations.",
    }


def save_quality_audit(directory, audit):
    path=Path(directory)/"source-quality-audit.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as file:
        json.dump(audit,file,ensure_ascii=False,sort_keys=True,indent=2)
        file.write("\n")
    return path


def validate_source_review(decision, quality, role):
    """Require a substantive affirmative or critical check for EVERY source.

    A global approved flag cannot override omitted articles or source issues.
    """
    urls={row["url"] for row in quality["sources"]}
    reviews=decision.get("source_reviews") if isinstance(decision,dict) else None
    _check(isinstance(reviews,list) and len(reviews)==len(urls),
           role+" reviewer did not inspect every quality-audit source")
    seen=set()
    for item in reviews:
        _check(isinstance(item,dict),"Malformed "+role+" source review")
        key=url_key(item.get("url"))
        _check(key in urls and key not in seen,
               role+" source review duplicates or omits an original URL")
        seen.add(key)
        _check(isinstance(item.get("assessment"),str)
               and len(item["assessment"].strip())>=30,
               role+" source review needs specific substantive findings")
        _check(item.get("disposition") in ("supported_as_qualified",
                                          "background_only","unverified_reject"),
               role+" source review missing evidence-quality disposition")
        if item["disposition"]=="unverified_reject":
            _check(decision.get("approved") is False,
                   role+" cannot approve a rejected or unverified source")
    _check(seen==urls,role+" source reviews omit quality audit URLs")
    return True
