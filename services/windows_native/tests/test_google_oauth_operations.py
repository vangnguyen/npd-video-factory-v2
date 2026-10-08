"""Actual private DPAPI/SQLite and explicit protocol mocks, never genuine OAuth."""
import asyncio,copy,json,tempfile,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlencode,parse_qs
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.google_oauth_vault import NativeGoogleOAuthVault,PrivateClient
from services.windows_native.google_oauth_operations import NativeGoogleOAuthOperations,Slot,Start,Refresh,Cancel,TABLES
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.backup import database_status
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_publications import CAPABILITIES
from services.windows_native.tests.test_google_oauth_protocol import client,TOKEN,REFRESH,SECRET,CODE
from app.google_oauth_protocol import GoogleOAuthTokenClient,GoogleOAuthError
from app.human_identity import HumanAuthVerifier,HumanAuthRegistry

class OAuthOperationsFixture:
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name).resolve();self.root=self.folder/'state';self.root.mkdir();self.store=Store(self.root)
        self.workspace='wsp_google_oauth_fixture';self.clock=[datetime.now(timezone.utc)];self.calls=[];self.mode=None
        (self.root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}),encoding='utf-8')
        self.raw,data=human_fixture('owner',workspace=self.workspace);self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400);self.principal=self.verifier.verify('Bearer '+self.raw)
        self.publications=NativePublications(self.store,CAPABILITIES,workspace_id=self.workspace,clock=lambda:self.clock[0]);self.accounts=NativeOfficialAccounts(self.store,workspace_id=self.workspace,clock=lambda:self.clock[0])
        self.review=NativeOfficialPublications(self.store,self.publications,self.accounts,identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])
        self.project=self.store.create('Explicit synthetic OAuth fixture','','media');self.private=self.folder/'private';self.vault=NativeGoogleOAuthVault(self.private,self.root,self.workspace)
        self.slots={}
        for purpose,char in (('analytics','a'),('publishing','b')):
            c=client(purpose);receipt=self.vault.save_client(PrivateClient(target=c.target,purpose=c.purpose,credential_alias='explicit-google-'+purpose,client_id=c.client_id,scopes=sorted(c.scopes),client_secret=c.client_secret))
            slot=Slot(slot_id='ngos_'+char*32,target=c.target,client=receipt,client_id=c.client_id,scopes=sorted(c.scopes));self.slots[slot.slot_id]=slot
        self.wire=GoogleOAuthTokenClient(transport=httpx.MockTransport(self.response));self.operations=self.service(enabled=True)
    def tearDown(self):
        assert self.folder.parent==Path(tempfile.gettempdir()).resolve();self.temp.cleanup()
    def service(self,enabled=False,slots=None,vault=None):return NativeGoogleOAuthOperations(self.review,vault or self.vault,slots=self.slots if slots is None else slots,client=self.wire,enabled=enabled)
    def response(self,request):
        fields=parse_qs(request.content.decode());self.calls.append({'method':request.method,'host':request.url.host,'path':request.url.path,'operation':fields['grant_type'][0]})
        if self.mode=='timeout':raise httpx.ReadTimeout(SECRET,request=request)
        if self.mode=='revoke':self.revoke()
        if self.mode=='edit':self.store.save(self.project['id'],self.project['revision'],prompt='Explicit later edit')
        if self.mode=='expired':self.clock[0]+=timedelta(seconds=601)
        if self.mode=='recover':self.operations.recover()
        if self.mode=='invalid-grant':return httpx.Response(400,json={'error':'invalid_grant','error_description':SECRET})
        if self.mode=='rate-limit':return httpx.Response(429,json={'error':'temporarily_unavailable'})
        if self.mode=='foreign-scope':return httpx.Response(200,json={'access_token':TOKEN,'refresh_token':REFRESH,'expires_in':3600,'token_type':'Bearer','scope':'openid'})
        c=client('publishing' if self.purpose=='publishing' else 'analytics');value={'access_token':TOKEN+str(len(self.calls)),'expires_in':3600,'token_type':'Bearer','scope':' '.join(sorted(c.scopes))}
        if fields['grant_type']==['authorization_code'] or self.mode=='rotate':value['refresh_token']=REFRESH+str(len(self.calls))
        return httpx.Response(200,json=value)
    def revoke(self):
        data=copy.deepcopy(self.verifier.registry.model_dump(mode='json'));data['tokens'][self.principal.token_id]['enabled']=False;self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
    def start_payload(self,purpose='analytics',**changes):
        self.purpose=purpose;slot=self.slots['ngos_'+('a' if purpose=='analytics' else 'b')*32]
        return Start.model_validate({'revision':self.project['revision'],'slot_id':slot.slot_id,'expected_configuration_sha256':slot.client.configuration_sha256,
            'acknowledged_credential_operation':True,'acknowledged_protocol_mock':True,'redirect_uri':'http://127.0.0.1:18047/oauth/google/callback','request_key':'explicit-google-start-key-'+purpose,**changes})
    def start(self,purpose='analytics',**changes):
        self.start_request=self.start_payload(purpose,**changes);self.saved=self.operations.start(self.project['id'],self.start_request,principal=self.principal)[0];return self.saved
    def query(self):
        flow=self.vault.authorization(self.saved['snapshot']['authorization_receipt']);return urlencode({'state':flow.state,'code':CODE})
    def exchange(self,query=None):return asyncio.run(self.operations.exchange(self.project['id'],self.saved['authorization_id'],query or self.query(),principal=self.principal,expected_snapshot_sha256=self.saved['snapshot_sha256']))
    def successful(self,purpose='analytics'):self.start(purpose);self.done=self.exchange();assert self.done['status']=='succeeded';return self.done
    def refresh_payload(self,**changes):
        return Refresh(revision=self.store.get(self.project['id'])['revision'],slot_id=self.done['snapshot']['request']['slot_id'],expected_configuration_sha256=self.done['snapshot']['request']['expected_configuration_sha256'],
            acknowledged_credential_operation=True,acknowledged_protocol_mock=True,source_operation_id=self.done['operation_id'],expected_result_sha256=self.done['result_sha256'],request_key='explicit-google-refresh-key',**changes)
    def refresh(self,payload=None):return asyncio.run(self.operations.refresh(self.project['id'],payload or self.refresh_payload(),principal=self.principal))

class GoogleOAuthOperationsTests(OAuthOperationsFixture,unittest.TestCase):
    def test_default_constructor_discovery_start_and_recovery_do_not_decrypt_or_send(self):
        self.operations=self.service()
        with patch.object(self.vault,'client',side_effect=AssertionError('NO DEFAULT DECRYPT')):
            self.operations.states();value=self.start();self.assertEqual(value['status'],'not_configured');self.assertIsNone(value['snapshot']['authorization_receipt']);self.operations.recover()
        self.assertEqual(self.calls,[]);self.assertFalse(self.operations.states()['enabled']);self.assertEqual(self.store.get(self.project['id'])['revision'],1)
    def test_start_exact_key_url_not_stored_explicit_cancel_and_no_provider(self):
        value=self.start();url=self.operations.authorization_url(self.project['id'],value['authorization_id'],principal=self.principal,expected_snapshot_sha256=value['snapshot_sha256'])
        self.assertTrue(url.startswith('https://accounts.google.com/o/oauth2/v2/auth?'));self.assertIn('code_challenge_method=S256',url)
        replay,found=self.operations.start(self.project['id'],self.start_request,principal=self.principal);self.assertTrue(found);self.assertEqual(value,replay)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.operations.start(self.project['id'],self.start_request.model_copy(update={'valid_for_seconds':601}),principal=self.principal)
        cancelled=self.operations.cancel(self.project['id'],value['authorization_id'],Cancel(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        self.assertEqual(cancelled['status'],'cancelled')
        with self.assertRaisesRegex(WorkflowError,'NOT_PENDING'):self.exchange()
        self.assertEqual(self.calls,[]);self.assertNotIn('state=',self.root.joinpath('workflow.sqlite3').read_bytes().decode(errors='ignore'))
    def test_actual_callback_claim_grant_cost_and_project_unchanged_for_both_purposes(self):
        original=self.store.get(self.project['id'])
        for purpose in ('analytics','publishing'):
            value=self.successful(purpose);proof=value['result']['grant_proof'];self.assertEqual(proof['purpose'],purpose);self.assertIsNone(proof['refresh_expires_at']);self.assertTrue(proof['mock'])
            self.assertFalse(value['result']['credential_selected']);self.assertFalse(proof['production_consent_renewed']);self.assertFalse(proof['account_verified']);self.assertFalse(proof['publishing_enabled'])
            self.assertEqual(self.operations.get(self.project['id'],value['operation_id']),value)
        costs=self.operations.costs.summary(self.project['id'])['records'];self.assertEqual(len(costs),2);self.assertTrue(all(x['status']=='response_received' and not x['paid'] and not x['external_call'] and x['actual_cost'] is None for x in costs))
        self.assertEqual(self.store.get(self.project['id']),original);self.assertEqual(len(self.calls),2)
    def test_bad_state_duplicate_fields_and_non_owner_fail_without_consuming(self):
        self.start()
        for query in ('state=foreign&code='+CODE,self.query()+'&state=duplicate','state=foreign&error=access_denied'):
            with self.assertRaises(WorkflowError):self.exchange(query)
        self.assertEqual(self.operations.get(self.project['id'],self.saved['authorization_id'],kind='authorization')['status'],'awaiting_callback')
        self.revoke()
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER'):self.exchange()
        self.assertEqual(self.calls,[])
    def test_valid_denial_is_consumed_without_cost_or_private_error_description(self):
        self.start();flow=self.vault.authorization(self.saved['snapshot']['authorization_receipt']);done=self.exchange(urlencode({'state':flow.state,'error':'access_denied','error_description':SECRET}))
        self.assertEqual(done['status'],'failed');self.assertEqual(done['failure_code'],'GOOGLE_OAUTH_CONSENT_DENIED');self.assertIsNone(done['cost_operation_id']);self.assertEqual(self.calls,[])
        self.assertNotIn(SECRET,json.dumps(done));self.assertEqual(self.operations.costs.summary(self.project['id'])['records'],[])
        with self.assertRaisesRegex(WorkflowError,'NOT_PENDING'):self.exchange()
    def test_concurrent_callback_and_restart_cannot_send_consumed_code_twice(self):
        self.start();query=self.query()
        def run(_):
            try:return self.exchange(query)['status']
            except WorkflowError as e:return e.code
        with ThreadPoolExecutor(2) as pool:values=list(pool.map(run,range(2)))
        self.assertEqual(values.count('succeeded'),1);self.assertIn('NATIVE_GOOGLE_OAUTH_AUTHORIZATION_NOT_PENDING',values);self.assertEqual(len(self.calls),1)
        self.operations=self.service();self.operations.recover()
        with self.assertRaisesRegex(WorkflowError,'NOT_PENDING'):self.exchange(query)
        self.assertEqual(len(self.calls),1)
    def test_timeout_rate_limit_invalid_grant_and_scope_error_never_retry(self):
        for index,(mode,status) in enumerate((('timeout','outcome_unknown'),('rate-limit','outcome_unknown'),('invalid-grant','failed'),('foreign-scope','outcome_unknown'))):
            self.start(request_key='explicit-unknown-google-start-key-'+str(index));self.mode=mode;value=self.exchange();self.assertEqual(value['status'],status);self.assertIsNone(value['result']);self.operations.recover()
            with self.assertRaisesRegex(WorkflowError,'NOT_PENDING'):self.exchange()
            self.assertNotIn(SECRET,json.dumps(value));self.mode=None
        self.assertEqual(len(self.calls),4);self.assertEqual(len(list(self.private.glob('*.dpapi'))),6)
    def test_current_owner_source_and_deadline_after_response_refuse_new_grant(self):
        for mode in ('edit','expired'):
            self.start(request_key='explicit-late-google-start-key-'+mode);self.mode=mode;value=self.exchange();self.assertEqual(value['status'],'review_required');self.assertIsNone(value['result'])
            self.project=self.store.get(self.project['id']);self.mode=None
        self.start(request_key='explicit-late-google-owner-key');self.mode='revoke';value=self.exchange();self.assertEqual(value['status'],'review_required');self.assertEqual(value['failure_code'],'NATIVE_GOOGLE_OAUTH_CURRENT_OWNER_REQUIRED');self.assertIsNone(value['result'])
        self.assertEqual(len(list(self.private.glob('*.dpapi'))),5);self.assertTrue(all(x['status']=='response_received' for x in self.operations.costs.summary(self.project['id'])['records']))
    def test_refresh_explicit_new_generation_retains_old_bytes_unknown_expiry_and_exact_key(self):
        old=self.successful();receipt=old['result']['grant_receipt'];oldsha=file_sha(self.vault.path(receipt['reference']));request=self.refresh_payload();self.mode='rotate';new=self.refresh(request)
        self.assertEqual(new['status'],'succeeded');self.assertNotEqual(new['result']['grant_receipt']['reference'],receipt['reference']);self.assertIsNone(new['result']['grant_proof']['refresh_expires_at'])
        self.assertEqual(file_sha(self.vault.path(receipt['reference'])),oldsha);self.assertEqual(self.operations.get(self.project['id'],old['operation_id']),old)
        replay=self.refresh(request);self.assertEqual(replay,new);self.assertEqual(len(self.calls),2)
        with self.assertRaisesRegex(WorkflowError,'SOURCE_ALREADY_CONSUMED'):self.refresh(request.model_copy(update={'request_key':'explicit-google-another-refresh-key'}))
        self.assertEqual(len(self.calls),2);self.assertFalse(new['result']['credential_selected'])
    def test_disabled_refresh_replay_is_history_but_new_refresh_does_not_decrypt(self):
        self.successful();self.operations=self.service()
        with patch.object(self.vault,'client',side_effect=AssertionError('NO DISABLED REFRESH DECRYPT')):
            with self.assertRaisesRegex(WorkflowError,'DISABLED'):self.refresh()
            self.assertEqual(self.operations.get(self.project['id'],self.done['operation_id']),self.done)
        self.assertEqual(len(self.calls),1)
    def test_current_owner_revoke_before_refresh_or_exact_replay_never_renews_consent(self):
        self.successful();payload=self.refresh_payload();new=self.refresh(payload);self.revoke()
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER'):self.refresh(payload)
        self.assertEqual(self.operations.get(self.project['id'],new['operation_id']),new);self.assertEqual(len(self.calls),2)
    def test_unchecked_ack_numeric_revision_extra_fields_and_foreign_receipt_refuse(self):
        payload=self.start_payload()
        for change in ({'acknowledged_credential_operation':1},{'acknowledged_protocol_mock':1},{'revision':True},{'redirect_uri':'http://localhost:18047/'},{'extra':True}):
            with self.assertRaises((ValidationError,GoogleOAuthError)):Start.model_validate({**payload.model_dump(mode='json'),**change})
            with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.operations.start(self.project['id'],payload.model_copy(update=change),principal=self.principal)
        self.assertEqual(self.calls,[])
    def test_mutated_slot_wire_workspace_and_private_cipher_refuse_before_wire(self):
        self.start();slot=self.operations.slots[self.start_request.slot_id];original=slot.client_id;object.__setattr__(slot,'client_id','123-other.apps.googleusercontent.com')
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER'):self.exchange()
        object.__setattr__(slot,'client_id',original);path=self.vault.path(slot.client.reference);path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(WorkflowError,'PRIVATE_UNAVAILABLE'):self.exchange()
        self.assertEqual(self.calls,[])
    def test_recovery_during_wire_preserves_unknown_and_never_selects_late_grant(self):
        self.start();self.mode='recover';value=self.exchange();self.assertEqual(value['status'],'outcome_unknown');self.assertIsNone(value['result']);self.assertEqual(len(self.calls),1)
        self.assertEqual(len(list(self.private.glob('*.dpapi'))),3);self.assertEqual(self.operations.costs.summary(self.project['id'])['records'][0]['status'],'outcome_unknown')
    def test_restart_between_cost_intent_and_link_recovers_pending_cost_without_private_read(self):
        self.start()
        with patch.object(self.operations,'execute',side_effect=SystemExit('EXPLICIT CLAIM CRASH')):
            with self.assertRaises(SystemExit):self.exchange()
        auth=self.operations.get(self.project['id'],self.saved['authorization_id'],kind='authorization');identity=auth['operation_id'];value=self.operations.get(self.project['id'],identity)
        cost=self.operations.costs.begin(project_id=self.project['id'],provider='official-google-oauth',model=None,operation='token:'+identity,request_sha256=digest({'operation':'authorization_code','snapshot_sha256':value['snapshot_sha256']}),paid=False,external_call=False)
        self.operations=self.service(slots={})
        with patch.object(self.vault,'client',side_effect=AssertionError('NO RECOVERY PRIVATE READ')):self.operations.recover()
        self.assertEqual(self.operations.get(self.project['id'],identity)['status'],'outcome_unknown');self.assertFalse(self.operations.costs.pending(cost));self.assertEqual(self.calls,[])
        self.assertEqual(database_status(self.store.db)['active_operations'],0)
    def test_history_reads_after_private_unmounted_expiry_and_source_edit_no_owner_or_provider(self):
        value=self.successful();self.clock[0]+=timedelta(hours=2);self.store.save(self.project['id'],self.project['revision'],prompt='Explicit historical later edit')
        vault=NativeGoogleOAuthVault(self.folder/'unmounted',self.root,self.workspace);self.operations=self.service(slots={},vault=vault)
        with patch.object(vault,'client',side_effect=AssertionError('NO HISTORY DECRYPT')):
            self.assertEqual(self.operations.get(self.project['id'],value['operation_id']),value);self.operations.recover()
        self.assertEqual(len(self.calls),1);self.assertFalse(vault.directory.exists())
    def test_database_public_exports_and_cost_journal_contain_no_private_values(self):
        self.successful();self.refresh();values=[]
        with self.store.transaction() as con:
            for table in TABLES+('native_cost_operations',):values.extend(dict(r) for r in con.execute('SELECT * FROM '+table))
        public=json.dumps(values)
        for private in (TOKEN,REFRESH,SECRET,CODE,self.raw,self.query()):self.assertNotIn(private,public)
        counts=database_status(self.store.db)['counts'];self.assertEqual(counts[TABLES[0]],1);self.assertEqual(counts[TABLES[1]],2);self.assertEqual(counts[TABLES[2]],5)
    def test_bounded_scoped_history_pagination_and_foreign_cursor_reject_without_decrypt(self):
        self.successful();self.refresh()
        with patch.object(self.vault,'client',side_effect=AssertionError('NO PAGE DECRYPT')):
            first=self.operations.page(self.project['id'],limit=1);self.assertTrue(first['truncated']);second=self.operations.page(self.project['id'],limit=1,cursor=first['next_cursor']);self.assertFalse(second['truncated'])
            self.assertNotEqual(first['items'][0]['operation_id'],second['items'][0]['operation_id'])
            other=self.store.create('Other explicit fixture','','media')
            with self.assertRaisesRegex(WorkflowError,'PAGE_INVALID'):self.operations.page(other['id'],cursor=first['next_cursor'])
            for change in ({'limit':True},{'limit':101},{'kind':'private'},{'cursor':'../outside'},{'cursor':'a'*2049}):
                with self.assertRaisesRegex(WorkflowError,'PAGE_INVALID'):self.operations.page(self.project['id'],**change)
            self.assertEqual(len(self.operations.page(self.project['id'],kind='authorization')['items']),1)
    def test_private_authorization_window_mismatch_refuses_before_claim_or_wire(self):
        from dataclasses import replace
        self.start();flow=self.vault.authorization(self.saved['snapshot']['authorization_receipt'])
        with patch.object(self.vault,'authorization',return_value=replace(flow,expires_at=flow.expires_at+timedelta(seconds=1))):
            with self.assertRaisesRegex(WorkflowError,'AUTHORIZATION_BINDING_CHANGED'):self.exchange()
        self.assertEqual(self.calls,[]);self.assertEqual(self.operations.page(self.project['id'])['items'],[])
    def test_owner_window_expiry_and_recovery_expire_pending_without_secrets(self):
        self.start();self.clock[0]+=timedelta(seconds=601)
        with patch.object(self.vault,'client',side_effect=AssertionError('NO EXPIRED INTENT DECRYPT')):
            with self.assertRaisesRegex(WorkflowError,'CONSENT_CHANGED'):self.exchange('state=unknown&code=EXPLICIT')
            self.operations.recover();self.assertEqual(self.operations.get(self.project['id'],self.saved['authorization_id'],kind='authorization')['status'],'expired')
        self.clock[0]=datetime.now(timezone.utc);record=self.verifier.registry.tokens[self.principal.token_id];object.__setattr__(record,'expires_at',self.clock[0]+timedelta(seconds=59))
        self.principal=self.verifier.verify('Bearer '+self.raw)
        with self.assertRaisesRegex(WorkflowError,'OWNER_WINDOW'):self.start(request_key='explicit-google-too-short-owner-key')
        self.assertEqual(self.calls,[])
    def test_mock_ack_raw_true_real_marker_false_and_frozen_operator_gate(self):
        payload=self.start_payload().model_copy(update={'acknowledged_protocol_mock':False})
        with self.assertRaisesRegex(WorkflowError,'SLOT_BINDING'):self.operations.start(self.project['id'],payload,principal=self.principal)
        self.operations.enabled=False
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.operations.states()
        self.operations.enabled=True;self.wire.network_enabled=True
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.operations.states()
        self.assertEqual(self.calls,[])
    def test_concurrent_explicit_refresh_consumes_original_generation_once(self):
        self.successful();request=self.refresh_payload()
        def run(index):
            try:return self.refresh(request.model_copy(update={'request_key':'explicit-google-concurrent-refresh-'+str(index)}))['status']
            except WorkflowError as e:return e.code
        with ThreadPoolExecutor(2) as pool:values=list(pool.map(run,range(2)))
        self.assertEqual(values.count('succeeded'),1);self.assertIn('NATIVE_GOOGLE_OAUTH_SOURCE_ALREADY_CONSUMED',values);self.assertEqual(len(self.calls),2)
    def test_private_client_changed_after_response_preserves_cost_and_no_selected_grant(self):
        self.start();original=self.wire.transport.handler
        def change(request):
            result=original(request);path=self.vault.path(self.slots[self.start_request.slot_id].client.reference);path.write_bytes(path.read_bytes()+b'changed');return result
        self.wire.transport.handler=change;value=self.exchange();self.assertEqual(value['status'],'review_required');self.assertIsNone(value['result']);self.assertEqual(value['failure_code'],'NATIVE_GOOGLE_OAUTH_PRIVATE_UNAVAILABLE')
        self.assertEqual(self.operations.costs.summary(self.project['id'])['records'][0]['status'],'response_received');self.assertEqual(len(self.calls),1)
    def test_historical_source_or_cost_receipt_corruption_refuses_without_provider(self):
        value=self.successful();operation=value['operation_id'];auth=self.saved['authorization_id']
        with self.store.transaction() as con:con.execute("UPDATE native_google_oauth_authorizations SET operation_id='ngop_ffffffffffffffffffffffffffffffff' WHERE authorization_id=?",(auth,))
        with self.assertRaisesRegex(WorkflowError,'SOURCE_EVIDENCE_CHANGED'):self.operations.get(self.project['id'],operation)
        with self.store.transaction() as con:
            con.execute('UPDATE native_google_oauth_authorizations SET operation_id=? WHERE authorization_id=?',(operation,auth))
            con.execute("UPDATE native_cost_operations SET operation='token:foreign' WHERE id=?",(value['cost_operation_id'],))
        with self.assertRaisesRegex(WorkflowError,'SOURCE_EVIDENCE_CHANGED'):self.operations.get(self.project['id'],operation)
        self.assertEqual(len(self.calls),1)
    def test_rehashed_result_cannot_erase_null_expiry_or_coerce_disabled_markers(self):
        value=self.successful();original=copy.deepcopy(value['result'])
        for change in ({'credential_selected':0},{'grant_proof':{**original['grant_proof'],'mock':1}},{'grant_proof':{**original['grant_proof'],'refresh_expires_at':'2026-10-09T00:00:00'}},{'extra':True}):
            result={**original,**change}
            with self.store.transaction() as con:con.execute('UPDATE native_google_oauth_operations SET result_sha256=?,result_json=? WHERE operation_id=?',(digest(result),json.dumps(result),value['operation_id']))
            with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.operations.get(self.project['id'],value['operation_id'])
        self.assertEqual(len(self.calls),1)
    def test_internal_callback_request_cannot_substitute_pkce_after_original_claim(self):
        from dataclasses import replace
        self.start();original=self.operations.execute
        async def changed(project,identity,slot,c,request,**values):
            fields={k:v[0] for k,v in parse_qs(request.body.decode()).items()};fields['code_verifier']='x'*43
            return await original(project,identity,slot,c,replace(request,body=urlencode(fields).encode()),**values)
        with patch.object(self.operations,'execute',side_effect=changed):value=self.exchange()
        self.assertEqual(value['status'],'failed');self.assertEqual(value['failure_code'],'NATIVE_GOOGLE_OAUTH_PRIVATE_REQUEST_CHANGED');self.assertEqual(self.calls,[])
        self.assertEqual(self.operations.costs.summary(self.project['id'])['records'][0]['status'],'rejected')
    def test_internal_refresh_request_cannot_substitute_another_private_token(self):
        from dataclasses import replace
        self.successful();original=self.operations.execute
        async def changed(project,identity,slot,c,request,**values):
            fields={k:v[0] for k,v in parse_qs(request.body.decode()).items()};fields['refresh_token']='EXPLICIT_FOREIGN_REFRESH_TOKEN_123456789'
            return await original(project,identity,slot,c,replace(request,body=urlencode(fields).encode()),**values)
        with patch.object(self.operations,'execute',side_effect=changed):value=self.refresh()
        self.assertEqual(value['status'],'failed');self.assertEqual(value['failure_code'],'NATIVE_GOOGLE_OAUTH_PRIVATE_REQUEST_CHANGED');self.assertEqual(len(self.calls),1)
    def test_identity_provider_object_replacement_is_configuration_drift(self):
        self.start();self.review.identity_provider=lambda:self.verifier
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.operations.states()
        self.assertEqual(self.calls,[])
