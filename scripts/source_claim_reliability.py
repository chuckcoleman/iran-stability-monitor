"""Prospective claim-specific factual reliability, separate from stability effects.

A deterministic, conservative ordinal rubric. No outlet gets a grade from its
name, URL count, or a model's unsupported self-assessment. Exact passage
witnesses establish source binding only, not the truth of a claim.

Only V10 and later reviews call this module. All historical records, reviewer
responses, original article bytes and prior grades remain immutable.
"""
from source_metadata import url_key

GRADES = ("Low", "Medium", "Medium-high", "High")
QUALITY = frozenset((
    "documented_original_method",
    "attributed_edited_original",
    "weak_or_unknown_source",
))
DIRECTNESS = frozenset((
    "primary_measurement_or_document",
    "firsthand_original_reporting",
    "attributed_claim",
    "analysis_or_unknown",
))
CONTRADICTIONS = frozenset((
    "material_unresolved", "addressed_with_qualification", "none_identified",
))
DIRECTION_CONFIDENCE = frozenset((
    "unverified", "qualified", "supported_from_evidence",
))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def reliability_from_factors(quality, directness, *,
                             confirmed_independent=False,
                             contradiction="none_identified",
                             exact_original_passage=False):
    """Reproducible ceiling based on actual witnessed claims and review factors.

    'High' requires an original primary document/measurement with documented
    method AND specifically corroborated genuinely independent original
    evidence, confirmed by BOTH reviewer perspectives. An uncorroborated
    transparent primary document can reach 'Medium-high' without a quota.
    No merely published headline or repeated wire counts as confirmation.
    """
    require(quality in QUALITY and directness in DIRECTNESS,
            "Unsupported reliability source-quality or directness category")
    require(contradiction in CONTRADICTIONS,
            "Unsupported material-contradiction classification")
    require(type(confirmed_independent) is bool
            and type(exact_original_passage) is bool,
            "Reliability witness indicators must be boolean")
    if not exact_original_passage or contradiction == "material_unresolved":
        return "Low"
    if (quality == "weak_or_unknown_source"
            or directness == "analysis_or_unknown"):
        return "Low"
    if directness == "attributed_claim":
        return "Medium" if contradiction == "none_identified" else "Low"
    if contradiction == "addressed_with_qualification":
        return "Medium"
    if (quality == "documented_original_method"
            and directness == "primary_measurement_or_document"):
        return "High" if confirmed_independent else "Medium-high"
    if (quality == "attributed_edited_original"
            and directness == "firsthand_original_reporting"):
        return "Medium-high" if confirmed_independent else "Medium"
    # A first-hand account from an inadequately documented institution, or
    # a declared primary method without documented methodological support,
    # cannot be upgraded merely by citing another URL.
    return "Medium"


def assess_review_claims(packet, role, reviewer_response):
    """Validate one reviewer's exact claim-level grades and actual corroborators.

    Raises on missing or invented IDs, same-publisher 'independence',
    unsupported witness or internally inconsistent source factors. Reviewer
    assertions remain explicitly attributed, not mechanically certified truth.
    """
    require(role in ("affirmative", "critical"), "Unknown reliability review role")
    require(isinstance(packet, dict) and isinstance(reviewer_response, dict),
            "Malformed claim reliability review")
    evidence = packet.get("evidence")
    decisions = packet.get("pre_review_claim_decisions")
    sources = packet.get("source_quality_audit", {}).get("sources")
    result = reviewer_response.get("claim_reliability_reviews")
    require(all(isinstance(x, list) for x in (evidence, decisions, sources, result)),
            role + " must return original-source claim reliability reviews")
    ids = [x["id"] for x in evidence]
    require(len(set(ids)) == len(ids)
            and len(result) == len(ids),
            role + " claim reliability review does not match admitted evidence")
    by_id = {x["id"]: x for x in evidence}
    original = {x["id"]: x for x in decisions}
    by_source = {x["url"]: x for x in sources}
    require(set(by_id).issubset(original) and
            len(by_source) == len(sources),
            "Claim reliability provenance lacks unique original source IDs")
    observed = {}
    for row in result:
        require(isinstance(row, dict), "Malformed claim reliability row")
        ident = row.get("evidence_id")
        require(ident in by_id and ident not in observed,
                role + " reliability review has unknown or duplicated ID")
        item = by_id[ident]
        entry = original[ident]
        key = url_key(item.get("source"))
        source = by_source.get(key)
        require(isinstance(source, dict)
                and row.get("original_url") == key
                and entry.get("original_url") == key,
                role + " claim reliability URL not bound to original")
        quality = row.get("source_quality")
        direct = row.get("directness")
        conflict = row.get("contradiction_status")
        # The model's asserted quality cannot override the original
        # category or reporting-chain provenance. Method documentation
        # remains a reviewable claim, not something a source's name proves.
        if (quality == "documented_original_method"):
            require(source.get("classification") == "direct_observation"
                    and source.get("origin") in (
                        "original_reporting", "official_or_advocacy_claim"),
                    role + " documented method is unsupported by source class")
        if (quality == "attributed_edited_original"):
            require(source.get("origin") == "original_reporting"
                    and source.get("classification") in (
                        "direct_observation", "attributed_claim"),
                    role + " edited original claim lacks original reporting")
        if direct == "primary_measurement_or_document":
            require(source.get("classification") == "direct_observation",
                    role + " primary observation must be source-classified "
                           "as a direct observation")
        if direct == "firsthand_original_reporting":
            require(source.get("origin") == "original_reporting",
                    role + " first-hand claim needs original reporting")
        direction = row.get("direction_confidence")
        require(quality in QUALITY and direct in DIRECTNESS and
                conflict in CONTRADICTIONS and
                direction in DIRECTION_CONFIDENCE,
                role + " returned invalid reliability dimensions")
        for field in ("source_quality_assessment",
                      "corroboration_assessment",
                      "contradiction_assessment"):
            require(isinstance(row.get(field), str)
                    and len(row[field].strip()) >= 60,
                    role + " claim reliability needs substantive " + field)
        confirms = row.get("independent_confirmation_ids")
        require(isinstance(confirms, list) and
                len(confirms) == len(set(confirms))
                and all(isinstance(x, str) and x in by_id and x != ident
                        for x in confirms),
                role + " supplied ungrounded independent confirmation IDs")
        passage = (entry.get("passage_status") ==
                   "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED"
                   and bool(entry.get("source_body_sha256"))
                   and bool(entry.get("original_passage"))
                   and entry.get("decision") ==
                       "PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW")
        require(row.get("exact_passage_witness") is passage,
                role + " reliability witness flag contradicts saved passage")
        # A reviewer's corroboration references may only name OTHER admitted
        # observations, each with its own exact original body passage, a
        # distinct ORIGINAL publisher, and no shared source/publisher lineage.
        publisher = item.get("publisher")
        for corroborator in confirms:
            other = by_id[corroborator]
            other_entry = original[corroborator]
            other_source = by_source.get(url_key(other.get("source")), {})
            require(bool(publisher) and bool(other.get("publisher"))
                    and publisher.casefold().strip() !=
                        other["publisher"].casefold().strip()
                    and url_key(item.get("source")) !=
                        url_key(other.get("source"))
                    and other_entry.get("passage_status") ==
                        "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED"
                    and bool(other_entry.get("source_body_sha256"))
                    and bool(other_entry.get("original_passage"))
                    and other_entry.get("decision") ==
                        "PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW"
                    and source.get("origin") == "original_reporting"
                    and other_source.get("origin") == "original_reporting"
                    and other_source.get("classification") not in (
                        "unverified", "analysis", "background_only"),
                    role + " called an unverified, repeated or uninspected "
                    "source an independent confirmation")
        require(not confirms or
                source.get("origin") == "original_reporting",
                role + " primary corroboration must be original reporting")
        # Corroboration is claim-specific, not a vote by distinct URLs:
        # reviewers must support it with a separate substantive comparison.
        require(not confirms or
                row.get("claim_match_independently_reviewed") is True,
                role + " independent claim agreement was not reviewed")
        # Qualitative grade cannot silently trump source status or unresolved
        # contradiction. Proposed higher grades cause validation failure.
        factual = reliability_from_factors(
            quality, direct,
            confirmed_independent=bool(confirms),
            contradiction=conflict,
            exact_original_passage=passage)
        require(row.get("factual_reliability") == factual,
                role + " reliability grade contradicts documented factors")
        # Separate geopolitical effect: even an excellent factual report
        # might be ambiguous or have an unverified causal implication.
        observed[ident] = {
            "evidence_id": ident, "original_url": key,
            "factual_reliability": factual,
            "stability_direction_confidence": direction,
            "quality": quality, "directness": direct,
            "contradiction_status": conflict,
            "independent_confirmation_ids": sorted(confirms),
            "exact_passage_witness": passage,
            "reviewer": role,
            "reviewer_judgment_not_independent_fact_verification": True,
        }
    require(set(observed) == set(ids), "Missing admitted claim reliability review")
    return [observed[ident] for ident in ids]


def reconcile_dual_reliability(packet, affirmative, critical):
    """Conservative ordinal agreement; never upgrade a reviewer disagreement."""
    first = assess_review_claims(packet, "affirmative", affirmative)
    second = assess_review_claims(packet, "critical", critical)
    output = []
    for a, b in zip(first, second):
        require(a["evidence_id"] == b["evidence_id"],
                "Review perspectives used different evidence ID order")
        independent = sorted(set(a["independent_confirmation_ids"]) &
                             set(b["independent_confirmation_ids"]))
        # Use the LESS confident factual grade. If the reviewers cited
        # DIFFERENT purported confirmers, the shared claim is uncorroborated:
        # independently documented primary evidence can still be Medium-high
        # without a mandatory confirmation quota, but it cannot be High.
        rating = GRADES[min(GRADES.index(a["factual_reliability"]),
                            GRADES.index(b["factual_reliability"]))]
        if not independent:
            rating = GRADES[min(GRADES.index(rating),
                                min(GRADES.index(
                                    reliability_from_factors(
                                        row["quality"], row["directness"],
                                        exact_original_passage=
                                            row["exact_passage_witness"],
                                        contradiction=row["contradiction_status"],
                                        confirmed_independent=False))
                                    for row in (a, b)))]
        direction = ("unverified" if "unverified" in (
            a["stability_direction_confidence"],
            b["stability_direction_confidence"])
            else "qualified" if "qualified" in (
                a["stability_direction_confidence"],
                b["stability_direction_confidence"])
            else "supported_from_evidence")
        output.append({
            "evidence_id": a["evidence_id"],
            "factual_reliability": rating,
            "stability_direction_confidence": direction,
            "independently_confirmed_claim_ids": independent,
            "affirmative_original_grade": a["factual_reliability"],
            "critical_original_grade": b["factual_reliability"],
            "source_confidence_not_geopolitical_effect": True,
            "review_status": "TWO_PERSPECTIVES_NOT_INDEPENDENT_MODEL_INSTANCES",
            "publication": "NOT AUTHORIZED",
        })
    return output


def apply_reviewed_reliability(current, original_frozen, certificate):
    """Only update NEW claims in a prospective forecast with dual-reviewed grades.

    Original source/event identity, stable evidence IDs, directions and
    carried-forward historical grades are preserved without modification.
    Excluded unreviewed new claims can never silently enter the forecast.
    The dual certificate is saved separately before forecast elicitation.
    """
    import copy

    require(isinstance(current, list) and
            isinstance(original_frozen, list) and
            isinstance(certificate, list),
            "Malformed prospective reliability inputs")
    original = {row["id"]: row for row in original_frozen}
    require(len(original) == len(original_frozen),
            "Duplicated original evidence identity")
    cert = {}
    for row in certificate:
        require(isinstance(row, dict) and
                isinstance(row.get("evidence_id"), str)
                and row["evidence_id"] not in cert,
                "Duplicated or malformed claim reliability certificate")
        ident = row["evidence_id"]
        require(ident in original
                and original[ident].get("evidence_status") == "new"
                and row.get("factual_reliability") in GRADES
                and row.get("source_confidence_not_geopolitical_effect") is True
                and row.get("review_status") ==
                    "TWO_PERSPECTIVES_NOT_INDEPENDENT_MODEL_INSTANCES",
                "Prospective grade has no corresponding dual-reviewed NEW claim")
        cert[ident] = row
    accepted = {row["id"] for row in current
                if row.get("evidence_status") == "new"}
    require(accepted == set(cert), "Unreviewed new evidence or unmatched grade")
    require(len({row["id"] for row in current}) == len(current),
            "Duplicated final evidence identity")
    final = []
    for entry in current:
        ident = entry["id"]
        require(ident in original, "New evidence appeared after source freeze")
        old = original[ident]
        require(entry == old, "Source review altered a frozen observation "
                              "instead of excluding or separately grading it")
        amended = copy.deepcopy(entry)
        if entry.get("evidence_status") == "new":
            amended["reliability"] = cert[ident]["factual_reliability"]
            # Do not replace direction=raises/lowers/ambiguous with a
            # factual truth grade or treat reliability as an effect magnitude.
            amended["reliability_basis"] = (
                "two_perspective_claim_specific_conservative_fact_review")
            amended["geopolitical_direction_confidence"] = cert[ident][
                "stability_direction_confidence"]
        final.append(amended)
    return final
