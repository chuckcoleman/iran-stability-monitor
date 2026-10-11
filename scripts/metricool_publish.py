#!/usr/bin/env python3
"""Schedule one X announcement ONLY for a verified newly deployed Sunday record.

Fail closed if verification, deduplication or API authorization is unavailable.
Never re-attempt a possibly successful POST automatically.
"""
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ZONE=ZoneInfo("America/New_York")
ROOT=Path(__file__).resolve().parent.parent
REPO=os.getenv("GITHUB_REPOSITORY","chuckcoleman/iran-stability-monitor")
METRICOOL_BASE="https://app.metricool.com/api/v2/scheduler/posts"
BRAND="7254821"
USER="5607453"
CANONICAL="https://iranstabilitymonitor.org"

def assert_true(value,message):
    if not value: raise RuntimeError(message)

def date_key(history):
    date=history["updates"][-1]["date"]
    assert_true(dt.date.fromisoformat(date).weekday()==6,"Not a Sunday assessment")
    now=dt.datetime.now(ZONE)
    assert_true(now.date().isoformat()==date,"Stale assessment: refusing X announcement")
    return date

def draft_text(history):
    latest=history["updates"][-1]
    prior=history["updates"][-2]
    assert_true((dt.date.fromisoformat(latest["date"])-dt.date.fromisoformat(prior["date"])).days==7,
                "Cannot truthfully claim prior-Sunday comparison after missing assessment")
    fs={f["event_id"]:f["p"] for f in latest["forecasts"] if f.get("scored")}
    old={f["event_id"]:f["p"] for f in prior["forecasts"] if f.get("scored")}
    a="regional_escalation_90d";b="regime_end_12m"
    txt=(f"Iran Stability Monitor — {latest['date']}: "
         f"90d escalation {fs[a]}% (prior Sunday {old[a]}%); "
         f"12m regime transition {fs[b]}% (prior {old[b]}%). "
         f"Four core forecasts and evidence updated. {CANONICAL}")
    assert_true(len(txt)<=280,"Over 280 characters")
    assert_true(CANONICAL in txt and ".com" not in txt,"Wrong canonical domain")
    return txt

def api(url,method="GET",data=None,headers=None):
    hdr={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}
    hdr.update(headers or {})
    payload=None if data is None else json.dumps(data).encode()
    if payload is not None: hdr["Content-Type"]="application/json"
    request=urllib.request.Request(url,method=method,data=payload,headers=hdr)
    with urllib.request.urlopen(request,timeout=35) as response:
        body=response.read()
        return json.loads(body) if body else {}

def github(relative,method="GET",data=None):
    token=os.environ["GH_TOKEN"]
    url="https://api.github.com/repos/"+REPO+"/"+relative
    return api(url,method,data,{"Authorization":"Bearer "+token})

def ledger_title(date):
    return "X-AUTOMATION-CLAIM-"+date

def claim(date):
    # This lock is persisted BEFORE a non-idempotent Metricool POST. A failed or
    # uncertain POST never automatically creates a second post on a rerun.
    issues=github("issues?state=all&per_page=100")
    assert_true(isinstance(issues,list),"Cannot inspect X posting ledger")
    if any(i.get("title")==ledger_title(date) for i in issues):
        print("Existing X posting claim; skip to avoid duplicate")
        return False
    github("issues",method="POST",data={
       "title":ledger_title(date),
       "body":"Unattended publication attempt reserved for "+date+
        ". Claim persists even if Metricool POST fails or times out: manually reconcile before retry.",
       "labels":[]})
    return True

def metricool(path,method="GET",payload=None):
    q=urllib.parse.urlencode({"blogId":BRAND,"userId":USER})
    token=os.environ["METRICOOL_API_TOKEN"]
    return api(METRICOOL_BASE+path+("?" if "?" not in path else "&")+q,
               method,payload,{"X-Mc-Auth":token})

def existing_post(date):
    # Include both scheduled and past entries; network-level publishing states vary.
    params=urllib.parse.urlencode({
        "start":date+"T00:00:00","end":date+"T23:59:59",
        "timezone":"America/New_York","extendedRange":"true"})
    response=metricool("?"+params)
    if isinstance(response,list): posts=response
    elif isinstance(response,dict) and isinstance(response.get("data"),list):
        posts=response["data"]
    else:
        raise RuntimeError("Cannot inspect Metricool post calendar; no X posting")
    for post in posts:
        if (isinstance(post,dict) and date in str(post.get("text","")) and
            CANONICAL in str(post.get("text","")) and
            any(isinstance(k,dict) and k.get("network") in ("twitter","x")
                for k in post.get("providers",[]))):
            return True
    return False

def schedule(history):
    if os.getenv("AUTO_X_ENABLED")!="true":
        print("X automation disabled")
        return
    date=date_key(history)
    txt=draft_text(history)
    if existing_post(date):
        print("Metricool already has post for this assessment; no duplicate")
        return
    assert_true(claim(date),"X post previously attempted; manual reconciliation required")
    # Future in New York, never now/past; no historical timestamps asserted.
    future=dt.datetime.now(ZONE)+dt.timedelta(minutes=15)
    future=future.replace(second=0,microsecond=0)
    payload={
        "publicationDate":{"dateTime":future.strftime("%Y-%m-%dT%H:%M:%S"),
                           "timezone":"America/New_York"},
        "text":txt,"providers":[{"network":"twitter"}],
        "twitterData":{"tags":[]},"autoPublish":True,"draft":False,
        "shortener":False
    }
    # No retries on uncertain response from this non-idempotent write.
    result=metricool("",method="POST",payload=payload)
    assert_true(isinstance(result,dict) and bool(result),
                "Metricool did not acknowledge scheduled post; manual reconciliation required")
    print("Metricool X post schedule acknowledged for "+date)

def main():
    history=json.loads((ROOT/"data/history.json").read_text(encoding="utf-8"))
    schedule(history)

if __name__=="__main__":
    main()
