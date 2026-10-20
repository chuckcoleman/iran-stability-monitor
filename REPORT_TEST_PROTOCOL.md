# Complete alternating review checklist for all Iran Monitor reports

**Effective:** 2026-10-25. Companion to [REVIEW_POLICY.md](REVIEW_POLICY.md).
Applies to prospective weekly/special assessments, research digests,
six-source-category audits, calculations, scenarios, figures, tables,
public summaries, X drafts, and **nonpublishing test reports**.

## Identification

- Title, report type, assessment or test date/time (timezone included)
- Exact input-data snapshot SHA-256; full draft SHA-256; protocol/version
- Evidence cutoff and reporting window; source identifiers and links
- Which checks actually ran: actual versus synthetic, complete versus partial
- Explicit publishing status: DRAFT / REVIEW FAILED / TEST ONLY / PUBLISHED
- Reviewer provenance: two **sequential ChatGPT perspectives**, not
  independent model invocations

## Run deterministic checks before editorial review

Inspect **every** applicable report component and every row/figure:
- Primary, international, regional, specialist, think-tank and
  economic/humanitarian source coverage; original release/event times,
  syndication, provenance, contradictions and material gaps
- Four frozen scored forecasts, confidence, ranges, deadlines and signed
  change contributions; no retrospective alteration
- Nine early-warning groups, Hormuz/energy/security conditions,
  political/regional scenarios, causal chains and absence indicators
- Houthi material/technical/independent diagnostics, six China oil-credit
  adjustments and sensitivity arithmetic; Hanke inflation and humanitarian
  claims
- Narrative/support/limitations, next thresholds, all tables/charts,
  dashboard values/statuses, units, legends, dates, and social copy
- File integrity, repeatability, chronology, artifact match, CI result
  and canonical website identity **only when genuinely tested**

For every applicable item record: **PASS**, **FAIL**, **NOT TESTED**, or
**NOT APPLICABLE** with the actual method/evidence. NOT TESTED is never
silently promoted to PASS. Known material FAIL blocks releasing the item.

## Alternating roles on one unchanged full draft

1. **Affirmative tests:** For every item, identify what directly supports
   it, recalculate relevant quantities, check source independence and
   chronology, scrutinize completeness and clearly separate facts from
   assumptions. Record one specific nonboilerplate test note and
   approved=true/issues=[] only if clean.
2. **Critical tests:** On the **same draft hash**, seek falsifying or
   alternative evidence, contradictory figures, missing rows/units,
   duplicated accounts, unsupported event resolution, overconfident
   scenario descriptions, and misrepresented negative evidence. Record a
   different specific test note and an explicit decision for each item.
3. If either perspective objects, **no global approval**. Correct only
   allowed evidence-closed unscored text/diagnostics, run all applicable
   deterministic tests again, then both reviewers again on the NEW
   complete draft. Never recycle previous approvals.
4. Apply the six-complete-round/60-minute fail-closed limits to Sunday
   assessment reviews. A test-only report must label any unavailable
   live steps honestly, irrespective of synthetic gate successes.
5. Retain the full report with a section-by-section checklist, both
   explicit verdicts, test notes, actual times and exact draft hash.
   Sunday assessments additionally require a version-3 machine
   section-review matrix and matching SHA-256 report/receipt digest.

## Explicit citation reconciliation tests

Before source freezing, every original source URL in the six-category
coverage audit and every *new* evidence URL must be matched to both a
Responses citation and an original source URL exposed by a genuine
web-search-tool call. Preserve a location-indexed ledger of the claimed
link, normalized URL, evidence/coverage role and independent match
results. Flag mismatches, invalid URLs and duplicate URLs within a
category; **never treat a similar AP ID, redirect guess or rewritten
headline as a verified equivalence**. Test both a clean match and
deliberately unsupported versions, including an evidence URL absent
from tool results.

If ANY citation is flagged, save the complete audit and an explicit
`UNSUPPORTED_CITATIONS_FLAGGED_NOT_PUBLISHABLE` test disposition;
neither an editor's approval nor a clean JSON schema can override the
missing provenance. The test must stop before frozen evidence,
scored forecasts and affirmative/critical publication reviews. This
prefreeze validation failure is appropriately recorded as both reviews
NOT REACHED, not as a claim they were approved. Missing source-trace
data is NOT TESTED, not an inferred verification.

## Request reliability and no-duplicate-work tests

For authenticated Responses research, test that the single initial
background POST is recorded before network activity, that its response ID
is persisted immediately on receipt, and that only read-only GET polling
may be retried. Intentionally inject a dropped initial connection, GET
network failure, failed/expired response, unexpected ID, incomplete result,
and request timeout. A lost acknowledgement is **unknown acceptance**, never
a reason to generate a duplicate paid assessment. The redacted request
audit must survive a failure without storing tokens, prompts or error bodies.
The actual API's background completion alone is NOT source validation,
editorial approval, a Sunday forecast, or publication.

## Distinct nonpublishing rehearsal results

The manual `research-dry-run` diagnostic tests actual Web Search
API calls and their cited source URLs, publication metadata, a six-class
source-coverage ledger and two alternating source-quality reviews.
Keep the API-provided search-call trace, the reviewed frozen source
digest and each actual reviewer decision. A simulated model response
is NOT a genuine API call, and a model's claimed search query that was
not exposed by the tool is NOT verified as executed.

The research-only run has NO future Sunday forecast, issued record,
fifteen-section Sunday report approval, visual browser verification,
GitHub PR, Pages deployment or X posting. These sections must appear
as NOT TESTED or NOT INVOKED in its final test report; a successful
research diagnostic never changes the publication state.

## Report disposition

Report each section and its negative-test result, then distinguish:
* validated factual report, but forecasting not performed
* forecast prepared but two-role approval incomplete
* reviewed assessment not yet merged/deployed
* verified canonical website publication
* X pending/disabled/posted independently

**Never publish or announce a failed/unvalidated artifact; never claim an
unfinished test or mock validation is a successful end-to-end live run.**
