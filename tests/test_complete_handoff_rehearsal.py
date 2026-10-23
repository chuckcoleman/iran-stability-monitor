"""Nonpublishing full-process rehearsal of repeated validation and review.

Uses only synthetic evidence/decisions, local temporary files, and a fake
unused API-key placeholder; never contacts GitHub or publishes a forecast.
"""
import copy
import datetime as dt
import json
import os
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from automation_fixtures import fixture, legacy_receipt_fixture
import assessment_pipeline as pipeline
import pre_github_review as pre
import submit_reviewed_assessment as handoff
from review_receipt import checked_receipt
from candidate_checks import one_append


class FullHandoffRehearsal(unittest.TestCase):
    @staticmethod
    def historical_checkout(path, history):
        """Use an isolated October 4 checkout for October 11 legacy receipt tests."""
        (path / "data").mkdir(parents=True)
        (path / "schema").mkdir()
        (path / "data/history.json").write_text(
            json.dumps(history, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.copyfile(ROOT / "schema/history.schema.json",
                        path / "schema/history.schema.json")

    def test_five_rounds_from_failed_validation_to_clean_handoff(self):
        history, base, evidence, opened = legacy_receipt_fixture()
        original = copy.deepcopy(history)
        day = opened.date().isoformat()
        cutoff = opened - dt.timedelta(seconds=10)
        sources = {x['source'] for x in evidence}
        drafts = []
        for i in range(1, 6):
            draft = copy.deepcopy(base)
            draft['summary'] = (
                f'Synthetic stage {i}: this is a test of the validation '
                'process, not a factual assessment or a live publication.')
            if i == 1:
                draft['regional'][0]['p'] += 1  # invalidate the scenario total
            drafts.append(draft)
        locked = json.dumps(base['forecasts'], sort_keys=True)
        checks, roles, corrections, assessments = [], [], [], []

        def researcher(prompt, search):
            self.assertTrue(search)
            return {'evidence': copy.deepcopy(evidence)}, set(sources)

        def assessor(prompt, search):
            if 'locked_forecasts' not in prompt:
                assessments.append('elicitation')
                return copy.deepcopy(drafts[0]), set()
            index = len(corrections) + 2
            corrections.append(index)
            self.assertEqual(
                json.dumps(drafts[index - 1]['forecasts'], sort_keys=True),
                locked)
            return copy.deepcopy(drafts[index - 1]), set()

        def reviewer(prompt, search):
            role = ('affirmative' if 'ROLE: AFFIRMATIVE' in prompt
                    else 'critical')
            record = json.loads(prompt.split('Input: ')[-1])
            stage = int(
                record['analysis']['summary'].split('stage ')[1].split(':')[0])
            roles.append((stage, role))
            if stage == 2 and role == 'affirmative':
                return {'approved': False, 'issues': [{
                    'type': 'support', 'location': 'summary',
                    'reason': 'Correct synthetic support gap'}]}, set()
            if stage == 3 and role == 'critical':
                return {'approved': False, 'issues': [{
                    'type': 'uncertainty', 'location': 'summary',
                    'reason': 'Correct synthetic uncertainty gap'}]}, set()
            return {'approved': True, 'issues': []}, set()

        real = pipeline._fully_validated_candidate

        def validator(h, a, e, c, o, issued, schema):
            stage = int(a['summary'].split('stage ')[1].split(':')[0])
            checks.append((stage, 'final' if issued != o else 'pre'))
            result = real(h, a, e, c, o, issued, schema)
            if stage == 4 and issued != o:
                raise ValueError('Synthetic final-issued-content defect')
            return result

        reviewer_fn = reviewer
        clock = iter([cutoff - dt.timedelta(seconds=5), cutoff, opened,
                      opened + dt.timedelta(seconds=3),
                      opened + dt.timedelta(seconds=7)])
        with tempfile.TemporaryDirectory(prefix='iran-no-publication-') as tmp:
            dest = Path(tmp) / 'approved'
            checkout = Path(tmp) / 'historical-checkout'
            self.historical_checkout(checkout, history)
            with patch.object(pre, 'ROOT', checkout), \
                 patch.object(pipeline, 'ROOT', checkout), \
                 patch.dict(os.environ, {
                'OPENAI_API_KEY': 'synthetic-unused',
                'GITHUB_ACTIONS': 'false'}, clear=True), \
                 patch.object(pipeline, '_fully_validated_candidate',
                              side_effect=validator), \
                 patch.object(handoff, 'gh') as git_write, \
                 patch.object(handoff, 'gh_json') as git_read:
                result = pre.prepare(
                    dest, now=opened,
                    producer=lambda h, reviewer=None: pipeline.produce(
                        h, researcher, assessor, lambda: next(clock),
                        lambda url: {}, reviewer=reviewer_fn),
                    review_finished_at=opened + dt.timedelta(seconds=8))
                handoff.validate_handoff(
                    result, root=checkout, now=opened + dt.timedelta(seconds=9),
                    test_only=True)
                git_write.assert_not_called()
                git_read.assert_not_called()

            new = json.loads((dest / 'data/history.json').read_text())
            receipt = json.loads(
                (dest / 'data/review-receipts' / f'{day}.json').read_text())
            one_append(history, new)
            checked_receipt(
                history, new, receipt, now=opened + dt.timedelta(seconds=9))
            self.assertEqual(history, original)
            self.assertEqual(
                [f['p'] for f in new['updates'][-1]['forecasts']],
                [f['p'] for f in base['forecasts']])
            self.assertEqual(assessments, ['elicitation'])
            self.assertEqual(corrections, [2, 3, 4, 5])
            self.assertEqual(checks, [
                (1, 'pre'), (2, 'pre'), (3, 'pre'),
                (4, 'pre'), (4, 'final'), (5, 'pre'), (5, 'final')])
            self.assertEqual(
                roles,
                [(stage, role) for stage in (2, 3, 4, 5)
                 for role in ('affirmative', 'critical')])
            self.assertEqual(receipt['approval']['round'], 5)
            for role in ('validation', 'affirmative',
                         'critical', 'final_validation'):
                audit = json.loads(
                    (dest / 'review-audit' /
                     f'review-05-{role}.json').read_text())
                self.assertEqual(audit['status'], 'clean')
                self.assertEqual(audit['issues'], [])
            (dest / 'review-audit/review-05-critical.json').unlink()
            with self.assertRaisesRegex(RuntimeError, 'critical review audit'):
                handoff.validate_handoff(
                    dest, root=checkout, now=opened + dt.timedelta(seconds=9),
                    test_only=True)
        self.assertEqual(history, original)

    def test_timeout_yields_no_clean_handoff(self):
        history, base, evidence, opened = legacy_receipt_fixture()
        sources = {x['source'] for x in evidence}
        cutoff = opened - dt.timedelta(seconds=10)
        dates = iter([cutoff - dt.timedelta(seconds=5), cutoff, opened])
        with tempfile.TemporaryDirectory(prefix='iran-unsafe-handoff-') as tmp:
            dest = Path(tmp) / 'should-not-exist'
            checkout = Path(tmp) / 'historical-checkout'
            self.historical_checkout(checkout, history)

            def producer(h, reviewer=None):
                return pipeline.produce(
                    h, lambda prompt, search: ({'evidence': evidence}, sources),
                    lambda prompt, search: (copy.deepcopy(base), set()),
                    lambda: next(dates), lambda url: {},
                    lambda prompt, search: (_ for _ in ()).throw(
                        TimeoutError('Synthetic independent reviewer timeout')))

            with patch.object(pre, 'ROOT', checkout), \
                 patch.object(pipeline, 'ROOT', checkout), \
                 patch.dict(os.environ, {
                     'OPENAI_API_KEY': 'synthetic-unused',
                     'GITHUB_ACTIONS': 'false'}, clear=True):
                with self.assertRaisesRegex(TimeoutError, 'reviewer timeout'):
                    pre.prepare(dest, now=opened, producer=producer)
            self.assertFalse(dest.exists())


if __name__ == '__main__':
    unittest.main()
