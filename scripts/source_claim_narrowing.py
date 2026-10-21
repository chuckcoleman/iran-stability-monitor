"""Deterministic, quote-limited evidence narrowing; never synthesize facts.

The correction uses ONLY text already recorded by the independent original
HTML passage inspector. It cannot assert the quoted text's truth, publish a
probability, invent an event, alter the original model record, or confirm first
publication. Affirmative and critical reviewers must assess each changed packet.
"""
import copy
import hashlib

from source_metadata import url_key
from source_research_batches import sha

LIMITED_STATUS = "QUOTE_ONLY_NOT_INDEPENDENTLY_VERIFIED"
FATAL_OBJECTIONS = frozenset((
    "caveat_mistaken_for_substantive_support",
    "insufficient_quote_context",
    "methodology_quote_not_finding",
    "unresolved_cutoff_eligibility",
    "unresolved_first_publication_and_cutoff_eligibility",
))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def quoted_observation(witness):
    """Fixed template: only claim is the presence of a source quotation."""
    quote = witness["passage"]
    require(isinstance(quote, str) and quote == quote.strip()
            and 4 <= len(quote.split()) <= 25
            and witness.get("status") == "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED",
            "A source passage must be independently captured before narrowing")
    return ('Original-source passage (attributed, not independently verified): '
            '“' + quote + '”. The wider event and implications for Iranian '
            'stability have not been established by this excerpt.')


def narrow_to_passage(entry, witness):
    """Return only a strictly weaker presentation of an original claim."""
    require(isinstance(entry, dict) and isinstance(witness, dict),
            "Missing original claim or source witness")
    require(witness.get("evidence_id") == entry.get("id")
            and witness.get("url") == url_key(entry.get("source"))
            and witness.get("observation_sha256") ==
                hashlib.sha256(entry["observation"].encode("utf-8")).hexdigest(),
            "Source witness does not match original claim")
    require(entry.get("evidence_status") == "new",
            "Archived observations cannot be reinterpreted through quotations")
    result = copy.deepcopy(entry)
    result["observation"] = quoted_observation(witness)
    result["direction"] = "ambiguous"
    result["impact_magnitude"] = "minor"
    result["reliability"] = "Low"
    result["affects"] = []
    result["editorial_support_status"] = LIMITED_STATUS
    return result


def permitted_narrowing(entry, witness, reasons):
    """An exact text match alone does not make an unrelated source relevant."""
    if not witness or witness.get("status") != "EXACT_PASSAGE_PRESENT_REVIEW_REQUIRED":
        return False
    if entry.get("evidence_status") != "new":
        return False
    if not reasons:
        return False
    types = {issue.get("type") for issue in reasons}
    # These objections say timing/context/content is too uncertain to retain
    # even a short quote as an admissible research observation.
    if types & FATAL_OBJECTIONS:
        return False
    if entry.get("editorial_support_status"):
        return False  # a repeatedly challenged quote cannot be polished again
    return True


def narrowing_record(before, after, witness, reasons):
    """Immutable mapping of exact source quote and original rejected claim."""
    return {
        "evidence_id": before["id"],
        "status": LIMITED_STATUS,
        "original_evidence": copy.deepcopy(before),
        "revised_evidence": copy.deepcopy(after),
        "original_observation_sha256": hashlib.sha256(
            before["observation"].encode("utf-8")).hexdigest(),
        "source_passage_sha256": sha(witness),
        "review_issue_types": sorted({x["type"] for x in reasons}),
        "review_issue_locations": [x["location"] for x in reasons],
        "publication": "NOT AUTHORIZED",
        "limitations": (
            "Only the source's exact recorded passage is quoted. Its relevance, "
            "factual accuracy, publication timing, any direction and magnitude "
            "remain unverified pending independent affirmative and critical "
            "source reviews.")
    }


def validate_narrowings(packet):
    """Prove no quote-only revision invented or amplified a source claim."""
    register = packet.get("claim_evidence_register")
    if register is None:
        require(not packet.get("editorial_narrowings"),
                "Legacy packet cannot acquire a fabricated narrowed claim")
        return True
    witness = {row["evidence_id"]: row for row in register["claims"]}
    require(len(witness) == len(register["claims"]),
            "Duplicate claim witnesses cannot support narrowed evidence")
    records = packet.get("editorial_narrowings", [])
    require(isinstance(records, list),
            "Malformed editorial narrowing register")
    live = {item["id"]: item for item in packet["evidence"]}
    seen = set()
    for record in records:
        require(isinstance(record, dict), "Malformed narrowed-claim record")
        key = record.get("evidence_id")
        require(key not in seen and key in witness,
                "Duplicated or unknown narrowed-claim ID")
        seen.add(key)
        original = record.get("original_evidence")
        revised = record.get("revised_evidence")
        require(isinstance(original, dict) and isinstance(revised, dict)
                and original.get("id") == key
                and record.get("status") == LIMITED_STATUS,
                "Invalid original/narrowed claim provenance")
        require(record.get("original_observation_sha256") ==
                hashlib.sha256(original["observation"].encode("utf-8")).hexdigest()
                and record.get("source_passage_sha256") == sha(witness[key]),
                "Narrowed claim no longer matches original evidence or passage")
        expected = narrow_to_passage(original, witness[key])
        require(expected == revised,
                "Narrowed evidence contains unsupported new interpretation")
        if key in live:
            require(live[key] == revised,
                    "Narrowed evidence differs from its immutable source passage")
        require(record.get("publication") == "NOT AUTHORIZED",
                "Narrowing cannot authorize publication")
    for key, item in live.items():
        if item.get("editorial_support_status") == LIMITED_STATUS:
            require(key in seen,
                    "Quote-limited evidence lacks deterministic correction provenance")
    return True
