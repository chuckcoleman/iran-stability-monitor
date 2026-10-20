# Iran Stability Monitor

Public, timestamped scenario estimates and early-warning indicators for Iran.

## Site structure
- `index.html` — public dashboard
- `data/history.json` — machine-readable, append-only forecast history
- `about.html` — definitions, evidence classes, source and revision policy
- `SOURCE_WATCHLIST.md` — prospective weekly news-source scan and corroboration guidance
- `REPORT_TEST_PROTOCOL.md` — reusable affirmative–critical tests for every report and test artifact
- `special-reports.html` — longer event-driven analyses
- `protocol-v1.html` — frozen prospective forecasting protocol
- `history.html` — full immutable forecast history
- `scripts/validate_history.py` — Protocol v1 publication validator
- `schema/history.schema.json` — machine-readable structural schema
- `.github/workflows/validate.yml` — automatic validation on repository changes
- `assets/` — static CSS/JS

## Protocol
Protocol v1.0 was frozen on 2026-10-03 and applies prospectively beginning with the 2026-10-04 forecast. Substantive methodological changes require a new numbered protocol and are never retroactively applied.

## Publication rule
Historical forecasts should not be silently rewritten. Append a new dated record for each Sunday update. Corrections to factual errors should be explicitly identified.

## GitHub Pages: validation-gated publication
The `.github/workflows/validate.yml` workflow now runs structural,
Protocol v1, JavaScript, and regression checks before its **Deploy validated website**
job may run. It packages only the static HTML, CSS, JavaScript, CNAME, and approved
history JSON. A failed validation job prevents **this workflow's** deployment.

**One GitHub repository setting is required to complete this safeguard:** open
**Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**
rather than **Deploy from a branch**. The current branch-source Pages system can
deploy changes from `main` even when validation fails; adding a gated
workflow does not disable branch-based publishing. Do not claim the public site
is protected until the source setting has been changed and checked.

For stronger integrity, also add a `main` branch protection rule
requiring pull requests and the `validate` status check, and restrict
direct pushes, including by administrators. Without branch protection, an
authorized writer could still bypass or change the validation workflow in
a direct commit.

On GitHub Actions source, the validated deployment runs automatically after a
successful push to `main`; pull-request validation never deploys.
A failed deploy leaves the most recently successful Actions deployment intact.

## Complete validation and review cycles

Before any new Sunday history append is authorized, the candidate must
pass full JSON Schema, frozen Protocol v1, historical immutability, revision
arithmetic and dashboard validation. Correctable failures lead to a
closed-evidence correction and **restart of every validator and both
affirmative/critical reviews** on the exact revised draft. A final full
validation is repeated after both approvals. Only one candidate with clean
validation and two same-draft clean reviews may be submitted. Six cycles
and the review time limit are failure ceilings, not successful outcomes.
Unresolved defects, timeouts, invalid evidence or tool failures stop
publication; no forecast or historical record may be silently changed.

## Sunday research source coverage

From October 25, 2026, each Sunday assessment requires a broad,
topic-specific scan across **reputable international and local media,
original wire reporting, specialist investigations, primary evidence,
independent economic research and security/regional think tanks**.
The search includes Iran International and other Persian-language
reporting, as well as relevant Arabic, Gulf, Israeli, European, US
and Asian outlets. It also looks for contrary and stabilizing evidence.

See [SOURCE_WATCHLIST.md](SOURCE_WATCHLIST.md) for six coverage
categories, an illustrative (not exhaustive) set of organizations,
source-quality rules and the required pre-cutoff coverage audit.
A think-tank opinion is not an observed event; a repeated Reuters/AP
report is not independent corroboration. Record missing or inaccessible
material coverage and never fabricate a source or original publication
time. No outlet is automatically accepted, and no outlet must be cited
just to satisfy a coverage target. The frozen four scored events and
forecast history are unaffected.

## Whole-report alternating validation

Beginning with the October 25 Sunday assessment, the required affirmative
then critical review covers the **entire report**, not just its four
prospective probabilities. The [report-section inventory](scripts/report_section_review.py)
tracks every JSON record field plus individually identified sources,
news events, forecasts, revision rows, warnings, scenario rows, diagnostic
components and dashboard indicators. An incomplete section or test note,
unsupported fact, missing adversarial perspective, mismatched draft hash,
or unreviewed new field blocks publication under the version-3 receipt.
The full Markdown review report must record the section-level results
and the exact matrix SHA-256. After an allowed correction, all automated
tests and both perspectives restart on the new exact draft; any core
scored forecast remains locked.

Supplemental and nonpublishing reports also require affirmative and
critical checks for each material claim, calculation, table and chart,
with NOT TESTED clearly distinguished from PASS. Separately review final
public/social copy before any optional X posting. These operational
review checks do not change frozen forecasting Protocol v1.0, historical
assessments or source cutoff rules. See [REVIEW_POLICY.md](REVIEW_POLICY.md).

## Explicit nonpublishing source-research rehearsal

The separate manual GitHub Actions diagnostic has a
`research-dry-run` option. It uses the configured short-lived
OpenAI workload identity to **test actual research web-search calls**,
the six-category audit, independently attempted article metadata, and
sequential affirmative/critical SOURCE-QUALITY assessments. It retains
real tool-call metadata and URL citations so self-reported model
coverage alone cannot authorize a clean test; source authenticity and
unavailable original release times remain explicitly qualified.

The diagnostic's GitHub permissions are read-only; it receives no
GitHub App writer or Metricool credential. It creates **no forecasts
or assessment history append**, GitHub PR, public website deployment
or X post, even when the test passes. It can run on weekdays without
faking future Sunday dates. A passing research-only result is NOT
end-to-end Sunday forecast certification and must be labeled
`NOT TESTED` for forecasts, live 15-section approvals, browser
rendering, publication and social messaging.

Use `scripts/read_only_research_dry_run.py` for the diagnostic;
see [AUTOMATION.md](AUTOMATION.md) for its exact limitations.
The separately retired GitHub-hosted assessment writer remains disabled.

## Sunday assessment automation (ChatGPT scheduled task)

**No separate computer or local OpenAI API key is required for the configured
ChatGPT-first path.** The existing ChatGPT Scheduled task, `Iran Sunday
Assessment`, is set for Sundays at 09:00 America/New_York starting October 18,
2026. It is instructed to research and close evidence, elicit exactly four
Protocol-v1 forecasts once, then alternate affirmative and critical reviews
until **both approve the same unchanged draft** before any GitHub access.
Failures, timeouts, incomplete reviews or exhausted review limits **never pass**.

After clean reviews it may use the connected GitHub app (subject to connection
permissions and possible write approvals) to submit the candidate and matching
review receipt through a strictly validated pull request. GitHub Actions remains
the **CI/Pages deployment platform, not the assessment writer**. The previous
GitHub Actions Sunday cron and assessment `run`/`dry-run` modes are retired.
The October 18 assessment was published and verified under its historical
single-critical-review policy. **From October 25 onward**, alternate ChatGPT
affirmative and critical perspectives on the same immutable draft, repeating
the entire validation and both reviews after every correction until both
explicitly approve with no issues. Both perspectives are from ChatGPT and must
not be misrepresented as independently executed model instances. A version-3
receipt with round-by-round timestamps, hashes and issues is mandatory.
Any unavailable review or required validation continues to fail closed. Social posting remains separately controlled by
`AUTO_X_ENABLED` and independent post-deployment checks. The optional local
script and complete safeguards are documented in [AUTOMATION.md](AUTOMATION.md).

## Canonical deployment verification

Every successful GitHub Pages deployment, including a code-only release, must
independently retrieve the canonical HTTPS `/data/history.json` and
`/protocol-v1.html` files and compare their **exact bytes** to the validated
checkout. This is separate from verifying the retained Pages upload artifact.
Unavailable responses, unexpected redirects, altered bytes, missing deployment
status, or a changed `main` baseline fail closed. A successful deployment
alone does not demonstrate that the custom domain serves the same content.
A verified code-only release produces an audit record but **never** a social
posting authorization. No retrospective or fabricated forecast is issued to
fill a missed Sunday; the next scheduled assessment remains blocked until
its required preceding-Sunday baseline is valid or a separately authorized
prospective protocol revision supplies an explicit gap policy.

## Automation
For each Sunday assessment, create a working branch and a pull request rather
than committing the proposed forecast record directly to `main`.
Require the PR validation checks to succeed; if they fail, leave the public
assessment unchanged. Merge only the validated change, then verify the gated
Pages deployment succeeded before scheduling the X announcement. Until GitHub
Pages is configured to use **GitHub Actions** as its publishing source, hold
publication and report the required settings change rather than treating a
successful validator run as an effective site publication gate.

Probabilities are analytical judgments, not market prices or official forecasts.

## Validator and regression tests
Run locally from the repository root:

    python -m unittest discover -s tests -v
    python scripts/validate_history.py
    python scripts/validate_history.py --baseline /path/to/previous_history.json

The baseline option compares against an earlier copy, prevents silent rewriting
of archived records and is mutually exclusive with `--baseline-ref GIT_SHA`.
On CI, the workflow supplies the relevant prior Git revision automatically.
If local validation has no baseline, it warns that historical immutability was
not checked.

The validator enforces the frozen Protocol v1 core event definitions, probability
bounds and attribution arithmetic. It checks **every** forecast opening against
the evidence cutoff and publication time, computes calendar-based 90-day and
12-month deadlines (February 29 maps to February 28), and verifies the
**America/New_York** UTC offsets at opening and deadline, including daylight
saving transitions. Evidence cutoff and publication instants may be recorded
in UTC or any timezone with an explicit offset. Nonexistent local DST times
and naive timestamps are rejected.

CI runs the validator and regression tests on both pushes and pull requests,
using complete git history for an append-only comparison against the prior
assessment data. Every dated assessment from October 4, 2026 onward must
declare Protocol v1 and contain four scored core forecasts and four unique,
reconciled revision-attribution records. From the second Protocol v1 forecast
forward, prior percentages must match the immediately preceding prospective
core forecasts; the inaugural record's explicitly retrospective comparison
is not reclassified. Resolutions require a valid Yes/No/indeterminate outcome,
a deadline-consistent date, an explanation, and evidence citations.
Previously issued evidence, warnings, probabilities and protocol definitions
cannot be silently altered. Only additional correction notes (with a date
and reason) and validated per-forecast resolution metadata are permitted on
earlier assessments.

Missing source publication times remain warnings, rather than fabricated
timestamps. Coincident cutoff, forecast opening and publication timestamps
also trigger a warning about provenance; the validator cannot independently
reconstruct when historical judgments were actually formed. The September
2026 pre-v1 assessments retain their original provenance and are not
retroactively classified as Protocol v1 forecasts.

The validator uses Python's standard-library IANA time-zone support. On
Windows without a time-zone database, install the optional package:
`pip install tzdata`.
