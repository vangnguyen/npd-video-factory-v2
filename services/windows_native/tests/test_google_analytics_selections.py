"""Explicit synthetic analytics grants; actual DPAPI/SQLite and no real account."""
import asyncio,json,unittest
from datetime import timedelta
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from app.analytics_official import AnalyticsHTTPClient,AnalyticsOAuthCredential,AnalyticsQuery,AnalyticsOfficialError
from app.publishing_wire import OfficialHTTPClient,OfficialRequest,bearer_headers
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.backup import database_status
from services.windows_native.google_oauth_selections import NativeGoogleOAuthSelections,Select,Revoke
from services.windows_native.official_account_registry import Account,OAuthAccount,Registry,AccountFactory,load
from services.windows_native.official_publication_registry import OAuthBinding,PublishingFactory
from services.windows_native.official_publication_models import Profile
from services.windows_native.tests.test_google_oauth_operations import OAuthOperationsFixture
from services.windows_native.tests.test_google_oauth_protocol import TOKEN,REFRESH,SECRET,CODE

class GoogleAnalyticsSelectionTests(OAuthOperationsFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.successful('analytics');self.channel_calls=[];self.channel_mode=None
        self.slot=self.slots['ngos_'+'a'*32]
        self.channel_client=AnalyticsHTTPClient('youtube',transport=httpx.MockTransport(self.channel_response))
        self.selections=NativeGoogleOAuthSelections(self.operations,purpose='analytics',enabled=True,client=self.channel_client)
    def channel_response(self,request):
        self.channel_calls.append({'method':request.method,'host':request.url.host,'path':request.url.path})
        self.assertEqual(request.method,'GET');self.assertEqual(request.url.params['mine'],'true');self.assertEqual(request.headers['authorization'],'Bearer '+TOKEN+'1')
        if self.channel_mode=='timeout':raise httpx.ReadTimeout(SECRET,request=request)
        if self.channel_mode=='revoke':self.revoke()
        if self.channel_mode=='edit':self.store.save(self.project['id'],1,prompt='Later explicit fixture')
        if self.channel_mode=='recover':self.selections.recover()
        if self.channel_mode=='backup':self.busy_status=database_status(self.store.db)
        return httpx.Response(200,json={'items':[{'id':'wrong-explicit-channel' if self.channel_mode=='wrong' else self.slot.target.target_account_id}]})
    def payload(self,**changes):
        return Select.model_validate({'revision':self.project['revision'],'source_operation_id':self.done['operation_id'],'expected_result_sha256':self.done['result_sha256'],
            'acknowledged_account_access':True,'acknowledged_credential_selection':True,'acknowledged_protocol_mock':True,'request_key':'explicit-analytics-select-fixture',**changes})
    def selection(self,**changes):return self.selections.create(self.project['id'],self.payload(**changes),principal=self.principal)[0]
    def verify(self,value):return asyncio.run(self.selections.verify(self.project['id'],value['selection_id'],principal=self.principal,expected_snapshot_sha256=value['snapshot_sha256']))
    def selected(self):return self.verify(self.selection())
    def factory(self,enabled=False):
        account=OAuthAccount(account_ref='npac_'+'d'*32,target=self.slot.target,credential_alias=self.slot.client.credential_alias,credential_source='google_oauth_selection',google_oauth_slot_id=self.slot.slot_id,read_enabled=True)
        return AccountFactory(account,self.root,self.workspace,owner_read_enabled=enabled,transport=self.channel_client.wire.transport)
    def test_disabled_constructor_registry_discovery_and_history_do_not_decrypt_or_send(self):
        self.selections=NativeGoogleOAuthSelections(self.operations,purpose='analytics',client=self.channel_client)
        with patch.object(self.vault,'grant',side_effect=AssertionError('No default decryption')):
            value=self.selection();self.assertEqual(value['status'],'not_configured');self.assertFalse(self.selections.states()['enabled'])
            factory=self.factory();factory.resolver.attach(self.selections);self.assertEqual(factory.public()['status'],'NOT_CONFIGURED')
            self.selections.get(self.project['id'],value['selection_id']);self.selections.page(self.project['id']);self.selections.recover()
        self.assertEqual(self.channel_calls,[]);self.assertFalse(value['publishing_enabled'])
    def test_exact_grant_account_and_typed_runtime_credential_remain_readonly(self):
        value=self.selected();self.assertEqual(value['status'],'active');self.assertTrue(value['selection_id'].startswith('ngasel_'))
        self.assertEqual(value['snapshot']['schema_version'],'native-google-analytics-selection-snapshot-v1')
        credential=self.selections.credential(self.slot.slot_id,self.slot.target);self.assertIs(type(credential),AnalyticsOAuthCredential);self.assertEqual(credential.token,TOKEN+'1')
        factory=self.factory(True);factory.resolver.attach(self.selections);self.assertEqual(factory.credential(now=self.clock[0]),credential)
        self.assertEqual(factory.public()['status'],'CONFIGURED');self.assertFalse(factory.public()['publishing_enabled']);self.assertFalse(value['result']['real_provider_tested'])
        with self.assertRaises(AnalyticsOfficialError):asyncio.run(self.channel_client.request(OfficialRequest('POST','https://www.googleapis.com/upload/youtube/v3/videos',bearer_headers(credential.token))))
        for secret in (TOKEN,REFRESH,SECRET,CODE):self.assertNotIn(secret,json.dumps([value,factory.public()]))
        self.assertEqual(len(self.channel_calls),1);self.assertEqual(self.store.get(self.project['id'])['revision'],1)
    def test_publishing_grant_and_resolver_cannot_be_substituted(self):
        self.successful('publishing')
        with self.assertRaisesRegex(WorkflowError,'PURPOSE_OR_MOCK_CHANGED'):self.selection()
        pubslot=self.slots['ngos_'+'b'*32];profile=Profile(target=pubslot.target,category_id='28',made_for_kids=False,contains_synthetic_media=True)
        factory=PublishingFactory(profile,self.root,self.workspace,binding=OAuthBinding(credential_source='google_oauth_selection',profile=profile,credential_alias=pubslot.client.credential_alias,google_oauth_slot_id=pubslot.slot_id))
        with self.assertRaises(WorkflowError):factory.resolver.attach(self.selections)
        analytics_factory=self.factory()
        with self.assertRaises(WorkflowError):analytics_factory.resolver.attach(NativeGoogleOAuthSelections(self.operations))
        self.assertIsNone(analytics_factory.resolver.service);self.assertEqual(self.channel_calls,[])
    def test_factory_read_gate_independent_and_mock_selection_cannot_mount_network(self):
        self.selected();factory=self.factory();factory.resolver.attach(self.selections)
        self.assertTrue(factory.public()['credential_present']);self.assertEqual(factory.public()['status'],'NOT_CONFIGURED')
        with self.assertRaisesRegex(WorkflowError,'READ_DISABLED'):factory.credential(now=self.clock[0])
        network=AccountFactory(factory.account,self.root,self.workspace,owner_read_enabled=True);network.resolver.attach(self.selections)
        self.assertFalse(network.public()['credential_present'])
    def test_revenue_scope_required_before_any_report_request(self):
        self.selected();factory=self.factory(True);factory.resolver.attach(self.selections)
        query=AnalyticsQuery(start_date=self.clock[0].date(),end_date=self.clock[0].date(),include_revenue=True)
        with self.assertRaisesRegex(AnalyticsOfficialError,'SCOPES_REQUIRED'):factory.credential(query,now=self.clock[0])
        self.assertEqual(len(self.channel_calls),1)
    def test_unknown_and_wrong_channel_do_not_retry_or_select(self):
        for mode,status in [('wrong','failed'),('timeout','outcome_unknown')]:
            self.channel_mode=mode;result=self.verify(self.selection(request_key='explicit-analytics-select-'+mode));self.assertEqual(result['status'],status)
            with self.assertRaises(WorkflowError):self.verify(result)
        self.assertEqual(len(self.channel_calls),2)
    def test_current_owner_and_document_change_after_response_prevent_selection(self):
        self.channel_mode='edit';result=self.verify(self.selection());self.assertEqual(result['status'],'review_required');self.assertIsNone(result['result'])
        self.assertEqual(len(self.channel_calls),1)
    def test_final_private_load_revocation_blocks_account_wire(self):
        value=self.selection();load=self.vault.grant
        def private(receipt):v=load(receipt);self.revoke();return v
        with patch.object(self.vault,'grant',side_effect=private):result=self.verify(value)
        self.assertEqual(result['status'],'failed');self.assertEqual(self.channel_calls,[])
    def test_local_revoke_and_readonly_nested_writer(self):
        value=self.selected();factory=self.factory(True);factory.resolver.attach(self.selections)
        with self.store.transaction():self.assertTrue(factory.public()['credential_present']);self.assertEqual(factory.credential(now=self.clock[0]).token,TOKEN+'1')
        self.selections.revoke(self.project['id'],value['selection_id'],Revoke(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        self.assertFalse(factory.public()['credential_present']);self.assertEqual(len(self.channel_calls),1)
    def test_refresh_requires_new_explicit_selection_and_never_decrypts_superseded_grant(self):
        value=self.selected();factory=self.factory(True);factory.resolver.attach(self.selections)
        self.done=self.refresh();self.assertEqual(self.done['status'],'succeeded')
        with patch.object(self.vault,'grant',side_effect=AssertionError('No superseded grant decrypt')):
            self.assertFalse(factory.public()['credential_present'])
            with self.assertRaises(WorkflowError):factory.credential(now=self.clock[0])
        self.assertEqual(len(self.channel_calls),1);self.assertEqual(self.selections.get(self.project['id'],value['selection_id'])['status'],'active')
    def test_expired_grant_margin_blocks_availability_and_private_decryption(self):
        self.selected();factory=self.factory(True);factory.resolver.attach(self.selections);self.clock[0]+=timedelta(seconds=3511)
        with patch.object(self.vault,'grant',side_effect=AssertionError('No expired selection decrypt')):
            self.assertFalse(factory.public()['credential_present'])
            with self.assertRaisesRegex(WorkflowError,'REFRESH_REQUIRED'):self.selections.credential(self.slot.slot_id,self.slot.target)
        self.assertEqual(len(self.channel_calls),1)
    def test_active_analytics_and_publishing_choices_use_separate_journals(self):
        analytics=self.selected();self.successful('publishing');slot=self.slots['ngos_'+'b'*32]
        def channel(request):
            self.assertEqual(request.headers['authorization'],'Bearer '+TOKEN+'2')
            return httpx.Response(200,json={'items':[{'id':slot.target.target_account_id}]})
        publishing=NativeGoogleOAuthSelections(self.operations,enabled=True,client=OfficialHTTPClient('youtube',transport=httpx.MockTransport(channel)))
        pending=publishing.create(self.project['id'],self.payload(),principal=self.principal)[0]
        active=asyncio.run(publishing.verify(self.project['id'],pending['selection_id'],principal=self.principal,expected_snapshot_sha256=pending['snapshot_sha256']))
        self.assertEqual(active['status'],'active');self.assertEqual(slot.target,self.slot.target)
        self.assertEqual(self.selections.get(self.project['id'],analytics['selection_id'])['status'],'active')
        publishing.revoke(self.project['id'],active['selection_id'],Revoke(expected_snapshot_sha256=active['snapshot_sha256']),principal=self.principal)
        self.assertEqual(self.selections.credential(self.slot.slot_id,self.slot.target).token,TOKEN+'1')
        self.assertEqual(len(self.selections.page(self.project['id'])['items']),1);self.assertEqual(len(publishing.page(self.project['id'])['items']),1)
    def test_recovery_claim_cost_and_history_without_provider_replay(self):
        self.channel_mode='recover';value=self.verify(self.selection());self.assertEqual(value['status'],'outcome_unknown')
        self.assertEqual(self.selections.recover(),0);self.assertEqual(len(self.channel_calls),1)
    def test_backup_counts_claimed_analytics_selection_and_blocks_midflight_snapshot(self):
        self.channel_mode='backup';self.selected();self.assertEqual(self.busy_status['active_operations'],1)
        self.assertEqual(self.busy_status['counts']['native_google_analytics_selections'],1)
        self.assertEqual(database_status(self.store.db)['active_operations'],0)
    def test_legacy_account_bytes_and_tagged_registry_pin_are_preserved(self):
        factory=self.factory();account=factory.account;legacy=Account(account_ref=account.account_ref,target=account.target,credential_alias=account.credential_alias,token_file=str(self.private/'legacy.dpapi'))
        raw={'account_ref':legacy.account_ref,'target':legacy.target.model_dump(mode='json'),'credential_alias':legacy.credential_alias,'token_file':legacy.token_file,'read_enabled':False,'publishing_enabled':False}
        self.assertEqual(legacy.model_dump(mode='json'),raw);self.assertEqual(digest(raw),digest(legacy.model_dump(mode='json')))
        path=self.folder/'public-analytics-selection-accounts.json';path.write_text(json.dumps(Registry(version=1,workspace_id=self.workspace,accounts=[account]).model_dump(mode='json')),encoding='utf-8')
        with patch.object(self.vault,'grant',side_effect=AssertionError('No registry decryption')):
            loaded=load(path,self.root,self.workspace)[account.account_ref];self.assertIs(type(loaded.account),OAuthAccount);self.assertIsNone(loaded.path);self.assertEqual(loaded.public()['status'],'NOT_CONFIGURED')
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(WorkflowError):loaded.public()
        invalid=account.model_dump(mode='json');invalid['token_file']=legacy.token_file
        with self.assertRaises(ValidationError):Registry(version=1,workspace_id=self.workspace,accounts=[invalid])
    def test_policy_table_wire_and_resolver_binding_mutations_fail_closed(self):
        self.selections.purpose='publishing'
        with self.assertRaises(WorkflowError):self.selections.states()
        factory=self.factory();factory.resolver.binding.credential_alias='explicit-wrong-alias'
        with self.assertRaises(WorkflowError):factory.public()
    def test_missing_or_foreign_transport_is_a_bounded_configuration_error(self):
        for attribute in ('wire','client'):
            service=NativeGoogleOAuthSelections(self.operations,purpose='analytics',enabled=True,client=self.channel_client)
            setattr(service,attribute,None)
            with self.assertRaises(WorkflowError):service.states()
    def test_policy_change_is_rejected_before_write_transaction_for_all_mutations(self):
        value=self.selection();self.selections.table='native_google_oauth_selections'
        with patch.object(self.store,'transaction',side_effect=AssertionError('No changed-policy SQL')):
            with self.assertRaises(WorkflowError):self.selections.create(self.project['id'],self.payload(),principal=self.principal)
            with self.assertRaises(WorkflowError):self.verify(value)
            with self.assertRaises(WorkflowError):self.selections.revoke(self.project['id'],value['selection_id'],Revoke(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)

if __name__=='__main__':unittest.main()
