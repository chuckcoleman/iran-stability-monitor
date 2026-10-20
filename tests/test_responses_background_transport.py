"""No-network tests for fail-closed background Responses and request audits."""
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from responses_transport import request_response


def response(obj):
    return io.BytesIO(json.dumps(obj).encode())


def payload():
    return {"input":"SECRET_REPORT_PROMPT_abc123", "model":"test-model",
            "store":False, "tools":[{"type":"web_search"}],
            "include":["web_search_call.action.sources"]}


def formatter(exc, search):
    return RuntimeError("Redacted OpenAI HTTP " + str(exc.code))


class BackgroundTransportTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="responses-background-audit-")
        self.addCleanup(d.cleanup)
        self.folder=Path(d.name)
        self.requests=[]

    def audit(self):
        files=list(self.folder.glob("api-request-*.json"))
        self.assertEqual(len(files),1)
        row=json.loads(files[0].read_text())
        self.assertNotIn("SECRET_REPORT_PROMPT_abc123",files[0].read_text())
        self.assertNotIn("TOP_SECRET_BEARER",files[0].read_text())
        self.assertEqual(row["post_attempts"],1)
        self.assertEqual(row["store"],False)
        return row

    def execute(self, opener, **options):
        settings={"sleeper":lambda seconds:None,"monotonic":lambda:0}
        settings.update(options)
        return request_response(payload(),search=True,
            token_supplier=lambda:"TOP_SECRET_BEARER",audit_dir=self.folder,
            http_error_formatter=formatter,opener=opener,**settings)

    def test_background_post_once_then_poll_and_preserve_search_sources(self):
        steps=[
          {"id":"resp_live123","status":"queued"},
          {"id":"resp_live123","status":"in_progress"},
          {"id":"resp_live123","status":"completed","output":[
             {"type":"web_search_call","action":{"sources":[{
                "url":"https://news.example.org/article"}]}}]}]
        def opener(req,timeout):
            self.requests.append(req)
            return response(steps.pop(0))
        raw=self.execute(opener)
        self.assertEqual(raw["status"],"completed")
        self.assertEqual([r.get_method() for r in self.requests],
                         ["POST","GET","GET"])
        self.assertEqual(self.audit()["response_id"],"resp_live123")
        self.assertEqual(self.audit()["status"],"api_completed_output_not_yet_validated")
        self.assertEqual(self.audit()["poll_count"],2)
        sent=json.loads(self.requests[0].data)
        self.assertTrue(sent["background"])
        self.assertFalse(sent["store"])
        self.assertEqual(sent["include"],["web_search_call.action.sources"])
        self.assertIn("include%5B%5D=web_search_call.action.sources",
                      self.requests[1].full_url)

    def test_disconnected_create_never_posts_twice_and_writes_preflight_audit(self):
        def fail(req,timeout):
            self.requests.append(req)
            raise http.client.RemoteDisconnected("SECRET_TOKEN_IN_REMOTE_ERROR")
        with self.assertRaisesRegex(RuntimeError,"no automatic POST retry") as ctx:
            self.execute(fail)
        self.assertEqual(len(self.requests),1)
        self.assertNotIn("SECRET_TOKEN_IN_REMOTE_ERROR",str(ctx.exception))
        audit=self.audit()
        self.assertEqual(audit["status"],"create_acknowledgement_unknown_no_replay")
        self.assertIsNone(audit["response_id"])
        self.assertEqual(audit["exception_class"],"RemoteDisconnected")

    def test_poll_network_fault_retries_only_get_after_ack(self):
        count=0
        def opener(req,timeout):
            nonlocal count
            self.requests.append(req)
            count+=1
            if count==1:
                return response({"id":"resp_test123","status":"queued"})
            if count==2:
                raise urllib.error.URLError("PRIVATE_IN_EXCEPTION")
            return response({"id":"resp_test123","status":"completed"})
        result=self.execute(opener)
        self.assertEqual(result["status"],"completed")
        self.assertEqual([r.get_method() for r in self.requests],["POST","GET","GET"])
        self.assertEqual(self.audit()["safe_get_retries"],1)
        self.assertEqual(self.audit()["response_id"],"resp_test123")

    def test_bounded_poll_retry_exhaustion_has_known_id_and_no_new_post(self):
        def opener(req,timeout):
            self.requests.append(req)
            if req.get_method()=="POST":
                return response({"id":"resp_lost123","status":"in_progress"})
            raise ConnectionResetError("PRIVATE_ERROR")
        with self.assertRaisesRegex(RuntimeError,"bounded safe retries"):
            self.execute(opener)
        self.assertEqual([r.get_method() for r in self.requests],
                         ["POST","GET","GET","GET","GET"])
        self.assertEqual(self.audit()["response_id"],"resp_lost123")
        self.assertEqual(self.audit()["status"],"poll_transport_failed_no_post_retry")

    def test_background_time_budget_exhaustion_is_not_approval(self):
        def opener(req,timeout):
            self.requests.append(req)
            return response({"id":"resp_still_running","status":"queued"})
        times=iter([0,1000])
        with self.assertRaisesRegex(RuntimeError,"poll budget"):
            self.execute(opener,monotonic=lambda:next(times),max_poll_seconds=9)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.audit()["status"],"background_timeout_no_replay")
        self.assertEqual(self.audit()["response_id"],"resp_still_running")

    def test_failed_background_status_is_not_approval(self):
        def opener(req,timeout):
            self.requests.append(req)
            return response({"id":"resp_error123","status":"failed"})
        with self.assertRaisesRegex(RuntimeError,"noncompleted status failed"):
            self.execute(opener)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.audit()["status"],"background_terminal_failure")

    def test_http_create_error_redacted_and_not_retried(self):
        def opener(req,timeout):
            self.requests.append(req)
            raise urllib.error.HTTPError("https://api.openai.com/v1/responses",
                400,"SECRET_HEADER",{},io.BytesIO(b'{"secret":"hidden"}'))
        with self.assertRaisesRegex(RuntimeError,"Redacted OpenAI HTTP 400"):
            self.execute(opener)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.audit()["status"],"create_http_error")

    def test_store_true_is_rejected_before_network(self):
        p=payload()
        p["store"]=True
        with self.assertRaisesRegex(ValueError,"store=false"):
            request_response(p,search=True,
                token_supplier=lambda:self.fail("No token call expected"),
                audit_dir=self.folder,http_error_formatter=formatter)
        self.assertEqual(list(self.folder.glob("api-request-*.json")),[])

    def test_nonsearch_remains_foreground_with_redacted_diagnostic(self):
        def opener(req,timeout):
            self.requests.append(req)
            return response({"id":"resp_regular123","status":"completed",
                             "output":[]})
        answer=request_response({"model":"test-model","store":False,
                                 "input":"SECRET_REPORT_PROMPT_abc123"},
            search=False,token_supplier=lambda:"TOP_SECRET_BEARER",
            audit_dir=self.folder,http_error_formatter=formatter,opener=opener)
        self.assertEqual(answer["status"],"completed")
        self.assertNotIn("background",json.loads(self.requests[0].data))
        self.assertEqual(self.audit()["background"],False)


if __name__=="__main__":
    unittest.main()
