"""Bounded, unauthenticated source-metadata capture before the evidence cutoff.

Only article publication metadata is retained, not article bodies. Network failures
remain explicit unknowns; model-supplied clock times are never treated as verified.
"""
import datetime as dt
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

MAX_BYTES = 1_500_000
UTC = dt.timezone.utc


def url_key(value):
    try:
        u = urlsplit(value)
        if (u.scheme != "https" or not u.hostname or "." not in u.hostname
                or u.username or u.password or u.port not in (None, 443)
                or re.search(r'[\s<>"\x00-\x1f]', value)
                or u.hostname.endswith((".localhost", ".local", ".internal"))):
            return None
        try:
            ipaddress.ip_address(u.hostname)
            return None  # Preserve the existing policy: no literal-IP source URLs.
        except ValueError:
            pass
        # Preserve content-selecting parameters; strip only recognized tracking keys.
        query = urlencode([(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
                           if not k.lower().startswith("utm_") and k not in ("fbclid", "gclid")])
        return urlunsplit(("https", u.hostname.lower(), u.path or "/", query, ""))
    except (TypeError, ValueError):
        return None


def assert_public_host(url):
    if not url_key(url):
        raise ValueError("Source URL is not a public HTTPS address")
    host = urlsplit(url).hostname
    addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Source resolves to a non-public network")


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_public_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Publication dates in a news-article heading are publisher statements, not
# proof of first release. The fallback is deliberately narrow: a standalone
# date immediately following the first article H1. Never scan arbitrary body,
# related links, site footers or "last updated" text for a publication date.
_MONTH = {
    name.lower(): i for i, name in enumerate(
        ("January", "February", "March", "April", "May", "June",
         "July", "August", "September", "October", "November", "December"), 1)
}
_MONTH_PATTERN = "|".join(_MONTH)
_HEADING_DATE_MDY = re.compile(
    rf"^(?:(?:Published|Release Date|Issued|Dated)\s*:?\s*)?"
    rf"({_MONTH_PATTERN})\s+(\d{{1,2}}),?\s+(\d{{4}})$", re.IGNORECASE)
_HEADING_DATE_DMY = re.compile(
    rf"^(?:(?:Published|Release Date|Issued|Dated)\s*:?\s*)?"
    rf"(\d{{1,2}})\s+({_MONTH_PATTERN})\s+(\d{{4}})$", re.IGNORECASE)


def _publisher_heading_day(text):
    if not isinstance(text, str):
        return None
    value = " ".join(text.split()).strip()
    if len(value) > 95 or re.search(r"\b(?:updated|revised|modified)\b", value, re.I):
        return None
    a = _HEADING_DATE_MDY.fullmatch(value)
    b = _HEADING_DATE_DMY.fullmatch(value) if a is None else None
    try:
        if a:
            month, day, year = a.groups()
            return dt.date(int(year), _MONTH[month.lower()], int(day)).isoformat()
        if b:
            day, month, year = b.groups()
            return dt.date(int(year), _MONTH[month.lower()], int(day)).isoformat()
    except ValueError:
        return None
    return None


class ArticleMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.times, self.title = [], []
        self.in_title = False
        self.json_ld = None
        self.first_h1_seen = False
        self.in_first_h1 = False
        self.after_h1 = False
        self.heading_fragments = []
        self.heading_datetime = []
        self._heading_count = 0
        self._ignored = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "nav", "footer", "aside", "noscript", "template"):
            self._ignored.append(tag)
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
            if key in ("article:published_time", "datepublished", "pubdate",
                       "publishdate", "dc.date.issued"):
                self.times.append(attrs.get("content", ""))
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.json_ld = []
        if tag == "h1" and not self.first_h1_seen and not self._ignored:
            self.first_h1_seen = True
            self.in_first_h1 = True
        if (tag == "time" and self.after_h1 and not self._ignored
                and self._heading_count <= 18):
            label = " ".join(str(attrs.get(k) or "") for k in
                             ("class", "id", "itemprop", "data-label")).casefold()
            raw = attrs.get("datetime")
            if raw and not re.search(r"updated|modified|revised", label):
                self.heading_datetime.append(str(raw)[:100])

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.json_ld is not None:
            self.json_ld.append(data)
        if self.after_h1 and not self._ignored and self.json_ld is None:
            value = " ".join(data.split()).strip()
            if value and self._heading_count < 18:
                self.heading_fragments.append(value[:180])
                self._heading_count += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "h1" and self.in_first_h1:
            self.in_first_h1 = False
            self.after_h1 = True
        if tag == "script" and self.json_ld is not None:
            try:
                obj = json.loads("".join(self.json_ld))
                self._article_dates(obj)
            except (ValueError, RecursionError):
                pass
            self.json_ld = None
        if self._ignored and tag == self._ignored[-1]:
            self._ignored.pop()

    def _article_dates(self, obj):
        if isinstance(obj, list):
            for item in obj:
                self._article_dates(item)
        elif isinstance(obj, dict):
            kind = obj.get("@type", [])
            if isinstance(kind, str):
                kind = [kind]
            if any(k in ("Article", "NewsArticle", "ReportageNewsArticle", "BlogPosting")
                   for k in kind):
                if isinstance(obj.get("datePublished"), str):
                    self.times.append(obj["datePublished"])
            self._article_dates(obj.get("@graph"))

    def heading_date_evidence(self):
        candidates = []
        for text in self.heading_fragments:
            day = _publisher_heading_day(text)
            if day is not None:
                candidates.append({
                    "location": "adjacent_to_first_article_h1",
                    "kind": "publisher_displayed_heading_date",
                    "raw": text, "date": day})
        for text in self.heading_datetime:
            try:
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                    day = dt.date.fromisoformat(text).isoformat()
                else:
                    stamp = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
                    day = stamp.date().isoformat()
                candidates.append({
                    "location": "time_tag_after_first_article_h1",
                    "kind": "publisher_time_element_date",
                    "raw": text, "date": day})
            except (ValueError, TypeError, AttributeError):
                continue
        # A heading with contradictory date labels is not automatically
        # converted into a verified publication date.
        days = {x["date"] for x in candidates}
        return candidates, (next(iter(days)) if len(days) == 1 else None)


def parse_metadata(text):
    parser = ArticleMetadata()
    parser.feed(text)
    instants, dates = set(), set()
    for value in parser.times:
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
                dates.add(dt.date.fromisoformat(value.strip()).isoformat())
                continue
            stamp = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if stamp.tzinfo is not None and stamp.utcoffset() is not None:
                instants.add(stamp.astimezone(UTC).isoformat())
                dates.add(stamp.date().isoformat())
        except (ValueError, TypeError, AttributeError):
            continue
    witnesses, heading_day = parser.heading_date_evidence()
    # Never use heading dates to replace a contradictory precise timestamp.
    if heading_day is not None and (
            not instants or heading_day in {
                dt.datetime.fromisoformat(t).date().isoformat() for t in instants
            }):
        dates.add(heading_day)
    elif heading_day is not None:
        heading_day = None
    evidence_status = (
        "publisher_reported_heading_date_not_first_publication_proof"
        if heading_day and not instants else
        "conflicting_heading_dates_not_admitted"
        if witnesses and not heading_day else
        "machine_readable_date_metadata_only"
        if dates or instants else "no_publisher_publication_date")
    return {
        "page_title": " ".join(" ".join(parser.title).split())[:500],
        "source_publication_time": next(iter(instants)) if len(instants) == 1 else None,
        "publication_candidates": sorted(instants),
        "publication_dates": sorted(dates),
        "publisher_heading_date_evidence": witnesses,
        "publisher_heading_admitted_day": heading_day,
        "publisher_heading_date_status": evidence_status,
        "metadata_status": ("publisher-reported article timestamp, not first publication proof"
                            if len(instants) == 1 else
                            "publisher-reported heading date only; precise first time unknown"
                            if heading_day else
                            "unknown precise time; absent, naive or conflicting metadata"),
    }


def capture_metadata(url, now=None):
    now = now or (lambda: dt.datetime.now(UTC))
    result = {"source": url, "source_publication_time": None,
              "publication_candidates": [], "publication_dates": []}
    try:
        assert_public_host(url)
        req = urllib.request.Request(url, headers={"User-Agent": "IranStabilityMonitor-source-audit/1.0",
                                                   "Accept": "text/html,application/xhtml+xml"})
        opener = urllib.request.build_opener(PublicRedirect())
        with opener.open(req, timeout=15) as response:
            assert_public_host(response.geturl())
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("Source metadata page exceeds capture bound")
            content_type = response.headers.get_content_type()
            if content_type not in ("text/html", "application/xhtml+xml"):
                raise ValueError("No HTML article metadata")
            result.update(parse_metadata(body.decode(response.headers.get_content_charset() or "utf-8", "replace")))
            result["content_sha256"] = hashlib.sha256(body).hexdigest()
            result["retrieved_url"] = response.geturl()
            result["retrieval_status"] = "retrieved"
    except (OSError, ValueError, urllib.error.HTTPError, RecursionError):
        result["retrieval_status"] = "unavailable; web-search citation only"
        result["metadata_status"] = "unknown precise time; independent metadata unavailable"
    result["source_retrieved_at"] = now().isoformat(timespec="seconds")
    return result
