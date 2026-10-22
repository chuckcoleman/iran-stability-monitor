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



MONTHS = ("January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December")
HEADING_DATE = re.compile(
    r"^(?:" + "|".join(MONTHS) + r")\\s+([0-3]?\\d),\\s+(20\\d\\d)$")
ARTICLE_DATE_ELEMENTS = frozenset(("time", "span", "div", "p"))


class PublisherHeadingDates(HTMLParser):
    """Only bounded visible date nodes immediately after the article H1.

    Never interpret body dates, navigation, footer or story references as
    publication dates. A visible publisher label is a witness, NOT proof of
    first publication or an independently authenticated timestamp.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1_seen = False
        self.in_h1 = False
        self.before_body = False
        self.node_count = 0
        self.text_count = 0
        self.excluded = []
        self.witnesses = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "nav", "aside", "footer", "noscript"):
            self.excluded.append(tag)
            return
        if self.excluded:
            return
        if tag == "h1" and not self.h1_seen:
            self.h1_seen, self.in_h1 = True, True
        elif tag == "p" and self.before_body:
            self.before_body = False
        if self.before_body and tag in ARTICLE_DATE_ELEMENTS:
            self.node_count += 1
            if self.node_count > 40:
                self.before_body = False
            elif tag == "time" and attrs.get("datetime"):
                self._add(attrs["datetime"], "article_heading_time_datetime")

    def handle_endtag(self, tag):
        if self.excluded:
            if tag == self.excluded[-1]:
                self.excluded.pop()
            return
        if tag == "h1" and self.in_h1:
            self.in_h1, self.before_body = False, True

    def _add(self, raw, origin):
        value = " ".join(raw.split())
        if not value or len(value) > 80:
            return
        day = None
        if HEADING_DATE.fullmatch(value):
            try:
                day = dt.datetime.strptime(value, "%B %d, %Y").date().isoformat()
            except ValueError:
                return
        elif origin == "article_heading_time_datetime":
            try:
                if re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", value):
                    day = dt.date.fromisoformat(value).isoformat()
                else:
                    timestamp = dt.datetime.fromisoformat(
                        value.replace("Z", "+00:00"))
                    # Publisher-reported date only; never invent a timezone.
                    day = timestamp.date().isoformat()
            except ValueError:
                return
        if day:
            item = {"date": day, "visible_text": value,
                    "location": origin,
                    "publisher_reported_only": True,
                    "first_publication_independently_verified": False}
            if item not in self.witnesses:
                self.witnesses.append(item)

    def handle_data(self, value):
        if self.in_h1 or not self.before_body or self.excluded:
            return
        self.text_count += len(value)
        if self.text_count > 1200:
            self.before_body = False
            return
        # An exact date-bearing text node after the primary H1 is a
        # conservative article-heading witness, not a random body date.
        self._add(value, "visible_article_heading_after_h1")


def heading_date_witnesses(html):
    parser = PublisherHeadingDates()
    parser.feed(html)
    return parser.witnesses


def parse_metadata(text, *, include_visible_heading_date=False):
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
    result = {
        "page_title": " ".join(" ".join(parser.title).split())[:500],
        "source_publication_time": next(iter(instants)) if len(instants) == 1 else None,
        "publication_candidates": sorted(instants),
        "publication_dates": sorted(dates),
        "metadata_status": ("verified article metadata" if len(instants) == 1
                            else "unknown precise time; absent, naive or conflicting metadata"),
    }
    if include_visible_heading_date:
        witnesses = heading_date_witnesses(text)
        heading_days = {w["date"] for w in witnesses}
        conflict = (len(heading_days) > 1 or
                    (bool(dates) and bool(heading_days) and
                     not heading_days.issubset(dates)))
        result["publication_date_witnesses"] = witnesses
        result["publication_date_conflict"] = bool(conflict)
        if conflict:
            result["publication_date_status"] = "CONFLICTING_PUBLISHER_DATE_WITNESSES"
            # Do not silently resolve a disagreement in publisher metadata.
        elif not dates and len(heading_days) == 1:
            result["publication_dates"] = sorted(heading_days)
            result["publication_date_status"] = (
                "VISIBLE_ARTICLE_HEADING_DATE_PUBLISHER_REPORTED_ONLY")
            result["metadata_status"] = (
                "publisher heading date only; precise first publication unverified")
        else:
            result["publication_date_status"] = (
                "ARTICLE_METADATA_OR_NO_USABLE_HEADING_DATE")
    return result


def capture_metadata(url, now=None, *, include_visible_heading_date=False):
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
            result.update(parse_metadata(
                body.decode(response.headers.get_content_charset() or "utf-8", "replace"),
                include_visible_heading_date=include_visible_heading_date))
            result["content_sha256"] = hashlib.sha256(body).hexdigest()
            result["retrieved_url"] = response.geturl()
            result["retrieval_status"] = "retrieved"
    except (OSError, ValueError, urllib.error.HTTPError, RecursionError):
        result["retrieval_status"] = "unavailable; web-search citation only"
        result["metadata_status"] = "unknown precise time; independent metadata unavailable"
    result["source_retrieved_at"] = now().isoformat(timespec="seconds")
    return result
