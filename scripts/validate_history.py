#!/usr/bin/env python3
"""Validate Iran Stability Monitor history against frozen Protocol v1.

Run: python scripts/validate_history.py
Tests: python -m unittest discover -s tests -v
Requires IANA timezone data (on Windows: pip install tzdata).
"""
import argparse
import datetime as _dt
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HISTORY_PATH = Path("data/history.json")
LOCAL_ZONE = "America/New_York"
PROTOCOL_EFFECTIVE_DATE = _dt.date(2026, 10, 4)
ALLOWED_OUTCOMES = frozenset({"Yes", "No", "indeterminate"})
CORE_EVENTS = frozenset({
    "regional_escalation_90d", "regime_end_12m",
    "currency_crisis_12m", "external_payments_crisis_12m",
})
WARNING_LEVELS = frozenset({"normal", "watch", "warning-level", "critical", "unknown"})
DIRECTIONS = frozenset({"up", "flat", "down", "unknown"})
RESOLUTION_FIELDS = frozenset({
    "outcome", "resolution", "resolution_date", "resolution_note",
    "resolution_evidence", "resolution_status", "resolved_at",
})


class ValidationError(ValueError):
    """An invariant violation that must block publication."""


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def warn(message):
    print("VALIDATION WARNING:", message)


def parse_timestamp(value, label):
    require(isinstance(value, str) and value.strip(), f"{label}: missing timestamp")
    try:
        stamp = _dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{label}: invalid ISO timestamp {value!r}") from exc
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
            f"{label}: timestamp must have an explicit UTC offset")
    return stamp


def parse_date(value, label):
    require(isinstance(value, str), f"{label}: date must be YYYY-MM-DD")
    try:
        day = _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"{label}: invalid calendar date {value!r}") from exc
    require(day.isoformat() == value, f"{label}: date must be YYYY-MM-DD")
    return day


def local_zone():
    try:
        return ZoneInfo(LOCAL_ZONE)
    except ZoneInfoNotFoundError as exc:
        raise ValidationError(f"No IANA time-zone data for {LOCAL_ZONE}; install tzdata") from exc


def check_eastern_offset(stamp, zone, label):
    """Validate Eastern UTC offset and reject nonexistent spring-forward wall times.

    At fall-back, either valid offset is accepted when specified explicitly.
    """
    wall = stamp.replace(tzinfo=None)
    for fold in (0, 1):
        candidate = wall.replace(tzinfo=zone, fold=fold)
        roundtrip = candidate.astimezone(_dt.timezone.utc).astimezone(zone)
        if (candidate.utcoffset() == stamp.utcoffset()
                and roundtrip.replace(tzinfo=None) == wall):
            return
    raise ValidationError(
        f"{label}: UTC offset does not match {LOCAL_ZONE} at this local time, "
        "or the time is nonexistent because of a DST transition"
    )


def check_probability(value, label):
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100,
            f"{label}: probability must be a finite number from 0 to 100")


def check_numbers(forecast, label):
    if "p" in forecast:
        check_probability(forecast["p"], label)
    if "range" in forecast:
        bounds = forecast["range"]
        require(isinstance(bounds, list) and len(bounds) == 2,
                f"{label}: range must contain exactly two endpoints")
        for point in bounds:
            check_probability(point, f"{label}: range endpoint")
        require("p" in forecast and bounds[0] <= forecast["p"] <= bounds[1],
                f"{label}: uncertainty range must contain point probability")


def expected_deadline(opening, event_id):
    if event_id == "regional_escalation_90d":
        day = opening.date() + _dt.timedelta(days=90)
    else:
        try:
            day = opening.date().replace(year=opening.year + 1)
        except ValueError:
            day = opening.date().replace(year=opening.year + 1, day=28)
    return _dt.datetime.combine(day, opening.time().replace(tzinfo=None))


def validate_resolution(forecast, label):
    """Validate optional resolution additions without modifying issued forecasts."""
    fields = set(forecast) & RESOLUTION_FIELDS
    if not fields:
        return
    unsupported = fields - {
        "outcome", "resolution_date", "resolution_note",
        "resolution_evidence", "resolved_at"
    }
    require(not unsupported,
            f"{label}: unsupported resolution fields: {sorted(unsupported)}")
    for key in ("outcome", "resolution_date", "resolution_note", "resolution_evidence"):
        require(key in forecast, f"{label}: resolution missing {key}")
    require(forecast["outcome"] in ALLOWED_OUTCOMES,
            f"{label}: outcome must be Yes, No, or indeterminate")
    resolution_day = parse_date(forecast["resolution_date"],
                                f"{label}: resolution_date")
    deadline = parse_timestamp(forecast["resolution_deadline"],
                               f"{label}: resolution_deadline")
    require(resolution_day >= deadline.date(),
            f"{label}: resolution_date precedes forecast deadline")
    require(isinstance(forecast["resolution_note"], str)
            and forecast["resolution_note"].strip(),
            f"{label}: resolution_note must explain the outcome")
    evidence = forecast["resolution_evidence"]
    require(isinstance(evidence, list) and evidence,
            f"{label}: resolution_evidence must be a nonempty list")
    for citation in evidence:
        require(isinstance(citation, str) and citation.strip(),
                f"{label}: resolution_evidence entries must be nonempty citations")
    if "resolved_at" in forecast:
        reviewed = parse_timestamp(forecast["resolved_at"],
                                   f"{label}: resolved_at")
        require(reviewed >= deadline,
                f"{label}: resolved_at precedes forecast deadline")
        require(reviewed.date() == resolution_day,
                f"{label}: resolved_at differs from resolution_date")


def validate_protocol_record(update, protocol, zone):
    date = update["date"]
    for field in ("evidence_cutoff", "publication_time", "forecasts", "warning", "evidence"):
        require(field in update, f"{date}: missing {field}")

    cutoff = parse_timestamp(update["evidence_cutoff"], f"{date}: evidence_cutoff")
    publication = parse_timestamp(update["publication_time"], f"{date}: publication_time")
    # Evidence cutoff and publication can be expressed in UTC or any explicit offset.
    # Forecast opening and deadline must preserve the Eastern local clock.
    require(cutoff <= publication, f"{date}: evidence_cutoff after publication_time")
    require(isinstance(update["forecasts"], list), f"{date}: forecasts must be an array")
    core = [f for f in update["forecasts"] if f.get("scored") is True]
    ids = [f.get("event_id") for f in core]
    require(len(core) == len(CORE_EVENTS) and set(ids) == CORE_EVENTS,
            f"{date}: exactly four distinct scored core forecasts required")
    definitions = {f["id"]: f["resolution"] for f in protocol["core_scored_set"]}
    require(set(definitions) == CORE_EVENTS, "Frozen protocol core event IDs differ")

    for forecast in core:
        event_id = forecast["event_id"]
        label = f"{date}: {event_id}"
        for key in ("forecast_id", "created_date", "forecast_open",
                    "resolution_deadline", "p", "range", "confidence", "event_definition"):
            require(key in forecast, f"{label}: missing {key}")
        require(forecast["forecast_id"] == f"{event_id}_{date.replace('-', '')}",
                f"{label}: forecast_id format mismatch")
        require(forecast["created_date"] == date, f"{label}: wrong created_date")
        require(forecast["event_definition"] == definitions[event_id],
                f"{label}: event definition differs from frozen Protocol v1")
        check_numbers(forecast, label)
        opening = parse_timestamp(forecast["forecast_open"], f"{label}: forecast_open")
        deadline = parse_timestamp(forecast["resolution_deadline"], f"{label}: resolution_deadline")
        check_eastern_offset(opening, zone, f"{label}: forecast_open")
        check_eastern_offset(deadline, zone, f"{label}: resolution_deadline")
        require(opening.date() == parse_date(date, f"{date}: assessment date"),
                f"{label}: forecast_open local date differs from assessment date")
        # EACH forecast must meet the time ordering, not merely the earliest opening.
        require(cutoff <= opening <= publication,
                f"{label}: require evidence_cutoff <= forecast_open <= publication_time")
        require(deadline.replace(tzinfo=None) == expected_deadline(opening, event_id),
                f"{label}: resolution deadline local calendar date/time mismatch")
        require(deadline > opening, f"{label}: resolution deadline must follow opening")
        validate_resolution(forecast, label)

    if cutoff == publication and all(
            parse_timestamp(f["forecast_open"], "forecast_open") == cutoff for f in core):
        warn(f"{date}: cutoff, opening and publication timestamps coincide; "
             "original temporal provenance cannot be independently established from these fields")

    require(isinstance(update["warning"], dict), f"{date}: warning must be an object")
    require(set(update["warning"]) == set(protocol["warning_transition_rules"]),
            f"{date}: warning category mismatch")
    for category, state in update["warning"].items():
        require(isinstance(state, dict) and state.get("level") in WARNING_LEVELS,
                f"{date}: invalid warning level for {category}")
        require(state.get("direction") in DIRECTIONS,
                f"{date}: invalid warning direction for {category}")

    require(isinstance(update["evidence"], list), f"{date}: evidence must be an array")
    evidence_ids = set()
    for entry in update["evidence"]:
        require(isinstance(entry, dict), f"{date}: evidence entry must be an object")
        evidence_id = entry.get("id")
        require(isinstance(evidence_id, str) and evidence_id and evidence_id not in evidence_ids,
                f"{date}: missing/duplicate evidence ID {evidence_id!r}")
        evidence_ids.add(evidence_id)
        for key in ("source", "reliability", "evidence_status", "direction", "impact_magnitude"):
            require(entry.get(key), f"{date}: evidence {evidence_id} missing {key}")
        published_at = entry.get("source_publication_time")
        if published_at is None or published_at == "":
            warn(f"{date}: evidence {evidence_id} lacks precise source_publication_time")
        else:
            published_at = parse_timestamp(published_at,
                                           f"{date}: evidence {evidence_id}: publication")
            require(published_at <= cutoff, f"{date}: post-cutoff evidence {evidence_id}")

    calc = update.get("haircut", {}).get("calculation")
    if calc:
        require(isinstance(calc.get("components"), list), f"{date}: invalid haircut components")
        raw = sum(row[1] for row in calc["components"])
        require(raw == calc["raw_sum"], f"{date}: haircut raw sum mismatch")
        affected = {"Physical delivery/blockade", "Sanctions/payment channels",
                    "Political/secondary-sanctions tail"}
        subtotal = sum(row[1] for row in calc["components"] if row[0] in affected)
        deduction = round(max(0, subtotal - 20) * .2)
        require(deduction == calc["overlap_deduction_20pct"]
                and raw - deduction == calc["adjusted_headline"],
                f"{date}: haircut overlap arithmetic mismatch")

    attributions = update.get("revision_attribution")
    require(isinstance(attributions, list) and len(attributions) == len(CORE_EVENTS),
            f"{date}: exactly four core revision-attribution records required")
    points = {f["event_id"]: f["p"] for f in core}
    seen = set()
    for row in attributions:
        require(isinstance(row, dict), f"{date}: revision attribution must be an object")
        event_id = row.get("event_id")
        require(event_id in points and event_id not in seen,
                f"{date}: missing, repeated, or unknown revision event_id {event_id}")
        seen.add(event_id)
        check_probability(row.get("prior_p"), f"{date}: {event_id}: prior_p")
        check_probability(row.get("new_p"), f"{date}: {event_id}: new_p")
        require("residual_pp" in row, f"{date}: {event_id}: missing residual_pp")
        residual = row["residual_pp"]
        require(type(residual) in (int, float) and math.isfinite(residual),
                f"{date}: {event_id}: residual_pp must be finite")
        contributions = row.get("contributions", [])
        require(isinstance(contributions, list),
                f"{date}: {event_id}: contributions must be an array")
        total = row["prior_p"] + residual
        for contribution in contributions:
            require(isinstance(contribution, dict)
                    and isinstance(contribution.get("label"), str)
                    and contribution["label"].strip(),
                    f"{date}: {event_id}: contribution requires a label")
            pp = contribution.get("pp")
            require(type(pp) in (int, float) and math.isfinite(pp),
                    f"{date}: {event_id}: contribution pp must be finite")
            total += pp
        require(round(total, 8) == round(row["new_p"], 8),
                f"{date}: {event_id}: revision contributions do not reconcile")
        require(row["new_p"] == points[event_id],
                f"{date}: {event_id}: revision new_p differs from actual forecast")


def validate_consecutive_baselines(previous_update, current_update):
    """Require new revisions to start from the preceding Protocol-v1 forecast.

    The inaugural 2026-10-04 assessment retains its clearly labeled
    pre-v1/retrospective comparators without reclassifying them as scored.
    """
    earlier = {
        f["event_id"]: f["p"] for f in previous_update["forecasts"]
        if f.get("scored") is True
    }
    for row in current_update["revision_attribution"]:
        event_id = row["event_id"]
        require(event_id in earlier and row["prior_p"] == earlier[event_id],
                f"{current_update['date']}: {event_id}: prior_p differs "
                "from preceding prospective core forecast")


def check_history_immutability(previous, current):
    """Only append records, correction notes, or resolution metadata to archived history."""
    require(previous.get("protocol") == current.get("protocol"),
            "frozen Protocol v1 was modified; use a prospectively versioned protocol instead")
    require(set(current) == set(previous),
            "historical root structure was changed; use a separate documented schema migration")
    for key in previous:
        if key not in ("protocol", "updates"):
            require(previous[key] == current.get(key),
                    f"historical root metadata changed: {key}")
    before, after = previous.get("updates", []), current.get("updates", [])
    require(len(after) >= len(before), "historical updates were deleted")
    for index, old in enumerate(before):
        new = after[index]
        date = old.get("date", f"index {index}")
        require(new.get("date") == old.get("date"),
                f"historical updates reordered or deleted at {date}")
        frozen_keys = set(old) - {"corrections", "forecasts"}
        require(set(new) - {"corrections", "forecasts"} == frozen_keys,
                f"{date}: historical record fields added or removed")
        for key in frozen_keys:
            require(old[key] == new[key], f"{date}: unauthorized historical mutation of {key}")
        old_notes, new_notes = old.get("corrections", []), new.get("corrections", [])
        require(isinstance(old_notes, list) and isinstance(new_notes, list),
                f"{date}: corrections must be an array")
        require(new_notes[:len(old_notes)] == old_notes,
                f"{date}: previous corrections cannot be removed or edited")
        for correction in new_notes[len(old_notes):]:
            require(isinstance(correction, dict) and correction.get("date") and correction.get("reason"),
                    f"{date}: appended corrections require a date and reason")
        old_fc, new_fc = old.get("forecasts", []), new.get("forecasts", [])
        require(len(old_fc) == len(new_fc), f"{date}: historical forecasts added or removed")
        for previous_fc, current_fc in zip(old_fc, new_fc):
            issued_keys = set(previous_fc) - RESOLUTION_FIELDS
            require(set(current_fc) - RESOLUTION_FIELDS == issued_keys,
                    f"{date}: historical forecast fields changed")
            for key in issued_keys:
                require(previous_fc[key] == current_fc[key],
                        f"{date}: historical forecast {previous_fc.get('forecast_id', 'unidentified')}: "
                        f"unauthorized change to {key}")
            for key in set(previous_fc) & RESOLUTION_FIELDS:
                require(previous_fc[key] == current_fc.get(key),
                        f"{date}: existing resolution information was edited")


def validate_history(data, previous=None):
    require(isinstance(data, dict), "history root must be an object")
    require(type(data.get("schema_version")) is int and data["schema_version"] >= 3,
            "schema_version must be at least 3")
    protocol = data.get("protocol")
    require(isinstance(protocol, dict) and protocol.get("version") == "1.0",
            "unexpected protocol version")
    updates = data.get("updates")
    require(isinstance(updates, list) and updates, "no updates")
    zone = local_zone()
    require(protocol.get("effective_for_forecasts_on_or_after") in
            (None, PROTOCOL_EFFECTIVE_DATE.isoformat()),
            "frozen Protocol v1 effective date was changed")
    last_date = None
    previous_v1 = None
    forecast_ids = set()
    for index, update in enumerate(updates):
        require(isinstance(update, dict), f"updates[{index}] must be an object")
        date = parse_date(update.get("date"), f"updates[{index}] date")
        require(last_date is None or last_date < date,
                f"updates[{index}]: dates must be strictly increasing and unique")
        last_date = date
        require(isinstance(update.get("forecasts", []), list),
                f"{date}: forecasts must be an array")
        for forecast in update.get("forecasts", []):
            require(isinstance(forecast, dict), f"{date}: forecast must be an object")
            forecast_id = forecast.get("forecast_id")
            if forecast_id:
                require(forecast_id not in forecast_ids, f"duplicate forecast_id {forecast_id}")
                forecast_ids.add(forecast_id)
            check_numbers(forecast, f"{date}: {forecast_id or forecast.get('label', 'unidentified')}")
        if date >= PROTOCOL_EFFECTIVE_DATE:
            require(update.get("protocol_version") == "1.0",
                    f"{date}: missing/invalid protocol_version; Protocol v1 is mandatory "
                    "for all assessments from 2026-10-04 onward")
            validate_protocol_record(update, protocol, zone)
            if previous_v1 is not None:
                validate_consecutive_baselines(previous_v1, update)
            previous_v1 = update
        else:
            require(update.get("protocol_version") in (None, "pre-v1"),
                    f"{date}: Protocol v1 must not be retroactively applied")
    if previous is not None:
        check_history_immutability(previous, data)


def load_baseline_file(path):
    try:
        with open(path, encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read baseline file {path}: {exc}") from exc


def load_previous_history(base):
    if not base or base == "0" * 40:
        return None
    try:
        blob = subprocess.check_output(
            ["git", "show", f"{base}:{HISTORY_PATH.as_posix()}"],
            encoding="utf-8", stderr=subprocess.PIPE
        )
        return json.loads(blob)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot inspect historical baseline {base}: {exc}; "
                              "refusing to bypass immutability check") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    baselines = parser.add_mutually_exclusive_group()
    baselines.add_argument("--baseline", metavar="FILE",
                           help="prior history.json file for strict archival comparison")
    baselines.add_argument("--baseline-ref", metavar="GIT_REF",
                           help="Git revision containing prior data/history.json")
    args = parser.parse_args(argv)
    try:
        with HISTORY_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        base = args.baseline_ref or os.environ.get("GITHUB_EVENT_BEFORE")
        previous = (load_baseline_file(args.baseline) if args.baseline
                    else load_previous_history(base))
        if previous is None:
            warn("no historical baseline supplied; archival immutability not checked")
        validate_history(data, previous)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print("VALIDATION ERROR:", exc, file=sys.stderr)
        return 1
    print("VALIDATION OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
