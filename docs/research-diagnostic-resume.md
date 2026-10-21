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

## Review-stage recovery after completed research

A completed six-category sweep is reusable: the saved original-source correction,
exact model/tool evidence, final citation reconciliation, and source-quality audit
are verified and restored rather than overwritten or queried again. If an older
artifact contains the completed source-quality audit but not the raw metadata
checkpoint, only the metadata fields actually retained in that audit are
reconstructed; missing original article retrieval instants remain explicitly
unknown. New diagnostics also retain raw metadata checkpoints for exact reuse.

After all research gates pass, the diagnostic saves the **exact closed
source-review input** (including its cutoff and hash), then writes separate
`source-review-affirmative.json` and `source-review-critical.json` files as
each review succeeds. An interrupted later run validates the saved input and
reuses a completed review only when its prompt, response, model and completed
OpenAI request journal match. No missing review becomes an automatic approval.

### Run #39608218460 (review POST acknowledgement lost)

That run saved all six source categories, the citation correction, and the
31-source quality audit. Its first review POST timed out **without an
acknowledged response ID**; it may have been accepted and billed even though
its output was not available. Resuming with `resume_run_id=39608218460`
restores the completed source research, but **does not automatically resend**
the ambiguous review request.

To authorize a new, possibly billable **review only**, choose:

- `mode`: `research-dry-run`
- `resume_run_id`: `39608218460`
- `allow_new_review_after_unknown`: `true`, only if you deliberately accept
  that a previous review request may have been billed without producing a result.

With the new-review option left false, the run is expected to fail closed
at the unknown review acknowledgement. The option cannot redo a prior source
search or bypass either required review. Once an affirmative or critical review
is checkpointed, that completed verdict is reused automatically on later
runs. If a different review POST loses its acknowledgement, a later invocation
also requires explicit consent before another possible charge.

A longer bounded (four-minute) non-search request timeout reduces premature
review socket timeouts, but never turns a timeout into a pass. This diagnostic
remains **read-only and nonpublishing**, regardless of review outcomes.

## Alternating affirmative and critical source reviews (mandatory)

Each **live** source-review version now receives BOTH independent reviews in this
order: **affirmative, critical**. An affirmative approval does not skip the critical
review; a critical rejection cannot be overridden by affirmative approval.
A clean result requires both to approve the **same frozen version**, plus the
independent deterministic source-access and research-cutoff checks.

When a round is rejected, the diagnostic attempts only conservative editorial
correction of its closed sources: exclude explicitly challenged or unavailable
original evidence, downclassify unsupported assertions, disclose that retrieved
metadata is not independent proof of full-text inspection or first publication,
and record the gap between the original research cutoff and later review
preparation. Corrections do not introduce new links, invent missing inspection,
alter historical forecasts or silently change the original research or its
source-quality audit. If source diversity, directional balance or sufficient
observations would be lost, the diagnostic fails rather than inventing evidence.
If further conservative corrections make no change, stop and retain the
rejection. No unchanged evidence version is re-reviewed to seek approval.

At most **four complete affirmative→critical rounds** run in one diagnostic.
A timeout, reviewer failure, unresolved objection, lack of qualified evidence,
exhaustion of the review cap or inconsistent preserved record remains a failure.

The original closed review and rejected verdicts remain in
`source-review-input.json`, `source-review-affirmative.json` and
`source-review-critical.json`. Each later version has an immutable
`source-review-round-NN-input.json` and two `source-review-round-NN-{role}.json`
files. The summary `source-review-cycles-outcome.json` records every review
round, exact input hash and clean/rejected status. An existing failed
`research-dry-run.json` is **never overwritten** by a revised result:
`research-dry-run-revised.json` holds the new outcome.

### Continuing rejected run 39629051453

Choose `research-dry-run`, `resume_run_id=39629051453`, and leave
`allow_new_review_after_unknown=false`. Both reviews in that run completed,
so their original objections and all research records can be reused without
repeating the earlier paid requests. **New** review rounds for a genuinely
revised closed source packet can incur new API charges. Any future lost POST
acknowledgement remains subject to explicit opt-in and never becomes a pass.
This workflow is a nonpublishing diagnostic, not Sunday forecast issuance.

## Original-page evidence register and fresh replacement evidence

For a **new** `research-dry-run` (leave `resume_run_id` empty), every new
source-category search asks for a short, verbatim `support_quote` from its
original public source, **or null** if no original text can be inspected.
A separate bounded public-HTTPS fetch checks the source itself, using no
publisher login and no private addresses or redirects. If the research model
has no usable quote, the inspector may suggest an **exact, short paragraph
fragment from the independently fetched page**, selected using conservative
vocabulary overlap with the claim. This is marked as a lexical candidate
rather than model-verbatim support; **both** reviewers must decide whether
it substantively supports the observation. No textual match or overlap is
accepted as proof by itself. The diagnostic saves
`claim-evidence-register.json` before the first affirmative review.

Each claim is identified by the exact frozen evidence ID, original URL and
observation digest. The register stores a maximum **25-word** excerpt only when
it matches independently fetched visible HTML, together with the page-content
and extracted-text SHA-256, offset, retrieved URL, content type, and actual
inspection time. The original research cutoff is retained; a later inspection
is disclosed as later, **not** misrepresented as contemporaneous. Missing,
paywalled, redirected, inaccessible, unsupported-PDF, guessed or nonmatching
passages stay explicitly **unverified**. Full article text is not archived.
Matching a few source words is **not** proof of the surrounding claim, event,
first-publication time, independence or causal/directional implication.

The complete register is included in and hashed with the **immutable closed
review input** of new diagnostics. Its presence adds independent checks:
every retained claim needs an exact original-page textual witness; official
statements cannot be silently promoted to direct measurements; and each
coverage category is reconciled with evidence removed during editorial
corrections. Original source lists and rejected observations remain preserved
for reproducibility. Both affirmative and critical reviews must still
independently determine whether the actual passage supports the observation.

The original audit from run `39637298150` predates this register. Its two
rejected rounds remain intact and **must not** be retrospectively certified
using web pages fetched later. Historic rejected packets can be replayed only
with strict checks against invented links, new observations, or upgraded
source access. Repeating that old run cannot fill a substantive evidence gap.

**To obtain new replacement evidence**, start a fresh `research-dry-run` on
`main` with **blank `resume_run_id`**. This begins a newly dated, potentially
billable six-category search and creates new source-passage evidence
checkpoints; it does not revise the earlier history or backdate a forecast.
If the new run is interrupted, resume **that new run ID** and keep the
original snapshot. The diagnostic still does not publish forecasts, pages,
or social posts. Insufficient qualified evidence, incomplete reviewers, a
timeout, or an unchanged set of unresolved objections remains a failure.

## Recovering a historical carried-forward status formatting error

Fresh staged research snapshots use version 2 prompts and **require** the exact
`evidence_status` strings `new` or `carried_forward`. A carried-forward
item must supply an independent `id` field that identifies an existing,
unchanged historical observation; the ID is never part of the status text.
Newly returned malformed statuses fail **before** a new source-category
checkpoint is saved. A failed stage and its original API response remain
available for diagnosis and cannot silently authorize publication.

The earlier source audit from run **39641953320** used the original version 1
research prompt. The economic/humanitarian batch contains the malformed string
`carried_forward with existing id E-20261004-05`. The linked original AP
article, its publication date, publisher and title match the existing
published evidence record, but the model supplied a different category and
interpretation. When resuming this **verified completed old stage only**, the
pipeline restores exactly the archived `E-20261004-05` record and marks it
`carried_forward`. Neither the later proposed category nor its new
interpretation is allowed to overwrite historical evidence.

The immutable `evidence-status-reconciliation.json` records the model's
original entry, all differences, the unchanged archived record, and
input/output SHA-256 fingerprints. This record is included in the
closed review input. Original research responses, staged search records,
citation corrections, audit metadata, forecasts and `data/history.json`
are never changed.

To resume without repeating six paid searches, choose `main`,
`research-dry-run`, `resume_run_id=39641953320`, and
`allow_new_review_after_unknown=false` (no review was submitted in that
run). As before, **both alternating affirmative and critical reviews**
must independently approve the actual source passages and qualifications
on the same closed evidence snapshot. This recovery does **not** certify
substantive claims, current events or publication readiness.

## Partial evidence corrections after completed independent reviews

The diagnostic no longer excludes an entire original observation **solely because
an affirmative or critical reviewer mentions its evidence ID**. When an
original-source passage was independently captured, the correction can create
a strictly weaker, **quote-only** candidate: it attributes the **exact** saved
25-word-or-shorter excerpt to the source, makes no claim that it is factually
correct, resets direction to `ambiguous`, reduces reliability and impact to
`Low`/`minor`, and removes scored-event effects. It **does not** synthesize
new facts, pull a new article, infer causal impact, or re-date evidence.
`editorial_narrowings` saves the full original and replacement records,
the exact passage digest, and every objection behind the change. The
original saved source review and research body remain unchanged.

A quotation is **not** admissible merely because its words were found.
Unretrievable original passages, a passage with no substantive findings
(such as a generic estimate caveat or a methodology-only excerpt), missing
speaker/context, unresolved pre-cutoff timing, or a **second critical
rejection** of an already-narrowed quotation cause exclusion rather than
another automatic paraphrase. Original historical carried-forward
observations may only be retained unchanged or excluded from the new
diagnostic; they cannot be reinterpreted through a source quote.

Source-quality annotations and each of the six coverage classes are
reconciled against surviving evidence. The original classifications and
claimed supporting URLs remain in immutable audits. Newly narrowed
quotations **never count as demonstrated changes in Iranian stability**;
they can be independently assessed by the next mandatory affirmative
then critical review of the **same updated immutable evidence hash**.

The original minimum evidence counts, publisher diversity and directional
balance **remain blocking requirements**. A corrected source-only diagnostic
can retain and review the provisional evidence version even when the
required directions are absent, but the recorded
`source_diversity_guard` independently prevents clean approval or any
forecast/publication. Two reviewer approvals cannot overrule that block.
If no defensible new correction remains, the diagnostic stops instead of
paying repeatedly for unchanged evidence.

### Continue rejected run 39649947370

Use `mode=research-dry-run`, `resume_run_id=39649947370` and
`allow_new_review_after_unknown=false` on `main`. The earlier six-category
research, passage register and completed first affirmative/critical round
are restored and verified without another paid research submission. The old
`source-review-cycles-outcome.json` and rejected-round blocker are retained
unchanged; a continuation writes
`source-review-cycles-outcome-revised.json` with explicit parent hashes.
Any **new** review round can entail new model charges. The closed initial
research cutoff and recorded unsearched period remain unchanged.
Nothing in this diagnostic authorizes publication.

## Fail early if the closed source snapshot cannot meet directional minimums

After each completed **affirmative then critical** review pair, the diagnostic
may prepare a strictly conservative corrected packet. Every excerpt narrowed
to a quoted original-page passage now resides **only** in
`background_quotes`, never in the pool of directional observations in
`evidence`. Each background row has the exact original source witness and
`editorial_directional_admissible=false`; its original claim and replacement
remain independently audited in `editorial_narrowings`. A quotation—even one
with words about an improving or worsening economy—does not count as an
observed directional change. It cannot satisfy publisher diversity or the
minimum number of new observations. An old quote-only packet that previously
put such quotations under `evidence` is preserved as historical, not
retroactively converted or certified.

The `source_directional_eligibility` gate independently recomputes four
conditions from **substantive, not quote-only** items: at least six observations,
three identified publishers, four new observations, and all of `raises`,
`lowers`, `ambiguous`. These are minimum candidate counts, **not** a finding
that an underlying report is true. Source access, original publication timing,
semantic support, evidence independence and BOTH reviews remain separate
blocking requirements.

Under a closed original research snapshot, corrective editing may only
exclude or weaken evidence, never add an unsearched observation, restore a
lost direction or invent a new original source. Consequently a failed
candidate-count or direction minimum is **irreversible in that snapshot**.
As soon as the *proposed correction* fails one of these minima, the workflow
records an immutable
`source-review-round-NN-terminal-gate.json`: exact parent and correction
hashes, entire unapproved correction, explicit missing directions and other
deficiencies, the original reviewer objections and instructions for a
**new dated source research snapshot**. It stops **before** creating the
next round input or making another billable affirmative/critical request.
Both reviewer approvals can never overrule this gate. Exhausted evidence
is not converted into success, and the original reports are never
overwritten.

### Diagnosing the October 21 rejected source run efficiently

To verify this early-stop repair without paying for the previous six source
searches or new reviewers, select `main`, `research-dry-run`,
`resume_run_id=39649947370`, and
`allow_new_review_after_unknown=false`. This restores the original
completed source research, passage register, and first two independent
reviews. The corrected proposal is now expected to fail the directional
eligibility gate **before any second review pair**; that is an accurate
diagnostic failure, not permission to publish.

Run `39654094747` already holds four complete **historical** rounds under
the older source-quotation rules. Do not resume that fully rejected record:
the workflow refuses to reinterpret its former quote-only directional
classification or to charge more reviews. To acquire genuinely new
improving/worsening observations, start a **fresh** `research-dry-run`
with a **blank** `resume_run_id`. That creates a new cutoff and new
potentially billable, independently evidenced six-category searches,
never an extension backdated to October 21. Only eligible versions then
proceed through alternating affirmative and critical source reviews.
No diagnostic changes published forecasts, pages, or social posts.
