"""Fail-closed V10 triage, promising-lead follow-up and dual review.

All entries are recorded statements of investigative work, not authenticated
proof that a search or remote retrieval occurred. The parent source packet and
both reviews are separately sealed by the preforecast certificate.
"""
import datetime as dt

from review_receipt import digest
from source_metadata import url_key

TRIAGE = frozenset(("promising", "context_only", "excluded"))
DISPOSITIONS = frozenset((
    "ready_for_v10_source_review", "held_unverified", "contradicted",
    "context_only"))
PRIORITIES = frozenset(("high", "normal", "low"))
SCOPES = frozenset(("geography", "time_window", "population_or_denominator",
                    "method_and_inclusions"))
LEAD_FIELDS = frozenset(("source_url", "triage", "priority", "relevance",
                         "admitted_evidence_ids", "followup"))
RESEARCH_FIELDS = frozenset((
    "performed_at", "disposition", "upstream_queries", "counter_queries",
    "checked_urls", "upstream_source_urls", "contrary_source_urls", "scope",
    "reporting_chain", "supporting_findings", "counterevidence_findings",
    "limitations"))
REVIEW_FIELDS = frozenset(("source_url", "triage", "disposition",
                           "lead_sha256", "approved", "issues", "assessment",
                           "limitations"))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def substantive(value, minimum=40):
    return isinstance(value, str) and len(value.strip()) >= minimum


def offset_time(value):
    require(isinstance(value, str), "Missing promising-lead investigation time")
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid promising-lead investigation time") from None
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
            "Promising-lead investigation time lacks timezone")
    return stamp


def checked_urls(values, allowed, why, *, must_include=None):
    require(isinstance(values, list) and len(set(map(str, values))) == len(values),
            why + ": duplicate or malformed URLs")
    require(all(isinstance(u, str) and url_key(u) == u and u in allowed
                for u in values), why + ": noncanonical or unregistered URL")
    require(must_include is None or must_include in values,
            why + ": source URL must be checked")
    return set(values)


def validate_followup_register(register, urls, new_evidence, cutoff):
    """One explicit triage per selected URL; deeper research for every lead.

    URLs found during follow-up must already be included in the normal
    six-category/source-quality inventory. No accepted-claim count is imposed.
    """
    require(isinstance(register, dict)
            and set(register) == {"version", "research_as_of", "leads"}
            and type(register["version"]) is int and register["version"] == 1
            and register["research_as_of"] == cutoff,
            "Missing or misbound V10 promising-evidence follow-up register")
    leads = register.get("leads")
    require(isinstance(leads, list) and len(leads) == len(urls),
            "Every selected source requires one promising-evidence triage")
    allowed = set(urls)
    by_url = {}
    by_claim = {}
    cutoff_at = offset_time(cutoff)
    for lead in leads:
        require(isinstance(lead, dict) and set(lead) == LEAD_FIELDS,
                "Malformed promising-evidence triage entry")
        url = lead["source_url"]
        require(isinstance(url, str) and url_key(url) == url and url in allowed
                and url not in by_url, "Unlisted or repeated promising lead")
        require(lead["triage"] in TRIAGE
                and lead["priority"] in PRIORITIES
                and substantive(lead["relevance"], 50),
                "Missing triage priority, rationale or source relevance")
        ids = lead["admitted_evidence_ids"]
        require(isinstance(ids, list) and len(ids) == len(set(map(str, ids)))
                and all(isinstance(ident, str) and ident
                        for ident in ids),
                "Promising follow-up claims have invalid or duplicated IDs")
        if lead["triage"] != "promising":
            require(lead["followup"] is None and ids == [],
                    "Nonpromising triage cannot silently admit evidence")
        else:
            follow = lead["followup"]
            require(isinstance(follow, dict) and set(follow) == RESEARCH_FIELDS,
                    "Promising source missing complete targeted follow-up")
            require(follow["disposition"] in DISPOSITIONS,
                    "Promising lead has no explicit final disposition")
            require(offset_time(follow["performed_at"]) <= cutoff_at,
                    "Follow-up performed after frozen evidence cutoff")
            for field in ("upstream_queries", "counter_queries"):
                queries = follow[field]
                require(isinstance(queries, list) and bool(queries)
                        and all(substantive(q, 18) for q in queries)
                        and len(queries) == len(set(queries)),
                        "Promising lead lacks actual upstream and counterevidence searches")
            require(set(follow["upstream_queries"]).isdisjoint(
                    follow["counter_queries"]),
                    "Upstream and counterevidence search queries must be distinct")
            checked = checked_urls(follow["checked_urls"], allowed,
                                   "Promising checked URLs", must_include=url)
            checked_urls(follow["upstream_source_urls"], checked,
                         "Promising upstream URLs")
            checked_urls(follow["contrary_source_urls"], checked,
                         "Promising contrary URLs")
            scope = follow["scope"]
            require(isinstance(scope, dict) and set(scope) == SCOPES
                    and all(substantive(value, 15) for value in scope.values()),
                    "Missing geography, interval, population or counting method")
            for name in ("reporting_chain", "supporting_findings",
                         "counterevidence_findings", "limitations"):
                require(substantive(follow[name], 60),
                        "Promising source follow-up lacks substantive " + name)
            if follow["disposition"] == "ready_for_v10_source_review":
                require(bool(ids) and bool(follow["upstream_source_urls"]),
                        "Promising admitted evidence needs original upstream support")
            else:
                require(not ids, "Held or contradicted promising lead cannot admit claims")
        for ident in ids:
            require(ident not in by_claim, "Claim admitted from multiple promising leads")
            by_claim[ident] = url
        by_url[url] = lead
    require(set(by_url) == allowed,
            "Missing source triage or follow-up for selected original URL")
    originals = {row["id"]: row["source"] for row in new_evidence}
    require(len(originals) == len(new_evidence) and originals == by_claim,
            "Every admitted new claim requires matching completed promising follow-up")
    return by_url


def validate_followup_reviews(response, register_by_url, role):
    """Both source-review perspectives must ratify EVERY triage and lead."""
    reviews = response.get("promising_followup_reviews")
    require(isinstance(reviews, list) and len(reviews) == len(register_by_url),
            role + " must review every promising-source triage and disposition")
    found = {}
    for review in reviews:
        require(isinstance(review, dict) and set(review) == REVIEW_FIELDS,
                role + " has malformed promising-evidence review")
        url = review["source_url"]
        require(isinstance(url, str) and url in register_by_url
                and url not in found,
                role + " has duplicated or unlisted promising-lead review")
        lead = register_by_url[url]
        disposition = (lead["followup"]["disposition"]
                       if lead["triage"] == "promising" else lead["triage"])
        require(review["triage"] == lead["triage"]
                and review["disposition"] == disposition
                and review["lead_sha256"] == digest(lead),
                role + " review detached from frozen promising-lead research")
        require(review["approved"] is True and review["issues"] == []
                and substantive(review["assessment"], 65)
                and substantive(review["limitations"], 60),
                role + " did not substantively approve promising-lead disposition")
        found[url] = review
    require(set(found) == set(register_by_url),
            role + " omits promising/context/excluded lead decisions")
    return found
