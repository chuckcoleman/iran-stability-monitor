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

    def test_gate_accepts_installation_token_without_user_push_boolean(self):
        """A GitHub App's repo permissions.push is not authoritative."""
        repo = 'chuckcoleman/iran-stability-monitor'
        rule = {
            'enforcement': 'active', 'bypass_actors': [],
            'conditions': {'ref_name': {'include': ['~DEFAULT_BRANCH'], 'exclude': []}},
            'rules': [
                {'type': 'deletion'}, {'type': 'non_fast_forward'},
                {'type': 'pull_request'},
                {'type': 'required_status_checks', 'parameters': {
                    'strict_required_status_checks_policy': True,
                    'required_status_checks': [{'context': 'validate', 'integration_id': 15368}]
                }}
            ]
        }
        def api(*args):
            if args == ('repos/' + repo + '/pages',):
                return {'build_type': 'workflow'}
            if args == ('repos/' + repo,):
                return {'default_branch': 'main', 'permissions': {'push': False}}
            if args == ('--paginate', '--slurp', 'installation/repositories?per_page=100'):
                return [{'total_count': 1, 'repositories': [{'full_name': repo}]}]
            if args == ('--paginate', '--slurp', 'repos/' + repo + '/rulesets?per_page=100'):
                return [[{'id': 5, 'enforcement': 'active'}]]
            if args == ('repos/' + repo + '/rulesets/5',):
                return rule
            raise AssertionError('Unexpected endpoint: ' + str(args))
        with patch.object(s, 'gh_json', side_effect=api):
            s.verify_repository_gate(repo)

    def test_gate_rejects_extra_installation_repository(self):
        repo = 'chuckcoleman/iran-stability-monitor'
        def api(*args):
            if args == ('repos/' + repo + '/pages',):
                return {'build_type': 'workflow'}
            if args == ('repos/' + repo,):
                return {'default_branch': 'main'}
            if args == ('--paginate', '--slurp', 'installation/repositories?per_page=100'):
                return [{'total_count': 2, 'repositories': [
                    {'full_name': repo}, {'full_name': 'chuckcoleman/other-repository'}]}]
            raise AssertionError('No other API request is allowed here')
        with patch.object(s, 'gh_json', side_effect=api):
            with self.assertRaisesRegex(RuntimeError, 'exactly the expected repository'):
                s.verify_repository_gate(repo)

    def test_readiness_reports_missing_metricool_without_leaking_tokens(self):
        import assessment_pipeline as a
        env = {'OPENAI_IDENTITY_PROVIDER_ID': 'idp_fake',
               'OPENAI_SERVICE_ACCOUNT_ID': 'user_fake', 'GH_TOKEN': 'secret-tok'}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(s, 'verify_repository_gate'), \
             patch.object(a, 'openai_bearer_token',
                          side_effect=RuntimeError('OpenAI token exchange HTTP 400 (invalid_subject_token)')):
            with self.assertRaises(RuntimeError) as result:
                s.service_checks()
        message = str(result.exception)
        self.assertIn('OpenAI OIDC/token exchange', message)
        self.assertIn('invalid_subject_token', message)
        self.assertIn('Metricool: missing METRICOOL_API_TOKEN', message)
        self.assertNotIn('secret-tok', message)

    def test_metricool_stages_identified_without_leaking_error_body(self):
        import assessment_pipeline as a
        import metricool_publish as mp
        env = {'GH_TOKEN':'safe-dummy', 'METRICOOL_API_TOKEN':'SECRET_NEVER_LOG',
               'OPENAI_IDENTITY_PROVIDER_ID':'idp_fake',
               'OPENAI_SERVICE_ACCOUNT_ID':'user_fake'}
        with patch.dict(os.environ,env,clear=True), \
             patch.object(s,'verify_repository_gate'), \
             patch.object(a,'openai_bearer_token',
                          side_effect=RuntimeError('OpenAI token exchange HTTP 401 (invalid_grant)')), \
             patch.object(mp,'check_brand'), \
             patch.object(mp,'scheduled_posts',side_effect=RuntimeError('Unrecognized Metricool list response')), \
             patch.object(mp,'published_posts',side_effect=RuntimeError('Published TwitterPost missing text')):
            with self.assertRaises(RuntimeError) as result:
                s.service_checks()
        message=str(result.exception)
        self.assertIn('OpenAI token exchange HTTP 401 (invalid_grant)',message)
        self.assertIn('Metricool scheduled posts: Unrecognized Metricool list response',message)
        self.assertIn('Metricool published X export: Published TwitterPost missing text',message)
        self.assertNotIn('SECRET_NEVER_LOG',message)

    def test_metricool_unknown_failure_does_not_echo_arbitrary_text(self):
        msg = s._metricool_read_failure('Metricool brand lookup',
                                        RuntimeError('private-token-secret-value'))
        self.assertEqual(msg, 'Metricool brand lookup: RuntimeError')

    def test_owner_helper_stores_app_not_personal_access_token(self):
        helper = self.workflow('scripts/configure_automation.py')
        self.assertIn('IRAN_GITHUB_APP_PRIVATE_KEY', helper)
        self.assertIn('IRAN_GITHUB_APP_CLIENT_ID', helper)
        self.assertNotIn('AUTOMATION_GH_TOKEN', helper)
        self.assertIn('METRICOOL_API_TOKEN', helper)


if __name__ == '__main__':
    unittest.main()
