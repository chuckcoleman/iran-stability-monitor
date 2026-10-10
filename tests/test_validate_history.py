"""Protocol-v1 validator regression tests: temporal, arithmetic and archive integrity."""
import copy
import datetime as dt
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_history import ValidationError, validate_history

ZONE = ZoneInfo("America/New_York")
EVENTS = [
    "regional_escalation_90d", "regime_end_12m",
    "currency_crisis_12m", "external_payments_crisis_12m",
]


def time_pair(day="2026-10-04", hour=14, minute=0):
    opened = dt.datetime.fromisoformat(f"{day}T{hour:02}:{minute:02}:00").replace(tzinfo=ZONE)
    deadlines = []
    for event in EVENTS:
        if event == EVENTS[0]:
            deadline_day = opened.date() + dt.timedelta(days=90)
        else:
            try:
                deadline_day = opened.date().replace(year=opened.year + 1)
            except ValueError:
                deadline_day = opened.date().replace(year=opened.year + 1, day=28)
        deadlines.append(dt.datetime.combine(
            deadline_day, opened.timetz().replace(tzinfo=None), tzinfo=ZONE
        ).isoformat())
    return opened.isoformat(), deadlines


def fixture(day="2026-10-04", hour=14, minute=0):
    opening, deadlines = time_pair(day, hour, minute)
    opening_dt = dt.datetime.fromisoformat(opening)
    cutoff = (opening_dt.astimezone(dt.timezone.utc)
              - dt.timedelta(minutes=30)).astimezone(ZONE).isoformat()
    publication = (opening_dt.astimezone(dt.timezone.utc)
                   + dt.timedelta(minutes=30)).astimezone(ZONE).isoformat()
    protocol = {
        "version": "1.0",
        "core_scored_set": [
            {"id": event, "resolution": f"Frozen definition: {event}"} for event in EVENTS
        ],
        "warning_transition_rules": {"Monetary / FX": {}},
    }
    probabilities = [56, 14, 78, 80]
    intervals = [[42, 70], [8, 24], [65, 88], [67, 90]]
    forecasts = [{
        "event_id": event,
        "forecast_id": f"{event}_{day.replace('-', '')}",
        "event_definition": f"Frozen definition: {event}",
        "created_date": day, "forecast_open": opening,
        "resolution_deadline": deadlines[i],
        "p": probabilities[i], "range": intervals[i],
        "confidence": "Medium", "scored": True,
    } for i, event in enumerate(EVENTS)]
    record = {
        "date": day, "summary": "Historical assessment",
        "protocol_version": "1.0", "evidence_cutoff": cutoff,
        "publication_time": publication, "forecasts": forecasts,
        "warning": {"Monetary / FX": {"level": "warning-level", "direction": "up"}},
        "evidence": [{
            "id": f"E-{day}", "source": "https://example.com/source",
            "reliability": "High", "evidence_status": "new",
            "direction": "raises", "impact_magnitude": "moderate",
            "source_publication_time": (opening_dt - dt.timedelta(hours=1)).isoformat(),
        }],
        "haircut": {"calculation": {
            "components": [
                ["Physical delivery/blockade", 15], ["Sanctions/payment channels", 10],
                ["Sovereign/counterparty", 6], ["Oil-price/basis", 4],
                ["Illiquidity/enforcement", 4],
                ["Political/secondary-sanctions tail", 5]
            ],
            "raw_sum": 44, "overlap_deduction_20pct": 2, "adjusted_headline": 42
        }},
        "revision_attribution": [{
            "event_id": EVENTS[0], "prior_p": 36, "new_p": 56,
            "contributions": [{"label": "Escalation", "pp": 15}], "residual_pp": 5
        }],
        "corrections": [],
    }
    return {"schema_version": 3, "protocol": protocol, "updates": [record]}


class ValidatorRegressionTests(unittest.TestCase):
    def rejects(self, history, pattern, previous=None):
        with self.assertRaisesRegex(ValidationError, pattern):
            validate_history(history, previous)

    def test_valid_record(self):
        validate_history(fixture())

    def test_late_second_opening(self):
        history = fixture()
        history["updates"][0]["forecasts"][1]["forecast_open"] = "2026-10-04T15:30:00-04:00"
        self.rejects(history, "regime_end_12m.*forecast_open")

    def test_early_fourth_opening(self):
        history = fixture()
        history["updates"][0]["forecasts"][3]["forecast_open"] = "2026-10-04T12:00:00-04:00"
        self.rejects(history, "external_payments_crisis_12m.*forecast_open")

    def test_deadline_wrong_winter_offset(self):
        history = fixture()
        history["updates"][0]["forecasts"][0]["resolution_deadline"] = "2027-01-02T14:00:00-04:00"
        self.rejects(history, "UTC offset does not match")

    def test_deadline_wrong_annual_offset(self):
        history = fixture("2026-11-15")
        history["updates"][0]["forecasts"][1]["resolution_deadline"] = "2027-11-15T14:00:00-04:00"
        self.rejects(history, "UTC offset does not match")

    def test_opening_wrong_dst_offset(self):
        history = fixture()
        history["updates"][0]["forecasts"][0]["forecast_open"] = "2026-10-04T14:00:00-05:00"
        self.rejects(history, "UTC offset does not match")

    def test_cutoff_in_utc_allowed(self):
        history = fixture()
        history["updates"][0]["evidence_cutoff"] = "2026-10-04T17:30:00+00:00"
        history["updates"][0]["publication_time"] = "2026-10-04T18:30:00+00:00"
        validate_history(history)

    def test_nonexistent_spring_forward_opening(self):
        history = fixture("2027-03-14")
        history["updates"][0]["forecasts"][0]["forecast_open"] = "2027-03-14T02:30:00-05:00"
        self.rejects(history, "DST transition")

    def test_fall_back_earlier_fold(self):
        validate_history(fixture("2026-11-01", 1, 30))

    def test_fall_back_later_fold(self):
        history = fixture("2026-11-01", 1, 30)
        history["updates"][0]["forecasts"][0]["forecast_open"] = "2026-11-01T01:30:00-05:00"
        history["updates"][0]["publication_time"] = "2026-11-01T02:30:00-05:00"
        validate_history(history)

    def test_february_29_maps_to_february_28(self):
        validate_history(fixture("2028-02-29"))

    def test_february_29_wrong_deadline(self):
        history = fixture("2028-02-29")
        history["updates"][0]["forecasts"][1]["resolution_deadline"] = "2029-03-01T14:00:00-05:00"
        self.rejects(history, "local calendar date/time mismatch")

    def test_naive_opening_timestamp(self):
        history = fixture()
        history["updates"][0]["forecasts"][2]["forecast_open"] = "2026-10-04T14:00:00"
        self.rejects(history, "explicit UTC offset")

    def test_nan_probability(self):
        history = fixture()
        history["updates"][0]["forecasts"][0]["p"] = float("nan")
        self.rejects(history, "finite number")

    def test_frozen_event_definition(self):
        history = fixture()
        history["updates"][0]["forecasts"][3]["event_definition"] = "Altered"
        self.rejects(history, "differs from frozen")

    def test_post_cutoff_source(self):
        history = fixture()
        history["updates"][0]["evidence"][0]["source_publication_time"] = "2026-10-04T18:00:00Z"
        self.rejects(history, "post-cutoff evidence")

    def test_missing_source_time_warns_but_passes(self):
        history = fixture()
        history["updates"][0]["evidence"][0]["source_publication_time"] = None
        validate_history(history)

    def test_revision_probability_must_match(self):
        history = fixture()
        row = history["updates"][0]["revision_attribution"][0]
        row["new_p"], row["residual_pp"] = 60, 9
        self.rejects(history, "differs from actual forecast")

    def test_duplicate_assessment_date(self):
        history = fixture()
        history["updates"].append(copy.deepcopy(history["updates"][0]))
        self.rejects(history, "strictly increasing and unique")

    def test_append_new_assessment(self):
        old = fixture()
        current = copy.deepcopy(old)
        current["updates"].append(fixture("2026-10-11")["updates"][0])
        validate_history(current, old)

    def test_historical_warning_edit_forbidden(self):
        old = fixture()
        current = copy.deepcopy(old)
        current["updates"][0]["warning"]["Monetary / FX"]["direction"] = "flat"
        self.rejects(current, "unauthorized historical mutation of warning", old)

    def test_historical_evidence_edit_forbidden(self):
        old = fixture()
        current = copy.deepcopy(old)
        current["updates"][0]["evidence"][0]["source"] = "https://example.com/altered"
        self.rejects(current, "unauthorized historical mutation of evidence", old)

    def test_historical_probability_edit_forbidden(self):
        old = fixture()
        old["updates"][0]["revision_attribution"] = []
        current = copy.deepcopy(old)
        current["updates"][0]["forecasts"][0]["p"] = 58
        self.rejects(current, "unauthorized change to p", old)

    def test_add_resolution_to_historical_forecast(self):
        old = fixture()
        current = copy.deepcopy(old)
        current["updates"][0]["forecasts"][0]["outcome"] = "Yes"
        current["updates"][0]["forecasts"][0]["resolution_note"] = "Archived evidence"
        validate_history(current, old)

    def test_append_correction_with_reason(self):
        old = fixture()
        current = copy.deepcopy(old)
        current["updates"][0]["corrections"].append({
            "date": "2027-01-10", "reason": "Source error", "corrected_claim": "Corrected"
        })
        validate_history(current, old)

    def test_empty_reason_for_correction_forbidden(self):
        old = fixture()
        current = copy.deepcopy(old)
        current["updates"][0]["corrections"].append({
            "date": "2027-01-10", "reason": ""
        })
        self.rejects(current, "require a date and reason", old)

    def test_historical_houthi_definition_edit_forbidden(self):
        old = fixture()
        old["updates"][0]["houthi"] = {"definition": "Archived wording"}
        current = copy.deepcopy(old)
        current["updates"][0]["houthi"]["definition"] = "Revised"
        self.rejects(current, "unauthorized historical mutation of houthi", old)

    def test_frozen_protocol_mutation_forbidden(self):
        old = fixture()
        current = copy.deepcopy(old)
        current["protocol"]["warning_transition_rules"]["Monetary / FX"]["green"] = "Changed"
        self.rejects(current, "frozen Protocol v1 was modified", old)


if __name__ == "__main__":
    unittest.main()
