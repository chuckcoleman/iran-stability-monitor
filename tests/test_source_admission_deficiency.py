"""V6 deficit diagnostics: explain, never waive, the closed-source gate."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from read_only_research_dry_run import admission_deficiency_report
from source_research_batches import sha


class AdmissionDeficiencyTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"version": 6, "snapshot_sha256": "a" * 64}
        self.preflight = {
            "status": "PRE_REVIEW_ADMISSIBILITY_BLOCKED_NO_PAID_REVIEWS",
            "per_claim": [
                {"id": "E-20261022-01", "decision": "HELD_OUT_BEFORE_PAID_REVIEW",
                 "reasons": ["NO_ORIGINAL_PUBLISHER_DATE",
                             "NO_ORIGINAL_PUBLISHER_DATE",
                             "NO_EXACT_RETRIEVED_ORIGINAL_BODY_PASSAGE"]},
                {"id": "E-20261022-02", "decision":
                 "PROVISIONAL_ORIGINAL_OBSERVATION_REQUIRES_DUAL_REVIEW",
                 "reasons": []},
            ],
            "admitted_original_ids": ["E-20261022-02"],
            "held_original_ids": ["E-20261022-01"],
            "directional_candidate_counts": {
                "directional_observations": 1,
                "new_directional_observations": 1,
                "distinct_directional_publishers": 1,
                "failures": ["fewer_than_six_source_observations",
                             "fewer_than_three_distinct_publishers",
                             "fewer_than_four_new_observations"],
            },
        }

    def test_deficit_projection_preserves_original_gate_and_exact_hash(self):
        original = copy.deepcopy(self.preflight)
        report = admission_deficiency_report(self.preflight, self.snapshot)
        self.assertEqual(self.preflight, original)
        self.assertEqual(report["source_pre_review_sha256"], sha(original))
        self.assertEqual(report["source_snapshot_sha256"], "a" * 64)
        self.assertEqual(report["total_original_candidates"], 2)
        self.assertEqual(report["admitted_original_count"], 1)
        self.assertEqual(report["held_original_count"], 1)
        self.assertEqual(report["rejection_reasons_counted_by_claim"], {
            "NO_EXACT_RETRIEVED_ORIGINAL_BODY_PASSAGE": 1,
            "NO_ORIGINAL_PUBLISHER_DATE": 1})
        self.assertEqual(report["unmet_original_eligibility_requirements"],
                         original["directional_candidate_counts"]["failures"])
        self.assertEqual(report["next_action"], "NEW_DATED_SOURCE_RESEARCH_SNAPSHOT_ONLY")
        self.assertEqual(report["publication"], "NOT AUTHORIZED")
        self.assertEqual(report, admission_deficiency_report(
            self.preflight, self.snapshot))

    def test_clean_gate_and_old_snapshot_cannot_receive_deficit_report(self):
        for altered, snapshot in [
            (dict(self.preflight, status="PRE_REVIEW_DIRECTIONAL_CANDIDATES_READY"),
             self.snapshot),
            (self.preflight, dict(self.snapshot, version=5)),
            (dict(self.preflight, per_claim=[{"id": "E-1", "reasons": ["bad"]},
                                              {"id": "E-1", "reasons": ["bad"]}]),
             self.snapshot),
            (dict(self.preflight, held_original_ids=[]), self.snapshot),
        ]:
            with self.subTest(status=altered.get("status"),
                              version=snapshot["version"]):
                with self.assertRaises(ValueError):
                    admission_deficiency_report(altered, snapshot)


if __name__ == "__main__":
    unittest.main()
