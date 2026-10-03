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
