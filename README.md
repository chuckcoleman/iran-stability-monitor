# Iran Stability & Escalation Monitor

Public, timestamped scenario estimates and early-warning indicators for Iran.

## Site structure
- `index.html` — public dashboard
- `data/history.json` — machine-readable, append-only forecast history
- `about.html` — definitions, evidence classes, source and revision policy
- `special-reports.html` — longer event-driven analyses
- `assets/` — static CSS/JS

## Publication rule
Historical forecasts should not be silently rewritten. Append a new dated record for each Sunday update. Corrections to factual errors should be explicitly identified.

## GitHub Pages
This is a static site. Enable GitHub Pages for the repository using the `main` branch and root (`/`) directory. No build step is required.

## Automation
The Sunday research workflow should append the new structured assessment to `data/history.json` and update special reports only when warranted. The dashboard renders the latest record automatically.

Probabilities are analytical judgments, not market prices or official forecasts.