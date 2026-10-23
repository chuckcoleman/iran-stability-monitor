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

Before freezing the source snapshot, **research promising evidence more
deeply**. After the six-category scan, identify relevant adverse, stabilizing
and contradictory leads; trace underlying data, dates, populations, methods
and common reporting chains; look for genuine primary corroboration and
challenging observations. Document the actual follow-up queries, original
source URLs, the result for each promising lead, and unresolved capture or
publication-time limitations in the working source audit. A held or
contradicted lead remains contextual, not a newly admitted observation.
Any discovered URLs proposed for citation must join the six-category
coverage and source-quality inventories. Both source-review perspectives
must inspect this follow-up before any forecast. The research cutoff is
immutable: later inspection cannot retroactively add sources to it.
This research stage introduces no accepted-evidence quota or shortcut
around raw HTML proof, conservative V10 grades or the preforecast seal.

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
  source-captures/
    E-YYYYMMDD-NN.html  # local-only, NEVER staged/published
  DO_NOT_PUBLISH.txt   # optional test-only marker, forbidden in production
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
  hashes, times, round inventories, both clean reviews, and three MANDATORY
  fields for new October 25+ records: `research_mode: chatgpt_first_no_api`,
  `source_dossier_sha256: <sha256 of canonical dossier JSON>`, and
  `preforecast_certificate_sha256: <sha256 of source-only certificate>`.
  Omitting the mode never opts out of V10 source review.
- `source-dossiers`: complete source, original passage and claim-level
  reliability metadata, as detailed below.
- `source-captures`: bounded original HTML bytes for each admitted claim,
  named by evidence ID, retained outside the repository; the guarded local
  validator recomputes their original-body SHA-256, visible-text digest and
  exact quotation character offset. Never commit entire copyrighted articles
  to the public repository or deploy them. Missing local captures fail closed.
  GitHub CI can check archived digest/metadata consistency only, NOT independently
  authenticate publisher content after private raw bytes are withheld.
- `DO_NOT_PUBLISH.txt` or any equivalent test-only marker blocks real
  submissions, as do obvious synthetic claim texts and reserved test hosts.

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
| `preforecast_certificate` | hash-bound source-only snapshot (original research packet, both source perspectives and reconciled factual grade certificate), closed BEFORE any forecast |

Each `coverage` row has `category`, actually attempted
`queries` (nonempty descriptive strings), `outcome` from the standard
eligible/searched-none/inaccessible statuses, `original_urls` of
canonical cited public HTTPS documents (can be empty), and `limitations`.
The `source_review_packet.source_quality_audit.sources` list must contain
**each unique URL**, including background items, with source/origin class,
`access_status`, `first_publication_clock_status`, independent
corroborating source URLs (or `[]`), and specific assessment/limitations.
Each row now also includes `access_channels` for the distinct search,
metadata HTTP and original article-body stages, with explicit original
claim IDs, stage limitations and `same_stage_conflicts: []`. Differences
ACROSS stages are not automatically contradictions; inconsistent HTTP
outcomes WITHIN a metadata stage or unresolved same-stage discrepancies
fail closed. Both reviewers must explicitly discuss these stages.

### Machine-enforced promising-evidence follow-up

The source packet MUST contain `promising_evidence_followup` for all
prospective October 25, 2026 and later V10 assessments. It is sealed by
the existing preforecast certificate's `source_packet_sha256`. The object
has `version: 1`, `research_as_of` equal to the frozen cutoff, and a
`leads` list covering **every distinct URL** in the existing six-category
coverage and source-quality inventories, including context and exclusions.

Each lead has `source_url`, `triage` (`promising`, `context_only`, or
`excluded`), `priority` (high/normal/low), `relevance`,
`admitted_evidence_ids`, and `followup`. Nonpromising leads have no
admitted IDs and `followup: null`. Every promising lead has an actual
offset-aware `performed_at` no later than the cutoff and a final
`disposition` of `ready_for_v10_source_review`, `held_unverified`,
`contradicted`, or `context_only`. It must document separate
`upstream_queries` and `counter_queries`, `checked_urls` (including
the source URL), `upstream_source_urls`, `contrary_source_urls`, and
`scope` with geography, time window, population/denominator and
method/inclusions. It must also give substantive `reporting_chain`,
`supporting_findings`, `counterevidence_findings`, and `limitations`.
Every cited follow-up URL must already occur in the six-category and
source-quality inventories. Empty contrary-source lists are allowed when
actual research finds none; do not manufacture corroboration or infer
that adverse evidence is absent.

Only a `ready_for_v10_source_review` lead with upstream source support
can carry new admitted claim IDs. A held, contradicted, excluded, or
context-only source cannot. Both `affirmative_source_review` and
`critical_source_review` MUST have `promising_followup_reviews` with
a distinct, substantive decision for **every lead**, including nonpromising
triages. Each row binds exact `source_url`, `triage`, `disposition`,
`lead_sha256`, `approved: true`, `issues: []`, assessment, and limitations.
The two assessments must differ. Missing or misdated research, unreviewed
triage, changed evidence, or inadequate upstream and contrary research fails
before forecasts. No minimum number of promising or accepted claims applies.

The validator checks consistency of **claimed** research, not whether
a live search ran or publisher bytes were independently authenticated;
the separate original-page capture and V10 review rules still apply.

`source_review_packet.evidence` has **every newly proposed accepted
claim as originally frozen**, with an unchanged original claim ID and
the model/editor's original, explicitly provisional `reliability`.
The packet's `pre_review_claim_decisions` binds every ID to its
original source, a 4–25-word exact original article-body passage,
64-digit SHA-256 of the independently recorded original HTML source body,
and admission status. Each admitted decision must contain a
`capture_verification` object recording the exact canonical original and
final URL, actual offset-aware retrieval instant before the cutoff, HTML
content-type/UTF-8, full raw-body SHA-256, visible-text SHA-256, exact
4–25-word visible passage and its character offset. Bind that object to
`capture_verification_sha256`. Local preflight verifies all against the
byte-exact `source-captures/<ID>.html` file; plausible-looking hashes
without the original bytes FAIL local preflight. Full publisher pages are
never staged or published. GitHub can confirm the recorded provenance is
internally consistent, not that captured bytes are authentic remote originals.
Do not fabricate passages or hashes; exclude unsupported observations.

Each source-review perspective must contain `approved:true`,
`issues:[]`, one substantively reviewed `source_reviews` entry for
**every** canonical source URL, and one `claim_reliability_reviews`
entry per retained evidence ID (see
`scripts/source_claim_reliability.py`). Additionally, EACH perspective
must provide `audit_integrity_review` confirming
`complete_with_disclosed_limitations` for the exact six classes, as-of,
source count, metadata-only scope, unknown independently authenticated
first release and unsearched later interval; its assessment and limitations
must each exceed 80 characters. EACH must provide
`source_adequacy_review` with exactly the original newly admitted claim
IDs and a defensible `supported_limited_inference` conclusion, again
with substantive assessments/limitations. A complete-but-INCONCLUSIVE
audit does **not** suffice for scoring forecasts. Each must also report
`source_query_balance_review` with disjoint real ChatGPT-authored
worsening and stabilizing queries drawn from the six supplied category
search descriptions. This is self-reported research, **not** an
independently audited Responses API search trace. The dossier's final
`claim_reliability` rows and the published newly added evidence grades,
`reliability_basis`, and `geopolitical_direction_confidence` must
**exactly match** the conservative algorithm. The frozen
`preforecast_certificate` contains version 1, clean limited-inference
status, cutoff, completed review time, historical baseline SHA and SHA-256
of the original research packet, affirmative/critical reviews and reconciled
grades; its exact digest must match the v3 receipt. Forecast/candidate hashes
are bound only afterward without rewriting the frozen source packet.
This is a consistency commitment, not a trusted third-party timestamp.
Carried-forward evidence
must match original history exactly apart from status. The original
quality audit, claims, factual grades, source identifiers, and cutoff
are never rewritten to manufacture agreement.

## Validation and submission

On a trusted checkout containing the `main` baseline, run:

```bash
python scripts/chatgpt_handoff.py --handoff /absolute/path/approved-handoff
```

This command is **offline** and read-only. It verifies all seven supplied
files and bounded local source captures, including full report receipt,
V10 source/claim rubric and original HTML witnesses, sealed preforecast
certificate, historical integrity, reference chronology, four forecasts,
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

The GitHub CI `validate.yml` **always** requires an exact V10 source
 dossier and preforecast certificate for every new version-3 receipt dated
 October 25 onward. There is no opt-out by omitting `research_mode`.
 Full-report `section_reviews` now also require `item_reviews` with
 two per-item affirmative/critical decisions, specific item-named
 `test_note` and `evidence_or_check`, own draft SHA and issues. A generic
 section-only review is insufficient. Existing V1–V9 and historical
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

## Nonpublishing tests and exact limitations

The normal full test suite is `python -m unittest discover -s tests -v`.
The expensive nested synthetic future-Sunday test runs in a DEDICATED CI
`future-append` job, which is also required before Pages deployment; locally
run it with `IRAN_RUN_FUTURE_APPEND=1 python -m unittest discover -s tests
-p 'test_future_append_readiness.py' -v`. Timeouts are failures, not passes.
Only an isolated test checkout may use `validate_handoff(test_only=True)`.
Real `submit()` always uses production mode; it does not expose a bypass.
Neither this nor a green GitHub validator independently proves external
article truth, first-release chronology, a credible original HTML retrieval,
or that two distinct independent model invocations occurred.
