"""Flag unsupported model-claimed source URLs BEFORE any evidence is frozen.

The reconciliation is an audit, not a URL resolver. It never repairs,
silently drops, or promotes a model-supplied URL to verified evidence.
Only exact matches after the existing conservative public-HTTPS/tracking-key
normalization qualify; similar headlines or article IDs are NOT sufficient.
"""
import json
from pathlib import Path

from source_metadata import url_key


def reconcile_source_citations(research, citations, search_calls=None):
    """Audit every coverage URL and new evidence URL against real citations.

    search_calls=None means real web-tool provenance was NOT TESTED, which is
    allowed only for injected offline fixtures; production callers must pass
    the actual captured search-call objects.
    """
    if not isinstance(research, dict) or not isinstance(research.get("evidence"), list):
        raise ValueError("Research result lacks an evidence list")
    if not isinstance(citations, (set, list, tuple)):
        raise ValueError("Research citations must be a concrete URL collection")
    referenced={url_key(url) for url in citations}
    referenced.discard(None)
    tool_sources=None
    if search_calls is not None:
        if not isinstance(search_calls, list) or not search_calls or not all(
            isinstance(row,dict) and row.get("search_calls_real") is True
            for row in search_calls
        ):
            raise ValueError("Actual search-tool trace is absent or malformed")
        tool_sources={
            url_key(src.get("url"))
            for call in search_calls
            for src in call.get("citation_sources_exposed_by_api",[])
            if isinstance(src,dict)
        }
        tool_sources.discard(None)

    items=[]
    def append(kind, location, raw_url, seen=None):
        key=url_key(raw_url)
        flagged=[]
        if key is None:
            flagged.append("invalid_public_https_url")
        if seen is not None and key is not None:
            if key in seen:
                flagged.append("duplicate_url_within_research_category")
            seen.add(key)
        cited=key is not None and key in referenced
        if not cited and key is not None:
            flagged.append("not_in_response_citations")
        observed=(key is not None and key in tool_sources) if tool_sources is not None else None
        if tool_sources is not None and not observed and key is not None:
            flagged.append("not_in_actual_web_search_sources")
        items.append({
            "kind":kind,"location":location,
            "claimed_url":raw_url,"normalized_claimed_url":key,
            "in_response_citations":bool(cited),
            "in_actual_search_tool_sources":observed,
            "status":"FLAGGED_UNSUPPORTED" if flagged else (
                "CITED_TOOL_MATCH" if tool_sources is not None else
                "CITED_TOOL_PROVENANCE_NOT_TESTED"),
            "flags":flagged
        })

    coverage=research.get("coverage_audit")
    if coverage is not None:
        if not isinstance(coverage,list):
            raise ValueError("Malformed source coverage audit")
        for i,row in enumerate(coverage):
            if not isinstance(row,dict):
                raise ValueError("Malformed source coverage row")
            urls=row.get("original_urls")
            if not isinstance(urls,list):
                raise ValueError("Malformed source coverage original_urls")
            seen=set()
            for j,url in enumerate(urls):
                append("coverage_url",
                       f"coverage_audit[{i}].original_urls[{j}]",url,seen)
    for i,item in enumerate(research["evidence"]):
        if not isinstance(item,dict):
            raise ValueError("Malformed evidence item")
        if item.get("evidence_status","new")=="new":
            append("new_evidence_url",f"evidence[{i}].source",item.get("source"))
    unsupported=[item for item in items if item["flags"]]
    unique_urls=sorted({str(item["claimed_url"]) for item in unsupported})
    return {
        "status":"UNSUPPORTED_CITATIONS_FLAGGED" if unsupported else
                 "ALL_CLAIMED_LINKS_MATCH",
        "all_claims":items,
        "unsupported":unsupported,
        "counts":{
            "coverage_url_claims":sum(x["kind"]=="coverage_url" for x in items),
            "new_evidence_url_claims":sum(x["kind"]=="new_evidence_url" for x in items),
            "unsupported_claims":len(unsupported),
            "unsupported_unique_urls":len(unique_urls),
            "unsupported_coverage_claims":sum(x["kind"]=="coverage_url"
                                               for x in unsupported),
            "unsupported_evidence_claims":sum(x["kind"]=="new_evidence_url"
                                               for x in unsupported)},
        "unsupported_unique_urls":unique_urls,
        "provenance_limitations":(
            "URL matches prove only API citation/tool-source exposure, not "
            "article contents, original publication time, independent reporting "
            "or truth of the underlying claims. Similar AP/article identifiers "
            "are never accepted without an exact verified cited URL.")
    }


def save_reconciliation(audit_dir, reconciliation):
    """Retain the exact claimed URLs and reasons in the diagnostic artifact."""
    folder=Path(audit_dir)
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/"citation-reconciliation.json"
    if path.exists():
        raise ValueError("Pre-freeze citation reconciliation audit already exists")
    with path.open("x",encoding="utf-8") as handle:
        json.dump(reconciliation,handle,ensure_ascii=False,sort_keys=True,indent=2)
        handle.write("\n")
        handle.flush()
    return path


def require_supported_citations(reconciliation):
    if reconciliation.get("unsupported"):
        raise ValueError(
            "Unsupported citations FLAGGED in citation-reconciliation.json; "
            "evidence freeze and forecast publication blocked")
    return True
