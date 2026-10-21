"""Fail-closed Responses transport with durable, redacted request diagnostics.

Only web research uses asynchronous background mode; all requests are issued
exactly once. Once acknowledged, only safe GET requests may be retried.
Background store=False uses temporary retention for polling, not archival
storage; completed analysis is retained only in the project's explicit audit.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ENDPOINT = "https://api.openai.com/v1/responses"
POLL_STATES = frozenset(("queued", "in_progress"))
MAX_POLL_SECONDS = 1200
POLL_INTERVAL_SECONDS = 6
CREATE_TIMEOUT_SECONDS = 60
GET_TIMEOUT_SECONDS = 35
MAX_GET_NETWORK_FAILURES = 3
MAX_POLLS = 240


def _timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _atomic_json(path, value):
    """Durably replace a redacted status record (never a token or prompt)."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _valid_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r"resp_[A-Za-z0-9_-]{2,128}", value))


_RESUMABLE = frozenset((
    "acknowledged", "poll_acknowledged", "safe_get_retry_pending",
    "background_timeout_no_replay", "poll_transport_failed_no_post_retry",
    "poll_http_error_no_post_retry", "api_completed_output_not_yet_validated",
    "resuming_existing_response",
))


def _resume_candidate(folder, fingerprint, model):
    """Only reuse a known, acknowledged ID for an identical research request."""
    folder = Path(folder)
    if not folder.is_dir():
        raise RuntimeError("Resume audit directory missing; no POST attempted")
    matches = []
    for path in sorted(folder.glob("api-request-*.json")):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RuntimeError("Unreadable resume audit; no POST attempted") from None
        if not isinstance(row, dict):
            raise RuntimeError("Malformed resume audit; no POST attempted")
        if row.get("request_sha256") == fingerprint:
            matches.append((path, row))
    if not matches:
        raise RuntimeError("No exact matching background request audit; no POST attempted")
    for _, row in matches:
        if (row.get("model") != model or row.get("background") is not True
                or row.get("store") is not False
                or row.get("status") not in _RESUMABLE
                or row.get("post_attempts") not in (0, 1)
                or not _valid_id(row.get("response_id"))):
            raise RuntimeError("Resume audit not resumable; no POST attempted")
    ids = {row["response_id"] for _, row in matches}
    if len(ids) != 1:
        raise RuntimeError("Ambiguous matching response IDs; no POST attempted")
    return next(iter(ids)), sorted(p.name for p, _ in matches), sum(
        row.get("poll_count", 0) for _, row in matches
        if type(row.get("poll_count")) is int and row["poll_count"] >= 0)


def request_response(payload, *, search, token_supplier, audit_dir,
                     http_error_formatter, opener=None, sleeper=None,
                     monotonic=None, max_poll_seconds=MAX_POLL_SECONDS,
                     resume_dir=None):
    """POST once, then poll the acknowledged background Response with GET.

    A lost POST acknowledgement may represent a billable accepted job: NEVER
    replay it. A known ID remains in the audit for safe, manual inspection.
    The API's error body and any raw exception URL/message are not logged.
    """
    opener = opener or urllib.request.urlopen
    sleeper = sleeper or time.sleep
    monotonic = monotonic or time.monotonic
    payload = dict(payload)
    if search:
        payload["background"] = True
    if payload.get("store") is not False:
        raise ValueError("Iran Responses requests must keep store=false")
    if resume_dir is not None and not search:
        raise ValueError("Only background web research can be resumed")
    audit_dir = Path(audit_dir)
    audit_dir.mkdir(parents=True, exist_ok=True)
    record_path = audit_dir / ("api-request-" + uuid.uuid4().hex + ".json")
    client_request_id = "iran-" + uuid.uuid4().hex
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True,
                      ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    record = {"phase": "web-search research" if search else "non-search assessment/review",
              "client_request_id": client_request_id,
              "request_sha256": fingerprint, "model": payload.get("model"),
              "background": bool(search), "store": False,
              "response_id": None, "status": "prepared_not_sent",
              "created_at": _timestamp(), "post_attempts": 0,
              "safe_get_retries": 0, "poll_count": 0,
              "security": "No prompts, bearer tokens, HTTP response bodies or OIDC claims stored",
              "publication": "not authorized by this audit"}

    def save(status, **extra):
        record.update(status=status, updated_at=_timestamp(), **extra)
        _atomic_json(record_path, record)

    save("prepared_not_sent")
    if resume_dir is not None:
        try:
            response_id, previous_files, prior_polls = _resume_candidate(
                resume_dir, fingerprint, payload.get("model"))
        except RuntimeError:
            save("resume_rejected_no_post")
            raise
        # First GET also retrieves a previously completed response.
        # No billable POST is issued when resumption is explicitly requested.
        status = "queued"
        initial = {"id": response_id, "status": status}
        save("resuming_existing_response", response_id=response_id,
             resumed_from_audits=previous_files, previous_poll_count=prior_polls,
             remote_status="unknown_until_GET")
    else:
        try:
            token = token_supplier()
        except Exception as exc:
            save("authentication_failed", exception_class=type(exc).__name__)
            raise
        req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "X-Client-Request-Id": client_request_id,
                                              "Authorization": "Bearer " + token})
        save("create_sent_acknowledgement_pending", post_attempts=1)
        try:
            with opener(req, timeout=CREATE_TIMEOUT_SECONDS) as response:
                initial = json.load(response)
        except urllib.error.HTTPError as exc:
            save("create_http_error", http_status=exc.code)
            raise http_error_formatter(exc, search) from None
        except (OSError, TimeoutError, ValueError, TypeError) as exc:
            save("create_acknowledgement_unknown_no_replay", exception_class=type(exc).__name__)
            raise RuntimeError("OpenAI Responses CREATE " + type(exc).__name__+
                               "; request acceptance unknown; no automatic POST retry") from None
        if not isinstance(initial, dict) or not _valid_id(initial.get("id")):
            save("invalid_create_acknowledgement")
            raise RuntimeError("OpenAI Responses returned no usable response ID; no POST retry")
        response_id = initial["id"]
        status = initial.get("status")
        save("acknowledged", response_id=response_id, remote_status=status)
    if not search:
        if status != "completed":
            save("nonsearch_not_completed", remote_status=status)
            raise RuntimeError("OpenAI non-search request not completed; no POST retry")
        save("api_completed_output_not_yet_validated", remote_status=status)
        return initial

    start = monotonic()
    response = initial
    poll_count = 0
    consecutive_errors = 0
    while status in POLL_STATES:
        if monotonic() - start >= max_poll_seconds or poll_count >= MAX_POLLS:
            save("background_timeout_no_replay", remote_status=status)
            raise RuntimeError("OpenAI background response did not finish within poll budget; "
                               "known response ID in diagnostic; no POST retry")
        sleeper(POLL_INTERVAL_SECONDS)
        query = urllib.parse.urlencode([("include[]", "web_search_call.action.sources")])
        url = ENDPOINT + "/" + urllib.parse.quote(response_id, safe="") + "?" + query
        try:
            token = token_supplier()  # Can rotate short-lived GitHub WIF tokens.
            get = urllib.request.Request(url, method="GET",
                       headers={"Authorization": "Bearer " + token,
                                "Accept": "application/json"})
            with opener(get, timeout=GET_TIMEOUT_SECONDS) as raw:
                response = json.load(raw)
            if not isinstance(response, dict) or response.get("id") != response_id:
                save("invalid_poll_response", poll_count=poll_count)
                raise RuntimeError("OpenAI background poll returned wrong/unknown response ID")
            poll_count += 1
            consecutive_errors = 0
            status = response.get("status")
            save("poll_acknowledged", poll_count=poll_count, remote_status=status)
        except urllib.error.HTTPError as exc:
            if exc.code in (408, 429, 500, 502, 503, 504):
                consecutive_errors += 1
                save("safe_get_retry_pending", safe_get_retries=record["safe_get_retries"]+1,
                     exception_class="HTTPError", http_status=exc.code)
                if consecutive_errors <= MAX_GET_NETWORK_FAILURES:
                    continue
            save("poll_http_error_no_post_retry", http_status=exc.code)
            raise http_error_formatter(exc, search) from None
        except (OSError, TimeoutError, ValueError, TypeError) as exc:
            consecutive_errors += 1
            save("safe_get_retry_pending", safe_get_retries=record["safe_get_retries"]+1,
                 exception_class=type(exc).__name__)
            if consecutive_errors <= MAX_GET_NETWORK_FAILURES:
                continue
            save("poll_transport_failed_no_post_retry")
            raise RuntimeError("OpenAI background GET failed after bounded safe retries ("+
                               type(exc).__name__+"); no POST retry") from None
    if status != "completed":
        save("background_terminal_failure", remote_status=status)
        raise RuntimeError("OpenAI background request ended with noncompleted status " +
                           (status if status in ("failed", "cancelled", "incomplete")
                            else "unknown") + "; no POST retry")
    save("api_completed_output_not_yet_validated", remote_status=status)
    return response
