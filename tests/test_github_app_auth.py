"""Offline GitHub App migration tests; no GitHub writes or secret material."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import sunday_automation as s


class GithubAppAuthTests(unittest.TestCase):
    def workflow(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_sunday_workflow_mints_separate_short_lived_tokens(self):
        text = self.workflow('.github/workflows/sunday-assessment.yml')
        self.assertEqual(text.count('uses: actions/create-github-app-token@v3'), 2)
        self.assertNotIn('AUTOMATION_GH_TOKEN', text)
        self.assertNotIn('secrets.OPENAI_API_KEY', text)
        self.assertIn('permission-pull-requests: write', text)
        self.assertIn('permission-pages: read', text)
        self.assertIn('permission-actions: read', text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('id-token: write', text)
        self.assertTrue(text.index('id: app-preflight') < text.index('python scripts/sunday_automation.py prepare'))
        self.assertTrue(text.index('python scripts/sunday_automation.py prepare') < text.index('id: app-publish'))
        self.assertTrue(text.index('id: app-publish') < text.index('python scripts/sunday_automation.py publish'))
        self.assertIn('GH_TOKEN: ${{ steps.app-publish.outputs.token }}', text)
        self.assertIn("if: steps.eligibility.outputs.eligible == 'true'", text)

    def test_social_token_minted_only_after_gated_site_confirmation(self):
        text = self.workflow('.github/workflows/verify-publication.yml')
        self.assertEqual(text.count('uses: actions/create-github-app-token@v3'), 1)
        self.assertNotIn('AUTOMATION_GH_TOKEN', text)
        self.assertIn('GH_TOKEN: ${{ github.token }}', text)
        self.assertIn('GH_TOKEN: ${{ steps.app-social.outputs.token }}', text)
        self.assertTrue(text.index('python scripts/verify_publication.py') < text.index('id: app-social'))
        self.assertTrue(text.index('id: app-social') < text.index('python scripts/metricool_publish.py'))
        self.assertIn("hashFiles('.verified-publication.json') != '' && vars.AUTO_X_ENABLED == 'true'", text)

    def test_disabled_live_mode_works_without_any_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(s.ready())

    def test_dry_run_can_use_openai_wif_without_github_app(self):
        env = {'OPENAI_IDENTITY_PROVIDER_ID': 'idp_test',
               'OPENAI_SERVICE_ACCOUNT_ID': 'user_test'}
        with patch.dict(os.environ, env, clear=True):
            self.assertTrue(s.ready(live=False))
            with self.assertRaisesRegex(RuntimeError, 'installation token'):
                s.ready(live=False, require_github_token=True)

    def test_temporary_push_auth_never_leaks_into_git_remote(self):
        with patch.dict(os.environ, {'GH_TOKEN':'short-lived-github-token'}, clear=True):
            with patch.object(s, 'run') as runner:
                s._git_push_with_app_token('sunday-auto-20261018')
        self.assertEqual(runner.call_args.args,
                         ('git', 'push', 'origin', 'sunday-auto-20261018'))
        env = runner.call_args.kwargs['env']
        self.assertEqual(env['GIT_CONFIG_COUNT'], '1')
        self.assertEqual(env['GIT_CONFIG_KEY_0'], 'http.https://github.com/.extraheader')
        self.assertNotIn('short-lived-github-token', str(runner.call_args.args))
        self.assertNotIn('x-access-token', str(runner.call_args.args))
        self.assertTrue(env['GIT_CONFIG_VALUE_0'].startswith('AUTHORIZATION: basic '))
        self.assertNotIn('short-lived-github-token', env['GIT_CONFIG_VALUE_0'])

    def test_publish_without_prepared_candidate_causes_no_writes(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            with patch.object(s, 'ready', return_value=True), \
                 patch.object(s, 'verify_repository_gate'), \
                 patch.object(s, '_candidate_paths', return_value=(base,base/'missing.json',base/'history.json')), \
                 patch.object(s, 'gh') as api, \
                 patch.object(s, 'run') as commands:
                self.assertIsNone(s.publish_candidate())
                api.assert_not_called()
                commands.assert_not_called()

    def test_owner_helper_stores_app_not_personal_access_token(self):
        helper = self.workflow('scripts/configure_automation.py')
        self.assertIn('IRAN_GITHUB_APP_PRIVATE_KEY', helper)
        self.assertIn('IRAN_GITHUB_APP_CLIENT_ID', helper)
        self.assertNotIn('AUTOMATION_GH_TOKEN', helper)
        self.assertIn('METRICOOL_API_TOKEN', helper)


if __name__ == '__main__':
    unittest.main()
