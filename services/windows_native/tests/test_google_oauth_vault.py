"""Actual Windows DPAPI custody over synthetic OAuth; no real secrets or network."""
import json,os,tempfile,unittest,warnings
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from services.windows_native.google_oauth_vault import NativeGoogleOAuthVault,PrivateClient,PrivateAuthorization,PrivateGrant,SecretReceipt,PREFIX
from services.windows_native.assemblyai_connection import _dpapi
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.tests.test_google_oauth_protocol import client,grant,NOW,TOKEN,REFRESH,SECRET
from app.google_oauth_protocol import authorization,refresh_request,parse_tokens,GoogleTokenResponse

class GoogleOAuthVaultFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name).resolve();self.owned=self.folder;self.root=self.folder/'state';self.root.mkdir()
        self.directory=self.folder/'private-google';self.workspace='wsp_google_oauth_fixture';self.vault=NativeGoogleOAuthVault(self.directory,self.root,self.workspace)
    def tearDown(self):
        assert self.folder.resolve()==self.owned and self.folder.parent==Path(tempfile.gettempdir()).resolve()
        self.temp.cleanup()
    def config(self,purpose='analytics'):
        c=client(purpose);return PrivateClient(target=c.target,purpose=purpose,credential_alias='explicit-google-'+purpose,client_id=c.client_id,scopes=sorted(c.scopes),client_secret=c.client_secret)
    def save(self,purpose='analytics'):
        value=self.config(purpose);receipt=self.vault.save_client(value);return value,receipt,self.vault.client(receipt)
    def reseal(self,receipt,change):
        path=self.vault.path(receipt['reference']);encrypted=path.read_bytes();decoded=_dpapi(encrypted[len(PREFIX):],decrypt=True,entropy=self.vault.entropy(receipt['kind'],receipt['purpose']))
        value=json.loads(decoded);change(value);path.write_bytes(PREFIX+_dpapi(json.dumps(value).encode(),entropy=self.vault.entropy(receipt['kind'],receipt['purpose'])))
        return{**receipt,'cipher_sha256':file_sha(path),'bytes':path.stat().st_size}

class GoogleOAuthVaultContractTests(GoogleOAuthVaultFixture,unittest.TestCase):
    def test_initialization_and_states_never_decrypt_create_directory_or_enable_runtime(self):
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO STARTUP PRIVATE READ')):
            vault=NativeGoogleOAuthVault(self.directory,self.root,self.workspace);value=vault.states()
        self.assertFalse(self.directory.exists());self.assertFalse(value['mounted'])
        for k in ('startup_decryption','token_returned','publishing_enabled','automatic_refresh','account_verified','real_provider_tested'):self.assertIs(value[k],False)
    def test_source_state_relative_linked_and_foreign_workspace_configuration_refuse(self):
        repo=Path(__file__).resolve().parents[3]
        for path,root,workspace in ((self.root/'private',self.root,self.workspace),(repo/'private-never',self.root,self.workspace),('relative-secret',self.root,self.workspace),
            (self.directory,Path('relative-state'),self.workspace),(self.directory,self.root,'wsp/foreign')):
            with self.assertRaises(WorkflowError):NativeGoogleOAuthVault(path,root,workspace)
        self.assertFalse(self.directory.exists())
    def test_receipts_references_and_raw_disabled_flags_reject_before_decrypt(self):
        value,r,c=self.save()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO INVALID RECEIPT DECRYPT')):
            for change in ({'reference':'../outside'},{'reference':'C:/unsafe'},{'workspace_id':'wsp_foreign'},{'bytes':True},{'token_returned':0},{'publishing_enabled':1},{'kind':'grant'},{'extra':True}):
                with self.assertRaises(WorkflowError):self.vault.client({**r,**change})
    def test_duplicate_client_scopes_naive_times_numeric_mock_and_unchecked_models_fail_before_save(self):
        value=self.config()
        for changes in ({'scopes':[value.scopes[0],value.scopes[0]]},{'client_secret':'unsafe\n'},{'target':{**value.target.model_dump(mode='json'),'workspace_id':'wsp_foreign'}},{'purpose':'service'}):
            with self.assertRaises(WorkflowError):self.vault.save_client(value.model_copy(update=changes))
        self.assertFalse(self.directory.exists());private,r,c=self.save();c,g=grant(c)
        for changed in (replace(g,mock=1),replace(g,expires_at=NOW.replace(tzinfo=None)),replace(g,refresh_token='bad'),replace(g,expires_at=NOW+timedelta(days=2))):
            before=list(self.directory.iterdir())
            with self.assertRaises(WorkflowError):self.vault.save_grant(changed,r)
            self.assertEqual(list(self.directory.iterdir()),before)
    def test_changed_vault_binding_or_hardlinked_private_file_refuses_before_decryption(self):
        private,r,c=self.save();self.vault.workspace='wsp_foreign'
        with self.assertRaises(WorkflowError):self.vault.client(r)
        self.vault.workspace=self.workspace;path=self.vault.path(r['reference']);linked=self.folder/'private-hardlink';os.link(path,linked)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO LINKED FILE DECRYPT')):
            with self.assertRaises(WorkflowError):self.vault.client(r)
        linked.unlink();self.assertEqual(self.vault.client(r).fingerprint(),c.fingerprint())
    def test_unchecked_private_model_never_emits_serializer_warning_containing_secret(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            with self.assertRaises(WorkflowError):self.vault.save_client(self.config().model_copy(update={'client_secret':[SECRET]}))
        self.assertEqual(caught,[]);self.assertFalse(self.directory.exists())

@unittest.skipUnless(os.name=='nt','Actual Windows DPAPI required')
class GoogleOAuthVaultDPAPITests(GoogleOAuthVaultFixture,unittest.TestCase):
    def test_actual_encrypted_client_roundtrip_private_acl_before_write_and_no_public_secret(self):
        from services.windows_native.assemblyai_connection import _restrict_file
        with patch('services.windows_native.assemblyai_connection._restrict_file',wraps=_restrict_file) as restricted:
            private,r,c=self.save()
        self.assertEqual(restricted.call_count,1);path=self.vault.path(r['reference']);raw=path.read_bytes();self.assertTrue(raw.startswith(PREFIX));self.assertEqual(file_sha(path),r['cipher_sha256'])
        self.assertEqual(c.fingerprint(),private.client().fingerprint());self.assertEqual(c.client_secret,SECRET)
        self.assertNotIn(SECRET.encode(),raw);self.assertNotIn(SECRET,repr(private)+repr(c)+json.dumps(r));self.assertFalse(r['publishing_enabled']);self.assertFalse(r['token_returned'])
    def test_both_purposes_remain_domain_bound_and_original_receipt_cannot_switch_target_alias_or_kind(self):
        for purpose in ('analytics','publishing'):
            private,r,c=self.save(purpose)
            for change in ({'purpose':'publishing' if purpose=='analytics' else 'analytics'},{'credential_alias':'foreign-alias'},{'configuration_sha256':'f'*64},{'target_binding_sha256':'e'*64},{'kind':'authorization'}):
                with self.assertRaises(WorkflowError):self.vault.client({**r,**change})
            self.assertEqual(self.vault.client(r).fingerprint(),c.fingerprint())
    def test_cipher_size_hash_and_prefix_tampering_never_reaches_private_decode(self):
        private,r,c=self.save();path=self.vault.path(r['reference']);raw=path.read_bytes()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO TAMPERED FILE DECRYPT')):
            for bad in (b'not-a-private-domain',raw[:-1],raw[:-1]+bytes([raw[-1]^1])):
                path.write_bytes(bad)
                with self.assertRaises(WorkflowError):self.vault.client(r)
        path.write_bytes(raw);self.assertEqual(self.vault.client(r).fingerprint(),c.fingerprint())
    def test_resealed_outer_and_inner_metadata_drift_cannot_pass_semantic_binding(self):
        for change in (lambda v:v.update(credential_alias='wrong-alias'),lambda v:v['value'].update(credential_alias='wrong-alias'),
            lambda v:v['value']['target'].update(profile_version=2),lambda v:v['value'].update(extra='not-allowed')):
            private,r,c=self.save();bad=self.reseal(r,change)
            with self.assertRaises(WorkflowError):self.vault.client(bad)
    def test_pending_pkce_state_roundtrips_to_exact_client_without_reopening_expired_authorization(self):
        private,r,c=self.save();flow=authorization(c,'http://127.0.0.1:8047/oauth/google/callback',now=NOW);saved=self.vault.save_authorization(flow,r)
        reopened=NativeGoogleOAuthVault(self.directory,self.root,self.workspace).authorization(saved)
        self.assertEqual(reopened.state,flow.state);self.assertEqual(reopened.verifier,flow.verifier);self.assertEqual(reopened.url(NOW),flow.url(NOW))
        self.assertNotIn(flow.state,json.dumps(saved));self.assertNotIn(flow.verifier,json.dumps(saved));self.assertNotIn(flow.state.encode(),self.vault.path(saved['reference']).read_bytes())
        with self.assertRaises(Exception):reopened.url(flow.expires_at)
        self.assertEqual(self.vault.authorization(saved).expires_at,flow.expires_at)
    def test_flow_rebinding_or_malformed_time_never_creates_new_private_generation(self):
        private,r,c=self.save();flow=authorization(c,'http://127.0.0.1:8047/',now=NOW);other,foreign,other_c=self.save('publishing')
        for altered,receipt in ((flow,foreign),(replace(flow,expires_at=NOW.replace(tzinfo=None)),r),(replace(flow,verifier='short'),r),(replace(flow,configuration_sha256='f'*64),r)):
            before=list(self.directory.iterdir())
            with self.assertRaises(WorkflowError):self.vault.save_authorization(altered,receipt)
            self.assertEqual(list(self.directory.iterdir()),before)
    def test_grant_both_purposes_roundtrip_and_historical_expiry_is_preserved_without_authority(self):
        for purpose in ('analytics','publishing'):
            private,r,c=self.save(purpose);c,g=grant(c);saved=self.vault.save_grant(g,r);reopened=NativeGoogleOAuthVault(self.directory,self.root,self.workspace).grant(saved)
            self.assertEqual(reopened.public(c),g.public(c));self.assertEqual(reopened.refresh_token,REFRESH);self.assertEqual(reopened.access_token,TOKEN);self.assertIsNone(reopened.refresh_expires_at)
            self.assertNotIn(TOKEN.encode(),self.vault.path(saved['reference']).read_bytes());self.assertNotIn(REFRESH,json.dumps(saved));self.assertFalse(reopened.public(c)['production_consent_renewed'])
            with self.assertRaises(Exception):reopened.credential(c,now=g.expires_at)
    def test_refresh_generation_keeps_old_cipher_and_token_then_requires_explicit_new_reference(self):
        private,r,c=self.save();c,g=grant(c);old=self.vault.save_grant(g,r);old_path=self.vault.path(old['reference']);old_sha=file_sha(old_path);stamp=NOW+timedelta(hours=2)
        request=refresh_request(c,g,now=stamp);raw={'access_token':TOKEN+'NEW','refresh_token':REFRESH+'ROTATED','expires_in':3600,'token_type':'Bearer','scope':' '.join(sorted(c.scopes))}
        refreshed=parse_tokens(c,request,GoogleTokenResponse(200,True,json.dumps(raw).encode()),now=stamp,previous=g);new=self.vault.save_grant(refreshed,r,previous=old)
        self.assertNotEqual(new['reference'],old['reference']);self.assertEqual(file_sha(old_path),old_sha);self.assertEqual(self.vault.grant(old).refresh_token,REFRESH)
        self.assertEqual(self.vault.grant(new).refresh_token,REFRESH+'ROTATED');self.assertFalse(self.vault.states()['automatic_refresh'])
    def test_prior_target_transport_configuration_or_known_refresh_expiry_cannot_expand_on_save(self):
        private,r,c=self.save();c,g=grant(c,refresh_token_expires_in=7200);old=self.vault.save_grant(g,r)
        for changed in (replace(g,mock=False),replace(g,obtained_at=NOW-timedelta(seconds=1)),replace(g,refresh_expires_at=None),replace(g,refresh_expires_at=NOW+timedelta(days=1))):
            before=list(self.directory.iterdir())
            with self.assertRaises(WorkflowError):self.vault.save_grant(changed,r,previous=old)
            self.assertEqual(list(self.directory.iterdir()),before)
        other,foreign,publishing=self.save('publishing')
        with self.assertRaises(WorkflowError):self.vault.save_grant(g,foreign,previous=old)
    def test_resealed_grant_outer_alias_target_or_client_pointer_drift_cannot_return_credential(self):
        private,r,c=self.save();c,g=grant(c)
        for change in (lambda v:v.update(target_binding_sha256='f'*64),lambda v:v.update(credential_alias='foreign-alias'),
            lambda v:v['value']['client'].update(reference='nogv_'+'f'*32),lambda v:v['value']['target'].update(profile_version=2)):
            saved=self.vault.save_grant(g,r);bad=self.reseal(saved,change)
            with self.assertRaises(WorkflowError):self.vault.grant(bad)
    def test_immutable_destination_collision_does_not_replace_original_cipher_or_leave_parts(self):
        class Fixed:hex='1'*32
        with patch('services.windows_native.google_oauth_vault.uuid.uuid4',return_value=Fixed()):
            first=self.vault.save_client(self.config());path=self.vault.path(first['reference']);sha=file_sha(path)
            with self.assertRaisesRegex(WorkflowError,'ALREADY_SAVED'):self.vault.save_client(self.config())
        self.assertEqual(file_sha(path),sha);self.assertEqual(list(self.directory.glob('*.part')),[])
    def test_missing_removed_private_client_stops_dependent_grant_and_startup_stays_inert(self):
        private,r,c=self.save();c,g=grant(c);saved=self.vault.save_grant(g,r);self.vault.path(r['reference']).unlink()
        with self.assertRaises(WorkflowError):self.vault.grant(saved)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO STARTUP DECRYPT')):
            self.assertTrue(NativeGoogleOAuthVault(self.directory,self.root,self.workspace).states()['mounted'])

if __name__=='__main__':unittest.main()
