"""Mocked side-effect ordering, duplicate checks and API acknowledgments."""
import contextlib
import copy
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import metricool_publish as x
from automation_fixtures import fixture, ZONE


class MetricoolTests(unittest.TestCase):
    def setUp(self):
        self.h, _, _, _ = fixture()
        self.h['updates'][-1]['social_summary'] = 'Military pressure increased; diplomacy remains an offset.'
        self.day = self.h['updates'][-1]['date']
        self.now = dt.datetime.combine(dt.date.fromisoformat(self.day), dt.time(16), ZONE)

    def test_text_dynamic_dates_and_probabilities(self):
        text = x.draft_text(self.h)
        self.assertLessEqual(len(text), 280)
        for date in (self.day, self.h['updates'][-2]['date']): self.assertIn(date, text)
        for row in self.h['updates'][-1]['forecasts'][:2]: self.assertIn(f"{row['p']}%", text)
        self.assertIn(x.CANONICAL, text)
        self.assertNotIn('iranstabilitymonitor.com', text)

    def test_missing_reviewed_summary_blocks(self):
        del self.h['updates'][-1]['social_summary']
        with self.assertRaisesRegex(RuntimeError, 'summary'): x.draft_text(self.h)

    def test_unknown_or_partial_calendar_blocks(self):
        for response in ({'wrong': []}, {'data': [], 'page': {'total': 9}}, {'data': [], 'page': {'next': 'cursor'}}):
            with self.assertRaises(RuntimeError): x.list_data(response)
        self.assertEqual(x.list_data({'data': [], 'page': None}), [])

    def test_published_csv_is_distinct_from_scheduler(self):
        csv = 'Date,Text,Impressions\n' + self.day + ',Iran ' + self.day + ' update,10\n'
        posts = x.parse_published_csv(csv)
        self.assertTrue(x.matches_assessment(posts[0], self.day))
        with self.assertRaises(RuntimeError): x.parse_published_csv('{"data":[]}')
        with self.assertRaises(RuntimeError): x.parse_published_csv('Date,Views\n2026-10-11,10\n')
        self.assertEqual(x.parse_published_csv('Date,Text\n'), [])

    def test_duplicate_works_with_shortened_url(self):
        post = {'text': 'Iran ' + self.day + ' assessment https://t.co/abc', 'providers': [{'network': 'twitter'}]}
        self.assertTrue(x.matches_assessment(post, self.day))

    def test_brand_identity_required(self):
        brand = {'id': 7254821, 'userId': 5607453, 'timezone': 'America/New_York', 'networksData': {'twitterData': 'IranStabilityMo'}}
        with patch.object(x, 'metricool', return_value={'data': [brand]}): x.check_brand()
        brand['timezone'] = 'Europe/Madrid'
        with patch.object(x, 'metricool', return_value=[brand]):
            with self.assertRaisesRegex(RuntimeError, 'timezone'): x.check_brand()

    def test_brand_schema_audit_does_not_log_untrusted_fields(self):
        brand = {'id': 7254821, 'userId': 5607453,
                 'timezone': 'America/New_York',
                 'private_api_token': 'SECRET_DO_NOT_LOG',
                 'networksData': {'twitterData': {
                     'username': 'IranStabilityMo', 'accessToken': 'SECRET_DO_NOT_LOG'}}}
        indicators = x.brand_identity_audit(brand)
        self.assertTrue(indicators['twitter_username_matches_expected'])
        self.assertEqual(indicators['twitterData_type'], 'dict')
        self.assertEqual(indicators['twitter_public_username_keys'], ['username'])
        self.assertNotIn('SECRET_DO_NOT_LOG', json.dumps(indicators))
        self.assertNotIn('IranStabilityMo', json.dumps(indicators))
        with patch.object(x, 'metricool', return_value={'data': [brand]}), \
             patch('sys.stdout', new_callable=io.StringIO) as out:
            x.check_brand(healthcheck=True)
        self.assertIn('non-secret indicators only', out.getvalue())
        self.assertNotIn('SECRET_DO_NOT_LOG', out.getvalue())
        self.assertNotIn('IranStabilityMo', out.getvalue())

    def test_bad_brand_identity_never_permits_post(self):
        brand = {'id': 7254821, 'userId': 5607453,
                 'timezone': 'America/New_York',
                 'networksData': {'twitterData': {'other_key': 'UNTRUSTED'}}}
        with patch.object(x, 'metricool', return_value=[brand]), \
             patch('sys.stdout', new_callable=io.StringIO) as out:
            with self.assertRaisesRegex(RuntimeError, 'connected X identity'):
                x.check_brand(healthcheck=True)
        self.assertIn('"twitterData_type": "dict"', out.getvalue())
        self.assertNotIn('UNTRUSTED', out.getvalue())

    def test_next_future_unoccupied_minute(self):
        now = self.now.replace(second=5)
        post = {'providers': [{'network': 'twitter'}], 'publicationDate': {
            'dateTime': (now + dt.timedelta(minutes=2)).replace(second=0).strftime('%Y-%m-%dT%H:%M:%S'), 'timezone': 'America/New_York'}}
        future = x.next_slot([post], now)
        self.assertEqual(future.minute, 3)
        self.assertGreater(future, now)

    def test_claim_creation_is_atomic_and_bound(self):
        with patch.object(x, 'github', return_value={'ref': 'refs/tags/x-announcement-' + self.day, 'object': {'sha': 'abc'}}) as call:
            self.assertTrue(x.claim(self.day, 'abc'))
            self.assertEqual(call.call_args.args[1], 'POST')
        err = urllib.error.HTTPError('https://api.github.com', 422, 'exists', {}, None)
        with patch.object(x, 'github', side_effect=[err, {'ref': 'refs/tags/x-announcement-' + self.day}]):
            self.assertFalse(x.claim(self.day, 'abc'))

    def test_previous_claim_stops_without_metricool(self):
        with self.setup_schedule() as stack:
            existing = stack.enter_context(patch.object(x, 'existing_claim', return_value=True))
            api = stack.enter_context(patch.object(x, 'metricool'))
            result = x.schedule(self.h, self.verifier, self.now)
            self.assertEqual(result['status'], 'previously_claimed')
            api.assert_not_called()

    @contextlib.contextmanager
    def setup_schedule(self):
        with contextlib.ExitStack() as stack:
            tmp = stack.enter_context(tempfile.TemporaryDirectory())
            root = Path(tmp); (root / 'data').mkdir()
            raw = json.dumps(self.h).encode(); (root / 'data/history.json').write_bytes(raw)
            stack.enter_context(patch.object(x, 'ROOT', root))
            stack.enter_context(patch.dict('os.environ', {'AUTO_X_ENABLED': 'true'}))
            self.receipt = {'assessment_date': self.day, 'head_sha': 'abc', 'history_sha256': hashlib.sha256(raw).hexdigest()}
            self.verifier = lambda: dict(self.receipt)
            yield stack

    def test_no_post_if_publication_not_verified(self):
        with self.setup_schedule() as stack:
            api = stack.enter_context(patch.object(x, 'metricool'))
            with self.assertRaisesRegex(RuntimeError, 'newly verified'):
                x.schedule(self.h, lambda: None, self.now)
            api.assert_not_called()

    def test_timeout_posts_once_after_claim(self):
        seen = []
        with self.setup_schedule() as stack:
            stack.enter_context(patch.object(x, 'existing_claim', return_value=False))
            stack.enter_context(patch.object(x, 'check_brand'))
            stack.enter_context(patch.object(x, 'scheduled_posts', return_value=[]))
            stack.enter_context(patch.object(x, 'published_posts', return_value=[]))
            stack.enter_context(patch.object(x, 'claim', side_effect=lambda *a: seen.append('claim') or True))
            def post(*a, **k):
                seen.append('POST'); raise TimeoutError('uncertain')
            call = stack.enter_context(patch.object(x, 'metricool', side_effect=post))
            with self.assertRaises(TimeoutError): x.schedule(self.h, self.verifier, self.now)
            self.assertEqual(seen, ['claim', 'POST'])
            self.assertEqual(call.call_count, 1)

    def test_success_requires_readback_and_receipt(self):
        with self.setup_schedule() as stack:
            stack.enter_context(patch.object(x, 'existing_claim', return_value=False))
            stack.enter_context(patch.object(x, 'check_brand'))
            stack.enter_context(patch.object(x, 'scheduled_posts', return_value=[]))
            stack.enter_context(patch.object(x, 'published_posts', return_value=[]))
            stack.enter_context(patch.object(x, 'claim', return_value=True))
            posted = {}
            def api(path, method='GET', payload=None, **kw):
                if method == 'POST':
                    posted.update(payload); posted['id'] = 42
                return {'data': dict(posted)}
            call = stack.enter_context(patch.object(x, 'metricool', side_effect=api))
            result = x.schedule(self.h, self.verifier, self.now)
            self.assertEqual(result['status'], 'scheduled_verified')
            self.assertEqual(call.call_count, 2)
            self.assertTrue((x.ROOT / '.automation-audit/x-post-receipt.json').exists())

    def test_ambiguous_success_body_is_not_success(self):
        with self.setup_schedule() as stack:
            for name, result in [('existing_claim', False), ('check_brand', {}), ('scheduled_posts', []), ('published_posts', []), ('claim', True)]:
                stack.enter_context(patch.object(x, name, return_value=result))
            call = stack.enter_context(patch.object(x, 'metricool', return_value={'error': 'not authorized'}))
            with self.assertRaisesRegex(RuntimeError, 'ID acknowledged'):
                x.schedule(self.h, self.verifier, self.now)
            self.assertEqual(call.call_count, 1)


if __name__ == '__main__': unittest.main()
