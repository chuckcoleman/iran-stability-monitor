"""Fail-closed structural tests for broad media and think-tank research coverage.

A coverage audit reports attempted categories and cited original URLs;
it never proves that a publisher is reliable or that every outlet was read.
"""
import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))

from assessment_pipeline import (RESEARCH, SOURCE_SCAN_GROUPS,
                                 validate_source_coverage_audit)

CITED="https://www.iiss.org/regions/middle-east-and-north-africa/iran/"


def coverage():
    items=[]
    for category in SOURCE_SCAN_GROUPS:
        items.append({
            "category":category,
            "queries":["Iran latest and prior-Sunday developments; original reporting"],
            "outcome":"searched_no_eligible_evidence",
            "original_urls":[],
            "limitations":"Only this bounded search was represented in the test, not universal coverage."
        })
    item=next(x for x in items if x["category"]=="think_tanks")
    item["outcome"]="eligible_reporting_found"
    item["original_urls"]=[CITED]
    return items


class BroadenedSourcesTests(unittest.TestCase):
    def test_all_six_categories_structurally_covered(self):
        self.assertEqual(len(SOURCE_SCAN_GROUPS),6)
        result=validate_source_coverage_audit(coverage(),{CITED})
        self.assertEqual({x["category"] for x in result},set(SOURCE_SCAN_GROUPS))

    def test_missing_group_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"Missing or incomplete"):
            validate_source_coverage_audit(coverage()[:-1],{CITED})

    def test_duplicate_group_fails(self):
        rows=coverage()
        rows[-1]["category"]=rows[0]["category"]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            validate_source_coverage_audit(rows,{CITED})

    def test_non_cited_original_url_fails(self):
        with self.assertRaisesRegex(ValueError,"web-cited"):
            validate_source_coverage_audit(coverage(),{"https://example.org/story"})

    def test_eligible_without_link_fails(self):
        rows=coverage()
        row=next(x for x in rows if x["category"]=="think_tanks")
        row["original_urls"]=[]
        with self.assertRaisesRegex(ValueError,"needs original cited"):
            validate_source_coverage_audit(rows,{CITED})

    def test_no_fake_queries(self):
        rows=coverage()
        rows[0]["queries"]=[]
        with self.assertRaisesRegex(ValueError,"attempted searches"):
            validate_source_coverage_audit(rows,{CITED})

    def test_unknown_scan_status_fails(self):
        rows=coverage()
        rows[0]["outcome"]="fully_exhaustive_all_outlets_scanned"
        with self.assertRaisesRegex(ValueError,"eligible/none/incomplete"):
            validate_source_coverage_audit(rows,{CITED})

    def test_incomplete_category_is_a_disclosed_outcome(self):
        rows=coverage()
        rows[0]["outcome"]="inaccessible_or_incomplete"
        rows[0]["limitations"]="The outlet was blocked and retrieval did not succeed."
        self.assertEqual(validate_source_coverage_audit(rows,{CITED})[0]["outcome"],
                         "inaccessible_or_incomplete")

    def test_commentary_is_not_primary_evidence(self):
        self.assertIn("may provide analysis, hypotheses or scenario estimates",RESEARCH)
        self.assertIn("do not misclassify",RESEARCH)
        self.assertIn("not a\nrequired citation",RESEARCH)

    def test_dynamic_broad_discovery(self):
        for term in ("BROAD, ADAPTIVE","six research classes separately",
                     "IISS, Chatham House","economic_humanitarian_academic",
                     "CONTROVERTING evidence","No forecasts in this first stage"):
            self.assertIn(term,RESEARCH)
        formatted=RESEARCH.format(date="2026-10-25",prior="[]")
        self.assertIn("2026-10-25",formatted)
        self.assertIn("Prior evidence for persistent carried-forward IDs: [].",formatted)

    def test_watchlist_categories_and_source_qualification(self):
        document=(ROOT/"SOURCE_WATCHLIST.md").read_text(encoding="utf-8")
        for term in ("International Crisis Group","Financial Times",
                     "Chatham House","IISS","RUSI","Iran International",
                     "Bellingcat","AFP","BBC Persian",
                     "Adaptive topical discovery",
                     "before the evidence cutoff",
                     "not a fixed whitelist"):
            if term=="not a fixed whitelist":
                self.assertIn("not a fixed whitelist",document)
            else:
                self.assertIn(term,document)
        self.assertIn("Do not rewrite earlier forecasts",document)

if __name__=="__main__":
    unittest.main()
