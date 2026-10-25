"""Offline chart regression tests: exact assessment-date ticks and elapsed-time spacing."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "assets" / "app.js"
INDEX = ROOT / "index.html"


@unittest.skipUnless(shutil.which("node"), "Node.js required for canvas regression")
class ChartDateTests(unittest.TestCase):
    def render(self, records):
        js = r"""
const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync('assets/app.js','utf8');
const start=source.indexOf('function axes(c,max=100)');
if(start<0)throw Error('Chart source is missing');
globalThis.pct=x=>x==null?'—':x+'%';
function canvas(height){
  const out={labels:[],dots:[],attributes:{},ticks:[]};
  const ctx={
    clearRect(){},beginPath(){},stroke(){},fill(){},save(){},restore(){},
    moveTo(x,y){out.ticks.push({x,y})},lineTo(){},
    arc(x,y){out.dots.push({x,y})},
    fillText(text,x,y){out.labels.push({text,x,y})}
  };
  return {width:900,height,getContext(){return ctx},
          setAttribute(k,v){out.attributes[k]=v},out};
}
globalThis.chart=canvas(300);
globalThis.haircutChart=canvas(240);
vm.runInThisContext(source.slice(start));
const input=JSON.parse(fs.readFileSync(0,'utf8'));
drawForecasts(input);
drawHaircut(input);
console.log(JSON.stringify({forecast:chart.out,haircut:haircutChart.out}));
"""
        result = subprocess.run(
            ["node", "-e", js], cwd=ROOT, input=json.dumps(records),
            text=True, capture_output=True, check=False, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip())

    def sample(self, date, escalation=30, regime=10, fx=84, haircut=38, scored=True):
        record = {"date":date,"metrics":{
            "regional_escalation_90d":escalation,
            "regime_end_12m":regime,
            "fx_crisis_12m":fx,
            "china_oil_credit_haircut":haircut}}
        if scored:
            # The legacy fx_crisis_12m metric is NOT a scored currency event.
            record["forecasts"] = [
                {"event_id":"regional_escalation_90d","p":escalation,"scored":True},
                {"event_id":"regime_end_12m","p":regime,"scored":True},
                {"event_id":"currency_crisis_12m","p":80,"scored":True},
                {"event_id":"external_payments_crisis_12m","p":86,"scored":True},
            ]
        return record

    def test_charts_use_their_proper_historical_date_sets(self):
        current=json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))
        records=current["updates"]
        out=self.render(records)
        dates=[x["date"] for x in records]
        scored_ids={"regional_escalation_90d","regime_end_12m",
                    "currency_crisis_12m","external_payments_crisis_12m"}
        scored_dates=[
            row["date"] for row in records
            if {f.get("event_id") for f in row.get("forecasts",[])
                if f.get("scored") is True} == scored_ids
        ]
        self.assertEqual(dates[:4],["2026-09-20","2026-09-27",
                                    "2026-10-04","2026-10-11"])
        self.assertTrue(scored_dates)
        self.assertEqual(scored_dates[0],"2026-10-04")
        for key,expected_dates in (("forecast",scored_dates),("haircut",dates)):
            chart=out[key]
            labels=[x["text"] for x in chart["labels"]
                    if x["text"] in dates]
            self.assertEqual(labels[0],expected_dates[0])
            self.assertEqual(labels[-1],expected_dates[-1])
            self.assertEqual(labels,[x for x in expected_dates if x in labels])
            if len(expected_dates)<=9:
                self.assertEqual(labels,expected_dates)
            self.assertTrue(all(x["y"]>=200 for x in chart["labels"]
                                if x["text"] in expected_dates))
            self.assertEqual(chart["attributes"]["role"],"img")
            self.assertIn(expected_dates[0],chart["attributes"]["aria-label"])
            self.assertIn(expected_dates[-1],chart["attributes"]["aria-label"])
        self.assertEqual(len(out["forecast"]["dots"]),4*len(scored_dates))
        self.assertEqual(len(out["haircut"]["dots"]),len(dates))

    def test_legacy_rows_do_not_create_scored_forecast_dates(self):
        points=[self.sample("2026-09-20",scored=False),
                self.sample("2026-10-04"),
                self.sample("2026-10-11")]
        out=self.render(points)
        labels=[v["text"] for v in out["forecast"]["labels"]]
        self.assertNotIn("2026-09-20",labels)
        self.assertIn("2026-10-04",labels)
        self.assertIn("2026-10-11",labels)
        self.assertEqual(len(out["forecast"]["dots"]),8)
        self.assertEqual(len(out["haircut"]["dots"]),3)
        self.assertNotIn("2026-09-20",out["forecast"]["attributes"]["aria-label"])

    def test_scored_currency_not_legacy_fx_composite(self):
        out=self.render([self.sample("2026-10-04",fx=82)])
        label=out["forecast"]["attributes"]["aria-label"]
        self.assertIn("Currency crisis 80%",label)
        self.assertNotIn("Currency crisis 82%",label)
        self.assertIn("Payments crisis 86%",label)

    def test_horizontal_position_follows_calendar_time_not_record_index(self):
        points=[self.sample("2026-01-01"),self.sample("2026-01-02"),
                self.sample("2026-01-11")]
        out=self.render(points)
        for key in ("forecast","haircut"):
            xx=[p["x"] for p in out[key]["dots"]]
            first,second,last=xx[:3] if key=="haircut" else xx[:3]
            self.assertAlmostEqual((second-first)/(last-first),0.1,places=7)
            labels=[p["text"] for p in out[key]["labels"]
                    if p["text"].startswith("2026-")]
            self.assertIn("2026-01-01",labels)
            self.assertIn("2026-01-11",labels)

    def test_dense_history_keeps_first_and_last_dates_without_overlap(self):
        import datetime as dt
        begin=dt.date(2026,1,1)
        points=[self.sample((begin+dt.timedelta(days=i*7)).isoformat())
                for i in range(52)]
        out=self.render(points)
        for key in ("forecast","haircut"):
            dates=[x for x in out[key]["labels"] if x["text"][:2]=="20"
                   and len(x["text"])==10]
            self.assertEqual(dates[0]["text"],points[0]["date"])
            self.assertEqual(dates[-1]["text"],points[-1]["date"])
            self.assertLessEqual(len(dates),11)
            for a,b in zip(dates,dates[1:]):
                self.assertGreaterEqual(b["x"]-a["x"],95)

    def test_single_dated_observation_is_centered(self):
        out=self.render([self.sample("2027-04-01")])
        for key in ("forecast","haircut"):
            dates=[x for x in out[key]["labels"] if x["text"]=="2027-04-01"]
            self.assertEqual(len(dates),1)
            self.assertAlmostEqual(dates[0]["x"],450)

    def test_invalid_date_is_rejected(self):
        with self.assertRaisesRegex(AssertionError,"Invalid assessment date"):
            self.render([self.sample("not-a-date")])

    def test_html_explains_date_axis_without_changing_archived_values(self):
        html=INDEX.read_text(encoding="utf-8")
        self.assertEqual(html.count("Horizontal axis: assessment date (YYYY-MM-DD)."),2)
        self.assertIn('id="chart" width="900" height="300"',html)
        self.assertIn('id="haircutChart" width="900" height="240"',html)


if __name__ == "__main__":
    unittest.main()
