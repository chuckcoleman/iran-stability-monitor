# Sunday unattended publication

## Installation state

The repository implementation covers live research, frozen evidence, four prospective
forecasts, a protected pull request and merge, validation-gated Pages publication,
canonical-site verification, and a single deduplicated X scheduling attempt.
**Both production switches remain off unless the owner explicitly enables them.**
Merging this installation does not issue a forecast, replace history, or post to X.

Offline tests exercise the code with synthetic inputs and mocked services. They do
not establish that the owner's API keys, subscription, permissions, billing, model
access, or live API response formats work. The read-only readiness run and the
unpublishable live dry-run exist to establish those boundaries before activation.
No new live assessment or social post is part of installation testing.

Frozen Protocol v1.0, all existing history, root metadata, and resolution rules are
unchanged. Additional operational safety checks stop a run; they do not redefine
any scored event or retrospectively change a forecast.

## Owner setup: the remaining external boundary

Use repository **Settings → Secrets and variables → Actions**. Never paste a key
into an issue, pull request, source file, public artifact, or ChatGPT message.

| Repository secret | Required access |
|---|---|
| `AUTOMATION_GH_TOKEN` | A repository-scoped fine-grained token or GitHub App token: Contents read/write, Pull requests read/write, Actions read, Pages read, Issues read, and sufficient read access to inspect repository rulesets; it must be able to merge without bypassing protections |
| `METRICOOL_API_TOKEN` | Metricool REST API access for userId `5607453`, brand/blogId `7254821`, X `@IranStabilityMo` |

OpenAI authentication uses **GitHub Actions OIDC workload identity federation**, not a long-lived `OPENAI_API_KEY`. The Sunday workflow has `id-token: write`; GitHub mints an ephemeral OIDC token for the configured audience and OpenAI exchanges it for a short-lived service-account token. The OpenAI mapping should match this repository, `refs/heads/main`, and `chuckcoleman/iran-stability-monitor/.github/workflows/sunday-assessment.yml@refs/heads/main`.

Metricool documents REST API access for Advanced or Custom accounts. The existing
connected Metricool ChatGPT app is not an exportable REST API token for Actions.
Do not purchase or enable anything merely because an offline test passed: verify
account access with the read-only check described below.

| Repository variable | Initial value |
|---|---|
| `OPENAI_IDENTITY_PROVIDER_ID` | The non-secret ID of the OpenAI GitHub OIDC workload identity provider |
| `OPENAI_SERVICE_ACCOUNT_ID` | The non-secret ID of the mapped dedicated OpenAI project service account |
| `IRAN_FORECAST_MODEL` | `gpt-6.1-sol`, or a Responses/web-search model explicitly tested in this API project |
| `ASSESSMENT_AUTOMATION_ENABLED` | `false` |
| `AUTO_X_ENABLED` | `false` |

The workflow audience is fixed to `https://api.openai.com/v1` and must exactly match the provider configuration. The OpenAI provider and service-account IDs are identifiers, not bearer secrets. Do not store the short-lived WIF access token; each Actions job obtains and exchanges its own GitHub identity token.

In **Settings → Rules → Rulesets → Protect validated forecasts**, keep all existing
protections and enable **Require branches to be up to date before merging** under
the required status check. Keep required pull requests, the Actions `validate`
check, no bypass actors, no force pushes, and no deletion. This installation checks
that strict up-to-date requirement; a missing check stops the pipeline. It prevents
publishing a candidate validated against an out-of-date `main`.

**Pages Source must remain GitHub Actions**, with canonical CNAME
`iranstabilitymonitor.org`. No branch-source deployment is permitted.
**Native repository auto-merge is not needed.** The orchestrator waits for CI and
performs a normal, SHA-guarded merge, never an administrative bypass.

An optional owner-run helper, `scripts/configure_automation.py`, accepts hidden
credential entry and can strengthen the existing strict-check setting. It requires
an authenticated GitHub CLI administrator. Its `--store-secrets` and
`--strict-protection` options are explicit actions, and it leaves both live switches
off. Running it is optional; the same steps can be done in GitHub Settings.

## Readiness and activation

After installation is merged, open **Actions → Prepare Sunday Iran assessment →
Run workflow**. Choose the operation from the dropdown:

1. **`healthcheck`** (compatible alias: `check-services`) — read-only GitHub safeguards, OpenAI WIF exchange/model GET access,
   Metricool brand identity, scheduled calendar, and published-X CSV. It creates no
   forecast, pull request, merge, or post, and does not call paid model inference.
   A pass verifies reads, not Metricool POST delivery or model forecasting quality.
2. **`dry-run`** — real, potentially billable web research, source-metadata capture,
   prospective elicitation and no-web review, then all data checks. Output is marked
   **UNPUBLISHABLE_DRY_RUN** and stored only in a run artifact. Production history,
   branches, PRs, website, and X remain unchanged. This output is never promotable
   into a later live forecast: a live run must capture its own actual evidence times.
3. Inspect the evidence and diagnostic output. After both runs pass and the live
   response formats are verified, set `ASSESSMENT_AUTOMATION_ENABLED=true`.
   Set `AUTO_X_ENABLED=true` only when the brand and both duplicate checks pass.
   The first actual scheduling attempt is checked by readback; it is not falsely
   represented as tested before a real authorized post is made.

`run` is an explicit live operation, allowed only on Sunday while enabled. The
scheduled workflow normally starts at **09:00 America/New_York**. Two UTC cron
entries cover daylight and standard time; the nominal cron is checked against the
Eastern date, so a same-day delayed runner does not accidentally miss the right
slot or run the second slot. GitHub scheduling is not an exact-time guarantee.

The existing ChatGPT Sunday task must not be a second independent writer after
GitHub scheduling is enabled. Use it as a supervisor or disable its publication
path. The GitHub orchestrator refuses a date already present on `main`, a concurrent
run, or an existing dated candidate branch. It never re-elicits already-issued
candidate probabilities to get a more convenient result.

## What a live run does

- Retains exact original history bytes and hashes the frozen inputs. Uses actual
  current reporting, captures accessible article `datePublished` metadata before
  cutoff, and retains source hashes and retrieval times. Model-inferred publication
  clocks are never substituted for verified metadata. Missing or contradictory
  precise times remain unknown; known later sources block the record. Citation
  presence is a provenance check, not independent proof that every claim is true.
- Closes research, records the real cutoff, then elicits exactly four core forecasts
  with web access disabled. A separate no-web review may reject but cannot silently
  revise them. Complete diagnostic scenario partitions are elicited, not generated
  from arbitrary multipliers. Genuine zero revisions may use explained zero
  contributions rather than invented offsets. Declared residuals must reconcile.
- Reuses persistent evidence identities across the archive; applies the frozen
  warning rubric, Houthi rule, six oil-credit components and 0/20/40 sensitivity.
  Monthly Hanke analysis retains a separately identified underlying observation
  date; intermediate Sundays carry the monthly diagnostic forward.
- Requires schema, Protocol validator, offline tests, JavaScript syntax, and
  dashboard-field consistency. No old record or root field may change. Only the
  new, not-yet-committed record receives a captured issuance time; that time equals
  the candidate Git commit's author/committer timestamp. Actual later public
  deployment is independently attested, not backdated.
- Commits only `data/history.json` on a dated branch, opens a PR, waits for the
  correct Actions `validate` job at its exact head SHA, checks `main` again, then
  merges without bypass. A separate authorized automation token is used so the
  subsequent CI/deployment events are not suppressed or left awaiting approval.
- Requires successful `validate` and **Deploy validated website** jobs from the
  correct main push workflow and SHA. Checks that the full canonical public JSON
  matches and is not superseded. An attestation records date, SHA, run ID and
  history hash. A code-only merge does not announce a new assessment.
- Re-verifies before X; checks **scheduled posts and the separate published-X CSV**.
  A unique Git tag `x-announcement-YYYY-MM-DD` atomically reserves the date before
  the non-idempotent Metricool POST. Old issue-based claims remain respected.
  A single future, unoccupied minute is chosen; one ≤280-character post contains
  the assessment date, principal change, two probabilities and dated prior
  comparisons, linking only to `https://iranstabilitymonitor.org`. The returned
  post ID, text, auto-publish status, network and future time must read back exactly.

## Failure and recovery

A failed evidence, clock, arithmetic, archival, CI, permission, source or merge-base
check leaves the candidate unmerged. A failed gated deployment leaves the previous
successful site in place, although the new merge remains in `main`. A social error
does not roll back a validated site.

If a Metricool POST times out or returns an uncertain acknowledgment, the persistent
Git claim remains and automatic retries stop. This is **at-most-one automatic
attempt**, not a claim of exactly-once external delivery. Reconcile the brand's
scheduled and published posts before any manual retry. Do not delete a successful
or uncertain posting tag to silence an error.

Source/issuance artifacts retain 30 days; publication receipts retain 90 days; PR
review-source artifacts retain 7 days. Public history remains in Git. Audit artifacts
contain public evidence and generated judgments, not API keys or full news articles.
Do not publish artifacts from a dry-run as scored forecasts.

Unfamiliar API response schemas fail closed rather than treating missing fields as
success. Readiness detects many permissions/format issues, but subscription or
service changes may still require maintenance. No software can guarantee the truth
of automated geopolitical judgments solely from schema tests or model review.

## References

- [OpenAI GitHub Actions workload identity federation](https://developers.openai.com/api/docs/guides/workload-identity-federation/github-actions)
- [OpenAI Responses web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [OpenAI model catalog](https://developers.openai.com/api/docs/models)
- [GitHub workflow triggering and automation tokens](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- [Metricool API setup](https://help.metricool.com/basic-guide-for-api-integration-r97af)
- [Metricool OpenAPI specification](https://app.metricool.com/api/swagger.json)

Methodology proposals belong only in the non-operative v1.1 research register; this
installation does not activate or amend that register.
