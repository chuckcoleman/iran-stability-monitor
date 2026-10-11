#!/usr/bin/env python3
"""Read-only, SHA-bound verification of the actual gated Pages publication."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
from candidate_checks import one_append

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://iranstabilitymonitor.org/data/history.json"
ZONE = ZoneInfo("America/New_York")


def check(value, why):
    if not value:
        raise RuntimeError(why)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Redirect refused for authenticated or canonical request")


def request_bytes(url, headers=None, data=None, method="GET"):
    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    with urllib.request.build_opener(NoRedirect).open(req, timeout=35) as response:
        body = response.read(4_000_001)
        check(len(body) <= 4_000_000, "Oversized API/site response")
        return body


def github(path, method="GET", data=None):
    repo = os.environ.get("GITHUB_REPOSITORY", "chuckcoleman/iran-stability-monitor")
    check(repo == "chuckcoleman/iran-stability-monitor", "Wrong repository")
    token = os.environ["GH_TOKEN"]
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    body = request_bytes("https://api.github.com/repos/" + repo + "/" + path,
                         headers, None if data is None else json.dumps(data).encode(), method)
    return json.loads(body) if body else {}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode().strip()


def fresh_record(before, after, now=None):
    one_append(before, after)
    latest = after["updates"][-1]
    date = dt.date.fromisoformat(latest["date"])
    current = now or dt.datetime.now(ZONE)
    publication = dt.datetime.fromisoformat(latest["publication_time"])
    check(date.weekday() == 6, "Not a Sunday assessment")
    check(publication.tzinfo is not None and publication.astimezone(ZONE).date() == date,
          "Issuance date does not match Sunday assessment")
    age = current - publication
    check(dt.timedelta(0) <= age <= dt.timedelta(hours=24), "Stale/future assessment")
    return latest["date"]


def validate_run(run, jobs, sha):
    check(run.get("head_sha") == sha and run.get("head_branch") == "main",
          "Run does not identify this main commit")
    check(run.get("event") == "push" and run.get("path") == ".github/workflows/validate.yml"
          and run.get("name") == "Validate and publish monitor",
          "Not the validation-gated push workflow")
    check(run.get("status") == "completed" and run.get("conclusion") == "success",
          "Deployment workflow has not succeeded")
    for name in ("validate", "Deploy validated website"):
        found = [j for j in jobs if j.get("name") == name]
        check(len(found) == 1 and found[0].get("conclusion") == "success"
              and found[0].get("status") == "completed", "Gated job failed/missing: " + name)
        check(found[0].get("head_sha", sha) == sha, "Job belongs to another commit")


def verify_run(sha):
    run_id = os.environ["SOURCE_WORKFLOW_RUN_ID"]
    check(run_id.isdigit(), "Missing source workflow run ID")
    run = github("actions/runs/" + run_id)
    payload = github("actions/runs/" + run_id + "/jobs?filter=latest&per_page=100")
    jobs = payload.get("jobs", [])
    check(payload.get("total_count") == len(jobs), "Incomplete deployment job listing")
    validate_run(run, jobs, sha)
    pages = github("pages")
    check(pages.get("build_type") == "workflow", "Pages is no longer Actions-source")
    check(pages.get("cname") == "iranstabilitymonitor.org", "Unexpected Pages domain")
    return run_id


def verify_public(expected, tries=12, sleeper=time.sleep):
    for attempt in range(tries):
        try:
            body = request_bytes(SITE + "?verify=" + str(time.time_ns()), {
                "Cache-Control": "no-cache", "User-Agent": "IranMonitor-publication-check/1.0"})
            # Full parsed equality: no stale prefixes or mismatching metadata accepted.
            if json.loads(body) == json.loads(expected):
                return
        except (OSError, ValueError):
            pass
        if attempt + 1 < tries:
            sleeper(30)
    raise RuntimeError("Canonical public JSON differs from validated commit")


def verify_all():
    sha = git("rev-parse", "HEAD")
    check(sha == os.environ["SOURCE_HEAD_SHA"], "Checkout/source commit mismatch")
    raw = (ROOT / "data/history.json").read_bytes()
    before = json.loads(git("show", "HEAD^:data/history.json"))
    after = json.loads(raw)
    if after == before:
        print("Code-only deployment; no new forecast or X announcement")
        return None
    date = fresh_record(before, after)
    from validate_history import validate_history
    validate_history(after, before)
    run_id = verify_run(sha)
    # A later main commit is harmless only when it preserves precisely this history.
    current = github("contents/data/history.json?ref=main")
    import base64
    check(current.get("encoding") == "base64", "Cannot inspect current main history")
    check(base64.b64decode(current["content"]) == raw, "A newer assessment superseded this run")
    verify_public(raw)
    receipt = {"assessment_date": date, "head_sha": sha, "source_run_id": run_id,
               "history_sha256": hashlib.sha256(raw).hexdigest(),
               "verified_at": dt.datetime.now(ZONE).isoformat(timespec="seconds")}
    (ROOT / ".verified-publication.json").write_text(json.dumps(receipt, indent=2) + "\n")
    audit = ROOT / ".automation-audit"
    audit.mkdir(exist_ok=True)
    (audit / "publication-verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("Gated public assessment verified: " + date)
    return receipt


if __name__ == "__main__":
    verify_all()
