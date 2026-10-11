"""Offline invariants for unattended Sunday assessment. No network or credentials."""
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
import assessment_pipeline as a
from validate_history import validate_history

EDT=ZoneInfo("America/New_York")

class SundayPipelineTests(unittest.TestCase):
    def test_deadline_dst_and_calendar(self):
        t=dt.datetime(2026,10,18,9,0,0,tzinfo=EDT)
        self.assertEqual(a.deadline(t,a.IDS[0]),"2027-01-16T09:00:00-05:00")
        self.assertEqual(a.deadline(t,a.IDS[1]),"2027-10-18T09:00:00-04:00")
        leap=dt.datetime(2028,2,29,13,21,0,tzinfo=EDT)
        self.assertEqual(a.deadline(leap,a.IDS[1]),"2029-02-28T13:21:00-05:00")

    def test_oil_credit_overlap(self):
        result=a.haircut({key:({25:18,15:12,10:6,8:5}.get(cap,4)
                          if key!="Political/secondary-sanctions tail" else 7)
                          for key,cap in a.CAPS})
        self.assertEqual(result["raw_sum"],53)
        self.assertEqual(result["overlap_deduction_20pct"],3)
        self.assertEqual(result["adjusted_headline"],50)
        self.assertEqual(result["sensitivity"]["overlap_40pct"],46)

    def test_source_balance_citation_and_unknown_publication_time(self):
        day="2026-10-18";cutoff=dt.datetime(2026,10,18,10,2,tzinfo=EDT)
        past={"evidence":[]}
        evidence=[]
        refs=[]
        for i in range(6):
            url=f"https://independent{i%3}.example.org/report/{i}"
            refs.append(url)
            evidence.append({
                "source":url,"source_title":"Credible source headline",
                "publisher":f"Publisher {i%3}","event_date":"2026-10-17",
                "category":"Iran stability","observation":"A dated public statement about regional risks",
                "reliability":"Medium","impact_magnitude":"moderate",
                "direction":("raises","lowers","ambiguous")[i%3],
                "evidence_status":"new","affects":["Sustained major regional escalation"]})
        result=a.freeze_evidence({"evidence":evidence},set(refs),past,day,cutoff)
        self.assertEqual(len(result),6)
        self.assertTrue(all(e["source_publication_time"] is None for e in result))
        with self.assertRaisesRegex(ValueError,"not verified"):
            a.freeze_evidence({"evidence":evidence},set(refs[:-1]),past,day,cutoff)

    def test_exact_history_immutability_and_scored_record(self):
        history=json.loads((ROOT/"data/history.json").read_text())
        old=copy.deepcopy(history)
        prior=history["updates"][-1]
        date="2026-10-18"
        opened=dt.datetime(2026,10,18,9,10,5,tzinfo=EDT)
        cutoff=dt.datetime(2026,10,18,9,10,0,tzinfo=EDT)
        issued=dt.datetime(2026,10,18,9,10,7,tzinfo=EDT)
        forecasts=[]
        revisions=[]
        for f in prior["forecasts"]:
            if f.get("scored") is True:
                forecasts.append({"event_id":f["event_id"],"p":f["p"],
                    "range":[max(0,f["p"]-12),min(100,f["p"]+12)],
                    "confidence":"Medium"})
                revisions.append({"event_id":f["event_id"],
                    "contributions":[{"label":"Raising evidence","pp":1},
                                     {"label":"Offsetting evidence","pp":-1}]})
        warnings={k:{"level":v["level"],"direction":v["direction"],
                     "coverage":v["coverage"],"text":v["text"]}
                  for k,v in prior["warning"].items()}
        h={
            "summary":"A cautious stress-test forecast record with no numeric forecast revisions.",
            "what_changed":"A diagnostic baseline exercise using wholly synthetic stable judgments.",
            "stabilizer":"Testing verifies continued adherence to the original Protocol v1 constraints.",
            "next_threshold":"All real event thresholds remain unaltered throughout this test harness.",
            "limitations":"This fixture is synthetic and never permitted to be published to the public website.",
            "forecasts":forecasts,"revision_attribution":revisions,
            "warning":warnings,"conditions":prior["conditions"],
            "haircut_components":{k:p for k,p,c in prior["haircut"]["calculation"]["components"]},
            "haircut_range":prior["haircut"]["range"],
            "houthi":{
               "headline_support_12m":prior["metrics"]["houthi_support_12m"],
               "material_support_12m":prior["houthi"]["material_support_12m"],
               "technical_financial_support_12m":prior["houthi"]["technical_financial_support_12m"],
               "independent_capability_12m":prior["houthi"]["independent_capability_12m"]},
            "status":prior["status"]
        }
        record=a.assemble(history,h,copy.deepcopy(prior["evidence"]),cutoff,opened,issued)
        new=copy.deepcopy(history);new["updates"].append(record)
        validate_history(new,history)
        self.assertEqual(old,history)
        self.assertEqual([f["forecast_id"] for f in record["forecasts"]],
            [f"{key}_20261018" for key in a.IDS])
        self.assertEqual(record["revision_attribution"][0]["prior_p"],
                         prior["forecasts"][0]["p"])

if __name__=="__main__":
    unittest.main()
