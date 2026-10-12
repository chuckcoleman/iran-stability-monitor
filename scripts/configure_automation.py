#!/usr/bin/env python3
"""Owner-run setup helper. Hidden secret entry; no forecast or social publication.

Requires an already authenticated GitHub CLI. Stores the Metricool credential and,
optionally, the GitHub App private PEM key via gh secret set stdin. Can set the
non-secret GitHub App Client ID and strengthen existing ruleset protection.
Both production flags remain OFF after any setup operation.
"""
import argparse
import getpass
import json
import os
import re
from pathlib import Path
import subprocess
import sys

REPO = "chuckcoleman/iran-stability-monitor"
RULESET = "24824611"


def command(args, payload=None):
    p = subprocess.run(["gh", *args], input=payload, text=True, capture_output=True)
    if p.returncode:
        # Do not echo key material, request bodies, or environment variables.
        raise RuntimeError("GitHub setup operation failed: " + " ".join(args[:3]))
    return p.stdout


def protect():
    rule = json.loads(command(["api", f"repos/{REPO}/rulesets/{RULESET}"]))
    if rule.get("enforcement") != "active" or rule.get("bypass_actors"):
        raise RuntimeError("Existing ruleset must be active with no bypass actors")
    found = False
    for row in rule.get("rules", []):
        if row.get("type") == "required_status_checks":
            names = row["parameters"].get("required_status_checks", [])
            if any(x.get("context") == "validate" and x.get("integration_id") == 15368 for x in names):
                row["parameters"]["strict_required_status_checks_policy"] = True
                found = True
    if not found:
        raise RuntimeError("Existing required GitHub Actions validate check not found")
    allowed = ("name", "target", "enforcement", "bypass_actors", "conditions", "rules")
    payload = {key: rule[key] for key in allowed if key in rule}
    command(["api", "-X", "PUT", f"repos/{REPO}/rulesets/{RULESET}", "--input", "-"], json.dumps(payload))
    result = json.loads(command(["api", f"repos/{REPO}/rulesets/{RULESET}"]))
    if not any(x.get("type") == "required_status_checks" and
               x.get("parameters", {}).get("strict_required_status_checks_policy") is True
               for x in result.get("rules", [])):
        raise RuntimeError("Strict branch checking did not persist")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-secrets", action="store_true", help="Prompt privately for the Metricool API token")
    parser.add_argument("--app-client-id", help="Non-secret GitHub App Client ID (usually Iv1...)")
    parser.add_argument("--app-private-key-file", type=Path,
                        help="Path to the downloaded GitHub App private .pem file (never in repository)")
    parser.add_argument("--strict-protection", action="store_true", help="Require up-to-date CI in existing ruleset")
    args = parser.parse_args()
    if not (args.store_secrets or args.strict_protection or args.app_client_id or args.app_private_key_file):
        parser.print_help()
        return 0
    if not sys.stdin.isatty():
        raise RuntimeError("Owner setup requires an interactive terminal")
    command(["auth", "status"])
    details = json.loads(command(["api", f"repos/{REPO}"]))
    if details.get("permissions", {}).get("admin") is not True:
        raise RuntimeError("Owner/admin authentication required for setup")
    for name in ("ASSESSMENT_AUTOMATION_ENABLED", "AUTO_X_ENABLED"):
        command(["variable", "set", name, "--repo", REPO, "--body", "false"])
    if args.strict_protection:
        protect()
        print("Existing protection strengthened; no PR/check bypass added.")
    if args.app_client_id:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", args.app_client_id):
            raise RuntimeError("Invalid GitHub App Client ID format")
        command(["variable", "set", "IRAN_GITHUB_APP_CLIENT_ID", "--repo", REPO, "--body", args.app_client_id])
        print("Non-secret GitHub App Client ID saved.")
    if args.app_private_key_file:
        path = args.app_private_key_file.resolve()
        root = Path(__file__).resolve().parent.parent
        if path == root or root in path.parents:
            raise RuntimeError("Private key must not be stored inside the repository")
        material = path.read_text(encoding="utf-8")
        if not (material.startswith("-----BEGIN RSA PRIVATE KEY-----") or
                material.startswith("-----BEGIN PRIVATE KEY-----")):
            raise RuntimeError("Invalid GitHub App private key PEM file")
        command(["secret", "set", "IRAN_GITHUB_APP_PRIVATE_KEY", "--repo", REPO], material)
        material = None
        print("GitHub App private key stored securely; private PEM must remain outside repository.")
    if args.store_secrets:
        for name in ("METRICOOL_API_TOKEN",):
            value = getpass.getpass(name + " (hidden; Enter keeps an existing secret): ").strip()
            if value:
                command(["secret", "set", name, "--repo", REPO], value)
                value = None
                print(name + " stored in GitHub; value not displayed.")
        command(["variable", "set", "IRAN_FORECAST_MODEL", "--repo", REPO, "--body", "gpt-6.1-sol"])
    print("Production remains OFF. Run check-services, then dry-run; enable only after both pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
