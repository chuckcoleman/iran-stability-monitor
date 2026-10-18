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
PROTOCOL_SITE = "https://iranstabilitymonitor.org/protocol-v1.html"
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


def verify_public(expected, tries=6, sleeper=time.sleep, url=SITE):
    """Require exact canonical HTTPS bytes, not JSON-equivalent content or GitHub success.

    Both the history and the frozen protocol page must be checked on every deploy,
    including code-only deploys. A cache-busting request cannot substitute for a
    successful independent .org response.
    """
    check(url in (SITE, PROTOCOL_SITE), "Unapproved canonical verification URL")
    check(tries >= 1, "No canonical verification attempts")
    errors = []
    for attempt in range(tries):
        try:
            body = request_bytes(url + "?verify=" + str(time.time_ns()), {
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "User-Agent": "IranMonitor-publication-check/1.1"})
            if body == expected:
                return hashlib.sha256(body).hexdigest()
            errors.append("byte mismatch")
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(type(exc).__name__ + ": " + str(exc)[:180])
        if attempt + 1 < tries:
            sleeper(20)
    raise RuntimeError("Canonical public bytes differ or unavailable: " + url +
                       " (last: " + errors[-1] + ")")


def verify_all():
    sha = git("rev-parse", "HEAD")
    check(sha == os.environ["SOURCE_HEAD_SHA"], "Checkout/source commit mismatch")
    raw = (ROOT / "data/history.json").read_bytes()
    protocol_raw = (ROOT / "protocol-v1.html").read_bytes()
    before = json.loads(git("show", "HEAD^:data/history.json"))
    after = json.loads(raw)
    code_only = after == before

    if not code_only:
        date = fresh_record(before, after)
        # A new forecast must already carry a legitimate clean pre-GitHub receipt.
        from review_receipt import checked_receipt
        receipt_file = ROOT / "data" / "review-receipts" / (date + ".json")
        check(receipt_file.is_file(), "Missing pre-GitHub approved-review receipt")
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        if receipt.get("version") == 2:
            draft_path = ROOT / "data" / "review-drafts" / (date + ".json")
            report_path = ROOT / "data" / "review-reports" / (date + ".md")
            check(draft_path.is_file() and report_path.is_file(),
                  "Missing exact critical-chat review draft/report")
            checked_receipt(before, after, receipt,
                            reviewed_draft=json.loads(draft_path.read_bytes()),
                            report_bytes=report_path.read_bytes())
        else:
            checked_receipt(before, after, receipt)
        from validate_history import validate_history
        validate_history(after, before)

    # These checks must NOT be skipped merely because the commit is code-only.
    run_id = verify_run(sha)
    import base64
    for path, expected in (("data/history.json", raw),
                           ("protocol-v1.html", protocol_raw)):
        current = github("contents/" + path + "?ref=main")
        check(current.get("encoding") == "base64", "Cannot inspect current main " + path)
        check(base64.b64decode(current["content"]) == expected,
              "Current main file differs from validated commit: " + path)

    public_history_hash = verify_public(raw, url=SITE)
    public_protocol_hash = verify_public(protocol_raw, url=PROTOCOL_SITE)
    checked_at = dt.datetime.now(ZONE).isoformat(timespec="seconds")
    evidence = {
        "verification_status": "CANONICAL_BYTES_VERIFIED",
        "kind": "code_only" if code_only else "new_assessment",
        "head_sha": sha,
        "source_run_id": run_id,
        "history_sha256": public_history_hash,
        "protocol_html_sha256": public_protocol_hash,
        "verified_at": checked_at,
        "scope": "canonical .org HTTPS responses, not only uploaded Pages artifacts"
    }
    audit = ROOT / ".automation-audit"
    audit.mkdir(exist_ok=True)
    (audit / "publication-verification.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    if code_only:
        print("Code-only deployment: validated commit and BOTH canonical files verified; no X announcement")
        return None

    social_receipt = {
        "assessment_date": date,
        "head_sha": sha,
        "source_run_id": run_id,
        "history_sha256": public_history_hash,
        "protocol_html_sha256": public_protocol_hash,
        "verified_at": checked_at
    }
    (ROOT / ".verified-publication.json").write_text(
        json.dumps(social_receipt, indent=2) + "\n", encoding="utf-8")
    print("Gated public assessment verified: " + date)
    return social_receipt


if __name__ == "__main__":
    verify_all()
