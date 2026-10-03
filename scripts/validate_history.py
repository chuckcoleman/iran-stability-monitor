#!/usr/bin/env python3
import json,sys,datetime,subprocess,os
P="data/history.json"
def fail(msg): print("VALIDATION ERROR:",msg); sys.exit(1)
def warn(msg): print("VALIDATION WARNING:",msg)
def dt(s):
  try:return datetime.datetime.fromisoformat(s)
  except Exception: fail("invalid ISO timestamp "+str(s))
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
for u in updates:
  if u.get("protocol_version")!="1.0": continue
  for k in ["date","evidence_cutoff","publication_time","forecasts","warning","evidence"]:
    if k not in u: fail(f"{u.get('date')}: missing {k}")
  cutoff,opening,pub=dt(u["evidence_cutoff"]),None,dt(u["publication_time"])
  core=[f for f in u["forecasts"] if f.get("scored") is True]
  expected={"regional_escalation_90d","regime_end_12m","currency_crisis_12m","external_payments_crisis_12m"}
  got={f.get("event_id") for f in core}
  if got!=expected or len(core)!=4: fail(f"{u['date']}: core scored set mismatch")
  for f in core:
    for k in ["forecast_id","created_date","forecast_open","resolution_deadline","p","range","confidence"]:
      if k not in f: fail(f"{u['date']}: {f.get('event_id')} missing {k}")
    if f["forecast_id"]!=f["event_id"]+"_"+u["date"].replace("-",""): fail("forecast_id format mismatch")
    fo=dt(f["forecast_open"]); rd=dt(f["resolution_deadline"])
    opening=fo if opening is None or fo<opening else opening
    if f["event_id"]=="regional_escalation_90d":
      # Protocol v1 executable convention: 90 local calendar days at same local clock time.
      expected_date=(fo.date()+datetime.timedelta(days=90))
      if rd.date()!=expected_date or rd.timetz().replace(tzinfo=None)!=fo.timetz().replace(tzinfo=None): fail("90d deadline convention mismatch")
    else:
      # 12m convention: same local calendar date/time one year later (Feb 29 -> Feb 28).
      try: expected_date=fo.date().replace(year=fo.year+1)
      except ValueError: expected_date=fo.date().replace(year=fo.year+1,day=28)
      if rd.date()!=expected_date or rd.timetz().replace(tzinfo=None)!=fo.timetz().replace(tzinfo=None): fail("12m deadline convention mismatch")
  if opening is not None and not (cutoff<=opening<=pub): fail(f"{u['date']}: require evidence_cutoff <= forecast_open <= publication_time")
  allowed={"normal","watch","warning-level","critical","unknown"}; dirs={"up","flat","down","unknown"}
  if set(u["warning"])!=set(p["warning_transition_rules"]): fail(f"{u['date']}: warning category mismatch")
  for k,v in u["warning"].items():
    if v.get("level") not in allowed: fail(f"{u['date']}: bad warning level {k}")
    if v.get("direction") not in dirs: fail(f"{u['date']}: bad direction {k}")
  evid=set()
  for e in u["evidence"]:
    eid=e.get("id")
    if not eid or eid in evid: fail(f"{u['date']}: missing/duplicate evidence id {eid}")
    evid.add(eid)
    for k in ["source","reliability","evidence_status","direction","impact_magnitude"]:
      if not e.get(k): fail(f"{u['date']}: evidence {eid} missing {k}")
    sp=e.get("source_publication_time")
    if sp:
      if dt(sp)>cutoff: fail(f"{u['date']}: post-cutoff evidence {eid}")
    else: warn(f"{u['date']}: evidence {eid} lacks precise source_publication_time")
  calc=u.get("haircut",{}).get("calculation")
  if calc:
    raw=sum(z[1] for z in calc["components"])
    if raw!=calc["raw_sum"]: fail("haircut raw sum mismatch")
    tri=sum(z[1] for z in calc["components"] if z[0] in {"Physical delivery/blockade","Sanctions/payment channels","Political/secondary-sanctions tail"})
    ded=round(max(0,tri-20)*.2)
    if ded!=calc["overlap_deduction_20pct"] or raw-ded!=calc["adjusted_headline"]: fail("haircut arithmetic mismatch")
  for r in u.get("revision_attribution",[]):
    if "residual_pp" not in r: fail("revision attribution missing residual")
    if round(r["prior_p"]+sum(z["pp"] for z in r.get("contributions",[]))+r["residual_pp"],8)!=round(r["new_p"],8): fail("revision attribution does not reconcile")
# Historical immutability on CI pushes: compare records existing in first parent.
base=os.environ.get("GITHUB_EVENT_BEFORE")
if base and base!="0"*40:
  try:
    old=json.loads(subprocess.check_output(["git","show",base+":"+P],text=True))
    old_by_date={u["date"]:u for u in old.get("updates",[])}
    new_by_date={u["date"]:u for u in updates}
    protected=["date","summary","metrics","regional","political","forecasts","assessment_evidence_cutoff","protocol_version_for_assessment"]
    for date,ou in old_by_date.items():
      if date not in new_by_date: fail("historical update deleted: "+date)
      nu=new_by_date[date]
      for k in protected:
        if k in ou and nu.get(k)!=ou.get(k): fail(f"unauthorized historical mutation {date}:{k}")
  except subprocess.CalledProcessError:
    warn("could not load prior history for immutability comparison")
print("VALIDATION OK")
