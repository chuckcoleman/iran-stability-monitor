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

## Historical v3 fresh-source pre-review admissibility (preserved on resume)

The original **version-3** live `research-dry-run` created its
own new research snapshot. That version remains immutable on any
`resume_run_id` replay. **After the v4 source-date and bilingual
improvements, fresh runs with blank `resume_run_id` instead create
version-4 snapshots.** The six saved
web searches now ask for **one narrow original-source observation per
item**, its exact 4–25-word source passage, a declared
`effect_type`, and a `direction_basis` sentence explaining why that
specific original passage suggests the proposed `raises`, `lowers`,
or `ambiguous` direction. The model must not invent an original article,
a dated event, directional balance or independent corroboration. Original
v1 and v2 snapshots and their paid request fingerprints are unchanged;
a missing or malformed optional admission field in a v3 model response
is logged and **held out** by the pre-review screen, not fixed by another
paid search.

After the full six-stage research, citation reconciliation, original
metadata capture and bounded page-passage inspection, the
**zero-additional-API-request** `source_pre_review_admissibility` gate
checks every original frozen observation for:

- independent direct-source passage retrieval (not just a citation or
  publisher metadata), compatible source-quality classification and a
  matching original URL;
- an event date inside the conservative 90-day research-event window;
- a publisher-reported pre-cutoff timestamp or a publisher-reported
  date **strictly earlier than the research date**; a same-day date with
  no verified clock, conflicting future time, or absent publication
  metadata cannot establish pre-cutoff eligibility;
- an actual short passage with meaningful original-language word
  overlap against the claim and its model-supplied directional rationale,
  and a declared observable policy action, reported event or measured
  series rather than merely analytical/retrospective/attributed context.

These tests are **screening conditions**, not independent proof that a
claim happened, that a publisher's metadata is the first release instant,
that sources are independent, or that a geopolitical effect has the
reported sign. All included observations are explicitly labeled
`PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW`. The two
independent affirmative and critical reviews remain mandatory for the
same immutable screened packet, and can reject any substantive assertion.
A publisher statement, snippet, or model rationale never constitutes
self-authenticating directional evidence.

The new immutable
`source-pre-review-admissibility.json` contains the original input hash,
per-claim admission/hold reasons, the full screened candidate packet,
the removed original claims, and the source/coverage reconciliation.
If the admitted provisional evidence fails any of the four existing
source-diversity/directional minima, a separate
`research-pre-review-dry-run.json` records the precise deficiency,
**neither reviewer is invoked**, and GitHub Actions exits with a
failure. No source-review payment can be triggered by an unsuccessful
pre-review gate, and there is no implied permission to publish. Resume
of that same v3 snapshot verifies the immutable screen and reuses the
original archived searches and passage captures without altering them.

A previously **fully reviewed** version-2 failed research run (such as
`39673989046`) is not retrospectively made admissible by version 3.
Do not simply resume old rejected evidence for more paid reviews.
To seek genuinely new original-direction evidence, start a
**new dated** run with blank `resume_run_id` and leave the
potential duplicate-review consent option off by default. New research
searches and, only if the pre-screen passes, reviews may incur API costs.
This test remains explicitly nonpublishing: no forecasts, historical
numerical data, GitHub publishing PRs or social updates are changed.

## Recovery of a completed research response with list-valued limitations

Fresh v3 diagnostic **39682616579** completed the primary-data and
international-media research stages. Its third (regional/multilingual)
OpenAI search also completed and its original response, request journal
and web-search trace were saved, but stage validation stopped because
`coverage_audit[0].limitations` contained **11 nonempty strings**
instead of one prose string. This is a representational formatting
problem, not permission to discard the 11 caveats or regenerate the
paid research.

When a **saved, independently verified** response supplies a bounded,
nonempty list of strings in `coverage_audit[].limitations` or
`source_quality[].limitations`, the pipeline constructs a newline-
separated string in a distinct **effective** stage result. The original
`response-N.json` and completed transport remain unchanged. For each
corrected field the immutable
`research-stage-format-regional_multilingual_media.json` (or matching
category name) stores the original ordered list, effective text,
snapshot, prompt SHA-256, exact API request fingerprint, response ID,
model, original result digest and effective result digest. The
research-stage checkpoint retains both the raw `result` and the
separate `effective_result`, tied to the normalization audit. A
resumed checkpoint recomputes and verifies all of them before reuse.

Normalization refuses empty arrays, invalid elements, oversized
inputs, mismatched Responses/transport journals, altered prior
checkpoints and any attempt to normalize other types of field.
The normalizer does **not** fix unsupported citations, manufacture
evidence, change event dates or cutoff, or approve source-quality
assertions. No live research prompt for v1, v2 or v3 was changed.

To continue **39682616579**, use `main`, `research-dry-run`,
`resume_run_id=39682616579`, and leave the checkbox about a possible
billable replacement review **unchecked**. The first two category
checkpoints are reused byte-for-byte; the saved third response is
validated and normalized with **no repeat search POST**. The
remaining three source categories may generate normal paid research
requests, after which the new no-review-cost source admissibility
screen runs. Only an admissible candidate set can proceed to
alternating affirmative and critical review. No diagnostic run
authorizes publication or changes historical forecasts.

## Resuming a completed citation-correction request with duplicate URL decisions

The original v3 diagnostic **39688687012** completed all six research
categories and a single corrective citation search. It then failed because
that saved corrective response supplied **nine** decisions for **eight**
distinct URL strings: the same ACLED Sistan/Baluchestan original appeared
once as a coverage citation and again as an evidence citation. Both
decisions said `withdrawn`, with different explanations. This is a
formatting/repetition error in one completed paid response, not
authorization to invent a URL or silently accept a withdrawn observation.

The pipeline now deterministically consolidates **only** responses that
refer to the **same exact** `claimed_url`, request the same
`verified`, `replaced`, or `withdrawn` action, and have compatible
replacement URLs and evidence edits. Disjoint replacement edits may be
combined, but repeated edits of one evidence index must match exactly.
Distinct claimed URLs are never conflated through guessed aliases.
Conflicting actions, unsupported replacements, missing URLs, or conflicting
changes still fail. The effective merged reason preserves **each
separate original reviewer/model explanation**, in its original order.

The unmodified corrective model output remains in the original
`citation-resolution.json` with status `FAILED_NOT_PUBLISHABLE`.
A failed record is recoverable only when the original research, original
citation flags, actual web-search calls, completed corrective Responses
record, exact prompt/request fingerprints, model, response ID and
acknowledged API transport all agree. The full independent citation gate
is then rerun against the effective eight-URL decisions. A successful,
verified recovery produces a separate immutable
`citation-resolution-recovery.json` containing the original failed
record hash, the exact original and effective decision digests, both
original ACLED reasons, the completed response ID, the final source
reconciliation, the corrected research and its hash. Neither the
original failed record nor paid response is overwritten.

For this specific recovery, run `research-dry-run` on `main` with
`resume_run_id=39688687012`. Leave the optional checkbox that allows
a new potentially billable replacement **review** POST **unchecked**.
This should reuse the completed six searches and the existing corrective
search with **no new paid corrective POST**. It then continues through
source metadata, claim-passage inspection and the stricter pre-review
admissibility gate. Only if admissible directional candidates survive
should fresh alternating affirmative and critical reviews be requested,
which may incur normal costs. Every failure still blocks publication
and leaves `data/history.json` and all previously scored forecasts
unchanged.

## Source-examination improvements for new v4 research

The source examination after diagnostic **39692255833** found several
potentially useful original reports that the original v3 zero-cost
pre-review screen held out. This update **does not reclassify or
overwrite that failed October 21 source snapshot**. Old v1, v2 and v3
research prompt strings, original API response IDs, source passages
and saved pre-review certificates remain historical. Fresh `main`
research-dry-run snapshots use **version 4**; recovery of an older
version retains its original cutoff and original screening algorithm.

### Original publication dates, not retrospectively verified clocks

The metadata parser now checks tightly constrained publisher date
labels immediately after a heading that matches the article's HTML
title. For example, the [U.S. Treasury press release dated
October 15, 2026](https://home.treasury.gov/news/press-releases/sb0660)
displays a visible date that some pages do not also encode in
`article:published_time` or `datePublished`. The stage now
records its **exact visible date string** and the matching HTML
article-heading method as `publication_date_evidence` in the original
metadata checkpoint and, where present, the source-quality audit. No
calendar dates found only in menus, ordinary body paragraphs, captions,
or unrelated article lists are promoted to article dates.

The extracted date is still **publisher-reported, not certified first
publication**. It is never turned into a fabricated time-of-day.
Same-day dates without a verifiable pre-cutoff instant remain
insufficient. Conflicting/future original-source dates fail the
existing source-timing controls. Late retrieval never moves an old
snapshot's research-as-of time.

### Facts, directions and model-draft translations are separate

For **v4 only**, the evidence screen records two different
questions: (1) whether an original source's *literal narrow factual
assertion* is sufficiently connected to the matched passage to be
submitted for review, and (2) whether that fact *actually warrants*
the model's proposed effect on regime stability. A vocabulary mismatch
between an otherwise exact source passage and a geopolitical
**direction rationale** is now an explicit review-only flag rather
than automatic word-overlap rejection or automatic approval. Both
affirmative and critical review checks must document the qualified
underlying event **and separately** the proposed directional effect
before a dual-review record can be clean. An issuer's documented
sanctions designation is a policy action, **not independent evidence**
of Treasury's claimed macroeconomic or regime effects.

An English statement based on an Arabic, Persian or other detected
non-Latin original passage must retain the unchanged **verbatim
original** and the original source-body hash. A v4 search can provide
a bounded `support_quote_translation`,
`original_quote_language`, and
`translation_status=MODEL_DRAFT_UNVERIFIED`. The translated text is
accepted only for preliminary *word-overlap triage*. It is not
a verified translation and cannot authenticate the original text or
causal interpretation. The review input explicitly records the
original passage, language, draft translation, and every unverified
assumption. **Both** affirmative and critical reviewers must
individually record original-language fidelity checks in their
`source_reviews[].translation_checks` and qualified evidence/sign
checks in `source_reviews[].direction_checks`. Failure, omission or
inability to inspect the original is a recorded review rejection,
never a silent admission or endorsement.

Where an original newsroom article reports its **own** satellite
image comparisons, it can be treated as a *candidate observed
image-derived change* even if source-quality annotations call it
`analysis`, but only with
`origin=original_reporting`,
`effect_type=measured_data`, and
`observational_method=original_satellite_imagery`. This is not a
verification of the actual satellite imagery, repair completeness,
operational readiness, coercive loyalty, or probability impact.
For example, [Al Jazeera's October 20 satellite-imagery
investigation](https://www.aljazeera.net/news/2026/10/20/%D9%85%D9%86-%D8%B4%D9%8A%D8%B1%D8%A7%D8%B2-%D8%A5%D9%84%D9%89-%D9%83%D8%A7%D8%B4%D8%A7%D9%86-%D9%88%D8%A8%D9%88%D8%B4%D9%87%D8%B1-%D9%83%D9%8A%D9%81-%D8%AA%D8%B9%D9%8A%D8%AF)
should not be read as proof that military facilities are fully
restored, or as certain stability improvement. The original
satellite-interpretation and opposing damage evidence must be
challenged in both source reviews.

Old analytical commentary remains visible as
`background_source_analyses` in new v4 packets and in the original
source inventory, but never counts as a new directional event. In
particular, the [RSIS regime-change analysis from
January](https://rsis.edu.sg/rsis-publication/rsis/evaluating-the-prospects-of-regime-change-in-iran/)
and the [Stimson political-system
analysis](https://www.stimson.org/2026/irans-political-system-after-the-war/)
are useful context, not freshly observed October changes.

This update does **not** change the existing minimum of six
observations, four new observations, three publishers or the
longstanding three-direction evidence-balance requirement. That
normative rule may merit separate consideration, because research
must not invent a `lowers` or `ambiguous` event just to pass a
minimum. The new prompts expressly forbid manufactured balancing
claims. All snapshots remain **research-only**; there is no automatic
forecast publication or authority to modify `data/history.json`.
