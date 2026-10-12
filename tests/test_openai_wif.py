"""Offline tests for OpenAI GitHub Actions workload identity federation."""
import json
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
            "OPENAI_SERVICE_ACCOUNT_ID":"svc_test",
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
            self.assertEqual(body["service_account_id"],"svc_test")
            return FakeResponse({"access_token":"openai-short-lived","expires_in":3600})
        with patch.dict(os.environ,env,clear=True),              patch.object(a.urllib.request,"urlopen",side_effect=fake_open),              patch.object(a.time,"time",return_value=1000):
            self.assertEqual(a.openai_bearer_token(),"openai-short-lived")
            self.assertEqual(a.openai_bearer_token(),"openai-short-lived")
        self.assertEqual(len(calls),2)

    def test_api_key_fallback_still_works_outside_github(self):
        with patch.dict(os.environ,{"OPENAI_API_KEY":"local-key"},clear=True):
            self.assertEqual(a.openai_bearer_token(),"local-key")

    def test_partial_wif_configuration_fails_closed(self):
        with patch.dict(os.environ,{"OPENAI_IDENTITY_PROVIDER_ID":"idp_only"},clear=True):
            with self.assertRaisesRegex(ValueError,"Incomplete OpenAI WIF"):
                a.openai_bearer_token()


if __name__=="__main__":
    unittest.main()
