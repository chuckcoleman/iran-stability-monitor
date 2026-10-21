"""Regression tests for exact-match GET-only recovery of research Responses."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import responses_transport as transport


def body(obj):
    return io.BytesIO(json.dumps(obj).encode("utf-8"))


def payload():
    return {"model": "test-model", "input": "DO_NOT_LEAK_prompt",
            "store": False, "tools": [{"type": "web_search"}],
            "include": ["web_search_call.action.sources"]}


def redacted(exc, search):
    return RuntimeError("Redacted HTTP " + str(exc.code))


class ResumeTests(unittest.TestCase):
    def setUp(self):
        context = tempfile.TemporaryDirectory()
        self.addCleanup(context.cleanup)
        self.dir = Path(context.name)
        self.methods = []

    def call(self, opener, *, resume=False, data=None, monotonic=None,
             max_poll_seconds=1200):
        def recorded(req, timeout):
            self.methods.append(req.get_method())
            return opener(req, timeout)
        return transport.request_response(
            payload() if data is None else data, search=True,
            token_supplier=lambda: "SECRET_ACCESS_TOKEN",
            audit_dir=self.dir, http_error_formatter=redacted,
            opener=recorded, sleeper=lambda _: None,
            monotonic=monotonic or (lambda: 0),
            max_poll_seconds=max_poll_seconds,
            resume_dir=self.dir if resume else None)

    def audits(self):
        rows = [json.loads(p.read_text(encoding="utf-8"))
                for p in self.dir.glob("api-request-*.json")]
        self.assertTrue(rows)
        for p in self.dir.glob("api-request-*.json"):
            t = p.read_text(encoding="utf-8")
            self.assertNotIn("DO_NOT_LEAK_prompt", t)
            self.assertNotIn("SECRET_ACCESS_TOKEN", t)
        return rows

    def timed_out_initial(self):
        times = iter((0, 1201))
        def opener(req, timeout):
            return body({"id": "resp_resume123", "status": "in_progress"})
        with self.assertRaisesRegex(RuntimeError, "poll budget"):
            self.call(opener, monotonic=lambda: next(times))
        self.assertEqual(self.methods, ["POST"])
        self.assertEqual(self.audits()[0]["status"], "background_timeout_no_replay")

    def test_budget_was_raised_but_bounded(self):
        self.assertEqual(transport.MAX_POLL_SECONDS, 1200)
        self.assertEqual(transport.MAX_POLLS, 240)

    def test_timeout_can_resume_via_get_without_second_post(self):
        self.timed_out_initial()
        result = self.call(lambda req, timeout: body({
            "id": "resp_resume123", "status": "completed",
            "output": [{"type": "web_search_call", "action": {"sources": [
                {"url": "https://news.example.org/iran"}]}}]}), resume=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.methods, ["POST", "GET"])
        rows = self.audits()
        self.assertEqual(len(rows), 2)
        recovered = next(r for r in rows if r["post_attempts"] == 0)
        self.assertEqual(recovered["response_id"], "resp_resume123")
        self.assertEqual(recovered["status"], "api_completed_output_not_yet_validated")
        self.assertEqual(recovered["poll_count"], 1)
        self.assertEqual(len(recovered["resumed_from_audits"]), 1)

    def test_missing_prior_artifact_fails_before_network(self):
        with self.assertRaisesRegex(RuntimeError, "No exact matching"):
            self.call(lambda req, timeout: self.fail("No network"), resume=True)
        self.assertEqual(self.methods, [])
        self.assertEqual(self.audits()[0]["status"], "resume_rejected_no_post")

    def test_changed_prompt_rejected_without_post(self):
        self.timed_out_initial()
        other = payload()
        other["input"] = "changed task"
        with self.assertRaisesRegex(RuntimeError, "No exact matching"):
            self.call(lambda req, timeout: self.fail("No network"),
                      resume=True, data=other)
        self.assertEqual(self.methods, ["POST"])
        self.assertEqual(len(self.audits()), 2)

    def test_terminal_failure_cannot_resume(self):
        self.timed_out_initial()
        path = next(self.dir.glob("api-request-*.json"))
        row = json.loads(path.read_text())
        row["status"] = "background_terminal_failure"
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(RuntimeError, "not resumable"):
            self.call(lambda req, timeout: self.fail("No network"), resume=True)
        self.assertEqual(self.methods, ["POST"])

    def test_ambiguous_response_ids_rejected_without_post(self):
        self.timed_out_initial()
        path = next(self.dir.glob("api-request-*.json"))
        row = json.loads(path.read_text())
        row["response_id"] = "resp_other456"
        (self.dir / "api-request-second.json").write_text(json.dumps(row))
        with self.assertRaisesRegex(RuntimeError, "Ambiguous matching"):
            self.call(lambda req, timeout: self.fail("No network"), resume=True)
        self.assertEqual(self.methods, ["POST"])

    def test_resume_poll_timeout_is_not_approval(self):
        self.timed_out_initial()
        times = iter((0, 1201))
        with self.assertRaisesRegex(RuntimeError, "poll budget"):
            self.call(lambda req, timeout: body({
                "id": "resp_resume123", "status": "in_progress"}),
                resume=True, monotonic=lambda: next(times))
        self.assertEqual(self.methods, ["POST"])
        rows = self.audits()
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(r["status"] == "background_timeout_no_replay"
                            and r["post_attempts"] == 0 for r in rows))

    def test_wrong_id_in_resumed_get_rejected(self):
        self.timed_out_initial()
        with self.assertRaisesRegex(RuntimeError, "wrong/unknown response ID"):
            self.call(lambda req, timeout: body({
                "id": "resp_wrong999", "status": "completed"}), resume=True)
        self.assertEqual(self.methods, ["POST", "GET"])

    def test_resume_disallowed_for_foreground_review(self):
        with self.assertRaisesRegex(ValueError, "Only background"):
            transport.request_response({"model": "test-model", "store": False},
                search=False, token_supplier=lambda: self.fail("No network"),
                audit_dir=self.dir, http_error_formatter=redacted,
                resume_dir=self.dir)
        self.assertEqual(self.methods, [])

    def test_workflow_requires_opt_in_and_preserves_diagnostics(self):
        workflow = (ROOT / ".github/workflows/sunday-assessment.yml").read_text()
        self.assertIn("timeout-minutes: 45", workflow)
        self.assertIn("resume_run_id:", workflow)
        self.assertIn("actions/download-artifact@v4", workflow)
        self.assertIn("IRAN_STAGED_RESUME:", workflow)
        self.assertIn("inputs.mode == 'research-dry-run'", workflow)
        self.assertIn("if: always()", workflow)
        self.assertNotIn("  schedule:", workflow)


if __name__ == "__main__":
    unittest.main()
