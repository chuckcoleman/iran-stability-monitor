#!/usr/bin/env python3
"""Create and review a Sunday candidate OUTSIDE GitHub before any submission.

Local environment: a checked-out source snapshot, OPENAI_API_KEY and Python
jsonschema. No gh, git push, GitHub Actions, GitHub token or remote API calls.
The prepared output is kept outside the repository until it has passed both
independent reviews and all frozen Protocol v1 validators.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import tempfile

from assessment_pipeline import clock, llm, produce
from candidate_checks import one_append, dashboard_record
from review_receipt import canonical, checked_receipt, digest
from validate_history import validate_history
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent


def require(value, message):
    if not value:
        raise RuntimeError(message)


def check_offline_environment():
    require(os.getenv("GITHUB_ACTIONS") != "true",
            "This assessment must be reviewed outside GitHub Actions")
    require(not os.getenv("GH_TOKEN") and not os.getenv("GITHUB_TOKEN")
            and not os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL"),
            "Do not use a GitHub identity or token during pre-GitHub review")
    require(not os.getenv("OPENAI_IDENTITY_PROVIDER_ID")
            and not os.getenv("OPENAI_SERVICE_ACCOUNT_ID"),
            "GitHub workload identity cannot be used for outside-GitHub review")
    require(bool(os.getenv("OPENAI_API_KEY")),
            "Local pre-GitHub review requires a separately configured OpenAI API credential")


def prepare(out_dir, *, now=None, producer=None):
    """Return paths only after two independent reviews and validation pass."""
    check_offline_environment()
    day = now or clock()
    require(day.tzinfo is not None and day.weekday() == 6,
            "Prospective Sunday assessment must be prepared on Sunday")
    root=ROOT.resolve()
    output=Path(out_dir).expanduser().resolve()
    require(output != root and root not in output.parents,
            "Review artifacts must stay outside the GitHub repository")
    require(not output.exists(), "Output directory already exists; do not overwrite review records")
    source=(ROOT/"data/history.json").read_bytes()
    history=json.loads(source)
    last=dt.date.fromisoformat(history["updates"][-1]["date"])
    require((day.date()-last).days==7,
            "The preceding Sunday record is missing or this candidate already exists")
    with tempfile.TemporaryDirectory(prefix="iran-pre-github-") as temporary:
        saved=os.environ.get("IRAN_OFFLINE_REVIEW_DIR")
        os.environ["IRAN_OFFLINE_REVIEW_DIR"]=temporary
        try:
            # No GitHub API calls, git commands, PRs, or site/social writes.
            candidate=(producer or produce)(history,reviewer=llm)
        finally:
            if saved is None:
                os.environ.pop("IRAN_OFFLINE_REVIEW_DIR",None)
            else:
                os.environ["IRAN_OFFLINE_REVIEW_DIR"]=saved
        one_append(history,candidate)
        validate_history(candidate,history)
        schema=json.loads((ROOT/"schema/history.schema.json").read_bytes())
        Draft202012Validator(schema).validate(candidate)
        dashboard_record(candidate["updates"][-1],history["updates"][-1])
        approval_file=Path(temporary)/"review-approval.json"
        require(approval_file.is_file(),
                "Both external reviews have not produced a clean approval receipt")
        approval=json.loads(approval_file.read_text(encoding="utf-8"))
        review_date=dt.datetime.now(dt.timezone.utc)
        receipt={
            "version":1,"origin":"off_github","status":"CLEAN",
            "date":candidate["updates"][-1]["date"],
            "baseline_sha256":digest(history),
            "record_sha256":digest(candidate["updates"][-1]),
            "candidate_sha256":digest(candidate),
            "review_completed_at":review_date.isoformat(timespec="seconds"),
            "approval":approval
        }
        checked_receipt(history,candidate,receipt,now=review_date)
        # Only fully approved candidates reach the external handoff folder.
        output.mkdir(parents=True)
        try:
            data=output/"data"
            evidence=data/"review-receipts"
            audit=output/"review-audit"
            evidence.mkdir(parents=True)
            audit.mkdir()
            (output/"history-before.json").write_bytes(source)
            (data/"history.json").write_text(
                json.dumps(candidate,ensure_ascii=False,indent=2)+"\n",
                encoding="utf-8")
            (evidence/(receipt["date"]+".json")).write_text(
                json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",
                encoding="utf-8")
            for src in Path(temporary).glob("review-*.json"):
                shutil.copyfile(src,audit/src.name)
            # One final readback; never deliver corrupt/incomplete handoff.
            from review_receipt import checked_receipt
            verify=json.loads((data/"history.json").read_text(encoding="utf-8"))
            handoff=json.loads((evidence/(receipt["date"]+".json")).read_text(encoding="utf-8"))
            checked_receipt(history,verify,handoff,now=review_date)
        except BaseException:
            shutil.rmtree(output,ignore_errors=True)
            raise
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",required=True,
                        help="New directory OUTSIDE the GitHub working tree")
    args=parser.parse_args()
    result=prepare(args.output_dir)
    print("Clean affirmative and critical reviews, then full schema and "
          "Protocol-v1 validation: PASSED.")
    print("External reviewed candidate staged at: "+str(result))
    print("No GitHub usage, repository mutation, website deployment or X posting occurred.")


if __name__=="__main__":
    main()
