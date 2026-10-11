#!/usr/bin/env python3
"""Verify a validated GitHub Actions Pages deployment and exact public history.

Only a new Sunday record on main may trigger the publication follow-up.
No publishing or third-party API side effects occur in this module.
"""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent.parent
SITE="https://iranstabilitymonitor.org/data/history.json"

def check(value,why):
    if not value: raise RuntimeError(why)

def has_new_record():
    changed=subprocess.check_output(
        ["git","diff","--name-only","HEAD^","HEAD"],cwd=ROOT,text=True).splitlines()
    if "data/history.json" not in changed:
        print("Non-assessment merge; no social publication permitted.")
        return False
    # Historical updates must remain untouched: local scripts/validator handled by PR CI.
    expected=json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))
    before=json.loads(subprocess.check_output(
        ["git","show","HEAD^:data/history.json"],cwd=ROOT,text=True))
    check(len(expected["updates"])==len(before["updates"])+1,
          "Commit did not append exactly one assessment")
    check(expected["updates"][:-1]==before["updates"],"Old assessments were changed")
    check({k:v for k,v in expected.items() if k!="updates"}==
          {k:v for k,v in before.items() if k!="updates"},"Root/protocol changed")
    date=expected["updates"][-1]["date"]
    now=dt.datetime.now(ZoneInfo("America/New_York"))
    check(now.date().isoformat()==date and now.weekday()==6,
          "Assessment is not a fresh Sunday record")
    return True

def verify_run():
    repo=os.environ["GITHUB_REPOSITORY"]
    runid=os.environ["SOURCE_WORKFLOW_RUN_ID"]
    token=os.environ["GH_TOKEN"]
    req=urllib.request.Request(
       f"https://api.github.com/repos/{repo}/actions/runs/{runid}/jobs?per_page=100",
       headers={"Authorization":"Bearer "+token,
                "Accept":"application/vnd.github+json",
                "X-GitHub-Api-Version":"2022-11-28"})
    with urllib.request.urlopen(req,timeout=30) as response:
        jobs=json.load(response)["jobs"]
    for required in ("validate","Deploy validated website"):
        candidates=[j for j in jobs if j.get("name")==required]
        check(len(candidates)==1 and candidates[0].get("conclusion")=="success",
              "Gated job not confirmed successful: "+required)

def verify_public():
    expected=json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))
    for attempt in range(12):
        try:
            req=urllib.request.Request(
                SITE+"?verify="+str(int(time.time())),
                headers={"Cache-Control":"no-cache","User-Agent":"IranMonitor-deployment-validator/1.0"})
            with urllib.request.urlopen(req,timeout=30) as response:
                observed=json.load(response)
            if observed==expected:
                print("Exact canonical public assessment verified: "+
                      expected["updates"][-1]["date"])
                return
        except (OSError,ValueError) as exc:
            print("Read-only website check did not succeed:",type(exc).__name__)
        if attempt!=11:time.sleep(30)
    raise RuntimeError("Canonical public assessment does not match the validated merge")

def main():
    if not has_new_record():return
    verify_run()
    verify_public()
    with (ROOT/".verified-assessment-date").open("w",encoding="utf-8") as f:
        date=json.loads((ROOT/"data/history.json").read_text())["updates"][-1]["date"]
        f.write(date)

if __name__=="__main__":
    main()
