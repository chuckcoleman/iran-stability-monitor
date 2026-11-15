"""Offline canvas and SVG date-axis regression tests.

Both chart renderers must print every dated assessment below its own
vertical tick, in 45-degree NW-to-SE orientation, inside the chart drawing
bounds. Dense histories scroll horizontally inside the chart card.
"""
import datetime as dt
import json
import math
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "assets" / "app.js"
INDEX = ROOT / "index.html"
CSS = ROOT / "assets" / "style.css"


@unittest.skipUnless(shutil.which("node"), "Node.js required for chart regressions")
class ChartDateTests(unittest.TestCase):
    def render(self, records, mode="canvas"):
        source = r"""
const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync('assets/app.js','utf8');
const start=source.indexOf('const dateAxisLayout=');
if(start<0)throw Error('Chart date geometry is missing');
globalThis.pct=x=>x==null?'—':x+'%';
const input=JSON.parse(fs.readFileSync(0,'utf8'));
function canvas(height){
  const out={labels:[],dots:[],attributes:{},segments:[]};
  let tx=0,ty=0,angle=0,stack=[],lastPoint=null;
  const ctx={
    clearRect(){},beginPath(){lastPoint=null},stroke(){},fill(){},
    save(){stack.push({tx,ty,angle})},
    restore(){const t=stack.pop();tx=t.tx;ty=t.ty;angle=t.angle},
    translate(x,y){tx+=x;ty+=y},
    rotate(rad){angle+=rad},
    moveTo(x,y){lastPoint={x,y}},
    lineTo(x,y){
      if(lastPoint)out.segments.push({x1:lastPoint.x,y1:lastPoint.y,x2:x,y2:y});
      lastPoint={x,y}
    },
    arc(x,y){out.dots.push({x,y})},
    fillText(text,x,y){
      out.labels.push({
        text,
        x:tx+Math.cos(angle)*x-Math.sin(angle)*y,
        y:ty+Math.sin(angle)*x+Math.cos(angle)*y,
        angle
      });
    }
  };
  return {width:900,height,style:{},getContext(){return ctx},
          setAttribute(k,v){out.attributes[k]=v},out};
}
globalThis.chart=canvas(340);
globalThis.haircutChart=canvas(280);
const nodes={};
function newNode(tag){
  return {tag,attrs:{},children:[],textContent:'',style:{},
    setAttribute(k,v){this.attrs[k]=String(v)},
    appendChild(child){this.children.push(child);return child}};
}
for(const id of ['chart','haircutChart']){
  const c=globalThis[id];
  c.parentElement=newNode('div');
  nodes[id]=c;
}
globalThis.document={
  createElementNS(ns,tag){return newNode(tag)},
  getElementById(id){return nodes[id]}
};
vm.runInThisContext(source.slice(start));
function parseSvg(c){
  const svg=c.parentElement.children.find(n=>n.tag==='svg');
  if(!svg)throw Error('Missing SVG');
  return {
    attributes:svg.attrs,
    ticks:svg.children.filter(n=>n.attrs.class==='date-tick')
      .map(n=>({...n.attrs})),
    labels:svg.children.filter(n=>n.attrs.class==='date-label')
      .map(n=>({text:n.textContent,...n.attrs})),
    dots:svg.children.filter(n=>n.tag==='circle').map(n=>({...n.attrs}))
  };
}
if(process.argv[1]==='svg'){
  renderAccessibleSvgCharts(input);
  console.log(JSON.stringify({
    forecast:parseSvg(chart),haircut:parseSvg(haircutChart),
    hidden:[chart.style.display,haircutChart.style.display]
  }));
}else{
  drawForecasts(input);drawHaircut(input);
  for(const c of [chart,haircutChart]){c.out.width=c.width;c.out.height=c.height}
  console.log(JSON.stringify({forecast:chart.out,haircut:haircutChart.out}));
}
"""
        result = subprocess.run(
            ["node", "-e", source, mode], cwd=ROOT, input=json.dumps(records),
            text=True, capture_output=True, check=False, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip())

    @staticmethod
    def sample(date, escalation=30, regime=10, fx=84, haircut=38, scored=True):
        record = {"date":date,"metrics":{
            "regional_escalation_90d":escalation,
            "regime_end_12m":regime,
            "fx_crisis_12m":fx,
            "china_oil_credit_haircut":haircut}}
        if scored:
            # Legacy fx_crisis_12m is NOT scored currency_crisis_12m.
            record["forecasts"] = [
                {"event_id":"regional_escalation_90d","p":escalation,"scored":True},
                {"event_id":"regime_end_12m","p":regime,"scored":True},
                {"event_id":"currency_crisis_12m","p":80,"scored":True},
                {"event_id":"external_payments_crisis_12m","p":86,"scored":True}
            ]
        return record

    @staticmethod
    def expected_dates(records):
        scored_ids={"regional_escalation_90d","regime_end_12m",
                    "currency_crisis_12m","external_payments_crisis_12m"}
        scored=[
            r["date"] for r in records if
            {f.get("event_id") for f in r.get("forecasts",[])
             if f.get("scored") is True}==scored_ids
        ]
        return {"forecast":scored,"haircut":[r["date"] for r in records]}

    def assert_dates_complete_inside_box(self, rendered, expected, svg=False):
        for key,dates in expected.items():
            block=rendered[key]
            width=float(block["attributes"]["width"]) if svg else block["width"]
            height=float(block["attributes"]["height"]) if svg else block["height"]
            labels=block["labels"] if svg else [
                q for q in block["labels"] if q["text"] in dates]
            self.assertEqual([q["text"] for q in labels],dates,key)
            if svg:
                self.assertEqual([t["data-date"] for t in block["ticks"]],dates)
                for label,tick in zip(labels,block["ticks"]):
                    self.assertEqual(label["data-date"],tick["data-date"])
                    self.assertTrue(label["transform"].startswith("rotate(45 "))
                    self.assertEqual(label["text-anchor"],"start")
                    x=float(label["x"]); y=float(label["y"])
                    self.assertAlmostEqual(x,float(tick["x1"]),places=6)
                    self.assertGreater(y,float(tick["y2"]))
                    self.assertAlmostEqual(float(tick["x1"]),float(tick["x2"]))
                    self.assertAlmostEqual(float(tick["y2"])-float(tick["y1"]),6)
                    self.assertGreaterEqual(x,0);self.assertGreaterEqual(y,0)
                    self.assertLessEqual(x+70,width)
                    self.assertLessEqual(y+70,height)
            else:
                ticks=[p for p in block["segments"] if
                       abs(p["x2"]-p["x1"])<1e-6 and
                       abs((p["y2"]-p["y1"])-6)<1e-6]
                self.assertEqual(len(ticks),len(dates),key)
                for label,tick in zip(labels,ticks):
                    self.assertAlmostEqual(label["angle"],math.pi/4,places=8)
                    self.assertAlmostEqual(label["x"],tick["x1"],places=6)
                    self.assertGreater(label["y"],tick["y2"])
                    self.assertGreaterEqual(label["x"],0)
                    self.assertGreaterEqual(label["y"],0)
                    self.assertLessEqual(label["x"]+70,width)
                    self.assertLessEqual(label["y"]+70,height)

    def test_actual_history_has_every_date_in_both_renderers(self):
        records=json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))["updates"]
        self.assertEqual([r["date"] for r in records[:4]],
                         ["2026-09-20","2026-09-27","2026-10-04","2026-10-11"])
        expected=self.expected_dates(records)
        for mode in ("canvas","svg"):
            out=self.render(records,mode)
            self.assert_dates_complete_inside_box(out,expected,mode=="svg")
            if mode=="canvas":
                self.assertEqual(len(out["forecast"]["dots"]),4*len(expected["forecast"]))
                self.assertEqual(len(out["haircut"]["dots"]),len(records))
                self.assertIn(expected["forecast"][-1],out["forecast"]["attributes"]["aria-label"])
            else:
                self.assertEqual(out["hidden"],["none","none"])

    def test_legacy_rows_do_not_create_scored_dates(self):
        records=[self.sample("2026-09-20",scored=False),
                 self.sample("2026-10-04"),self.sample("2026-10-11")]
        expected=self.expected_dates(records)
        for mode in ("canvas","svg"):
            out=self.render(records,mode)
            self.assert_dates_complete_inside_box(out,expected,mode=="svg")
            if mode=="canvas":
                self.assertEqual(len(out["forecast"]["dots"]),8)
                self.assertEqual(len(out["haircut"]["dots"]),3)

    def test_scored_currency_not_legacy_fx_composite(self):
        out=self.render([self.sample("2026-10-04",fx=82)])
        label=out["forecast"]["attributes"]["aria-label"]
        self.assertIn("Currency crisis 80%",label)
        self.assertNotIn("Currency crisis 82%",label)
        self.assertIn("Payments crisis 86%",label)

    def test_horizontal_position_follows_calendar_time_not_record_index(self):
        records=[self.sample("2026-01-01"),self.sample("2026-01-02"),
                 self.sample("2026-01-11")]
        for mode in ("canvas","svg"):
            out=self.render(records,mode)
            for key in ("forecast","haircut"):
                if mode=="canvas":
                    xx=[q["x"] for q in out[key]["labels"] if q["text"] in
                        [r["date"] for r in records]]
                else:
                    xx=[float(q["x"]) for q in out[key]["labels"]]
                self.assertAlmostEqual((xx[1]-xx[0])/(xx[2]-xx[0]),0.1,places=7)

    def test_52_week_history_shows_every_date_without_overlap(self):
        begin=dt.date(2026,1,1)
        records=[self.sample((begin+dt.timedelta(days=i*7)).isoformat())
                 for i in range(52)]
        for mode in ("canvas","svg"):
            out=self.render(records,mode)
            self.assert_dates_complete_inside_box(out,self.expected_dates(records),mode=="svg")
            for key in ("forecast","haircut"):
                self.assertGreater(float(out[key]["attributes"]["width"] if
                                         mode=="svg" else out[key]["width"]),900)
                xx=([float(x["x"]) for x in out[key]["labels"]] if mode=="svg"
                    else [x["x"] for x in out[key]["labels"]
                          if x["text"].startswith("2026-")])
                for a,b in zip(xx,xx[1:]):
                    self.assertGreaterEqual(b-a,73.99)

    def test_single_observation_is_centered(self):
        for mode in ("canvas","svg"):
            out=self.render([self.sample("2027-04-01")],mode)
            for key in ("forecast","haircut"):
                dates=out[key]["labels"] if mode=="svg" else [
                    x for x in out[key]["labels"] if x["text"]=="2027-04-01"]
                ]
                self.assertEqual(len(dates),1)
                self.assertAlmostEqual(float(dates[0]["x"]),450)

    def test_rejects_invalid_or_duplicate_dates(self):
        for mode in ("canvas","svg"):
            with self.assertRaisesRegex(AssertionError,"Invalid assessment date"):
                self.render([self.sample("not-a-date")],mode)
            with self.assertRaisesRegex(AssertionError,"Non-increasing assessment date"):
                self.render([self.sample("2026-01-01"),
                             self.sample("2026-01-01")],mode)

    def test_container_scroll_and_chart_heights(self):
        html=INDEX.read_text(encoding="utf-8")
        css=CSS.read_text(encoding="utf-8")
        self.assertEqual(html.count("Horizontal axis: assessment date (YYYY-MM-DD)."),2)
        self.assertIn('id="chart" width="900" height="340"',html)
        self.assertIn('id="haircutChart" width="900" height="280"',html)
        self.assertIn("overflow-x:auto",css)
        self.assertIn("max-width:100%",css)
        self.assertIn(".chartbox svg{display:block;max-width:none}",css)


if __name__ == "__main__":
    unittest.main()
