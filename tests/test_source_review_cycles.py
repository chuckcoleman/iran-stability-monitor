"""Offline proof that every review version receives both independent roles.

No live research, network calls, forecasts or publishing are made.
"""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from source_research_batches import sha, read_json
from source_review_cycles import (run_alternating_review_cycles,
                                  conservative_revision, deterministic_review_issues)

NOW = dt.datetime(2026, 10, 21, 15, 0, tzinfo=dt.timezone.utc)
ORIGINAL = "2026-10-21T09:28:21-04:00"
REVIEW = "2026-10-21T11:49:00-04:00"


def packet():
    sources = []
    evidence = []
    for i in range(1, 10):
        url = f"https://source.example.org/iran/independent-{i}"
        ident = f"E-20261021-{i:02d}"
        evidence.append({
            "id": ident, "source": url,
            "publisher": f"Independent original publisher {i}",
            "observation": f"Unverified original source assertion number {i}",
            "direction": ("raises", "lowers", "ambiguous")[(i-1) % 3],
            "evidence_status": "new"
        })
        sources.append({
            "url": url, "metadata_status": "verified article metadata",
            "access_status": ("source_unavailable" if i == 1
                              else "source_metadata_captured"),
            "source_retrieval_status": "not independently verified",
            "classification": "attributed_claim",
            "origin": "original_reporting",
            "limitations": "Original reporting has not been independently reproduced.",
            "role": "new_evidence", "new_evidence_indices": [i-1],
            "flags": [], "source_publication_time": None
        })
    return {
        "evidence": evidence,
        "coverage": [{"category": "primary_data",
                      "limitations": "The original research stage is limited in scope."}],
        "source_quality_audit": {
            "status": "SOURCE_BY_SOURCE_REVIEW_REQUIRED",
            "sources": sources, "source_count": len(sources),
            "evidence_source_count": len(sources),
            "context_only_source_count": 0
        },
        "cutoff": REVIEW,
        "published_history_sha256": "f" * 64,
        "mode": "RESEARCH_ONLY_TEST_NO_SCORED_FORECASTS"
    }


class AlternatingCyclesTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="source-review-rounds-")
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)
        self.calls = []
        self.data = packet()

    def review(self, prompt, search):
        self.assertFalse(search)
        role = "affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical"
        from re import search as match
        found = match(r"Identical input SHA-256: ([a-f0-9]{64})", prompt)
        self.assertIsNotNone(found)
        digest = found.group(1)
        self.calls.append((role, digest))
        first = len(self.calls) <= 2
        if first and role == "critical":
            return {"approved": False, "issues": [{
                "type": "unavailable_original",
                "location": "E-20261021-01 / primary_data",
                "reason": "The original claimed direct support without a retrievable source."
            }]}, set()
        return {"approved": True, "issues": []}, set()

    def run_review(self, *, reviewer=None, correction=True):
        return run_alternating_review_cycles(
            folder=self.root, sample=self.data, input_sha=sha(self.data),
            reviewer=reviewer or self.review, now=lambda: NOW,
            original_cutoff=ORIGINAL,
            common="Closed original sources only. Return structured JSON.",
            enable_corrections=correction, max_rounds=4)

    def test_both_roles_alternate_on_each_version_until_both_clean(self):
        initial = copy.deepcopy(self.data)
        result = self.run_review()
        self.assertEqual(result["status"], "RESEARCH_ONLY_REVIEW_CLEAN_NOT_PUBLISHABLE")
        self.assertEqual([role for role, _ in self.calls],
                         ["affirmative", "critical", "affirmative", "critical"])
        self.assertEqual(self.calls[0][1], self.calls[1][1])
        self.assertEqual(self.calls[2][1], self.calls[3][1])
        self.assertNotEqual(self.calls[0][1], self.calls[2][1])
        self.assertTrue((self.root / "source-review-round-01.json").exists())
        self.assertTrue((self.root / "source-review-round-02.json").exists())
        self.assertTrue((self.root / "source-review-round-02-input.json").exists())
        self.assertTrue((self.root / "source-review-round-02-affirmative.json").exists())
        self.assertTrue((self.root / "source-review-round-02-critical.json").exists())
        revised = read_json(self.root / "source-review-round-02-input.json")["sample"]
        self.assertEqual(revised["cutoff"], ORIGINAL)
        self.assertEqual(revised["unsearched_interval"]["status"],
                         "NOT_SEARCHED_OR_CLAIMED_AS_COVERED")
        self.assertNotIn("E-20261021-01", [r["id"] for r in revised["evidence"]])
        self.assertIn("E-20261021-01",
                      [r["id"] for r in revised["excluded_evidence"]])
        self.assertEqual(self.data, initial)
        self.assertEqual(len(revised["source_quality_audit"]["sources"]), 9)
        self.assertEqual(len(revised["evidence"]), 8)
        self.assertFalse(read_json(self.root / "source-review-round-01.json")["both_clean"])
        self.assertTrue(read_json(self.root / "source-review-round-02.json")["both_clean"])
        self.assertEqual(result["publication"], "NOT AUTHORIZED")

    def test_checkpoint_replay_uses_no_extra_model_calls(self):
        original = self.run_review()
        self.calls.clear()
        replay = self.run_review(reviewer=lambda *args:
                                 self.fail("Do not repeat paid reviewer"))
        self.assertEqual(replay, original)
        self.assertEqual(self.calls, [])

    def test_all_approvals_do_not_override_missing_source_or_cutoff(self):
        calls = []
        def too_permissive(prompt, search):
            calls.append(prompt)
            return {"approved": True, "issues": []}, set()
        result = self.run_review(reviewer=too_permissive)
        self.assertEqual(len(calls), 4)
        self.assertFalse(result["review_rounds"][0]["both_clean"])
        self.assertTrue(result["review_rounds"][1]["both_clean"])
        issues = read_json(self.root / "source-review-round-01.json")[
            "deterministic_issues"]
        self.assertTrue(any(x["type"] == "uninspected_original" for x in issues))
        self.assertTrue(any(x["type"] == "cutoff_scope_mismatch" for x in issues))

    def test_unchanged_substantive_objection_stops_without_extra_cycles(self):
        roles = []
        def reject(prompt, search):
            role = "affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical"
            roles.append(role)
            return ({"approved": False, "issues": [{
                "type": "ongoing_disagreement",
                "location": "coverage / publication metadata",
                "reason": "No independently inspected full source is available."
            }]}, set())
        outcome = self.run_review(reviewer=reject)
        self.assertEqual(roles,
                         ["affirmative", "critical", "affirmative", "critical"])
        self.assertEqual(outcome["status"],
                         "RESEARCH_ONLY_REVIEW_ISSUES_NOT_PUBLISHABLE")
        self.assertEqual(outcome["rounds"], 2)
        self.assertTrue((self.root / "source-review-round-02-blocked.json").exists())

    def test_review_packet_tampering_rejected_without_new_calls(self):
        self.run_review()
        file = self.root / "source-review-round-02-input.json"
        row = read_json(file)
        row["sample"]["evidence"][0]["observation"] = "Invented factual support"
        file.write_text(json.dumps(row))
        with self.assertRaisesRegex(ValueError, "differs|invalid parent or hash"):
            self.run_review(reviewer=lambda *args:
                            self.fail("No new model call allowed"))

    def test_not_enough_qualified_evidence_blocks_instead_of_fabricating(self):
        draft = packet()
        for src in draft["source_quality_audit"]["sources"][:6]:
            src["access_status"] = "source_unavailable"
        revision, blocker = conservative_revision(
            draft, [{"type": "unavailable", "location": "sources",
                     "reason": "The documents are not accessible."}], ORIGINAL)
        self.assertIsNone(revision)
        self.assertIn("Not enough independently qualified", blocker["reason"])

    def test_correction_only_excludes_or_downgrades_originals(self):
        original = packet()
        amended, _ = conservative_revision(original, [{
            "type": "unsupported", "location": "E-20261021-01",
            "reason": "Original unavailable"
        }], ORIGINAL)
        self.assertIsNotNone(amended)
        for entry in amended["evidence"]:
            self.assertIn(entry, original["evidence"])
        self.assertTrue(all(
            row["source_publication_time"] is None
            for row in amended["source_quality_audit"]["sources"]))
        again, _ = conservative_revision(amended, [{
            "type": "unsupported", "location": "E-20261021-01",
            "reason": "Still unavailable"
        }], ORIGINAL)
        self.assertIsNone(again)


if __name__ == "__main__":
    unittest.main()
