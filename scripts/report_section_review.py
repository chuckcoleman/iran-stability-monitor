"""Coverage manifest for two-perspective reviews of every report component.

This is a structural fail-closed receipt guard, not proof that AI reasoning,
web searches, deterministic tests or independent human review actually ran.
No report content or frozen forecasting Protocol v1 is changed here.
"""
from collections import OrderedDict

# Every top-level item other than the actual post-review issuance timestamp
# is assigned to precisely one report section. New fields require a reviewed
# mapping change rather than silently escaping affirmative/critical scrutiny.
REPORT_SECTIONS = OrderedDict((
    ("source_search_and_provenance", (
        "evidence", "evidence_cutoff", "assessment_evidence_cutoff")),
    ("new_events_and_news", (
        "news", "what_changed")),
    ("four_scored_forecasts", ("forecasts",)),
    ("revision_calibration_and_attribution", (
        "revision_attribution", "revision_attribution_status")),
    ("nine_warning_indicators", ("warning",)),
    ("political_and_regional_scenarios", (
        "regional", "political", "binary_political",
        "regional_resolution_note", "political_resolution_note")),
    ("causal_chains_and_absence_indicators", (
        "chains", "absence_indicators")),
    ("hormuz_energy_elites_and_coercion", ("conditions",)),
    ("houthi_support_and_independent_capability", ("houthi",)),
    ("oil_credit_sanctions_and_payment_mechanisms", ("haircut",)),
    ("inflation_and_humanitarian_diagnostics", ("hanke_hyperinflation",)),
    ("dashboard_metrics_tables_and_statuses", ("metrics", "status")),
    ("narratives_stabilizers_and_thresholds", (
        "summary", "stabilizer", "next_threshold", "limitations")),
    ("publication_copy_and_schedule", (
        "social_summary", "next_scheduled_update")),
    ("methods_integrity_and_corrections", (
        "date", "protocol_version", "protocol_version_for_assessment",
        "methodology_revision_date", "methodology_notes", "corrections")),
))
SOURCE_CLASSES = (
    "primary_data", "international_media", "regional_multilingual_media",
    "specialist_investigative", "think_tanks",
    "economic_humanitarian_academic",
)


def report_inventory(record):
    """Derive a per-section named item list from the EXACT reviewed record.

    Include top-level fields AND independently important nested entries. A
    section review may not omit one forecast, event, scenario, warning or metric.
    """
    if not isinstance(record, dict):
        raise ValueError("Reviewed report record is missing")
    assigned = [f for fields in REPORT_SECTIONS.values() for f in fields]
    if len(set(assigned)) != len(assigned):
        raise ValueError("Report field belongs to multiple review sections")
    if set(assigned) != set(record) - {"publication_time"}:
        missing = sorted(set(record) - set(assigned) - {"publication_time"})
        extra = sorted(set(assigned) - set(record))
        raise ValueError("Unreviewed or missing report fields: " + repr((missing, extra)))
    result = {}
    for section, fields in REPORT_SECTIONS.items():
        items = ["field:" + name for name in fields]
        for field in fields:
            value = record[field]
            if field == "evidence" and isinstance(value, list):
                items += ["evidence:" + str(row["id"]) for row in value]
            elif field == "news" and isinstance(value, list):
                items += ["news:" + str(i) + ":" + str(row.get("url", ""))
                          for i, row in enumerate(value)]
            elif field in ("forecasts", "revision_attribution", "binary_political"):
                items += [field + ":" + str(row["event_id"]) for row in value]
            elif field in ("regional", "political", "chains"):
                items += [field + ":" + str(row["name"]) for row in value]
            elif field == "absence_indicators":
                items += [field + ":" + str(row["label"]) for row in value]
            elif field in ("metrics", "status", "warning", "conditions", "houthi"):
                items += [field + ":" + str(key) for key in sorted(value)]
            elif field == "haircut":
                items += ["haircut:" + str(key) for key in sorted(value)]
                components = value.get("calculation", {}).get("components", [])
                items += ["haircut_component:" + str(row[0]) for row in components]
            elif field == "hanke_hyperinflation":
                items += ["hanke:" + str(key) for key in sorted(value)]
                probs = value.get("hyperinflation_probability", {})
                if isinstance(probs, dict):
                    items += ["hanke_probability:" + str(k) for k in sorted(probs)]
            elif field == "methodology_notes" and isinstance(value, list):
                items += ["methodology_note:" + str(i) for i in range(len(value))]
            elif field == "corrections" and isinstance(value, list):
                items += ["correction:" + str(i) for i in range(len(value))]
        if section == "source_search_and_provenance":
            items += ["research_category:" + cat for cat in SOURCE_CLASSES]
        if len(items) != len(set(items)):
            raise ValueError("Duplicate report review item within " + section)
        result[section] = sorted(items)
    return result


def validate_report_section_reviews(section_reviews, record, draft_hash,
                                    final_round=True, role_approvals=None):
    """Require affirmative AND critical explicit checks for every section.

    For the final round, compare item-by-item with the actual published-draft
    inventory; for prior rejected rounds the earlier draft may not be stored,
    so require nonempty declarations tied to the prior draft SHA instead.
    """
    required = report_inventory(record) if final_round else None
    if not isinstance(section_reviews, dict) or set(section_reviews) != set(REPORT_SECTIONS):
        raise ValueError("Every report section needs both review perspectives")
    failed_by_role = {"affirmative": 0, "critical": 0}
    for section in REPORT_SECTIONS:
        item = section_reviews[section]
        if not isinstance(item, dict) or set(item) != {"items", "affirmative", "critical"}:
            raise ValueError("Malformed report section review: " + section)
        inventory = item["items"]
        if not isinstance(inventory, list) or not inventory or len(inventory) != len(set(inventory)):
            raise ValueError("Missing or repeated reviewed report items: " + section)
        if not all(isinstance(x, str) and x for x in inventory):
            raise ValueError("Invalid reviewed report item: " + section)
        if final_round and inventory != required[section]:
            raise ValueError("Unreviewed or mismatched report items: " + section)
        for role in ("affirmative", "critical"):
            decision = item[role]
            if not isinstance(decision, dict):
                raise ValueError(role + " report section review missing: " + section)
            approved = decision.get("approved")
            issues = decision.get("issues")
            note = decision.get("test_note")
            if (decision.get("draft_sha256") != draft_hash
                or type(approved) is not bool
                or not isinstance(issues, list)
                or any(not isinstance(x, str) or not x.strip() for x in issues)
                or not isinstance(note, str) or len(note.strip()) < 25):
                raise ValueError(role + " report section test incomplete: " + section)
            if approved != (len(issues) == 0):
                raise ValueError(role + " report section verdict inconsistent: " + section)
            if not approved:
                failed_by_role[role] += 1
    if role_approvals is not None:
        for role in ("affirmative", "critical"):
            if role_approvals[role] != (failed_by_role[role] == 0):
                raise ValueError(role + " global/section review verdict inconsistent")
    return True
