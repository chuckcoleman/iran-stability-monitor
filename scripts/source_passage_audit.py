"""Conservative original-page passage inspection for individual research claims.

A matched passage proves *only* that a short string was found in the
independently fetched public HTML. It does not verify the surrounding event,
the model's interpretation, first publication time, or corroboration.
Never archive entire copyright-protected article bodies.
"""
import datetime as dt
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

from source_metadata import (
    MAX_BYTES, PublicRedirect, assert_public_host, url_key,
)
from source_research_batches import sha, save_new, read_json

MAX_QUOTE_WORDS = 25
MIN_QUOTE_WORDS = 4
MAX_TEXT_CHARS = 250_000
BLOCKS = frozenset(("p", "h1", "h2", "h3", "h4", "li", "blockquote"))
SKIPPED = frozenset(("script", "style", "nav", "aside", "footer",
                     "header", "noscript", "template", "form", "svg"))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def normalize_text(value):
    return re.sub(r"\s+", " ", value).strip()


class VisiblePassages(HTMLParser):
    """Read visible paragraph and heading text, not script/meta/title snippets."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.excluded = []
        self.blocks = []
        self.active = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIPPED:
            self.excluded.append(tag)
        elif tag in BLOCKS and not self.excluded:
            self.active.append([tag, []])

    def handle_data(self, value):
        if self.active and not self.excluded:
            self.active[-1][1].append(value)

    def handle_endtag(self, tag):
        if self.excluded:
            if tag == self.excluded[-1]:
                self.excluded.pop()
            return
        if self.active and tag == self.active[-1][0]:
            _, pieces = self.active.pop()
            value = normalize_text("".join(pieces))
            if len(value) >= 4:
                self.blocks.append(value)


def visible_text(raw, encoding="utf-8"):
    parser = VisiblePassages()
    parser.feed(raw.decode(encoding or "utf-8", "replace"))
    return normalize_text(" ".join(parser.blocks))[:MAX_TEXT_CHARS]


def _fetch_public_html(url):
    """Bounded public HTTPS GET with host and redirect checks."""
    assert_public_host(url)
    req = urllib.request.Request(
        url, headers={
            "User-Agent": "IranStabilityMonitor-claim-audit/1.0",
            "Accept": "text/html,application/xhtml+xml"})
    opener = urllib.request.build_opener(PublicRedirect())
    with opener.open(req, timeout=12) as response:
        final_url = response.geturl()
        assert_public_host(final_url)
        content_type = response.headers.get_content_type()
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("Original source exceeds bounded fetch size")
    if content_type not in ("text/html", "application/xhtml+xml"):
        raise ValueError("Original is not inspectable HTML")
    return body, final_url, content_type, charset


def capture_claim_passage(url, proposed_quote, *, observation, now=None,
                          fetcher=None, original_cutoff=None):
    """Return immutable, short source witness; never infer semantic truth.

    A missing or guessed quote cannot be replaced with a model citation, a
    metadata title, a search snippet, or automatically selected similar text.
    """
    now = now or (lambda: dt.datetime.now(dt.timezone.utc))
    stamp = now()
    require(isinstance(stamp, dt.datetime) and stamp.tzinfo is not None
            and stamp.utcoffset() is not None,
            "Claim inspection timestamp requires an aware clock")
    key = url_key(url)
    require(key is not None, "Claim source is not a public HTTPS URL")
    require(isinstance(observation, str) and observation.strip(),
            "Missing substantive observation for source-passage audit")
    quote = normalize_text(proposed_quote) if isinstance(proposed_quote, str) else ""
    status = "NO_VERBATIM_QUOTE"
    if quote and (len(quote.split()) < MIN_QUOTE_WORDS
                  or len(quote.split()) > MAX_QUOTE_WORDS
                  or any(ord(c) < 32 for c in quote)):
        status = "INVALID_QUOTE_LENGTH_OR_CONTENT"
    record = {
        "url": key, "observation_sha256": hashlib.sha256(
            observation.encode("utf-8")).hexdigest(),
        "proposed_quote": quote[:900],
        "passage": None, "passage_offset": None,
        "source_body_sha256": None, "visible_text_sha256": None,
        "retrieved_url": None, "content_type": None,
        "inspected_at": stamp.isoformat(),
        "original_cutoff": original_cutoff,
        "inspection_after_original_cutoff": bool(
            original_cutoff and stamp >
            dt.datetime.fromisoformat(original_cutoff)),
        "status": status,
        "semantic_support": "NOT_INDEPENDENTLY_ESTABLISHED",
        "first_publication_verified": False,
        "limitations": (
            "An exact original-page passage is a textual witness only. "
            "Event interpretation, original publication timing, publisher "
            "independence and directional effects require critical review.")
    }
    if status != "NO_VERBATIM_QUOTE":
        return record
    if not quote:
        return record
    try:
        body, final_url, content_type, charset = (
            fetcher(url) if fetcher is not None else _fetch_public_html(url))
        require(isinstance(body, bytes) and len(body) <= MAX_BYTES,
                "Malformed or oversized source response")
        record["retrieved_url"] = url_key(final_url)
        record["content_type"] = content_type
        if url_key(final_url) != key:
            record["status"] = "REDIRECTED_TO_DIFFERENT_ORIGINAL"
            return record
        if content_type not in ("text/html", "application/xhtml+xml"):
            record["status"] = "NOT_INSPECTABLE_HTML"
            return record
        text = visible_text(body, charset)
        record["source_body_sha256"] = hashlib.sha256(body).hexdigest()
        record["visible_text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        offset = text.find(quote)
        if offset < 0:
            record["status"] = "QUOTE_NOT_FOUND_IN_ORIGINAL"
            return record
        record["passage"] = quote
        record["passage_offset"] = offset
        record["status"] = "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED"
    except (OSError, ValueError, UnicodeError, urllib.error.HTTPError):
        record["status"] = "ORIGINAL_TEXT_UNAVAILABLE"
    return record


def _quote_for_frozen(raw_research, frozen):
    """Only a unique exact original claim may supply the proposed quotation."""
    matches = [
        item for item in raw_research.get("evidence", [])
        if isinstance(item, dict)
        and url_key(item.get("source")) == url_key(frozen.get("source"))
        and item.get("event_date") == frozen.get("event_date")
        and item.get("category") == frozen.get("category")
    ]
    if len(matches) != 1:
        return None
    return matches[0].get("support_quote")


def verify_register(register, frozen, *, snapshot_sha=None, history_sha=None):
    """Validate shape, source binding and all textual witness invariants."""
    require(isinstance(register, dict) and register.get("version") == 1
            and register.get("status") == "PASSAGES_ONLY_NOT_APPROVED",
            "Invalid claim-passage audit version")
    if snapshot_sha is not None:
        require(register.get("research_snapshot_sha256") == snapshot_sha,
                "Claim-passage audit references another research snapshot")
    if history_sha is not None:
        require(register.get("baseline_history_sha256") == history_sha,
                "Claim-passage audit history fingerprint changed")
    require(register.get("evidence_sha256") == sha(frozen),
            "Claim-passage audit evidence list changed")
    claims = register.get("claims")
    require(isinstance(claims, list) and len(claims) == len(frozen),
            "Incomplete claim-passage inventory")
    seen = set()
    for item, evidence in zip(claims, frozen):
        require(isinstance(item, dict) and item.get("evidence_id") == evidence["id"]
                and item["evidence_id"] not in seen,
                "Duplicated or mismatched claim evidence ID")
        seen.add(item["evidence_id"])
        require(item.get("url") == url_key(evidence.get("source")),
                "Claim record references a different original URL")
        require(item.get("observation_sha256") ==
                hashlib.sha256(evidence["observation"].encode()).hexdigest(),
                "Claim record assertion changed")
        require(item.get("semantic_support") == "NOT_INDEPENDENTLY_ESTABLISHED"
                and item.get("first_publication_verified") is False,
                "Source passage was incorrectly promoted to established truth")
        state = item.get("status")
        require(isinstance(state, str), "Claim passage has no inspection state")
        if state == "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED":
            quote = item.get("passage")
            require(isinstance(quote, str)
                    and quote == item.get("proposed_quote")
                    and MIN_QUOTE_WORDS <= len(quote.split()) <= MAX_QUOTE_WORDS
                    and type(item.get("passage_offset")) is int
                    and item["passage_offset"] >= 0
                    and item.get("retrieved_url") == item.get("url")
                    and re.fullmatch(r"[a-f0-9]{64}",
                                     item.get("source_body_sha256") or "")
                    and re.fullmatch(r"[a-f0-9]{64}",
                                     item.get("visible_text_sha256") or ""),
                    "Quoted original-page witness is incomplete or malformed")
        else:
            require(item.get("passage") is None
                    and item.get("passage_offset") is None,
                    "Missing/unmatched page cannot contain an accepted quotation")
        try:
            inspected = dt.datetime.fromisoformat(item["inspected_at"])
        except (TypeError, ValueError, KeyError):
            raise ValueError("Malformed claim inspection timestamp") from None
        require(inspected.tzinfo is not None and inspected.utcoffset() is not None,
                "Naive claim inspection timestamp")
    return True


def build_claim_register(folder, *, research, frozen, baseline_sha, snapshot,
                         inspector=None):
    """Inspect each candidate once, checkpoint source-text witnesses, no scores.

    A legacy review input is never silently retrofitted. New research runs
    bind the register to the original frozen evidence list and snapshot.
    """
    folder = Path(folder)
    destination = folder / "claim-evidence-register.json"
    if destination.exists():
        previous = read_json(destination)
        verify_register(
            previous, frozen, history_sha=baseline_sha,
            snapshot_sha=snapshot["snapshot_sha256"] if snapshot else None)
        return previous
    inspector = inspector or capture_claim_passage
    rows = []
    for evidence in frozen:
        quote = _quote_for_frozen(research, evidence)
        inspected = inspector(
            evidence["source"], quote,
            observation=evidence["observation"],
            original_cutoff=snapshot["cutoff_at"] if snapshot else None)
        require(isinstance(inspected, dict), "Source inspector returned no audit")
        row = dict(inspected, evidence_id=evidence["id"],
                   evidence_status=evidence.get("evidence_status"))
        rows.append(row)
    register = {
        "version": 1, "status": "PASSAGES_ONLY_NOT_APPROVED",
        "baseline_history_sha256": baseline_sha,
        "research_snapshot_sha256": (
            snapshot["snapshot_sha256"] if snapshot else None),
        "evidence_sha256": sha(frozen), "claims": rows,
        "publication": "NOT AUTHORIZED",
        "limitations": (
            "Verbatim matched passages establish only that the text appears "
            "on a fetched public page. Claims and timestamps remain unverified "
            "until both independent reviews accept the same closed version.")
    }
    verify_register(register, frozen, history_sha=baseline_sha,
                    snapshot_sha=snapshot["snapshot_sha256"] if snapshot else None)
    save_new(destination, register)
    return register
