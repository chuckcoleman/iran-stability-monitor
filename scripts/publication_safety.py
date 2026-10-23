"""Production-only rejection of explicitly synthetic handoff artifacts.

Fixtures may run solely in an isolated test checkout. No flag on an upload or
repository receipt can authorize publishing synthetic results. This tests
obvious fixture contamination, not the truth of a superficially plausible lie.
"""
import re
from pathlib import Path
from urllib.parse import urlsplit

TEST_MARKERS = ("DO_NOT_PUBLISH.txt", ".test-only", "TEST_ONLY", "SYNTHETIC_FIXTURE")
FAKE_TEXT = re.compile(r"\b(synthetic|test fixture|not for publication|do.not.publish)\b", re.I)


def require_production_material(record, dossier=None, folder=None):
    """Fail closed on obvious synthetic evidence and test-only file markers."""
    if folder is not None:
        base = Path(folder)
        for marker in TEST_MARKERS:
            if any(p.is_file() for p in base.rglob(marker)):
                raise ValueError("Test-only marker blocks production submission: " + marker)
    if not isinstance(record, dict) or record.get("test_only") is True:
        raise ValueError("Synthetic assessment marker blocks publication")
    if dossier is not None and (not isinstance(dossier, dict)
                                or dossier.get("test_only") is True):
        raise ValueError("Synthetic source dossier marker blocks publication")
    for row in record.get("evidence", []):
        for key in ("observation", "publisher"):
            value = row.get(key, "")
            if isinstance(value, str) and FAKE_TEXT.search(value):
                raise ValueError("Synthetic evidence blocks publication: " + key)
    urls = [row.get("source") for row in record.get("evidence", [])]
    if dossier is not None:
        urls += [u for c in dossier.get("coverage", []) for u in
                 c.get("original_urls", [])]
    for u in urls:
        if not isinstance(u, str):
            continue  # URLs are fully checked by the separate source validators.
        host = (urlsplit(u).hostname or "").lower()
        if host in ("example.com", "example.org", "example.net", "localhost") \
                or host.endswith((".example.com", ".example.org", ".example.net",
                                  ".example", ".invalid", ".test")):
            raise ValueError("Reserved synthetic source URL blocks production: " + host)
    return True
