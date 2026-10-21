"""Synthetic checkpoint/recovery tests; no OpenAI, GitHub, or publication calls."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from assessment_pipeline import responses_payload
from source_research_batches import (
    CATEGORIES, batch_prompt, batched_research, canonical, combine, prior_index,
    read_json, research_snapshot, require_pre_snapshot_publication, sha)
from source_search_trace import observed_search_calls

STAMP = dt.datetime(2026, 10, 20, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
LATER = dt.datetime(2026, 10, 21, 9, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))


class BatchResearchTests(unittest.TestCase):
    def setUp(self):
        context = tempfile.TemporaryDirectory(prefix="iran-staged-source-")
        self.addCleanup(context.cleanup)
        self.dir = Path(context.name)
        self.prompts = []
        self.baseline = "b" * 64

    def build_response(self, prompt, search):
        self.assertTrue(search)
        match = re.search(r"This stage is ONLY category: ([a-z_]+)", prompt)
        self.assertIsNotNone(match)
        category = match.group(1)
        self.prompts.append(category)
        index = CATEGORIES.index(category)
        url = f"https://example.org/iran-observation-{index}"
        obj = {
            "coverage_audit": [{
                "category": category,
                "queries": [f"Synthetic offline source search for {category}"],
                "outcome": "eligible_reporting_found",
                "original_urls": [url],
                "limitations": "Synthetic fixture; reporting is not independently verified."
            }],
            "evidence": [{
                "event_date": "2026-10-19",
                "category": "Iran governance",
                "observation": f"Independent synthetic observation number {index}.",
                "source": url, "source_title": f"Synthetic article {index}",
                "publisher": f"Synthetic Outlet {index}", "reliability": "Medium",
                "affects": ["regime_end_12m"], "evidence_status": "new",
                "impact_magnitude": "minor",
                "direction": ("raises", "lowers", "ambiguous")[index % 3]
            }],
            "source_quality": [{
                "url": url, "kind": "attributed_claim",
                "origin": "original_reporting", "corroborating_urls": [],
                "assessment": "The synthetic article reports a claim whose truth is not established.",
                "limitations": "Original publication clock and independent corroboration are unavailable."
            }]
        }
        calls = observed_search_calls([{"type": "web_search_call",
            "action": {"type": "search", "query": "Synthetic Iran research",
                       "sources": [{"url": url, "title": "Synthetic source"}]}}])
        files = list(self.dir.glob("response-*.json"))
        record = {"model": "gpt-6.1-sol", "response_id": f"resp_synthetic{index+20}",
                  "search": True, "result": obj, "citations": [url],
                  "tool_search_calls": calls,
                  "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}
        path = self.dir / f"response-{len(files)+1}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return obj, {url}

    def update_synthetic_tool_record(self, obj):
        """Make a malformed model output match the mocked API-returned record."""
        files = sorted(self.dir.glob("response-*.json"))
        self.assertTrue(files)
        row = read_json(files[-1])
        row["result"] = obj
        files[-1].write_text(json.dumps(row), encoding="utf-8")

    def run_sweep(self, researcher=None, *, resume=False, when=STAMP, baseline=None):
        return batched_research(
            researcher=researcher or self.build_response,
            folder=self.dir, prior=[], day=when.date().isoformat(),
            baseline_sha=baseline or self.baseline, started_at=when,
            resume=resume)

    def test_six_batches_complete_and_trace_is_preserved(self):
        result, citations, calls, snap = self.run_sweep()
        self.assertEqual(self.prompts, list(CATEGORIES))
        self.assertEqual(len(result["coverage_audit"]), 6)
        self.assertEqual(len(result["source_quality"]), 6)
        self.assertEqual(len(result["evidence"]), 6)
        self.assertEqual(len(citations), 6)
        self.assertEqual(len(calls), 6)
        self.assertTrue(all(row["search_calls_real"] for row in calls))
        self.assertEqual(len(list(self.dir.glob("research-batch-*.json"))), 6)
        merged = read_json(self.dir / "research-batches-merged.json")
        self.assertEqual(merged["completed_categories"], list(CATEGORIES))
        self.assertEqual(merged["status"],
                         "SIX_SOURCE_BATCHES_COMPLETE_PENDING_CITATION_REVIEW")
        self.assertEqual(snap["date"], "2026-10-20")

    def test_resume_after_all_stages_is_zero_new_posts(self):
        original = self.run_sweep()
        self.prompts.clear()
        result = self.run_sweep(researcher=lambda p, s: self.fail("No paid calls"),
                          resume=True, when=LATER)
        self.assertEqual(self.prompts, [])
        self.assertEqual(result[:3], original[:3])
        self.assertEqual(result[3], original[3])

    def test_partial_run_resumes_without_replaying_completed_stage(self):
        def stop_on_second(prompt, search):
            if "category: international_media" in prompt:
                raise RuntimeError("Simulated transient research failure")
            return self.build_response(prompt, search)
        with self.assertRaisesRegex(RuntimeError, "transient research failure"):
            self.run_sweep(researcher=stop_on_second)
        self.assertEqual(self.prompts, ["primary_data"])
        self.assertFalse((self.dir / "research-batches-merged.json").exists())
        self.prompts.clear()
        _, _, _, snap = self.run_sweep(resume=True, when=LATER)
        self.assertEqual(self.prompts, list(CATEGORIES)[1:])
        self.assertEqual(snap["date"], "2026-10-20")
        self.assertEqual(snap["cutoff_at"], STAMP.isoformat())

    def test_legacy_resume_without_snapshot_fails_before_paid_call(self):
        with self.assertRaisesRegex(ValueError, "legacy monolithic"):
            self.run_sweep(researcher=lambda p, s: self.fail("No new request"),
                     resume=True, when=LATER)
        self.assertEqual(list(self.dir.glob("api-request-*.json")), [])

    def test_modified_history_rejected_even_when_old_stages_pass(self):
        self.run_sweep()
        self.prompts.clear()
        with self.assertRaisesRegex(ValueError, "immutable history"):
            self.run_sweep(resume=True, when=LATER, baseline="a"*64,
                     researcher=lambda p, s: self.fail("No new request"))
        self.assertEqual(self.prompts, [])

    def test_wrong_category_never_marks_stage_complete(self):
        def wrong(prompt, search):
            obj, urls = self.build_response(prompt, search)
            obj["coverage_audit"][0]["category"] = "other"
            self.update_synthetic_tool_record(obj)
            return obj, urls
        with self.assertRaisesRegex(ValueError, "wrong source category"):
            self.run_sweep(researcher=wrong)
        self.assertFalse((self.dir / "research-batch-primary_data.json").exists())

    def test_future_event_never_enters_stage(self):
        def future(prompt, search):
            obj, urls = self.build_response(prompt, search)
            obj["evidence"][0]["event_date"] = "2026-10-22"
            self.update_synthetic_tool_record(obj)
            return obj, urls
        with self.assertRaisesRegex(ValueError, "Post-snapshot event"):
            self.run_sweep(researcher=future)
        self.assertFalse((self.dir / "research-batches-merged.json").exists())

    def test_missing_source_classification_fails_closed(self):
        def omitted(prompt, search):
            obj, urls = self.build_response(prompt, search)
            obj["source_quality"] = []
            self.update_synthetic_tool_record(obj)
            return obj, urls
        with self.assertRaisesRegex(ValueError, "omits source URLs"):
            self.run_sweep(researcher=omitted)

    def test_post_snapshot_source_publication_rejected_but_late_retrieval_is_not(self):
        self.run_sweep()
        snap = read_json(self.dir / "research-snapshot.json")
        obj = read_json(self.dir / "research-batch-primary_data.json")["result"]
        src = obj["evidence"][0]["source"]
        require_pre_snapshot_publication(obj, {
            src: {"source_publication_time": "2026-10-19T17:00:00Z",
                  "source_retrieved_at": "2026-10-21T16:00:00Z"}}, snap)
        with self.assertRaisesRegex(ValueError, "after research snapshot cutoff"):
            require_pre_snapshot_publication(obj, {
                src: {"source_publication_time": "2026-10-21T13:00:00Z"}}, snap)

    def test_prior_unacknowledged_post_cannot_be_replayed(self):
        snap = research_snapshot(self.dir, day="2026-10-20", prior=[],
                                 baseline_sha=self.baseline, started_at=STAMP,
                                 model="gpt-6.1-sol", resume=False)
        prompt = batch_prompt(CATEGORIES[0], snap)
        payload = responses_payload(prompt, True)
        payload["background"] = True
        (self.dir / "api-request-interrupted.json").write_text(json.dumps({
            "request_sha256": sha(payload),
            "post_attempts": 1, "response_id": None,
            "status": "create_acknowledgement_unknown_no_replay"}))
        with self.assertRaisesRegex(ValueError, "no POST attempted"):
            self.run_sweep(researcher=lambda p, s: self.fail("No network"))
        self.assertFalse((self.dir / "research-batches-merged.json").exists())

    def test_prior_acknowledged_request_sets_get_only_for_exact_stage(self):
        snap = research_snapshot(self.dir, day="2026-10-20", prior=[],
                                 baseline_sha=self.baseline, started_at=STAMP,
                                 model="gpt-6.1-sol", resume=False)
        prompt = batch_prompt(CATEGORIES[0], snap)
        payload = responses_payload(prompt, True)
        payload["background"] = True
        (self.dir / "api-request-interrupted.json").write_text(json.dumps({
            "request_sha256": sha(payload),
            "post_attempts": 1, "response_id": "resp_recovered123",
            "status": "background_timeout_no_replay"}))
        env = []
        def observe(prompt, search):
            env.append((CATEGORIES[len(env)], os.environ.get("IRAN_RESUME_AUDIT_DIR")))
            return self.build_response(prompt, search)
        self.run_sweep(researcher=observe, resume=True, when=LATER)
        self.assertEqual(env[0][1], str(self.dir))
        self.assertTrue(all(v is None for _, v in env[1:]))

    def test_checkpoint_trace_tampering_rejected_before_reuse(self):
        self.run_sweep()
        path = self.dir / "research-batch-primary_data.json"
        item = read_json(path)
        item["citations"].append("https://unrelated.example.org/false")
        path.write_text(json.dumps(item))
        with self.assertRaisesRegex(ValueError, "checkpoint differs"):
            self.run_sweep(resume=True, when=LATER,
                     researcher=lambda p, s: self.fail("No new request"))

    def test_missing_category_cannot_be_approved(self):
        self.run_sweep()
        stages = {category: read_json(
            self.dir / ("research-batch-" + category + ".json"))
            for category in CATEGORIES[:-1]}
        snap = read_json(self.dir / "research-snapshot.json")
        with self.assertRaisesRegex(ValueError, "Six independent source categories"):
            combine(stages, snap)


if __name__ == "__main__":
    unittest.main()
