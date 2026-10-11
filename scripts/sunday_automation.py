#!/usr/bin/env python3
"""GitHub Actions orchestration: branch -> candidate -> CI -> protected merge.

Requires a separate fine-grained PAT because GITHUB_TOKEN-created PR/push events
do not independently trigger normal validation / Pages workflow runs.
"""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent.parent
ZONE=ZoneInfo("America/New_York")

def run(*args,check=True):
    p=subprocess.run(args,cwd=ROOT,text=True,capture_output=True)
    if check and p.returncode:
        # Never echo environment variables, secrets, or untrusted generated text.
        raise RuntimeError("Command failed: "+" ".join(args[:3])+
                           "; see GitHub Actions step details")
    return p

def gh(*args):
    return run("gh",*args).stdout.strip()

def gh_json(*args):
    return json.loads(gh("api",*args))

def check(condition,why):
    if not condition:raise RuntimeError(why)

def eastern_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(ZONE)

def schedule_slot():
    now=eastern_now()
    if now.weekday()!=6:
        return False
    local_nine=dt.datetime.combine(now.date(),dt.time(9),ZONE)
    expected=("0 13 * * 0" if local_nine.utcoffset()==dt.timedelta(hours=-4)
              else "0 14 * * 0")
    return os.getenv("GITHUB_EVENT_SCHEDULE")==expected

def ready():
    if os.getenv("ASSESSMENT_AUTOMATION_ENABLED")!="true":
        print("Sunday automation disabled; safely skipped")
        return False
    if os.getenv("GITHUB_EVENT_NAME")=="schedule" and not schedule_slot():
        print("UTC cron not currently 09:00 Eastern; safely skipped")
        return False
    for secret in ("OPENAI_API_KEY","AUTOMATION_GH_TOKEN"):
        check(os.getenv(secret), "Required secret missing: "+secret)
    check(os.getenv("GH_TOKEN")==os.getenv("AUTOMATION_GH_TOKEN"),
          "Authenticated gh token mismatch")
    return True

def verify_repository_gate(repo):
    # Pages must be Actions-source, not branch-source, even when a gated workflow exists.
    pages=gh_json("repos/"+repo+"/pages")
    check(pages.get("build_type")=="workflow",
          "GitHub Pages Source is not verified as GitHub Actions")
    rules=gh_json("repos/"+repo+"/rulesets")
    check(isinstance(rules,list) and rules,"Branch protections missing")
    active=[]
    for entry in rules:
        if entry.get("enforcement")=="active":
            detail=gh_json("repos/"+repo+"/rulesets/"+str(entry["id"]))
            includes=detail.get("conditions",{}).get("ref_name",{}).get("include",[])
            if "~DEFAULT_BRANCH" in includes or "refs/heads/main" in includes:
                active.append(detail)
    check(any(any(x.get("type")=="pull_request" for x in rule.get("rules",[])) and
              any(x.get("type")=="required_status_checks" and
                  any(c.get("context")=="validate" for c in
                      x.get("parameters",{}).get("required_status_checks",[]))
                  for x in rule.get("rules",[])) and
              not rule.get("bypass_actors")
              for rule in active), "Protective PR rules and required validate check not enforced")

def wait_checks(repo,branch,sha,seconds=1800):
    stop=time.monotonic()+seconds
    while time.monotonic()<stop:
        results=gh_json("repos/"+repo+"/actions/runs",
                        "-X","GET","-f","event=pull_request",
                        "-f","branch="+branch,
                        "-f","per_page=30")
        runs=[x for x in results.get("workflow_runs",[]) if
              x.get("head_sha")==sha and
              x.get("name")=="Validate and publish monitor"]
        if not runs:
            print("PR validation has not started")
        else:
            job=sorted(runs,key=lambda x:x["id"])[-1]
            if job.get("status")=="completed":
                check(job.get("conclusion")=="success",
                      "PR validator concluded "+str(job.get("conclusion")))
                jobs=gh_json("repos/"+repo+"/actions/runs/"+str(job["id"])+"/jobs")
                entries=jobs.get("jobs",[])
                checks=[x for x in entries if x.get("name")=="validate"]
                check(len(checks)==1 and checks[0].get("conclusion")=="success",
                      "Required validate job has not passed")
                return
        time.sleep(15)
    raise RuntimeError("PR validation never completed within 30 minutes")

def prepare_and_merge():
    repo=os.environ.get("GITHUB_REPOSITORY","chuckcoleman/iran-stability-monitor")
    verify_repository_gate(repo)
    date=eastern_now().date().isoformat()
    with (ROOT/"data/history.json").open(encoding="utf-8") as f: history=json.load(f)
    check(history["updates"][-1]["date"]<date,"Assessment exists already")
    check((dt.date.fromisoformat(date)-dt.date.fromisoformat(history["updates"][-1]["date"])).days==7,
          "Missed prior Sunday record; manual audit required before prospective update")
    branch="sunday-auto-"+date.replace("-","")
    remote=run("git","ls-remote","--heads","origin",branch).stdout
    check(not remote.strip(),"An automation branch already exists; manual reconciliation required")
    check(not run("git","status","--porcelain").stdout.strip(),"Working tree not clean")
    base_sha=run("git","rev-parse","HEAD").stdout.strip()
    run("git","config","user.name","Iran Stability Monitor Automation")
    run("git","config","user.email","automation@users.noreply.github.com")
    run("git","checkout","-b",branch)
    with tempfile.TemporaryDirectory() as tmp:
        baseline=Path(tmp)/"exact_preupdate_history.json"
        baseline.write_bytes((ROOT/"data/history.json").read_bytes())
        run(sys.executable,"scripts/assessment_pipeline.py","prepare")
        run(sys.executable,"-m","jsonschema","-i","data/history.json","schema/history.schema.json")
        run(sys.executable,"-m","unittest","discover","-s","tests","-v")
        run(sys.executable,"scripts/validate_history.py","--baseline",str(baseline))
    # One data file must be changed; no protocol, scripts or previous files.
    changed=run("git","diff","--name-only").stdout.splitlines()
    check(changed==["data/history.json"],"Unexpected tracked files changed")
    run("git","add","data/history.json")
    run("git","commit","-m","Append prospective Iran assessment "+date)
    sha=run("git","rev-parse","HEAD").stdout.strip()
    run("git","push","origin",branch)
    url=gh("pr","create","-R",repo,"--base","main","--head",branch,
           "--title","Prospective Iran assessment "+date,
           "--body","Unattended Protocol v1 Sunday assessment; one append-only record. "
                     "Pre-validated locally. Required PR CI must succeed before a "
                     "ruleset-compliant merge. No bypass permitted.")
    print("Candidate PR created: "+url)
    wait_checks(repo,branch,sha)
    current_main=gh_json("repos/"+repo+"/git/ref/heads/main").get("object",{}).get("sha")
    check(current_main==base_sha,"Main changed after candidate baseline: do not merge stale record")
    # No --admin bypass and no blind --auto; checks have already succeeded.
    gh("pr","merge",url,"-R",repo,"--squash",
       "--match-head-commit",sha)
    print("Validated PR merged; gated main-branch CI and Pages deployment must follow.")
    # The workflow_run publication verifier will separately check the deployed site.

def main():
    cmd=sys.argv[1] if len(sys.argv)==2 else ""
    if cmd=="preflight":
        return 0 if ready() else 3
    if cmd=="run":
        if ready():prepare_and_merge()
        return 0
    raise SystemExit("Usage: sunday_automation.py preflight|run")

if __name__=="__main__":
    sys.exit(main())
