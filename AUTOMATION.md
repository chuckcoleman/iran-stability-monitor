# Sunday publication automation — installation state

The Sunday workflow is deliberately **fail-closed** until a real audited research-and-forecast adapter and secure credentials are installed. This is not an operational unattended forecasting system yet. Do not change Protocol v1.0 or historical records to enable it.

## Intended sequence

1. Sunday 09:00 America/New_York: start collection; independently timestamp source publication and event occurrence.
2. Close evidence collection; record the actual cutoff; elicit exactly four forecasts afterward.
3. Build one append-only record with frozen event definitions, calendar deadlines, evidence ledger, reconciled signed revisions, warning categories, China oil-credit 0/20/40 sensitivity, Houthi diagnostics and first-Sunday Hanke diagnostics.
4. Validate against the exact original history and protocol; open a PR; require the repository's validate check.
5. Enable GitHub native auto-merge in Settings → General → Pull Requests, preserving the active required-check ruleset. Do not merge without successful checks.
6. After the gated deployment, compare the public canonical .org JSON against the merged version byte-for-byte or by exact parsed JSON.
7. Only after that verification, schedule one auto-published X post through Metricool brand 7254821. Check existing scheduled and published posts first, and use an idempotency key for the assessment date.

## Required external configuration

- Real, tested research-source provider and credentials: IRAN_RESEARCH_API_KEY.
- Real, tested forecasting provider and credentials: IRAN_FORECAST_API_KEY.
- GitHub App/automation identity with narrowly scoped PR creation and merge permission; GitHub's native auto-merge must be enabled.
- Metricool integration credentials or approved service, scoped to blogId 7254821.
- An independently audited live adapter implementing the above steps, failure recovery, and deduplication.
- Only after a successful end-to-end staging test: ASSESSMENT_AUTOMATION_ENABLED=true.

**Do not set the enable variable yet.** The preparation entry point currently refuses to generate assessments rather than invent forecasts or bypass safety checks. The public verifier is read-only and can run now.

Frozen Protocol v1.0 remains authoritative. Future methodology proposals belong only in the non-operative v1.1 research register.
