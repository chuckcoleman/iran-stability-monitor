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
from report_section_review import (REPORT_SECTIONS, validate_report_section_reviews)

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


def checked_receipt(before, after, receipt, now=None, reviewed_draft=None, report_bytes=None):
    """Validate legacy review receipts and prospective alternating ChatGPT reviews."""
    one_append(before, after)
    record = after["updates"][-1]
    date = record["date"]
    require(dt.date.fromisoformat(date).weekday() == 6,
            "Pre-GitHub review receipt can authorize only a Sunday record")
    require(isinstance(receipt, dict) and receipt.get("status") == "CLEAN"
            and receipt.get("date") == date,
            "Missing or invalid review receipt")
    # Version-1 receipts are historical only. The published 2026-10-18
    # assessment used version 2; all 2026-10-25+ assessments require version 3.
    legacy = (receipt.get("version") == 1
              and receipt.get("origin") == "off_github"
              and date < "2026-10-18")
    chat_critical = (receipt.get("version") == 2 and receipt.get("origin") == "chatgpt_critical"
                     and receipt.get("review_mode") == "single_critical_chat"
                     and date >= "2026-10-18")
    alternating = (receipt.get("version") == 3
                   and receipt.get("origin") == "chatgpt_alternating"
                   and receipt.get("review_mode") == "affirmative_then_critical_chat"
                   and receipt.get("reviewer_provenance") == "one_chatgpt_session_two_perspectives"
                   and date >= "2026-10-25")
    require(legacy or (chat_critical and date < "2026-10-25") or alternating,
            "Unknown or unauthorized review policy/version")
    require(receipt.get("baseline_sha256") == digest(before)
            and receipt.get("candidate_sha256") == digest(after)
            and receipt.get("record_sha256") == digest(record),
            "Reviewed candidate/baseline digest mismatch")
    approval = receipt.get("approval")
    require(isinstance(approval, dict) and approval.get("status") == "CLEAN"
            and type(approval.get("round")) is int
            and 1 <= approval["round"] <= 6,
            "No completed clean approval")
    draft_hash = approval.get("draft_sha256")
    require(isinstance(draft_hash, str) and len(draft_hash) == 64
            and all(ch in "0123456789abcdef" for ch in draft_hash),
            "Invalid reviewed-draft digest")
    if chat_critical or alternating:
        require(isinstance(reviewed_draft, dict) and isinstance(report_bytes, bytes),
                "Chat critical review requires immutable draft and report artifacts")
        require(draft_hash == digest(reviewed_draft), "Reviewed chat draft digest mismatch")
        require(reviewed_draft.get("updates", [])[:-1] == before.get("updates", [])
                and len(reviewed_draft.get("updates", [])) == len(after.get("updates", []))
                and {key: value for key, value in reviewed_draft.items() if key != "updates"}
                    == {key: value for key, value in after.items() if key != "updates"},
                "Reviewed chat draft baseline or root metadata changed")
        reviewed_record = dict(reviewed_draft["updates"][-1])
        actual_record = dict(record)
        reviewed_record.pop("publication_time", None)
        actual_record.pop("publication_time", None)
        require(reviewed_record == actual_record,
                "Reviewed chat draft changed after approval beyond publication timestamp")
        require(receipt.get("report_sha256") == hashlib.sha256(report_bytes).hexdigest(),
                "Critical review report digest mismatch")
        report_text = report_bytes.decode("utf-8")
        if chat_critical:
            require(draft_hash in report_text
                    and "Approved for final timestamping and complete deterministic revalidation: yes." in report_text
                    and "**Issues:** " + chr(96) + "[]" + chr(96) in report_text,
                    "Chat review report does not document clean approval of this draft")
            require(approval.get("affirmative") is None,
                    "Legacy chat critical mode cannot claim an affirmative review")
        else:
            for role in ("Affirmative", "Critical"):
                line = (role + " verdict: approved=true; issues=[]; draft_sha256="
                        + draft_hash)
                require(line in report_text,
                        role + " review report lacks an exact same-draft clean verdict")
            require("Both review perspectives are from one ChatGPT session" in report_text,
                    "Chat review provenance absent in report")
            for name in REPORT_SECTIONS:
                require("### " + name in report_text,
                        "Full report lacks the " + name + " review section")
    for role in (("affirmative", "critical") if legacy or alternating else ("critical",)):
        decision = approval.get(role)
        require(isinstance(decision, dict)
                and decision.get("approved") is True
                and decision.get("issues") == []
                and decision.get("draft_sha256") == draft_hash,
                role + " clean approval missing or belongs to another draft")
    if alternating:
        rounds = approval.get("rounds")
        require(isinstance(rounds, list) and len(rounds) == approval["round"]
                and 1 <= len(rounds) <= 6,
                "Every review round must be documented; maximum six")
        last_hash, last_critical_time, started = None, None, None
        def parsed_time(value):
            require(isinstance(value, str), "Missing review or validation time")
            stamp = dt.datetime.fromisoformat(value)
            require(stamp.tzinfo is not None, "Review/validation time lacks offset")
            return stamp
        for index, item in enumerate(rounds):
            require(isinstance(item, dict) and item.get("round") == index + 1,
                    "Review round numbers must be sequential")
            round_hash = item.get("draft_sha256")
            require(isinstance(round_hash, str) and len(round_hash) == 64
                    and all(c in "0123456789abcdef" for c in round_hash)
                    and round_hash != last_hash,
                    "A revised draft must have a new 64-character SHA-256")
            require(item.get("forecast_sha256") == approval.get("forecast_sha256"),
                    "Four scored forecast locks changed during review")
            validation = item.get("validation")
            require(isinstance(validation, dict) and validation.get("passed") is True,
                    "Full deterministic pre-review validation was not clean")
            validation_time = parsed_time(validation.get("completed_at"))
            if started is None:
                started = validation_time
            if last_critical_time is not None:
                require(last_critical_time < validation_time,
                        "Revised draft not fully validated after previous reviews")
            affirmative = item.get("affirmative")
            critical = item.get("critical")
            require(isinstance(affirmative, dict) and isinstance(critical, dict),
                    "Each round needs affirmative followed by critical review")
            affirmative_time = parsed_time(affirmative.get("completed_at"))
            critical_time = parsed_time(critical.get("completed_at"))
            require(validation_time <= affirmative_time < critical_time,
                    "Required order: validate, affirmative, critical")
            validate_report_section_reviews(
                item.get("section_reviews"), reviewed_record, round_hash,
                final_round=(index == len(rounds) - 1),
                role_approvals={"affirmative": affirmative.get("approved"),
                                "critical": critical.get("approved")})
            for role, decision in (("affirmative", affirmative), ("critical", critical)):
                require(decision.get("draft_sha256") == round_hash
                        and type(decision.get("approved")) is bool
                        and isinstance(decision.get("issues"), list),
                        role + " verdict must identify the same exact draft")
                if decision["approved"]:
                    require(decision["issues"] == [],
                            "Reviewer with issues cannot approve")
                else:
                    require(bool(decision["issues"]),
                            "Reviewer rejection must document actionable defects")
            final = index == len(rounds) - 1
            if final:
                require(round_hash == draft_hash
                        and affirmative["approved"] and critical["approved"]
                        and affirmative["issues"] == [] and critical["issues"] == [],
                        "Both final reviewers must approve the identical draft")
                post = item.get("post_review_validation")
                require(isinstance(post, dict) and post.get("passed") is True,
                        "Missing full post-review validation")
                post_time = parsed_time(post.get("completed_at"))
                require(critical_time <= post_time,
                        "Full final validation must follow critical approval")
                require(parsed_time(receipt.get("review_completed_at")) == critical_time,
                        "Review completion must equal the final critical decision time")
                require(post_time - started <= dt.timedelta(minutes=60),
                        "Review phase exceeded sixty minutes")
            else:
                require(not (affirmative["approved"] and critical["approved"]),
                        "Cannot revise after an already clean approval")
                require(item.get("post_review_validation") is None,
                        "Rejected round cannot claim final validation")
            last_hash, last_critical_time = round_hash, critical_time
        section_sha = digest(rounds[-1]["section_reviews"])
        require(receipt.get("report_section_review_sha256") == section_sha
                and "Section review matrix SHA-256: " + section_sha in report_text,
                "Full report section-review matrix is absent or unbound")
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
    if legacy:
        require(issuance_at.tzinfo is not None
                and issuance_at <= reviewed_at
                and reviewed_at.astimezone(EASTERN).date().isoformat() == date,
                "Review must complete on the original Sunday after issuance")
    else:
        opened = dt.datetime.fromisoformat(record["forecasts"][0]["forecast_open"])
        require(issuance_at.tzinfo is not None and opened.tzinfo is not None
                and opened <= reviewed_at <= issuance_at
                and reviewed_at.astimezone(EASTERN).date().isoformat() == date
                and issuance_at.astimezone(EASTERN).date().isoformat() == date,
                "Critical review must follow opening and precede actual Sunday issuance")
    if alternating:
        require(post_time <= issuance_at, "Final validation must precede issuance")
    current = now or dt.datetime.now(dt.timezone.utc)
    require(reviewed_at <= current, "Review cannot have a future completion time")
    return True


def verify_all_chatgpt_source_dossiers(root, history):
    """Read-only certification of ALL retained no-API provenance snapshots.

    A code-only PR must not be able to alter a source dossier or its reviewer
    reference without a new publication record. Rebuild the exact original
    prefix that a prospective Sunday receipt bound. No API calls or external
    fetching occur. This is integrity checking, not external fact proof.
    """
    from chatgpt_handoff import validate_optional_dossier
    root = Path(root)
    evidence_dir = root / "data" / "source-dossiers"
    receipts_dir = root / "data" / "review-receipts"
    rows = history.get("updates")
    require(isinstance(rows, list), "Historical assessment records missing")
    by_date = {u["date"]: i for i, u in enumerate(rows)}
    require(len(by_date) == len(rows),
            "Duplicate historical assessment dates")
    count = 0
    for path in sorted(evidence_dir.glob("*.json")):
        require(path.stem in by_date and path.name == path.stem + ".json",
                "Unexpected unbound or malformed ChatGPT source dossier")
        receipt_path = receipts_dir / path.name
        require(receipt_path.is_file(),
                "ChatGPT source dossier lacks a matching review receipt")
        receipt = json.loads(receipt_path.read_bytes())
        require(receipt.get("research_mode") == "chatgpt_first_no_api",
                "Source dossier was detached from its original review receipt")
        index = by_date[path.stem]
        require(index > 0, "Source dossier cannot certify first historic record")
        before = dict(history, updates=rows[:index])
        after = dict(history, updates=rows[:index + 1])
        dossier = json.loads(path.read_bytes())
        validate_optional_dossier(before, after, receipt, dossier)
        count += 1
    for path in sorted(receipts_dir.glob("*.json")):
        receipt = json.loads(path.read_bytes())
        if receipt.get("research_mode") == "chatgpt_first_no_api":
            require((evidence_dir / path.name).is_file(),
                    "Missing bound ChatGPT source dossier for prior receipt")
    return count


def verify_repository_change(baseline_ref, root=ROOT, now=None):
    """Read only the local checkout and git object database. No remote calls."""
    root = Path(root)
    original = subprocess.check_output(
        ["git", "show", baseline_ref + ":data/history.json"], cwd=root)
    before = json.loads(original)
    after = json.loads((root / "data/history.json").read_bytes())
    # Validate all extant ChatGPT provenance even on a code-only change.
    # A changed dossier with unchanged data/history.json is not an exemption.
    verify_all_chatgpt_source_dossiers(root, after)
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
    if receipt.get("version") in (2, 3):
        date = after["updates"][-1]["date"]
        draft_file = root / "data" / "review-drafts" / (date + ".json")
        report_file = root / "data" / "review-reports" / (date + ".md")
        require(draft_file.is_file() and report_file.is_file(),
                "Missing chat critical review's exact draft or report")
        checked_receipt(before, after, receipt, now=now,
                        reviewed_draft=json.loads(draft_file.read_bytes()),
                        report_bytes=report_file.read_bytes())
        if receipt.get("research_mode") is not None:
            from chatgpt_handoff import validate_optional_dossier
            dossier_file = root / "data" / "source-dossiers" / (date + ".json")
            require(dossier_file.is_file(),
                    "ChatGPT-first research receipt lacks source dossier")
            validate_optional_dossier(
                before, after, receipt,
                json.loads(dossier_file.read_bytes()))
        return "ChatGPT alternating receipt, complete source dossier and review artifacts verified"
    require(receipt.get("research_mode") is None,
            "New ChatGPT-first provenance cannot use a historical receipt")
    checked_receipt(before, after, receipt, now=now)
    return "Legacy external two-role clean-review receipt verified"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True,
                        help="PR base commit SHA or before-push SHA")
    args = parser.parse_args()
    print(verify_repository_change(args.baseline_ref))


if __name__ == "__main__":
    main()
