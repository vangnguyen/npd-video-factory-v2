"""Actual DPAPI for synthetic scoped publishing credentials; no real OAuth/wire."""
import json,os,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from services.windows_native.contracts import WorkflowError
from services.windows_native import official_publication_tokens as tokens
from services.windows_native import official_account_tokens as read_tokens
from services.windows_native.official_publication_registry import Binding,Registry,PublishingFactory,load
from services.windows_native.official_publication_models import Profile,Gates
from services.windows_native.assemblyai_connection import _dpapi
from app.publishing_credentials import PublishingCredentialError,UPLOAD,READ
from app.publishing_models import PublishingTargetBinding
from app.publishing_wire import OfficialHTTPClient

class PublishingTokenFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.root=self.folder/'state';self.root.mkdir();self.path=self.folder/'secrets'/'publishing.dpapi'
        self.target=PublishingTargetBinding(workspace_id='wsp_publish_fixture',profile_id='ppf_publish_fixture',profile_version=1,platform='youtube',provider_key='youtube-data-api-publishing',target_account_id='UC_EXPLICIT_FIXTURE',credential_binding_sha256='a'*64)
        self.profile=Profile(target=self.target,category_id='27',made_for_kids=False,contains_synthetic_media=True)
        self.token=tokens.AccessToken(target=self.target,credential_alias='fixture-youtube-upload',expires_at=datetime.now(timezone.utc)+timedelta(hours=1),scopes=[UPLOAD,READ],token='EXPLICIT-PUBLISHING-TOKEN-FIXTURE-0123456789')
        self.binding=Binding(profile=self.profile,credential_alias=self.token.credential_alias,token_file=str(self.path),gates=Gates(publish_enabled=True,external_execution_enabled=True,owner_gate_enabled=True))
        self.registry=self.folder/'secrets'/'publishing-registry.json';self.registry.parent.mkdir()
    def tearDown(self):self.temp.cleanup()
    def registry_value(self):return Registry(version=1,workspace_id=self.target.workspace_id,bindings=[self.binding]).model_dump(mode='json')
    def write_registry(self,value=None):self.registry.write_text(json.dumps(value or self.registry_value()),encoding='utf-8')
    def client(self):return OfficialHTTPClient('youtube',transport=httpx.MockTransport(lambda _:self.fail('No request is authorized by token tests')))

class PublishingTokenContractTests(PublishingTokenFixture,unittest.TestCase):
    def test_read_scopes_invalid_targets_and_injected_header_data_cannot_become_upload_credentials(self):
        for change in ({'scopes':[READ]},{'scopes':[UPLOAD]},{'scopes':[UPLOAD,READ,READ]},{'scopes':['video.publish']},{'token':'EXPLICIT-FIXTURE\nINJECTION'},{'expires_at':True},{'expires_at':'2026-01-01T00:00:00'}):
            with self.assertRaises(Exception):tokens.AccessToken.model_validate({**self.token.model_dump(mode='json'),**change})
        foreign=self.target.model_copy(update={'platform':'tiktok','provider_key':'tiktok-content-posting-api'})
        with self.assertRaises(Exception):tokens.AccessToken.model_validate({**self.token.model_dump(mode='json'),'target':foreign.model_dump(mode='json')})
        self.assertNotIn(self.token.token,repr(self.token));self.assertNotIn(str(self.path),repr(self.binding))
    def test_registry_workspace_duplicates_numeric_gates_and_secret_body_fields_are_rejected(self):
        original=self.registry_value()
        for changes in ({'version':True},{'workspace_id':'wsp_foreign'},{'bindings':[original['bindings'][0],original['bindings'][0]]}):
            with self.assertRaises(ValueError):Registry.model_validate({**original,**changes})
        for changes in ({'publish_enabled':1},{'owner_gate_enabled':0},{'token':'never accepted'}):
            with self.assertRaises(ValueError):Gates.model_validate(changes)
        self.write_registry();self.assertEqual(load(self.registry,self.root,self.target.workspace_id)[self.target.profile_id].public()['status'],'NOT_CONFIGURED')
        with self.assertRaisesRegex(WorkflowError,'WORKSPACE_MISMATCH'):load(self.registry,self.root,'wsp_foreign')
        with self.assertRaises(WorkflowError):load(self.registry,self.root,self.target.workspace_id,owner_enabled=1)
    def test_registry_duplicate_json_keys_invalid_mounts_and_source_or_state_paths_reject(self):
        self.registry.write_text('{"version":1,"version":1}',encoding='utf-8')
        with self.assertRaisesRegex(WorkflowError,'REGISTRY_INVALID'):load(self.registry,self.root,self.target.workspace_id)
        for path in (self.root/'registry.json',Path('relative-registry.json')):
            with self.assertRaises(WorkflowError):load(path,self.root,self.target.workspace_id)
        for path in (str(self.root/'credential.dpapi'),'relative-token.dpapi'):
            with self.assertRaises(WorkflowError):PublishingFactory(self.profile,self.root,self.target.workspace_id,binding=self.binding.model_copy(update={'token_file':path}))
    def test_default_factory_and_registry_status_never_decrypt_or_allocate_network(self):
        self.write_registry()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No startup decryption')),patch('httpx.AsyncHTTPTransport',side_effect=AssertionError('No startup network')):
            factory=load(self.registry,self.root,self.target.workspace_id)[self.target.profile_id];state=factory.public()
            self.assertFalse(state['gates']['publish_enabled']);self.assertFalse(state['external_actions_enabled']);self.assertFalse(state['credential_present']);self.assertEqual(state['status'],'NOT_CONFIGURED')
        with self.assertRaisesRegex(WorkflowError,'NOT_CONFIGURED'):factory.credential()
    def test_binding_alias_mount_gates_client_and_root_are_frozen_against_mutation(self):
        for mutation in ('alias','mount','gates','root','binding-removed','client'):
            factory=PublishingFactory(self.profile,self.root,self.target.workspace_id,binding=self.binding,gates=self.binding.gates,client=self.client())
            if mutation=='alias':factory.binding.credential_alias='another-valid-alias'
            elif mutation=='mount':factory.binding.token_file=str(self.folder/'other.dpapi')
            elif mutation=='gates':factory.binding.gates.owner_gate_enabled=False
            elif mutation=='root':factory.root=self.folder/'other-state'
            elif mutation=='binding-removed':factory.binding=None
            else:factory.client=self.client()
            with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):factory.public()
    def test_authoritative_registry_file_change_or_removal_refuses_before_secret_resolution(self):
        self.write_registry();factory=load(self.registry,self.root,self.target.workspace_id)[self.target.profile_id]
        changed=self.registry_value();changed['bindings'][0]['gates']['publish_enabled']=False;self.write_registry(changed)
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):factory.public()
        self.write_registry();factory=load(self.registry,self.root,self.target.workspace_id)[self.target.profile_id];self.registry.unlink()
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):factory.public()

@unittest.skipUnless(os.name=='nt','Actual Windows DPAPI publishing secret tests')
class PublishingTokenWindowsTests(PublishingTokenFixture,unittest.TestCase):
    def test_actual_dpapi_private_acl_scoped_roundtrip_and_inert_receipt(self):
        receipt=tokens.save(self.path,self.root,self.token);raw=self.path.read_bytes();self.assertTrue(raw.startswith(tokens.PREFIX));self.assertNotIn(self.token.token.encode(),raw)
        loaded=tokens.load(self.path,self.root,self.target,self.token.credential_alias);self.assertEqual(loaded.token,self.token.token);self.assertEqual(loaded.target,self.target)
        self.assertFalse(receipt['publishing_enabled']);self.assertEqual(receipt['external_calls'],0);self.assertNotIn(self.token.token,json.dumps(receipt));self.assertNotIn(str(self.path),json.dumps(receipt))
        import subprocess
        acl=subprocess.check_output(['icacls',str(self.path)],encoding='utf-8',errors='replace');self.assertNotIn('Authenticated Users',acl);self.assertNotIn('(I)',acl)
    def test_publishing_and_read_only_secret_domains_are_not_interchangeable(self):
        tokens.save(self.path,self.root,self.token);raw=self.path.read_bytes()
        with self.assertRaises(Exception):_dpapi(raw[len(tokens.PREFIX):],decrypt=True,entropy=read_tokens.ENTROPY)
        with self.assertRaisesRegex(WorkflowError,'TOKEN_UNAVAILABLE'):read_tokens.load(self.path,self.root,self.target,self.token.credential_alias)
        readonly=self.folder/'secrets'/'read-only.dpapi';read_tokens.save(readonly,self.root,{'workspace_id':self.target.workspace_id,'credential_alias':self.token.credential_alias,'credential_binding_sha256':'a'*64,'platform':'youtube','expires_at':self.token.expires_at.isoformat(),'scopes':[READ],'token':self.token.token})
        with self.assertRaisesRegex(WorkflowError,'TOKEN_UNAVAILABLE'):tokens.load(readonly,self.root,self.target,self.token.credential_alias)
    def test_configured_mount_status_does_not_decrypt_and_expiry_refuses_before_wire(self):
        expired=self.token.model_copy(update={'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)});tokens.save(self.path,self.root,expired)
        factory=PublishingFactory(self.profile,self.root,self.target.workspace_id,binding=self.binding,gates=self.binding.gates,client=self.client())
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Public status cannot decrypt')):
            state=factory.public();self.assertEqual(state['status'],'CONFIGURED');self.assertFalse(state['credential_verified']);self.assertNotIn(str(self.path),json.dumps(state))
        with self.assertRaisesRegex(PublishingCredentialError,'REFRESH_REQUIRED'):factory.credential()
    def test_foreign_target_profile_version_alias_corruption_and_missing_cipher_fail_closed(self):
        tokens.save(self.path,self.root,self.token)
        for target in (self.target.model_copy(update={'workspace_id':'wsp_foreign'}),self.target.model_copy(update={'profile_version':2}),self.target.model_copy(update={'target_account_id':'UC_OTHER'}),self.target.model_copy(update={'credential_binding_sha256':'f'*64})):
            with self.assertRaisesRegex(WorkflowError,'TOKEN_UNAVAILABLE'):tokens.load(self.path,self.root,target,self.token.credential_alias)
        with self.assertRaisesRegex(WorkflowError,'TOKEN_UNAVAILABLE'):tokens.load(self.path,self.root,self.target,'another-alias')
        self.path.write_bytes(b'EXPLICIT CORRUPTED CIPHER FIXTURE')
        with self.assertRaisesRegex(WorkflowError,'TOKEN_UNAVAILABLE'):tokens.load(self.path,self.root,self.target,self.token.credential_alias)
        self.path.unlink()
        with self.assertRaisesRegex(WorkflowError,'TOKEN_UNAVAILABLE'):tokens.load(self.path,self.root,self.target,self.token.credential_alias)
    def test_atomic_save_refuses_replacement_and_source_state_hardlinks_or_invalid_token(self):
        tokens.save(self.path,self.root,self.token);before=self.path.read_bytes()
        with self.assertRaisesRegex(WorkflowError,'ALREADY_SAVED'):tokens.save(self.path,self.root,self.token)
        self.assertEqual(self.path.read_bytes(),before);self.assertEqual(list(self.path.parent.glob('*.part')),[])
        for path in (self.root/'token.dpapi','relative-secret.dpapi'):
            with self.assertRaises(WorkflowError):tokens.save(path,self.root,self.token)
        linked=self.folder/'secrets'/'linked.dpapi';os.link(self.path,linked)
        with self.assertRaisesRegex(WorkflowError,'TOKEN_UNAVAILABLE'):tokens.load(linked,self.root,self.target,self.token.credential_alias)
    def test_explicit_registry_enablement_still_does_not_read_credentials_or_verify_accounts(self):
        tokens.save(self.path,self.root,self.token);self.write_registry()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No registry-time secret read')),patch('httpx.AsyncHTTPTransport',side_effect=AssertionError('No network allocation')):
            factory=load(self.registry,self.root,self.target.workspace_id,owner_enabled=True)[self.target.profile_id];state=factory.public()
            self.assertEqual(state['status'],'CONFIGURED');self.assertTrue(state['external_actions_enabled']);self.assertFalse(state['credential_verified']);self.assertFalse(state['real_provider_tested'])
        self.assertNotIn(self.token.token,json.dumps(state));self.assertNotIn(str(self.path),json.dumps(state))

if __name__=='__main__':unittest.main()
