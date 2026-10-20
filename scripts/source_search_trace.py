"""Sanitized factual provenance of actual Responses web_search_call tool outputs.

This records which search-call objects and citation URLs the API returned. It
does not prove the truth of model-generated coverage claims, source content,
or that every requested search query was run. No credentials are stored.
"""
from source_metadata import url_key


def observed_search_calls(output):
    if not isinstance(output, list):
        raise ValueError("Malformed Responses output")
    records = []
    for idx, message in enumerate(output):
        if not isinstance(message, dict) or message.get("type") != "web_search_call":
            continue
        action = message.get("action")
        action = action if isinstance(action, dict) else {}
        queries = []
        for field in ("query", "queries"):
            raw = action.get(field)
            if isinstance(raw, str) and raw.strip():
                queries.append(raw.strip()[:450])
            elif isinstance(raw, list):
                queries.extend(q.strip()[:450] for q in raw
                               if isinstance(q, str) and q.strip())
        sources = []
        raw_sources = action.get("sources")
        for src in raw_sources if isinstance(raw_sources, list) else []:
            if not isinstance(src, dict):
                continue
            url = src.get("url")
            if url_key(url) is None:
                continue
            sources.append({
                "url": url_key(url),
                "title": str(src.get("title") or "")[:250]})
        records.append({
            "output_index": idx,
            "action_type": str(action.get("type") or "unavailable")[:80],
            "queries_exposed_by_api": sorted(set(queries)),
            "citation_sources_exposed_by_api": sources,
            "search_calls_real": True})
    return records


def verify_search_trace(result):
    if not isinstance(result, list) or not result:
        raise ValueError("Actual Responses web-search tool execution not evidenced")
    if not all(isinstance(row, dict) and row.get("search_calls_real") is True
               for row in result):
        raise ValueError("Malformed web-search execution trace")
    return True


def verify_claimed_source_links(coverage, calls):
    """Fail closed if any claimed originally inspected URL lacks tool-source evidence.

    Only tests whether the web-search service surfaced the URL, not whether
    the article's contents, timing or factual assertions are verified.
    """
    verify_search_trace(calls)
    surfaced={entry.get("url") for row in calls for entry in
              row.get("citation_sources_exposed_by_api",[])
              if isinstance(entry,dict)}
    for category in coverage:
        for url in category.get("original_urls",[]):
            if url_key(url) not in surfaced:
                raise ValueError("Research category claims URL never exposed by web-search tool")
    return True


def load_matching_search_trace(folder, research_result):
    """Locate the actual saved Responses search record matching this model JSON.

    Synthetic tests can bypass this with injected researchers; production may
    not treat self-reported category claims as actual tool execution.
    """
    import json
    from pathlib import Path
    for path in reversed(sorted(Path(folder).glob("response-*.json"))):
        try:
            payload=json.loads(path.read_text(encoding="utf-8"))
            if (payload.get("search") is True
                    and payload.get("result") == research_result):
                calls=payload.get("tool_search_calls")
                verify_search_trace(calls)
                return calls
        except (OSError,ValueError,TypeError):
            continue
    raise ValueError("No actual web-search tool trace matches this source-sweep result")
