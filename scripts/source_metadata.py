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



# Dates visible immediately after the article headline are useful publisher
# assertions even when the page omits datePublished/og:published_time. They
# are NOT independently verified first-publication instants. In particular,
# dates elsewhere in body copy, navigation or related-article lists do not
# qualify as original article dates.
_EN_MONTHS = (
    "January February March April May June July August September October "
    "November December"
).split()
_MONTH_TOKEN = "(?:" + "|".join(_EN_MONTHS) + ")"
_VISIBLE_ARTICLE_DATE = re.compile(
    r"^(?:(?:Published|Released|Date)(?: on)?\s*:?\s*)?"
    r"(" + _MONTH_TOKEN + r"\s+\d{1,2},?\s+\d{4}"
    r"|\d{4}-\d{2}-\d{2})\.?$",
    re.IGNORECASE)


def _visible_date(value):
    if not isinstance(value, str):
        return None
    clean = " ".join(value.split())
    match = _VISIBLE_ARTICLE_DATE.fullmatch(clean)
    if not match:
        return None
    date = match.group(1)
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            return dt.date.fromisoformat(date).isoformat()
        date = re.sub(r",", "", date).title()
        return dt.datetime.strptime(date, "%B %d %Y").date().isoformat()
    except ValueError:
        return None


class HeadlineDateScanner(HTMLParser):
    """Find only complete date tokens adjacent to the actual page headline.

    The qualifying heading must agree with the HTML <title> (not an
    arbitrary menu heading). Inspect at most six following visible text
    fragments. This intentionally avoids mining a date from the body.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.document_title = []
        self.in_title = False
        self.in_headline = False
        self.headline_tag = None
        self.headline_text = []
        self.after_headline = False
        self.remaining = 0
        self.found = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        # An ordinary article-body paragraph containing a date does NOT
        # establish the publication date, even if it is the first paragraph
        # after the headline. Only a standalone heading-adjacent date label
        # or time/date element is eligible for the bounded scanner.
        if self.after_headline:
            attrs_map = dict(attrs)
            date_label = " ".join(
                str(attrs_map.get(x) or "") for x in ("class", "id", "itemprop"))
            explicitly_dated = bool(re.search(
                r"(?:^|[\\s_-])(?:date|published|pubdate|release|timestamp)",
                date_label, re.IGNORECASE))
            if tag in ("section", "figure", "table") or (
                    tag == "p" and not explicitly_dated):
                self.after_headline = False
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if (tag in ("h1", "h2") and not self.after_headline
                and not self.found and self.skip == 0):
            self.in_headline = True
            self.headline_tag = tag
            self.headline_text = []

    def handle_data(self, value):
        if self.skip:
            return
        if self.in_title:
            self.document_title.append(value)
        if self.in_headline:
            self.headline_text.append(value)
        elif self.after_headline and self.remaining > 0:
            fragment = " ".join(value.split())
            if fragment:
                self.remaining -= 1
                when = _visible_date(fragment)
                if when:
                    self.found.append({
                        "date": when,
                        "origin": "article_headline_adjacent_visible_date",
                        "original_text": fragment[:100],
                        "first_publication_verified": False})
                    self.after_headline = False
                elif self.remaining == 0:
                    self.after_headline = False

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if self.in_headline and tag == self.headline_tag:
            heading = " ".join(" ".join(self.headline_text).split())
            title = " ".join(" ".join(self.document_title).split())
            self.in_headline = False
            self.headline_tag = None
            # Avoid a site-wide heading or generic navigation being treated
            # as an article title. The HTML title must contain this heading.
            if len(heading) >= 25 and heading.casefold()[:25] in title.casefold():
                self.after_headline = True
                self.remaining = 6
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1


def headline_publication_dates(text):
    require_text = isinstance(text, str) and len(text) <= MAX_BYTES * 3
    if not require_text:
        return []
    parser = HeadlineDateScanner()
    parser.feed(text)
    return parser.found


def parse_metadata(text):
    parser = ArticleMetadata()
    parser.feed(text)
    instants, dates = set(), set()
    header_dates = headline_publication_dates(text)
    for witness in header_dates:
        dates.add(witness["date"])
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
        "metadata_status": (
            "verified article metadata" if len(instants) == 1 else
            "publisher-reported visible headline date; precise time unknown"
            if header_dates else
            "unknown precise time; absent, naive or conflicting metadata"),
    }
    if header_dates:
        result["publication_date_evidence"] = header_dates
        result["first_publication_verified"] = False
    return result


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
