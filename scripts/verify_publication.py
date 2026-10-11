#!/usr/bin/env python3
"""Read-only public deployment verification. Does not post or publish anything."""
import json
import pathlib
import time
import urllib.request

LOCAL = pathlib.Path("data/history.json")
URL = "https://iranstabilitymonitor.org/data/history.json"

def main():
    expected = json.loads(LOCAL.read_text(encoding="utf-8"))
    latest = expected["updates"][-1]["date"]
    for attempt in range(12):
        try:
            request = urllib.request.Request(URL, headers={"Cache-Control": "no-cache", "User-Agent": "IranStabilityMonitor-verifier/1.0"})
            with urllib.request.urlopen(request, timeout=25) as response:
                observed = json.load(response)
            if observed == expected:
                print("PUBLICATION VERIFIED: " + latest)
                return
        except (OSError, ValueError) as error:
            print(f"Verification attempt {attempt + 1} failed: {error}")
        if attempt != 11:
            time.sleep(30)
    raise SystemExit("PUBLICATION NOT VERIFIED; X posting forbidden.")

if __name__ == "__main__":
    main()
