"""Tests ensuring every substantive report field and item gets BOTH reviews."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from report_section_review import (REPORT_SECTIONS, SOURCE_CLASSES,
                                   report_inventory, validate_report_section_reviews)


class ReportCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = json.loads((ROOT / "data/history.json").read_text(encoding="utf-8"))
        cls.record = data["updates"][-1]

    def test_every_top_level_report_field_is_assigned_once(self):
        inventory = report_inventory(self.record)
        self.assertEqual(set(inventory), set(REPORT_SECTIONS))
        self.assertEqual(len(REPORT_SECTIONS), 15)
        self.assertTrue(all(inventory.values()))
        self.assertEqual(set().union(*(set(v) for v in REPORT_SECTIONS.values())),
                         set(self.record) - {"publication_time"})

    def test_nested_items_get_explicit_coverage(self):
        inv = report_inventory(self.record)
        for key in self.record["warning"]:
            self.assertIn("warning:" + key, inv["nine_warning_indicators"])
        for row in self.record["evidence"]:
            self.assertIn("evidence:" + row["id"], inv["source_search_and_provenance"])
        for row in self.record["forecasts"]:
            self.assertIn("forecasts:" + row["event_id"], inv["four_scored_forecasts"])
        for row in self.record["regional"]:
            self.assertIn("regional:" + row["name"],
                          inv["political_and_regional_scenarios"])
        for key in self.record["metrics"]:
            self.assertIn("metrics:" + key, inv["dashboard_metrics_tables_and_statuses"])
        for cat in SOURCE_CLASSES:
            self.assertIn("research_category:" + cat, inv["source_search_and_provenance"])

    def test_new_report_field_without_review_mapping_blocks(self):
        record = copy.deepcopy(self.record)
        record["new_untested_figure"] = {"score": 99}
        with self.assertRaisesRegex(ValueError, "Unreviewed or missing report fields"):
            report_inventory(record)

    def test_deleted_report_field_without_mapping_update_blocks(self):
        record = copy.deepcopy(self.record)
        record.pop("social_summary")
        with self.assertRaisesRegex(ValueError, "Unreviewed or missing report fields"):
            report_inventory(record)

    def test_duplicate_news_or_evidence_item_does_not_pass(self):
        record = copy.deepcopy(self.record)
        record["evidence"].append(copy.deepcopy(record["evidence"][-1]))
        with self.assertRaisesRegex(ValueError, "Duplicate report review item"):
            report_inventory(record)

    def test_test_note_must_explain_each_perspective(self):
        h = "a" * 64
        expected = report_inventory(self.record)
        reviews = {
          name: {
            "items": items,
            "affirmative": {
              "draft_sha256": h, "approved": True, "issues": [],
              "test_note": "Synthetic supportive review tests underlying source and arithmetic."},
            "critical": {
              "draft_sha256": h, "approved": True, "issues": [],
              "test_note": "Synthetic adversarial review challenges competing explanations."}
          } for name, items in expected.items()
        }
        self.assertTrue(validate_report_section_reviews(reviews,self.record,h,
                                                        role_approvals={"affirmative":True,
                                                                        "critical":True}))
        reviews["narratives_stabilizers_and_thresholds"]["critical"]["test_note"] = ""
        with self.assertRaisesRegex(ValueError,"critical report section test incomplete"):
            validate_report_section_reviews(reviews,self.record,h)

    def test_rejected_section_cannot_be_globally_approved(self):
        h="b"*64
        reviews = {
          name: {"items": items,
                 "affirmative": {"draft_sha256":h,"approved":True,"issues":[],
                                 "test_note":"Positive synthetic review examined every named report item."},
                 "critical": {"draft_sha256":h,"approved":True,"issues":[],
                              "test_note":"Negative synthetic test actively tried to falsify the claim."}}
          for name,items in report_inventory(self.record).items()
        }
        bad=reviews["houthi_support_and_independent_capability"]["critical"]
        bad["approved"]=False
        bad["issues"]=["New evidence does not support Houthi material resupply"]
        with self.assertRaisesRegex(ValueError,"global/section"):
            validate_report_section_reviews(reviews,self.record,h,
                role_approvals={"affirmative":True,"critical":True})
        self.assertTrue(validate_report_section_reviews(reviews,self.record,h,
                role_approvals={"affirmative":True,"critical":False}))


if __name__ == "__main__":
    unittest.main()
