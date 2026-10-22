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


class ArticleMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.times, self.title = [], []
        self.in_title = False
        self.json_ld = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
            if key in ("article:published_time", "datepublished", "pubdate", "publishdate", "dc.date.issued"):
                self.times.append(attrs.get("content", ""))
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.json_ld = []

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.json_ld is not None:
            self.json_ld.append(data)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.json_ld is not None:
            try:
                obj = json.loads("".join(self.json_ld))
                self._article_dates(obj)
            except (ValueError, RecursionError):
                pass
            self.json_ld = None

    def _article_dates(self, obj):
        if isinstance(obj, list):
            for item in obj:
                self._article_dates(item)
        elif isinstance(obj, dict):
            kind = obj.get("@type", [])
            if isinstance(kind, str):
                kind = [kind]
            if any(k in ("Article", "NewsArticle", "ReportageNewsArticle", "BlogPosting") for k in kind):
                if isinstance(obj.get("datePublished"), str):
                    self.times.append(obj["datePublished"])
            self._article_dates(obj.get("@graph"))



_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December")
_MONTH_PATTERN = "(?:" + "|".join(_MONTHS) + ")"
_PUBLISHER_DATE = re.compile(
    r"\b(" + _MONTH_PATTERN + r")\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE)
_DATE_MARKER = re.compile(
    r"(?:^|[\s_\-])(date|published|publication|release-date|datepublished)"
    r"(?:[\s_\-]|$)", re.IGNORECASE)


class VisiblePublisherDates(HTMLParser):
    """Capture clearly designated article-date elements, never navigation dates.

    Only <time> or date/published-marked elements nested under main/article
    count. No global text searches, footer dates, 'last updated' substitution,
    timezone inference, or conversion of a page date into a first-release time.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.candidates = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("main", "article"):
            self.stack.append(("scope", None, tag))
        if not any(kind == "scope" for kind, _, _ in self.stack):
            return
        details = " ".join(str(attrs.get(key) or "")
                           for key in ("class", "id", "itemprop"))
        semantic = (tag == "time" or bool(_DATE_MARKER.search(details)))
        # Metadata fields are read separately; this parser captures the
        # publication date *visibly* labeled on the original page.
        if semantic:
            if tag == "time" and isinstance(attrs.get("datetime"), str):
                self._capture(attrs["datetime"], "time_datetime", tag)
            self.stack.append(("date", [], tag))
        elif self.stack and self.stack[-1][0] == "date":
            self.stack.append(("nested", None, tag))

    def handle_data(self, data):
        if not data:
            return
        for kind, chunks, _ in self.stack:
            if kind == "date":
                chunks.append(data[:250])

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1][2] == tag:
            kind, chunks, _ = self.stack.pop()
            if kind == "date":
                self._capture(" ".join(chunks)[:250], "article_visible_date", tag)

    def _capture(self, value, method, tag):
        clean = " ".join(value.split())[:180]
        day = None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", clean):
            try:
                day = dt.date.fromisoformat(clean)
            except ValueError:
                return
        else:
            match = _PUBLISHER_DATE.search(clean)
            if match:
                try:
                    month = next(i for i, name in enumerate(_MONTHS, 1)
                                 if name.lower() == match.group(1).lower())
                    day = dt.date(int(match.group(3)), month,
                                  int(match.group(2)))
                except (ValueError, StopIteration):
                    return
            elif method == "time_datetime":
                # A complete timezone-aware <time datetime> already has
                # separate precise timestamp extraction in parse_metadata.
                try:
                    stamp = dt.datetime.fromisoformat(
                        clean.replace("Z", "+00:00"))
                    if stamp.utcoffset() is not None:
                        day = stamp.date()
                except (ValueError, TypeError):
                    pass
        if day:
            row = {"date": day.isoformat(), "method": method, "tag": tag,
                   "publisher_visible_excerpt": clean}
            if row not in self.candidates:
                self.candidates.append(row)


def visible_publisher_dates(text):
    """Evidence for publisher-labeled dates; does not authenticate release."""
    reader = VisiblePublisherDates()
    reader.feed(text)
    return reader.candidates


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
        except (ValueError, TypeError):
            continue
    publisher_dates = visible_publisher_dates(text)
    dates.update(item["date"] for item in publisher_dates)
    # Only a scoped original article <time datetime=...> with an actual
    # timezone is precise enough to contribute a publisher-supplied clock.
    # The visible month/day heading alone NEVER supplies a clock.
    for item in publisher_dates:
        if item["method"] != "time_datetime":
            continue
        try:
            stamp = dt.datetime.fromisoformat(
                item["publisher_visible_excerpt"].replace("Z", "+00:00"))
            if stamp.utcoffset() is not None:
                instants.add(stamp.astimezone(UTC).isoformat())
        except (TypeError, ValueError):
            continue
    report = {
        "page_title": " ".join(" ".join(parser.title).split())[:500],
        "source_publication_time": next(iter(instants)) if len(instants) == 1 else None,
        "publication_candidates": sorted(instants),
        "publication_dates": sorted(dates),
        "metadata_status": ("verified article metadata" if len(instants) == 1
                            else "publisher-reported article date without precise first-publication time"
                            if publisher_dates else
                            "unknown precise time; absent, naive or conflicting metadata"),
    }
    if publisher_dates:
        report["publisher_date_evidence"] = publisher_dates
    return report


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
