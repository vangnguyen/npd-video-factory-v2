"""Local DPAPI/SQLite with explicit Owner/platform/provider and nonplayable media mocks."""
import copy, json, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from app.meta_publishing_credentials import REQUIRED
from app.publishing_models import PublishingTargetBinding
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.publication_models import NativePublicationCreate, NativePublishApproval
from services.windows_native.official_accounts import NativeOfficialAccounts, Verify
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_models import MetaCreate, Gates, Approve, Renew, Action, publication_request
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native import meta_connection as account, meta_distribution as meta
from services.windows_native.tests.test_publications import render_fixture, CAPABILITIES
from services.windows_native.tests.test_human_identity import fixture as human_fixture


class MetaAdmissionTests(unittest.TestCase):
    PLATFORM='instagram_reels'

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.root=self.folder/'state';self.root.mkdir()
        self.workspace='wsp_meta_admission_fixture';self.clock=[datetime.now(timezone.utc)];self.calls=[]
        (self.root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}),encoding='utf8')
        self.store=Store(self.root);self.project,self.job=render_fixture(self.store)
        raw,registry=human_fixture('owner',workspace=self.workspace);self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400)
        self.principal=self.verifier.verify('Bearer '+raw)
        caps=json.loads(CAPABILITIES.read_bytes());caps['platforms'][self.PLATFORM]['verification_state']='owner_verified_for_live'
        caps['notice']='EXPLICIT OWNER/PLATFORM/NONPLAYABLE MEDIA FIXTURES; NOT REAL ACCEPTANCE';self.caps=self.folder/'fixture-capabilities.json'
        self.caps.write_text(json.dumps(caps),encoding='utf8');self.publications=NativePublications(self.store,self.caps,workspace_id=self.workspace,clock=lambda:self.clock[0])
        parent,_=self.publications.create(self.project['id'],NativePublicationCreate(revision=self.project['revision'],final_job_id=self.job['id'],platform=self.PLATFORM,
            metadata={'title':'Tên tiếng Việt cho bản duyệt Meta','privacy':'public'},request_key='explicit-meta-dry-run-fixture-key'),actor=self.principal.token_id)
        self.publications.approve(self.project['id'],parent['publication_id'],NativePublishApproval(expected_fingerprint=parent['request_fingerprint'],
            expected_artifact_sha256=parent['snapshot']['final_sha256'],acknowledged=True),actor=self.principal.token_id);self.parent=self.publications.process()
        self.target=PublishingTargetBinding(workspace_id=self.workspace,profile_id='ppf_meta_admission_'+self.PLATFORM,profile_version=1,platform=self.PLATFORM,
            provider_key={'facebook':'facebook-graph-api-publishing','instagram_reels':'instagram-graph-api-publishing'}[self.PLATFORM],
            target_account_id='12345' if self.PLATFORM=='facebook' else '23456',credential_binding_sha256='a'*64)
        self.profile=account.Profile(target=self.target,page_id='12345',api_version='v24.0');self.token='META-EXPLICIT-LOCAL-PROTOCOL-MOCK-TOKEN-1234567890'
        self.path=self.folder/'private'/'meta-token.dpapi';account.save_token(self.path,self.root,{'profile':self.profile.model_dump(mode='json'),
            'credential_alias':'meta-admission-fixture','expires_at':(self.clock[0]+timedelta(hours=1)).isoformat(),'scopes':sorted(REQUIRED[self.PLATFORM]),'token':self.token})
        binding=account.Binding(account_ref='npac_'+'a'*32,profile=self.profile,credential_alias='meta-admission-fixture',token_file=str(self.path),read_enabled=True)
        self.connection=account.NativeMetaAccountFactory(binding,self.root,self.workspace,owner_read_enabled=True,transport=httpx.MockTransport(self.response))
        self.accounts=NativeOfficialAccounts(self.store,workspace_id=self.workspace,factories={binding.account_ref:self.connection},clock=lambda:self.clock[0])
        self.accounts.create(self.project['id'],binding.account_ref,Verify(revision=self.project['revision'],expected_configuration_sha256=self.connection.sha256,
            acknowledged_read_only=True,request_key='explicit-meta-read-account-fixture-key'),actor=self.principal.token_id);self.check=self.accounts.process()
        self.factory=meta.NativeMetaPublishingFactory(self.connection,owner_enabled=True,gates=Gates(publish_enabled=True,external_execution_enabled=True,owner_gate_enabled=True))
        self.service=self.journal(self.factory)

    def tearDown(self):self.temp.cleanup()
    def response(self,request):
        self.calls.append((request.method,request.url.path));return httpx.Response(200,json={'id':'12345','instagram_business_account':{'id':'23456'}} if request.url.path.endswith('/me') else {'id':'23456'})
    def journal(self,factory=None):
        service=NativeOfficialPublications(self.store,self.publications,self.accounts,identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])
        if factory is not None:service.bind_meta_accounts(factories={factory.profile.target.profile_id:factory})
        return service
    def body(self,**changes):
        return MetaCreate.model_validate({'revision':self.project['revision'],'dry_run_publication_id':self.parent['publication_id'],
            'expected_dry_run_snapshot_sha256':self.parent['snapshot_sha256'],'account_check_id':self.check['check_id'],
            'expected_account_check_snapshot_sha256':self.check['snapshot_sha256'],'expected_account_result_sha256':self.check['result_sha256'],
            'profile_id':self.target.profile_id,'expected_configuration_sha256':self.factory.sha256,'request_key':'explicit-meta-publication-fixture-key',**changes})
    def create(self,body=None):return self.service.create(self.project['id'],body or self.body(),principal=self.principal)[0]
    def approve(self,value,**changes):return self.service.approve(self.project['id'],value['publication_id'],Approve(expected_snapshot_sha256=value['snapshot_sha256'],acknowledged_official_publication=True,**changes),principal=self.principal)
    def mutate_snapshot(self,value,mutate):
        snapshot=copy.deepcopy(value['snapshot']);mutate(snapshot)
        with self.store.transaction() as con:con.execute('UPDATE native_official_publications SET snapshot_json=?,snapshot_sha256=? WHERE publication_id=?',(json.dumps(snapshot),digest(snapshot),value['publication_id']))

    def test_separate_owner_grant_binds_current_account_dry_run_final_and_metadata_without_wire(self):
        before=self.store.get(self.project['id']);value=self.create();self.assertEqual(value['status'],'awaiting_publish_approval');self.assertIsNone(value['approval_id'])
        self.assertEqual(value['snapshot']['meta_account_proof'],self.check);self.assertEqual(value['snapshot']['metadata'],self.parent['snapshot']['request']['metadata'])
        self.assertFalse(value['snapshot']['account_check_is_publish_authority']);self.assertFalse(value['snapshot']['dry_run_receipt_is_publish_authority'])
        self.assertFalse(value['snapshot']['execution_supported']);self.assertIsNone(value['receipt']);self.assertFalse(value['published'])
        with self.assertRaisesRegex(WorkflowError,'NOT_DISPATCHABLE'):self.service.admission(self.project['id'],value['publication_id'])
        approved=self.approve(value);admitted=self.service.admission(self.project['id'],value['publication_id']);self.assertEqual(approved['status'],'queued')
        self.assertEqual(admitted[3]['phase'],'prepared');self.assertEqual(self.store.get(self.project['id']),before)
        self.assertEqual(len(self.calls),1 if self.PLATFORM=='facebook' else 2);self.assertNotIn(self.token,json.dumps(approved));self.assertNotIn(str(self.path),json.dumps(approved))

    def test_current_owner_expiry_revocation_and_explicit_renewal_preserve_original_history(self):
        value=self.create();old=self.approve(value,valid_for_seconds=60);self.clock[0]+=timedelta(seconds=61)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.service.admission(self.project['id'],value['publication_id'])
        payload=Renew(expected_snapshot_sha256=value['snapshot_sha256'],expected_dispatch_version=1,acknowledged_official_publication=True,valid_for_seconds=60,request_key='explicit-meta-renew-consent-fixture-key')
        renewed=self.service.renew(self.project['id'],value['publication_id'],payload,principal=self.principal);self.assertEqual(renewed['dispatch_version'],2)
        self.assertNotEqual(renewed['approval_id'],old['approval_id']);self.assertTrue(self.service.renew(self.project['id'],value['publication_id'],payload,principal=self.principal)['replayed'])
        self.service.admission(self.project['id'],value['publication_id']);self.service.revoke(self.project['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        with self.assertRaises(WorkflowError):self.service.admission(self.project['id'],value['publication_id'])
        self.assertEqual(self.service.get(self.project['id'],value['publication_id'])['snapshot'],value['snapshot'])

    def test_read_consent_expiry_blocks_new_admission_but_is_not_reused_as_owner_publish_consent(self):
        value=self.create();self.clock[0]+=timedelta(seconds=901)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_ACCOUNT_PROOF_REQUIRED'):self.create(self.body(request_key='explicit-meta-expired-new-review-key'))
        self.assertEqual(self.service.get(self.project['id'],value['publication_id']),value)
        self.approve(value);self.service.admission(self.project['id'],value['publication_id'])
        self.assertFalse(self.factory.public()['external_actions_enabled'])

    def test_default_factory_cannot_approve_or_decrypt_and_execution_is_not_implemented(self):
        with patch.object(account,'load_token',side_effect=AssertionError('No publish decrypt')):
            disabled=meta.NativeMetaPublishingFactory(self.connection);service=self.journal(disabled)
            value,_=service.create(self.project['id'],self.body(expected_configuration_sha256=disabled.sha256),principal=self.principal)
            self.assertEqual(value['status'],'not_configured');self.assertFalse(disabled.public()['execution_supported'])
            with self.assertRaises(WorkflowError):service.approve(self.project['id'],value['publication_id'],Approve(expected_snapshot_sha256=value['snapshot_sha256'],acknowledged_official_publication=True),principal=self.principal)
            with self.assertRaisesRegex(WorkflowError,'EXECUTION_NOT_IMPLEMENTED'):disabled.credential()

    def test_worker_rejects_before_credentials_intents_or_provider_mutation(self):
        value=self.create();self.approve(value);worker=NativeOfficialPublicationWorker(self.service,SessionVault(self.service,self.folder/'private'/'sessions'))
        calls=list(self.calls)
        with patch.object(account,'load_token',side_effect=AssertionError('No unsupported Meta decrypt')):
            with self.assertRaisesRegex(WorkflowError,'EXECUTION_NOT_IMPLEMENTED'):worker.context(self.project['id'],value['publication_id'],1)
        with self.store.transaction() as con:
            for table in ('native_official_publish_intents','native_official_publish_sessions','native_official_publish_receipts'):
                self.assertEqual(con.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.assertEqual(calls,self.calls);self.assertTrue(all(method=='GET' for method,_ in self.calls))

    def test_idempotency_duplicate_cancel_and_concurrent_create_preserve_history(self):
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.service.create(self.project['id'],self.body(),principal=self.principal),range(2)))
        self.assertEqual(sum(not replay for _,replay in results),1);value=results[0][0]
        with self.assertRaisesRegex(WorkflowError,'DUPLICATE_REVIEW_REQUIRED'):self.create(self.body(request_key='explicit-meta-other-key-same-final'))
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.create(self.body(expected_account_result_sha256='f'*64))
        self.approve(value);old=self.service.cancel(self.project['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        replacement=self.create(self.body(request_key='explicit-meta-replace-cancelled-review'));self.assertNotEqual(replacement['publication_id'],value['publication_id'])
        self.assertEqual(self.service.get(self.project['id'],value['publication_id']),old)

    def test_signed_human_role_and_revision_still_required(self):
        value=self.create();self.approve(value);raw,registry=human_fixture('viewer',workspace=self.workspace)
        self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400)
        with self.assertRaisesRegex(WorkflowError,'HUMAN_OWNER'):self.service.create(self.project['id'],self.body(),principal=self.verifier.verify('Bearer '+raw))
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.service.admission(self.project['id'],value['publication_id'])

    def test_current_final_project_capability_and_proof_fingerprints_are_required(self):
        for key in ('expected_account_check_snapshot_sha256','expected_account_result_sha256','expected_configuration_sha256','expected_dry_run_snapshot_sha256'):
            with self.assertRaises(WorkflowError):self.create(self.body(**{key:'f'*64,'request_key':'explicit-meta-fingerprint-'+key}))
        caps=json.loads(CAPABILITIES.read_bytes());self.caps.write_text(json.dumps(caps),encoding='utf8')
        with self.assertRaises(WorkflowError):self.create()

    def test_later_project_edit_or_missing_original_bytes_allows_history_only(self):
        body=self.body();value=self.create();self.approve(value)
        with self.store.transaction() as con:
            document=copy.deepcopy(self.project['document']);document['prompt']='EXPLICIT later edit fixture'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document),self.project['id']));self.store.version(con,self.project['id'])
        history=self.service.get(self.project['id'],value['publication_id']);replay,exact=self.service.create(self.project['id'],body,principal=self.principal)
        self.assertTrue(exact);self.assertEqual(replay,history)
        with self.assertRaises(WorkflowError):self.service.admission(self.project['id'],value['publication_id'])
        (self.root/'jobs'/self.job['id']/'final.mp4').unlink();self.assertEqual(self.service.get(self.project['id'],value['publication_id']),history)

    def test_keyless_reopened_history_has_no_factory_secret_load_or_claim_promotion(self):
        value=self.create();self.approve(value);expected=self.service.page(self.project['id']);self.path.unlink()
        with patch.object(account,'load_token',side_effect=AssertionError('No historical secret load')):
            store=Store(self.root);accounts=NativeOfficialAccounts(store,workspace_id=self.workspace)
            service=NativeOfficialPublications(store,NativePublications(store,self.caps,workspace_id=self.workspace),accounts)
            self.assertEqual(service.page(self.project['id']),expected);self.assertEqual(service.states()['profiles'],[])
            self.assertFalse(service.get(self.project['id'],value['publication_id'])['published'])

    def test_rehashed_embedded_proof_source_and_authority_claims_are_rejected(self):
        value=self.create()
        mutations=(lambda s:s.update(execution_supported=True),lambda s:s.update(account_check_is_publish_authority=0),lambda s:s.update(chunk_size=float(s['chunk_size'])),
            lambda s:s['meta_account_proof']['result']['meta'].update(provider_permissions_verified=True),
            lambda s:s['meta_account_proof']['result'].update(account_match=1),lambda s:s.update(final_bytes=s['final_bytes']+1))
        for mutate in mutations:
            self.mutate_snapshot(value,mutate)
            with self.assertRaises(WorkflowError):self.service.get(self.project['id'],value['publication_id'])

    def test_borrowed_cost_proof_and_fabricated_provider_dispatch_are_rejected(self):
        value=self.create();approved=self.approve(value)
        with self.store.transaction() as con:con.execute("UPDATE native_official_publish_dispatches SET phase='uploaded',remote_post_id='12345678901' WHERE publication_id=?",(value['publication_id'],))
        with self.assertRaisesRegex(WorkflowError,'EXECUTION_EVIDENCE_UNSUPPORTED'):self.service.get(self.project['id'],value['publication_id'])
        with self.store.transaction() as con:
            con.execute("UPDATE native_official_publish_dispatches SET phase='prepared',remote_post_id=NULL WHERE publication_id=?",(value['publication_id'],))
            proof=copy.deepcopy(self.check['result']);proof['meta']['observations'][0]['request_sha256']='f'*64
            con.execute('UPDATE native_official_account_checks SET result_json=?,result_sha256=? WHERE check_id=?',(json.dumps(proof),digest(proof),self.check['check_id']))
        with self.assertRaisesRegex(WorkflowError,'COST_EVIDENCE_CHANGED'):self.service.get(self.project['id'],value['publication_id'])

    def test_factory_and_protected_companion_configuration_are_frozen_without_startup_decrypt(self):
        path=self.folder/'private'/'distribution.json';path.write_text(json.dumps({'version':1,'workspace_id':self.workspace,'bindings':[{
            'account_ref':self.connection.account.account_ref,'expected_account_configuration_sha256':self.connection.sha256,
            'gates':{'publish_enabled':True,'external_execution_enabled':True,'owner_gate_enabled':True}}]}),encoding='utf8')
        with patch.object(account,'load_token',side_effect=AssertionError('No registry startup decrypt')):
            values=meta.load(path,self.accounts);self.assertEqual(values[self.target.profile_id].public()['status'],'NOT_CONFIGURED')
            enabled=meta.load(path,self.accounts,owner_enabled=True)[self.target.profile_id];self.assertEqual(enabled.public()['status'],'CONFIGURED')
            path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):enabled.public()
        self.factory.execution_supported=True
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.factory.public()

    def test_tagged_fields_forbid_metadata_credentials_endpoints_coercion_and_foreign_binding(self):
        for changes in ({'metadata':{'privacy':'private'}},{'token':'secret'},{'endpoint':'https://foreign.invalid'},{'revision':True},{'schema_version':'unknown'}):
            with self.assertRaises(ValueError):publication_request({**self.body().model_dump(mode='json'),**changes})
        with self.assertRaises(ValueError):meta.Options(share_to_feed=1)
        other=self.journal();foreign=copy.copy(self.factory);foreign.connection=copy.copy(self.connection)
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):other.bind_meta_accounts(factories={self.target.profile_id:foreign})


class FacebookAdmissionTests(MetaAdmissionTests):
    PLATFORM='facebook'
