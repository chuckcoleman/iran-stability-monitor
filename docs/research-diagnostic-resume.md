# Checkpointed research diagnostics and recovery

The manual **Iran diagnostics and nonpublishing source rehearsal** workflow gathers live sources but does **not** issue forecasts, change `data/history.json`, publish the website, or post to social media.

## How the staged source sweep works

The source inquiry is now six independent and separately journaled searches:

1. Primary and official observations.
2. Independent international reporting.
3. Regional and multilingual reporting.
4. Specialist investigation, shipping, energy and rights monitoring.
5. Research institutes and think tanks.
6. Economic, humanitarian and academic evidence, including credible counterevidence.

Each search produces exactly one coverage row, zero to four evidence candidates, explicit source-quality annotations, a real web-search trace, and a redacted OpenAI request journal. Stages can report no eligible evidence without inventing any. Checkpoints `research-batch-<category>.json` are saved as soon as each stage completes; the diagnostic artifact preserves them on subsequent failure. No category is silently omitted. Conflicting duplicated source classifications cause failure rather than unreviewed promotion to evidence.

Before **any** research request, `research-snapshot.json` freezes the originally intended Eastern date, historical evidence digest, model and cutoff. On recovery, the same original prompt, source bound and evidence baseline are required. Source retrieval on a later recovery date is recorded truthfully as later retrieval, while demonstrably post-snapshot published sources are prohibited. Unverifiable first-publication times remain explicitly uncertain.

Only after all six valid stages are assembled may citation reconciliation, original-source metadata gathering, evidence freezing and **both** source-only reviews proceed. An unverified URL, failed category, incomplete response, timeout, conflicting annotations, failed review, or missing audit blocks approval.

## Running a new staged diagnostic

Open **Actions → Iran diagnostics and nonpublishing source rehearsal → Run workflow**, choose `research-dry-run`, leave `resume_run_id` empty and start. This intentionally starts new paid API calls as the six stages are reached. Completed stages may take several minutes and are retained even when a later stage cannot finish. The 45-minute job budget and bounded individual API polling remain safety limits, not measures of analytic validity.

## Continuing a staged run

For an interrupted **staged** run, choose the same mode and set `resume_run_id` to its GitHub Actions run ID. The workflow downloads its diagnostic artifact first. All completed stage/checkpoint records are revalidated and reused without another POST. For a pending, acknowledged Responses ID whose **full original request fingerprint** matches, polling continues through GET requests only. A source category not yet begun can make its first new paid POST; continuing the complete sweep is **not guaranteed to be cost-free**. A previously submitted request with unknown acceptance must not be posted again.

The original snapshot is mandatory. A changed original history baseline, changed model/prompt, unreadable artifact, ambiguous response IDs, terminal failed response or missing prior snapshot causes **fail-closed**, never an invented pass. An expired provider response can be unrecoverable. The diagnosis includes exact stage completion and limitations.

**Old monolithic diagnostics such as runs `39509619816` and `39522021887` contain no six-stage research snapshot; they cannot be resumed through this staged mode.** Entering one of those IDs is rejected before any new paid POST. Run a new staged diagnostic first; if it is interrupted, use *that* run's ID to continue.

All stages and reviews in this workflow remain **nonpublishing**. Passing these checks is not permission to make forecasts or deploy anything. The independent publication process retains its full validation and dual-review requirements.
