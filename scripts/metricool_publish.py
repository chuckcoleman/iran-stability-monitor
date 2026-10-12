#!/usr/bin/env python3
"""One at-most-once X scheduling attempt after fresh, SHA-bound public verification.

Scheduled calendar and published Twitter JSON are separate read-only sources. An atomic Git ref
claims the assessment before the non-idempotent POST. Uncertain delivery never
causes an automatic retry. Authentication and response-shape failures stop posting.
"""
import datetime as dt
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
from zoneinfo import ZoneInfo
from verify_publication import github, request_bytes, verify_all

ROOT = Path(__file__).resolve().parent.parent
ZONE = ZoneInfo("America/New_York")
BASE = "https://app.metricool.com/api"
BRAND = "7254821"
USER = "5607453"
CANONICAL = "https://iranstabilitymonitor.org"


def check(value, message):
    if not value:
        raise RuntimeError(message)


def metricool(path, method="GET", payload=None, params=None, csv_response=False):
    check(path.startswith("/") and "?" not in path, "Invalid Metricool endpoint")
    query = {"blogId": BRAND, "userId": USER, **(params or {})}
    headers = {"X-Mc-Auth": os.environ["METRICOOL_API_TOKEN"],
               "Accept": "text/csv" if csv_response else "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    raw = request_bytes(BASE + path + "?" + urllib.parse.urlencode(query), headers,
                        None if payload is None else json.dumps(payload).encode(), method)
    text = raw.decode("utf-8-sig")
    return text if csv_response else json.loads(text)


def list_data(response):
    if isinstance(response, list):
        data = response
    else:
        check(isinstance(response, dict) and isinstance(response.get("data"), list),
              "Unrecognized Metricool list response")
        data = response["data"]
        paging = response.get("page")
        # This endpoint advertises a bounded calendar, not a documented cursor API.
        # Never call a partial result complete: unfamiliar pagination fails closed.
        if paging:
            check(isinstance(paging, dict), "Unrecognized pagination")
            check(not any(paging.get(k) for k in ("next", "nextPage", "nextCursor", "hasMore")),
                  "Metricool returned an incomplete page")
            for k in ("total", "totalElements", "totalCount"):
                if k in paging:
                    check(type(paging[k]) is int and paging[k] <= len(data), "Partial Metricool list")
            known = {"next", "nextPage", "nextCursor", "hasMore", "total", "totalElements",
                     "totalCount", "size", "page", "pageSize", "currentPage", "totalPages"}
            check(set(paging).issubset(known), "Undocumented Metricool pagination")
            check(paging.get("totalPages", 1) <= 1, "More Metricool pages require reconciliation")
    check(all(isinstance(x, dict) for x in data), "Malformed list item")
    return data


def brand_identity_audit(profile):
    """Only emit structural, non-secret indicators for one known brand.

    Never print raw user-profile fields, connected social account metadata,
    tokens, or untrusted API error bodies.
    """
    networks = profile.get("networksData")
    twitter = networks.get("twitterData") if isinstance(networks, dict) else None
    keys = ("username", "screenName")
    fields = [k for k in keys if isinstance(twitter, dict) and k in twitter]
    candidate = (twitter.get("username") or twitter.get("screenName")
                 if isinstance(twitter, dict) else twitter)
    return {
        "brand_id_matches": str(profile.get("id")) == BRAND,
        "timezone_matches": profile.get("timezone") == "America/New_York",
        "account_id_matches": str(profile.get("userId", USER)) == USER,
        "networksData_type": type(networks).__name__,
        "twitterData_type": type(twitter).__name__,
        "twitter_public_username_keys": fields,
        "twitter_username_present": isinstance(candidate, str) and bool(candidate),
        "twitter_username_matches_expected": (
            isinstance(candidate, str) and
            candidate.lstrip("@").lower() == "iranstabilitymo"),
    }


def check_brand(healthcheck=False):
    # v2 brands returns BrandLite.networksData.twitterData per official Swagger.
    # Legacy /admin/simpleProfiles (PublicBlog) omits networksData entirely.
    brands = list_data(metricool("/v2/settings/brands"))
    found = [b for b in brands if str(b.get("id")) == BRAND]
    check(len(found) == 1, "Iran Stability Monitor brand not accessible")
    b = found[0]
    if healthcheck:
        print("Metricool brand schema (non-secret indicators only): " +
              json.dumps(brand_identity_audit(b), sort_keys=True), flush=True)
    check(b.get("timezone") == "America/New_York", "Brand timezone mismatch")
    networks = b.get("networksData") or {}
    check(isinstance(networks, dict), "Malformed Metricool network metadata")
    identity = networks.get("twitterData")
    if isinstance(identity, dict):
        identity = identity.get("username") or identity.get("screenName")
    check(isinstance(identity, str) and identity.lstrip("@").lower() == "iranstabilitymo",
          "Unexpected or missing connected X identity")
    check(str(b.get("userId", USER)) == USER, "Metricool user identity mismatch")
    return b


def metricool_local_datetime(value):
    """Metricool date query fields are local ISO seconds; timezone is separate.

    ISO offsets or trailing Z cause Metricool HTTP 400. Do not lose the
    intended instant: convert into the brand's configured IANA timezone first.
    """
    check(isinstance(value, dt.datetime) and
          value.tzinfo is not None and value.utcoffset() is not None,
          "Metricool date must be timezone aware")
    return value.astimezone(ZONE).strftime("%Y-%m-%dT%H:%M:%S")


def scheduled_posts(day, now=None):
    date = dt.date.fromisoformat(day)
    start = dt.datetime.combine(date - dt.timedelta(days=1), dt.time.min, ZONE)
    end = dt.datetime.combine(date + dt.timedelta(days=8), dt.time.min, ZONE)
    return list_data(metricool("/v2/scheduler/posts", params={
        "start": metricool_local_datetime(start),
        "end": metricool_local_datetime(end),
        "timezone": "America/New_York", "extendedRange": "true"}))


def published_posts(day, now=None):
    """Query documented JSON TwitterPost records, NOT an unrelated CSV export.

    The endpoint is scoped to the verified brand, but reject inconsistent
    brand IDs and X handles in returned records rather than silently accepting
    another account's posts. Never treat unfamiliar or paginated data as empty.
    """
    date = dt.date.fromisoformat(day)
    start = dt.datetime.combine(date - dt.timedelta(days=1), dt.time.min, ZONE)
    current = now or dt.datetime.now(ZONE)
    check(current.tzinfo is not None and current.utcoffset() is not None,
          "Metricool published-post end must be timezone aware")
    check(current >= start, "Published-post interval is reversed")
    result = list_data(metricool("/v2/analytics/posts/twitter", params={
        "from": metricool_local_datetime(start),
        "to": metricool_local_datetime(current),
        "timezone": "America/New_York"}))
    rows = []
    for item in result:
        check(isinstance(item.get("text"), str), "Published TwitterPost missing text")
        if "blogId" in item:
            check(str(item["blogId"]) == BRAND, "Published TwitterPost belongs to another brand")
        if "username" in item:
            check(isinstance(item["username"], str) and
                  item["username"].lstrip("@").lower() == "iranstabilitymo",
                  "Published TwitterPost belongs to another X account")
        rows.append({"text": item["text"], "providers": [{"network": "twitter"}]})
    return rows


def is_x(post):
    return any(isinstance(p, dict) and p.get("network") in ("twitter", "x")
               for p in post.get("providers", []))


def matches_assessment(post, day):
    if not is_x(post):
        return False
    date = dt.date.fromisoformat(day)
    text = str(post.get("text", "")).lower()
    variants = [day, f"{date.month}/{date.day}", f"{date.month:02}/{date.day:02}",
                f"{date.strftime('%b').lower()} {date.day}",
                f"{date.strftime('%B').lower()} {date.day}"]
    # The date is mandatory in our posts; ignore shortened URLs when checking old posts.
    return any(v in text for v in variants) and any(
        clue in text for clue in ("iran", "escalation", "regime", "assessment"))


def draft_text(history):
    prior, latest = history["updates"][-2:]
    current = {f["event_id"]: f["p"] for f in latest["forecasts"] if f.get("scored")}
    old = {f["event_id"]: f["p"] for f in prior["forecasts"] if f.get("scored")}
    a, b = "regional_escalation_90d", "regime_end_12m"
    brief = latest.get("social_summary")
    check(isinstance(brief, str) and 5 <= len(brief) <= 65, "Missing reviewed short change summary")
    check(not any(c in brief for c in "<>\n\r") and "http" not in brief, "Invalid social summary")
    text = (f"Iran {latest['date']}: {brief} "
            f"90d escalation {current[a]:g}% (was {old[a]:g}%); "
            f"12m regime transition {current[b]:g}% (was {old[b]:g}%). "
            f"Prior: {prior['date']}. {CANONICAL}")
    # Restrict to Latin text so Python length conservatively bounds X weighted length.
    check(all(ord(c) < 0x2000 for c in text), "Unreviewed Unicode in social post")
    check(len(text) <= 280, "Post exceeds 280 characters")
    return text


def existing_claim(day):
    ref = "git/ref/tags/x-announcement-" + day
    try:
        github(ref)
        return True
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    # Honor any legacy issue-based claims, including closed ones and later pages.
    for page in range(1, 101):
        issues = github(f"issues?state=all&per_page=100&page={page}")
        check(isinstance(issues, list), "Cannot inspect old X claim ledger")
        if any(i.get("title") == "X-AUTOMATION-CLAIM-" + day for i in issues):
            return True
        if len(issues) < 100:
            return False
    raise RuntimeError("Posting claim ledger listing incomplete")


def claim(day, sha):
    # Git ref creation is atomic: two concurrent callers cannot both reserve a date.
    try:
        result = github("git/refs", "POST", {"ref": "refs/tags/x-announcement-" + day, "sha": sha})
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            found = github("git/ref/tags/x-announcement-" + day)
            check(found.get("ref") == "refs/tags/x-announcement-" + day, "Claim creation failed")
            return False
        raise
    check(result.get("ref") == "refs/tags/x-announcement-" + day and
          result.get("object", {}).get("sha") == sha, "Claim was not acknowledged")
    return True


def next_slot(posts, now=None):
    current = now or dt.datetime.now(ZONE)
    future = (current + dt.timedelta(minutes=2)).replace(second=0, microsecond=0)
    occupied = set()
    for p in posts:
        if not is_x(p):
            continue
        value = p.get("publicationDate", {})
        check(isinstance(value, dict) and value.get("dateTime"), "Unknown scheduled X time")
        stamp = dt.datetime.fromisoformat(value["dateTime"])
        if stamp.tzinfo is None:
            check(value.get("timezone"), "Scheduled post lacks timezone")
            stamp = stamp.replace(tzinfo=ZoneInfo(value["timezone"]))
        occupied.add(stamp.astimezone(ZONE).replace(second=0, microsecond=0))
    while future in occupied:
        future += dt.timedelta(minutes=1)
    check(future > current and future - current <= dt.timedelta(hours=1), "No near-term future slot")
    return future


def schedule(history, verifier=None, now=None):
    if os.getenv("AUTO_X_ENABLED") != "true":
        print("X automation disabled")
        return {"status": "disabled"}
    verifier = verifier or verify_all
    receipt = verifier()  # Never trust a marker without checking actual run and site.
    check(receipt and receipt["assessment_date"] == history["updates"][-1]["date"],
          "Not a newly verified assessment")
    import hashlib
    raw = (ROOT / "data/history.json").read_bytes()
    check(receipt["history_sha256"] == hashlib.sha256(raw).hexdigest()
          and json.loads(raw) == history, "History differs from verified publication")
    day = receipt["assessment_date"]
    if existing_claim(day):
        return {"status": "previously_claimed", "date": day}
    check_brand()
    planned = scheduled_posts(day)
    past = published_posts(day, now)
    if any(matches_assessment(p, day) for p in planned + past):
        return {"status": "already_scheduled_or_published", "date": day}
    text = draft_text(history)
    # Recheck immediately before reservation; a newer assessment blocks the announcement.
    second = verifier()
    check(second and second["head_sha"] == receipt["head_sha"] and
          second["history_sha256"] == receipt["history_sha256"], "Publication changed during checks")
    future = next_slot(planned, now)
    if not claim(day, receipt["head_sha"]):
        return {"status": "concurrent_claim", "date": day}
    payload = {"publicationDate": {"dateTime": future.strftime("%Y-%m-%dT%H:%M:%S"),
                                   "timezone": "America/New_York"},
               "text": text, "providers": [{"network": "twitter"}], "twitterData": {"tags": []},
               "autoPublish": True, "draft": False, "shortener": False}
    # Intentionally one call, no retry. The permanent claim survives any exception.
    response = metricool("/v2/scheduler/posts", "POST", payload)
    data = response.get("data") if isinstance(response, dict) else None
    check(isinstance(data, dict) and isinstance(data.get("id"), (int, str)) and data["id"],
          "No scheduled-post ID acknowledged; reconcile manually, never retry blindly")
    post_id = str(data["id"])
    check(re.fullmatch(r"[A-Za-z0-9_-]+", post_id), "Invalid scheduled-post ID")
    readback = metricool("/v2/scheduler/posts/" + post_id)
    post = readback.get("data") if isinstance(readback, dict) else None
    check(isinstance(post, dict) and str(post.get("id")) == post_id and post.get("text") == text
          and post.get("autoPublish") is True and post.get("draft") is False and is_x(post)
          and post.get("publicationDate") == payload["publicationDate"],
          "Scheduled post could not be verified; persistent claim retained")
    result = {"status": "scheduled_verified", "date": day, "post_id": post_id,
              "scheduled_time": future.isoformat(), "text": text, "head_sha": receipt["head_sha"]}
    audit = ROOT / ".automation-audit"
    audit.mkdir(exist_ok=True)
    (audit / "x-post-receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    history = json.loads((ROOT / "data/history.json").read_text(encoding="utf-8"))
    result = schedule(history)
    print("X status: " + result["status"])


if __name__ == "__main__":
    main()
