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

## GitHub Pages
This is a static site published from the `main` branch and repository root. No build step is required.

## Automation
The Sunday research workflow should append the new structured assessment to `data/history.json` and update special reports only when warranted. The dashboard renders the latest record automatically.

Probabilities are analytical judgments, not market prices or official forecasts.

## Validator and regression tests
Run locally from the repository root:

    python -m unittest discover -s tests -v
    python scripts/validate_history.py

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
assessment data. Previously issued evidence, warnings, probabilities and
protocol definitions cannot be silently altered. Only additional correction
notes (with a date and reason) and per-forecast resolution metadata are
permitted on earlier assessments.

Missing source publication times remain warnings, rather than fabricated
timestamps. Coincident cutoff, forecast opening and publication timestamps
also trigger a warning about provenance; the validator cannot independently
reconstruct when historical judgments were actually formed. The September
2026 pre-v1 assessments retain their original provenance and are not
retroactively classified as Protocol v1 forecasts.

The validator uses Python's standard-library IANA time-zone support. On
Windows without a time-zone database, install the optional package:
`pip install tzdata`.
