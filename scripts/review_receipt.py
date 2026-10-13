#!/usr/bin/env python3
"""Verify that a new assessment was approved outside GitHub before submission.

A receipt is an integrity/accountability record, not a cryptographic signature
or evidence that any claimed review actually took place. Protected PR review
remains necessary. Fail closed for new assessments with no valid receipt.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

from candidate_checks import one_append

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data/history.json"
EASTERN = ZoneInfo("America/New_York")
CORE = ("regional_escalation_90d", "regime_end_12m",
        "currency_crisis_12m", "external_payments_crisis_12m")


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def checked_receipt(before, after, receipt, now=None):
    """Validate one append and exact dual-review approval of the new record."""
    one_append(before, after)
    record = after["updates"][-1]
    date = record["date"]
    require(dt.date.fromisoformat(date).weekday() == 6,
            "Pre-GitHub review receipt can authorize only a Sunday record")
    require(isinstance(receipt, dict) and receipt.get("version") == 1
            and receipt.get("origin") == "off_github"
            and receipt.get("status") == "CLEAN"
            and receipt.get("date") == date,
            "Missing or invalid external review receipt")
    require(receipt.get("baseline_sha256") == digest(before)
            and receipt.get("candidate_sha256") == digest(after)
            and receipt.get("record_sha256") == digest(record),
            "Reviewed candidate/baseline digest mismatch")
    approval = receipt.get("approval")
    require(isinstance(approval, dict) and approval.get("status") == "CLEAN"
            and type(approval.get("round")) is int
            and 1 <= approval["round"] <= 6,
            "No completed dual-role clean approval")
    draft_hash = approval.get("draft_sha256")
    require(isinstance(draft_hash, str) and len(draft_hash) == 64
            and all(ch in "0123456789abcdef" for ch in draft_hash),
            "Invalid reviewed-draft digest")
    for role in ("affirmative", "critical"):
        decision = approval.get(role)
        require(isinstance(decision, dict)
                and decision.get("approved") is True
                and decision.get("issues") == []
                and decision.get("draft_sha256") == draft_hash,
                role + " clean approval missing or belongs to another draft")
    locked = approval.get("locked_forecasts")
    require(isinstance(locked, list) and len(locked) == 4
            and approval.get("forecast_sha256") == digest(locked),
            "Scored forecasts do not match reviewed forecast lock")
    issued = record.get("forecasts")
    require(isinstance(issued, list) and len(issued) == 4,
            "Exactly four scored forecasts required")
    require([x.get("event_id") for x in issued] == list(CORE),
            "Core forecasts missing or out of order")
    reviewed_ids=[x.get("event_id") for x in locked if isinstance(x,dict)]
    require(len(reviewed_ids)==4 and set(reviewed_ids)==set(CORE),
            "Reviewed four core events do not match the frozen protocol")
    by_id={row["event_id"]:row for row in locked}
    for actual in issued:
        reviewed=by_id[actual["event_id"]]
        for field in ("event_id", "p", "range", "confidence"):
            require(reviewed.get(field) == actual.get(field),
                    "Scored forecast changed after clean review: " + field)
        for optional in ("raise", "lower"):
            if optional in reviewed:
                require(reviewed[optional] == actual.get(optional),
                        "Scored forecast narrative changed after review")
    time_string = receipt.get("review_completed_at")
    require(isinstance(time_string, str), "Missing pre-GitHub review completion time")
    reviewed_at = dt.datetime.fromisoformat(time_string)
    require(reviewed_at.tzinfo is not None,
            "Pre-GitHub completion time must include timezone")
    issuance_at = dt.datetime.fromisoformat(record["publication_time"])
    require(issuance_at.tzinfo is not None
            and issuance_at <= reviewed_at
            and reviewed_at.astimezone(EASTERN).date().isoformat() == date,
            "Review must complete on the original Sunday after issuance")
    current = now or dt.datetime.now(dt.timezone.utc)
    require(reviewed_at <= current, "Review cannot have a future completion time")
    return True


def verify_repository_change(baseline_ref, root=ROOT, now=None):
    """Read only the local checkout and git object database. No remote calls."""
    root = Path(root)
    original = subprocess.check_output(
        ["git", "show", baseline_ref + ":data/history.json"], cwd=root)
    before = json.loads(original)
    after = json.loads((root / "data/history.json").read_bytes())
    if before == after:
        return "No assessment change; external receipt not required"
    if len(after.get("updates", [])) == len(before.get("updates", [])):
        # Existing forecast resolution/correction metadata is already governed
        # by frozen validator rules. Do not reissue or rereview old predictions.
        return "No new assessment; historical resolution validator applies"
    receipt_path = (root / "data" / "review-receipts" /
                    (after["updates"][-1]["date"] + ".json"))
    require(receipt_path.is_file(),
            "New assessment has no off-GitHub clean-review receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    checked_receipt(before, after, receipt, now=now)
    return "External two-role clean-review receipt verified"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True,
                        help="PR base commit SHA or before-push SHA")
    args = parser.parse_args()
    print(verify_repository_change(args.baseline_ref))


if __name__ == "__main__":
    main()
