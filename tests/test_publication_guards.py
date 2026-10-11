"""Bounded, no-network source and publication tests."""
import base64
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import source_metadata as m
import verify_publication as v
from automation_fixtures import fixture, ZONE


class SourceMetadataTests(unittest.TestCase):
    def test_exact_article_time(self):
        result = m.parse_metadata('<html><title>Sample</title><meta property="article:published_time" content="2026-10-11T09:00:00-04:00"></html>')
        self.assertEqual(result["source_publication_time"], "2026-10-11T13:00:00+00:00")

    def test_jsonld_published_not_modified(self):
        obj = {"@type": "NewsArticle", "datePublished": "2026-10-10T12:00:00Z", "dateModified": "2026-10-15T14:00:00Z"}
        result = m.parse_metadata('<script type="application/ld+json">' + json.dumps(obj) + '</script>')
        self.assertEqual(result["source_publication_time"], "2026-10-10T12:00:00+00:00")

    def test_naive_or_conflicting_dates_stay_unknown(self):
        raw = '<meta name="pubdate" content="2026-10-11T09:00:00">'
        self.assertIsNone(m.parse_metadata(raw)["source_publication_time"])
        raw = '<meta name="pubdate" content="2026-10-11T09:00:00Z"><meta name="pubdate" content="2026-10-11T10:00:00Z">'
        self.assertIsNone(m.parse_metadata(raw)["source_publication_time"])
        self.assertEqual(len(m.parse_metadata(raw)["publication_candidates"]), 2)

    def test_preserve_query_identity_strip_tracking(self):
        self.assertNotEqual(m.url_key('https://example.org/news?id=1'), m.url_key('https://example.org/news?id=2'))
        self.assertEqual(m.url_key('https://example.org/news?id=1&utm_source=x'), 'https://example.org/news?id=1')

    def test_unsafe_source_urls_rejected(self):
        for url in ('http://example.org', 'https://127.0.0.1/a', 'https://user:pass@example.org',
                    'https://example.org/" onload="bad', 'https://example.local/a'):
            self.assertIsNone(m.url_key(url))

    def test_network_failure_explicit_unknown(self):
        with patch.object(m, 'assert_public_host', side_effect=OSError('unavailable')):
            result = m.capture_metadata('https://example.org/news', now=lambda: dt.datetime(2026, 10, 11, 14, tzinfo=dt.timezone.utc))
        self.assertIsNone(result['source_publication_time'])
        self.assertIn('unavailable', result['retrieval_status'])
        self.assertEqual(result['source_retrieved_at'], '2026-10-11T14:00:00+00:00')


class PublicationTests(unittest.TestCase):
    def run_data(self):
        run = {'head_sha': 'abc', 'head_branch': 'main', 'event': 'push', 'path': '.github/workflows/validate.yml',
               'name': 'Validate and publish monitor', 'status': 'completed', 'conclusion': 'success'}
        jobs = [{'name': n, 'status': 'completed', 'conclusion': 'success', 'head_sha': 'abc'}
                for n in ('validate', 'Deploy validated website')]
        return run, jobs

    def test_only_bound_gated_run_accepted(self):
        run, jobs = self.run_data()
        v.validate_run(run, jobs, 'abc')
        for key, value in [('head_sha', 'wrong'), ('event', 'dynamic'), ('head_branch', 'other'),
                           ('path', '.github/workflows/pages.yml'), ('conclusion', 'failure')]:
            bad = copy.deepcopy(run); bad[key] = value
            with self.assertRaises(RuntimeError): v.validate_run(bad, jobs, 'abc')

    def test_deploy_cannot_be_skipped(self):
        run, jobs = self.run_data()
        jobs[-1]['conclusion'] = 'skipped'
        with self.assertRaisesRegex(RuntimeError, 'Gated job'):
            v.validate_run(run, jobs, 'abc')

    def test_exact_public_json_required(self):
        raw = b'{"updates":[{"date":"2026-10-11"}]}'
        with patch.object(v, 'request_bytes', return_value=raw):
            v.verify_public(raw, tries=1)
        with patch.object(v, 'request_bytes', return_value=b'{"updates":[]}'):
            with self.assertRaisesRegex(RuntimeError, 'differs'):
                v.verify_public(raw, tries=1)

    def test_canonical_redirect_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'Redirect'):
            v.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.org')

    def test_new_record_is_fresh_and_sunday(self):
        h, a, e, opened = fixture()
        before = copy.deepcopy(h); after = copy.deepcopy(h)
        u = copy.deepcopy(h['updates'][-1]); u['date'] = opened.date().isoformat(); u['publication_time'] = opened.isoformat()
        after['updates'].append(u)
        self.assertEqual(v.fresh_record(before, after, opened + dt.timedelta(minutes=20)), u['date'])
        with self.assertRaisesRegex(RuntimeError, 'Stale'):
            v.fresh_record(before, after, opened + dt.timedelta(days=2))
        after['protocol']['version'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'metadata'):
            v.fresh_record(before, after, opened + dt.timedelta(minutes=20))


if __name__ == '__main__': unittest.main()
