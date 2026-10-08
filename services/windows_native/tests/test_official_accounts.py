"""Durable owned account-read/wire fixtures; no real credentials/publication."""
import copy,json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.official_account_registry import Account,AccountFactory
from services.windows_native.official_accounts import NativeOfficialAccounts,Verify
from app.publishing_models import PublishingTargetBinding
from app.analytics_official import AnalyticsOAuthCredential,YT_READ,YT_ANALYTICS

class OfficialAccountsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.root=self.folder/'state';self.root.mkdir();self.store=Store(self.root)
        (self.root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':'wsp_fixture'}),encoding='utf-8')
        self.project=self.store.create('Explicit account read fixture','No inference');self.calls=[]
        self.target=PublishingTargetBinding(workspace_id='wsp_fixture',profile_id='ppf_explicit_fixture',profile_version=1,platform='youtube',
            provider_key='youtube-data-api-publishing',target_account_id='UC_EXPLICIT_FIXTURE',credential_binding_sha256='a'*64)
        self.account=Account(account_ref='npac_'+'a'*32,target=self.target,credential_alias='youtube-fixture-read',token_file=str(self.folder/'secrets'/'test.dpapi'),read_enabled=True)
        self.credential=AnalyticsOAuthCredential(self.target,datetime.now(timezone.utc)+timedelta(hours=1),frozenset({YT_READ,YT_ANALYTICS}),'EXPLICIT-TOKEN-FIXTURE-ONLY-1234567890')
        self.transport=httpx.MockTransport(self.response)
        self.factory=AccountFactory(self.account,self.root,'wsp_fixture',owner_read_enabled=True,transport=self.transport,resolver=lambda _:self.credential)
        self.service=NativeOfficialAccounts(self.store,workspace_id='wsp_fixture',factories={self.account.account_ref:self.factory})
    def tearDown(self):self.temp.cleanup()
    def response(self,request):
        self.calls.append((request.method,str(request.url)));return httpx.Response(200,json={'items':[{'id':self.target.target_account_id}]})
    def body(self,**kwargs):
        return Verify(revision=self.project['revision'],expected_configuration_sha256=self.factory.sha256,acknowledged_read_only=True,
            request_key='explicit-account-read-fixture-key',**kwargs)
    def create(self,body=None):return self.service.create(self.project['id'],self.account.account_ref,body or self.body(),actor='EXPLICIT OWNER FIXTURE')[0]
    def test_scoped_account_read_records_one_wire_call_and_cost_without_project_jobs_or_publish_authority(self):
        before=self.store.get(self.project['id']);check=self.create();self.assertEqual(self.calls,[])
        result=self.service.process(project=self.project['id'],identity=check['check_id'],fingerprint=check['request_fingerprint']);self.assertEqual(result['status'],'succeeded')
        proof=result['result'];self.assertTrue(proof['account_match']);self.assertTrue(proof['mock']);self.assertFalse(proof['external_call']);self.assertFalse(proof['publishing_enabled'])
        self.assertEqual(len(self.calls),1);self.assertEqual(self.calls[0][0],'GET');self.assertEqual(self.store.get(self.project['id']),before)
        self.assertNotIn(self.credential.token,json.dumps(result));self.assertNotIn(str(self.folder/'secrets'),json.dumps(result))
        costs=self.service.costs.summary(self.project['id']);self.assertEqual(len(costs['records']),1);self.assertIsNone(costs['records'][0]['actual_cost']);self.assertFalse(costs['records'][0]['external_call'])
        self.assertEqual(self.service.process(project=self.project['id'],identity=check['check_id'],fingerprint=check['request_fingerprint']),result);self.assertEqual(len(self.calls),1)
        self.assertFalse(self.service.states()['publishing_enabled'])
    def test_exact_request_replay_survives_project_edit_and_conflict_does_not_dispatch(self):
        body=self.body();check=self.create(body);self.store.save(self.project['id'],self.project['revision'],prompt='Explicit later edit')
        replay,exact=self.service.create(self.project['id'],self.account.account_ref,body,actor='OTHER FIXTURE');self.assertTrue(exact);self.assertEqual(replay,check)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):
            self.service.create(self.project['id'],self.account.account_ref,body.model_copy(update={'revision':body.revision+1}),actor='EXPLICIT')
        result=self.service.process();self.assertEqual(result['status'],'failed');self.assertEqual(result['failure_code'],'NATIVE_OFFICIAL_ACCOUNT_PROJECT_CHANGED');self.assertEqual(self.calls,[])
    def test_changed_configuration_after_queue_or_during_wire_prevents_success(self):
        check=self.create();self.factory.read_enabled=False;result=self.service.process();self.assertEqual(result['status'],'failed');self.assertEqual(self.calls,[])
        self.factory.read_enabled=True;current=self.store.get(self.project['id']);self.project=current
        body=self.body().model_copy(update={'request_key':'explicit-second-read-fixture-key'});check=self.create(body)
        def changed(request):
            self.calls.append((request.method,str(request.url)));self.store.save(self.project['id'],self.project['revision'],prompt='Explicit edit during provider response')
            return httpx.Response(200,json={'items':[{'id':self.target.target_account_id}]})
        self.transport.handler=changed
        result=self.service.process();self.assertEqual(result['status'],'failed');self.assertEqual(result['failure_code'],'NATIVE_OFFICIAL_ACCOUNT_PROJECT_CHANGED');self.assertEqual(len(self.calls),1)
    def test_wrong_account_foreign_scope_or_body_cannot_gain_account_authority(self):
        self.transport.handler=lambda _:httpx.Response(200,json={'items':[{'id':'FOREIGN'}]})
        check=self.create();result=self.service.process();self.assertEqual(result['status'],'failed');self.assertEqual(result['failure_code'],'ANALYTICS_ACCOUNT_NOT_CONFIRMED');self.assertIsNone(result['result'])
        other=self.store.create('Foreign explicit project','No providers')
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.service.get(other['id'],check['check_id'])
        with self.assertRaises(WorkflowError):NativeOfficialAccounts(self.store,workspace_id='wsp_foreign')
        for change in [{'revision':True},{'acknowledged_read_only':1},{'token':'never accepted'},{'endpoint':'https://untrusted.invalid'}]:
            with self.assertRaises(ValueError):Verify.model_validate({**self.body().model_dump(),**change})
    def test_disabled_or_missing_secret_mount_records_not_configured_without_cost_or_wire(self):
        factory=AccountFactory(self.account,self.root,'wsp_fixture');service=NativeOfficialAccounts(self.store,workspace_id='wsp_fixture',factories={self.account.account_ref:factory})
        body=self.body().model_copy(update={'expected_configuration_sha256':factory.sha256});check,_=service.create(self.project['id'],self.account.account_ref,body,actor='EXPLICIT')
        self.assertEqual(check['status'],'not_configured');self.assertIsNone(service.process());self.assertEqual(self.calls,[]);self.assertEqual(service.costs.summary(self.project['id'])['records'],[])
    def test_recovery_never_resends_uncertain_read_and_history_rejects_rehashed_safety_claim(self):
        check=self.create()
        with self.store.transaction() as con:con.execute("UPDATE native_official_account_checks SET status='running',claim_id='EXPLICIT-CLAIM',attempts=1 WHERE check_id=?",(check['check_id'],))
        reopened=NativeOfficialAccounts(Store(self.root),workspace_id='wsp_fixture',factories={self.account.account_ref:self.factory});reopened.recover()
        self.assertEqual(reopened.get(self.project['id'],check['check_id'])['status'],'outcome_unknown');self.assertIsNone(reopened.process());self.assertEqual(self.calls,[])
        check=self.create(self.body().model_copy(update={'request_key':'explicit-confirmed-read-fixture-key'}));result=self.service.process();proof=copy.deepcopy(result['result']);proof['publishing_enabled']=0
        with self.store.transaction() as con:con.execute('UPDATE native_official_account_checks SET result_json=?,result_sha256=? WHERE check_id=?',(json.dumps(proof),digest(proof),check['check_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.service.get(self.project['id'],check['check_id'])
    def test_rehashed_mock_result_cannot_be_relabelled_as_external_account_evidence(self):
        check=self.create();result=self.service.process();proof=copy.deepcopy(result['result']);proof['mock']=False;proof['external_call']=True
        with self.store.transaction() as con:con.execute('UPDATE native_official_account_checks SET result_json=?,result_sha256=? WHERE check_id=?',(json.dumps(proof),digest(proof),check['check_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.service.get(self.project['id'],check['check_id'])
    def test_fresh_owner_checks_have_distinct_cost_intents_while_exact_replay_never_resends(self):
        first=self.create();first=self.service.process();body=self.body().model_copy(update={'request_key':'explicit-fresh-owner-account-read-key'})
        second=self.create(body);second=self.service.process()
        self.assertEqual(first['status'],second['status']);self.assertEqual(second['status'],'succeeded');self.assertEqual(len(self.calls),2)
        self.assertNotEqual(first['result']['cost_operation_id'],second['result']['cost_operation_id']);costs=self.service.costs.summary(self.project['id'])['records']
        self.assertEqual(len(costs),2);self.assertEqual({r['operation'] for r in costs},{'account_lookup.'+v['check_id'] for v in (first,second)})
        self.assertTrue(all(r['actual_cost'] is None and not r['external_call'] and not r['paid'] for r in costs))
        replay,exact=self.service.create(self.project['id'],self.account.account_ref,body,actor='EXPLICIT SECOND OWNER FIXTURE');self.assertTrue(exact);self.assertEqual(replay,second)
        self.assertIsNone(self.service.process());self.assertEqual(len(self.calls),2)
