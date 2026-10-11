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
    return {
        "page_title": " ".join(" ".join(parser.title).split())[:500],
        "source_publication_time": next(iter(instants)) if len(instants) == 1 else None,
        "publication_candidates": sorted(instants),
        "publication_dates": sorted(dates),
        "metadata_status": ("verified article metadata" if len(instants) == 1
                            else "unknown precise time; absent, naive or conflicting metadata"),
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
