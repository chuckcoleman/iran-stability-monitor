"""Offline tests; no inference, GitHub writes, or publication."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import assessment_pipeline as a
import candidate_checks as c
import sunday_automation as s
from validate_history import validate_history
from automation_fixtures import fixture, ZONE


class SundayPipelineTests(unittest.TestCase):
    def setUp(self):
        self.h, self.analysis, self.e, self.opened = fixture()
        self.cutoff = self.opened - dt.timedelta(seconds=10)
        self.date = self.opened.date().isoformat()
        self.sources = {x["source"] for x in self.e}

    def frozen(self, metadata=None):
        return a.freeze_evidence({"evidence": self.e}, self.sources, self.h["updates"][-1], self.date, self.cutoff, metadata)

    def record(self):
        return a.assemble(self.h, self.analysis, self.frozen(), self.cutoff, self.opened, self.opened + dt.timedelta(seconds=1))

    def test_next_threshold_requires_declarative_event_sentences(self):
        """Do not reintroduce narrative 'we', questions or merged events."""
        for fragment in (
            "Whether essential state allocations become disrupted for fourteen days.",
            "We are watching whether payments fail in multiple import categories.",
            "We will check whether the rial depreciates over the next month.",
            "A regional war may expand; currency payments may fail.",
            "Will major interstate strikes continue for three days?",
            "The rial may fall by 25% over 30 days"
        ):
            with self.subTest(fragment=fragment):
                self.analysis["next_threshold"] = fragment
                with self.assertRaisesRegex(ValueError, "simple declarative sentences"):
                    self.record()
        self.analysis["next_threshold"] = (
            "A two-week payment disruption in two essential import categories could signal a crisis. "
            "A sustained 25% rial depreciation over 30 days would reach the currency threshold."
        )
        self.assertEqual(self.record()["next_threshold"], self.analysis["next_threshold"])

    def test_deadline_dst_and_leap(self):
        x = dt.datetime(2026, 10, 18, 9, tzinfo=ZONE)
        self.assertEqual(a.deadline(x, a.IDS[0]), "2027-01-16T09:00:00-05:00")
        self.assertEqual(a.deadline(dt.datetime(2028, 2, 29, 13, 21, tzinfo=ZONE), a.IDS[1]), "2029-02-28T13:21:00-05:00")

    def test_oil_credit_overlap(self):
        vals = [18, 12, 6, 5, 5, 7]
        out = a.haircut(dict(zip([k for k, cap in a.CAPS], vals)))
        self.assertEqual((out["raw_sum"], out["adjusted_headline"], out["sensitivity"]["overlap_40pct"]), (53, 50, 46))
        with self.assertRaises(ValueError):
            a.haircut({k: cap + 1 for k, cap in a.CAPS})

    def test_unknown_time_is_not_fabricated(self):
        self.assertTrue(all(x["source_publication_time"] is None for x in self.frozen()))

    def test_uncited_source_blocks(self):
        self.sources.pop()
        with self.assertRaisesRegex(ValueError, "not verified"):
            self.frozen()

    def test_known_metadata_time_is_retained(self):
        value = (self.cutoff - dt.timedelta(hours=1)).isoformat()
        out = self.frozen({self.e[0]["source"]: {"source_publication_time": value,
                            "publication_candidates": [value], "metadata_status": "verified article metadata"}})
        self.assertEqual(out[0]["source_publication_time"], value)

    def test_future_metadata_blocks(self):
        stamp = (self.cutoff + dt.timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "post-cutoff"):
            self.frozen({self.e[0]["source"]: {"publication_candidates": [stamp]}})

    def test_future_claim_cannot_be_hidden_as_unknown(self):
        self.e[0]["source_publication_time"] = (self.cutoff + dt.timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "post-cutoff"):
            self.frozen()

    def test_metadata_must_finish_before_cutoff(self):
        with self.assertRaisesRegex(ValueError, "retrieved after cutoff"):
            self.frozen({self.e[0]["source"]: {"source_retrieved_at": (self.cutoff + dt.timedelta(seconds=1)).isoformat()}})

    def test_duplicate_source_reuses_persistent_id(self):
        prior = {"evidence": [self.frozen()[0]]}
        out = a.freeze_evidence({"evidence": self.e}, self.sources, prior, self.date, self.cutoff)
        self.assertEqual(out[0]["evidence_status"], "carried_forward")
        self.assertEqual(out[0]["id"], prior["evidence"][0]["id"])

    def test_exact_append_and_prospective_baselines(self):
        before = copy.deepcopy(self.h)
        new = copy.deepcopy(self.h)
        new["updates"].append(self.record())
        c.one_append(self.h, new)
        validate_history(new, self.h)
        self.assertEqual(self.h, before)
        for f, r in zip(new["updates"][-1]["forecasts"], new["updates"][-1]["revision_attribution"]):
            self.assertEqual(f["forecast_id"], f["event_id"] + "_" + self.date.replace("-", ""))
            self.assertEqual(r["prior_p"], f["p"])

    def test_core_count_and_probabilities_block_invalid(self):
        self.analysis["forecasts"].pop()
        with self.assertRaisesRegex(ValueError, "Exactly four"):
            self.record()

    def test_zero_revision_does_not_require_invented_offsets(self):
        self.assertTrue(all(r["contributions"][0]["pp"] == 0 for r in self.record()["revision_attribution"]))

    def test_no_auto_residual(self):
        self.analysis["revision_attribution"][0]["contributions"][0]["pp"] = 3
        with self.assertRaisesRegex(ValueError, "does not reconcile"):
            self.record()

    def test_declared_residual_is_accepted(self):
        self.analysis["revision_attribution"][0]["contributions"][0]["pp"] = 3
        self.analysis["revision_attribution"][0]["residual_pp"] = -3
        self.assertEqual(self.record()["revision_attribution"][0]["residual_pp"], -3)

    def test_no_fabricated_scenario_partition(self):
        del self.analysis["regional"]
        with self.assertRaisesRegex(ValueError, "refreshed dashboard"):
            self.record()

    def test_no_stale_houthi_horizons(self):
        del self.analysis["houthi"]["m24"]
        with self.assertRaisesRegex(ValueError, "m24"):
            self.record()

    def test_html_and_attribute_injection_blocked(self):
        self.analysis["summary"] = '<script>alert("bad")</script>' + 'x' * 50
        with self.assertRaisesRegex(ValueError, "Unsafe HTML"):
            self.record()
        self.analysis["summary"] = 'A' * 50
        self.analysis["chains"][0]["level"] = '" onclick="bad'
        with self.assertRaisesRegex(ValueError, "Unsafe chain"):
            self.record()

    def test_full_pipeline_phase_order_and_reviewer(self):
        calls = []
        times = iter([self.cutoff - dt.timedelta(seconds=5), self.cutoff, self.opened,
                      self.opened + dt.timedelta(seconds=4)])
        def research(prompt, search):
            calls.append("research")
            self.assertTrue(search)
            return {"evidence": self.e}, self.sources
        def metadata(url):
            calls.append("metadata")
            return {"source_retrieved_at": (self.cutoff - dt.timedelta(seconds=1)).isoformat()}
        def assess(prompt, search):
            calls.append("assess")
            self.assertFalse(search)
            return self.analysis, set()
        def review(prompt, search):
            calls.append("review")
            self.assertFalse(search)
            return {"approved": True, "issues": []}, set()
        out = a.produce(self.h, research, assess, lambda: next(times), metadata, review)
        validate_history(out, self.h)
        self.assertEqual(calls, ["research"] + ["metadata"] * 6 + ["assess", "review"])
        self.assertEqual(len(out["updates"][-1]["forecasts"]), 4)

    def test_rejected_review_never_produces_candidate(self):
        times = iter([self.cutoff, self.cutoff, self.opened])
        with self.assertRaisesRegex(ValueError, "review rejected"):
            a.produce(self.h, lambda p, s: ({"evidence": self.e}, self.sources),
                      lambda p, s: (self.analysis, set()), lambda: next(times),
                      lambda u: {}, lambda p, s: ({"approved": False, "issues": ["unsupported"]}, set()))

    def test_commit_issue_time_only_new_record(self):
        out = copy.deepcopy(self.h)
        out["updates"].append(self.record())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text(json.dumps(out))
            stamp = self.opened + dt.timedelta(seconds=20)
            c.issue_time(path, self.h, stamp)
            result = json.loads(path.read_text())
            self.assertEqual(result["updates"][:-1], self.h["updates"])
            self.assertEqual(result["updates"][-1]["publication_time"], stamp.isoformat())

    def test_multiple_sundays_including_first_of_month(self):
        history = copy.deepcopy(self.h)
        stamp = self.opened
        for week in range(5):
            items = copy.deepcopy(self.e)
            for item in items:
                item["event_date"] = (stamp.date() - dt.timedelta(days=1)).isoformat()
            ledger = a.freeze_evidence({"evidence": items}, self.sources, history["updates"][-1],
                                       stamp.date().isoformat(), stamp - dt.timedelta(seconds=5))
            record = a.assemble(history, self.analysis, ledger, stamp - dt.timedelta(seconds=5), stamp,
                                stamp + dt.timedelta(seconds=1))
            candidate = copy.deepcopy(history); candidate["updates"].append(record)
            validate_history(candidate, history)
            c.one_append(history, candidate)
            history = candidate
            stamp += dt.timedelta(days=7)
        self.assertEqual(len(history["updates"]), len(self.h["updates"]) + 5)

    def test_all_historical_and_root_mutations_block(self):
        out = copy.deepcopy(self.h)
        out["updates"].append(self.record())
        out["updates"][0]["summary"] += "silently revised"
        with self.assertRaisesRegex(ValueError, "Historical"):
            c.one_append(self.h, out)


class OrchestrationTests(unittest.TestCase):
    def test_schedule_nominal_dst_and_delays(self):
        summer = dt.datetime(2026, 10, 18, 11, 30, tzinfo=ZONE)
        winter = dt.datetime(2026, 11, 1, 10, 30, tzinfo=ZONE)
        self.assertTrue(s.schedule_slot(summer, "0 13 * * 0"))
        self.assertFalse(s.schedule_slot(summer, "0 14 * * 0"))
        self.assertTrue(s.schedule_slot(winter, "0 14 * * 0"))
        self.assertFalse(s.schedule_slot(winter, "0 13 * * 0"))

    def rule(self):
        return {"enforcement": "active", "bypass_actors": [], "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
           "rules": [{"type": "pull_request"}, {"type": "deletion"}, {"type": "non_fast_forward"},
                     {"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": True,
                           "required_status_checks": [{"context": "validate", "integration_id": 15368}]}}]}

    def test_main_gate_requires_strict_no_bypass(self):
        r = self.rule()
        self.assertTrue(s.protects_main(r))
        r["rules"][-1]["parameters"]["strict_required_status_checks_policy"] = False
        self.assertFalse(s.protects_main(r))
        r = self.rule(); r["bypass_actors"] = [{"actor_id": 1}]
        self.assertFalse(s.protects_main(r))
        r = self.rule(); r["conditions"]["ref_name"]["exclude"] = ["refs/heads/main"]
        self.assertFalse(s.protects_main(r))

    def test_failed_ci_cannot_merge(self):
        data = {"workflow_runs": [{"id": 1, "head_sha": "abc", "path": ".github/workflows/validate.yml", "status": "completed", "conclusion": "failure"}]}
        with patch.object(s, "gh_json", return_value=data):
            with self.assertRaisesRegex(RuntimeError, "CI failed"):
                s.wait_checks("owner/repo", "branch", "abc")

    def test_disabled_run_does_not_require_secrets(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(s.ready())


if __name__ == "__main__":
    unittest.main()
