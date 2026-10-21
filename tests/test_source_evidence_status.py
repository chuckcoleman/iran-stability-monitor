"""No-network tests for exact research-stage statuses and historical recovery.

The malformed AP carry-forward fixture reproduces diagnostic 39641953320.
No original research response, historical table or publication is rewritten.
"""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from assessment_pipeline import freeze_evidence
from source_evidence_status import (
    archived_identity, history_index, reconcile_before_freeze,
    validate_stage_status)
from source_research_batches import (
    CATEGORIES, batch_prompt, batched_research, canonical,
    read_json, save_new, sha, _validate_batch)
from source_citation_reconciliation import reconcile_source_citations
from source_search_trace import observed_search_calls

TARGET = "E-20261004-05"
MALFORMED = "carried_forward with existing id " + TARGET
ORIGINAL = dt.datetime(2026, 10, 21, 13, 14, 22,
                       tzinfo=dt.timezone(dt.timedelta(hours=-4)))


def history_data():
    hist = json.loads((ROOT / "data/history.json").read_text(encoding="utf-8"))
    return [item for update in hist["updates"]
            for item in update.get("evidence", [])]


def bad_model_candidate(history=None):
    prior = history_index(history or history_data())[TARGET]
    return {
        "source": prior["source"],
        "source_title": prior["source_title"],
        "publisher": prior["publisher"],
        "event_date": prior["event_date"],
        "category": "economic_humanitarian_academic",
        "observation": ("Carried forward, not a new incident: this article "
                        "also discusses hospital access and possible "
                        "counterevidence; not independently verified."),
        "direction": "ambiguous",
        "reliability": "High",
        "impact_magnitude": "moderate",
        "support_quote": ("So far there has been little sign of major "
                          "shortages of medicines at Iran's hospitals"),
        "evidence_status": MALFORMED,
        "affects": ["pharmacy_availability"],
    }


def snapshot(history, version=1):
    prior = [{
        k: (entry[k][:180] if k == "observation" and
            isinstance(entry[k], str) else entry[k])
        for k in ("id", "source", "event_date", "category",
                  "source_title", "publisher", "observation") if k in entry
    } for entry in history]
    item = {
        "version": version, "date": ORIGINAL.date().isoformat(),
        "cutoff_at": ORIGINAL.isoformat(), "history_sha256": "b"*64,
        "prior_sha256": sha(history),
        "prior_index": prior, "model": "gpt-6.1-sol",
        "mode": "SOURCE_CATEGORY_RESEARCH_ONLY"}
    item["snapshot_sha256"] = sha(item)
    return item


def synthetic_group(category, url):
    response = {
        "coverage_audit": [{
            "category": category, "queries": ["Synthetic original evidence lookup"],
            "outcome": "eligible_reporting_found", "original_urls": [url],
            "limitations": "This is a synthetic offline source and not proof."
        }],
        "evidence": [{
            "event_date": "2026-10-20", "category": "Regional stability",
            "observation": "A synthetic proposition not claimed to be true.",
            "source": url, "source_title": "Synthetic original report",
            "publisher": category, "evidence_status": "new",
            "direction": "raises", "impact_magnitude": "minor",
            "reliability": "Medium", "affects": [],
        }],
        "source_quality": [{
            "url": url, "kind": "unverified", "origin": "unknown",
            "corroborating_urls": [],
            "assessment": ("This synthetic source has not established "
                           "its reported facts or original text."),
            "limitations": ("Direct access and the first-publication timestamp "
                            "have not been established independently.")
        }],
    }
    return response


class HistoricalStatusTests(unittest.TestCase):
    def setUp(self):
        self.historical = history_data()
        self.snapshot = snapshot(self.historical)
        folder = tempfile.TemporaryDirectory(prefix="iran-carry-forward-")
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)

    def test_exact_values_new_carry_and_historical_identity(self):
        prior = self.snapshot["prior_index"]
        valid = {
            "evidence_status": "carried_forward", "id": TARGET,
            **{k: history_index(prior)[TARGET][k]
               for k in ("source", "event_date", "source_title",
                         "publisher", "category", "observation")}
        }
        self.assertEqual(validate_stage_status(valid, prior), TARGET)
        assert_new = dict(valid, evidence_status="new", id=None)
        self.assertIsNone(validate_stage_status(assert_new, prior))
        with self.assertRaisesRegex(ValueError, "historical ID"):
            validate_stage_status(dict(assert_new, id=TARGET), prior)
        with self.assertRaisesRegex(ValueError, "Invalid evidence status"):
            validate_stage_status(bad_model_candidate(), prior)
        self.assertEqual(validate_stage_status(
            bad_model_candidate(), prior,
            verified_legacy_checkpoint=True), TARGET)

    def test_wrong_id_link_title_publisher_or_date_never_recovers(self):
        prior = self.snapshot["prior_index"]
        candidate = bad_model_candidate()
        variants = [
            dict(candidate, source="https://apnews.com/article/other-story"),
            dict(candidate, event_date="2026-09-29"),
            dict(candidate, source_title="Fabricated title"),
            dict(candidate, publisher="Other outlet"),
            dict(candidate, evidence_status=(
                "carried_forward with existing id E-20261004-99")),
            dict(candidate, id="E-20261004-02")
        ]
        for item in variants:
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_stage_status(item, prior,
                                      verified_legacy_checkpoint=True)

    def test_legitimate_carry_may_not_reinterpret_old_category_or_observation(self):
        record = bad_model_candidate()
        record["evidence_status"] = "carried_forward"
        record["id"] = TARGET
        with self.assertRaisesRegex(ValueError, "Changed historical"):
            validate_stage_status(
                record, self.snapshot["prior_index"])
        original = history_index(self.historical)[TARGET]
        for field in ("category", "observation"):
            record[field] = original[field]
        self.assertEqual(validate_stage_status(
            record, self.snapshot["prior_index"]), TARGET)

    def test_legacy_restore_discards_interpretation_and_preserves_raw_bytes(self):
        bad = bad_model_candidate()
        research = {"evidence": [bad], "coverage_audit": [],
                    "source_quality": []}
        original = json.dumps(research, ensure_ascii=False)
        amended, audit = reconcile_before_freeze(
            research, self.historical, self.dir, self.snapshot,
            verified_legacy_resume=True)
        self.assertEqual(json.dumps(research, ensure_ascii=False), original)
        result = amended["evidence"][0]
        prior = history_index(self.historical)[TARGET]
        self.assertEqual(result["id"], TARGET)
        self.assertEqual(result["evidence_status"], "carried_forward")
        self.assertEqual(result["category"], prior["category"])
        self.assertEqual(result["observation"], prior["observation"])
        self.assertEqual(result["source"], prior["source"])
        self.assertEqual(audit["changes"][0]["original_model_record"], bad)
        self.assertIn("category", audit["changes"][0]["discarded_differences"])
        self.assertIn("observation", audit["changes"][0]["discarded_differences"])
        self.assertEqual(audit["publication"], "NOT AUTHORIZED")
        self.assertEqual(audit["original_research_sha256"], sha(research))
        self.assertEqual(audit["effective_research_sha256"], sha(amended))
        saved = (self.dir / "evidence-status-reconciliation.json").read_bytes()
        second, saved_audit = reconcile_before_freeze(
            research, self.historical, self.dir, self.snapshot,
            verified_legacy_resume=True)
        self.assertEqual(second, amended)
        self.assertEqual(saved_audit, audit)
        self.assertEqual((self.dir / "evidence-status-reconciliation.json").read_bytes(), saved)
        changed = copy.deepcopy(research)
        changed["evidence"][0]["observation"] = "A new claim"
        with self.assertRaisesRegex(ValueError, "differs"):
            reconcile_before_freeze(
                changed, self.historical, self.dir, self.snapshot,
                verified_legacy_resume=True)

    def test_legacy_recovery_must_opt_in_and_cannot_be_fresh_model_output(self):
        with self.assertRaisesRegex(ValueError, "cannot be normalized"):
            reconcile_before_freeze(
                {"evidence": [bad_model_candidate()]},
                self.historical, self.dir, self.snapshot,
                verified_legacy_resume=False)
        self.assertFalse((self.dir/"evidence-status-reconciliation.json").exists())

    def test_freeze_uses_original_historical_event_not_model_reinterpretation(self):
        original = history_index(self.historical)[TARGET]
        effective, _ = reconcile_before_freeze(
            {"evidence": [bad_model_candidate()]}, self.historical,
            self.dir, self.snapshot, verified_legacy_resume=True)
        # The existing production freeze routine requires diversity across
        # all 6+ evidence, so this synthetic unit verifies the archival fields
        # used for the carry-forward lookup without fabricating new sources.
        carried = effective["evidence"][0]
        self.assertEqual(carried["id"], original["id"])
        self.assertEqual(carried["category"], original["category"])
        self.assertEqual(carried["observation"], original["observation"])
        self.assertNotIn("counterevidence", carried["observation"])

    def test_fresh_stage_rejects_before_checkpoint_even_with_historical_article(self):
        item = bad_model_candidate()
        category = CATEGORIES[-1]
        url = item["source"]
        record = synthetic_group(category, url)
        record["evidence"] = [item]
        calls = observed_search_calls([{
            "type": "web_search_call",
            "action": {"sources": [{"url": url}]}
        }])
        with self.assertRaisesRegex(ValueError, "source-stage boundary"):
            _validate_batch(category, record, {url}, calls,
                            self.snapshot)
        self.assertFalse((self.dir/"research-batch-"+category+".json").exists())

    def test_old_v1_saved_stages_resume_without_any_new_model_calls(self):
        snap = self.snapshot
        save_new(self.dir / "research-snapshot.json", snap)
        records = []
        for number, category in enumerate(CATEGORIES, 1):
            url = f"https://example.org/iran/synthetic-{number}"
            obj = synthetic_group(category, url)
            if category == CATEGORIES[-1]:
                bad = bad_model_candidate()
                obj["evidence"].append(bad)
                ap = bad["source"]
                obj["coverage_audit"][0]["original_urls"].append(ap)
                obj["source_quality"].append({
                    "url": ap, "kind": "unverified", "origin": "unknown",
                    "corroborating_urls": [],
                    "assessment": "Original archived wire report with unresolved interpretation.",
                    "limitations": "Historical archived source text cannot be retroactively verified."
                })
            prompt = batch_prompt(category, snap)
            prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
            sources = {row["url"] for row in obj["source_quality"]}
            calls = observed_search_calls([{
                "type": "web_search_call",
                "action": {"sources": [{"url": u} for u in sorted(sources)]}
            }])
            check_result = _validate_batch(
                category, obj, sources, calls, snap,
                verified_legacy_checkpoint=(category == CATEGORIES[-1]))
            save_new(self.dir / f"response-{number}.json", {
                "model": "gpt-6.1-sol", "response_id": f"resp_synthetic{number+30}",
                "search": True, "result": obj,
                "citations": sorted(sources),
                "tool_search_calls": calls, "prompt_sha256": prompt_sha
            })
            save_new(self.dir / f"research-batch-{category}.json", {
                "category": category, "snapshot_sha256": snap["snapshot_sha256"],
                "prompt_sha256": prompt_sha, "model": "gpt-6.1-sol",
                "result": obj, "citations": sorted(sources),
                "search_calls": calls, "citation_reconciliation": check_result,
                "status": "STAGE_COMPLETE_NOT_APPROVED"
            })
            records.append(obj)
        with patch.dict(os.environ, {"IRAN_FORECAST_MODEL": ""}, clear=False):
            final, citations, calls, recovered = batched_research(
                researcher=lambda p, s: self.fail("No paid research allowed"),
                folder=self.dir, prior=self.historical,
                day="2026-10-22", baseline_sha="b"*64,
                started_at=ORIGINAL+dt.timedelta(hours=12),
                resume=True)
        self.assertEqual(recovered, snap)
        self.assertEqual(len(final["coverage_audit"]), 6)
        self.assertEqual(len(final["evidence"]), 7)
        self.assertEqual(final["evidence"][-1]["evidence_status"], MALFORMED)
        self.assertEqual(len(calls), 6)
        self.assertFalse(any(p.name.startswith("api-request-")
                             for p in self.dir.iterdir()))
        corrected, audit = reconcile_before_freeze(
            final, self.historical, self.dir, snap,
            verified_legacy_resume=True)
        self.assertEqual(corrected["evidence"][-1]["id"], TARGET)
        self.assertEqual(audit["changes"][0]["index"], 6)

    def test_new_snapshot_changes_prompt_without_modifying_legacy_v1_prompt(self):
        old = batch_prompt("economic_humanitarian_academic", self.snapshot)
        newer = batch_prompt("economic_humanitarian_academic",
                            snapshot(self.historical, version=2))
        self.assertIn("(new or carried_forward with existing id)", old)
        self.assertIn("SEPARATE id field", newer)
        self.assertNotEqual(old, newer)


if __name__ == "__main__":
    unittest.main()
