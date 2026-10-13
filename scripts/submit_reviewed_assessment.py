#!/usr/bin/env python3
"""Publish an approved external Iran assessment via a protected GitHub PR.

No GitHub operation occurs until the complete handoff passes local validation.
Run only AFTER scripts/pre_github_review.py has created an off-repository handoff.
A failed check, timeout, stale main branch, or conflicting candidate blocks merge.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

from candidate_checks import dashboard_record, one_append
from review_receipt import checked_receipt
from validate_history import validate_history
from jsonschema import Draft202012Validator
from sunday_automation import gh, gh_json, protects_main, run, wait_checks

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY = "chuckcoleman/iran-stability-monitor"
EASTERN = ZoneInfo("America/New_York")


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def validate_handoff(folder, root=ROOT, now=None):
    """Run all substantive checks locally BEFORE touching a GitHub API/remote."""
    root=Path(root).resolve()
    folder=Path(folder).expanduser().resolve()
    require(folder!=root and root not in folder.parents,
            "Handoff must remain outside the GitHub checkout")
    before_file=folder/"history-before.json"
    candidate_file=folder/"data/history.json"
    require(before_file.is_file() and candidate_file.is_file(),
            "External handoff missing exact baseline or approved history")
    before_bytes=before_file.read_bytes()
    require(before_bytes==(root/"data/history.json").read_bytes(),
            "Checkout history does not match external pre-review baseline")
    before=json.loads(before_bytes)
    after=json.loads(candidate_file.read_bytes())
    one_append(before,after)
    date=after["updates"][-1]["date"]
    receipt_file=folder/"data/review-receipts"/(date+".json")
    require(receipt_file.is_file(),
            "No completed off-GitHub dual-review receipt in handoff")
    receipt=json.loads(receipt_file.read_bytes())
    current=now or dt.datetime.now(EASTERN)
    require(current.tzinfo is not None
            and current.astimezone(EASTERN).date().isoformat()==date
            and current.astimezone(EASTERN).weekday()==6,
            "Sunday candidate is stale, future-dated, or not yet issuable")
    checked_receipt(before,after,receipt,now=current)
    validate_history(after,before)
    schema=json.loads((root/"schema/history.schema.json").read_bytes())
    Draft202012Validator(schema).validate(after)
    dashboard_record(after["updates"][-1],before["updates"][-1])
    approval=receipt["approval"]
    round_no=approval["round"]
    draft=approval["draft_sha256"]
    for role in ("affirmative","critical"):
        p=folder/"review-audit"/f"review-{round_no:02d}-{role}.json"
        require(p.is_file(),"Missing off-GitHub "+role+" review audit")
        audit=json.loads(p.read_bytes())
        require(audit.get("role")==role and audit.get("round")==round_no
                and audit.get("status")=="clean"
                and audit.get("draft_sha256")==draft
                and audit.get("issues")==[],
                "Off-GitHub "+role+" audit disagrees with clean receipt")
    return {"date":date,"before":before,"after":after,
            "candidate_file":candidate_file,"receipt_file":receipt_file}


def verify_remote_ready():
    """READ Github only after every external review and local check passes."""
    remote=run("git","remote","get-url","origin").stdout.strip()
    require(remote in (
        "https://github.com/"+REPOSITORY,
        "https://github.com/"+REPOSITORY+".git",
        "git@github.com:"+REPOSITORY+".git",
        "git@github.com:"+REPOSITORY),
        "Origin is not the exact designated Iran monitor repository")
    require(run("git","branch","--show-current").stdout.strip()=="main",
            "Submissions must begin from a clean main checkout")
    require(not run("git","status","--porcelain").stdout.strip(),
            "Checkout has uncommitted changes; do not mix them with the assessment")
    base=run("git","rev-parse","HEAD").stdout.strip()
    details=gh_json("repos/"+REPOSITORY)
    require(details.get("default_branch")=="main",
            "Unexpected GitHub default branch")
    require(gh_json("repos/"+REPOSITORY+"/git/ref/heads/main")["object"]["sha"]==base,
            "Main branch changed after external review; reconcile before submitting")
    pages=gh_json("repos/"+REPOSITORY+"/pages")
    require(pages.get("build_type")=="workflow",
            "GitHub Pages is not workflow-validated")
    summaries=gh_json("repos/"+REPOSITORY+"/rulesets?per_page=100")
    require(isinstance(summaries,list)
            and len(summaries)<100,"Ruleset listing incomplete")
    rules=[gh_json("repos/"+REPOSITORY+"/rulesets/"+str(row["id"]))
           for row in summaries if row.get("enforcement")=="active"]
    require(any(protects_main(x) for x in rules),
            "Strict required CI, PR, and no-bypass protections unavailable")
    return base


def submit(folder, *, merge=False, root=ROOT):
    """Validate off-GitHub work first, then open the protected candidate PR."""
    # All external review / data guards precede any use of gh or a remote.
    checked=validate_handoff(folder,root)
    require(Path(root).resolve()==ROOT.resolve(),
            "Only the designated repository checkout may submit")
    base=verify_remote_ready()
    date=checked["date"]
    branch="reviewed-iran-"+date.replace("-","")
    require(not run("git","ls-remote","--heads","origin",branch).stdout.strip(),
            "Review branch already exists; reconcile rather than reissue forecasts")
    run("git","config","user.name","Iran Stability Monitor Assessment")
    run("git","config","user.email","assessment@users.noreply.github.com")
    run("git","checkout","-b",branch)
    new_receipt=ROOT/"data/review-receipts"/(date+".json")
    require(not new_receipt.exists(),"Receipt for this date already present")
    new_receipt.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(checked["candidate_file"],ROOT/"data/history.json")
    shutil.copyfile(checked["receipt_file"],new_receipt)
    require(run("git","diff","--name-only").stdout.splitlines()==["data/history.json"],
            "Unexpected tracked changes in approved candidate")
    # Validate the bytes actually being committed a second time.
    actual=json.loads((ROOT/"data/history.json").read_bytes())
    checked_receipt(checked["before"],actual,json.loads(new_receipt.read_bytes()))
    validate_history(actual,checked["before"])
    run("git","add","--","data/history.json",
        "data/review-receipts/"+date+".json")
    require(run("git","diff","--cached","--name-only").stdout.splitlines()==[
        "data/history.json","data/review-receipts/"+date+".json"],
        "Staged files differ from the two approved publication artifacts")
    run("git","commit","-m","Append externally reviewed Iran assessment "+date)
    sha=run("git","rev-parse","HEAD").stdout.strip()
    # This is the first GitHub write in the complete off-GitHub review workflow.
    run("git","push","origin",branch)
    url=gh("pr","create","-R",REPOSITORY,
           "--base","main","--head",branch,
           "--title","Prospective Iran assessment "+date,
           "--body","External affirmative and critical reviews both approved the "
                    "same frozen-evidence draft. Verify data/review-receipts/"
                    +date+".json, append-only history, CI and branch protection.")
    print("Externally reviewed candidate PR: "+url)
    if not merge:
        print("PR opened; protected CI and owner merge remain required.")
        return url
    wait_checks(REPOSITORY,branch,sha)
    require(gh_json("repos/"+REPOSITORY+"/git/ref/heads/main")["object"]["sha"]==base,
            "Main changed before merge; do not publish stale forecasts")
    gh("pr","merge",url,"-R",REPOSITORY,"--squash","--match-head-commit",sha)
    print("Protected merge completed; Pages and X still require independent checks.")
    return url


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff",required=True,
                        help="Absolute path to completed off-GitHub reviewed output")
    parser.add_argument("--merge",action="store_true",
                        help="Merge automatically ONLY after required CI succeeds")
    args=parser.parse_args()
    submit(args.handoff,merge=args.merge)


if __name__=="__main__":
    main()
