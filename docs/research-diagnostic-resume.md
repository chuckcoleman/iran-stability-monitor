# Recovering an interrupted research diagnostic

The `Iran diagnostics and nonpublishing source rehearsal` workflow is a **read-only, nonpublishing** manual workflow. Its `research-dry-run` mode performs real OpenAI web research and source-only reviews; it never issues scored forecasts or updates the public monitor.

## Normal research diagnostic

From **Actions → Iran diagnostics and nonpublishing source rehearsal → Run workflow**, choose `research-dry-run`. Leave `resume_run_id` empty for an intentional new paid research request. The polling allowance is 1,200 seconds with at most 240 polls; the workflow job has a 45-minute limit. Exceeding a limit is a **failure**, never approval.

## Resume a known background response

If the prior run ended with `background_timeout_no_replay` and preserved its diagnostic artifact, start the same workflow again with:

- `mode`: `research-dry-run`
- `resume_run_id`: the numeric GitHub Actions run ID that contains `integration-diagnostics-<run-id>-<attempt>`, for example `39509619816`.

The workflow downloads that run's diagnostic JSON files before live research. The transport checks that the original recorded request's SHA-256 fingerprint, model, request mode, and known response ID exactly match the new request. If there is an acceptable unique match, it **only issues authenticated GET polls** to the saved response ID. It never retries the chargeable POST. The new run preserves its own diagnostic JSON alongside the recovered history.

**Important:** The research prompt includes the current Eastern date and historical evidence. A later date, changed history, model, payload, incomplete audit, ambiguous response IDs, or terminal failure can make recovery impossible. The workflow **must fail without POST** rather than silently starting new research. Completed background responses are only retrievable while OpenAI retains them; expired or unavailable responses are also failures.

Do not rerun a paid diagnostic without `resume_run_id` unless a new research request and possible additional charge are intentional. A lost CREATE acknowledgment has no reliable response ID and cannot be safely replayed.

## Publication boundary

Neither successfully recovering the response nor passing the research and source-only reviews authorizes publication. Forecast issuance, complete draft review, history mutation, a GitHub pull request, Pages deployment, and social posting remain out of scope. The two-review and all-deterministic-check requirements of the separate publication process are unchanged.
