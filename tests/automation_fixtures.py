"""Synthetic no-network inputs. Dates and baselines follow the archived history."""
import copy
import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
ZONE = ZoneInfo("America/New_York")


def fixture(history=None):
    if history is None:
        history = json.loads((ROOT / "data/history.json").read_text())
    history = copy.deepcopy(history)
    prev = history["updates"][-1]
    day = dt.date.fromisoformat(prev["date"]) + dt.timedelta(days=7)
    opened = dt.datetime.combine(day, dt.time(10, 0, 20), ZONE)
    evidence = []
    for i in range(6):
        evidence.append({"source": f"https://publisher{i % 3}.example.org/news/{i}",
          "source_title": "Synthetic source headline for a unit test", "publisher": f"Publisher {i % 3}",
          "event_date": (day - dt.timedelta(days=1)).isoformat(), "category": "Synthetic test evidence",
          "observation": "Synthetic supporting observation; not a real geopolitical assertion.",
          "reliability": "Medium", "impact_magnitude": "moderate",
          "direction": ("raises", "lowers", "ambiguous")[i % 3], "evidence_status": "new",
          "affects": ["Sustained major regional escalation"]})
    forecasts, revisions = [], []
    for f in prev["forecasts"]:
        if f.get("scored") is True:
            forecasts.append({"event_id": f["event_id"], "p": f["p"], "range": f["range"], "confidence": "Medium"})
            revisions.append({"event_id": f["event_id"], "contributions": [{"label": "Synthetic unchanged judgment", "pp": 0}], "residual_pp": 0})
    analysis = {k: "Synthetic test narrative, not live evidence or a publishable assessment. " + k
                for k in ("summary", "what_changed", "stabilizer", "next_threshold", "limitations")}
    analysis["next_threshold"] = (
        "A hypothetical 14-day settlement failure would be one monitored event. "
        "A separate currency shock could occur in this synthetic test."
    )
    analysis.update({"forecasts": forecasts, "revision_attribution": revisions,
                    "warning": copy.deepcopy(prev["warning"]), "conditions": copy.deepcopy(prev["conditions"]),
                    "haircut_components": {k: p for k, p, cap in prev["haircut"]["calculation"]["components"]},
                    "haircut_range": prev["haircut"]["range"], "status": prev["status"],
                    "houthi": {k: prev["houthi"][k] for k in ("m6", "m24", "material_support_12m",
                                  "technical_financial_support_12m", "independent_capability_12m")},
                    "social_summary": "This is a synthetic automation test, not news.",
                    "hanke_hyperinflation": {"probabilities": {"m3": 1, "m6": 2, "m12": 3},
                         "annual_inflation_pct": None, "assessment": "Synthetic monthly diagnostic only."}})
    # The source of each synthetic haircut point is explicit, matching the
    # production requirement without claiming these fixtures are real evidence.
    source_id = "E-" + day.strftime("%Y%m%d") + "-01"
    analysis["haircut_component_support"] = {
        k: {"basis": "assumption" if p else "no_support",
            "evidence_ids": [source_id] if p else [],
            "rationale": ("An explicitly assumed synthetic adjustment for unit tests, "
                          "with no real-world empirical claim or market observation."
                          if p else
                          "No supporting observation in this synthetic test.")}
        for k,p,cap in prev["haircut"]["calculation"]["components"]}
    analysis["houthi"]["headline_support_12m"] = prev["metrics"]["houthi_support_12m"]
    for key in ("regional", "political", "chains", "absence_indicators"):
        analysis[key] = copy.deepcopy(prev[key])
    return history, analysis, evidence, opened


def legacy_receipt_fixture():
    """Synthetic October 11 v1 receipt test using immutable Oct 4 history.

    Keeps historical-compatibility tests meaningful as current history grows.
    It must never authorize a future date through a legacy approval format.
    """
    history=json.loads((ROOT / "data/history.json").read_text(encoding="utf-8"))
    indices=[i for i, item in enumerate(history["updates"])
             if item["date"] == "2026-10-11"]
    if len(indices) != 1 or indices[0] < 1:
        raise ValueError("Historical October 11 receipt fixture unavailable")
    history["updates"]=history["updates"][:indices[0]]
    result=fixture(history=history)
    if result[3].date().isoformat() != "2026-10-11":
        raise ValueError("Legacy receipt fixture must target October 11")
    return result
