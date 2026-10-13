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
            "The parallel-market rial may fall by 25% over a rolling 30-day period"
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

    def test_pre_v1_carried_evidence_without_publisher_is_preserved(self):
        """The real September archive omits newer optional provenance fields."""
        history=json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))
        legacy=next(row for update in history["updates"]
                    if update["date"]=="2026-09-27"
                    for row in update["evidence"] if row["id"]=="E-20260927-03")
        self.assertNotIn("publisher",legacy)
        self.assertNotIn("source_title",legacy)
        self.assertNotIn("event_date",legacy)
        before=copy.deepcopy(legacy)
        claimed={"id":legacy["id"],"source":legacy["source"],
                 "category":legacy["category"],"evidence_status":"carried_forward",
                 "publisher":"Unverified attribution must not be copied",
                 "source_title":"Unverified replacement headline"}
        out=a.freeze_evidence(
            {"evidence":copy.deepcopy(self.e)+[claimed]},self.sources,
            {"evidence":[legacy]},self.date,self.cutoff)
        expected=copy.deepcopy(before)
        expected["evidence_status"]="carried_forward"
        self.assertEqual(out[-1],expected)
        self.assertEqual(legacy,before)
        self.assertNotIn("publisher",out[-1])

    def test_legacy_record_does_not_weaken_publisher_diversity(self):
        history=json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))
        legacy=next(row for update in history["updates"]
                    if update["date"]=="2026-09-27"
                    for row in update["evidence"] if row["id"]=="E-20260927-03")
        items=copy.deepcopy(self.e)
        for item in items:
            item["publisher"]="Only one verified publisher"
        items.append({"id":legacy["id"],"source":legacy["source"],
                      "evidence_status":"carried_forward"})
        with self.assertRaisesRegex(ValueError,"Require three source publishers"):
            a.freeze_evidence({"evidence":items},self.sources,
                              {"evidence":[legacy]},self.date,self.cutoff)

    def test_ap_syndicated_mirror_is_carried_with_original_id(self):
        """An ABC-hosted reprint is not a second independent AP report."""
        archived=next(e for u in self.h["updates"] for e in u.get("evidence",[])
                      if e.get("id")=="E-20261004-05")
        mirror={"event_date":archived["event_date"],
                "category":"Medicine / claimed supply resilience",
                "observation":"Extra context from the identical syndicated report.",
                "source":"https://abcnews.com/Business/wireStory/iranians-face-soaring-prices-medicine-us-blockade-sanctions-136878849",
                "source_title":archived["source_title"],
                "publisher":"Associated Press via ABC News",
                "reliability":"High","affects":["Food / medicine"],
                "evidence_status":"new","impact_magnitude":"moderate","direction":"lowers"}
        items=copy.deepcopy(self.e)+[mirror]
        cited=set(self.sources)|{mirror["source"]}
        out=a.freeze_evidence({"evidence":items},cited,
                              {"evidence":[archived]},self.date,self.cutoff)
        expected=copy.deepcopy(archived)
        expected["evidence_status"]="carried_forward"
        self.assertEqual(out[-1],expected)
        self.assertEqual(len(out),len(items))
        self.assertEqual(sum(v["evidence_status"]=="new" for v in out),6)
        # An uncited mirror cannot evade the source-verification rule.
        with self.assertRaisesRegex(ValueError,"Syndicated source"):
            a.freeze_evidence({"evidence":items},self.sources,
                              {"evidence":[archived]},self.date,self.cutoff)
        # A different report date is not necessarily the same source/event.
        other=copy.deepcopy(mirror)
        other["event_date"]=self.date
        different=a.freeze_evidence({"evidence":copy.deepcopy(self.e)+[other]},cited,
                                    {"evidence":[archived]},self.date,self.cutoff)
        self.assertEqual(different[-1]["evidence_status"],"new")

    def test_haircut_component_support_is_not_optional_for_nonzero_points(self):
        without=copy.deepcopy(self.analysis)
        del without["haircut_component_support"]
        with self.assertRaisesRegex(ValueError,"Six explicit oil-credit"):
            a.assemble(self.h,without,self.frozen(),self.cutoff,
                       self.opened,self.opened+dt.timedelta(seconds=1))
        unsupported=copy.deepcopy(self.analysis)
        point="Oil-price/basis"
        self.assertGreater(unsupported["haircut_components"][point],0)
        unsupported["haircut_component_support"][point]={
            "basis":"no_support","evidence_ids":[],
            "rationale":"There is no relevant synthetic source that supports this adjustment."}
        with self.assertRaisesRegex(ValueError,"Nonzero oil-credit component"):
            a.assemble(self.h,unsupported,self.frozen(),self.cutoff,
                       self.opened,self.opened+dt.timedelta(seconds=1))

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
        self.assertEqual(calls, ["research"] + ["metadata"] * 6 + ["assess", "review", "review"])
        self.assertEqual(len(out["updates"][-1]["forecasts"]), 4)

    def test_rejected_review_never_produces_candidate(self):
        times = iter([self.cutoff, self.cutoff, self.opened])
        calls=[]
        def reject(prompt,search):
            self.assertFalse(search)
            calls.append("affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical")
            return {"approved":False,"issues":[{"type":"evidence_gap",
                "location":"summary","reason":"Unsupported assertion persists."}]},set()
        with self.assertRaisesRegex(ValueError, "cycles exhausted"):
            a.produce(self.h, lambda p, s: ({"evidence": self.e}, self.sources),
                      lambda p, s: (self.analysis, set()), lambda: next(times),
                      lambda u: {}, reject)
        self.assertEqual(calls,["affirmative","critical"]*a.REVIEW_CYCLES_LIMIT)

    def test_reviewer_can_correct_language_without_changing_four_forecasts(self):
        times=iter([self.cutoff-dt.timedelta(seconds=5),self.cutoff,
                    self.opened,self.opened+dt.timedelta(seconds=4)])
        first=copy.deepcopy(self.analysis)
        first["warning"]["Food / medicine"]["text"]="Unsupported affirmative hospital resilience."
        corrected=copy.deepcopy(first)
        corrected["warning"]["Food / medicine"]["text"]=(
            "No broad hospital shortage has been documented; the available "
            "evidence does not establish resilience or normal supply.")
        calls=[]
        def research(prompt,search):
            return {"evidence":self.e},self.sources
        def assess(prompt,search):
            self.assertFalse(search)
            calls.append("assess")
            return (first if calls.count("assess")==1 else corrected),set()
        def review(prompt,search):
            self.assertFalse(search)
            calls.append("review")
            self.assertIn("ONLY to next_threshold",prompt)
            if calls.count("review")==1:
                return {"approved":False,"issues":[{
                    "type":"unsupported_claim","location":"warning.Food / medicine",
                    "reason":"Unsupported hospital supply resilience."}]},set()
            return {"approved":True,"issues":[]},set()
        out=a.produce(self.h,research,assess,lambda:next(times),
                      lambda url:{},review)
        self.assertEqual([x for x in calls if x=="assess"],["assess","assess"])
        self.assertEqual([x for x in calls if x=="review"],["review"]*4)
        self.assertEqual(out["updates"][-1]["warning"]["Food / medicine"]["text"],
                         corrected["warning"]["Food / medicine"]["text"])
        self.assertEqual(out["updates"][-1]["forecasts"][0]["p"],first["forecasts"][0]["p"])
        validate_history(out,self.h)

    def test_review_correction_cannot_change_scored_forecasts(self):
        times=iter([self.cutoff-dt.timedelta(seconds=5),self.cutoff,self.opened])
        altered=copy.deepcopy(self.analysis)
        altered["forecasts"][0]["p"]+=1
        n=[0]
        def assessor(prompt,search):
            n[0]+=1
            return (self.analysis if n[0]==1 else altered),set()
        def reviewer(prompt,search):
            return {"approved":False,"issues":[{"type":"unsupported_claim",
                                                "location":"summary","reason":"Fix a claim."}]},set()
        unchanged=copy.deepcopy(self.h)
        with self.assertRaisesRegex(ValueError,"locked four core forecasts"):
            a.produce(self.h,
                      lambda p,search:({"evidence":self.e},self.sources),
                      assessor,lambda:next(times),lambda url:{},reviewer)
        self.assertEqual(self.h,unchanged)

    def test_positive_review_alone_cannot_pass_critical_rejection(self):
        times=iter([self.cutoff-dt.timedelta(seconds=5),self.cutoff,
                    self.opened,self.opened+dt.timedelta(seconds=4)])
        initial=copy.deepcopy(self.analysis)
        revision=copy.deepcopy(initial)
        revision["summary"]="The synthetic report explicitly distinguishes judgment from observation."
        calls=[]
        def assessor(prompt,search):
            calls.append("assessor")
            if "locked_forecasts" in prompt:
                self.assertIn('"review_role": "critical"',prompt)
                return revision,set()
            return initial,set()
        def reviewer(prompt,search):
            role="affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical"
            calls.append(role)
            self.assertFalse(search)
            if role=="critical" and calls.count("critical")==1:
                return {"approved":False,"issues":[{"type":"unsupported_claim",
                    "location":"summary","reason":"The summary overstates an observation."}]},set()
            return {"approved":True,"issues":[]},set()
        before=copy.deepcopy(self.h)
        result=a.produce(self.h,
                         lambda p,q:({"evidence":self.e},self.sources),
                         assessor,lambda:next(times),lambda u:{},reviewer)
        self.assertEqual(calls,["assessor","affirmative","critical",
                                "assessor","affirmative","critical"])
        self.assertEqual(result["updates"][-1]["summary"],revision["summary"])
        self.assertEqual(result["updates"][-1]["forecasts"][0]["p"],
                         initial["forecasts"][0]["p"])
        self.assertEqual(self.h,before)

    def test_review_timeout_or_service_failure_is_never_a_pass(self):
        for failing_role in ("affirmative","critical"):
            with self.subTest(failing_role=failing_role):
                times=iter([self.cutoff-dt.timedelta(seconds=5),self.cutoff,self.opened])
                calls=[]
                def assessor(prompt,search):
                    calls.append("assessor")
                    return self.analysis,set()
                def reviewer(prompt,search):
                    role="affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical"
                    calls.append(role)
                    if role==failing_role:
                        raise TimeoutError("Review service timed out")
                    return {"approved":True,"issues":[]},set()
                with self.assertRaisesRegex(TimeoutError,"timed out"):
                    a.produce(self.h,
                              lambda p,q:({"evidence":self.e},self.sources),
                              assessor,lambda:next(times),lambda u:{},reviewer)
                self.assertEqual(calls,["assessor"]+(
                    ["affirmative"] if failing_role=="affirmative" else
                    ["affirmative","critical"]))
                self.assertEqual(self.h["updates"][-1]["date"],
                                 (self.opened.date()-dt.timedelta(days=7)).isoformat())

    def test_inconsistent_or_malformed_verdict_fails_without_correction(self):
        for response in ({"approved":True,"issues":[{"type":"x",
                           "location":"summary","reason":"Not actually clean."}]},
                         {"approved":False,"issues":[]},
                         {"approved":True},
                         {"approved":False,"issues":["bad issue"]}):
            with self.subTest(response=response):
                times=iter([self.cutoff-dt.timedelta(seconds=5),self.cutoff,self.opened])
                calls=[]
                def assessor(prompt,search):
                    calls.append("assessor")
                    return self.analysis,set()
                def reviewer(prompt,search):
                    calls.append("reviewer")
                    return response,set()
                with self.assertRaisesRegex(ValueError,"review"):
                    a.produce(self.h,
                              lambda p,q:({"evidence":self.e},self.sources),
                              assessor,lambda:next(times),lambda u:{},reviewer)
                self.assertEqual(calls,["assessor","reviewer"])

    def test_review_elapsed_limit_is_blocking(self):
        times=iter([self.cutoff-dt.timedelta(seconds=5),self.cutoff,self.opened])
        called=[]
        def reviewer(prompt,search):
            called.append("review")
            return {"approved":True,"issues":[]},set()
        with patch.object(a.time,"monotonic",side_effect=[0,1,a.REVIEW_ELAPSED_LIMIT_SECONDS+1]):
            with self.assertRaisesRegex(ValueError,"time limit exceeded"):
                a.produce(self.h,
                          lambda p,q:({"evidence":self.e},self.sources),
                          lambda p,q:(self.analysis,set()),
                          lambda:next(times),lambda u:{},reviewer)
        self.assertEqual(called,[])

    def test_affirmative_and_critical_are_called_in_order_on_same_draft(self):
        times=iter([self.cutoff-dt.timedelta(seconds=5),self.cutoff,
                    self.opened,self.opened+dt.timedelta(seconds=4)])
        calls=[]
        def reviewer(prompt,search):
            role="affirmative" if "ROLE: AFFIRMATIVE" in prompt else "critical"
            calls.append((role,prompt.split('Input: ')[-1]))
            return {"approved":True,"issues":[]},set()
        result=a.produce(self.h,
                         lambda p,q:({"evidence":self.e},self.sources),
                         lambda p,q:(self.analysis,set()),
                         lambda:next(times),lambda u:{},reviewer)
        self.assertEqual([x[0] for x in calls],["affirmative","critical"])
        self.assertEqual(calls[0][1],calls[1][1])
        self.assertEqual(len(result["updates"]),len(self.h["updates"])+1)

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
            current=copy.deepcopy(self.analysis)
            for row in current["haircut_component_support"].values():
                if row["evidence_ids"]:
                    row["evidence_ids"]=[ledger[0]["id"]]
            record = a.assemble(history, current, ledger, stamp - dt.timedelta(seconds=5), stamp,
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
    def test_live_audit_does_not_include_synthetic_offline_test_records(self):
        workflow=(ROOT/".github/workflows/sunday-assessment.yml").read_text(encoding="utf-8")
        self.assertIn("rm -rf -- .automation-audit",workflow)
        self.assertLess(workflow.index("- name: Offline readiness tests"),
                        workflow.index("- name: Discard synthetic offline-test audit files"))
        self.assertLess(workflow.index("- name: Discard synthetic offline-test audit files"),
                        workflow.index("- name: Mint short-lived diagnostic GitHub App token"))

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
