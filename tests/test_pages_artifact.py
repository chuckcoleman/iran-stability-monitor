"""Fail-closed regression tests for the uploaded Pages artifact comparator."""
from __future__ import annotations
import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from verify_pages_artifact import verify

SHA = "a" * 40


class PagesArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.site = self.base / "_site"
        self.repo = self.base / "repo"
        self.site.mkdir()
        self.repo.mkdir()
        self.tar = self.base / "artifact.tar"
        self.data = {
            "index.html": b"<html>OK</html>",
            "data/history.json": b"{}",
            ".nojekyll": b"",
        }
        for name, data in self.data.items():
            for root in (self.site, self.repo):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
        self.package(self.data)

    def package(self, data):
        with tarfile.open(self.tar, "w") as tar:
            for name, content in data.items():
                info = tarfile.TarInfo("./" + name)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))

    def test_exact_artifact(self):
        result = verify(self.site, self.repo, self.tar, SHA)
        self.assertEqual(result["result"], "pass")
        self.assertEqual(set(result["files"]), set(self.data))

    def test_tampered_artifact(self):
        bad = dict(self.data)
        bad["data/history.json"] = b'{"tampered":true}'
        self.package(bad)
        with self.assertRaisesRegex(ValueError, "bytes"):
            verify(self.site, self.repo, self.tar, SHA)

    def test_absent_member(self):
        bad = dict(self.data)
        bad.pop("index.html")
        self.package(bad)
        with self.assertRaisesRegex(ValueError, "file set"):
            verify(self.site, self.repo, self.tar, SHA)

    def test_extra_member(self):
        bad = dict(self.data)
        bad["secrets.txt"] = b"secret"
        self.package(bad)
        with self.assertRaisesRegex(ValueError, "file set"):
            verify(self.site, self.repo, self.tar, SHA)

    def test_hidden_marker_omitted_from_archive_fails_closed(self):
        # upload-pages-artifact@v4 strips dotfiles; staging .nojekyll must
        # therefore fail unless the staging script is changed to omit it.
        self.package({name: data for name, data in self.data.items() if name != ".nojekyll"})
        with self.assertRaisesRegex(ValueError, r"missing=.*nojekyll"):
            verify(self.site, self.repo, self.tar, SHA)

    def test_wrong_source_bytes(self):
        (self.repo / "index.html").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "repository bytes"):
            verify(self.site, self.repo, self.tar, SHA)

    def test_symlink_member(self):
        with tarfile.open(self.tar, "w") as tar:
            info = tarfile.TarInfo("index.html")
            info.type = tarfile.SYMTYPE
            info.linkname = "/tmp/secret"
            tar.addfile(info)
        with self.assertRaisesRegex(ValueError, "Nonregular"):
            verify(self.site, self.repo, self.tar, SHA)

    def test_duplicate_member(self):
        with tarfile.open(self.tar, "w") as tar:
            for _ in range(2):
                info = tarfile.TarInfo("index.html")
                info.size = 1
                tar.addfile(info, io.BytesIO(b"X"))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            verify(self.site, self.repo, self.tar, SHA)


if __name__ == "__main__":
    unittest.main()
