"""Offline fail-closed tests for canonical verification on every deployment."""
import base64
import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, call

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import verify_publication as v

SHA = "a" * 40


class CanonicalContentTests(unittest.TestCase):
    def test_exact_public_bytes(self):
        source = b'{"a":1}\n'
        with patch.object(v, "request_bytes", return_value=source) as reader:
            value = v.verify_public(source, tries=1)
            self.assertEqual(value, hashlib.sha256(source).hexdigest())
            self.assertTrue(reader.call_args.args[0].startswith(v.SITE + "?verify="))

    def test_json_equivalence_is_not_byte_equivalence(self):
        with patch.object(v, "request_bytes", return_value=b'{"a": 1}\n'):
            with self.assertRaisesRegex(RuntimeError, "Canonical public bytes differ"):
                v.verify_public(b'{"a":1}\n', tries=1)

    def test_protocol_bytes_also_required(self):
        expected = b'<!doctype html><title>Protocol v1</title>'
        with patch.object(v, "request_bytes", return_value=expected) as reader:
            v.verify_public(expected, url=v.PROTOCOL_SITE, tries=1)
            self.assertTrue(reader.call_args.args[0].startswith(v.PROTOCOL_SITE + "?verify="))
        with patch.object(v, "request_bytes", return_value=b"<html>different</html>"):
            with self.assertRaisesRegex(RuntimeError, "Canonical public bytes differ"):
                v.verify_public(expected, url=v.PROTOCOL_SITE, tries=1)

    def test_unavailable_domain_is_failure_not_skip(self):
        with patch.object(v, "request_bytes", side_effect=OSError("DNS failure")):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                v.verify_public(b"{}", tries=2, sleeper=lambda seconds: None)

    def test_refuses_other_verification_hosts(self):
        with self.assertRaisesRegex(RuntimeError, "Unapproved"):
            v.verify_public(b"{}", tries=1, url="https://untrusted.test/")

    def _code_only(self, *, fail_protocol=False, fail_run=False, changed_main=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data = root / "data"
            data.mkdir()
            history = {"schema_version": 3, "updates": [{"date": "2026-10-11"}]}
            history_raw = (json.dumps(history) + "\n").encode()
            proto = b"<!doctype html><title>Frozen v1</title>\n"
            (data / "history.json").write_bytes(history_raw)
            (root / "protocol-v1.html").write_bytes(proto)

            def git(*args):
                if args == ("rev-parse", "HEAD"):
                    return SHA
                if args == ("show", "HEAD^:data/history.json"):
                    return json.dumps(history)
                raise AssertionError(args)

            def github(path, method="GET", data=None):
                if path == "contents/data/history.json?ref=main":
                    return {"encoding": "base64", "content": base64.b64encode(
                        history_raw + (b" " if changed_main else b"")).decode()}
                if path == "contents/protocol-v1.html?ref=main":
                    return {"encoding": "base64", "content": base64.b64encode(proto).decode()}
                raise AssertionError("Unexpected external lookup: " + path)

            def public(raw, *, url):
                if fail_protocol and url == v.PROTOCOL_SITE:
                    raise RuntimeError("Public protocol unavailable")
                return hashlib.sha256(raw).hexdigest()

            with (patch.object(v, "ROOT", root),
                  patch.object(v, "git", side_effect=git),
                  patch.object(v, "github", side_effect=github),
                  patch.object(v, "verify_run", side_effect=(RuntimeError("failed deploy") if fail_run else None), return_value="123"),
                  patch.object(v, "verify_public", side_effect=public) as reader,
                  patch.dict(v.os.environ, {"SOURCE_HEAD_SHA": SHA})):
                if fail_run:
                    with self.assertRaisesRegex(RuntimeError, "failed deploy"):
                        v.verify_all()
                elif fail_protocol:
                    with self.assertRaisesRegex(RuntimeError, "Public protocol unavailable"):
                        v.verify_all()
                elif changed_main:
                    with self.assertRaisesRegex(RuntimeError, "differs from validated commit"):
                        v.verify_all()
                else:
                    self.assertIsNone(v.verify_all())
                    self.assertEqual(reader.call_count, 2)
                    self.assertEqual([x.kwargs["url"] for x in reader.call_args_list],
                                     [v.SITE, v.PROTOCOL_SITE])
                    evidence = json.loads((root / ".automation-audit/publication-verification.json").read_text())
                    self.assertEqual(evidence["verification_status"], "CANONICAL_BYTES_VERIFIED")
                    self.assertEqual(evidence["kind"], "code_only")
                    self.assertEqual(evidence["head_sha"], SHA)
                    self.assertEqual(evidence["history_sha256"], hashlib.sha256(history_raw).hexdigest())
                    self.assertEqual(evidence["protocol_html_sha256"], hashlib.sha256(proto).hexdigest())
                if fail_run or fail_protocol or changed_main:
                    self.assertFalse((root / ".automation-audit/publication-verification.json").exists())
                self.assertFalse((root / ".verified-publication.json").exists())

    def test_code_only_verifies_both_urls_and_creates_audit_not_social_receipt(self):
        self._code_only()

    def test_code_only_fails_if_protocol_unavailable(self):
        self._code_only(fail_protocol=True)

    def test_code_only_fails_if_deployment_not_verified(self):
        self._code_only(fail_run=True)

    def test_code_only_fails_if_main_changed(self):
        self._code_only(changed_main=True)


if __name__ == "__main__":
    unittest.main()
