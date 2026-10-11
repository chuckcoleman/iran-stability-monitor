"""Additional publication guards. These do not revise the frozen Protocol v1 rules."""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from source_metadata import url_key

ZONE = ZoneInfo("America/New_York")
CORE = ("regional_escalation_90d", "regime_end_12m", "currency_crisis_12m", "external_payments_crisis_12m")


def require(value, message):
    if not value:
        raise ValueError(message)


def finite(value, low=0, high=100):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def one_append(before, after):
    require(set(before) == set(after), "Root structure changed")
    require(all(before[k] == after[k] for k in before if k != "updates"), "Frozen root metadata changed")
    require(len(after["updates"]) == len(before["updates"]) + 1, "Exactly one appended record required")
    require(after["updates"][:-1] == before["updates"], "Historical record changed")


def safe_text(value):
    if isinstance(value, str):
        require(not re.search(r"<\s*(?:/?[a-zA-Z]|!|\?)", value), "Unsafe HTML in generated data")
        require("\x00" not in value and len(value) < 10000, "NUL or oversized generated data")
    elif isinstance(value, list):
        for item in value:
            safe_text(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            safe_text(key)
            safe_text(item)


def dashboard_record(u, previous):
    required = ("date", "summary", "metrics", "status", "forecasts", "regional", "political",
                "warning", "conditions", "haircut", "houthi", "chains", "absence_indicators",
                "news", "evidence", "what_changed", "stabilizer", "next_threshold", "limitations")
    require(all(k in u for k in required), "Missing JavaScript-facing data")
    safe_text(u)
    by_id = {f["event_id"]: f for f in u["forecasts"] if f.get("scored") is True}
    require(set(by_id) == set(CORE) and len(u["forecasts"]) == 4, "Core display mismatch")
    for key in CORE:
        require(u["metrics"][key] == by_id[key]["p"], "Dashboard/core probability mismatch")
    for key, event in (("regional", CORE[0]), ("political", CORE[1])):
        rows = u[key]
        names = [x["name"] for x in previous[key]]
        require(isinstance(rows, list) and [x.get("name") for x in rows] == names,
                "Legacy descriptive scenario names changed")
        require(all(finite(x.get("p")) for x in rows) and abs(sum(x["p"] for x in rows) - 100) < 1e-8,
                "Descriptive scenario probabilities must total 100")
        require(rows[-1]["p"] == by_id[event]["p"], "Descriptive/core event mismatch")
    for key in ("m6", "m24", "material_support_12m", "technical_financial_support_12m", "independent_capability_12m"):
        require(finite(u["houthi"].get(key)), "Invalid Houthi diagnostic: " + key)
    require(finite(u["metrics"].get("houthi_support_12m")), "Invalid headline Houthi diagnostic")
    r = u["haircut"].get("range")
    point = u["metrics"]["china_oil_credit_haircut"]
    require(isinstance(r, list) and len(r) == 2 and all(finite(x) for x in r) and r[0] <= point <= r[1],
            "Invalid oil-credit range")
    require(point == u["haircut"]["calculation"]["adjusted_headline"], "Oil-credit display mismatch")
    for key in ("chains", "absence_indicators", "news", "evidence"):
        require(isinstance(u[key], list), "Display array missing: " + key)
    for chain in u["chains"]:
        require(chain.get("level") in ("normal", "watch", "warning", "critical", "unknown"), "Unsafe chain class")
        steps = chain.get("steps")
        require(isinstance(steps, list) and steps and all(isinstance(x, str) for x in steps), "Invalid diagnostic steps")
        require(type(chain.get("confirmed")) is int and 0 <= chain["confirmed"] <= len(steps), "Invalid confirmed steps")
        require(type(chain.get("current")) is int and 0 <= chain["current"] < len(steps), "Invalid current step")
    for item in u["absence_indicators"]:
        require(item.get("status") in ("normal", "watch", "warning-level", "critical", "unknown"), "Unsafe absence class")
        require(all(isinstance(item.get(k), str) and item[k].strip() for k in ("label", "text", "coverage")), "Incomplete absence indicator")
    evidence_ids = {e["id"] for e in u["evidence"]}
    for entry in u["evidence"]:
        require(url_key(entry.get("source")), "Unsafe evidence URL")
        require(isinstance(entry.get("affects"), list) and all(isinstance(x, str) for x in entry["affects"]), "Invalid affects list")
    for item in u["news"]:
        require(url_key(item.get("url")), "Unsafe news URL")
    for row in u["revision_attribution"]:
        for part in row["contributions"]:
            require(all(k in evidence_ids for k in part.get("evidence_ids", [])), "Attribution references absent evidence")
    for key, state in u["warning"].items():
        require(state.get("coverage") in ("High", "Medium-high", "Medium", "Low", "Unknown"), "Invalid warning coverage")
        require(not (state["level"] == "critical" and state["coverage"] in ("Low", "Unknown")), "Low evidence cannot alone establish critical")
    for binary in u.get("binary_political", []):
        require(binary.get("event_id") == CORE[1] and binary.get("p") == by_id[CORE[1]]["p"],
                "Secondary political display is stale or adds a scored event")
    require(isinstance(u.get("social_summary"), str) and 5 <= len(u["social_summary"]) <= 65, "A reviewed social summary is required")


def scheduled_slot(day, cron, now):
    """Match the nominal cron, not runner start hour; permit same-day queue delays."""
    if day.weekday() != 6 or now.astimezone(ZONE).date() != day:
        return False
    due = dt.datetime.combine(day, dt.time(9), ZONE)
    expected = f"0 {due.astimezone(dt.timezone.utc).hour} * * 0"
    return cron == expected and now >= due


def issue_time(path, original, stamp):
    """Finalize only the new uncommitted record, at the exact chosen Git commit time."""
    require(stamp.tzinfo is not None, "Naive commit timestamp")
    data = json.loads(Path(path).read_bytes())
    one_append(original, data)
    record = data["updates"][-1]
    require(stamp.astimezone(ZONE).date().isoformat() == record["date"], "Commit crossed assessment day")
    require(all(dt.datetime.fromisoformat(f["forecast_open"]) <= stamp for f in record["forecasts"]), "Commit precedes forecast formation")
    record["publication_time"] = stamp.isoformat(timespec="seconds")
    record["methodology_notes"] = [
        "Frozen Protocol v1.0 retained. Evidence collection closed before forecast elicitation.",
        "publication_time equals the actual captured Git candidate commit timestamp; public deployment is separately verified."
    ]
    from validate_history import validate_history
    validate_history(data, original)
    dashboard_record(record, original["updates"][-1])
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
