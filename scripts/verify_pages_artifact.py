"""Verify the downloaded GitHub Pages artifact against exact repository bytes.

This verifies the uploaded Pages payload, not what the public custom domain serves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
from datetime import datetime, timezone


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_bytes(root: Path) -> dict[str, bytes]:
    result = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symlink forbidden: {path}")
        if path.is_file():
            name = path.relative_to(root).as_posix()
            if name.startswith(".git/") or name.startswith(".github/"):
                raise ValueError(f"Repository metadata forbidden: {name}")
            result[name] = path.read_bytes()
    if not result:
        raise ValueError(f"Empty site directory: {root}")
    return result


def _tar_bytes(path: Path) -> dict[str, bytes]:
    result = {}
    with tarfile.open(path, mode="r:*") as archive:
        for member in archive:
            name = member.name.removeprefix("./")
            if name in ("", "."):
                continue
            parts = PurePosixPath(name).parts
            if member.name.startswith("/") or ".." in parts or "\\" in name:
                raise ValueError(f"Unsafe archive name: {member.name}")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"Nonregular archive member: {name}")
            if name in result:
                raise ValueError(f"Duplicate archive member: {name}")
            f = archive.extractfile(member)
            if f is None:
                raise ValueError(f"Cannot read archive member: {name}")
            result[name] = f.read()
    if not result:
        raise ValueError("Empty Pages artifact")
    return result


def verify(site: Path, checkout: Path, downloaded_tar: Path, git_sha: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", git_sha):
        raise ValueError("Expected exact 40-character Git commit SHA")
    staged = _file_bytes(site)
    archived = _tar_bytes(downloaded_tar)
    if archived.keys() != staged.keys():
        raise ValueError(
            f"Pages archive file set differs from staged site: "
            f"missing={sorted(staged.keys() - archived.keys())}, "
            f"extra={sorted(archived.keys() - staged.keys())}"
        )
    for name in sorted(staged):
        if name.startswith(".") and name != ".nojekyll":
            raise ValueError(f"Unapproved hidden file: {name}")
        source = checkout / name
        if not source.is_file() or source.is_symlink():
            if name == ".nojekyll" and staged[name] == archived[name] == b"":
                continue
            raise ValueError(f"Pages file missing from repository checkout: {name}")
        if archived[name] != staged[name] or archived[name] != source.read_bytes():
            raise ValueError(f"Pages artifact does not match repository bytes: {name}")
    return {
        "verification": "downloaded_pages_archive_vs_exact_git_checkout_files",
        "result": "pass",
        "commit_sha": git_sha,
        "verified_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "artifact_tar_sha256": digest(downloaded_tar.read_bytes()),
        "files": {name: digest(archived[name]) for name in sorted(archived)},
        "scope": "uploaded GitHub Pages artifact only; canonical domain not verified",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=Path, required=True)
    ap.add_argument("--checkout", type=Path, required=True)
    ap.add_argument("--downloaded-tar", type=Path, required=True)
    ap.add_argument("--commit-sha", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    receipt = verify(args.site, args.checkout, args.downloaded_tar, args.commit_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"VERIFIED downloaded Pages artifact matches {len(receipt['files'])} source files at {args.commit_sha}")
    print("Canonical domain NOT verified by this attestation.")


if __name__ == "__main__":
    main()
