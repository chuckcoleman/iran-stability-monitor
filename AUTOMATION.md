# Sunday unattended publication — installation and audit

## Deployment state

The code implements **two workflows** plus an audited generator and social adapter. It is OFF by default. Do not set the enabling variables until all required credentials, billing, permissions and live smoke tests are complete. No live forecasts or X posts are created merely by merging this configuration.

The frozen Protocol v1.0, previous forecast probabilities, and existing `data/history.json` records remain untouched.

### Schedule

`.github/workflows/sunday-assessment.yml` schedules both 13:00 and 14:00 UTC each Sunday. Runtime rejects the occurrence that is not 09:00 in `America/New_York`, covering DST without manual date conversion. A GitHub Actions scheduled job may begin later than its nominal time due to runner capacity. `workflow_dispatch` supports an authorized manual live run after setup.

### Credentials and variables (repository → Settings → Secrets and variables → Actions)

Create the following **repository secrets**, never committed to Git.

| Name | Purpose |
|---|---|
| `OPENAI_API_KEY` | Paid OpenAI API project key with Responses API and `web_search` access, not the ChatGPT subscription token |
| `AUTOMATION_GH_TOKEN` | Fine-grained GitHub PAT, repository-scoped; metadata read; Contents read/write; Pull requests read/write; Actions read; Pages read; repository rulesets read, plus permission to merge under existing protection |
| `METRICOOL_API_TOKEN` | Metricool REST API token, with API access on an Advanced or Custom plan, linked to the Iran Stability Monitor brand |

Create the following **repository variables**:

| Name | Value |
|---|---|
| `IRAN_FORECAST_MODEL` | `gpt-5.5` (or another web-search-capable Responses model tested in the project) |
| `ASSESSMENT_AUTOMATION_ENABLED` | `true` **only after** credentials and research pipeline are live-tested |
| `AUTO_X_ENABLED` | `true` **only after** Metricool GET/POST and deduplication are tested using the actual account |

The connected Metricool account uses **userId 5607453**, Iran Stability Monitor **blogId 7254821**, X **@IranStabilityMo**, timezone **America/New_York**.

GitHub **Settings → Pages → Build and deployment → Source** must remain **GitHub Actions**, not Deploy from a branch. The preflight checks GitHub's Pages `build_type=workflow` before proposing a forecast. Main must remain protected by a required pull request and the `validate` job; no bypass actors are acceptable.

**Native GitHub auto-merge is NOT required:** the workflow itself waits for the required PR `validate` job to succeed and merges using a SHA guard without an administrative bypass. This avoids enabling repository-wide auto-merge.

### Read-only readiness test (before turning automation on)

After adding all three secrets above, open **GitHub → Actions → Prepare Sunday Iran assessment → Run workflow**, select **healthcheck** (the default), and start the workflow. This tests GitHub Pages source, the enforced PR ruleset, authentication with the OpenAI Models API, and Metricool calendar read access. It creates **no forecast, branch, PR, website change, issue claim, or X post**, and works while both enabling variables are unset. A pass verifies authentication and read permissions only; the first live Sunday run must still prove OpenAI web-search model access and GitHub write/merge rights.

Only after the readiness test succeeds should you set `ASSESSMENT_AUTOMATION_ENABLED=true`. Set `AUTO_X_ENABLED=true` when Metricool posting is also authorized. If X posting fails, the website assessment must remain intact.

### Weekly execution

1. Check date and source configuration, confirm the previous assessment is on `main`, and lock against simultaneous runs.
2. Use the OpenAI Responses API with live web search to collect source-linked observations. Enforce source-citation URLs, at least three publishers and raising, lowering and ambiguous evidence. Carried-forward evidence retains IDs. Missing original source publication times are recorded as **unknown**, never fabricated.
3. Capture the real evidence cutoff **after** research and **before** a second, web-disabled probability elicitation. Capture the four prospective forecasts at completion and record a later issuance timestamp.
4. Freeze the four Protocol-v1 definitions, derive deadlines from Eastern local calendar time, maintain prior prospective `prior_p`, reconcile signed attributions, compute oil-credit 20% overlap and 0/20/40 sensitivity, update nine warning categories and Houthi diagnostics. First-Sunday Hanke probabilities receive monthly treatment.
5. Run JSON Schema, the Protocol v1 validator against the **exact pre-update file**, the full regression suite, and Python syntax checking. No historical record or root field may change.
6. Commit **only** `data/history.json` to a unique Sunday candidate branch, push with a separately authorized PAT (not the default `GITHUB_TOKEN`), and open a PR.
7. Wait for the **actual required `validate` CI job** associated with that SHA. Abort on failure, missing checks, timeout or changed branch. Squash-merge without using admin bypass, only after success.
8. GitHub's existing `Validate and publish monitor` workflow deploys from `main` **only after validation**. A separate `workflow_run` checks both actual jobs succeeded, verifies a single new Sunday record and the entire published `https://iranstabilitymonitor.org/data/history.json` equals the validated commit.
9. If `AUTO_X_ENABLED` is true and the assessment is fresh, check the Metricool calendar for already published/scheduled X announcements. Reserve a persistent one-per-date GitHub issue **before** the non-idempotent POST to Metricool. Schedule a single X post fifteen minutes into the future, at most 280 characters, using the two core probabilities and preceding Sunday comparisons. On uncertain API response, never retry automatically; inspect Metricool manually.

### Failure behavior

- Missing API secret, missing model access, unsupported Metricool API plan, GitHub permissions failure, missing Pages source confirmation, unverified evidence, bad JSON, unexpected earlier history changes, API timeouts, missing CI check, failed CI or deployment, stale or unmatched public site, or existing social posting claim **stops at that boundary**.
- A failed **candidate** never reaches `main`. If a gated Pages deployment fails after the merge, the last successfully deployed site remains public and X is suppressed. That new merge is still in `main`; assess the error before a later attempt.
- A Metricool failure does not roll back the validated site. No repeated X post attempts occur automatically after a possibly successful POST.

### Before switching to unattended production

- Review a dry-run PR, confirm the API reports evidence-rich, plausible source-grounded forecasts and warning language; automated grammar checking is a model task, not an independent proof of truth.
- Exercise tests for the 90-day daylight saving boundary, Feb 29, post-cutoff data, no source citations, duplicate forecasts, baseline mismatch, failed CI, duplicate X post, and failed Metricool response. Offline invariants are covered by `tests/test_sunday_automation.py`; live third-party flows cannot be tested without keys.
- Prefer setting reasonable API usage and spending limits on the OpenAI API project and reviewing the running costs.
- Ensure GitHub repository Issues are enabled; the X deduplication claim uses issues. Do not close/delete claim issues for already scheduled/published assessments.
- If Metricool REST API is not included in your plan, do not set `AUTO_X_ENABLED` until API access exists. The connected Metricool ChatGPT app is **not** a GitHub Actions secret or API token.

### References

- [OpenAI web-search Responses API](https://developers.openai.com/api/docs/guides/tools-web-search)
- [GitHub automation token rules](https://docs.github.com/en/actions/concepts/security/github_token)
- [Metricool REST API setup](https://help.metricool.com/basic-guide-for-api-integration-r97af)
- [Canonical site](https://iranstabilitymonitor.org)

**Not a Protocol revision:** Any future methodology proposals belong only in the nonoperative v1.1 research register.
