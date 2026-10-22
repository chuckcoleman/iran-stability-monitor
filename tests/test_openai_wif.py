"""Offline tests for OpenAI GitHub Actions workload identity federation."""
import base64
import json
import io
import urllib.error
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
import assessment_pipeline as a


class FakeResponse:
    def __init__(self,obj):
        self.payload=json.dumps(obj).encode()
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False
    def read(self,*args):
        return self.payload
    def __iter__(self):
        return iter(self.payload.splitlines(True))


class WIFTests(unittest.TestCase):
    def setUp(self):
        a._OPENAI_WIF_CACHE.update(access_token=None,expires_at=0.0)

    def test_github_oidc_exchanges_and_caches_short_lived_token(self):
        env={
            "OPENAI_IDENTITY_PROVIDER_ID":"idp_test",
            "OPENAI_SERVICE_ACCOUNT_ID":"user-1e07e217b5a13cf3bc804060",
            "OPENAI_WIF_AUDIENCE":"https://api.openai.com/v1",
            "ACTIONS_ID_TOKEN_REQUEST_URL":"https://token.actions.example/oidc?x=1",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN":"github-request-token",
        }
        calls=[]
        def fake_open(req,timeout=0):
            calls.append(req)
            if len(calls)==1:
                self.assertIn("audience=https%3A%2F%2Fapi.openai.com%2Fv1",req.full_url)
                self.assertEqual(req.headers.get("Authorization"),"bearer github-request-token")
                return FakeResponse({"value":"github-oidc-jwt"})
            body=json.loads(req.data.decode())
            self.assertEqual(req.full_url,"https://auth.openai.com/oauth/token")
            self.assertEqual(body["subject_token"],"github-oidc-jwt")
            self.assertEqual(body["identity_provider_id"],"idp_test")
            self.assertEqual(body["service_account_id"],"user-1e07e217b5a13cf3bc804060")
            return FakeResponse({"access_token":"openai-short-lived","expires_in":3600})
        with patch.dict(os.environ,env,clear=True),              patch.object(a.urllib.request,"urlopen",side_effect=fake_open),              patch.object(a.time,"time",return_value=1000):
            self.assertEqual(a.openai_bearer_token(),"openai-short-lived")
            self.assertEqual(a.openai_bearer_token(),"openai-short-lived")
        self.assertEqual(len(calls),2)

    def test_exchange_failure_is_stage_specific_and_redacts_body(self):
        env = {
            "OPENAI_IDENTITY_PROVIDER_ID": "idp_fake",
            "OPENAI_SERVICE_ACCOUNT_ID": "user_fake",
            "OPENAI_WIF_AUDIENCE": "https://api.openai.com/v1",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.actions.example/oidc",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "SECRET_GITHUB_REQUEST_TOKEN",
        }
        denied = urllib.error.HTTPError(
            "https://auth.openai.com/oauth/token", 400, "Bad Request", {},
            io.BytesIO(json.dumps({
                "error": "invalid_subject_token",
                "error_description": "do-not-log-credentials"
            }).encode()))
        with patch.dict(os.environ, env, clear=True), \
             patch.object(a.urllib.request, "urlopen", side_effect=[
                 FakeResponse({"value":"SECRET_SUBJECT_JWT"}), denied]):
            with self.assertRaises(RuntimeError) as result:
                a.openai_bearer_token()
        message = str(result.exception)
        self.assertEqual(message, "OpenAI token exchange HTTP 400 (invalid_subject_token)")
        self.assertNotIn("SECRET_SUBJECT_JWT", message)
        self.assertNotIn("do-not-log-credentials", message)

    def test_oidc_request_failure_is_distinct_from_exchange_failure(self):
        env = {
            "OPENAI_IDENTITY_PROVIDER_ID": "idp_fake",
            "OPENAI_SERVICE_ACCOUNT_ID": "user_fake",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.actions.example/oidc",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "SECRET_GITHUB_REQUEST_TOKEN",
        }
        denied = urllib.error.HTTPError(
            "https://token.actions.example/oidc", 403, "Denied", {},
            io.BytesIO(b'{"error":"forbidden","secret":"never-print"}'))
        with patch.dict(os.environ, env, clear=True), \
             patch.object(a.urllib.request, "urlopen", side_effect=denied):
            with self.assertRaisesRegex(RuntimeError, "GitHub OIDC token request HTTP 403"):
                a.openai_bearer_token()

    def test_oidc_503_is_retried_by_get_before_one_exchange(self):
        env = {
            "OPENAI_IDENTITY_PROVIDER_ID": "idp_fake",
            "OPENAI_SERVICE_ACCOUNT_ID": "user_fake",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.actions.example/oidc",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "SECRET_GITHUB_REQUEST_TOKEN",
        }
        calls, sleeps = [], []
        def fake_open(req, timeout=0):
            calls.append(req)
            if req.get_method() == "GET":
                self.assertEqual(req.headers["Authorization"],
                                 "bearer SECRET_GITHUB_REQUEST_TOKEN")
                if len(calls) <= 2:
                    raise urllib.error.HTTPError(
                        req.full_url, 503, "Service Unavailable", {},
                        io.BytesIO(b"SECRET_ERROR_BODY_MUST_NOT_LEAK"))
                return FakeResponse({"value": "SECRET_OIDC_JWT"})
            self.assertEqual(req.get_method(), "POST")
            self.assertEqual(req.full_url, "https://auth.openai.com/oauth/token")
            return FakeResponse({"access_token": "FINAL_ACCESS_TOKEN",
                                 "expires_in": 3600})
        with patch.dict(os.environ, env, clear=True), \
             patch.object(a.urllib.request, "urlopen", side_effect=fake_open), \
             patch.object(a.time, "sleep", side_effect=sleeps.append), \
             patch.object(a.time, "time", return_value=1000):
            self.assertEqual(a.openai_bearer_token(), "FINAL_ACCESS_TOKEN")
        self.assertEqual([req.get_method() for req in calls],
                         ["GET", "GET", "GET", "POST"])
        self.assertEqual(sleeps, [1, 2])

    def test_oidc_503_exhaustion_fails_closed_without_token_exchange(self):
        env = {
            "OPENAI_IDENTITY_PROVIDER_ID": "idp_fake",
            "OPENAI_SERVICE_ACCOUNT_ID": "user_fake",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.actions.example/oidc",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "SECRET_GITHUB_REQUEST_TOKEN",
        }
        calls, sleeps = [], []
        def fail(req, timeout=0):
            calls.append(req)
            raise urllib.error.HTTPError(req.full_url, 503,
                "Service Unavailable", {}, io.BytesIO(b"SECRET_RESPONSE_BODY"))
        with patch.dict(os.environ, env, clear=True), \
             patch.object(a.urllib.request, "urlopen", side_effect=fail), \
             patch.object(a.time, "sleep", side_effect=sleeps.append):
            with self.assertRaisesRegex(RuntimeError,
                    "GitHub OIDC token request HTTP 503 after bounded GET retries") as ctx:
                a.openai_bearer_token()
        self.assertEqual(len(calls), a._GITHUB_OIDC_MAX_ATTEMPTS)
        self.assertEqual([req.get_method() for req in calls], ["GET"] * 4)
        self.assertEqual(sleeps, [1, 2, 4])
        self.assertNotIn("SECRET_GITHUB_REQUEST_TOKEN", str(ctx.exception))
        self.assertNotIn("SECRET_RESPONSE_BODY", str(ctx.exception))

    def test_oidc_urLError_retries_but_exchange_http_503_not_replayed(self):
        env = {
            "OPENAI_IDENTITY_PROVIDER_ID": "idp_fake",
            "OPENAI_SERVICE_ACCOUNT_ID": "user_fake",
            "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.actions.example/oidc",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "SECRET_GITHUB_REQUEST_TOKEN",
        }
        calls, sleeps = [], []
        def first_network_failure(req, timeout=0):
            calls.append(req)
            if len(calls) == 1:
                raise urllib.error.URLError("SENSITIVE_NETWORK_MESSAGE")
            if req.get_method() == "GET":
                return FakeResponse({"value": "SECRET_OIDC_JWT"})
            raise urllib.error.HTTPError(req.full_url, 503,
                "Service Unavailable", {}, io.BytesIO(b"SECRET_OAUTH_ERROR"))
        with patch.dict(os.environ, env, clear=True), \
             patch.object(a.urllib.request,"urlopen", side_effect=first_network_failure), \
             patch.object(a.time, "sleep", side_effect=sleeps.append):
            with self.assertRaisesRegex(RuntimeError,
                                        "OpenAI token exchange HTTP 503") as ctx:
                a.openai_bearer_token()
        self.assertEqual([req.get_method() for req in calls],
                         ["GET", "GET", "POST"])
        self.assertEqual(sleeps, [1])
        self.assertNotIn("SECRET_OIDC_JWT", str(ctx.exception))
        self.assertNotIn("SECRET_OAUTH_ERROR", str(ctx.exception))

    def test_public_oidc_claims_never_include_signed_jwt_or_unlisted_secrets(self):
        values = {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "https://api.openai.com/v1",
            "sub": "repo:chuckcoleman@25271226/iran-stability-monitor@1373559199:ref:refs/heads/main",
            "repository": "chuckcoleman/iran-stability-monitor",
            "repository_id": "1373559199",
            "repository_owner_id": "25271226",
            "ref": "refs/heads/main",
            "workflow_ref": "chuckcoleman/iran-stability-monitor/.github/workflows/sunday-assessment.yml@refs/heads/main",
            "raw_jwt_claim_that_must_not_appear": "DO_NOT_OUTPUT_PRIVATE_CLAIM",
        }
        payload = base64.urlsafe_b64encode(json.dumps(values).encode()).decode().rstrip("=")
        jwt = "SECRET_HEADER." + payload + ".SECRET_SIGNATURE"
        public = a._public_oidc_claims(jwt)
        self.assertEqual(public["sub"], values["sub"])
        self.assertEqual(public["workflow_ref"], values["workflow_ref"])
        self.assertNotIn("raw_jwt_claim_that_must_not_appear", public)
        self.assertNotIn("DO_NOT_OUTPUT_PRIVATE_CLAIM", json.dumps(public))
        self.assertNotIn("SECRET_HEADER", json.dumps(public))
        self.assertNotIn("SECRET_SIGNATURE", json.dumps(public))

    def test_malformed_oidc_payload_is_not_echoed(self):
        with self.assertRaisesRegex(ValueError, "GitHub OIDC"):
            a._public_oidc_claims("SECRET_HEADER.not_base64~.SECRET_SIGNATURE")

    def test_workflow_uses_complete_admin_verified_service_id(self):
        """Do not let a truncated or stale GitHub repo variable override WIF."""
        workflow=(ROOT / ".github/workflows/sunday-assessment.yml").read_text(encoding="utf-8")
        self.assertIn(
            "OPENAI_SERVICE_ACCOUNT_ID: user-1e07e217b5a13cf3bc804060",
            workflow)
        self.assertNotIn("user-1e07e217b5a1'", workflow)
        self.assertNotIn("vars.OPENAI_SERVICE_ACCOUNT_ID", workflow)
        self.assertIn("OPENAI_IDENTITY_PROVIDER_ID", workflow)

    def test_api_key_fallback_still_works_outside_github(self):
        with patch.dict(os.environ,{"OPENAI_API_KEY":"local-key"},clear=True):
            self.assertEqual(a.openai_bearer_token(),"local-key")

    def test_partial_wif_configuration_fails_closed(self):
        with patch.dict(os.environ,{"OPENAI_IDENTITY_PROVIDER_ID":"idp_only"},clear=True):
            with self.assertRaisesRegex(ValueError,"Incomplete OpenAI WIF"):
                a.openai_bearer_token()


if __name__=="__main__":
    unittest.main()
