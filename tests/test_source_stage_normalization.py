"""Immutable restoration of research limitations returned as ordered JSON lists.

Regression for diagnostic #39682616579: the third saved search result carried
eleven limitation strings, while the earlier two category checkpoints used
ordinary strings. The original Responses body and request must not be altered,
and completed stage requests must not be POSTed again.
"""
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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import assessment_pipeline
from assessment_pipeline import responses_payload
from source_research_batches import (
    CATEGORIES, _normalize_limitation_lists, _verified_stage_normalization,
    batched_research, canonical, read_json, sha, save_new)
from source_search_trace import observed_search_calls

# The same structural failure as the preserved regional/multilingual response:
# eleven nonempty, separately reasoned textual limitations in list order.
REGIONAL_LIMITATIONS = [
    "Research cutoff applied: 2026-10-21T17:55:46.321287-04:00. Directions refer to instability pressure, not a probability forecast.",
    "This was a retrieval and source-admission review, not a completed independent audit. Media assertions remain attributed.",
    "The protest article displays an update time earlier than its displayed original time. Metadata inconsistency remains unresolved.",
    "The border halt is dated October 20 and not assumed ongoing at the original cutoff; reopening was an attributed claim.",
    "Regional export estimates do not establish normal Hormuz traffic or independent Iranian oil-export recovery.",
    "A regional de-escalation article was paywalled beyond its introduction; substantive source access remains incomplete.",
    "Older coercion investigations concern January events and cannot establish a new October crackdown.",
    "Medicine and foreign-exchange searches supplied no adequately grounded new observation.",
    "BBC Persian and Radio Farda searches exposed secondary transcripts and changing homepages, not certified original reports.",
    "Wire reprints and official claims were not counted as independent corroboration or proof of Iran-to-Houthi resupply.",
    "Historical evidence records were neither carried forward nor counted again.",
]

START = dt.datetime(
    2026, 10, 21, 17, 55, 46,
    tzinfo=dt.timezone(dt.timedelta(hours=-4)))
LATER = START + dt.timedelta(minutes=15)


class StageNormalizationTests(unittest.TestCase):
    def setUp(self):
        context = tempfile.TemporaryDirectory(prefix="iran-limitation-replay-")
        self.addCleanup(context.cleanup)
        self.folder = Path(context.name)
        self.model = "gpt-6.1-sol"
        self.calls = []

    def _response(self, prompt, search):
        self.assertTrue(search)
        match = re.search(r"This stage is ONLY category: ([a-z_]+)", prompt)
        self.assertIsNotNone(match)
        category = match.group(1)
        self.calls.append(category)
        index = CATEGORIES.index(category)
        url = f"https://research.example.org/regional-source-{index}"
        limits = (copy.deepcopy(REGIONAL_LIMITATIONS)
                  if category == "regional_multilingual_media" else
                  "Original publication times were not independently verified; this is a test.")
        obj = {
            "coverage_audit": [{
                "category": category, "queries": [
                    "Independent original source coverage in Iranian research"],
                "outcome": "eligible_reporting_found",
                "original_urls": [url],
                "limitations": limits,
            }],
            "evidence": [{
                "event_date": "2026-10-20", "category": category,
                "observation": f"One illustrative, unverified event for {category}.",
                "source": url, "source_title": "Original example article",
                "publisher": f"Publisher {index}", "reliability": "Medium",
                "affects": [], "evidence_status": "new",
                "impact_magnitude": "minor",
                "direction": ("raises", "lowers", "ambiguous")[index % 3],
                "effect_type": "background_context", "direction_basis": None,
            }],
            "source_quality": [{
                "url": url, "kind": "attributed_claim",
                "origin": "original_reporting", "corroborating_urls": [],
                "assessment": "Only an attributed claim is available in this model source.",
                "limitations": "The original account and first-publication instant have not been verified."
            }]
        }
        calls = observed_search_calls([{
            "type": "web_search_call", "action": {
                "type": "search",
                "query": "Iran original media source independent review",
                "sources": [{"url": url, "title": "Original example"}]}}])
        id_ = f"resp_researchsource{index+30}"
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        request = responses_payload(prompt, True)
        request["background"] = True
        request_sha = sha(request)
        save_new(self.folder / f"api-request-test-{index}.json", {
            "request_sha256": request_sha,
            "response_id": id_,
            "status": "api_completed_output_not_yet_validated",
            "post_attempts": 1})
        save_new(self.folder / f"response-{index+1}.json", {
            "model": self.model, "response_id": id_, "search": True,
            "result": obj, "citations": [url], "tool_search_calls": calls,
            "prompt_sha256": prompt_sha})
        return obj, {url}

    def _run(self, researcher, *, resume=False, clock=START):
        with patch.object(assessment_pipeline, "LIVE_RESEARCHER", researcher):
            with patch.dict(os.environ, {"IRAN_FORECAST_MODEL": ""}, clear=False):
                return batched_research(
                    researcher=researcher, folder=self.folder, prior=[],
                    day=clock.date().isoformat(), baseline_sha="b"*64,
                    started_at=clock, resume=resume)

    def test_eleven_original_statements_are_ordered_and_raw_response_unchanged(self):
        original = {
            "coverage_audit": [{"limitations": copy.deepcopy(REGIONAL_LIMITATIONS)}],
            "source_quality": [{"limitations": [
                "First independent limitation needs verification and original access.",
                "Second sentence is a separate source-specific disclosure."
            ]}],
            "evidence": [{"id": "untouched", "direction": "raises"}]
        }
        untouched = copy.deepcopy(original)
        normalized, changes = _normalize_limitation_lists(original)
        self.assertEqual(original, untouched)
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0]["path"], ["coverage_audit", 0, "limitations"])
        self.assertEqual(changes[0]["original_value"], REGIONAL_LIMITATIONS)
        self.assertEqual(
            normalized["coverage_audit"][0]["limitations"],
            "\n".join(REGIONAL_LIMITATIONS))
        self.assertEqual(
            normalized["source_quality"][0]["limitations"],
            "First independent limitation needs verification and original access.\n"
            "Second sentence is a separate source-specific disclosure.")
        self.assertEqual(normalized["evidence"], untouched["evidence"])
        self.assertNotEqual(sha(normalized), sha(original))

    def test_invalid_or_ambiguous_limitation_lists_are_rejected_not_repaired(self):
        for invalid in ([], [""], ["valid", None], ["valid", 2],
                        ["one"]*33, ["x"*6001]):
            with self.subTest(invalid=str(invalid)[:60]):
                original = {"coverage_audit": [{"limitations": invalid}]}
                with self.assertRaisesRegex(ValueError, "limitations list"):
                    _normalize_limitation_lists(original)
        # Other structured fields do not get coerced to strings.
        original = {"coverage_audit": [{"limitations": "A compliant string",
                  "original_urls": ["https://example.org/source"]}]}
        normalized, changes = _normalize_limitation_lists(original)
        self.assertEqual(normalized, original)
        self.assertEqual(changes, [])

    def test_completed_saved_response_recovers_after_interrupted_third_stage(self):
        def interrupted(prompt, search):
            category = re.search(r"This stage is ONLY category: ([a-z_]+)",
                                 prompt).group(1)
            if category == "regional_multilingual_media":
                obj, urls = self._response(prompt, search)
                raise RuntimeError("Simulate old list-format validation failure")
            return self._response(prompt, search)
        with self.assertRaisesRegex(RuntimeError, "old list-format"):
            self._run(interrupted)
        response_path = self.folder / "response-3.json"
        saved_response = response_path.read_bytes()
        original_one = (self.folder / "research-batch-primary_data.json").read_bytes()
        original_two = (self.folder / "research-batch-international_media.json").read_bytes()
        self.assertFalse((self.folder /
                          "research-batch-regional_multilingual_media.json").exists())
        self.assertFalse((self.folder /
                          "research-stage-format-regional_multilingual_media.json").exists())
        self.calls.clear()
        original_fake = interrupted
        def finish(prompt, search):
            category = re.search(r"This stage is ONLY category: ([a-z_]+)",
                                 prompt).group(1)
            if category in CATEGORIES[:3]:
                self.fail("A saved and completed source search must not POST again")
            return self._response(prompt, search)
        result, cited, trace, snapshot = self._run(finish, resume=True, clock=LATER)
        self.assertEqual(self.calls, list(CATEGORIES)[3:])
        # Fresh LIVE research now uses v4; an archived v3 snapshot retains v3.
        self.assertEqual(snapshot["version"], 4)
        self.assertEqual(len(result["coverage_audit"]), 6)
        self.assertEqual(len(cited), 6)
        self.assertEqual(len(trace), 6)
        self.assertEqual(
            result["coverage_audit"][2]["limitations"],
            "\n".join(REGIONAL_LIMITATIONS))
        self.assertEqual(response_path.read_bytes(), saved_response)
        self.assertEqual((self.folder /
            "research-batch-primary_data.json").read_bytes(), original_one)
        self.assertEqual((self.folder /
            "research-batch-international_media.json").read_bytes(), original_two)
        stage = read_json(
            self.folder / "research-batch-regional_multilingual_media.json")
        self.assertEqual(stage["result"]["coverage_audit"][0]["limitations"],
                         REGIONAL_LIMITATIONS)
        self.assertEqual(stage["effective_result"]["coverage_audit"][0][
                         "limitations"], "\n".join(REGIONAL_LIMITATIONS))
        audit = read_json(
            self.folder / "research-stage-format-regional_multilingual_media.json")
        self.assertEqual(audit["original_response_id"],
                         read_json(response_path)["response_id"])
        self.assertEqual(audit["original_result_sha256"],
                         sha(read_json(response_path)["result"]))
        self.assertEqual(audit["effective_result_sha256"],
                         sha(stage["effective_result"]))
        self.assertEqual(audit["snapshot_sha256"], snapshot["snapshot_sha256"])
        self.assertEqual(stage["normalization_sha256"], sha(audit))
        self.assertEqual(audit["publication"], "NOT AUTHORIZED")
        self.calls.clear()
        replay = self._run(
            lambda *args: self.fail("Complete replay cannot repeat paid searches"),
            resume=True, clock=LATER + dt.timedelta(minutes=1))
        self.assertEqual(replay[:3], (result, cited, trace))
        self.assertEqual(self.calls, [])
        self.assertEqual(response_path.read_bytes(), saved_response)

    def test_tampered_audit_or_response_blocks_resume(self):
        self._run(self._response)
        path = self.folder / "research-stage-format-regional_multilingual_media.json"
        audit = read_json(path)
        audit["changes"][0]["effective_value"] = "Invented change"
        path.write_text(json.dumps(audit))
        with self.assertRaisesRegex(ValueError, "normalization differs"):
            self._run(lambda *args: self.fail("No network"), resume=True, clock=LATER)
        self.assertEqual(len(list(self.folder.glob("research-batch-*.json"))), 6)

    def test_changed_completed_response_or_request_journal_is_not_resumed(self):
        self._run(self._response)
        response_path = self.folder / "response-3.json"
        original = response_path.read_bytes()
        changed = read_json(response_path)
        changed["result"]["coverage_audit"][0]["limitations"][0] = (
            "A different unsupported claim was inserted after the paid research.")
        response_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "matching saved Responses output"):
            self._run(lambda *args: self.fail("No replay POST"), resume=True,
                      clock=LATER)
        response_path.write_bytes(original)
        journal_path = self.folder / "api-request-test-2.json"
        original_journal = journal_path.read_bytes()
        journal = read_json(journal_path)
        journal["request_sha256"] = "0" * 64
        journal_path.write_text(json.dumps(journal))
        with self.assertRaisesRegex(ValueError, "matching completed API transport"):
            self._run(lambda *args: self.fail("No replay POST"), resume=True,
                      clock=LATER)
        journal_path.write_bytes(original_journal)

    def test_unverified_responses_are_not_normalized_or_replayed(self):
        folder = self.folder
        snap = {"snapshot_sha256": "s"*64}
        raw = {"coverage_audit": [{"limitations": ["one", "two"]}]}
        with self.assertRaisesRegex(ValueError, "response not verified"):
            _verified_stage_normalization(
                folder, "regional_multilingual_media", raw,
                snapshot=snap, prompt_sha="a"*64, model=self.model,
                request_sha="b"*64, response=None)
        self.assertFalse((folder /
                          "research-stage-format-regional_multilingual_media.json").exists())


if __name__ == "__main__":
    unittest.main()
