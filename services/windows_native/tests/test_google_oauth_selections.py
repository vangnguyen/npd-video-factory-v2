"""Owned DPAPI/SQLite and explicit protocol fixtures; no real OAuth or upload."""
import asyncio,json,unittest
from datetime import timedelta
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from app.publishing_wire import OfficialHTTPClient
from app.publishing_credentials import PublishingOAuthCredential
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.google_oauth_selections import NativeGoogleOAuthSelections,Select,Revoke
from services.windows_native.official_publication_registry import Binding,OAuthBinding,Registry,PublishingFactory,load
from services.windows_native.official_publication_models import Profile,Gates
from services.windows_native.tests.test_google_oauth_operations import OAuthOperationsFixture
from services.windows_native.tests.test_google_oauth_protocol import TOKEN,REFRESH,SECRET,CODE


class GoogleOAuthSelectionTests(OAuthOperationsFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.successful('publishing');self.channel_calls=[];self.channel_mode=None
        self.channel_wire=OfficialHTTPClient('youtube',transport=httpx.MockTransport(self.channel_response))
        self.selections=NativeGoogleOAuthSelections(self.operations,enabled=True,client=self.channel_wire)
        self.slot=self.slots['ngos_'+'b'*32]

    def channel_response(self,request):
        self.channel_calls.append({'method':request.method,'host':request.url.host,'path':request.url.path,'query':str(request.url.query)})
        self.assertEqual(request.method,'GET');self.assertEqual(request.url.path,'/youtube/v3/channels');self.assertEqual(request.url.params['mine'],'true')
        self.assertEqual(request.headers['authorization'],'Bearer '+TOKEN+'1')
        if self.channel_mode=='timeout':raise httpx.ReadTimeout(SECRET,request=request)
        if self.channel_mode=='revoke-owner':self.revoke()
        if self.channel_mode=='edit':self.store.save(self.project['id'],self.project['revision'],prompt='Later fixture edit')
        if self.channel_mode=='recover':self.selections.recover()
        return httpx.Response(200,json={'items':[{'id':'foreign-fixture-channel' if self.channel_mode=='wrong' else self.slot.target.target_account_id}]})

    def payload(self,**changes):
        return Select.model_validate({'revision':self.project['revision'],'source_operation_id':self.done['operation_id'],
            'expected_result_sha256':self.done['result_sha256'],'acknowledged_account_access':True,'acknowledged_credential_selection':True,
            'acknowledged_protocol_mock':True,'request_key':'explicit-google-credential-selection',**changes})

    def selection(self,**changes):return self.selections.create(self.project['id'],self.payload(**changes),principal=self.principal)[0]
    def verify_selection(self,value):return asyncio.run(self.selections.verify(self.project['id'],value['selection_id'],principal=self.principal,expected_snapshot_sha256=value['snapshot_sha256']))
    def active_selection(self):return self.verify_selection(self.selection())
    def factory(self,**changes):
        binding=OAuthBinding(credential_source='google_oauth_selection',profile=Profile(target=self.slot.target,category_id='28',made_for_kids=False,contains_synthetic_media=True),
            credential_alias=self.slot.client.credential_alias,google_oauth_slot_id=self.slot.slot_id)
        return PublishingFactory(binding.profile,self.root,self.workspace,binding=binding,client=self.channel_wire,**changes)

    def test_default_inert_discovery_and_selection_keep_publish_disabled(self):
        self.selections=NativeGoogleOAuthSelections(self.operations,client=self.channel_wire)
        with patch.object(self.vault,'grant',side_effect=AssertionError('No default decryption')):
            value=self.selection();self.assertEqual(value['status'],'not_configured');self.selections.page(self.project['id']);self.selections.recover()
            factory=self.factory();self.assertFalse(factory.public()['credential_present']);factory.resolver.attach(self.selections)
            self.assertEqual(factory.public()['status'],'NOT_CONFIGURED')
        self.assertEqual(self.channel_calls,[]);self.assertFalse(value['publishing_enabled'])

    def test_explicit_verify_exact_account_returns_runtime_credential_no_public_secret(self):
        value=self.active_selection();self.assertEqual(value['status'],'active');self.assertTrue(value['result']['mock'])
        self.assertFalse(value['result']['real_provider_tested']);self.assertEqual(len(self.channel_calls),1)
        credential=self.selections.credential(self.slot.slot_id,self.slot.target);self.assertIs(type(credential),PublishingOAuthCredential);self.assertEqual(credential.token,TOKEN+'1')
        public=json.dumps(value)
        for secret in (TOKEN,REFRESH,SECRET,CODE):self.assertNotIn(secret,public)
        self.assertEqual(self.store.get(self.project['id'])['revision'],1)
        self.assertFalse(value['publishing_enabled']);self.assertFalse(value['automatic_refresh'])
        self.assertEqual(self.verify_selection(value),value);self.assertEqual(len(self.channel_calls),1)

    def test_owner_idempotency_and_raw_separate_acknowledgements(self):
        first=self.selection();value,replay=self.selections.create(self.project['id'],self.payload(),principal=self.principal)
        self.assertTrue(replay);self.assertEqual(value,first);self.assertEqual(self.channel_calls,[])
        with self.assertRaises(WorkflowError):self.selection(valid_for_seconds=601)
        for field in ('acknowledged_account_access','acknowledged_credential_selection','acknowledged_protocol_mock'):
            for raw in (1,'true',None):
                with self.subTest(field=field,raw=raw),self.assertRaises(ValidationError):self.payload(**{field:raw})
        self.revoke()
        with self.assertRaises(WorkflowError):self.selection()

    def test_analytics_grant_cannot_be_selected_for_publishing(self):
        self.successful('analytics')
        with self.assertRaisesRegex(WorkflowError,'PURPOSE_OR_MOCK_CHANGED'):self.selection()
        self.assertEqual(self.channel_calls,[])

    def test_wrong_channel_and_timeout_never_enable_or_auto_retry(self):
        for mode,status in (('wrong','failed'),('timeout','outcome_unknown')):
            with self.subTest(mode=mode):
                self.channel_mode=mode;value=self.selection(request_key='explicit-selection-'+mode);result=self.verify_selection(value)
                self.assertEqual(result['status'],status);self.assertIsNone(result['result'])
                with self.assertRaises(WorkflowError):self.verify_selection(result)
                with self.assertRaises(WorkflowError):self.selections.credential(self.slot.slot_id,self.slot.target)
        self.assertEqual(len(self.channel_calls),2);self.assertNotIn(SECRET,json.dumps(result))

    def test_revocation_or_edit_during_channel_response_requires_review(self):
        self.channel_mode='edit';value=self.verify_selection(self.selection());self.assertEqual(value['status'],'review_required')
        self.assertIsNone(value['result']);self.assertEqual(len(self.channel_calls),1)

    def test_revocation_at_last_private_load_prevents_any_channel_wire(self):
        value=self.selection();original=self.vault.grant
        def load(receipt):
            grant=original(receipt);self.revoke();return grant
        with patch.object(self.vault,'grant',side_effect=load):result=self.verify_selection(value)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.channel_calls,[])

    def test_revoked_owner_and_expired_token_fail_runtime_metadata_without_decrypt(self):
        self.active_selection();factory=self.factory();factory.resolver.attach(self.selections)
        with patch.object(self.vault,'grant',side_effect=AssertionError('No metadata decryption')):
            self.assertTrue(factory.public()['credential_present']);self.clock[0]+=timedelta(seconds=3511)
            self.assertFalse(factory.public()['credential_present'])
        self.assertEqual(len(self.channel_calls),1)

    def test_local_revoke_blocks_resolver_without_external_action(self):
        value=self.active_selection();factory=self.factory();factory.resolver.attach(self.selections)
        result=self.selections.revoke(self.project['id'],value['selection_id'],Revoke(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        self.assertEqual(result['status'],'revoked');self.assertFalse(factory.public()['credential_present']);self.assertEqual(len(self.channel_calls),1)
        self.assertEqual(self.selections.get(self.project['id'],value['selection_id'])['result'],value['result'])

    def test_refresh_supersedes_selection_and_requires_explicit_new_verification(self):
        self.active_selection();next_grant=self.refresh();self.assertEqual(next_grant['status'],'succeeded')
        with self.assertRaisesRegex(WorkflowError,'GRANT_SUPERSEDED'):self.selections.credential(self.slot.slot_id,self.slot.target)
        self.done=next_grant;value=self.selection(request_key='explicit-select-refreshed-grant')
        self.assertEqual(value['status'],'pending_verification');self.assertEqual(len(self.channel_calls),1)

    def test_encrypted_file_or_cost_tampering_blocks_current_or_history(self):
        value=self.active_selection();path=self.vault.path(value['snapshot']['grant_receipt']['reference']);original=path.read_bytes()
        path.write_bytes(original+b'fixture')
        with self.assertRaisesRegex(WorkflowError,'PRIVATE_FILE_CHANGED'):self.selections.active(self.slot.slot_id,self.slot.target)
        path.write_bytes(original)
        with self.store.transaction() as con:con.execute("UPDATE native_cost_operations SET external_call=1 WHERE id=?",(value['cost_operation_id'],))
        with self.assertRaisesRegex(WorkflowError,'COST_EVIDENCE_CHANGED'):self.selections.get(self.project['id'],value['selection_id'])

    def test_recovery_claim_has_no_nested_writer_or_provider_replay(self):
        value=self.selection();self.channel_mode='recover';result=self.verify_selection(value)
        self.assertEqual(result['status'],'outcome_unknown');self.assertIsNone(result['result']);self.assertEqual(len(self.channel_calls),1)
        self.assertEqual(self.selections.recover(),0)
        with self.assertRaises(WorkflowError):self.verify_selection(result)

    def test_oauth_factory_gates_remain_off_and_selected_mock_cannot_mount_network(self):
        self.active_selection();factory=self.factory();factory.resolver.attach(self.selections)
        self.assertTrue(factory.public()['credential_present']);self.assertEqual(factory.public()['status'],'NOT_CONFIGURED')
        with self.assertRaises(WorkflowError):factory.credential(now=self.clock[0])
        enabled=self.factory(gates=Gates(publish_enabled=True,external_execution_enabled=True,owner_gate_enabled=True));enabled.resolver.attach(self.selections)
        self.assertEqual(enabled.credential(now=self.clock[0]).token,TOKEN+'1')
        network=PublishingFactory(enabled.profile,self.root,self.workspace,binding=enabled.binding,gates=enabled.gates,client=OfficialHTTPClient('youtube',network_enabled=True))
        network.resolver.attach(self.selections);self.assertFalse(network.public()['credential_present'])

    def test_atomic_attachment_freezes_binding_root_slot_and_rejects_twice(self):
        factory=self.factory();wrong=self.factory();wrong.resolver.binding.credential_alias='explicit-wrong-alias'
        with self.assertRaises(WorkflowError):wrong.resolver.attach(self.selections)
        self.assertIsNone(wrong.resolver.service)
        factory.resolver.attach(self.selections)
        with self.assertRaises(WorkflowError):factory.resolver.attach(self.selections)
        factory.binding.google_oauth_slot_id='ngos_'+'a'*32
        with self.assertRaises(WorkflowError):factory.public()

    def test_legacy_binding_serialization_and_strict_registry_are_unchanged(self):
        profile=self.factory().profile
        binding=Binding(profile=profile,credential_alias='legacy-explicit-fixture',token_file=str(self.private/'legacy.dpapi'))
        raw={'profile':profile.model_dump(mode='json'),'credential_alias':binding.credential_alias,'token_file':binding.token_file,'gates':Gates().model_dump()}
        self.assertEqual(binding.model_dump(mode='json'),raw);self.assertEqual(digest(binding.model_dump(mode='json')),digest(raw))
        registry=Registry(version=1,workspace_id=self.workspace,bindings=[self.factory().binding]);self.assertIs(type(registry.bindings[0]),OAuthBinding)
        invalid=self.factory().binding.model_dump(mode='json');invalid['token_file']=binding.token_file
        with self.assertRaises(ValidationError):Registry(version=1,workspace_id=self.workspace,bindings=[invalid])
        self.assertEqual(self.channel_calls,[])

    def test_protected_oauth_registry_load_stays_inert_and_pins_original_bytes(self):
        binding=self.factory().binding;path=self.folder/'publishing-selected-fixture.json'
        path.write_text(json.dumps(Registry(version=1,workspace_id=self.workspace,bindings=[binding]).model_dump(mode='json')),encoding='utf-8')
        with patch.object(self.vault,'grant',side_effect=AssertionError('No registry decryption')):
            factory=load(path,self.root,self.workspace)[self.slot.target.profile_id]
            self.assertIs(type(factory.binding),OAuthBinding);self.assertIsNone(factory.path);self.assertIsNone(factory.resolver.service)
            self.assertEqual(factory.public()['status'],'NOT_CONFIGURED');factory.resolver.attach(self.selections)
            self.assertFalse(factory.public()['credential_present'])
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):factory.public()
        self.assertEqual(self.channel_calls,[])

    def test_runtime_readonly_snapshot_is_safe_inside_existing_writer_and_pins_db(self):
        value=self.active_selection()
        with self.store.transaction() as con:
            current,_=self.selections.active(self.slot.slot_id,self.slot.target);self.assertEqual(current,value)
            self.assertEqual(con.execute('SELECT count(*) FROM native_google_oauth_selections').fetchone()[0],1)
        self.store.db=self.root/'foreign-fixture.sqlite3'
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.selections.states()

    def test_pending_history_rejects_extra_private_authority_fields_even_with_rehashed_snapshot(self):
        value=self.selection();snapshot=value['snapshot'];snapshot['authority']['private_token']=TOKEN
        with self.store.transaction() as con:con.execute('UPDATE native_google_oauth_selections SET snapshot_json=?,snapshot_sha256=? WHERE selection_id=?',
            (json.dumps(snapshot),digest(snapshot),value['selection_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.selections.get(self.project['id'],value['selection_id'])
        self.assertEqual(self.channel_calls,[])


if __name__=='__main__':unittest.main()
