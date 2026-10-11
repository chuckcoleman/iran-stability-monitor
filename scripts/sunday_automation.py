#!/usr/bin/env python3
"""Fail-closed preparation entry point for a future independently audited Sunday assessment agent.

No dummy forecasts, synthetic evidence timestamps, silent fallback to previous probabilities,
or automatic changes to frozen Protocol v1 are permitted.
"""
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/New_York")

def preflight():
    now = dt.datetime.now(ZONE)
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
        if now.weekday() != 6 or now.hour != 9:
            print("Scheduled UTC slot is not 09:00 Sunday in America/New_York; skip.")
            return 2
    if os.environ.get("ASSESSMENT_AUTOMATION_ENABLED") != "true":
        raise RuntimeError("Automation not enabled; set ASSESSMENT_AUTOMATION_ENABLED only after end-to-end approval.")
    if not os.environ.get("RESEARCH_API_KEY") or not os.environ.get("FORECAST_API_KEY"):
        raise RuntimeError("Research and forecasting service credentials are missing.")
    raise RuntimeError("No audited live research/forecast adapter configured. Refusing to create a forecast.")

def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "preflight":
        return preflight()
    if command == "prepare":
        raise RuntimeError("Preparation is disabled until an audited source-fetch/forecast/PR adapter is installed.")
    raise SystemExit("Usage: sunday_automation.py preflight|prepare")

if __name__ == "__main__":
    sys.exit(main())
