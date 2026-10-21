"""Fail-closed status validation and audited historical carry-forward recovery.

Original Responses, six stage results, citation checks and historical archive
remain untouched. A legacy model formatting error is repairable *only* from a
verified, previously saved stage, never from a fresh paid model response.
"""
import copy
import re
from pathlib import Path

from source_metadata import url_key

EXACT = frozenset(("new", "carried_forward"))
LEGACY_CARRY = re.compile(r"carried_forward with existing id (E-[0-9]{8}-[0-9]{2})\Z")
IDENTITY = ("source", "event_date", "source_title", "publisher")
HISTORICAL_FIELDS = IDENTITY + ("category", "observation")


def require(value, reason):
    if not value:
        raise ValueError(reason)


def history_index(rows):
    """Check repeated historical IDs for ambiguous archival identities."""
    require(isinstance(rows, list), "Historical evidence ledger is malformed")
    indexed = {}
    for row in rows:
        require(isinstance(row, dict), "Invalid historical evidence entry")
        key = row.get("id")
        if not isinstance(key, str):
            continue
        if key in indexed:
            prior = indexed[key]
            for field in HISTORICAL_FIELDS:
                a = url_key(prior.get(field)) if field == "source" else prior.get(field)
                b = url_key(row.get(field)) if field == "source" else row.get(field)
                require(a == b, "Conflicting historical records for evidence ID " + key)
        else:
            indexed[key] = row
    return indexed


def archived_identity(candidate, historical_id, history, *,
                      require_unchanged_content):
    """Only original source/date/title/publisher may bind a historical ID.

    A claim with a different category or interpretation can never change the
    archived observation: the old record is used, and the attempted
    reinterpretation is retained as untrusted diagnostic data.
    """
    require(isinstance(candidate, dict), "Malformed model evidence candidate")
    require(isinstance(historical_id, str) and historical_id in history,
            "Carried-forward evidence ID is not present in published history")
    old = history[historical_id]
    require(url_key(candidate.get("source")) is not None,
            "Historical source is not a public HTTPS URL")
    for field in IDENTITY:
        actual = (url_key(candidate.get(field)) if field == "source"
                  else candidate.get(field))
        expected = (url_key(old.get(field)) if field == "source"
                    else old.get(field))
        require(actual == expected,
                "Carried-forward source identity mismatch in " + field)
    supplied_id = candidate.get("id")
    require(supplied_id in (None, historical_id),
            "Conflicting carried-forward ID and legacy status reference")
    if require_unchanged_content:
        for field in ("category", "observation"):
            require(candidate.get(field) == old.get(field),
                    "Changed historical " + field +
                    " cannot be accepted as a carried-forward observation")
    return old


def validate_stage_status(candidate, original_history, *,
                          verified_legacy_checkpoint=False):
    """Reject invalid status at the stage boundary, before checkpoint creation."""
    history = history_index(original_history)
    require(isinstance(candidate, dict), "Malformed model evidence item")
    status = candidate.get("evidence_status")
    if status == "new":
        require(candidate.get("id") is None,
                "New evidence may not claim a historical ID")
        return None
    if status == "carried_forward":
        ident = candidate.get("id")
        archived_identity(candidate, ident, history,
                          require_unchanged_content=True)
        return ident
    match = LEGACY_CARRY.fullmatch(status) if isinstance(status, str) else None
    require(verified_legacy_checkpoint and match is not None,
            "Invalid evidence status at source-stage boundary")
    archived_identity(candidate, match.group(1), history,
                      require_unchanged_content=False)
    return match.group(1)


def reconcile_before_freeze(research, history_rows, folder, snapshot, *,
                            verified_legacy_resume=False):
    """Replace ONLY verified legacy carried-forward candidates for freezing.

    Keep the untrusted original and all differences in an immutable audit.
    Neither revised observations nor classifications may be promoted.
    """
    from source_research_batches import read_json, save_new, sha
    require(isinstance(research, dict) and isinstance(research.get("evidence"), list),
            "Research evidence is missing for status reconciliation")
    archive = history_index(history_rows)
    revised = copy.deepcopy(research)
    edits = []
    for index, candidate in enumerate(revised["evidence"]):
        status = candidate.get("evidence_status")
        if status == "new":
            require(candidate.get("id") is None,
                    "New evidence must not overwrite a historical ID")
            continue
        if status == "carried_forward":
            old = archived_identity(candidate, candidate.get("id"), archive,
                                    require_unchanged_content=True)
            # No new assertion may be inferred: preserve old historical fields
            # exactly, except the explicit carried-forward marker.
            revised["evidence"][index] = dict(copy.deepcopy(old),
                                             evidence_status="carried_forward")
            continue
        parsed = LEGACY_CARRY.fullmatch(status) if isinstance(status, str) else None
        require(parsed and verified_legacy_resume,
                "Invalid evidence status cannot be normalized on a new research run")
        historical_id = parsed.group(1)
        old = archived_identity(candidate, historical_id, archive,
                                require_unchanged_content=False)
        restored = dict(copy.deepcopy(old), evidence_status="carried_forward")
        revised["evidence"][index] = restored
        differences = {
            field: {"untrusted_model": copy.deepcopy(candidate.get(field)),
                    "archived": copy.deepcopy(old.get(field))}
            for field in sorted(set(candidate) | set(old))
            if (candidate.get(field) != old.get(field)
                and field not in ("id", "evidence_status"))
        }
        edits.append({
            "index": index, "historical_id": historical_id,
            "original_model_record": copy.deepcopy(candidate),
            "archived_original_record": copy.deepcopy(old),
            "effective_carried_forward_record": copy.deepcopy(restored),
            "discarded_differences": differences,
            "action": "RESTORED_EXACT_ARCHIVE_WITH_MODEL_REINTERPRETATION_EXCLUDED",
            "source_claim_verification": "NOT_ESTABLISHED",
        })
    path = Path(folder) / "evidence-status-reconciliation.json"
    if edits:
        record = {
            "version": 1,
            "status": "LEGACY_FORMAT_REPAIRED_FROM_VERIFIED_ARCHIVE_ONLY",
            "original_research_sha256": sha(research),
            "effective_research_sha256": sha(revised),
            "historical_evidence_sha256": sha(history_rows),
            "snapshot_sha256": snapshot["snapshot_sha256"],
            "changes": edits,
            "publication": "NOT AUTHORIZED",
            "limitations": (
                "Only the archived observation is carried forward; new claims, "
                "category changes, or interpretation in the malformed model "
                "record were discarded rather than treated as evidence.")
        }
        if path.exists():
            require(read_json(path) == record,
                    "Saved historical status correction differs from verified archive")
        else:
            save_new(path, record)
    else:
        require(not path.exists(),
                "Unexpected historical status correction without a malformed input")
        record = None
    return revised, record
