"""V10 publication-bypass regression suite: synthetic only, no network/writes."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from test_chatgpt_handoff import bundle, CUTOFF
import test_alternating_chat_receipt
from chatgpt_handoff import validate_optional_dossier, validate_source_dossier
from publication_safety import require_production_material
from source_capture_witness import (validate_capture_metadata,
                                    verify_capture_bytes,
                                    verify_offline_handoff_captures)
from review_receipt import digest

HTML = ("<html><body><p>The original synthetic measurement "
        "reported a documented independent indicator.</p></body></html>").encode()


class V10HardeningTests(unittest.TestCase):
    def test_verified_local_original_capture(self):
        b, a, dossier = bundle()
        decision = dossier["source_review_packet"]["pre_review_claim_decisions"][0]
        self.assertTrue(verify_capture_bytes(decision, HTML, CUTOFF))
        with tempfile.TemporaryDirectory() as tmp:
            captures = Path(tmp)/"source-captures"
            captures.mkdir()
            (captures/(decision["id"]+".html")).write_bytes(HTML)
            self.assertEqual(verify_offline_handoff_captures(tmp,dossier),1)
            (captures/(decision["id"]+".html")).write_bytes(HTML+b" ")
            with self.assertRaisesRegex(ValueError,"source-body SHA-256"):
                verify_offline_handoff_captures(tmp,dossier)
            (captures/(decision["id"]+".html")).unlink()
            with self.assertRaisesRegex(ValueError,"Missing offline HTML"):
                verify_offline_handoff_captures(tmp,dossier)

    def test_capture_fabrications_and_wrong_original_final_url_fail(self):
        for field, value in (("final_url","https://fake.example.org/reprint"),
                             ("retrieved_at","2026-10-26T09:00:00-04:00"),
                             ("passage_offset",7),
                             ("source_body_sha256","0"*64),
                             ("visible_text_sha256","a"*64)):
            b,a,dossier=bundle()
            decision=dossier["source_review_packet"]["pre_review_claim_decisions"][0]
            cap=decision["capture_verification"]
            cap[field]=value
            decision["capture_verification_sha256"]=digest(cap)
            with self.subTest(field=field),self.assertRaises(ValueError):
                verify_capture_bytes(decision,HTML,CUTOFF)

    def test_missing_capture_proof_is_rejected_even_with_plausible_hash(self):
        b,a,dossier=bundle()
        decision=dossier["source_review_packet"]["pre_review_claim_decisions"][0]
        decision.pop("capture_verification")
        decision["source_body_sha256"]="f"*64
        dossier["source_review_packet"]["evidence"][0]["observation"]=(
            "This is a plausible but unauthenticated assertion")
        with self.assertRaisesRegex(ValueError,"capture verification"):
            validate_source_dossier(dossier,b,a)

    def test_cross_stage_disagreement_allowed_but_same_stage_conflict_rejected(self):
        b,a,dossier=bundle()
        source=dossier["source_review_packet"]["source_quality_audit"]["sources"][0]
        # Search stage reportedly blocked; a later independent metadata GET
        # succeeded. These are not the same operation or an automatic conflict.
        source["access_channels"]["search"]["status"]="blocked_reported"
        cert=dossier["preforecast_certificate"]
        cert["source_packet_sha256"]=digest(dossier["source_review_packet"])
        self.assertEqual(validate_source_dossier(dossier,b,a)["source_count"],6)
        source["access_channels"]["metadata"]["http_status"]=403
        with self.assertRaisesRegex(ValueError,"Same-stage metadata"):
            validate_source_dossier(dossier,b,a)
        source["access_channels"]["metadata"]["http_status"]=200
        source["access_channels"]["same_stage_conflicts"]=["Contradictory HTTP status"]
        with self.assertRaisesRegex(ValueError,"Unresolved contradiction"):
            validate_source_dossier(dossier,b,a)

    def test_sealed_preforecast_source_packet_cannot_be_rewritten(self):
        b,a,dossier=bundle()
        self.assertIsInstance(validate_source_dossier(dossier,b,a),dict)
        dossier["source_review_packet"]["source_quality_audit"]["sources"][1][
            "limitations"] += " Later justification changed after forecast."
        with self.assertRaisesRegex(ValueError,"Preforecast source packet"):
            validate_source_dossier(dossier,b,a)
        b,a,dossier=bundle()
        dossier["critical_source_review"]["source_query_balance_review"][
            "assessment"] += " Extra later review text."
        with self.assertRaisesRegex(ValueError,"Preforecast source packet"):
            validate_source_dossier(dossier,b,a)
        b,a,dossier=bundle()
        receipt={"version":3,"research_mode":"chatgpt_first_no_api",
                 "source_dossier_sha256":digest(dossier),
                 "preforecast_certificate_sha256":"f"*64}
        with self.assertRaisesRegex(ValueError,"sealed preforecast"):
            validate_optional_dossier(b,a,receipt,dossier)

    def test_v3_mode_or_dossier_deletion_does_not_opt_out(self):
        b,a,dossier=bundle()
        receipt={"version":3,"research_mode":"chatgpt_first_no_api",
                 "source_dossier_sha256":digest(dossier),
                 "preforecast_certificate_sha256":digest(dossier["preforecast_certificate"])}
        self.assertEqual(validate_optional_dossier(b,a,receipt,dossier)["api_requests"],0)
        for field in ("research_mode", "source_dossier_sha256",
                      "preforecast_certificate_sha256"):
            modified=dict(receipt)
            modified.pop(field)
            with self.subTest(field=field),self.assertRaises(ValueError):
                validate_optional_dossier(b,a,modified,dossier)
        with self.assertRaises(ValueError):
            validate_optional_dossier(b,a,dict(receipt),None)
        with self.assertRaises(ValueError):
            validate_optional_dossier(b,a,{"version":3},None)

    def test_v3_checked_receipt_rejects_opt_out_before_source_file_lookup(self):
        case=test_alternating_chat_receipt.AlternatingReviewTests("test_one_clean_cycle_accepted")
        case.setUp()
        self.assertTrue(case.check())
        for field in ("research_mode", "source_dossier_sha256",
                      "preforecast_certificate_sha256"):
            original=case.receipt.pop(field)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"V10 source dossier"):
                case.check()
            case.receipt[field]=original

    def test_test_only_bundle_marker_and_fake_urls_are_production_denials(self):
        b,a,dossier=bundle()
        with self.assertRaisesRegex(ValueError,"Synthetic evidence"):
            require_production_material(a["updates"][-1],dossier)
        record=copy.deepcopy(a["updates"][-1])
        for row in record["evidence"]:
            row["observation"]="A documented but otherwise unverified measurement"
        with self.assertRaisesRegex(ValueError,"Reserved synthetic"):
            require_production_material(record,dossier)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/"DO_NOT_PUBLISH.txt").write_text("fixture")
            with self.assertRaisesRegex(ValueError,"Test-only marker"):
                require_production_material({"evidence":[]},folder=folder)
        with self.assertRaisesRegex(ValueError,"Synthetic evidence"):
            require_production_material({"evidence":[{
                "observation":"This synthetic test is not a real observation",
                "publisher":"Source"}]})

    def test_missing_item_review_blocks_full_report(self):
        case=test_alternating_chat_receipt.AlternatingReviewTests("test_one_clean_cycle_accepted")
        case.setUp()
        section=case.receipt["approval"]["rounds"][0]["section_reviews"][
            "source_search_and_provenance"]
        del section["item_reviews"][section["items"][0]]
        with self.assertRaisesRegex(ValueError,"Missing individual item"):
            case.check()
        case.setUp()
        section=case.receipt["approval"]["rounds"][0]["section_reviews"][
            "source_search_and_provenance"]
        name=section["items"][0]
        section["item_reviews"][name]["critical"]["evidence_or_check"]="none"
        with self.assertRaisesRegex(ValueError,"item-level"):
            case.check()


if __name__ == "__main__":
    unittest.main()
