"""Regression tests of paid, nonpublishing Responses probe and redacted API errors."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
import assessment_pipeline as a
import sunday_automation as sunday


def rejected(message, param="tools[0].type", code="invalid_request_error"):
    payload={"error":{
        "type":"invalid_request_error",
        "code":code,
        "param":param,
        "message":message
    }}
    return urllib.error.HTTPError(
        "https://api.openai.com/v1/responses",400,"Bad Request",
        {"x-request-id":"req_12345abc"},
        io.BytesIO(json.dumps(payload).encode()))


class ResponsesContractTests(unittest.TestCase):
    def test_error_is_safe_and_identifies_parameter_and_phase(self):
        err=rejected(
            "web_search tool_choice JSON format failed. SECRET_OPENAI_KEY_12345 "
            "https://unsafe.example/?apikey=SECRET_BODY_TOKEN",
            "tools[0].type"
        )
        report=str(a._safe_responses_error(err,True))
        self.assertIn("OpenAI Responses web-search research HTTP 400",report)
        self.assertIn('"param": "tools[0].type"',report)
        self.assertIn('"code": "invalid_request_error"',report)
        self.assertIn('"type": "invalid_request_error"',report)
        self.assertIn('"request_id": "req_12345abc"',report)
        self.assertIn("web_search",report)
        self.assertIn("json_format",report)
        self.assertNotIn("SECRET_OPENAI_KEY_12345",report)
        self.assertNotIn("SECRET_BODY_TOKEN",report)
        self.assertNotIn("unsafe.example",report)

    def test_nonsearch_error_rejects_arbitrary_freeform_fields(self):
        err=rejected("PRIVATE_API_TOKEN_IN_MESSAGE",
                     "inject\"} PRIVATE_TOKEN {", "bad:code")
        report=str(a._safe_responses_error(err,False))
        self.assertIn("non-search assessment/review HTTP 400",report)
        self.assertNotIn("PRIVATE_API_TOKEN_IN_MESSAGE",report)
        self.assertNotIn("PRIVATE_TOKEN",report)
        self.assertNotIn("bad:code",report)
        self.assertNotIn('"param"',report)

    def test_search_request_retains_paid_web_and_json_constraints(self):
        requests=[]
        def deny(req,timeout=0):
            requests.append(json.loads(req.data.decode("utf-8")))
            raise rejected("Unsupported tool mode: web_search json format",
                           "text.format.type")
        with patch.object(a,"openai_bearer_token",return_value="SECRET_BEARER"), \
             patch.object(a.urllib.request,"urlopen",side_effect=deny):
            with self.assertRaisesRegex(RuntimeError,"Responses web-search research HTTP 400") as caught:
                a.llm("Search live web. Return JSON object.",True)
        p=requests[0]
        self.assertEqual(p["model"],"gpt-6.1-sol")
        self.assertEqual(p["tools"],[{"type":"web_search","external_web_access":True}])
        self.assertEqual(p["tool_choice"],"required")
        self.assertEqual(p["include"],["web_search_call.action.sources"])
        self.assertFalse(p["store"])
        self.assertEqual(p["text"]["format"],{"type":"json_object"})
        self.assertNotIn("SECRET_BEARER",str(caught.exception))
        self.assertIn("text.format.type",str(caught.exception))

    def test_api_probe_never_writes_history_or_touches_github_or_metricool(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"data").mkdir()
            original=b'{"updates":[{"date":"2026-10-11"}]}'
            (root/"data/history.json").write_bytes(original)
            calls=[]
            def fake_llm(prompt,search):
                calls.append((prompt,search))
                return (({"title":"Example","url":"https://news.example.org/iran"},
                         {"https://news.example.org/iran"}) if search else
                        ({"probe":True},set()))
            with patch.object(sunday,"ROOT",root), \
                 patch.object(sunday,"ready",return_value=True), \
                 patch.object(a,"llm",side_effect=fake_llm), \
                 patch.object(sunday,"gh") as github, \
                 patch.object(sunday,"run") as commands:
                sunday.api_probe()
                github.assert_not_called()
                commands.assert_not_called()
            self.assertEqual([s for _,s in calls],[True,False])
            self.assertEqual((root/"data/history.json").read_bytes(),original)

    def test_api_probe_is_separate_from_live_publication_steps(self):
        workflow=(ROOT/".github/workflows/sunday-assessment.yml").read_text()
        self.assertIn("          - api-probe",workflow)
        self.assertIn("inputs.mode == 'api-probe'",workflow)
        self.assertIn("python scripts/sunday_automation.py api-probe",workflow)
        self.assertIn("inputs.mode == 'dry-run'",workflow)
        self.assertNotIn("inputs.mode == 'api-probe' || steps.eligibility.outputs.eligible",workflow)


if __name__=="__main__":
    unittest.main()
