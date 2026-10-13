# Iran Stability Monitor — nonpublishing process rehearsal
**Rehearsal date:** 2026-10-13
**Baseline commit:** `50a2d1f022ee79f9fbd2f5b1398be2a9e3e45538`
**Scope:** Local isolated synthetic fixtures; frozen Protocol v1.0 and October 11 published history unchanged.

## Tests run and observed outcomes

- Original repository regression suite: **193 tests passed**.
- Expanded suite incorporating two end-to-end integration regressions: **195 tests passed locally**.
- Synthetic October 18 assessment: **five full validation/review rounds** were required to obtain a clean result, with **four evidence-closed corrections**.
- In the first round, deliberately inconsistent descriptive probability totals were detected by the full dashboard validator **before** reviewers could approve.
- In the second round, the simulated affirmative reviewer rejected a narrative claim; the candidate was corrected and the **entire validator and both review roles restarted**.
- In the third round, the simulated critical reviewer rejected an uncertainty claim; the entire process restarted again.
- In the fourth round, both reviewers returned clean verdicts, but an intentionally injected *final-issued-record* validation failure revoked approval and restarted the full cycle.
- In the fifth round, the full pre-review suite, affirmative review, critical review and final-issued-record suite passed on the corrected candidate.
- Observed totals: **5 pre-review validation runs; 2 final-issued-record validation runs; 8 simulated reviewer calls; 1 scored forecast elicitation**. All four locked prospective forecast values and the immutable historical baseline remained unchanged.
- The actual `pre_github_review.prepare()` created a complete **synthetic** handoff, with candidate and baseline histories, review-audit files and a matching integrity receipt; `submit_reviewed_assessment.validate_handoff()` accepted the handoff without contacting GitHub.
- Deleting the final critical-review audit file caused validation to reject the handoff, correctly failing closed.
- A separate injected reviewer timeout aborted and produced **no approved handoff directory**.

## Important boundaries and limitations

All purported news, scored probabilities, source identities, and review decisions used in these tests are **synthetic test fixtures**. No new geopolitical inference, genuine independent model review or live Sunday forecast was produced. The end-to-end test does not establish that a ChatGPT cloud-scheduled run can exercise every publishing tool or approval gate; the first full live run is still unverified.

The validator emits provenance **warnings** for archived records that lack precise source-publication timestamps. The synthetic source metadata also lacks precise publication times; these are documented as warnings under the current frozen rules and were **not** silently labeled verified. A validator PASS here means all *enforced* invariants passed; it must not be described as proof that every historical publication time is known. New real evidence must be checked for public availability before the evidence cutoff, with unknowns recorded honestly.

No production history, frozen Protocol v1.0 rules, public assessment, X schedule or published website data was changed by the rehearsal. The two regression tests in `tests/test_complete_handoff_rehearsal.py` are added to required CI so the same workflow remains checked on future code changes.

**Result:** PASS for the nonpublishing repeat-until-clean synthetic process and fail-closed negative controls. **Live research, real reviewer independence, connected GitHub publication, public-domain serving and automatic X posting:** not exercised, therefore not certified.
