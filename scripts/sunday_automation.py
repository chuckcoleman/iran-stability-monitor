#!/usr/bin/env python3
"""Research -> one-data-file PR -> required CI -> protected, SHA-guarded merge.

Service checks and dry-runs never open a PR, merge, deploy, or schedule X.
A separate repository-scoped automation token is required for unattended CI.
"""
import datetime as dt
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

from candidate_checks import issue_time, one_append, scheduled_slot

ROOT = Path(__file__).resolve().parent.parent
ZONE = ZoneInfo("America/New_York")


def check(value, message):
    if not value:
        raise RuntimeError(message)


def run(*args, check_result=True, env=None):
    p = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, env=env)
    if check_result and p.returncode:
        raise RuntimeError("Command failed: " + " ".join(args[:3]) + "; inspect the run log")
    return p


def gh(*args):
    return run("gh", *args).stdout.strip()


def gh_json(*args):
    return json.loads(gh("api", *args))


def eastern_now():
    return dt.datetime.now(dt.timezone.utc).astimezone(ZONE)


def schedule_slot(now=None, cron=None):
    now = now or eastern_now()
    return scheduled_slot(now.date(), cron or os.getenv("GITHUB_EVENT_SCHEDULE", ""), now)


def ready(live=True):
    if live and os.getenv("ASSESSMENT_AUTOMATION_ENABLED") != "true":
        print("Sunday automation disabled; safely skipped")
        return False
    if live and os.getenv("GITHUB_EVENT_NAME") == "schedule" and not schedule_slot():
        print("Wrong nominal DST cron; safely skipped")
        return False
    if live:
        check(eastern_now().weekday() == 6, "Live assessments may be issued only on Sunday")
    for name in ("OPENAI_API_KEY", "AUTOMATION_GH_TOKEN"):
        check(os.getenv(name), "Required secret missing: " + name)
    check(os.getenv("GH_TOKEN") == os.getenv("AUTOMATION_GH_TOKEN"), "Automation gh token mismatch")
    return True


def protects_main(rule):
    condition = rule.get("conditions", {}).get("ref_name", {})
    includes, excludes = condition.get("include", []), condition.get("exclude", [])
    matches = lambda x: x in ("~DEFAULT_BRANCH", "~ALL") or fnmatch.fnmatchcase("refs/heads/main", x)
    if not any(matches(x) for x in includes) or any(matches(x) for x in excludes):
        return False
    if rule.get("enforcement") != "active" or rule.get("bypass_actors"):
        return False
    rules = rule.get("rules", [])
    kinds = {x.get("type") for x in rules}
    if not {"pull_request", "required_status_checks", "deletion", "non_fast_forward"}.issubset(kinds):
        return False
    return any(x.get("type") == "required_status_checks"
               and x.get("parameters", {}).get("strict_required_status_checks_policy") is True
               and any(c.get("context") == "validate" and c.get("integration_id") == 15368
                       for c in x["parameters"].get("required_status_checks", [])) for x in rules)


def verify_repository_gate(repo):
    pages = gh_json("repos/" + repo + "/pages")
    check(pages.get("build_type") == "workflow", "Pages Source must be GitHub Actions, not a branch")
    details = gh_json("repos/" + repo)
    check(details.get("default_branch") == "main", "Unexpected default branch")
    check(details.get("permissions", {}).get("push") is True, "Token lacks repository write access")
    summaries = gh_json("--paginate", "--slurp", "repos/" + repo + "/rulesets?per_page=100")
    check(isinstance(summaries, list) and all(isinstance(x, list) for x in summaries), "Cannot inspect all rulesets")
    rules = [gh_json("repos/" + repo + "/rulesets/" + str(x["id"]))
             for page in summaries for x in page if x.get("enforcement") == "active"]
    check(any(protects_main(x) for x in rules),
          "Require PRs, Actions validate, up-to-date branches, no bypass, no deletion and no force pushes on main")


def main_sha(repo):
    return gh_json("repos/" + repo + "/git/ref/heads/main")["object"]["sha"]


def wait_checks(repo, branch, sha, seconds=1800):
    stop = time.monotonic() + seconds
    while time.monotonic() < stop:
        data = gh_json("repos/" + repo + "/actions/runs", "-X", "GET",
                       "-f", "event=pull_request", "-f", "branch=" + branch, "-f", "per_page=100")
        matching = [x for x in data.get("workflow_runs", []) if x.get("head_sha") == sha
                    and x.get("path") == ".github/workflows/validate.yml"]
        if matching:
            latest = max(matching, key=lambda x: x["id"])
            if latest.get("status") == "completed":
                check(latest.get("conclusion") == "success", "PR CI failed; do not merge")
                jobs = gh_json("repos/" + repo + "/actions/runs/" + str(latest["id"]) + "/jobs?per_page=100")
                checks = [x for x in jobs.get("jobs", []) if x.get("name") == "validate"]
                check(len(checks) == 1 and checks[0].get("conclusion") == "success", "Required validate job did not succeed")
                return latest["id"]
        time.sleep(15)
    raise RuntimeError("Timed out waiting for PR CI; candidate remains unmerged")


def service_checks():
    ready(live=False)
    repo = os.environ.get("GITHUB_REPOSITORY", "chuckcoleman/iran-stability-monitor")
    errors = []
    try:
        verify_repository_gate(repo)
        print("GitHub Pages and branch safeguards: verified")
    except Exception as exc:
        errors.append("GitHub safeguards: " + str(exc))
    try:
        model = os.getenv("IRAN_FORECAST_MODEL") or "gpt-6.1-sol"
        from urllib.parse import quote
        request = urllib.request.Request("https://api.openai.com/v1/models/" + quote(model, safe=""),
                  headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        check(data.get("id") == model, "Configured OpenAI model was not verified")
        print("OpenAI key and model: GET access verified; no paid inference performed")
    except Exception:
        errors.append("OpenAI model/key GET check failed")
    try:
        from metricool_publish import check_brand, scheduled_posts, published_posts
        check(os.getenv("METRICOOL_API_TOKEN"), "METRICOOL_API_TOKEN missing")
        check_brand()
        day = eastern_now().date().isoformat()
        scheduled_posts(day)
        published_posts(day)
        print("Metricool brand, scheduled and published reads: verified; no post created")
    except Exception as exc:
        errors.append("Metricool read checks: " + type(exc).__name__)
    check(not errors, "; ".join(errors))
    print("READINESS PASSED (read-only). Run dry-run before enabling production.")


def dry_run():
    """Real API research with NO public side effects. Output cannot be promoted."""
    ready(live=False)
    from assessment_pipeline import produce, llm
    from candidate_checks import dashboard_record
    from validate_history import validate_history
    from jsonschema import Draft202012Validator
    source = (ROOT / "data/history.json").read_bytes()
    history = json.loads(source)
    today = eastern_now().date().isoformat()
    # Same-day repetition is allowed only in this isolated, never-published test.
    if history["updates"][-1]["date"] == today:
        history["updates"] = history["updates"][:-1]
    check(history["updates"] and history["updates"][-1]["date"] < today, "No usable dry-run baseline")
    candidate = produce(history, reviewer=llm)
    validate_history(candidate, history)
    Draft202012Validator(json.loads((ROOT / "schema/history.schema.json").read_bytes())).validate(candidate)
    dashboard_record(candidate["updates"][-1], history["updates"][-1])
    audit = ROOT / ".automation-audit"
    audit.mkdir(exist_ok=True)
    (audit / "dry-run-result.json").write_text(json.dumps({"mode": "UNPUBLISHABLE_DRY_RUN",
        "production_history_sha256": hashlib.sha256(source).hexdigest(), "candidate": candidate},
        ensure_ascii=False, indent=2), encoding="utf-8")
    check((ROOT / "data/history.json").read_bytes() == source, "Dry-run altered production history")
    print("DRY-RUN PASSED; no PR, merge, deployment or X post was made")


def prepare_and_merge():
    repo = os.environ.get("GITHUB_REPOSITORY", "chuckcoleman/iran-stability-monitor")
    verify_repository_gate(repo)
    date = eastern_now().date().isoformat()
    base = main_sha(repo)
    check(run("git", "rev-parse", "HEAD").stdout.strip() == base, "Checkout is not current main")
    source = (ROOT / "data/history.json").read_bytes()
    original = json.loads(source)
    if original["updates"][-1]["date"] == date:
        print("Today's assessment already exists; no new judgment or duplicate PR")
        return
    check(original["updates"][-1]["date"] < date, "Future assessment in history")
    check((dt.date.fromisoformat(date)-dt.date.fromisoformat(original["updates"][-1]["date"])).days == 7,
          "Preceding Sunday missing; manual reconciliation required")
    branch = "sunday-auto-" + date.replace("-", "")
    check(not run("git", "ls-remote", "--heads", "origin", branch).stdout.strip(),
          "Existing candidate branch: retain its issued forecasts; reconcile instead of regenerating")
    check(not run("git", "status", "--porcelain").stdout.strip(), "Working tree not clean")
    run("git", "config", "user.name", "Iran Stability Monitor Automation")
    run("git", "config", "user.email", "automation@users.noreply.github.com")
    run("git", "checkout", "-b", branch)
    run(sys.executable, "scripts/assessment_pipeline.py", "prepare")
    candidate = json.loads((ROOT / "data/history.json").read_bytes())
    one_append(original, candidate)
    run(sys.executable, "-m", "jsonschema", "-i", "data/history.json", "schema/history.schema.json")
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v")
    run("node", "--check", "assets/app.js")
    run(sys.executable, "scripts/validate_history.py", "--baseline", ".automation-audit/history-exact-before.json")
    check(main_sha(repo) == base, "Main changed during research; do not publish against a different baseline")
    changed = run("git", "diff", "--name-only").stdout.splitlines()
    check(changed == ["data/history.json"], "Unexpected tracked files changed")
    issued = eastern_now().replace(microsecond=0)
    digest = issue_time(ROOT / "data/history.json", original, issued)
    stamp = issued.isoformat()
    run("git", "add", "data/history.json")
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    run("git", "commit", "-m", "Append prospective Iran assessment " + date, env=env)
    check(run("git", "show", "-s", "--format=%cI", "HEAD").stdout.strip() == stamp, "Commit timestamp mismatch")
    sha = run("git", "rev-parse", "HEAD").stdout.strip()
    (ROOT / ".automation-audit/issuance.json").write_text(json.dumps(
        {"date": date, "base_sha": base, "head_sha": sha, "history_sha256": digest, "publication_time": stamp}, indent=2))
    run("git", "push", "origin", branch)
    url = gh("pr", "create", "-R", repo, "--base", "main", "--head", branch,
             "--title", "Prospective Iran assessment " + date,
             "--body", "One append-only Protocol-v1 record. Required Actions validation and strict up-to-date branch protection must pass. No bypass authorized.")
    print("Candidate PR: " + url)
    wait_checks(repo, branch, sha)
    verify_repository_gate(repo)
    check(main_sha(repo) == base, "Main changed before merge; strict CI requires a new review")
    gh("pr", "merge", url, "-R", repo, "--squash", "--match-head-commit", sha)
    print("Protected merge completed; deployment and X require independent post-merge verification")


def main():
    cmd = sys.argv[1] if len(sys.argv) == 2 else ""
    if cmd in ("check-services", "healthcheck"):
        service_checks()
    elif cmd == "preflight":
        return 0 if ready() else 3
    elif cmd == "dry-run":
        dry_run()
    elif cmd == "run":
        if ready():
            prepare_and_merge()
    else:
        raise SystemExit("Usage: sunday_automation.py check-services|dry-run|run")


if __name__ == "__main__":
    main()
