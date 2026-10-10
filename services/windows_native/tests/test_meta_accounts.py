"""Actual local DPAPI/SQLite account custody with explicit provider/Owner mocks."""
import asyncio, copy, json, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from app.meta_publishing_credentials import REQUIRED
from app.publishing_models import PublishingTargetBinding
from app.publishing_wire import OfficialRequest
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.official_accounts import NativeOfficialAccounts, Verify
from services.windows_native import meta_connection as meta


class MetaAccountsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.root=self.folder/'state';self.root.mkdir()
        self.workspace='wsp_meta_fixture';(self.root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}),encoding='utf8')
        self.store=Store(self.root);self.project=self.store.create('Meta account fixture','No media production or publish authority')
        self.instant=datetime.now(timezone.utc);self.calls=[];self.token='META-EXPLICIT-NATIVE-PROTOCOL-MOCK-ONLY-1234567890'
        self.profile=self.profile_for('instagram_reels');self.path=self.folder/'secrets'/'ig-page.dpapi'
        self.receipt=meta.save_token(self.path,self.root,self.token_value(self.profile))
        self.binding=meta.Binding(account_ref='npac_'+'a'*32,profile=self.profile,credential_alias='meta-page-fixture',token_file=str(self.path),read_enabled=True)
        self.transport=httpx.MockTransport(self.response);self.factory=meta.NativeMetaAccountFactory(self.binding,self.root,self.workspace,owner_read_enabled=True,transport=self.transport)
        self.service=NativeOfficialAccounts(self.store,workspace_id=self.workspace,factories={self.binding.account_ref:self.factory},clock=lambda:self.instant)

    def tearDown(self):self.temp.cleanup()

    def profile_for(self,platform):
        target=PublishingTargetBinding(workspace_id=self.workspace,profile_id='ppf_meta_'+platform,profile_version=1,platform=platform,
            provider_key={'facebook':'facebook-graph-api-publishing','instagram_reels':'instagram-graph-api-publishing'}[platform],
            target_account_id='12345' if platform=='facebook' else '23456',credential_binding_sha256='a'*64)
        return meta.Profile(target=target,page_id='12345',api_version='v24.0')

    def token_value(self,profile):
        return {'profile':profile.model_dump(mode='json'),'credential_alias':'meta-page-fixture','expires_at':(self.instant+timedelta(hours=1)).isoformat(),
            'scopes':sorted(REQUIRED[profile.target.platform]),'token':self.token}

    def response(self,request):
        self.calls.append((request.method,request.url.path))
        return httpx.Response(200,json={'id':'12345','instagram_business_account':{'id':'23456'}} if request.url.path.endswith('/me') else {'id':'23456'})

    def body(self,key='explicit-meta-account-fixture-key'):
        return Verify(revision=self.project['revision'],expected_configuration_sha256=self.factory.sha256,acknowledged_read_only=True,request_key=key)

    def run_check(self,key='explicit-meta-account-fixture-key'):
        value,_=self.service.create(self.project['id'],self.binding.account_ref,self.body(key),actor='EXPLICIT OWNER FIXTURE')
        return value,self.service.process(project=self.project['id'],identity=value['check_id'],fingerprint=value['request_fingerprint'])

    def test_factory_startup_never_decrypts_or_allocates_network_and_private_custody_is_domain_bound(self):
        with patch.object(meta,'load_token',side_effect=AssertionError('No startup decrypt')):
            factory=meta.NativeMetaAccountFactory(self.binding,self.root,self.workspace,transport=self.transport)
            self.assertEqual(factory.public()['status'],'NOT_CONFIGURED');self.assertFalse(factory.client.wire.network_enabled)
        credential=self.factory.credential(now=self.instant);self.assertEqual(credential.token,self.token)
        self.assertNotIn(self.token,repr(credential));self.assertNotIn(self.token,json.dumps(self.receipt));self.assertNotIn(self.token.encode(),self.path.read_bytes())
        with self.assertRaisesRegex(WorkflowError,'ALREADY_SAVED'):meta.save_token(self.path,self.root,self.token_value(self.profile))
        with self.assertRaisesRegex(WorkflowError,'UNAVAILABLE'):meta.load_token(self.path,self.root,self.profile,'wrong-alias')

    def test_page_and_linked_instagram_read_is_exact_cost_bound_idempotent_and_never_publishes(self):
        before=self.store.get(self.project['id']);queued,result=self.run_check();self.assertEqual(result['status'],'succeeded');proof=result['result']['meta']
        self.assertEqual(self.calls,[('GET','/v24.0/me'),('GET','/v24.0/23456')]);self.assertTrue(proof['token_page_match']);self.assertTrue(proof['linked_instagram_match'])
        self.assertFalse(proof['provider_permissions_verified']);self.assertFalse(proof['app_eligibility_verified']);self.assertFalse(proof['publishing_enabled'])
        costs=self.service.costs.summary(self.project['id'])['records'];self.assertEqual(len(costs),2)
        self.assertTrue(all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs))
        self.assertEqual(self.store.get(self.project['id']),before);self.assertNotIn(self.token,json.dumps(result));self.assertNotIn(str(self.path),json.dumps(result))
        replay,exact=self.service.create(self.project['id'],self.binding.account_ref,self.body(),actor='OTHER FIXTURE');self.assertTrue(exact);self.assertEqual(replay,result)
        self.assertIsNone(self.service.process());self.assertEqual(len(self.calls),2)

    def test_facebook_page_checks_only_exact_token_identity_with_one_cost(self):
        profile=self.profile_for('facebook');path=self.folder/'secrets'/'facebook.dpapi';meta.save_token(path,self.root,self.token_value(profile))
        binding=self.binding.model_copy(update={'profile':profile,'token_file':str(path),'account_ref':'npac_'+'b'*32})
        factory=meta.NativeMetaAccountFactory(binding,self.root,self.workspace,owner_read_enabled=True,transport=self.transport)
        service=NativeOfficialAccounts(self.store,workspace_id=self.workspace,factories={binding.account_ref:factory},clock=lambda:self.instant)
        value,_=service.create(self.project['id'],binding.account_ref,self.body().model_copy(update={'expected_configuration_sha256':factory.sha256}),actor='EXPLICIT OWNER FIXTURE')
        result=service.process();self.assertEqual(result['status'],'succeeded');self.assertIsNone(result['result']['meta']['instagram_account_id'])
        self.assertIsNone(result['result']['meta']['linked_instagram_match']);self.assertEqual(self.calls,[('GET','/v24.0/me')])

    def test_missing_or_foreign_page_link_stops_before_second_wire(self):
        for n,response in enumerate(({'id':'99999'},{'id':'12345'},{'id':'12345','instagram_business_account':{'id':'99999'}})):
            self.transport.handler=lambda request: (self.calls.append((request.method,request.url.path)) or httpx.Response(200,json=response))
            _,result=self.run_check('explicit-meta-mismatch-'+str(n));self.assertEqual(result['status'],'failed');self.assertIsNone(result['result'])
        self.assertEqual(len(self.calls),3);self.assertTrue(all(path.endswith('/me') for _,path in self.calls))

    def test_profile_cipher_registry_and_read_window_changes_block_before_wire(self):
        queued,_=self.service.create(self.project['id'],self.binding.account_ref,self.body(),actor='EXPLICIT')
        self.instant+=timedelta(seconds=901);result=self.service.process();self.assertEqual(result['status'],'failed');self.assertEqual(self.calls,[])
        self.instant-=timedelta(seconds=901);queued,_=self.service.create(self.project['id'],self.binding.account_ref,self.body('explicit-meta-changed-cipher'),actor='EXPLICIT')
        self.path.write_bytes(self.path.read_bytes()+b'changed');result=self.service.process();self.assertEqual(result['status'],'failed');self.assertEqual(self.calls,[])

    def test_project_or_custody_change_between_requests_does_not_complete_linked_proof(self):
        def changed(request):
            response=self.response(request);self.store.save(self.project['id'],self.project['revision'],prompt='Edit during readonly proof');return response
        self.transport.handler=changed;_,result=self.run_check();self.assertEqual(result['status'],'failed');self.assertEqual(len(self.calls),1)
        self.assertIsNone(result['result']);self.assertEqual(len(self.service.costs.summary(self.project['id'])['records']),1)

    def test_network_unknown_or_restart_never_auto_replays_and_cost_receipt_remains_honest(self):
        def unknown(request):self.calls.append((request.method,request.url.path));raise httpx.ReadTimeout('explicit mock uncertainty')
        self.transport.handler=unknown;queued,result=self.run_check();self.assertEqual(result['status'],'failed');self.assertIsNone(self.service.process());self.assertEqual(len(self.calls),1)
        cost=self.service.costs.summary(self.project['id'])['records'][0];self.assertEqual(cost['status'],'outcome_unknown');self.assertIsNone(cost['actual_cost'])
        other,_=self.service.create(self.project['id'],self.binding.account_ref,self.body('explicit-meta-interrupted-key'),actor='EXPLICIT')
        with self.store.transaction() as con:con.execute("UPDATE native_official_account_checks SET status='running',claim_id='fixture-claim' WHERE check_id=?",(other['check_id'],))
        self.service.recover();self.assertEqual(self.service.get(self.project['id'],other['check_id'])['status'],'outcome_unknown');self.assertIsNone(self.service.process());self.assertEqual(len(self.calls),1)

    def test_rehashed_permission_promotion_or_borrowed_cost_proof_is_rejected_without_secret(self):
        queued,result=self.run_check();proof=copy.deepcopy(result['result']);proof['meta']['provider_permissions_verified']=True
        with self.store.transaction() as con:con.execute('UPDATE native_official_account_checks SET result_json=?,result_sha256=? WHERE check_id=?',(json.dumps(proof),digest(proof),queued['check_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.service.get(self.project['id'],queued['check_id'])
        proof=copy.deepcopy(result['result']);proof['meta']['observations'][0]['request_sha256']='f'*64
        with self.store.transaction() as con:con.execute('UPDATE native_official_account_checks SET result_json=?,result_sha256=? WHERE check_id=?',(json.dumps(proof),digest(proof),queued['check_id']))
        with self.assertRaisesRegex(WorkflowError,'COST_EVIDENCE_CHANGED'):self.service.get(self.project['id'],queued['check_id'])

    def test_disabled_keyless_history_preserves_both_observations_and_no_factory_load(self):
        queued,result=self.run_check();self.path.unlink();self.assertEqual(self.factory.public()['status'],'NOT_CONFIGURED')
        reopened=NativeOfficialAccounts(Store(self.root),workspace_id=self.workspace);reopened.recover()
        self.assertEqual(reopened.get(self.project['id'],queued['check_id']),result);self.assertEqual(reopened.page(self.project['id'])['items'],[result])
        self.assertIsNone(reopened.process());self.assertEqual(len(self.calls),2)

    def test_protected_registry_pins_workspace_hash_and_rejects_duplicates_and_private_source_paths(self):
        path=self.folder/'secrets'/'registry.json';raw={'schema_version':'native-meta-account-registry-v1','version':1,'workspace_id':self.workspace,'accounts':[self.binding.model_dump(mode='json')]}
        path.write_text(json.dumps(raw),encoding='utf8')
        with patch.object(meta,'load_token',side_effect=AssertionError('No registry decrypt')):factories=meta.load(path,self.root,self.workspace)
        factory=factories[self.binding.account_ref];self.assertEqual(factory.public()['status'],'NOT_CONFIGURED');path.write_text(json.dumps({**raw,'version':2}),encoding='utf8')
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):factory.public()
        with self.assertRaises(ValueError):meta.Registry.model_validate({**raw,'accounts':[raw['accounts'][0],raw['accounts'][0]]})
        with self.assertRaisesRegex(WorkflowError,'OUTSIDE_SOURCE_STATE'):meta.save_token(self.root/'forbidden.dpapi',self.root,self.token_value(self.profile))
        with self.assertRaises(WorkflowError):asyncio.run(self.factory.client.request(OfficialRequest('POST','https://graph.facebook.com/v24.0/23456/media')))
