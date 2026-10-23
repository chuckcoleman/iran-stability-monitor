"""Bounded, reproducible *local* original-HTML passage and digest verification.

The source's own publication date and authenticity still require external
editorial verification. The exact HTML bytes stay in an off-repository handoff
and are NEVER deployed or added to a public GitHub PR. CI can audit the
hash-bound metadata, but cannot refetch/authenticate the publisher bytes.
"""
import datetime as dt
import hashlib
from pathlib import Path
import re

from source_metadata import MAX_BYTES, url_key
from source_passage_audit import visible_text
from review_receipt import digest

HEX = re.compile(r"^[a-f0-9]{64}$")
CONTENT_TYPES = frozenset(("text/html", "application/xhtml+xml"))


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def aware_time(value, label):
    require(isinstance(value, str), "Missing " + label)
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Invalid " + label) from None
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
            "No timezone on " + label)
    return stamp


def validate_capture_metadata(decision, cutoff):
    """Validate exact prospective publisher-body witness *claims* in a dossier."""
    cap = decision.get("capture_verification")
    require(isinstance(cap, dict), "Missing original source capture verification")
    required = {"original_url", "final_url", "retrieved_at", "content_type",
                "charset", "source_body_sha256", "visible_text_sha256",
                "passage_offset", "passage"}
    require(set(cap) == required, "Incomplete original capture verification metadata")
    url = decision.get("original_url")
    require(url_key(url) == url and cap["original_url"] == url and
            cap["final_url"] == url,
            "Original capture final URL differs from cited canonical URL")
    require(aware_time(cap["retrieved_at"], "original body retrieval") <=
            aware_time(cutoff, "frozen research cutoff"),
            "Original body was not captured before research cutoff")
    require(cap["content_type"] in CONTENT_TYPES and
            cap["charset"] == "utf-8",
            "Unsupported original HTML content type or encoding")
    require(all(isinstance(cap[k], str) and HEX.fullmatch(cap[k])
                for k in ("source_body_sha256", "visible_text_sha256")),
            "Malformed original HTML or visible-text hash")
    require(type(cap["passage_offset"]) is int and cap["passage_offset"] >= 0,
            "Missing exact passage character offset")
    require(cap["passage"] == decision.get("original_passage")
            and cap["source_body_sha256"] == decision.get("source_body_sha256"),
            "Capture metadata does not bind exact source quote and body hash")
    require(decision.get("capture_verification_sha256") == digest(cap),
            "Capture verification metadata changed after source freeze")
    return cap


def verify_capture_bytes(decision, raw, cutoff):
    """Recompute genuine local bytes, visible text and exact quotation offset."""
    cap = validate_capture_metadata(decision, cutoff)
    require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES,
            "Source capture is empty or exceeds safety bound")
    require(hashlib.sha256(raw).hexdigest() == cap["source_body_sha256"],
            "Original HTML bytes do not match asserted source-body SHA-256")
    txt = visible_text(raw, cap["charset"])
    require(hashlib.sha256(txt.encode("utf-8")).hexdigest() ==
            cap["visible_text_sha256"],
            "Original HTML visible text changed or was truncated incorrectly")
    pos, quote = cap["passage_offset"], cap["passage"]
    require(txt[pos:pos+len(quote)] == quote,
            "Original quotation absent at recorded visible-text character offset")
    return True


def verify_offline_handoff_captures(folder, dossier):
    """Require all claimed new original passages to be checked against bytes.

    Source files are local only, named by reviewed claim ID. Neither the CLI
    nor the GitHub API transfers original article bodies to the public repo.
    """
    folder = Path(folder)
    cutoff = dossier.get("research_as_of")
    packet = dossier.get("source_review_packet", {})
    claims = packet.get("evidence", [])
    decisions = {d.get("id"): d for d in
                 packet.get("pre_review_claim_decisions", [])}
    require(len(decisions) == len(packet.get("pre_review_claim_decisions", [])),
            "Repeated source-capture claim identifiers")
    directory = folder / "source-captures"
    require(directory.is_dir(), "Missing offline original-body captures directory")
    required_names = set()
    for row in claims:
        ident = row.get("id")
        require(isinstance(ident, str) and
                re.fullmatch(r"[A-Za-z0-9_-]{1,100}", ident) is not None,
                "Unsafe source capture filename/claim ID")
        claim = decisions.get(ident)
        require(isinstance(claim, dict), "Missing original capture claim")
        name = ident + ".html"
        required_names.add(name)
        path = directory / name
        require(path.is_file() and not path.is_symlink(),
                "Missing offline HTML capture: " + name)
        require(path.stat().st_size <= MAX_BYTES,
                "Source HTML capture exceeds maximum size")
        verify_capture_bytes(claim, path.read_bytes(), cutoff)
    actual = {p.name for p in directory.iterdir() if p.is_file()}
    require(actual == required_names,
            "Unmatched or missing original HTML captures in handoff")
    return len(required_names)


def validate_access_channels(source, cutoff):
    """Different *stages* may disagree; contradictions *within* a stage cannot.

    A publisher metadata GET after a search-stage block is not evidence that
    the earlier search accessed the article. These are reported facts in the
    packet, not authenticated network telemetry.
    """
    channels = source.get("access_channels")
    require(isinstance(channels, dict) and
            set(channels) == {"search", "metadata", "body", "same_stage_conflicts"},
            "All three source-access stages and conflicts must be recorded")
    require(channels["same_stage_conflicts"] == [],
            "Unresolved contradiction within a source-access stage")
    allowed = {
        "search": {"accessible_reported", "blocked_reported", "unknown", "not_searched"},
        "metadata": {"captured", "failed", "not_attempted"},
        "body": {"captured", "failed", "not_attempted"},
    }
    for stage in ("search", "metadata", "body"):
        row = channels[stage]
        require(isinstance(row, dict) and row.get("status") in allowed[stage]
                and isinstance(row.get("limitations"), str)
                and len(row["limitations"].strip()) >= 30,
                "Missing distinct source-access stage status/limitations: " + stage)
        when = row.get("checked_at")
        if when is not None:
            stamp = aware_time(when, stage + " checked_at")
            if stage == "search":
                require(stamp <= aware_time(cutoff, "source cutoff"),
                        "Search-stage source access cannot occur after cutoff")
    meta = channels["metadata"]
    http = meta.get("http_status")
    if meta["status"] == "captured":
        require(type(http) is int and 200 <= http < 300,
                "Same-stage metadata GET success conflicts with HTTP status")
    elif meta["status"] == "failed":
        require(http is None or
                (type(http) is int and not (200 <= http < 300)),
                "Same-stage metadata GET failure conflicts with success status")
    else:
        require(http is None, "Unattempted metadata stage claims HTTP status")
    body = channels["body"]
    claim_ids = body.get("captured_claim_ids")
    require(isinstance(claim_ids, list) and
            len(claim_ids) == len(set(claim_ids)) and
            all(isinstance(v, str) and v for v in claim_ids),
            "Incomplete original-body claim access register")
    if body["status"] != "captured":
        require(not claim_ids, "Original body stage claims captures but is unavailable")
    require(source.get("access_status") ==
            ("source_metadata_captured" if meta["status"] == "captured" else
             "source_unavailable" if meta["status"] == "failed" else
             "source_not_retrieved"),
            "Recorded source access status disagrees with metadata-stage result")
    return channels
