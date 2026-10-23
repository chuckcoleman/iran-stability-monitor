"""Fail-closed coverage of EVERY selected media, specialist and think-tank URL.

All examples are synthetic. Matching URLs, the model's source classification,
and a source-site timestamp do NOT certify the claims as independently true.
"""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
from source_quality_audit import (
    source_inventory, source_quality_audit, save_quality_audit,
    validate_source_review)
from assessment_pipeline import SOURCE_SCAN_GROUPS


URL1="https://www.reuters.com/world/iran-one"
URL2="https://www.iranintl.com/en/202610200001"
URL3="https://www.chathamhouse.org/iran/analysis"


def research():
    rows=[{"category":k,"original_urls":[],"queries":["Synthetic source test"],
           "outcome":"searched_no_eligible_evidence",
           "limitations":"This record is artificial and not verified."}
          for k in SOURCE_SCAN_GROUPS]
    rows[0]["original_urls"]=[URL1]
    rows[2]["original_urls"]=[URL2]
    rows[4]["original_urls"]=[URL3]
    evidence=[
        {"source":URL1,"evidence_status":"new","direction":"ambiguous"},
        {"source":URL2,"evidence_status":"new","direction":"raises"},
        {"source":"https://old.example.org/archived",
         "evidence_status":"carried_forward","id":"E-ARCHIVE-01"}]
    qualities=[
        {"url":URL1,"kind":"attributed_claim","origin":"original_reporting",
         "corroborating_urls":[],
         "assessment":"Reuters reported an attributed source assertion without direct independent verification.",
         "limitations":"No outside corroboration was independently established by these synthetic tests."},
        {"url":URL2,"kind":"unverified","origin":"unknown",
         "corroborating_urls":[],
         "assessment":"The outlet alleged a worsening condition but its testimony remains inaccessible.",
         "limitations":"Original release clock and testimony independence remain unknown to this audit."},
        {"url":URL3,"kind":"analysis","origin":"analytical_secondary",
         "corroborating_urls":[],
         "assessment":"The research institute discussed a scenario, not a new observed event.",
         "limitations":"Its forecast is an opinion with institutional perspective, not a measured incident."}
    ]
    return {"coverage_audit":rows,"evidence":evidence,"source_quality":qualities}


def metadata():
    return {
        URL1:{"source_publication_time":"2026-10-20T17:05:00+00:00",
              "retrieval_status":"retrieved","metadata_status":"verified article metadata",
              "publication_dates":["2026-10-20"]},
        URL2:{"retrieval_status":"unavailable; web-search citation only",
              "metadata_status":"unknown first publication time"},
        URL3:{"retrieval_status":"retrieved","source_publication_time":None}
    }


class QualityAuditTests(unittest.TestCase):
    def test_covers_context_articles_including_thinktanks_and_every_new_evidence(self):
        result=source_quality_audit(research(),metadata(),strict=True)
        self.assertEqual(result["source_count"],3)
        self.assertEqual(result["evidence_source_count"],2)
        self.assertEqual(result["context_only_source_count"],1)
        self.assertEqual(result["unverified_clock_count"],2)
        by={x["url"]:x for x in result["sources"]}
        self.assertEqual(by[URL3]["classification"],"analysis")
        self.assertEqual(by[URL3]["role"],"coverage_context_only")
        self.assertEqual(by[URL1]["first_publication_clock_status"],
                         "publisher_supplied_metadata_not_independently_confirmed")
        self.assertEqual(by[URL2]["access_status"],"source_unavailable")
        self.assertIn("no_independent_corroboration_identified",by[URL2]["flags"])
        self.assertIn("directional_claim_needs_explicit_review",by[URL2]["flags"])
        self.assertEqual(by[URL2]["factual_verification"],"not_automatically_established")
        self.assertEqual(len(source_inventory(research())),3)

    def test_repeated_or_missing_source_quality_is_fail_closed(self):
        obj=research()
        obj["source_quality"].pop()
        with self.assertRaisesRegex(ValueError,"omits source URLs"):
            source_quality_audit(obj,metadata())
        obj=research()
        obj["source_quality"][-1]["url"]=URL1
        with self.assertRaisesRegex(ValueError,"repeated source quality URL"):
            source_quality_audit(obj,metadata())
        obj=research()
        obj["source_quality"][-1]["url"]="https://uncited.example.org/source"
        with self.assertRaisesRegex(ValueError,"unknown or repeated"):
            source_quality_audit(obj,metadata())

    def test_corrob_urls_must_be_other_cited_urls_not_outside_or_same(self):
        for cited in [URL1,"https://unknown.example.org/story"]:
            with self.subTest(cited=cited):
                obj=research()
                obj["source_quality"][0]["corroborating_urls"]=[cited]
                with self.assertRaisesRegex(ValueError,"distinct cited source"):
                    source_quality_audit(obj,metadata())

    def test_malformed_classes_are_rejected(self):
        for key,value in [("kind","verified_as_factual_truth"),("origin","independently_proven"),
                          ("assessment","too short"),("limitations","")]:
            with self.subTest(key=key):
                obj=research();obj["source_quality"][0][key]=value
                with self.assertRaises(ValueError):
                    source_quality_audit(obj,metadata())

    def test_no_future_source_publication_timestamp_is_admitted(self):
        with self.assertRaisesRegex(ValueError,"after research cutoff"):
            source_quality_audit(research(),metadata(),strict=True,
               cutoff=dt.datetime(2026,10,20,16,0,tzinfo=dt.timezone.utc))

    def test_synthetic_missing_annotations_are_marked_unverified(self):
        obj=research()
        del obj["source_quality"]
        with self.assertRaisesRegex(ValueError,"Missing required"):
            source_quality_audit(obj,metadata(),strict=True)
        test=source_quality_audit(obj,metadata(),strict=False)
        self.assertEqual(len(test["sources"]),3)
        self.assertTrue(all(x["classification"]=="unverified" for x in test["sources"]))

    def test_persisted_audit_is_complete_and_not_rewritten(self):
        result=source_quality_audit(research(),metadata())
        with tempfile.TemporaryDirectory() as folder:
            path=save_quality_audit(folder,result)
            self.assertEqual(json.loads(path.read_text()),result)
            with self.assertRaises(FileExistsError):
                save_quality_audit(folder,result)

    def test_each_perspective_must_review_every_original_url(self):
        quality=source_quality_audit(research(),metadata())
        reviews=[{"url":row["url"],
                  "assessment":"This specific original link was assessed with its stated uncertainties.",
                  "disposition":"supported_as_qualified" if row["role"]=="new_evidence"
                               else "background_only"}
                 for row in quality["sources"]]
        self.assertTrue(validate_source_review(
            {"approved":True,"issues":[],"source_reviews":reviews},quality,"affirmative"))
        for invalid in [reviews[1:],reviews+[reviews[0]],list(reversed(reviews[:-1]))]:
            with self.assertRaises(ValueError):
                validate_source_review({"approved":True,"source_reviews":invalid},
                                       quality,"critical")

    def test_tracking_only_aliases_are_transparent_redundancies_not_new_sources(self):
        quality = source_quality_audit(research(), metadata())
        rows = [{
            "url": source["url"],
            "assessment": ("The original article was individually assessed; "
                           "its publisher-supplied details do not establish truth."),
            "disposition": "supported_as_qualified",
        } for source in quality["sources"]]
        aliases = [
            {"url": URL1 + "?utm_source=chatgpt.com",
             "assessment": ("This is only the tracking-parameter rendition "
                            "of the original source, not another observation."),
             "disposition": "supported_as_qualified"},
            {"url": URL2 + "?utm_medium=referral&utm_source=chatgpt.com",
             "assessment": ("This tracked URL refers to the same actual "
                            "original article, not to an independent source."),
             "disposition": "supported_as_qualified"},
        ]
        reviewed = {"approved": True, "issues": [],
                    "source_reviews": rows + aliases}
        before = copy.deepcopy(reviewed)
        ledger = validate_source_review(
            reviewed, quality, "affirmative", return_aliases=True)
        self.assertEqual(len(ledger), 2)
        self.assertEqual([entry["canonical_url"] for entry in ledger],
                         [URL1, URL2])
        self.assertEqual(
            {entry["origin"] for entry in ledger},
            {"TRACKING_ONLY_REDUNDANT_NOT_INDEPENDENT_SOURCE"})
        self.assertTrue(validate_source_review(reviewed, quality, "affirmative"))
        self.assertEqual(reviewed, before)

        for kind in ("missing_canonical", "wrong_disposition", "unknown_path",
                     "nontracking_query", "url_fragment", "duplicate_alias",
                     "duplicate_canonical", "fake_new_source", "too_many"):
            bad = copy.deepcopy(reviewed)
            if kind == "missing_canonical":
                bad["source_reviews"] = bad["source_reviews"][1:]
            elif kind == "wrong_disposition":
                bad["source_reviews"][-1]["disposition"] = "background_only"
            elif kind == "unknown_path":
                bad["source_reviews"][-1]["url"] = (
                    URL2.replace("202610200001", "different") + "?utm_source=x")
            elif kind == "nontracking_query":
                bad["source_reviews"][-1]["url"] = URL2 + "?article=another"
            elif kind == "url_fragment":
                bad["source_reviews"][-1]["url"] = (
                    URL2 + "?utm_source=chatgpt.com#unverified")
            elif kind == "duplicate_alias":
                bad["source_reviews"].append(copy.deepcopy(aliases[0]))
            elif kind == "duplicate_canonical":
                bad["source_reviews"].append(copy.deepcopy(rows[0]))
            elif kind == "fake_new_source":
                bad["source_reviews"][-1]["url"] = (
                    "https://invented.example.org/uncited")
            elif kind == "too_many":
                bad["source_reviews"].extend(copy.deepcopy(aliases[0])
                    for _ in range(17))
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    validate_source_review(bad, quality, "critical")
        # A tracking alias cannot make a rejected source look approved.
        rejected = copy.deepcopy(reviewed)
        rejected["source_reviews"][-1]["disposition"] = "unverified_reject"
        with self.assertRaises(ValueError):
            validate_source_review(rejected, quality, "affirmative")

    def test_only_explicit_rejected_v7_conflict_can_be_preserved_not_approved(self):
        quality = source_quality_audit(research(), metadata())
        rows = [{
            "url": source["url"],
            "assessment": ("The canonical original article was individually "
                           "assessed while retaining its limits and provenance."),
            "disposition": "supported_as_qualified",
        } for source in quality["sources"]]
        variant = {
            "url": URL2 + "?utm_source=chatgpt.com",
            "assessment": ("The tracked article variant lacks separately "
                           "demonstrated original body and source provenance."),
            "disposition": "unverified_reject",
        }
        rejected = {"approved": False, "issues": [{
            "type": "disputed_source_provenance",
            "location": URL2,
            "reason": "Article variant was not separately verified."}],
                    "source_reviews": rows + [variant]}
        before = copy.deepcopy(rejected)
        with self.assertRaisesRegex(ValueError,
                                    "tracking alias contradicts canonical"):
            validate_source_review(rejected, quality, "critical",
                                   return_aliases=True)
        with self.assertRaisesRegex(ValueError,
                                    "require an explicit returned audit"):
            validate_source_review(rejected, quality, "critical",
                                   record_rejected_conflicts=True)
        aliases = validate_source_review(
            rejected, quality, "critical", return_aliases=True,
            record_rejected_conflicts=True)
        self.assertEqual(len(aliases), 1)
        self.assertEqual(aliases[0]["canonical_url"], URL2)
        self.assertEqual(aliases[0]["canonical_disposition"],
                         "supported_as_qualified")
        self.assertEqual(aliases[0]["disposition"], "unverified_reject")
        self.assertEqual(
            aliases[0]["conflict_status"],
            "UNRESOLVED_REJECTED_REVIEW_SOURCE_DISPOSITION_CONFLICT")
        self.assertEqual(before, rejected)

        approved = copy.deepcopy(rejected)
        approved["approved"] = True
        with self.assertRaises(ValueError):
            validate_source_review(
                approved, quality, "critical", return_aliases=True,
                record_rejected_conflicts=True)
        no_issues = copy.deepcopy(rejected)
        no_issues["issues"] = []
        with self.assertRaises(ValueError):
            validate_source_review(
                no_issues, quality, "critical", return_aliases=True,
                record_rejected_conflicts=True)
        missing = copy.deepcopy(rejected)
        missing["source_reviews"].pop(1)
        with self.assertRaises(ValueError):
            validate_source_review(
                missing, quality, "critical", return_aliases=True,
                record_rejected_conflicts=True)
        changed_path = copy.deepcopy(rejected)
        changed_path["source_reviews"][-1]["url"] = (
            URL2 + "/new-article?utm_source=chatgpt.com")
        with self.assertRaises(ValueError):
            validate_source_review(
                changed_path, quality, "critical", return_aliases=True,
                record_rejected_conflicts=True)

    def test_tracker_aliases_preserve_original_content_selecting_query(self):
        quality = {"sources": [{"url":
            "https://www.intellinews.com/iran-report/?source=iran"}]}
        original = quality["sources"][0]["url"]
        text = ("Review of the original publisher URL and the limits "
                "of the source's publication-time provenance.")
        reviews = [{
            "url": original, "assessment": text,
            "disposition": "background_only"
        }, {
            "url": original + "&utm_source=chatgpt.com",
            "assessment": text,
            "disposition": "background_only"
        }]
        verdict = {"approved": True, "source_reviews": reviews}
        self.assertEqual(
            len(validate_source_review(verdict, quality, "affirmative",
                                       return_aliases=True)), 1)
        wrong = copy.deepcopy(verdict)
        wrong["source_reviews"][-1]["url"] = (
            "https://www.intellinews.com/iran-report/"
            "?source=other&utm_source=chatgpt.com")
        with self.assertRaises(ValueError):
            validate_source_review(wrong, quality, "critical")

    def test_critical_unverified_rejection_disallows_global_pass(self):
        quality=source_quality_audit(research(),metadata())
        reviews=[{"url":row["url"],
                  "assessment":"This linked assertion lacks enough corroboration to treat as established.",
                  "disposition":"unverified_reject" if row["role"]=="new_evidence"
                                else "background_only"}
                 for row in quality["sources"]]
        with self.assertRaisesRegex(ValueError,"cannot approve"):
            validate_source_review({"approved":True,"source_reviews":reviews},quality,"critical")
        self.assertTrue(validate_source_review(
            {"approved":False,"source_reviews":reviews},quality,"critical"))


if __name__=="__main__":
    unittest.main()
