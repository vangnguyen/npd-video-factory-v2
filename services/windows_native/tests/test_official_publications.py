"""Explicit nonplayable QC/rights/identity/account fixtures; never Owner/provider acceptance."""
import copy,json,tempfile,unittest,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
import httpx
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.publications import NativePublications
from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
from services.windows_native.tests.test_publications import render_fixture,CAPABILITIES
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.official_account_registry import Account,AccountFactory
from services.windows_native.official_accounts import NativeOfficialAccounts,Verify
from services.windows_native.official_publication_registry import PublishingFactory
from services.windows_native.official_publication_models import Profile,Gates,Create,Approve,Action
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.backup import database_status
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.analytics_official import AnalyticsOAuthCredential,YT_READ,YT_ANALYTICS
from app.publishing_credentials import PublishingOAuthCredential,UPLOAD,READ
from app.publishing_models import PublishingTargetBinding
from app.publishing_wire import OfficialHTTPClient

class OfficialPublicationReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.root=self.folder/'state';self.root.mkdir();self.store=Store(self.root);self.workspace='wsp_official_publication_fixture'
        (self.root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}),encoding='utf-8')
        self.clock=[datetime.now(timezone.utc)];self.raw,registry=human_fixture('owner',workspace=self.workspace);self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400);self.principal=self.verifier.verify('Bearer '+self.raw)
        caps=json.loads(CAPABILITIES.read_bytes());caps['platforms']['youtube']['verification_state']='owner_verified_for_live';caps['notice']='EXPLICIT SYNTHETIC PLATFORM ACCEPTANCE FIXTURE; NOT OWNER VERIFICATION'
        self.caps=self.folder/'explicit-capabilities.json';self.caps.write_text(json.dumps(caps),encoding='utf-8');self.project,self.job=render_fixture(self.store)
        self.publications=NativePublications(self.store,self.caps,workspace_id=self.workspace,clock=lambda:self.clock[0])
        payload=NativePublicationCreate(revision=self.project['revision'],final_job_id=self.job['id'],platform='youtube',metadata={'title':'Explicit official review fixture','privacy':'private'},request_key='explicit-dry-run-publication-fixture-key')
        parent,_=self.publications.create(self.project['id'],payload,actor=self.principal.token_id)
        self.publications.approve(self.project['id'],parent['publication_id'],NativePublishApproval(expected_fingerprint=parent['request_fingerprint'],expected_artifact_sha256=parent['snapshot']['final_sha256'],acknowledged=True),actor=self.principal.token_id)
        self.parent=self.publications.process();self.calls=[]
        self.target=PublishingTargetBinding(workspace_id=self.workspace,profile_id='ppf_official_publication_fixture',profile_version=1,platform='youtube',provider_key='youtube-data-api-publishing',target_account_id='UC_EXPLICIT_FIXTURE',credential_binding_sha256='a'*64)
        account=Account(account_ref='npac_'+'a'*32,target=self.target,credential_alias='youtube-fixture-read',token_file=str(self.folder/'secrets'/'explicit.dpapi'),read_enabled=True)
        read_credential=AnalyticsOAuthCredential(self.target,self.clock[0]+timedelta(hours=1),frozenset({YT_READ,YT_ANALYTICS}),'EXPLICIT-READ-TOKEN-FIXTURE-0123456789')
        def read_response(request):self.calls.append(request.method);return httpx.Response(200,json={'items':[{'id':self.target.target_account_id}]})
        self.account_factory=AccountFactory(account,self.root,self.workspace,owner_read_enabled=True,transport=httpx.MockTransport(read_response),resolver=lambda _:read_credential)
        self.accounts=NativeOfficialAccounts(self.store,workspace_id=self.workspace,factories={account.account_ref:self.account_factory},clock=lambda:self.clock[0])
        check,_=self.accounts.create(self.project['id'],account.account_ref,Verify(revision=self.project['revision'],expected_configuration_sha256=self.account_factory.sha256,acknowledged_read_only=True,request_key='explicit-account-proof-fixture-key'),actor=self.principal.token_id)
        self.check=self.accounts.process()
        self.credential=PublishingOAuthCredential(self.target,self.clock[0]+timedelta(hours=1),frozenset({UPLOAD,READ}),'EXPLICIT-UPLOAD-TOKEN-FIXTURE-0123456789')
        self.profile=Profile(target=self.target,category_id='27',made_for_kids=False,contains_synthetic_media=True)
        self.client=OfficialHTTPClient('youtube',transport=httpx.MockTransport(lambda _:self.fail('Journal must never dispatch')))
        self.factory=PublishingFactory(self.profile,self.root,self.workspace,gates=Gates(publish_enabled=True,external_execution_enabled=True,owner_gate_enabled=True),client=self.client,resolver=lambda _:self.credential)
        self.service=self.journal(self.factory)
    def tearDown(self):self.temp.cleanup()
    def journal(self,factory):return NativeOfficialPublications(self.store,self.publications,self.accounts,factories={self.target.profile_id:factory},identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])
    def body(self,**changes):return Create.model_validate({'revision':self.project['revision'],'dry_run_publication_id':self.parent['publication_id'],'expected_dry_run_snapshot_sha256':self.parent['snapshot_sha256'],
        'account_check_id':self.check['check_id'],'profile_id':self.target.profile_id,'expected_configuration_sha256':self.factory.sha256,'request_key':'explicit-official-publication-fixture-key',**changes})
    def create(self,body=None):return self.service.create(self.project['id'],body or self.body(),principal=self.principal)[0]
    def approve(self,value,**changes):return self.service.approve(self.project['id'],value['publication_id'],Approve(expected_snapshot_sha256=value['snapshot_sha256'],acknowledged_official_publication=True,**changes),principal=self.principal)
    def test_dry_run_and_account_proof_cannot_authorize_an_official_dispatch(self):
        before=self.store.get(self.project['id']);value=self.create();self.assertEqual(value['status'],'awaiting_publish_approval');self.assertIsNone(value['approval_id'])
        self.assertFalse(value['snapshot']['dry_run_receipt_is_publish_authority']);self.assertFalse(value['snapshot']['account_check_is_publish_authority'])
        with self.assertRaisesRegex(WorkflowError,'NOT_DISPATCHABLE'):self.service.admission(self.project['id'],value['publication_id'])
        approved=self.approve(value);admitted=self.service.admission(self.project['id'],value['publication_id']);self.assertEqual(approved['status'],'queued');self.assertEqual(admitted[3]['phase'],'prepared')
        self.assertEqual(len(self.calls),1);self.assertEqual(self.store.get(self.project['id']),before);self.assertNotIn(self.credential.token,json.dumps(approved));self.assertFalse(self.factory.public()['automatic_publishing'])
    def test_owner_identity_role_revocation_and_revision_are_checked_again_at_admission(self):
        value=self.create();self.approve(value)
        old=self.verifier;raw,data=human_fixture('viewer',workspace=self.workspace);self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.service.admission(self.project['id'],value['publication_id'])
        with self.assertRaisesRegex(WorkflowError,'HUMAN_OWNER'):self.service.create(self.project['id'],self.body(),principal=self.verifier.verify('Bearer '+raw))
        self.verifier=old;object.__setattr__(self.verifier.registry.tokens[self.principal.token_id],'enabled',False)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.service.admission(self.project['id'],value['publication_id'])
    def test_current_grant_expiry_is_bounded_and_never_reuses_dry_run_consent(self):
        value=self.create();self.approve(value,valid_for_seconds=60);self.clock[0]+=timedelta(seconds=61)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.service.admission(self.project['id'],value['publication_id'])
        self.assertEqual(self.publications.get(self.project['id'],self.parent['publication_id'])['status'],'dry_run_succeeded')
    def test_exact_key_replay_survives_later_media_edit_but_dispatch_cannot(self):
        body=self.body();value=self.create(body);self.approve(value)
        # This deliberately minimal render fixture has no editable Source timeline.
        # An explicit persisted edit fixture exercises publication revision fencing.
        with self.store.transaction() as con:
            document=copy.deepcopy(self.project['document']);document['prompt']='Explicit later edit fixture'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document),self.project['id']));self.store.version(con,self.project['id'])
        replay,exact=self.service.create(self.project['id'],body,principal=self.principal);self.assertTrue(exact);self.assertEqual(replay['publication_id'],value['publication_id'])
        with self.assertRaises(WorkflowError):self.service.admission(self.project['id'],value['publication_id'])
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.service.create(self.project['id'],body.model_copy(update={'revision':body.revision+1}),principal=self.principal)
    def test_new_key_cannot_create_duplicate_same_account_and_final_artifact(self):
        self.create()
        with self.assertRaisesRegex(WorkflowError,'DUPLICATE_REVIEW_REQUIRED'):self.create(self.body(request_key='explicit-new-key-same-media-fixture'))
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_publications').fetchone()[0],1)
    def test_cancelled_prepared_review_can_be_replaced_without_rewriting_history(self):
        value=self.create();self.approve(value)
        cancelled=self.service.cancel(self.project['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        replacement=self.create(self.body(request_key='explicit-replace-unsent-cancelled-review-key'))
        self.assertNotEqual(value['publication_id'],replacement['publication_id']);self.assertEqual(self.service.get(self.project['id'],value['publication_id']),cancelled)
        self.assertEqual(len(self.calls),1)
    def test_not_configured_review_does_not_reserve_an_unsent_artifact_forever(self):
        disabled=PublishingFactory(self.profile,self.root,self.workspace,client=self.client);service=self.journal(disabled)
        old,_=service.create(self.project['id'],self.body(expected_configuration_sha256=disabled.sha256),principal=self.principal)
        replacement=self.create(self.body(request_key='explicit-new-configured-review-key'))
        self.assertEqual(old['status'],'not_configured');self.assertEqual(replacement['status'],'awaiting_publish_approval')
        self.assertEqual(service.get(self.project['id'],old['publication_id']),old);self.assertEqual(len(self.calls),1)
    def test_concurrent_requests_create_one_review_and_one_separate_grant(self):
        with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(lambda _:self.service.create(self.project['id'],self.body(),principal=self.principal),range(2)))
        self.assertEqual(sum(not replay for _,replay in values),1);value=values[0][0]
        with ThreadPoolExecutor(max_workers=2) as pool:approved=list(pool.map(lambda _:self.approve(value),range(2)))
        self.assertEqual(approved[0]['approval_id'],approved[1]['approval_id'])
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_publish_approvals').fetchone()[0],1)
    def test_default_factory_is_not_configured_and_cannot_approve_or_read_secret(self):
        factory=PublishingFactory(self.profile,self.root,self.workspace,client=self.client,resolver=lambda _:self.fail('Default must not resolve OAuth'))
        service=self.journal(factory);body=self.body(expected_configuration_sha256=factory.sha256);value,_=service.create(self.project['id'],body,principal=self.principal)
        self.assertEqual(value['status'],'not_configured');self.assertFalse(factory.public()['external_actions_enabled'])
        with self.assertRaises(WorkflowError):service.approve(self.project['id'],value['publication_id'],Approve(expected_snapshot_sha256=value['snapshot_sha256'],acknowledged_official_publication=True),principal=self.principal)
        with self.assertRaisesRegex(WorkflowError,'NOT_CONFIGURED'):factory.credential()
    def test_changed_account_factory_or_publish_configuration_cannot_gain_dispatch(self):
        value=self.create();self.approve(value);self.account_factory.read_enabled=False
        with self.assertRaises(WorkflowError):self.service.admission(self.project['id'],value['publication_id'])
        self.account_factory.read_enabled=True;self.factory.gates.publish_enabled=False
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.factory.public()
        with self.assertRaises(WorkflowError):self.service.admission(self.project['id'],value['publication_id'])
    def test_foreign_project_workspace_or_account_proof_is_rejected(self):
        value=self.create();other=self.store.create('Foreign explicit fixture','No source')
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.service.get(other['id'],value['publication_id'])
        with self.assertRaises(WorkflowError):self.create(self.body(account_check_id='nack_'+'f'*32,request_key='explicit-foreign-account-fixture-key'))
        self.factory.workspace='wsp_foreign'
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.factory.public()
    def test_internal_safe_platform_profile_remains_blocked_for_official_publication(self):
        caps=json.loads(CAPABILITIES.read_bytes());self.caps.write_text(json.dumps(caps),encoding='utf-8')
        with self.assertRaises(WorkflowError):self.create()
        self.assertEqual(len(self.calls),1)
    def test_source_artifact_corruption_prevents_create_and_existing_dispatch(self):
        value=self.create();self.approve(value);(self.root/'jobs'/self.job['id']/'final.mp4').write_bytes(b'EXPLICIT CORRUPTION FIXTURE')
        with self.assertRaises(WorkflowError):self.service.admission(self.project['id'],value['publication_id'])
        with self.assertRaises(WorkflowError):self.create(self.body(request_key='explicit-corrupt-final-fixture-key'))
    def test_cancel_revokes_prepared_grant_and_never_deletes_a_remote_post(self):
        value=self.create();approved=self.approve(value);cancelled=self.service.cancel(self.project['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        self.assertEqual(cancelled['status'],'cancelled')
        with self.assertRaisesRegex(WorkflowError,'NOT_DISPATCHABLE'):self.service.admission(self.project['id'],value['publication_id'])
        with self.store.transaction() as con:
            self.assertEqual(con.execute('SELECT status FROM native_official_publish_approvals WHERE approval_id=?',(approved['approval_id'],)).fetchone()[0],'revoked')
            con.execute("UPDATE native_official_publish_dispatches SET phase='init_intent' WHERE publication_id=?",(value['publication_id'],))
        with self.assertRaisesRegex(WorkflowError,'EXTERNAL_RECONCILIATION_REQUIRED'):self.service.cancel(self.project['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
    def test_rehashed_safety_claim_and_grant_cannot_create_authority(self):
        value=self.create();self.approve(value)
        with self.store.transaction() as con:
            row=self.service.row(con,self.project['id'],value['publication_id']);grant_row=con.execute('SELECT * FROM native_official_publish_approvals WHERE approval_id=?',(row['approval_id'],)).fetchone()
            grant=json.loads(grant_row['grant_json']);grant['acknowledged_official_publication']=1
            con.execute('UPDATE native_official_publish_approvals SET grant_json=?,grant_sha256=? WHERE approval_id=?',(json.dumps(grant),digest(grant),row['approval_id']))
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.service.admission(self.project['id'],value['publication_id'])
        snapshot=copy.deepcopy(value['snapshot']);snapshot['dry_run_receipt_is_publish_authority']=0
        with self.store.transaction() as con:con.execute('UPDATE native_official_publications SET snapshot_json=?,snapshot_sha256=? WHERE publication_id=?',(json.dumps(snapshot),digest(snapshot),value['publication_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.service.get(self.project['id'],value['publication_id'])
    def test_strict_requests_disclosures_and_transport_identity_reject_coercion_or_mutation(self):
        for changes in [{'revision':True},{'mode':'live'},{'token':'not accepted'}]:
            with self.assertRaises(ValueError):Create.model_validate({**self.body().model_dump(),**changes})
        for changes in [{'acknowledged_official_publication':1},{'valid_for_seconds':True},{'valid_for_seconds':3601}]:
            with self.assertRaises(ValueError):Approve.model_validate({'expected_snapshot_sha256':'a'*64,'acknowledged_official_publication':True,**changes})
        for changes in [{'made_for_kids':0},{'contains_synthetic_media':1},{'chunk_size':True},{'chunk_size':300000}]:
            with self.assertRaises(ValueError):Profile.model_validate({**self.profile.model_dump(),**changes})
        self.factory.client=OfficialHTTPClient('youtube',transport=self.client.transport)
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.factory.public()
    def test_offline_backup_counts_consent_dispatch_and_blocks_pending_official_work(self):
        value=self.create();self.approve(value);facts=database_status(self.store.db)
        self.assertEqual(facts['counts']['native_official_publications'],1);self.assertEqual(facts['counts']['native_official_publish_approvals'],1)
        self.assertEqual(facts['counts']['native_official_publish_dispatches'],1);self.assertEqual(facts['active_operations'],1)
        self.service.cancel(self.project['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        self.assertEqual(database_status(self.store.db)['active_operations'],0)
    def test_pure_contract_import_requires_no_api_framework_database_crypto_or_gpu(self):
        subprocess.run([sys.executable,'-c',"from services.windows_native.official_publications import NativeOfficialPublications; import sys; assert not any(name.startswith(('sqlalchemy','fastapi','torch','vieneu','cryptography')) for name in sys.modules)"],cwd=Path(__file__).resolve().parents[3],check=True,capture_output=True,timeout=10)
    def test_configuration_fingerprint_cannot_be_replaced_with_unbound_text(self):
        self.factory.sha256='f'*64
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.factory.public()
    def test_rehashed_invalid_final_size_is_a_sanitized_native_evidence_error(self):
        value=self.create();snapshot=copy.deepcopy(value['snapshot']);snapshot['final_bytes']=True
        with self.store.transaction() as con:con.execute('UPDATE native_official_publications SET snapshot_json=?,snapshot_sha256=? WHERE publication_id=?',(json.dumps(snapshot),digest(snapshot),value['publication_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.service.get(self.project['id'],value['publication_id'])
