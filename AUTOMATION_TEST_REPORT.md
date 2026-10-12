# Automation test report — October 11, 2026

## Completed locally

100 offline tests passed, including a five-week sequence crossing the first Sunday
of November and the Eastern daylight-saving transition. Tests use synthetic
judgments and mocked external services; no real forecast or X post was issued.

JSON Schema validation, the frozen Python validator against the exact original
history, Python compilation, JavaScript syntax and YAML parsing passed.

The existing history file, root metadata, frozen Protocol v1 page, frozen validator,
schema, README, public JavaScript, CNAME, and original validator regression tests
are unchanged byte-for-byte.

## Not yet live-tested

OpenAI paid inference, the owner's actual credentials and spending settings,
GitHub unattended merge permissions, Metricool subscription/API response formats,
and a real X scheduling write require owner-authorized service access. A green
unit-test run is not evidence that these external prerequisites are configured.

The workflow provides read-only `check-services` and a paid, unpublishable `dry-run`
for that boundary. Both live enable flags remain off by default. GitHub PR CI must
also pass on the exact reviewed commit before installation is merged.

No changes to historical probabilities or frozen Protocol v1 were made.

## October 12 — GitHub App authentication migration

Replaced the personal-access-token dependency with the GitHub-owned
`actions/create-github-app-token@v3`. A first token checks repository readiness,
a **fresh** token is minted after research for the protected PR write/merge, and a
separate token is minted after Pages verification for one X-posting claim.
Offline tests include token phase ordering, scoped Git authentication, disabled-mode
behavior, no candidate = no write, and social publication gating.

Actual GitHub App installation, private key, token minting, permissions, model
billing, Metricool API and live posting are **not yet tested**. They require owner
installation and credentials. No historical forecast or frozen Protocol v1 change.
