"""Exact-URL duplicate decisions, historic failed checkpoint and no-POST replay.

Synthetic source facts are NEVER treated as verified news. These offline tests
reproduce the structure of diagnostic 39688687012 (nine decisions for eight
URLs, including two compatible withdrawals of one ACLED article).
"""
import copy
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

from assessment_pipeline import LIVE_RESEARCHER, responses_payload
from source_citation_reconciliation import reconcile_source_citations
from source_citation_resolution import (
    _correction_prompt, apply_resolutions, consolidate_compatible_resolutions,
    digest, resolve_source_citations, save,
)
from source_research_batches import sha
from test_source_citation_reconciliation import A, B, BAD, trace

UKMTO = "https://www.ukmto.org/ukmto-products/weekly-reports"
NATIONAL = ("https://www.thenationalnews.com/business/energy/2026/10/21/"
            "non-iran-middle-east-oil-exports-recover-to-prewar-levels-with-hormuz-alternatives/")
ACLED = ("https://acleddata.com/expert-comment/"
         "more-entrenched-insurgency-emerging-irans-sistan-and-baluchestan")
ORIGINAL_URLS = [
    UKMTO,
    "https://apnews.com/article/iran-us-war-leadership-politics-khamenei-f2e45b2c77f5994ed9d9534ae988403b",
    NATIONAL,
    "https://www.al-monitor.com/originals/2026/10/turkey-turns-iran-contain-houthis-saudi-defense-commitments-grow",
    ACLED,
    "https://acleddata.com/expert-comment/strait-hormuz-becoming-safer-oil-flows-recover",
    "https://www.lloydslist.com/LL1158741/UAE-owned-VLCC-abandoned-as-attacks-spread-across-Middle-East-Gulf",
    "https://www.lloydslist.com/LL1158752/China-turns-to-new-Middle-East-Gulf-crude-flows-as-Iranian-supplies-squeezed",
]


def research():
    return {
        "evidence": [{
            "source": ACLED, "evidence_status": "new",
            "observation": "Unverified synthetic test of dated original-source interpretation."
        }],
        "coverage_audit": [{
            "category": "regional_multilingual_media",
            "original_urls": list(ORIGINAL_URLS),
            "outcome": "eligible_reporting_found",
            "limitations": "Several original reports lack publication clocks and original-body access."
        }],
        "source_quality": [{
            "url": url, "kind": "unverified", "origin": "unknown",
            "corroborating_urls": [],
            "assessment": "This is only a synthetic attribution and not an independently established event.",
            "limitations": "Independent publisher access and original first-publication timing were not verified."
        } for url in ORIGINAL_URLS]
    }


def decision():
    decisions = []
    for url in ORIGINAL_URLS:
        verified = url in (UKMTO, NATIONAL)
        decisions.append({
            "claimed_url": url,
            "action": "verified" if verified else "withdrawn",
            "replacement_url": None,
            "evidence_replacements": [],
            "reason": (
                "The original link surfaced in a mocked independent source trace, "
                "but its real-world factual support is not established by this offline test."
                if verified else
                "The original article text was not available to verify the exact "
                "observation; this example withdraws the unsupported source."
            ),
        })
    # Original 39688687012's duplicate referred to a single exact URL
    # as a coverage_url and again as evidence[4]. Both requested withdrawal.
    decisions.append({
        "claimed_url": ACLED,
        "action": "withdrawn",
        "replacement_url": None,
        "evidence_replacements": [],
        "reason": (
            "For the separate original evidence source, no passage verifying the "
            "reported incident total was exposed; exclude that evidence entry.")
    })
    return {"resolutions": decisions}


class DuplicateCitationRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="iran-duplicate-citation-")
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.original = research()
        self.citations = set()
        self.search_calls = trace(A)
        self.initial = reconcile_source_citations(
            self.original, self.citations, self.search_calls)
        self.assertEqual(len(self.initial["unsupported_unique_urls"]), 8)
        self.assertEqual(len(self.initial["unsupported"]), 9)

    def test_nine_original_decisions_become_eight_without_losing_reasons(self):
        raw = decision()
        before = copy.deepcopy(raw)
        effective, audit = consolidate_compatible_resolutions(raw)
        self.assertEqual(raw, before)
        self.assertEqual(len(raw["resolutions"]), 9)
        self.assertEqual(len(effective["resolutions"]), 8)
        self.assertEqual(audit["original_decision_count"], 9)
        self.assertEqual(audit["distinct_claimed_url_count"], 8)
        self.assertEqual(audit["original_decision_sha256"], digest(raw))
        self.assertEqual(audit["effective_decision_sha256"], digest(effective))
        self.assertEqual(len(audit["merges"]), 1)
        self.assertEqual(audit["merges"][0]["claimed_url"], ACLED)
        self.assertEqual(audit["merges"][0]["original_entry_indices"], [4, 8])
        self.assertEqual(len(audit["merges"][0]["original_reasons"]), 2)
        self.assertIn("Original decision 1/2:", effective["resolutions"][4]["reason"])
        self.assertIn("Original decision 2/2:", effective["resolutions"][4]["reason"])
        self.assertEqual(audit["publication"], "NOT AUTHORIZED")
        revised, final = apply_resolutions(
            self.original, self.initial, raw, {UKMTO, NATIONAL},
            self.search_calls + trace(UKMTO, NATIONAL))
        self.assertEqual(final["unsupported"], [])
        self.assertEqual(revised["evidence"], [])
        self.assertEqual(revised["coverage_audit"][0]["original_urls"],
                         [UKMTO, NATIONAL])
        self.assertIn("Original decision 1/2", revised["coverage_audit"][0]["limitations"])
        self.assertIn("Original decision 2/2", revised["coverage_audit"][0]["limitations"])
        self.assertEqual(self.original, research())

    def test_conflicting_duplicate_actions_and_urls_fail_closed(self):
        originals = decision()
        for change in (
            {"action": "verified"},
            {"action": "replaced", "replacement_url": B},
            {"replacement_url": B},
        ):
            raw = copy.deepcopy(originals)
            raw["resolutions"][-1].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(
                    ValueError, "Conflicting decisions|Unexpected replacement fields"):
                consolidate_compatible_resolutions(raw)
        for changes in (
            originals["resolutions"][:-2],  # omit one genuinely required URL
            originals["resolutions"] + [{
                "claimed_url": "https://unrelated.example.org/not-requested",
                "action": "withdrawn", "replacement_url": None,
                "evidence_replacements": [],
                "reason": "No provenance for this unrelated original claim."}],
        ):
            with self.subTest(n=len(changes)), self.assertRaises(ValueError):
                apply_resolutions(
                    self.original, self.initial, {"resolutions": changes},
                    {UKMTO, NATIONAL},
                    self.search_calls + trace(UKMTO, NATIONAL))

    def test_replacement_merges_only_identical_or_disjoint_index_edits(self):
        data = {
            "evidence": [
                {"source": BAD, "evidence_status": "new", "observation": "First synthetic claim"},
                {"source": BAD, "evidence_status": "new", "observation": "Second synthetic claim"},
            ],
            "coverage_audit": [{
                "category": "international_media",
                "original_urls": [BAD],
                "outcome": "eligible_reporting_found",
                "limitations": "Two synthetic claims require a checked replacement source."
            }]
        }
        initial = reconcile_source_citations(data, set(), trace(A))
        edits = [
            {"evidence_index": i,
             "replacement": {"source": B, "evidence_status": "new",
                             "observation": f"Qualified synthetic claim {i}"}} for i in range(2)
        ]
        rows = [{
            "claimed_url": BAD, "action": "replaced", "replacement_url": B,
            "reason": "The replacement must be fully rechecked against original source text.",
            "evidence_replacements": [edit],
        } for edit in edits]
        merged, audit = consolidate_compatible_resolutions({"resolutions": rows})
        self.assertEqual(len(merged["resolutions"]), 1)
        self.assertEqual(merged["resolutions"][0]["evidence_replacements"], edits)
        self.assertIsNotNone(audit)
        final, reconciliation = apply_resolutions(
            data, initial, {"resolutions": rows}, {B}, trace(A) + trace(B))
        self.assertEqual(reconciliation["unsupported"], [])
        self.assertEqual([r["source"] for r in final["evidence"]], [B, B])
        same = copy.deepcopy(rows)
        same[1]["evidence_replacements"] = [copy.deepcopy(edits[0])]
        deduped, _ = consolidate_compatible_resolutions({"resolutions": same})
        self.assertEqual(len(deduped["resolutions"][0]["evidence_replacements"]), 1)
        with self.assertRaisesRegex(ValueError, "Every affected"):
            apply_resolutions(
                data, initial, {"resolutions": same}, {B}, trace(A)+trace(B))
        incompatible = copy.deepcopy(same)
        incompatible[1]["evidence_replacements"][0]["replacement"]["observation"] = (
            "Contradictory proposed evidence revision")
        with self.assertRaisesRegex(ValueError, "Conflicting replacement instructions"):
            consolidate_compatible_resolutions({"resolutions": incompatible})

    def _save_failed_archive(self, raw=None, *, error_type="ValueError"):
        from source_research_batches import save_new
        raw = copy.deepcopy(raw if raw is not None else decision())
        save(self.folder, "citation-resolution-initial.json", {
            "status": "FLAGGED_BEFORE_CORRECTIVE_SEARCH",
            "research": self.original,
            "research_sha256": digest(self.original),
            "citations": sorted(self.citations),
            "search_calls": self.search_calls,
            "reconciliation": self.initial})
        corrective_calls = trace(UKMTO, NATIONAL)
        merged_cites = {UKMTO, NATIONAL}
        save(self.folder, "citation-resolution.json", {
            "status": "FAILED_NOT_PUBLISHABLE",
            "attempt_limit": 1,
            "original_research_sha256": digest(self.original),
            "decision": raw,
            "citations": sorted(merged_cites),
            "search_calls": self.search_calls+corrective_calls,
            "error_type": error_type})
        prompt = _correction_prompt(self.original, self.initial, self.search_calls)
        model = "gpt-6.1-sol"
        payload = responses_payload(prompt, True)
        payload["background"] = True
        request_sha = sha(payload)
        response_id = "resp_synthetic_duplicate_verified_71"
        save_new(self.folder / "response-7.json", {
            "search": True,
            "model": model,
            "response_id": response_id,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "result": raw,
            "citations": sorted(merged_cites),
            "tool_search_calls": corrective_calls})
        save_new(self.folder / "api-request-seven.json", {
            "request_sha256": request_sha,
            "response_id": response_id,
            "post_attempts": 1,
            "status": "api_completed_output_not_yet_validated"})
        return prompt

    def _resume(self):
        with patch.dict(os.environ, {"IRAN_FORECAST_MODEL": "gpt-6.1-sol"},
                        clear=False):
            # Real model is supplied only as an identity check for the saved
            # POST journal. It is NEVER CALLED in recovery.
            return resolve_source_citations(
                self.original, self.citations, self.search_calls,
                researcher=LIVE_RESEARCHER, audit_dir=self.folder)

    def test_new_compatible_duplicate_correction_records_complete_audit_and_replays(self):
        from source_research_batches import save_new
        invoked = []
        original_decisions = decision()
        def one_paid_correction(prompt, search):
            self.assertTrue(search)
            invoked.append(prompt)
            output = copy.deepcopy(original_decisions)
            response_id = "resp_new_citation_recovery_81"
            payload = responses_payload(prompt, True)
            payload["background"] = True
            save_new(self.folder / "response-8.json", {
                "search": True, "model": "gpt-6.1-sol",
                "response_id": response_id,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "result": output, "citations": [UKMTO, NATIONAL],
                "tool_search_calls": trace(UKMTO, NATIONAL)})
            save_new(self.folder / "api-request-eight.json", {
                "request_sha256": sha(payload), "response_id": response_id,
                "post_attempts": 1,
                "status": "api_completed_output_not_yet_validated"})
            return output, {UKMTO, NATIONAL}
        with patch.dict(os.environ, {"IRAN_FORECAST_MODEL": "gpt-6.1-sol"},
                        clear=False):
            first = resolve_source_citations(
                self.original, self.citations, self.search_calls,
                researcher=one_paid_correction, audit_dir=self.folder)
        self.assertEqual(len(invoked), 1)
        saved = json.loads((self.folder / "citation-resolution.json").read_text())
        self.assertEqual(saved["status"],
                         "CITATIONS_RESOLVED_PENDING_ALL_OTHER_GATES")
        self.assertEqual(saved["decision"], original_decisions)
        self.assertEqual(saved["decision_normalization"]["original_decision_count"], 9)
        self.assertEqual(saved["decision_normalization"]["distinct_claimed_url_count"], 8)
        self.assertEqual(saved["final_reconciliation"]["unsupported"], [])
        self.assertFalse((self.folder / "citation-resolution-recovery.json").exists())
        preserved = {
            p: p.read_bytes()
            for p in (self.folder/"response-8.json",
                      self.folder/"api-request-eight.json",
                      self.folder/"citation-resolution.json")
        }
        second = self._resume()
        self.assertEqual(first, second)
        self.assertEqual(len(invoked), 1)
        for path, data in preserved.items():
            self.assertEqual(path.read_bytes(), data)

    def test_failed_archived_duplicates_recover_without_a_second_paid_call(self):
        self._save_failed_archive()
        raw_path = self.folder / "response-7.json"
        failed_path = self.folder / "citation-resolution.json"
        initial_path = self.folder / "citation-resolution-initial.json"
        journal_path = self.folder / "api-request-seven.json"
        preserved = {p: p.read_bytes() for p in
                     (raw_path, failed_path, initial_path, journal_path)}
        first = self._resume()
        self.assertEqual(first[1], {UKMTO, NATIONAL})
        self.assertEqual(first[0]["evidence"], [])
        saved = self.folder / "citation-resolution-recovery.json"
        self.assertTrue(saved.exists())
        audit = json.loads(saved.read_text())
        self.assertEqual(audit["status"],
                         "CITATION_RESOLUTIONS_RECOVERED_FROM_VERIFIED_DUPLICATES")
        self.assertEqual(audit["original_failed_checkpoint_sha256"],
                         digest(json.loads(failed_path.read_text())))
        self.assertEqual(audit["normalization"]["original_decision_count"], 9)
        self.assertEqual(audit["normalization"]["distinct_claimed_url_count"], 8)
        self.assertEqual(audit["original_decision_sha256"],
                         digest(json.loads(raw_path.read_text())["result"]))
        self.assertEqual(audit["final_reconciliation"]["unsupported"], [])
        self.assertEqual(audit["publication"], "NOT AUTHORIZED")
        once = saved.read_bytes()
        second = self._resume()
        self.assertEqual(second, first)
        self.assertEqual(saved.read_bytes(), once)
        for p, original_bytes in preserved.items():
            self.assertEqual(p.read_bytes(), original_bytes)

    def test_conflicts_and_other_failed_runs_are_never_recovered(self):
        self._save_failed_archive(error_type="TimeoutError")
        with self.assertRaisesRegex(ValueError, "not an eligible duplicate-URL"):
            self._resume()
        self.assertFalse((self.folder/"citation-resolution-recovery.json").exists())

    def test_saved_response_or_transport_tampering_rejected_no_repeat_post(self):
        self._save_failed_archive()
        response_path = self.folder / "response-7.json"
        original = response_path.read_bytes()
        changed = json.loads(original)
        changed["result"]["resolutions"][-1]["reason"] = (
            "A new unreviewed model claim was inserted after the original paid request.")
        response_path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError, "matching original model/tool output"):
            self._resume()
        self.assertFalse((self.folder/"citation-resolution-recovery.json").exists())
        response_path.write_bytes(original)
        journal = self.folder / "api-request-seven.json"
        original_journal = journal.read_bytes()
        row = json.loads(original_journal)
        row["request_sha256"] = "0"*64
        journal.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, "matching completed API transport journal"):
            self._resume()
        journal.write_bytes(original_journal)

    def test_tampered_recovery_certificate_fails_closed(self):
        self._save_failed_archive()
        self._resume()
        recovery = self.folder / "citation-resolution-recovery.json"
        bad = json.loads(recovery.read_text())
        bad["normalization"]["merges"][0]["original_reasons"][0] = "Forged reason"
        recovery.write_text(json.dumps(bad))
        with self.assertRaisesRegex(ValueError, "Saved citation recovery differs"):
            self._resume()


if __name__ == "__main__":
    unittest.main()
