"""Closed-snapshot source-eligibility gate, independent of model opinions.

Quoted background is never directional evidence. Under the conservative
correction policy, observations can only be removed or weakened; no new
source, impact direction, publisher or evidentiary status may appear.
Hence failure of a minimum count or directional category is irreversible
until a NEW dated six-category source-research snapshot is created.
"""
from source_claim_narrowing import LIMITED_STATUS

DIRECTIONS = frozenset(("raises", "lowers", "ambiguous"))
MIN_OBSERVATIONS = 6
MIN_PUBLISHERS = 3
MIN_NEW_OBSERVATIONS = 4


def require(value, why):
    if not value:
        raise ValueError(why)


def eligibility(packet):
    """Return exact, independently recomputed monotone acceptance blockers.

    Raw source quotes and carried editorial context are retained for
    reproducibility, but never count as observations in any direction.
    A candidate count does not certify source truth: both independent
    reviewers and the separate passage controls remain mandatory.
    """
    require(isinstance(packet, dict), "Malformed closed source packet")
    entries = packet.get("evidence")
    background = packet.get("background_quotes", [])
    require(isinstance(entries, list) and isinstance(background, list),
            "Missing or malformed directional/background evidence lists")
    require(all(isinstance(x, dict) and isinstance(x.get("id"), str)
                for x in entries + background),
            "Malformed closed source evidence identifiers")
    active = [x for x in entries
              if x.get("editorial_support_status") != LIMITED_STATUS]
    legacy_background = [x for x in entries
                         if x.get("editorial_support_status") == LIMITED_STATUS]
    require(len({x["id"] for x in entries + background}) ==
            len(entries + background),
            "Evidence/background ID duplicated or reused")
    if packet.get("quote_separation_version") == 2:
        require(not legacy_background,
                "Quote-only context improperly retained as directional evidence")
        require(all(x.get("editorial_support_status") == LIMITED_STATUS and
                    x.get("editorial_role") == "background_source_quote" and
                    x.get("editorial_directional_admissible") is False
                    for x in background),
                "Background quote was promoted to directional evidence")
    real_publishers = {
        x["publisher"] for x in active
        if isinstance(x.get("publisher"), str) and x["publisher"].strip()
    }
    directions = {x.get("direction") for x in active}
    missing = sorted(DIRECTIONS - directions)
    count_new = sum(x.get("evidence_status") == "new" for x in active)
    failures = []
    if len(active) < MIN_OBSERVATIONS:
        failures.append("fewer_than_six_source_observations")
    if len(real_publishers) < MIN_PUBLISHERS:
        failures.append("fewer_than_three_distinct_publishers")
    if missing:
        failures.append("missing_required_directional_balance")
    if count_new < MIN_NEW_OBSERVATIONS:
        failures.append("fewer_than_four_new_observations")
    return {
        "version": 1,
        "directional_evidence_ids": [x["id"] for x in active],
        "background_quote_ids": [x["id"] for x in legacy_background + background],
        "directional_observations": len(active),
        "new_directional_observations": count_new,
        "distinct_directional_publishers": len(real_publishers),
        "present_directions": sorted(directions & DIRECTIONS),
        "missing_directions": missing,
        "failures": failures,
        "irreversible_under_closed_source_corrections": bool(failures),
        "recovery": ("REQUIRES_NEW_DATED_SOURCE_RESEARCH" if failures else
                     "CONTINUE_ALTERNATING_SOURCE_REVIEWS"),
        "publication": "NOT AUTHORIZED",
    }
