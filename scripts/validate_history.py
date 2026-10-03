#!/usr/bin/env python3
import json,sys,datetime,re
P="data/history.json"
def fail(msg): print("VALIDATION ERROR:",msg); sys.exit(1)
with open(P,encoding="utf-8") as f:d=json.load(f)
if d.get("schema_version",0)<3: fail("schema_version < 3")
p=d.get("protocol",{})
if p.get("version")!="1.0": fail("unexpected protocol version")
updates=d.get("updates",[])
if not updates: fail("no updates")
ids=set()
for u in updates:
  for fc in u.get("forecasts",[]):
    fid=fc.get("forecast_id")
    if fid:
      if fid in ids: fail("duplicate forecast_id "+fid)
      ids.add(fid)
    q=fc.get("p")
    if q is not None and not 0<=q<=100: fail("probability out of range")
    r=fc.get("range")
    if r and not (0<=r[0]<=q<=r[1]<=100): fail("uncertainty range does not contain point")
# Strict v1 checks only for prospective v1 records.
for u in updates:
  if u.get("protocol_version")!="1.0": continue
  req=["date","evidence_cutoff","publication_time","forecasts","warning","evidence"]
  for k in req:
    if k not in u: fail(f"{u.get('date')}: missing {k}")
  core=[f for f in u["forecasts"] if f.get("scored") is True]
  expected={"regional_escalation_90d","regime_end_12m","currency_crisis_12m","external_payments_crisis_12m"}
  got={f.get("event_id") for f in core}
  if got!=expected: fail(f"{u['date']}: core scored set mismatch {got}")
  if len(core)!=4: fail(f"{u['date']}: expected exactly four scored forecasts")
  for f in core:
    for k in ["forecast_id","created_date","forecast_open","resolution_deadline","p","range","confidence"]:
      if k not in f: fail(f"{u['date']}: {f.get('event_id')} missing {k}")
    if f["forecast_id"]!=f["event_id"]+"_"+u["date"].replace("-",""): fail("forecast_id format mismatch")
  allowed={"normal","watch","warning-level","critical","unknown"}
  dirs={"up","flat","down","unknown"}
  if set(u["warning"])!=set(p["warning_transition_rules"]): fail(f"{u['date']}: warning category mismatch")
  for k,v in u["warning"].items():
    if v.get("level") not in allowed: fail(f"{u['date']}: bad warning level {k}")
    if v.get("direction") not in dirs: fail(f"{u['date']}: bad direction {k}")
  evid=set()
  for e in u["evidence"]:
    eid=e.get("id")
    if not eid: fail(f"{u['date']}: evidence missing id")
    if eid in evid: fail(f"{u['date']}: duplicate evidence id {eid}")
    evid.add(eid)
    for k in ["source","reliability","evidence_status","direction","impact_magnitude"]:
      if not e.get(k): fail(f"{u['date']}: evidence {eid} missing {k}")
  h=u.get("haircut",{})
  calc=h.get("calculation")
  if calc:
    raw=sum(z[1] for z in calc["components"])
    if raw!=calc["raw_sum"]: fail("haircut raw sum mismatch")
    tri=sum(z[1] for z in calc["components"] if z[0] in {"Physical delivery/blockade","Sanctions/payment channels","Political/secondary-sanctions tail"})
    ded=round(max(0,tri-20)*.2)
    if ded!=calc["overlap_deduction_20pct"]: fail("haircut overlap mismatch")
    if raw-ded!=calc["adjusted_headline"]: fail("haircut adjusted headline mismatch")
  for r in u.get("revision_attribution",[]):
    if round(r["prior_p"]+sum(z["pp"] for z in r.get("contributions",[]))+r.get("residual_pp",0),8)!=round(r["new_p"],8):
      fail("revision attribution does not reconcile "+r.get("forecast_id",""))
print("VALIDATION OK")
