# ChatGPT-first Iran Monitor handoff (no separate OpenAI API)

This is the default **human/ChatGPT prepared** path for future Sunday reports.
ChatGPT creates the research, reliability assessment, forecast proposal and
affirmative/critical reviews. The repository **only validates submitted bytes**
and, after a protected merge, GitHub Actions deploys public website files.
Running the validator or submitting a completed handoff does **not** send
an OpenAI Responses request, invoke the paid `api-probe`, or use the
`research-dry-run` OpenAI workflow.

This is **not** a claim that GitHub can call an active ChatGPT conversation,
run background research inside GitHub without API access, or validate the
truth of external article contents merely from self-reported JSON. Research
and both editorial perspectives must actually have been completed in ChatGPT.
If the required capabilities are unavailable, **do not invent the
attestation or publish**.

## Prepare the handoff in ChatGPT

Research all six source categories defined by `SOURCE_WATCHLIST.md`:
`primary_data`, `international_media`,
`regional_multilingual_media`, `specialist_investigative`,
`think_tanks`, `economic_humanitarian_academic`. Seek supportive and
countervailing material and document what was **actually** searched. One
source may occur in several categories; multiple citations to a wire story
are not independent confirmation. Missing originals, release dates and
corroboration must be recorded, not fabricated or replaced with a guessed
timestamp. An empty category is a documented limit, **not** evidence of
stability. None of these categories imposes an accepted-evidence quota.

Freeze the original evidence as-of instant, exact original URL links,
claim passages and reporting-chain identities. Prepare the V10 conservative
factual reliability assessment for **every newly admitted claim**: both
affirmative and critical perspectives assess original-source quality,
directness, independent claim-matched corroboration and contradictions.
A source reputation alone does not set a grade. The lower supported factual
grade prevails, and confirmation counts only if both perspectives identify
the same independently authored original claim and passage. Record
`geopolitical_direction_confidence` separately.

Only after the source review is actually complete should ChatGPT issue
the four scored Protocol-v1 event forecasts **once**. Review the full
15-section prospective report using both perspectives on the same hashed
draft, with deterministic validation before and after the reviews. If
either perspective fails or an original source is missing, mark the report
inconclusive/rejected; **no publication or probability is authorized by a
source-only result**.

## Bundle layout

Construct this directory **outside** the checked-out public GitHub
repository. The original history must match the current `main` copy
byte-for-byte. No file is generated or signed automatically on behalf of
ChatGPT; populate fields from real completed work.

```text
approved-handoff/
  history-before.json
  data/
    history.json
    review-receipts/YYYY-MM-DD.json
    review-drafts/YYYY-MM-DD.json
    review-reports/YYYY-MM-DD.md
    source-dossiers/YYYY-MM-DD.json
```

- `history-before.json`: unchanged preceding `data/history.json`.
- `data/history.json`: exactly one newly appended Sunday assessment;
  archived records/protocol unchanged. Never rewrite older observations.
- `review-drafts`: the full **pre-final-publication-timestamp** draft that
  was actually reviewed; it must match the final candidate in all other
  fields, including locked probabilities and evidence.
- `review-reports`: the real full 15-section, same-SHA affirmative/critical
  review with source and arithmetic checks, issues, provenance and all
  required headings.
- `review-receipts`: prospective receipt version 3 with provenance
  `chatgpt_alternating`, mode `affirmative_then_critical_chat`,
  `reviewer_provenance: one_chatgpt_session_two_perspectives`, exact
  hashes, times, round inventories, both clean reviews, and two extra fields:
  `research_mode: chatgpt_first_no_api` and
  `source_dossier_sha256: <sha256 of canonical dossier JSON>`.
- `source-dossiers`: complete source, original passage and claim-level
  reliability metadata, as detailed below.

The `review_receipt.py` validator authenticates record **consistency**
with the supplied report and receipt, not that the report was actually
written, read or approved by two genuinely independent agents. ChatGPT
editorial perspectives remain **one ChatGPT session**, not independent
model instances.

## Exact source-dossier structure

The JSON object has these top-level fields:

| Field | Value or requirement |
|---|---|
| `version` | integer `1` |
| `mode` | `chatgpt_first_no_api` |
| `research_provenance` | `CHATGPT_RESEARCH_REPORTED_NOT_API_WEB_SEARCH_TRACE` |
| `baseline_sha256` | canonical JSON SHA-256 of `history-before.json` |
| `candidate_sha256` | canonical JSON SHA-256 of `data/history.json` |
| `research_as_of` | exactly the candidate's closed `assessment_evidence_cutoff` |
| `source_review_completed_at` | actual offset-aware instant after cutoff and before forecast opening |
| `post_snapshot_interval` | `NOT_SEARCHED` |
| `provenance_limitations` | at least 80 characters honestly disclosing what ChatGPT/structural checks cannot verify |
| `coverage` | exactly six rows, one for each required category |
| `source_review_packet` | original V10 pre-review source/claim packet, with `pre_review_admission_version: 7`, matching cutoff and baseline hash |
| `affirmative_source_review` | recorded clean independent source-review perspective |
| `critical_source_review` | recorded clean critical source-review perspective |
| `claim_reliability` | deterministic dual-review result from `reconcile_dual_reliability` |

Each `coverage` row has `category`, actually attempted
`queries` (nonempty descriptive strings), `outcome` from the standard
eligible/searched-none/inaccessible statuses, `original_urls` of
canonical cited public HTTPS documents (can be empty), and `limitations`.
The `source_review_packet.source_quality_audit.sources` list must contain
**each unique URL**, including background items, with source/origin class,
`access_status`, `first_publication_clock_status`, independent
corroborating source URLs (or `[]`), and specific assessment/limitations.

`source_review_packet.evidence` has **every newly proposed accepted
claim as originally frozen**, with an unchanged original claim ID and
the model/editor's original, explicitly provisional `reliability`.
The packet's `pre_review_claim_decisions` binds every ID to its
original source, a 4–25-word exact original article-body passage,
64-digit SHA-256 of the independently recorded original HTML source body,
and admission status. This digest is a **provided provenance assertion**,
not independent confirmation of the remote publisher's bytes. Do not
fabricate the passage or hash: if unavailable, keep the observation
excluded, rather than submitting a false eligible witness.

Each source-review perspective must contain `approved:true`,
`issues:[]`, one substantively reviewed `source_reviews` entry for
**every** canonical source URL, and one `claim_reliability_reviews`
entry per retained evidence ID (see
`scripts/source_claim_reliability.py`). The dossier's final
`claim_reliability` rows and the published newly added evidence grades,
`reliability_basis`, and `geopolitical_direction_confidence` must
**exactly match** the conservative algorithm. Carried-forward evidence
must match original history exactly apart from status. The original
quality audit, claims, factual grades, source identifiers, and cutoff
are never rewritten to manufacture agreement.

## Validation and submission

On a trusted checkout containing the `main` baseline, run:

```bash
python scripts/chatgpt_handoff.py --handoff /absolute/path/approved-handoff
```

This command is **offline** and read-only. It verifies all seven supplied
files, including full report receipt, V10 source/claim rubric, original
historical integrity, reference chronology, four scored forecasts,
deterministic history, JSON Schema and dashboard safety. It makes **zero**
OpenAI API requests and **zero GitHub writes**.

To submit after the successful check, the existing guarded entry point
can open a PR:

```bash
python scripts/submit_reviewed_assessment.py --handoff /absolute/path/approved-handoff
```

This requires a configured trusted GitHub CLI on the submitter's computer.
It stages **all five** candidate/review/dossier files under `data/`,
rechecks the imported bytes, verifies the exact `main` baseline and
repository protections, opens a PR, then leaves the merge to protected
CI and the repository owner. It never calls OpenAI. There is no
automatic `--merge` in the default path. If ChatGPT uses a connected
GitHub app instead of the local CLI, submit those same five files as a PR;
the CI receipt validator will reject missing or changed artifacts.

The GitHub CI `validate.yml` automatically verifies a source dossier
**only** when the prospective v3 receipt explicitly opts into
`research_mode: chatgpt_first_no_api`. Existing V1–V9 and historical
review receipts retain their original immutable validation regime;
adding this new mode never upgrades a past source claim or forecast.

## API fallback and truthful limits

The existing `sunday-assessment.yml` diagnostic
`research-dry-run` and `api-probe` remain **explicitly paid** API
modes. A GitHub Actions script cannot call a ChatGPT subscription/chat
as a substitute for an API endpoint. The ChatGPT-first workflow requires
ChatGPT to actually perform and hand off work; it does **not** run ChatGPT
inside CI. Deterministic GitHub schema checks do not verify external
source truth, real independent reporting chains, human approval or the
actual occurrence of claimed ChatGPT web searches. Any such uncertainty
must be noted and cause a failed publication decision when material.
