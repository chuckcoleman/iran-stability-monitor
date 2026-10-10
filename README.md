# Iran Stability Monitor

Public, timestamped scenario estimates and early-warning indicators for Iran.

## Site structure
- `index.html` — public dashboard
- `data/history.json` — machine-readable, append-only forecast history
- `about.html` — definitions, evidence classes, source and revision policy
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
