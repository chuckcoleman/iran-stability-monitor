# Sunday unattended publication

## Installation state

The repository implementation covers live research, frozen evidence, four prospective
forecasts, a protected pull request and merge, validation-gated Pages publication,
canonical-site verification, and a single deduplicated X scheduling attempt.
**Both production switches remain off unless the owner explicitly enables them.**
Merging this installation does not issue a forecast, replace history, or post to X.

Offline tests exercise the code with synthetic inputs and mocked services. They do
not establish that the owner's installed GitHub App, private key, Metricool API
access, OpenAI subscription, billing, permissions, or live responses work. The read-only readiness run and the
unpublishable live dry-run exist to establish those boundaries before activation.
No new live assessment or social post is part of installation testing.

Frozen Protocol v1.0, all existing history, root metadata, and resolution rules are
unchanged. Additional operational safety checks stop a run; they do not redefine
any scored event or retrospectively change a forecast.

## Live healthcheck lessons (October 12, 2026)

- The GitHub App successfully minted a short-lived installation token after the
  installation owner accepted the updated permissions. Do not create a PAT or
  replace the App key.
- The old readiness guard wrongly used repository metadata
  `permissions.push`, which represents user-style access and can be
  false/absent for an installation token with an explicit write grant. The
  healthcheck now checks the authenticated App's
  `GET /installation/repositories` scope and insists it
  contains exactly the intended repository. The official App-token action itself
  must successfully mint `contents:write` and `pull_requests:write` tokens before
  the script runs. Main ruleset protections still fail closed.
- OpenAI diagnostics now distinguish a failed GitHub OIDC token request, a failed
  exchange at OpenAI's OAuth endpoint, and a failed read of the configured
  model. Only safe stage/status and a validated OAuth **error code** appear in
  logs; neither JWTs nor API tokens nor raw error descriptions are recorded.
- The initial healthcheck exposed a missing GitHub Actions repository secret
  `METRICOOL_API_TOKEN`. Save the owner's actual API token as that exact
  **secret**, not a repository variable, before expecting full readiness.
- The app still does **not** publish unless the independent production switches
  are set to true. Do not enable them before a passing read-only healthcheck and
  unpublishable dry-run.

## Oct 12 read-only healthcheck follow-up

After enabling GitHub App permissions and storing the Metricool secret, the
healthcheck now confirms **GitHub App installation and strict repository
safeguards passed**. Remaining independent failures are the OpenAI token
exchange (`HTTP 401 invalid_grant`) and the Metricool account/read-only
verification (formerly logged as an unhelpful `RuntimeError`).

GitHub's [immutable default OIDC subject
format](https://docs.github.com/en/actions/reference/security/oidc#immutable-subject-claims)
applies to repositories created after July 15, 2026. This repository was created
September 16, 2026, and its owner/repository IDs are `25271226`/`1373559199`.
Its main-branch token is therefore expected to use this **non-secret**
`sub` selector:

```text
repo:chuckcoleman@25271226/iran-stability-monitor@1373559199:ref:refs/heads/main
```

The existing OpenAI mapping was created with the older name-only `sub` claim,
which likely explains `invalid_grant`. The read-only healthcheck now prints
**only allowlisted, non-secret** GitHub OIDC identity selectors (issuer,
audience, subject, repository, ref, workflow_ref, and GitHub numeric IDs)
directly from the JWT payload. It never prints the JWT itself, signature,
bearer token, arbitrary claims, OAuth response body or the API secret.
Verify the actual logged `sub` and `workflow_ref` against the mapping and edit
only the corresponding OpenAI Workload Identity Provider mapping entries.

Metricool diagnostics now report **which read-only stage** failed (brand and
connected X identity, scheduled-post lookup, or published-X export), with only
pre-approved messages or HTTP status codes; no raw response body or secret.
Do not relax the API response checks or create an X post until all three
stages verify as intended. Avoid retrying an ambiguous social POST.

Neither auth diagnostic changes the canonical site, frozen Protocol v1,
existing forecast records, nor live production switches.

## October 12 follow-up: confirmed claims and Metricool profile shape

A read-only `healthcheck` run at 20:50 UTC confirmed that the OpenAI exchange
still returns `401 invalid_grant`, but the actual GitHub OIDC subject is
`repo:chuckcoleman@25271226/iran-stability-monitor@1373559199:ref:refs/heads/main`.
The asserted `iss`, `aud`, `repository`, `ref` and `workflow_ref` match
the intended provider restrictions. Compare **every configured key/value**
on the OpenAI `iran-monitor-main` mapping, especially `sub`; the older
name-only `sub` cannot match this repository's immutable subject.

The Metricool REST API now passes brand lookup and timezone checks, but fails
the exact X account identity check. A separate connected Metricool account
inspection shows the intended `IranStabilityMo` handle; the REST response
structure may differ. The read-only healthcheck emits only a fixed set of
booleans/types/known field-presence markers to establish the actual REST
schema. It never logs raw connected-account fields, arbitrary profile values,
user secrets, response bodies, or API tokens. Do not weaken the exact
`IranStabilityMo` match or schedule any posts until reconciliation.

## October 12: supported Metricool X identity lookup

The Oct 12 read-only healthcheck confirmed that the legacy endpoint
`GET /admin/simpleProfiles` returns the correct brand, owner, and timezone
but **does not provide** the connected X account in `networksData`. This
is expected: the [Metricool OpenAPI specification](https://app.metricool.com/api/swagger.json)
defines that endpoint's response as `PublicBlog`, which has no
`networksData` field. The documented `GET /v2/settings/brands` returns
`JsonOkListResponseBrandLite`; `BrandLite.networksData.twitterData`
is explicitly documented as a string username. The code now queries that
endpoint for both read-only readiness and actual pre-scheduling verification,
keeps the brand ID/user ID/timezone checks, and requires an exact
`IranStabilityMo` identity. **An absent or unexpected X account still blocks
posting.** The change makes no social POST and does not enable production.

The OpenAI WIF exchange remains a separate issue (`HTTP 401 invalid_grant`).
GitHub OIDC `sub` and mapping `iss` have been compared; check the
**provider-level OIDC Issuer URL**, enabled status, mapping selection and
service-account target separately, without disclosing any JWT or credentials.

## October 12: local date query and JSON analytics corrections

The latest read-only healthcheck proved that **GitHub App / Pages / strict
branch protections** and **Metricool's exact IranStabilityMo X connection**
are verified. The remaining Metricool calendar and published-post endpoints
returned HTTP 400. Against [Metricool's published OpenAPI specification]
(https://app.metricool.com/api/swagger.json):

- `GET /v2/scheduler/posts` expects `start` and `end` in
  **local** `YYYY-MM-DDTHH:MM:SS` form and `timezone=America/New_York`
  as a separate query parameter, not date-time values containing UTC offsets.
- `GET /v2/analytics/posts/twitter` likewise documents separate local
  `from`, `to`, and `timezone` values. Its response is
  `JsonOkListResponseTwitterPost` in **JSON**, not a CSV export.
- Published Tweet records have a `text` field and optional `blogId`
  and `username` fields. The duplicate-posting checker now rejects
  missing text, any conflicting known brand or username, and incomplete
  pagination rather than treating them as empty posts.
- A live read-only healthcheck must pass before creating any social post.
  The future one-post-per-assessment claim mechanism and post-publication
  verification remain unchanged. No X post is created by this repair.

OpenAI WIF **still returns HTTP 401 `invalid_grant`** even after aligning
the issuer slash. Its exchange HTTP request agrees with OpenAI's published
`POST /oauth/token` JSON token-exchange reference. Check that the
**saved** OpenAI provider and service-account mapping are enabled,
unambiguous, and associated with the `iran-monitor` service account in
`Default project`; confirm the mapping `iss` has **no trailing slash**.
The incoming GitHub JWT itself has already been verified for `iss`,
`aud`, `sub`, `repository`, `ref`, and `workflow_ref` selectors.
Never share the token or private credential.

## Owner setup: the remaining external boundary

Use repository **Settings → Secrets and variables → Actions**. Never paste a key
into an issue, pull request, source file, public artifact, or ChatGPT message.

| Repository secret | Required access |
|---|---|
| `IRAN_GITHUB_APP_PRIVATE_KEY` | The **complete PEM private key** generated for the dedicated GitHub App (store as a repository secret; never in source control) |
| `METRICOOL_API_TOKEN` | Metricool REST API access for userId `5607453`, brand/blogId `7254821`, X `@IranStabilityMo` |

**GitHub App authentication replaces `AUTOMATION_GH_TOKEN`.** No fine-grained
personal access token is needed. The official `actions/create-github-app-token@v3`
action creates one-hour installation tokens from the dedicated App identity and
private key. The workflow checks the App before paid research, creates **another
fresh token after research** before the protected PR operation, and separately
mints a new token just before any X posting claim. Tokens are scoped to the
current repository and revoked at the end of each job. The App's PEM private key
is long-lived (no routine expiration); replace it if compromised or revoked.

OpenAI authentication uses **GitHub Actions OIDC workload identity federation**, not a long-lived `OPENAI_API_KEY`. The Sunday workflow has `id-token: write`; GitHub mints an ephemeral OIDC token for the configured audience and OpenAI exchanges it for a short-lived service-account token. The OpenAI mapping should match this repository, `refs/heads/main`, and `chuckcoleman/iran-stability-monitor/.github/workflows/sunday-assessment.yml@refs/heads/main`.

Metricool documents REST API access for Advanced or Custom accounts. The existing
connected Metricool ChatGPT app is not an exportable REST API token for Actions.
Do not purchase or enable anything merely because an offline test passed: verify
account access with the read-only check described below.

| Repository variable | Initial value |
|---|---|
| `IRAN_GITHUB_APP_CLIENT_ID` | Optional override: the current non-secret App Client ID (`Iv23liGgGQPahqYbv6in`) is already configured as a workflow default |
| `OPENAI_IDENTITY_PROVIDER_ID` | Optional override; the workflow already contains the current non-secret provider ID |
| `OPENAI_SERVICE_ACCOUNT_ID` | Optional override; the workflow already contains the current non-secret mapped service-account User ID |
| `IRAN_FORECAST_MODEL` | `gpt-6.1-sol`, or a Responses/web-search model explicitly tested in this API project |
| `ASSESSMENT_AUTOMATION_ENABLED` | `false` |
| `AUTO_X_ENABLED` | `false` |

### Create and install the dedicated GitHub App (one-time owner action)

1. In GitHub, open **personal Settings → Developer settings → GitHub Apps → New GitHub App**.
   Name it `Iran Stability Monitor Automation` (or a unique variant).
   Set its homepage URL to `https://iranstabilitymonitor.org`. The automation
   handles no webhooks: disable **Active** in the Webhook section. Leave any
   optional OAuth/authorization callback fields unset.
2. Under **Repository permissions**, grant ONLY: **Contents Read & write**, **Pull
   requests Read & write**, **Actions Read-only**, **Pages Read-only**, **Issues
   Read-only**. **Metadata Read-only** is automatic. Do NOT grant Administration,
   Secrets, Members, Workflows, or organization-wide permissions.
3. Restrict **Where can this GitHub App be installed?** to **Only on this account**.
   Create the App, then use its **Install App** page to install it on account
   `chuckcoleman` with **Only select repositories → iran-stability-monitor**.
4. The Client ID `Iv23liGgGQPahqYbv6in` is already configured as a non-secret
   default in both workflows. No GitHub Actions variable is needed for this App.
   An optional `IRAN_GITHUB_APP_CLIENT_ID` variable can override it if replacing the App.
5. Select **Generate a private key** from the App's settings. A `.pem` file downloads.
   Open the file privately, copy the **entire PEM including BEGIN/END lines**, and
   store it as the GitHub repository **secret** `IRAN_GITHUB_APP_PRIVATE_KEY` under
   **Settings → Secrets and variables → Actions → Secrets**. On desktop you may use
   the optional owner helper with `--app-private-key-file /path/to/downloaded.pem`.
   Never upload the private key to this chat, GitHub issues/PRs, or source control.
6. After installation, run the read-only Actions **healthcheck**. It requests a
   short-lived token and checks the actual App installation, Pages source and
   strict ruleset; also checks OpenAI WIF and Metricool reads. Then run **dry-run**
   before enabling either live switch.

Installation access tokens automatically expire in about one hour. **Nothing
needs to be renewed manually each Sunday**: the official action mints new tokens
for each GitHub work phase. The private PEM is not periodically expiring but
should be rotated promptly if compromised. This does not automate Metricool's own
independent API/connection renewal requirements.

The two OpenAI WIF identifiers are configured as non-secret defaults in `.github/workflows/sunday-assessment.yml`; GitHub Actions repository variables of the same names may override them. **Do not enter access tokens in either field.** WIF still requires a live `healthcheck` and `dry-run` before enabling unattended publication.

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

An optional owner-run helper, `scripts/configure_automation.py`, can store the
non-secret App Client ID, import a downloaded private PEM file directly into a
GitHub secret, prompt for the Metricool token, and strengthen the existing strict
ruleset. It requires an authenticated GitHub CLI administrator and **leaves both
live switches OFF**. Running it is optional; GitHub Settings works on iPhone.

## Readiness and activation

After installation is merged, open **Actions → Prepare Sunday Iran assessment →
Run workflow**. Choose the operation from the dropdown:

1. **`healthcheck`** (compatible alias: `check-services`) — mints a temporary GitHub App token to perform read-only safeguards, and checks OpenAI WIF/model GET access,
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
- Research runs after the GitHub App's initial permissions/safety preflight, but
  before a fresh App installation token is minted for publication. Commits only
  `data/history.json` on a dated branch, opens a PR, waits for the correct Actions
  `validate` job at its exact head SHA, checks `main` again, then merges without
  bypass. GitHub App-authenticated writes trigger CI/deployment unlike writes
  authenticated by the default `GITHUB_TOKEN`. Transient push credentials remain
  process-scoped rather than stored in a Git remote URL or checkout settings.
- Requires successful `validate` and **Deploy validated website** jobs from the
  correct main push workflow and SHA. Checks that the full canonical public JSON
  matches and is not superseded. An attestation records date, SHA, run ID and
  history hash. A code-only merge does not announce a new assessment.
- Re-verifies before X with a distinct newly minted installation token; checks **scheduled posts and the separate published-X CSV**.
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

- [Official GitHub App installation-token action](https://github.com/actions/create-github-app-token)
- [Create a GitHub App](https://docs.github.com/en/apps/creating-github-apps/setting-up-a-github-app/creating-a-github-app)

- [OpenAI GitHub Actions workload identity federation](https://developers.openai.com/api/docs/guides/workload-identity-federation/github-actions)
- [OpenAI Responses web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [OpenAI model catalog](https://developers.openai.com/api/docs/models)
- [GitHub workflow triggering and automation tokens](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- [Metricool API setup](https://help.metricool.com/basic-guide-for-api-integration-r97af)
- [Metricool OpenAPI specification](https://app.metricool.com/api/swagger.json)

Methodology proposals belong only in the non-operative v1.1 research register; this
installation does not activate or amend that register.
