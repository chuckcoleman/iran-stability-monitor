#!/usr/bin/env python3
"""Two-stage append-only Protocol-v1 research and prospective assessment generator."""
import copy
import datetime as dt
import json
import os
import ipaddress
import re
from html.parser import HTMLParser
from pathlib import Path
import sys
import urllib.request
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent.parent
EST=ZoneInfo("America/New_York")
IDS=("regional_escalation_90d","regime_end_12m","currency_crisis_12m","external_payments_crisis_12m")
CAPS=(("Physical delivery/blockade",25),("Sanctions/payment channels",15),
      ("Sovereign/counterparty",10),("Oil-price/basis",8),
      ("Illiquidity/enforcement",8),("Political/secondary-sanctions tail",8))

def check(ok,why):
    if not ok: raise ValueError(why)

def clock():
    return dt.datetime.now(dt.timezone.utc).astimezone(EST)

def deadline(opened,key):
    if key==IDS[0]:
        day=opened.date()+dt.timedelta(days=90)
    else:
        try: day=opened.date().replace(year=opened.year+1)
        except ValueError: day=opened.date().replace(year=opened.year+1,day=28)
    return dt.datetime.combine(day,opened.time().replace(tzinfo=None),EST).isoformat(timespec="seconds")

def llm(prompt,search):
    payload={"model":os.getenv("IRAN_FORECAST_MODEL","gpt-5.5"),"input":prompt,
             "store":False,"max_output_tokens":14000,
             "text":{"format":{"type":"json_object"}}}
    if search:
        payload.update({"tools":[{"type":"web_search","external_web_access":True}],
                        "tool_choice":"required","include":["web_search_call.action.sources"]})
    req=urllib.request.Request("https://api.openai.com/v1/responses",
       data=json.dumps(payload).encode(),method="POST",
       headers={"Content-Type":"application/json","Authorization":"Bearer "+os.environ["OPENAI_API_KEY"]})
    with urllib.request.urlopen(req,timeout=500) as response: raw=json.load(response)
    check(raw.get("status")=="completed","OpenAI response incomplete")
    output=raw.get("output",[])
    check(not search or any(x.get("type")=="web_search_call" for x in output),
          "Search stage did not use web search")
    messages=[x for x in output if x.get("type")=="message"]
    texts=[p.get("text","") for x in messages for p in x.get("content",[]) if p.get("type")=="output_text"]
    check(bool(texts),"Empty model response")
    txt="\n".join(texts).strip()
    if txt.startswith(chr(96)*3):
        txt="\n".join(txt.splitlines()[1:-1]).strip()
    obj=json.loads(txt)
    check(isinstance(obj,dict),"Expected JSON object")
    citations=set()
    for x in messages:
        for p in x.get("content",[]):
            for a in p.get("annotations",[]):
                if a.get("type")=="url_citation": citations.add(a.get("url",""))
    for x in output:
        if x.get("type")=="web_search_call":
            for s in (x.get("action") or {}).get("sources",[]):
                if isinstance(s,dict) and s.get("url"): citations.add(s["url"])
    return obj,citations

def urlkey(url):
    try:
        u=urlsplit(url)
        if u.scheme!="https" or not u.hostname or "." not in u.hostname or u.username or u.password: return None
        try:
            ipaddress.ip_address(u.hostname)
            return None  # Reject literal IP targets, including private/loopback addresses.
        except ValueError:
            pass
        if u.hostname.endswith((".localhost",".local",".internal")): return None
        return u.hostname.lower()+u.path.rstrip("/")
    except (ValueError,TypeError): return None

class _PublicationMetadata(HTMLParser):
    def __init__(self):
        super().__init__();self.times=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()!="meta":return
        a=dict(attrs)
        key=(a.get("property") or a.get("name") or "").lower()
        if key in ("article:published_time","datepublished","pubdate","publication_date"):
            if a.get("content"):self.times.append(a["content"])

def article_publication_time(url):
    """Use direct article metadata only; lack of precise time is nonfatal."""
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"IranStabilityMonitor-evidence/1.0"})
        with urllib.request.urlopen(req,timeout=10) as response:
            html=response.read(180000).decode("utf-8",errors="replace")
        parser=_PublicationMetadata();parser.feed(html)
        matches=parser.times
        if not matches:
            matches=re.findall(r'["\x27]datePublished["\x27]\s*:\s*["\x27]([^"\x27]+)',html)
        for raw in matches:
            try:
                stamp=dt.datetime.fromisoformat(raw.strip().replace("Z","+00:00"))
                if stamp.tzinfo is not None and stamp.utcoffset() is not None:
                    return stamp
            except ValueError:pass
    except (OSError,ValueError,UnicodeError):
        pass
    return None

def freeze_evidence(obj,citations,previous,date,cutoff):
    new=obj.get("evidence")
    check(isinstance(new,list) and 6<=len(new)<=30,"Require 6-30 evidence items")
    cited={urlkey(u) for u in citations}
    check(bool(cited-{None}),"Research source citations missing")
    seen=set(); out=[]; publishers=set(); directions=set()
    archived={e["id"]:e for e in previous.get("evidence",[])}
    for i,item in enumerate(new,1):
        check(isinstance(item,dict),"Bad evidence item")
        carried=item.get("evidence_status")=="carried_forward"
        if carried:
            original=archived.get(item.get("id"))
            check(original is not None,"Unrecognized carried-forward ID")
            entry=copy.deepcopy(original);entry["evidence_status"]="carried_forward"
        else:
            u=item.get("source")
            check(urlkey(u) in cited and urlkey(u) is not None,
                  "Source not verified in web-search citations: "+str(u))
            for k in ("category","observation","source_title","publisher","event_date"):
                check(isinstance(item.get(k),str) and bool(item[k].strip()),"Evidence field missing: "+k)
            d=dt.date.fromisoformat(item["event_date"])
            check(d<=cutoff.date(),"Event date after cutoff")
            check(item.get("reliability") in ("High","Medium-high","Medium","Low"),"Invalid reliability")
            check(item.get("direction") in ("raises","lowers","ambiguous"),"Invalid direction")
            check(item.get("impact_magnitude") in ("minor","moderate","major"),"Invalid impact")
            published_at=article_publication_time(u)
            if published_at is not None:
                check(published_at<=cutoff,"Directly verified post-cutoff publication; exclude source")
            entry={"id":f"E-{date.replace('-','')}-{i:02d}","date":date,
                   "event_date":item["event_date"],"category":item["category"],
                   "observation":item["observation"],"source":u,"source_title":item["source_title"],
                   "publisher":item["publisher"],
                   "source_publication_time":published_at.isoformat() if published_at else None,
                   "source_publication_status":"verified article metadata" if published_at else "unknown precise time; source independently cited",
                   "reliability":item["reliability"],"affects":item.get("affects",[]),
                   "evidence_status":"new","impact_magnitude":item["impact_magnitude"],
                   "direction":item["direction"]}
        check(entry["id"] not in seen,"Duplicate evidence identifier")
        seen.add(entry["id"])
        if entry.get("source_publication_time"):
            check(dt.datetime.fromisoformat(entry["source_publication_time"])<=cutoff,
                  "Post-cutoff evidence")
        out.append(entry);publishers.add(entry["publisher"]);directions.add(entry["direction"])
    check(len(publishers)>=3,"Require three source publishers")
    check({"raises","lowers","ambiguous"}.issubset(directions),"Require raising, lowering, ambiguous evidence")
    check(sum(e["evidence_status"]=="new" for e in out)>=4,"Require four new source observations")
    return out

def haircut(values):
    check(isinstance(values,dict),"Missing six haircut inputs")
    comps=[]
    for key,cap in CAPS:
        p=values.get(key)
        check(type(p) in (float,int) and 0<=p<=cap,"Bad haircut component "+key)
        comps.append([key,p,cap])
    raw=sum(p for _,p,_ in comps)
    subtotal=sum(p for k,p,_ in comps if k in
        ("Physical delivery/blockade","Sanctions/payment channels","Political/secondary-sanctions tail"))
    def adjusted(rate):return raw-round(max(0,subtotal-20)*rate)
    return {"components":comps,"raw_sum":raw,"overlap_deduction_20pct":raw-adjusted(.2),
            "adjusted_headline":adjusted(.2),
            "sensitivity":{"overlap_0pct":adjusted(0),"overlap_20pct":adjusted(.2),
                           "overlap_40pct":adjusted(.4)}}

def assemble(history,assessment,evidence,cutoff,opened,issued):
    date=opened.date().isoformat()
    prev=history["updates"][-1]
    check(date>prev["date"],"Already recorded Sunday date")
    u=copy.deepcopy(prev);u["date"]=date
    for key in ("summary","what_changed","stabilizer","next_threshold","limitations"):
        val=assessment.get(key)
        check(isinstance(val,str) and len(val.strip())>=40,"Missing analytical narrative: "+key)
        u[key]=val
    pf=assessment.get("forecasts")
    check(isinstance(pf,list) and len(pf)==4,"Exactly four forecasts required")
    byid={f["event_id"]:f for f in pf}
    check(set(byid)==set(IDS),"Wrong/repeated core event")
    rules={x["id"]:x for x in history["protocol"]["core_scored_set"]}
    u["forecasts"]=[]
    for key in IDS:
        f=byid[key];p=f.get("p");rng=f.get("range")
        check(type(p) in (int,float) and 0<=p<=100,"Invalid point forecast")
        check(isinstance(rng,list) and len(rng)==2 and
              all(type(n) in (int,float) and 0<=n<=100 for n in rng)
              and rng[0]<=p<=rng[1],"Invalid reasonable-analyst range")
        check(f.get("confidence") in ("Low","Medium","Medium-high","High"),"Invalid confidence")
        u["forecasts"].append({"label":rules[key]["event"],"p":p,
            "horizon":"within 90 days" if key==IDS[0] else "within 12 months",
            "confidence":f["confidence"],"range":rng,
            "event_definition":rules[key]["resolution"],
            "raise":f.get("raise","Further deterioration in the event drivers."),
            "lower":f.get("lower","Confirmed stabilization of core drivers."),
            "scored":True,"created_date":date,"provenance":"Prospective Protocol v1.0",
            "forecast_id":f"{key}_{date.replace('-','')}","event_id":key,
            "forecast_open":opened.isoformat(timespec="seconds"),
            "resolution_deadline":deadline(opened,key)})
        u["metrics"][key]=p
    prior={f["event_id"]:f["p"] for f in prev["forecasts"] if f.get("scored")}
    rows=assessment.get("revision_attribution")
    check(isinstance(rows,list) and len(rows)==4,"Exactly four attribution records")
    u["revision_attribution"]=[]
    for row in rows:
        key=row.get("event_id")
        check(key in prior and key not in [r["event_id"] for r in u["revision_attribution"]],
              "Duplicate or invalid revision key")
        contrib=row.get("contributions")
        check(isinstance(contrib,list) and bool(contrib),"Empty revision attribution")
        check(all(isinstance(x.get("label"),str) and x["label"].strip() and
                  type(x.get("pp")) in (int,float) and abs(x["pp"])<=30 for x in contrib),
              "Bad signed attribution")
        point=byid[key]["p"];residual=round(point-prior[key]-sum(x["pp"] for x in contrib),6)
        check(abs(residual)<=5,"Unexplained revision residual exceeds 5pp")
        if prior[key]==point:
            check(any(x["pp"]<0 for x in contrib) and any(x["pp"]>0 for x in contrib),
                  "Zero change must show offsetting evidence")
        u["revision_attribution"].append({"event_id":key,"prior_p":prior[key],
          "new_p":point,"contributions":contrib,"residual_pp":residual})
    wc=assessment.get("warning")
    check(isinstance(wc,dict) and set(wc)==set(history["protocol"]["warning_transition_rules"]),
          "Must preserve nine warning categories")
    for key,row in wc.items():
        check(row.get("level") in ("normal","watch","warning-level","critical","unknown") and
              row.get("direction") in ("up","flat","down","unknown") and
              isinstance(row.get("text"),str) and len(row["text"])>=25,"Bad warning "+key)
        for attr in ("level","direction","text"):u["warning"][key][attr]=row[attr]
        u["warning"][key]["coverage"]=row.get("coverage","Medium")
        check(not(row.get("coverage")=="Low" and row.get("level")=="normal"),
              "Unobserved risk cannot be classified as affirmatively normal")
    conditions=assessment.get("conditions")
    check(isinstance(conditions,dict) and all(
         isinstance(conditions.get(k),str) and conditions[k].strip()
         for k in ("hormuz","energy","elite","coercion")),"Missing conditions")
    u["conditions"]=conditions
    h=haircut(assessment.get("haircut_components"))
    u["haircut"]["calculation"]=h
    u["haircut"]["method"]["components"]=h["components"]
    u["haircut"]["method"]["rule"]=history["protocol"]["haircut_protocol"]["dependence_rule"]
    u["haircut"]["note"]="Risk-equivalent model, not an observed transaction price."
    u["haircut"]["range"]=assessment.get("haircut_range",[max(0,h["adjusted_headline"]-15),
                                                       min(100,h["adjusted_headline"]+15)])
    check(u["haircut"]["range"][0]<=h["adjusted_headline"]<=u["haircut"]["range"][1],
          "Haircut outside judgmental range")
    u["metrics"]["china_oil_credit_haircut"]=h["adjusted_headline"]
    diag=assessment.get("houthi")
    check(isinstance(diag,dict),"Houthi diagnostic missing")
    for key in ("material_support_12m","technical_financial_support_12m",
                "independent_capability_12m","headline_support_12m"):
        check(type(diag.get(key)) in (int,float) and 0<=diag[key]<=100,
              "Missing/out-of-range Houthi probability "+key)
    for key in ("material_support_12m","technical_financial_support_12m",
                "independent_capability_12m"):u["houthi"][key]=diag[key]
    u["metrics"]["houthi_support_12m"]=diag["headline_support_12m"]
    u["houthi"]["diagnostic_note"]="Unscored: local capability alone does not establish continuing Iranian material, technical or financial support."
    u["metrics"]["hormuz"]=assessment.get("hormuz_status",prev["metrics"]["hormuz"])
    u["metrics"]["energy_stress"]=assessment.get("energy_stress",prev["metrics"]["energy_stress"])
    u["metrics"]["fx_crisis_12m"]=prev["metrics"].get("fx_crisis_12m") # legacy comparator
    status=assessment.get("status")
    check(isinstance(status,dict) and set(status)==set(u["status"]),"Dashboard statuses incomplete")
    check(all(x in ("green","amber","red") for x in status.values()),"Bad dashboard status")
    u["status"]=status
    region=byid[IDS[0]]["p"];regime=byid[IDS[1]]["p"]
    deesc=round((100-region)*.3)
    u["regional"]=[{"name":"Negotiated de-escalation / partial reopening","p":deesc},
      {"name":"Prolonged militarized standoff","p":100-region-deesc},
      {"name":"Wider regional escalation","p":region}]
    rem=100-regime;a=round(rem*.65);b=round(rem*.18)
    u["political"]=[{"name":"Hardline/security continuity","p":a},
      {"name":"Continuity + external stabilization","p":b},
      {"name":"Major internal reconfiguration","p":rem-a-b},
      {"name":"Regime-ending transition","p":regime}]
    u["evidence"]=evidence
    u["news"]=[{"date":e["date"],"event_date":e["event_date"],
                "type":e["category"],"title":e["source_title"],"impact":e["observation"],
                "url":e["source"],"revision_type":"New event","revision_date":date}
               for e in evidence if e["evidence_status"]=="new"]
    u["evidence_cutoff"]=cutoff.isoformat(timespec="seconds")
    u["assessment_evidence_cutoff"]=u["evidence_cutoff"]
    u["publication_time"]=issued.isoformat(timespec="seconds")
    following=dt.datetime.combine(opened.date()+dt.timedelta(days=7),dt.time(9),EST)
    u["next_scheduled_update"]=following.isoformat(timespec="seconds")
    u["protocol_version"]="1.0";u["protocol_version_for_assessment"]="1.0"
    u["methodology_revision_date"]=date
    u["methodology_notes"]=[
      "Protocol v1 remains frozen; the source cutoff preceded independent forecast elicitation.",
      "publication_time denotes the observed assessment issuance before commit; validated web deployment is separately checked."]
    u["revision_attribution_status"]="Prospective Protocol-v1 signed judgment audit; not causal estimates"
    u["corrections"]=[]
    if opened.day<=7:
        hv=assessment.get("hanke_hyperinflation")
        check(isinstance(hv,dict) and isinstance(hv.get("probabilities"),dict),
              "First-Sunday monthly Hanke analysis required")
        vals=hv["probabilities"]
        check(all(type(vals.get(k)) in (int,float) and 0<=vals[k]<=100 for k in ("m3","m6","m12")),
              "Missing monthly Hanke diagnostic probabilities")
        u["hanke_hyperinflation"]={
          "analysis_date":date,"latest_recoverable_annual_inflation_pct":hv.get("annual_inflation_pct"),
          "source_publication_time_status":hv.get("publication_time_status","unknown"),
          "assessment":hv.get("assessment","No new verifiable Hanke observation"),
          "hyperinflation_probability":vals,"status":"diagnostic, unscored"}
    else:
        u["hanke_hyperinflation"]["status"]="Prior first-Sunday diagnostic carried forward; unscored"
    return u

RESEARCH="""Today (Eastern) is {date}. Search the LIVE web for the newest publicly available Iran
stability reporting. Gather a balanced, evidence-based ledger from Reuters, AP, primary
sources, other independent journalists and experts. Include Hormuz, sanctions,
FX, external settlement, food/medicine, energy, protests, elite/coercive reliability,
China and Russia support, China oil credit, Houthi resupply separately from local
capability, military scenarios, and Hanke inflation when applicable.
Prior evidence for persistent carried-forward IDs: {prior}.
Return ONLY a JSON object with evidence array of 8-22 items.
Each item: event_date YYYY-MM-DD, category, observation, source full HTTPS URL,
source_title, publisher, reliability (High/Medium-high/Medium/Low),
affects (array), evidence_status new or carried_forward (with old id if carried),
impact_magnitude minor/moderate/major, direction raises/lowers/ambiguous.
Do NOT invent sources or precise publication times. Cite every new URL using the search tool.
No forecasts in this first stage; include new raising/lowering/ambiguous evidence."""

ASSESS="""Only use the following CLOSED evidence set. No additional web search or new
information. Elicit exactly four independent prospective probabilities under frozen
Protocol v1.0, retaining exact event definitions, warning rules and Houthi rule.
Output JSON ONLY with:
summary, what_changed, stabilizer, next_threshold, limitations (>=40 chars);
forecasts array exactly four, each with event_id,p,range [lower,upper]
(10th and 90th percentiles of informed analysts),confidence
(Low/Medium/Medium-high/High), raise, lower;
revision_attribution exactly four items event_id,contributions array
[{{"label":"...","pp":number}}], including positive and negative offset for zero net;
warning EXACT nine frozen categories each with level
(normal/watch/warning-level/critical/unknown), direction (up/flat/down/unknown),
coverage (Low/Medium/Medium-high/High), text >=25 chars;
conditions object (hormuz,energy,elite,coercion);
haircut_components six named capped point adjustments; haircut_range [low,high];
houthi four probabilities (headline_support_12m,material_support_12m,
technical_financial_support_12m,independent_capability_12m);
status map regional,regime,fx,hormuz,energy,houthi,china (green/amber/red);
hormuz_status and energy_stress. For first Sunday of month, add hanke_hyperinflation
with probabilities m3,m6,m12, annual_inflation_pct (or null),
publication_time_status and assessment.
Distinguish no proof of frozen resolution event from warning conditions.
Use October 4 and subsequent prior PROSPECTIVE core percentages, not retrospective comparators.
Judgmental contributions must reconcile exactly or within 5 pp residual.
Frozen protocol: {protocol}
Prior prospective forecasts: {prior}
Closed evidence: {evidence}"""

def produce(history,researcher=llm,assessor=llm,now=clock):
    baseline=json.dumps(history,sort_keys=True,ensure_ascii=False)
    today=now().date().isoformat()
    check(history["updates"][-1]["date"]<today,"Sunday assessment already exists")
    previous=history["updates"][-1]
    result,sources=researcher(RESEARCH.format(date=today,prior=json.dumps(previous.get("evidence",[]))),True)
    research_complete=now()
    evidence=freeze_evidence(result,sources,previous,today,research_complete)
    cutoff=now() # actual closure AFTER checking primary-source publication metadata
    input=ASSESS.format(protocol=json.dumps(history["protocol"]),prior=json.dumps(
       [{"event_id":f["event_id"],"p":f["p"]} for f in previous["forecasts"] if f.get("scored")]),
       evidence=json.dumps(evidence))
    analysis,_=assessor(input,False)
    opened=now() # forecast formation completes here; same open timestamp for four scored events
    issued=now()
    check(cutoff<=opened<=issued and opened.date().isoformat()==today,"Timestamp ordering/date failed")
    u=assemble(history,analysis,evidence,cutoff,opened,issued)
    out=copy.deepcopy(history);out["updates"].append(u)
    check(json.dumps(history,sort_keys=True,ensure_ascii=False)==baseline,"Historical data changed in memory")
    return out

def main():
    if len(sys.argv)!=2 or sys.argv[1]!="prepare":
        raise SystemExit("usage: assessment_pipeline.py prepare")
    from jsonschema import Draft202012Validator
    from validate_history import validate_history
    path=ROOT/"data/history.json"
    source=path.read_bytes()
    original=json.loads(source)
    candidate=produce(original)
    schema=json.loads((ROOT/"schema/history.schema.json").read_text())
    Draft202012Validator(schema).validate(candidate)
    validate_history(candidate,original)
    # Write only after independent schema + Protocol-v1 + immutability checks.
    path.write_text(json.dumps(candidate,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("Prepared one append-only validated Protocol-v1 record: "+candidate["updates"][-1]["date"])

if __name__=="__main__":
    main()
