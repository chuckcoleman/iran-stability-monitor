#!/usr/bin/env python3
"""Research -> one-data-file PR -> required CI -> protected, SHA-guarded merge.

Service checks and dry-runs never open a PR, merge, deploy, or schedule X.
A GitHub App installation token is minted on demand, after research and before writes.
"""
import base64
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
import urllib.error
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


def ready(live=True, require_github_token=False):
    """Fail closed for live operations, without requiring a long-lived PAT."""
    if live and os.getenv("ASSESSMENT_AUTOMATION_ENABLED") != "true":
        print("Sunday automation disabled; safely skipped")
        return False
    if live and os.getenv("GITHUB_EVENT_NAME") == "schedule" and not schedule_slot():
        print("Wrong nominal DST cron; safely skipped")
        return False
    if live:
        check(eastern_now().weekday() == 6, "Live assessments may be issued only on Sunday")
    wif = bool(os.getenv("OPENAI_IDENTITY_PROVIDER_ID") and
               os.getenv("OPENAI_SERVICE_ACCOUNT_ID"))
    check(wif or os.getenv("OPENAI_API_KEY"),
          "OpenAI WIF provider/service IDs are missing and no local fallback exists")
    if require_github_token:
        check(os.getenv("GH_TOKEN"), "Short-lived GitHub App installation token missing")
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
    # GitHub's user-style `permissions.push` field does NOT reflect installation-token
    # Contents permission. The token was minted with explicit contents:write
    # and pull_requests:write by create-github-app-token, which fails otherwise.
    # Check the installation-scoped repository list, not that user field.
    installations = gh_json("--paginate", "--slurp", "installation/repositories?per_page=100")
    check(isinstance(installations, list) and installations
          and all(isinstance(p, dict) and isinstance(p.get("repositories"), list)
                  for p in installations), "Cannot inspect GitHub App installation scope")
    allowed = [item.get("full_name") for page in installations
               for item in page["repositories"] if isinstance(item, dict)]
    check(allowed == [repo],
          "GitHub App token must be scoped to exactly the expected repository")
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


def _metricool_read_failure(stage, exc):
    """Return an allowlisted diagnostic; never echo API response bodies."""
    if isinstance(exc, urllib.error.HTTPError):
        return stage + ": HTTP " + str(exc.code)
    safe = {
        "Iran Stability Monitor brand not accessible",
        "Brand timezone mismatch",
        "Unexpected or missing connected X identity",
        "Metricool user identity mismatch",
        "Malformed Metricool network metadata",
        "Unrecognized Metricool list response",
        "Unrecognized Metricool pagination",
        "Metricool returned an incomplete page",
        "Partial Metricool list",
        "Undocumented Metricool pagination",
        "More Metricool pages require reconciliation",
        "Malformed list item",
        "Published TwitterPost missing text",
        "Published TwitterPost belongs to another brand",
        "Published TwitterPost belongs to another X account",
        "Published-post interval is reversed",
    }
    reason = str(exc)
    return stage + ": " + (reason if isinstance(exc, RuntimeError) and reason in safe
                            else type(exc).__name__)


def service_checks():
    """Read-only independent diagnostics: never disclose bearer, JWT, or API response."""
    ready(live=False, require_github_token=True)
    repo = os.environ.get("GITHUB_REPOSITORY", "chuckcoleman/iran-stability-monitor")
    errors = []
    try:
        verify_repository_gate(repo)
        print("GitHub App installation, Pages and strict branch safeguards: VERIFIED")
    except Exception as exc:
        # Messages here are generated by our own gate; do not dump HTTP request data.
        errors.append("GitHub safeguards: " + str(exc))

    from assessment_pipeline import openai_bearer_token
    os.environ['OPENAI_WIF_AUDIT_CLAIMS'] = 'true'
    try:
        bearer = openai_bearer_token()
        print("OpenAI OIDC token exchange: VERIFIED (no paid inference)")
    except Exception as exc:
        if isinstance(exc, (RuntimeError, ValueError)):
            errors.append("OpenAI OIDC/token exchange: " + str(exc))
        elif isinstance(exc, urllib.error.HTTPError):
            errors.append("OpenAI OIDC/token exchange: HTTP " + str(exc.code))
        else:
            errors.append("OpenAI OIDC/token exchange: " + type(exc).__name__)
    else:
        try:
            model = os.getenv("IRAN_FORECAST_MODEL") or "gpt-6.1-sol"
            from urllib.parse import quote
            request = urllib.request.Request(
                "https://api.openai.com/v1/models/" + quote(model, safe=""),
                headers={"Authorization": "Bearer " + bearer})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
            check(data.get("id") == model, "Returned model identity mismatch")
            print("OpenAI model GET " + model + ": VERIFIED (no paid inference)")
        except urllib.error.HTTPError as exc:
            errors.append("OpenAI model GET " + model + ": HTTP " + str(exc.code)
                          + " (check model access and service-account permissions)")
        except Exception as exc:
            errors.append("OpenAI model GET " + model + ": " + type(exc).__name__)

    if not os.getenv("METRICOOL_API_TOKEN"):
        errors.append("Metricool: missing METRICOOL_API_TOKEN repository secret")
    else:
        from metricool_publish import check_brand, scheduled_posts, published_posts
        try:
            check_brand(healthcheck=True)
            print("Metricool brand and connected X identity: VERIFIED (read-only)",flush=True)
        except Exception as exc:
            errors.append(_metricool_read_failure("Metricool brand lookup", exc))
        else:
            day = eastern_now().date().isoformat()
            for stage, query in (
                    ("Metricool scheduled posts", lambda: scheduled_posts(day)),
                    ("Metricool published X export", lambda: published_posts(day))):
                try:
                    query()
                    print(stage + ": VERIFIED (read-only)",flush=True)
                except Exception as exc:
                    errors.append(_metricool_read_failure(stage, exc))
    check(not errors, "; ".join(errors))
    print("READINESS PASSED (read-only). Run dry-run before enabling production.")


def api_probe():
    """Small paid contract test of both Responses paths; never publish results.

    The real WIF credential and full production web-search request contract
    are tested against the API, without eliciting any scored forecast.
    """
    ready(live=False)
    from assessment_pipeline import llm
    path=ROOT / "data/history.json"
    original=path.read_bytes()
    try:
        article,citations=llm(
            "Search the live web for one recent Reuters or AP news article about Iran. "
            "Return ONLY a JSON object with two string fields: title and url. "
            "Cite the original source URL.",True)
        check(isinstance(article,dict) and bool(citations),
              "Responses API probe did not return cited live web evidence")
        print("OpenAI Responses web-search request: VERIFIED (paid, unpublishable)",flush=True)
        result,_=llm(
            "Do not use web search. Return ONLY a JSON object: {\"probe\": true}.",
            False)
        check(isinstance(result,dict) and result.get("probe") is True,
              "Responses API no-search JSON-mode probe was not confirmed")
        print("OpenAI Responses non-search JSON-mode request: VERIFIED",flush=True)
    finally:
        check(path.read_bytes()==original,
              "The unpublishable Responses API probe altered historical data")
    print("API PROBE PASSED; no assessment, PR, merge, deployment or X post",flush=True)


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


def _repo():
    return os.environ.get("GITHUB_REPOSITORY", "chuckcoleman/iran-stability-monitor")


def _candidate_paths():
    audit = ROOT / ".automation-audit"
    return audit, audit / "prepared-candidate.json", audit / "history-exact-before.json"


def _existing_sunday_or_stale_baseline(repo, date):
    base = main_sha(repo)
    check(run("git", "rev-parse", "HEAD").stdout.strip() == base,
          "Checkout is not current protected main")
    source = (ROOT / "data/history.json").read_bytes()
    original = json.loads(source)
    if original["updates"][-1]["date"] == date:
        print("Today's assessment already exists; no new judgment or duplicate PR")
        return None
    check(original["updates"][-1]["date"] < date, "Future assessment in history")
    check((dt.date.fromisoformat(date) -
           dt.date.fromisoformat(original["updates"][-1]["date"])).days == 7,
          "Preceding Sunday missing; manual reconciliation required")
    return base, source, original


def prepare_candidate():
    """Research and validate a candidate; do not authenticate Git writes or issue a forecast yet."""
    if not ready(live=True, require_github_token=True):
        return
    repo = _repo()
    verify_repository_gate(repo)  # Checked with a separate preflight installation token.
    date = eastern_now().date().isoformat()
    prior = _existing_sunday_or_stale_baseline(repo, date)
    if prior is None:
        return
    base, source, original = prior
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
    audit, marker, baseline = _candidate_paths()
    check(baseline.is_file() and baseline.read_bytes() == source,
          "The exact original-history snapshot differs from the checked-out baseline")
    run(sys.executable, "scripts/validate_history.py", "--baseline", str(baseline))
    changed = run("git", "diff", "--name-only").stdout.splitlines()
    check(changed == ["data/history.json"], "Unexpected tracked files changed")
    record = {"date": date, "branch": branch, "base_sha": base,
              "original_sha256": hashlib.sha256(source).hexdigest(),
              "candidate_sha256": hashlib.sha256((ROOT / "data/history.json").read_bytes()).hexdigest()}
    marker.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("Validated provisional Sunday candidate prepared; no GitHub write or public issuance")


def _git_push_with_app_token(branch):
    """Authenticate one git push through process-scoped config, never through a stored URL."""
    token = os.getenv("GH_TOKEN")
    check(token, "Fresh GitHub App installation token is required for push")
    encoded = base64.b64encode(("x-access-token:" + token).encode()).decode()
    env = dict(os.environ)
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: basic " + encoded
    run("git", "push", "origin", branch, env=env)


def publish_candidate():
    """Issue, push, open PR, await CI and merge using a FRESH installation token."""
    if not ready(live=True, require_github_token=True):
        return
    repo = _repo()
    verify_repository_gate(repo)
    audit, marker, baseline = _candidate_paths()
    if not marker.is_file():
        print("No provisional candidate was generated; no GitHub publication action")
        return
    data = json.loads(marker.read_text(encoding="utf-8"))
    date = eastern_now().date().isoformat()
    check(data.get("date") == date, "Candidate date differs from Eastern issuance date")
    branch, base = data["branch"], data["base_sha"]
    check(run("git", "branch", "--show-current").stdout.strip() == branch,
          "Prepared candidate branch changed after research")
    check(main_sha(repo) == base, "Main changed during research; do not publish a stale candidate")
    source = baseline.read_bytes()
    check(hashlib.sha256(source).hexdigest() == data["original_sha256"],
          "Original historical bytes do not match the prepared baseline")
    git_original = subprocess.check_output(["git", "show", "HEAD:data/history.json"], cwd=ROOT)
    check(git_original == source, "Committed historical baseline no longer matches original bytes")
    candidate_raw = (ROOT / "data/history.json").read_bytes()
    check(hashlib.sha256(candidate_raw).hexdigest() == data["candidate_sha256"],
          "Candidate changed after the evidence and forecasting review")
    original = json.loads(source)
    candidate = json.loads(candidate_raw)
    one_append(original, candidate)
    run(sys.executable, "-m", "jsonschema", "-i", "data/history.json", "schema/history.schema.json")
    run(sys.executable, "scripts/validate_history.py", "--baseline", str(baseline))
    check(run("git", "diff", "--name-only").stdout.splitlines() == ["data/history.json"],
          "Unexpected files changed before issuing the record")
    issued = eastern_now().replace(microsecond=0)
    digest = issue_time(ROOT / "data/history.json", original, issued)
    stamp = issued.isoformat()
    # Validate the real recorded issuance timestamp before committing.
    run(sys.executable, "scripts/validate_history.py", "--baseline", str(baseline))
    run("git", "add", "data/history.json")
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    run("git", "commit", "-m", "Append prospective Iran assessment " + date, env=env)
    check(run("git", "show", "-s", "--format=%cI", "HEAD").stdout.strip() == stamp,
          "Commit timestamp mismatch")
    sha = run("git", "rev-parse", "HEAD").stdout.strip()
    (audit / "issuance.json").write_text(json.dumps(
        {"date": date, "base_sha": base, "head_sha": sha,
         "history_sha256": digest, "publication_time": stamp}, indent=2))
    _git_push_with_app_token(branch)
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
    elif cmd == "eligible":
        eligible = ready(live=True)
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as f:
                f.write("eligible=" + ("true" if eligible else "false") + "\n")
        print("Sunday candidate eligibility: " + ("eligible" if eligible else "skipped"))
    elif cmd == "preflight":
        if ready(live=True, require_github_token=True):
            verify_repository_gate(_repo())
    elif cmd == "api-probe":
        api_probe()
    elif cmd == "dry-run":
        dry_run()
    elif cmd == "prepare":
        prepare_candidate()
    elif cmd == "publish":
        publish_candidate()
    else:
        raise SystemExit("Usage: sunday_automation.py healthcheck|eligible|preflight|api-probe|dry-run|prepare|publish")


if __name__ == "__main__":
    main()
