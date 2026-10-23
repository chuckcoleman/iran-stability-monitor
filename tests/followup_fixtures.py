"""Explicitly fictional V10 promising-follow-up entries for offline tests only."""
import datetime as dt

from review_receipt import digest


def attach_followup(packet, cutoff, affirmative, critical):
    """Attach one full triage per test source and two distinct reviews."""
    checked_at = (dt.datetime.fromisoformat(cutoff)
                  - dt.timedelta(minutes=1)).isoformat()
    leads = []
    for source in packet["source_quality_audit"]["sources"]:
        url = source["url"]
        ids = [e["id"] for e in packet["evidence"] if e["source"] == url]
        if ids:
            followup = {
                "performed_at": checked_at,
                "disposition": "ready_for_v10_source_review",
                "upstream_queries": [
                    "Locate the original fictional measurement and exact methodology for " + url],
                "counter_queries": [
                    "Find contradictory fictional observations and stabilizing alternatives for " + url],
                "checked_urls": [url], "upstream_source_urls": [url],
                "contrary_source_urls": [],
                "scope": {
                    "geography": "Synthetic geographic area; no real national coverage asserted",
                    "time_window": "Fictional period before the frozen test-only cutoff",
                    "population_or_denominator": "Invented measurement universe used for unit tests only",
                    "method_and_inclusions": "Local generated HTML with a documented synthetic passage",
                },
                "reporting_chain": (
                    "A single entirely synthetic primary document supplies this "
                    "fictional claim; no independent real-world corroborator exists."),
                "supporting_findings": (
                    "The test-only source HTML contains the exact made-up claim "
                    "and a captured synthetic passage for software validation."),
                "counterevidence_findings": (
                    "The synthetic counterevidence query does not establish "
                    "real-world contrary reporting or any absence of risk."),
                "limitations": (
                    "All queries and underlying measurements are deliberately "
                    "fictional; this test fixture must never authorize a forecast."),
            }
            triage = "promising"
        else:
            followup = None
            triage = "context_only"
        leads.append({
            "source_url": url,
            "triage": triage,
            "priority": "normal",
            "relevance": (
                "This source is examined for potential significance to the "
                "synthetic assessment, without asserting an actual event."),
            "admitted_evidence_ids": ids,
            "followup": followup,
        })
    packet["promising_evidence_followup"] = {
        "version": 1, "research_as_of": cutoff, "leads": leads,
    }
    for name, review in (("affirmative", affirmative), ("critical", critical)):
        review["promising_followup_reviews"] = []
        for lead in leads:
            disposition = (lead["followup"]["disposition"]
                           if lead["followup"] is not None else lead["triage"])
            review["promising_followup_reviews"].append({
                "source_url": lead["source_url"],
                "triage": lead["triage"],
                "disposition": disposition,
                "lead_sha256": digest(lead),
                "approved": True,
                "issues": [],
                "assessment": (
                    ("Affirmative review confirmed the synthetic working register "
                     "matches the cited source identity and recorded inquiry. ")
                    if name == "affirmative" else
                    ("Critical review challenged the alleged original access, "
                     "scope, independent reporting and contrary material. ")
                ) + lead["source_url"],
                "limitations": (
                    "All promising follow-up rows are simulated, and cannot "
                    "authenticate publisher content or independent searches."),
            })
    return packet["promising_evidence_followup"]
