"""Owned DPAPI/wire fixtures; no genuine secret, account or provider request."""
import copy,json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from services.windows_native.contracts import WorkflowError
from services.windows_native.official_account_tokens import AccessToken,save,load,PREFIX,ENTROPY
from services.windows_native.official_account_registry import Account,AccountFactory,Registry,load as registry_load
from app.analytics_official import AnalyticsHTTPClient,AnalyticsOAuthCredential,YT_READ,YT_ANALYTICS,AnalyticsOfficialError
from app.publishing_wire import OfficialHTTPClient
from app.publishing_models import PublishingTargetBinding

class OfficialAccountRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.root=self.folder/'state';self.root.mkdir();self.secret=self.folder/'secrets'/'test.dpapi'
        self.target=PublishingTargetBinding(workspace_id='wsp_fixture',profile_id='ppf_explicit_fixture',profile_version=1,platform='youtube',
            provider_key='youtube-data-api-publishing',target_account_id='UC_EXPLICIT_FIXTURE',credential_binding_sha256='a'*64)
        self.account=Account(account_ref='npac_'+'a'*32,target=self.target,credential_alias='youtube-fixture-read',token_file=str(self.secret),read_enabled=True)
        self.token={'workspace_id':'wsp_fixture','credential_alias':self.account.credential_alias,'credential_binding_sha256':'a'*64,'platform':'youtube',
            'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'scopes':[YT_READ,YT_ANALYTICS],'token':'EXPLICIT-SECRET-FIXTURE-ONLY-0123456789'}
        self.credential=AnalyticsOAuthCredential(self.target,datetime.now(timezone.utc)+timedelta(hours=1),frozenset(self.token['scopes']),self.token['token'])
    def tearDown(self):self.temp.cleanup()
    def factory(self,**kwargs):return AccountFactory(self.account,self.root,'wsp_fixture',**kwargs)
    def test_default_factory_never_reads_token_or_network_and_missing_mount_is_not_configured(self):
        with patch('services.windows_native.official_account_registry.token_load',side_effect=AssertionError('No secret read')):
            factory=self.factory();self.assertEqual(factory.public()['status'],'NOT_CONFIGURED');self.assertFalse(factory.public()['external_reads_enabled'])
            with self.assertRaisesRegex(WorkflowError,'READ_DISABLED'):factory.credential()
            enabled=self.factory(owner_read_enabled=True);self.assertEqual(enabled.public()['status'],'NOT_CONFIGURED');self.assertFalse(enabled.public()['credential_present'])
        self.assertFalse(self.secret.exists())
    def test_explicit_scoped_fixture_uses_resolver_without_paths_tokens_or_publish_permission_in_public_state(self):
        factory=self.factory(owner_read_enabled=True,transport=httpx.MockTransport(lambda _:None),resolver=lambda _:self.credential)
        public=factory.public();self.assertEqual(public['status'],'CONFIGURED');self.assertEqual(public['mode'],'fixture');self.assertFalse(public['external_reads_enabled'])
        self.assertEqual(factory.credential(),self.credential);self.assertFalse(public['publishing_enabled']);self.assertFalse(public['account_verified']);self.assertFalse(public['credential_verified'])
        text=json.dumps(public);self.assertNotIn(str(self.secret),text);self.assertNotIn(self.token['token'],text)
    def test_actual_domain_dpapi_roundtrip_never_contains_plain_token_or_changes_existing_secret(self):
        result=save(self.secret,self.root,self.token);self.assertFalse(result['token_returned']);self.assertEqual(result['external_calls'],0)
        data=self.secret.read_bytes();self.assertTrue(data.startswith(PREFIX));self.assertNotIn(self.token['token'].encode(),data)
        credential=load(self.secret,self.root,self.target,self.account.credential_alias);self.assertEqual(credential.token,self.token['token'])
        with self.assertRaisesRegex(WorkflowError,'ALREADY_SAVED'):save(self.secret,self.root,self.token)
        self.assertEqual(self.secret.read_bytes(),data)
        from services.windows_native.assemblyai_connection import _dpapi
        with self.assertRaises(WorkflowError):_dpapi(data[len(PREFIX):],decrypt=True)
        self.assertFalse(self.factory().public()['external_reads_enabled'])
    def test_foreign_workspace_alias_platform_binding_or_corrupt_ciphertext_is_sanitized(self):
        save(self.secret,self.root,self.token)
        for changes,alias in [({'workspace_id':'wsp_foreign'},self.account.credential_alias),({'credential_binding_sha256':'b'*64},self.account.credential_alias),
            ({'platform':'tiktok','provider_key':'tiktok-content-posting-api'},self.account.credential_alias),({},'foreign-alias')]:
            target=PublishingTargetBinding.model_validate({**self.target.model_dump(),**changes})
            with self.assertRaisesRegex(WorkflowError,'TOKEN_UNAVAILABLE') as error:load(self.secret,self.root,target,alias)
            self.assertNotIn(self.token['token'],str(error.exception))
        self.secret.write_bytes(b'EXPLICIT CORRUPTION FIXTURE')
        with self.assertRaisesRegex(WorkflowError,'TOKEN_UNAVAILABLE'):load(self.secret,self.root,self.target,self.account.credential_alias)
    def test_registry_duplicate_keys_accounts_or_foreign_scope_and_private_mount_in_state_reject(self):
        raw={'version':1,'workspace_id':'wsp_fixture','accounts':[self.account.model_dump(mode='json')]};path=self.folder/'registry.json';path.write_text(json.dumps(raw),encoding='utf-8')
        factories=registry_load(path,self.root,'wsp_fixture');self.assertEqual(len(factories),1);self.assertEqual(next(iter(factories.values())).public()['status'],'NOT_CONFIGURED')
        with self.assertRaisesRegex(WorkflowError,'WORKSPACE_MISMATCH'):registry_load(path,self.root,'wsp_foreign')
        for changes in [{'version':True},{'accounts':raw['accounts']*2},{'workspace_id':'wsp_foreign'}]:
            path.write_text(json.dumps({**raw,**changes}),encoding='utf-8')
            with self.assertRaises(WorkflowError):registry_load(path,self.root,'wsp_fixture')
        path.write_text('{"version":1,"version":1,"workspace_id":"wsp_fixture"}',encoding='utf-8')
        with self.assertRaises(WorkflowError):registry_load(path,self.root,'wsp_fixture')
        with self.assertRaisesRegex(WorkflowError,'OUTSIDE_SOURCE_STATE'):
            AccountFactory(self.account.model_copy(update={'token_file':str(self.root/'secret.dpapi')}),self.root,'wsp_fixture')
    def test_configuration_enablement_transport_or_resolver_cannot_mutate_after_frozen_admission(self):
        transport=httpx.MockTransport(lambda _:None)
        for mutate in [lambda f:setattr(f,'read_enabled',True),lambda f:setattr(f.client.wire,'network_enabled',True),
            lambda f:setattr(f,'resolver',lambda _:self.credential),lambda f:setattr(f.client.wire,'transport',None),
            lambda f:setattr(f,'client',AnalyticsHTTPClient('youtube',transport=transport)),
            lambda f:setattr(f.client,'wire',OfficialHTTPClient('analytics_youtube',transport=transport)),
            lambda f:setattr(f.client.wire,'platform','analytics_tiktok'),
            lambda f:object.__setattr__(f.account.target,'target_account_id','FOREIGN'),lambda f:setattr(f,'workspace','wsp_foreign')]:
            factory=self.factory(transport=transport);mutate(factory)
            with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):factory.public()
    def test_relative_secret_mount_is_rejected_before_source_or_ciphertext_access(self):
        with self.assertRaisesRegex(WorkflowError,'ABSOLUTE_SECRET_PATH_REQUIRED'):
            AccountFactory(self.account.model_copy(update={'token_file':'relative-fixture.dpapi'}),self.root,'wsp_fixture')
    def test_invalid_tokens_scopes_and_timezone_are_rejected_without_secret_files(self):
        for change in [{'token':'bad\r\nX-Forged: value'}, {'expires_at':True},{'expires_at':'2026-10-08T12:00:00'},
            {'scopes':[YT_READ,YT_READ]},{'scopes':['https://www.googleapis.com/auth/youtube.upload']},{'refresh_token':'never admitted'}]:
            with self.assertRaises(WorkflowError):save(self.secret,self.root,{**self.token,**change})
            self.assertFalse(self.secret.exists())
        for change in [{'read_enabled':1},{'publishing_enabled':0},{'publishing_enabled':True},{'endpoint':'https://untrusted.invalid'}]:
            with self.assertRaises(ValidationError):Account.model_validate({**self.account.model_dump(mode='json'),**change})
    def test_expired_wrong_scope_or_foreign_resolver_credential_fails_before_network(self):
        for credential in [AnalyticsOAuthCredential(self.target,datetime.now(timezone.utc)-timedelta(seconds=1),frozenset(self.token['scopes']),self.token['token']),
            AnalyticsOAuthCredential(self.target,datetime.now(timezone.utc)+timedelta(hours=1),frozenset({YT_READ}),self.token['token'])]:
            factory=self.factory(owner_read_enabled=True,transport=httpx.MockTransport(lambda _:None),resolver=lambda _:credential)
            with self.assertRaises(AnalyticsOfficialError):factory.credential()
