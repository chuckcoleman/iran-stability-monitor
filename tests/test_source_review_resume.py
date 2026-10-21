"""No-network recovery tests for the saved Iran source-review handoff."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import assessment_pipeline as pipeline
import source_review_resume as recovery
from source_citation_resolution import resolve_source_citations, _correction_prompt
from source_citation_reconciliation import reconcile_source_citations
from source_quality_audit import source_quality_audit
from source_research_batches import sha
from test_source_citation_resolution import research as unsupported_research
from test_source_citation_resolution import decision as correction_decision
from test_source_citation_reconciliation import A, B, trace

URL = "https://www.reuters.com/world/middle-east/iran-offline-synthetic"
NOW = dt.datetime(2026, 10, 21, 13, 0, tzinfo=dt.timezone.utc)
BASE = "c" * 64


def study():
    return {
        "evidence": [{"source": URL, "evidence_status": "new",
                      "event_date": "2026-10-20", "direction": "ambiguous",
                      "category": "politics"}],
        "coverage_audit": [{
            "category": "international_media",
            "queries": ["Iran synthetic original news search"],
            "outcome": "eligible_reporting_found",
            "original_urls": [URL],
            "limitations": "Synthetic source search with no claim of verified truth."
        }],
        "source_quality": [{
            "url": URL, "kind": "attributed_claim",
            "origin": "original_reporting", "corroborating_urls": [],
            "assessment": "The source reports a synthetic, unconfirmed account.",
            "limitations": "The event and timing are not independently verified by this test."
        }]
    }


def metadata():
    return {URL: {
        "retrieval_status": "retrieved",
        "source_publication_time": "2026-10-20T11:00:00+00:00",
        "publication_dates": ["2026-10-20"],
        "metadata_status": "verified article metadata",
        "source_retrieved_at": "2026-10-21T12:00:00+00:00"}}


class AuditRecoveryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="iran-review-checkpoints-")
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)

    def test_reconciliation_replays_exactly_and_blocks_mutation(self):
        obj = study()
        result = recovery.load_or_save_reconciliation(
            self.dir, obj, {URL}, trace(URL))
        self.assertFalse(result["unsupported"])
        self.assertEqual(recovery.load_or_save_reconciliation(
            self.dir, obj, {URL}, trace(URL)), result)
        previous = self.dir / "citation-reconciliation.json"
        record = json.loads(previous.read_text())
        record["status"] = "ALL_CLAIMED_LINKS_MATCH_WITHOUT_TOOL_PROOF"
        previous.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, "differs"):
            recovery.load_or_save_reconciliation(
                self.dir, obj, {URL}, trace(URL))

    def test_restores_prior_source_quality_without_fetching_or_overwriting(self):
        obj = study()
        expected = source_quality_audit(
            obj, metadata(), cutoff=NOW, strict=True)
        quality_path = self.dir / "source-quality-audit.json"
        quality_path.write_text(json.dumps(expected, sort_keys=True))
        original_bytes = quality_path.read_bytes()
        quality, recovered = recovery.load_or_capture_quality(
            self.dir, obj, {URL},
            lambda url: self.fail("No additional article retrieval permitted"),
            lambda: NOW, None, BASE)
        self.assertEqual(quality, expected)
        self.assertEqual(quality_path.read_bytes(), original_bytes)
        self.assertEqual(recovered[URL]["source_publication_time"],
                         "2026-10-20T11:00:00+00:00")
        self.assertIsNone(recovered[URL].get("source_retrieved_at"))
        checkpoint = json.loads((
            self.dir / "source-metadata-checkpoint.json").read_text())
        self.assertEqual(checkpoint["provenance"],
                         "reconstructed_from_saved_quality_audit")
        quality2, _ = recovery.load_or_capture_quality(
            self.dir, obj, {URL},
            lambda url: self.fail("No retrieval permitted"),
            lambda: NOW, None, BASE)
        self.assertEqual(quality2, expected)

    def test_source_quality_tampering_blocks_resume(self):
        obj = study()
        q = source_quality_audit(obj, metadata(), cutoff=NOW)
        q["sources"][0]["classification"] = "direct_observation"
        (self.dir / "source-quality-audit.json").write_text(json.dumps(q))
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            recovery.load_or_capture_quality(
                self.dir, obj, {URL}, lambda u: self.fail("No fetch"),
                lambda: NOW, None, BASE)

    def test_review_input_is_identical_on_resume_and_cannot_change(self):
        result = study()
        quality = source_quality_audit(result, metadata(), cutoff=NOW)
        calls = []
        def freeze(*args):
            calls.append("freeze")
            return copy.deepcopy(result["evidence"])
        opts = {
            "result": result, "citations": {URL},
            "coverage": result["coverage_audit"], "quality": quality,
            "baseline_sha": BASE, "snapshot": None,
            "archive": {"evidence": []}, "date": "2026-10-21",
            "now": lambda: NOW, "freeze": freeze}
        one = recovery.load_or_create_review_input(self.dir, **opts)
        self.assertEqual(calls, ["freeze"])
        two = recovery.load_or_create_review_input(self.dir, **opts)
        self.assertEqual(one, two)
        self.assertEqual(calls, ["freeze"])
        changed = dict(opts, baseline_sha="other-history")
        with self.assertRaisesRegex(ValueError, "differs"):
            recovery.load_or_create_review_input(self.dir, **changed)

    def test_review_declares_immutable_research_asof_separate_from_processing(self):
        study_result = study()
        quality = source_quality_audit(study_result, metadata(), cutoff=NOW)
        snap = {"snapshot_sha256": "d"*64,
                "cutoff_at": "2026-10-21T12:00:00+00:00"}
        seen = []
        args = dict(result=study_result, citations={URL},
                    coverage=study_result["coverage_audit"], quality=quality,
                    baseline_sha=BASE, snapshot=snap,
                    archive={"evidence":[]}, date="2026-10-21",
                    now=lambda: NOW,
                    freeze=lambda obj, citations, history, day, cutoff:
                        seen.append(cutoff) or copy.deepcopy(study_result["evidence"]))
        original = recovery.load_or_create_review_input(self.dir, **args)
        saved = original[0]
        self.assertEqual(saved["research_as_of"], snap["cutoff_at"])
        self.assertEqual(saved["cutoff"], NOW.isoformat())
        self.assertEqual(saved["post_asof_window"], "NOT_SEARCHED")
        self.assertIn("NOT a claim", saved["cutoff_meaning"])
        self.assertEqual(seen, [NOW])
        repeated = recovery.load_or_create_review_input(self.dir, **args)
        self.assertEqual(original, repeated)
        self.assertEqual(seen, [NOW])
        changed = dict(args, snapshot={**snap,
                     "cutoff_at":"2026-10-21T12:30:00+00:00"})
        with self.assertRaisesRegex(ValueError, "unsupported post-snapshot coverage"):
            recovery.load_or_create_review_input(self.dir, **changed)

    def test_future_asof_cannot_be_backdated_as_completed_research(self):
        study_result = study()
        quality = source_quality_audit(study_result, metadata(), cutoff=NOW)
        snap = {"snapshot_sha256":"e"*64,
                "cutoff_at":"2026-10-21T14:00:00+00:00"}
        with self.assertRaisesRegex(ValueError,"Source snapshot is after"):
            recovery.load_or_create_review_input(
                self.dir, result=study_result, citations={URL},
                coverage=study_result["coverage_audit"], quality=quality,
                baseline_sha=BASE, snapshot=snap,
                archive={"evidence":[]}, date="2026-10-21",
                now=lambda:NOW,
                freeze=lambda *args:self.fail("No freeze after future as-of"))

    def test_both_reviews_checkpoint_and_reuse_without_post(self):
        quality = source_quality_audit(study(), metadata(), cutoff=NOW)
        calls = []
        def reviewer(prompt, search):
            calls.append(prompt)
            return {"approved": True, "issues": [],
                    "source_reviews": [{"url": URL,
                        "assessment": "Synthetic reviewer checked the original source and stated uncertainties.",
                        "disposition": "supported_as_qualified"}]}, set()
        for role in ("affirmative", "critical"):
            kwargs = {"role": role, "prompt": "Source review: " + role,
                      "input_sha": "input-hash-one",
                      "quality": quality, "reviewer": reviewer,
                      "now": lambda: NOW}
            first = recovery.review_with_checkpoint(self.dir, **kwargs)
            self.assertTrue(first["approved"])
            reused = recovery.review_with_checkpoint(
                self.dir, **dict(kwargs, reviewer=lambda *x:
                    self.fail("Saved verdict must be reused")))
            self.assertEqual(first, reused)
            self.assertEqual(first["draft_sha256"], "input-hash-one")
        self.assertEqual(len(calls), 2)

    def test_unknown_foreground_post_never_auto_retried(self):
        quality = source_quality_audit(study(), metadata(), cutoff=NOW)
        (self.dir / "api-request-unknown.json").write_text(json.dumps({
            "phase": "non-search assessment/review", "post_attempts": 1,
            "response_id": None, "request_sha256": "d" * 64,
            "status": "create_acknowledgement_unknown_no_replay"}))
        called = []
        def live_reviewer(prompt, search):
            called.append(prompt)
            response = {"approved": True, "issues": [],
                        "source_reviews": [{"url": URL,
                            "assessment": "A synthetic example was examined and limitations were explicitly assessed.",
                            "disposition": "supported_as_qualified"}]}
            model = "gpt-6.1-sol"
            payload = pipeline.responses_payload(prompt, False)
            self.assertFalse(search)
            (self.dir / "response-8.json").write_text(json.dumps({
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "search": False, "model": model,
                "response_id": "resp_review123", "result": response}))
            (self.dir / "api-request-complete.json").write_text(json.dumps({
                "phase": "non-search assessment/review", "post_attempts": 1,
                "status": "api_completed_output_not_yet_validated",
                "response_id": "resp_review123",
                "request_sha256": sha(payload)}))
            return response, set()
        params = dict(role="affirmative", prompt="A frozen-source review",
                      input_sha="known-closed-snapshot", quality=quality,
                      reviewer=live_reviewer, now=lambda: NOW)
        with patch.object(recovery, "LIVE_RESEARCHER", live_reviewer):
            with self.assertRaisesRegex(ValueError, "no automatic paid retry"):
                recovery.review_with_checkpoint(self.dir, **params)
            self.assertEqual(called, [])
            first = recovery.review_with_checkpoint(
                self.dir, **params, allow_new_after_unknown=True)
            self.assertTrue(first["approved"])
            self.assertEqual(len(called), 1)
            self.assertEqual(first["superseded_unknown_requests"], ["d" * 64])
            second = recovery.review_with_checkpoint(self.dir, **params)
            self.assertEqual(first, second)
            self.assertEqual(len(called), 1)

    def test_restores_completed_correction_without_second_search(self):
        initial = unsupported_research()
        before = copy.deepcopy(initial)
        calls = trace(A)
        attempted = []
        def correct(prompt, search):
            self.assertTrue(search)
            attempted.append(prompt)
            verdict = correction_decision()
            (self.dir / "response-7.json").write_text(json.dumps({
                "search": True, "model": "gpt-6.1-sol",
                "response_id": "resp_corrective123",
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "result": verdict, "citations": [B],
                "tool_search_calls": trace(B)}))
            (self.dir / "api-request-correction.json").write_text(json.dumps({
                "phase": "web-search research", "post_attempts": 1,
                "status": "api_completed_output_not_yet_validated",
                "response_id": "resp_corrective123",
                "request_sha256": sha(dict(
                    pipeline.responses_payload(prompt, True),
                    background=True))}))
            return verdict, {B}
        first = resolve_source_citations(
            initial, {A}, calls, researcher=correct, audit_dir=self.dir)
        self.assertEqual(len(attempted), 1)
        self.assertEqual(initial, before)
        # A real staged-research artifact is saved with sort_keys=True,
        # while citation-resolution-initial.json preserves original insertion
        # order. The same exact data therefore generate different prompt bytes.
        sorted_research = json.loads(json.dumps(initial, sort_keys=True))
        sorted_calls = json.loads(json.dumps(calls, sort_keys=True))
        self.assertEqual(sorted_research, initial)
        self.assertEqual(sorted_calls, calls)
        changed_order_prompt = _correction_prompt(
            sorted_research,
            reconcile_source_citations(sorted_research, {A}, sorted_calls),
            sorted_calls)
        self.assertNotEqual(
            hashlib.sha256(attempted[0].encode()).hexdigest(),
            hashlib.sha256(changed_order_prompt.encode()).hexdigest())
        with patch.object(pipeline, "LIVE_RESEARCHER", correct):
            second = resolve_source_citations(
                sorted_research, {A}, sorted_calls,
                researcher=correct, audit_dir=self.dir)
        self.assertEqual(first, second)
        self.assertEqual(len(attempted), 1)
        tampered_research = copy.deepcopy(sorted_research)
        tampered_research["evidence"][0]["observation"] = (
            "A materially different unsupported claim")
        with self.assertRaisesRegex(ValueError, "initial evidence differs"):
            resolve_source_citations(
                tampered_research, {A}, sorted_calls,
                researcher=correct, audit_dir=self.dir)
        self.assertEqual(len(attempted), 1)
        saved_file = self.dir / "citation-resolution.json"
        changed = json.loads(saved_file.read_text())
        changed["revised_research"]["evidence"][0]["source"] = A
        saved_file.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "deterministic replay"):
            resolve_source_citations(initial, {A}, calls,
                                     researcher=correct, audit_dir=self.dir)
        self.assertEqual(len(attempted), 1)


if __name__ == "__main__":
    unittest.main()
