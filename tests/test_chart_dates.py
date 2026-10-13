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
const input=JSON.parse(process.argv[1]);
drawForecasts(input);
drawHaircut(input);
console.log(JSON.stringify({forecast:chart.out,haircut:haircutChart.out}));
"""
        result = subprocess.run(
            ["node", "-e", js, json.dumps(records)], cwd=ROOT,
            text=True, capture_output=True, check=False, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip())

    def sample(self, date, escalation=30, regime=10, fx=84, haircut=38):
        return {"date":date,"metrics":{
            "regional_escalation_90d":escalation,
            "regime_end_12m":regime,"fx_crisis_12m":fx,
            "china_oil_credit_haircut":haircut}}

    def test_both_charts_label_every_date_of_current_history(self):
        current=json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))
        records=current["updates"]
        out=self.render(records)
        dates=[x["date"] for x in records]
        self.assertEqual(dates,["2026-09-20","2026-09-27","2026-10-04","2026-10-11"])
        for chart in (out["forecast"],out["haircut"]):
            labels=[x["text"] for x in chart["labels"] if x["text"] in dates]
            self.assertEqual(labels,dates)
            self.assertTrue(all(x["y"]>=200 for x in chart["labels"]
                                if x["text"] in dates))
            self.assertEqual(chart["attributes"]["role"],"img")
            self.assertIn(dates[0],chart["attributes"]["aria-label"])
            self.assertIn(dates[-1],chart["attributes"]["aria-label"])
        self.assertEqual(len(out["forecast"]["dots"]),3*len(dates))
        self.assertEqual(len(out["haircut"]["dots"]),len(dates))

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
