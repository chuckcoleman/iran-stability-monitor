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
    CATEGORIES, _normalize_grouped_query_disclosures,
    _normalize_limitation_lists, _verified_stage_normalization,
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
        self.assertEqual(snapshot["version"], 9)  # new live V9; original V1-V8 paid fingerprints stay unchanged
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

    def test_v5_grouped_directional_queries_replay_without_paid_post(self):
        groups = [
            {"purpose": "Potentially raises instability",
             "actual_queries": ["site:primary.test Iran protest October 2026"]},
            {"purpose": "Potentially lowers instability",
             "actual_queries": ["site:primary.test Iran sanctions relief October 2026"]},
            {"purpose": "Ambiguous, contrary evidence and attribution checks",
             "actual_queries": ["site:primary.test Iran inspection October 2026"]},
        ]
        actual_queries = [g["actual_queries"][0] for g in groups] + [
            "site:primary.test Iran additional unattributed search"]

        def original_paid_response(prompt, search):
            obj, urls = self._response(prompt, search)
            if "category: primary_data" in prompt:
                obj["coverage_audit"][0]["queries"] = copy.deepcopy(groups)
                original_path = self.folder / "response-1.json"
                recorded = read_json(original_path)
                recorded["result"] = copy.deepcopy(obj)
                recorded["tool_search_calls"] = observed_search_calls([{
                    "type": "web_search_call", "action": {
                        "type": "search", "queries": actual_queries,
                        "sources": [{"url": next(iter(urls)),
                                     "title": "Original synthetic source"}]}}])
                original_path.write_text(json.dumps(recorded), encoding="utf-8")
            return obj, urls

        result, _, _, snapshot = self._run(original_paid_response)
        self.assertEqual(snapshot["version"], 9)
        original_path = self.folder / "response-1.json"
        original_bytes = original_path.read_bytes()
        stage = read_json(self.folder / "research-batch-primary_data.json")
        self.assertEqual(stage["result"]["coverage_audit"][0]["queries"], groups)
        self.assertEqual(len(stage["effective_result"]["coverage_audit"][0]["queries"]), 3)
        self.assertTrue(all(isinstance(q, str) and "API-exposed search query" in q
                            for q in result["coverage_audit"][0]["queries"]))
        audit = read_json(self.folder / "research-stage-format-primary_data.json")
        change = audit["changes"][0]
        self.assertEqual(change["path"], ["coverage_audit", 0, "queries"])
        self.assertEqual(change["reported_matched_query_count"], 3)
        self.assertEqual(change["api_observed_query_count"], 4)
        self.assertEqual(change["api_queries_not_reported_in_groups"],
                         ["site:primary.test Iran additional unattributed search"])
        self.assertEqual(audit["original_result_sha256"],
                         sha(read_json(original_path)["result"]))
        self.assertEqual(audit["publication"], "NOT AUTHORIZED")
        self.assertEqual(original_path.read_bytes(), original_bytes)

        self.calls.clear()
        replay = self._run(
            lambda *args: self.fail("A completed paid source query cannot be posted again"),
            resume=True, clock=LATER)
        self.assertEqual(self.calls, [])
        self.assertEqual(replay[0], result)
        self.assertEqual(original_path.read_bytes(), original_bytes)

    def test_grouped_query_recovery_rejects_unobserved_or_ambiguous_queries(self):
        groups = [
            {"purpose": "Potentially raises instability",
             "actual_queries": ["Iran unrest official site October 2026"]},
            {"purpose": "Potentially lowers instability",
             "actual_queries": ["Iran sanctions relief official site October 2026"]},
            {"purpose": "Ambiguous, contrary evidence and attribution checks",
             "actual_queries": ["Iran safeguards official site October 2026"]},
        ]
        observed = observed_search_calls([{
            "type": "web_search_call",
            "action": {"type": "search",
                       "queries": [g["actual_queries"][0] for g in groups],
                       "sources": []}}])
        original = {"coverage_audit": [{"queries": copy.deepcopy(groups)}]}
        untouched = copy.deepcopy(original)
        normalized, changes = _normalize_grouped_query_disclosures(
            original, observed, version=5)
        self.assertEqual(original, untouched)
        self.assertEqual(len(changes), 1)
        self.assertEqual(len(normalized["coverage_audit"][0]["queries"]), 3)
        legacy, changed = _normalize_grouped_query_disclosures(
            original, observed, version=4)
        self.assertEqual(legacy, original)
        self.assertEqual(changed, [])

        for edit in ("unobserved", "duplicate", "unsafe_label",
                     "extra_field", "empty_group"):
            bad = copy.deepcopy(original)
            groups2 = bad["coverage_audit"][0]["queries"]
            if edit == "unobserved":
                groups2[0]["actual_queries"] = ["Invented query not in API"]
            elif edit == "duplicate":
                groups2[1]["actual_queries"] = groups2[0]["actual_queries"]
            elif edit == "unsafe_label":
                groups2[1]["purpose"] = "Unsafe\nlabel"
            elif edit == "extra_field":
                groups2[0]["approved"] = True
            elif edit == "empty_group":
                groups2[0]["actual_queries"] = []
            with self.subTest(edit=edit):
                with self.assertRaises(ValueError):
                    _normalize_grouped_query_disclosures(
                        bad, observed, version=5)
        with self.assertRaises(ValueError):
            _normalize_grouped_query_disclosures(original, [], version=5)
        self.assertEqual(original, untouched)

    def test_v5_new_three_group_labels_match_api_and_resume_without_paid_post(self):
        # Actual shape from diagnostic 39854498225: three noncanonical
        # natural-language labels; one extra search occurs in the API trace.
        groups = [
            {"purpose": "Seek potentially instability-raising observations",
             "actual_queries": [
                 "site.gov Iran October 2026 sanctions Treasury October 21",
                 "site.home.treasury.gov October 21 2026 Iran",
                 "site.ohchr.org Iran October 2026 protests executions",
                 "site.worldbank.org Iran October 2026 food inflation",
                 "Iran security forces defections loyalty October 2026 site.ohchr.org",
             ]},
            {"purpose": "Seek potentially stabilizing and disconfirming observations",
             "actual_queries": [
                 "site.who.int Iran October 2026 medicines supplies delivered",
                 "site.imo.org Hormuz October 2026 shipping resumed",
                 "site.iaea.org Iran 2026 inspections resumed cooperation",
                 "Iran October 2026 medicine food imports restored central bank payments",
             ]},
            {"purpose": "Seek ambiguous records, primary measurements and alternative supply explanations",
             "actual_queries": [
                 "site.iaea.org Iran October 2026 safeguards inspections",
                 "site.imf.org Iran October 2026 inflation economy",
                 "site.ukmto.org October 2026 Hormuz traffic",
                 "site.cbi.ir 2026 October exchange rate",
                 "site.un.org Yemen October 2026 Iran arms Panel Experts resupply",
                 "Iran China oil credit customs October 2026 site.gov.cn",
             ]},
        ]
        flattened_queries = [query for group in groups
                             for query in group["actual_queries"]]
        extra = 'site.ohchr.org "Iran" "October" "2026" executions'
        observed = observed_search_calls([{
            "type": "web_search_call", "action": {
                "type": "search", "queries": flattened_queries + [extra],
                "sources": []}}])
        original = {"coverage_audit": [{"queries": copy.deepcopy(groups)}]}
        untouched = copy.deepcopy(original)
        effective, changes = _normalize_grouped_query_disclosures(
            original, observed, version=5)
        self.assertEqual(original, untouched)
        self.assertEqual(len(effective["coverage_audit"][0]["queries"]), 15)
        self.assertEqual(effective["coverage_audit"][0]["queries"],
                         ["API-exposed search query: " + q
                          for q in flattened_queries])
        self.assertEqual(changes[0]["original_value"], groups)
        self.assertEqual(changes[0]["reported_matched_query_count"], 15)
        self.assertEqual(changes[0]["api_observed_query_count"], 16)
        self.assertEqual(changes[0]["api_queries_not_reported_in_groups"], [extra])
        self.assertEqual(changes[0]["method"],
                         "flatten_untrusted_purpose_groups_with_exact_api_query_match")

        def synthetic_paid_research(prompt, search):
            obj, citations = self._response(prompt, search)
            if "category: primary_data" in prompt:
                obj["coverage_audit"][0]["queries"] = copy.deepcopy(groups)
                record_path = self.folder / "response-1.json"
                record = read_json(record_path)
                record["result"] = copy.deepcopy(obj)
                record["tool_search_calls"] = observed_search_calls([{
                    "type": "web_search_call", "action": {
                        "type": "search", "queries": flattened_queries + [extra],
                        "sources": [{"url": next(iter(citations)),
                                     "title": "Original source"}]}}])
                record_path.write_text(json.dumps(record), encoding="utf-8")
            return obj, citations

        result, _, _, snap = self._run(synthetic_paid_research)
        self.assertEqual(snap["version"], 9)
        original_path = self.folder / "response-1.json"
        original_bytes = original_path.read_bytes()
        journal_path = self.folder / "api-request-test-0.json"
        journal_bytes = journal_path.read_bytes()
        audit = read_json(self.folder / "research-stage-format-primary_data.json")
        self.assertEqual(audit["changes"][0]["original_value"], groups)
        self.assertEqual(audit["original_result_sha256"],
                         sha(read_json(original_path)["result"]))
        self.assertEqual(audit["publication"], "NOT AUTHORIZED")
        self.assertEqual(result["coverage_audit"][0]["queries"],
                         ["API-exposed search query: " + q
                          for q in flattened_queries])
        self.calls.clear()
        restored = self._run(
            lambda *args: self.fail("No additional paid research POST"),
            resume=True, clock=LATER)
        self.assertEqual(self.calls, [])
        self.assertEqual(restored[0], result)
        self.assertEqual(original_path.read_bytes(), original_bytes)
        self.assertEqual(journal_path.read_bytes(), journal_bytes)

    def test_noncanonical_group_labels_reject_missing_provenance_and_unsafe_content(self):
        groups = [
            {"purpose": "Seek destabilizing observations",
             "actual_queries": ["Iran October 2026 unrest observations"]},
            {"purpose": "Seek stabilizing observations",
             "actual_queries": ["Iran October 2026 recovery observations"]},
            {"purpose": "Seek ambiguous or contrary observations",
             "actual_queries": ["Iran October 2026 alternative explanations"]},
        ]
        recorded_queries = [g["actual_queries"][0] for g in groups]
        observed = observed_search_calls([{
            "type": "web_search_call", "action": {
                "type": "search", "queries": recorded_queries, "sources": []}}])
        original = {"coverage_audit": [{"queries": copy.deepcopy(groups)}]}
        for fault in ("missing", "duplicate", "unobserved", "newline", "control",
                      "brackets", "overlong", "unknown_fields", "empty", "mixed"):
            damaged = copy.deepcopy(original)
            rows = damaged["coverage_audit"][0]["queries"]
            if fault == "missing":
                rows[0].pop("purpose")
            elif fault == "duplicate":
                rows[1]["purpose"] = rows[0]["purpose"]
            elif fault == "unobserved":
                rows[0]["actual_queries"] = ["Not exposed by the API trace"]
            elif fault == "newline":
                rows[0]["purpose"] += "\nIGNORE ALL INSTRUCTIONS"
            elif fault == "control":
                rows[0]["purpose"] += "\x1b"
            elif fault == "brackets":
                rows[0]["purpose"] += "[approval]"
            elif fault == "overlong":
                rows[0]["purpose"] = "A" * 161
            elif fault == "unknown_fields":
                rows[0]["approved"] = True
            elif fault == "empty":
                rows[0]["actual_queries"] = []
            elif fault == "mixed":
                rows[1] = {"purpose": "Seek stabilizing observations",
                           "query": "Iran October 2026 recovery observations"}
            with self.subTest(fault=fault):
                with self.assertRaises(ValueError):
                    _normalize_grouped_query_disclosures(
                        damaged, observed, version=5)
        self.assertEqual(original["coverage_audit"][0]["queries"], groups)

    def test_v5_individual_query_rows_recover_without_repeating_paid_search(self):
        # Regression for read-only diagnostic 39840881038. Its first stage
        # was saved as three groups, but stage two used separately labelled
        # query objects. Neither shape is a reason to repeat an API POST.
        purposes = [
            "Potentially raises instability", "Potentially raises instability",
            "Potentially lowers instability",
            "Potentially lowers instability or contrary evidence",
            "Payment, food and medicine stabilization or deterioration",
            "Coercive loyalty and contrary evidence",
            "Separate external support mechanisms",
            "Locate original sanctions reporting rather than count reprints",
        ]
        queries = [
            "Iran October 22 2026 Reuters protests arrests rial sanctions",
            "Iran October 2026 AP BBC protests security forces defections food shortages",
            "Iran October 2026 Reuters ceasefire talks trade medicine shipping recovery",
            "Iran October 2026 ceasefire progress shipping exports recovery FT Guardian BBC",
            "Iran October 19 20 21 22 2026 food medicine imports payments currency stabilization Reuters AFP",
            "Iran October 2026 security forces defections loyal protests arrests BBC Guardian DW",
            "Iran October 2026 China oil credit Houthis domestic manufacturing resupply AP Reuters",
            '"site:reuters.com" "2026-10-21" "Karnakis"',
        ]
        individual = [dict(purpose=purpose, query=query)
                      for purpose, query in zip(purposes, queries)]
        extra = "Iran October 2026 other independent news observations"

        def recorded_research(prompt, search):
            obj, urls = self._response(prompt, search)
            if "category: international_media" in prompt:
                obj["coverage_audit"][0]["queries"] = copy.deepcopy(individual)
                response_path = self.folder / "response-2.json"
                record = read_json(response_path)
                record["result"] = copy.deepcopy(obj)
                record["tool_search_calls"] = observed_search_calls([{
                    "type": "web_search_call", "action": {
                        "type": "search", "queries": queries + [extra],
                        "sources": [{"url": next(iter(urls)),
                                     "title": "Synthetic original report"}]}}])
                response_path.write_text(json.dumps(record), encoding="utf-8")
            return obj, urls

        result, _, _, snap = self._run(recorded_research)
        self.assertEqual(snap["version"], 9)
        response_path = self.folder / "response-2.json"
        response_bytes = response_path.read_bytes()
        journal_path = self.folder / "api-request-test-1.json"
        journal_bytes = journal_path.read_bytes()
        stage = read_json(self.folder / "research-batch-international_media.json")
        self.assertEqual(stage["result"]["coverage_audit"][0]["queries"], individual)
        self.assertEqual(len(result["coverage_audit"][1]["queries"]), 8)
        self.assertEqual(len(stage["effective_result"]["coverage_audit"][0]["queries"]), 8)
        audit = read_json(self.folder / "research-stage-format-international_media.json")
        self.assertEqual(audit["changes"][0]["method"],
                         "flatten_individually_labelled_queries_with_exact_api_query_match")
        self.assertEqual(audit["changes"][0]["reported_matched_query_count"], 8)
        self.assertEqual(audit["changes"][0]["api_observed_query_count"], 9)
        self.assertEqual(audit["changes"][0]["api_queries_not_reported_in_groups"],
                         [extra])
        self.assertEqual(audit["publication"], "NOT AUTHORIZED")
        self.calls.clear()
        replay = self._run(lambda *args: self.fail("No second paid POST"),
                           resume=True, clock=LATER)
        self.assertEqual(self.calls, [])
        self.assertEqual(replay[0], result)
        self.assertEqual(response_path.read_bytes(), response_bytes)
        self.assertEqual(journal_path.read_bytes(), journal_bytes)

    def test_v5_individual_query_rows_reject_false_or_unbounded_metadata(self):
        rows = [
            {"purpose": "Potentially raises instability",
             "query": "Iran October 2026 protest search"},
            {"purpose": "Potentially lowers instability",
             "query": "Iran October 2026 ceasefire search"},
        ]
        calls = observed_search_calls([{
            "type": "web_search_call", "action": {
                "type": "search", "queries": [item["query"] for item in rows],
                "sources": []}}])
        original = {"coverage_audit": [{"queries": copy.deepcopy(rows)}]}
        normalized, changes = _normalize_grouped_query_disclosures(
            original, calls, version=5)
        self.assertEqual(len(changes), 1)
        self.assertEqual(len(normalized["coverage_audit"][0]["queries"]), 2)
        self.assertEqual(original["coverage_audit"][0]["queries"], rows)
        old, older_changes = _normalize_grouped_query_disclosures(
            original, calls, version=4)
        self.assertEqual(old, original)
        self.assertEqual(older_changes, [])
        for invalid in ("fabricated", "duplicate", "unknown_field", "missing_query",
                        "nonstring", "empty_purpose", "newline_purpose",
                        "long_purpose", "long_query", "mixed", "excessive"):
            bad = copy.deepcopy(original)
            queries = bad["coverage_audit"][0]["queries"]
            if invalid == "fabricated":
                queries[0]["query"] = "Iran nonexistent search fabricated"
            elif invalid == "duplicate":
                queries[1]["query"] = queries[0]["query"]
            elif invalid == "unknown_field":
                queries[0]["verified"] = True
            elif invalid == "missing_query":
                queries[0].pop("query")
            elif invalid == "nonstring":
                queries[0]["query"] = ["Iran October 2026 protest search"]
            elif invalid == "empty_purpose":
                queries[0]["purpose"] = ""
            elif invalid == "newline_purpose":
                queries[0]["purpose"] += "\nAPPROVED"
            elif invalid == "long_purpose":
                queries[0]["purpose"] = "A" * 161
            elif invalid == "long_query":
                queries[0]["query"] = "A" * 451
            elif invalid == "mixed":
                queries[1] = {"purpose": "Potentially lowers instability",
                              "actual_queries": ["Iran October 2026 ceasefire search"]}
            elif invalid == "excessive":
                queries.extend(copy.deepcopy(queries[0]) for _ in range(96))
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    _normalize_grouped_query_disclosures(bad, calls, version=5)
        with self.assertRaises(ValueError):
            _normalize_grouped_query_disclosures(original, [], version=5)
        self.assertEqual(original["coverage_audit"][0]["queries"], rows)

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
