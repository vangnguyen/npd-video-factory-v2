"""Admission only: local DPAPI/SQLite and explicit nonplayable/provider fixtures.

Transfer/status/session execution and genuine provider/Owner acceptance are separate.
"""
import copy,json,unittest
from datetime import timedelta
from unittest.mock import patch
from types import SimpleNamespace
from pydantic import ValidationError
from services.windows_native import tiktok_connection as connection
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_models import TikTokCreate,Gates,Approve,Renew,publication_request
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native import official_publication_routes
from services.windows_native.publications import NativePublications
from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
from services.windows_native.store import Store
from services.windows_native.tiktok_distribution import NativeTikTokPublishingFactory,DistributionRegistry,load
from services.windows_native.tiktok_creators import NativeTikTokCreators,Action as CreatorAction
from services.windows_native.tests.test_tiktok_creators import TikTokCreatorFixture
from services.windows_native.tests.test_publications import CAPABILITIES

class TikTokDistributionAdmissionTests(TikTokCreatorFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        capabilities=json.loads(CAPABILITIES.read_bytes());capabilities['platforms']['tiktok']['verification_state']='owner_verified_for_live'
        capabilities['notice']='EXPLICIT PROTOCOL ACCEPTANCE FIXTURE, NOT OWNER OR PROVIDER VERIFICATION'
        self.capabilities=self.folder/'explicit-capabilities.json';self.capabilities.write_text(json.dumps(capabilities),encoding='utf-8')
        self.publications=NativePublications(self.store,self.capabilities,workspace_id=self.workspace,clock=lambda:self.clock[0])
        self.official=self.journal();self.service=NativeTikTokCreators(self.official,factories={self.target.profile_id:self.factory},enabled=True)
        self.distribution=NativeTikTokPublishingFactory(self.factory,gates=Gates(publish_enabled=True,external_execution_enabled=True,owner_gate_enabled=True),owner_enabled=True)
        self.official.bind_tiktok_creators(self.service,factories={self.target.profile_id:self.distribution})
        self.check=self.completed();self.draft=self.service.draft(self.project['id'],self.draft_body(self.check),principal=self.principal)[0]
        payload=NativePublicationCreate(revision=self.project['revision'],final_job_id=self.job['id'],platform='tiktok',metadata=self.draft['snapshot']['request']['metadata'],request_key='explicit-tiktok-distribution-dry-run-key')
        parent,_=self.publications.create(self.project['id'],payload,actor=self.principal.token_id)
        self.publications.approve(self.project['id'],parent['publication_id'],NativePublishApproval(expected_fingerprint=parent['request_fingerprint'],expected_artifact_sha256=parent['snapshot']['final_sha256'],acknowledged=True),actor=self.principal.token_id)
        self.parent=self.publications.process()
    def journal(self):
        return NativeOfficialPublications(self.store,self.publications,self.accounts,identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])
    def publication_body(self,**changes):
        return TikTokCreate.model_validate({'revision':self.project['revision'],'dry_run_publication_id':self.parent['publication_id'],'expected_dry_run_snapshot_sha256':self.parent['snapshot_sha256'],
            'creator_draft_id':self.draft['draft_id'],'expected_creator_draft_snapshot_sha256':self.draft['snapshot_sha256'],'profile_id':self.target.profile_id,
            'expected_configuration_sha256':self.distribution.sha256,'request_key':'explicit-tiktok-distribution-publication-key',**changes})
    def publication(self,**changes):return self.official.create(self.project['id'],self.publication_body(**changes),principal=self.principal)[0]
    def approve_publication(self,value,**changes):
        return self.official.approve(self.project['id'],value['publication_id'],Approve(expected_snapshot_sha256=value['snapshot_sha256'],acknowledged_official_publication=True,**changes),principal=self.principal)
    def test_draft_and_dry_run_require_separate_owner_publication_approval(self):
        before=self.store.get(self.project['id'])
        with patch.object(connection,'load_token',side_effect=AssertionError('Admission must not decrypt')):
            value=self.publication();self.assertEqual(value['status'],'awaiting_publish_approval');self.assertIsNone(value['approval_id'])
            with self.assertRaisesRegex(WorkflowError,'NOT_DISPATCHABLE'):self.official.admission(self.project['id'],value['publication_id'])
            approved=self.approve_publication(value);admitted=self.official.admission(self.project['id'],value['publication_id'])
        self.assertEqual(approved['status'],'queued');self.assertEqual(admitted[3]['phase'],'prepared');self.assertEqual(admitted[3]['acknowledged_bytes'],0)
        self.assertFalse(value['snapshot']['dry_run_receipt_is_publish_authority']);self.assertFalse(value['snapshot']['account_check_is_publish_authority'])
        self.assertEqual(value['snapshot']['creator_draft'],self.draft);self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(len(self.wire),2)
    def test_default_off_factory_does_not_decrypt_enable_network_or_publish(self):
        with patch.object(connection,'load_token',side_effect=AssertionError('No implicit decrypt')):
            factory=NativeTikTokPublishingFactory(self.factory);journal=self.journal();creators=NativeTikTokCreators(journal,factories={self.target.profile_id:self.factory},enabled=True)
            journal.bind_tiktok_creators(creators,factories={self.target.profile_id:factory})
            state=factory.public();value,_=journal.create(self.project['id'],self.publication_body(expected_configuration_sha256=factory.sha256),principal=self.principal)
        self.assertEqual(state['status'],'NOT_CONFIGURED');self.assertFalse(state['external_actions_enabled']);self.assertTrue(state['execution_supported']);self.assertFalse(factory.client.network_enabled)
        self.assertEqual(value['status'],'not_configured');self.assertFalse(value['published']);self.assertIsNone(value['receipt']);self.assertEqual(len(self.wire),2)
    def test_request_key_and_final_account_dedupe_never_make_a_second_publication(self):
        first=self.publication();same,replayed=self.official.create(self.project['id'],self.publication_body(),principal=self.principal)
        self.assertTrue(replayed);self.assertEqual(first,same)
        with self.assertRaisesRegex(WorkflowError,'DUPLICATE_REVIEW_REQUIRED'):self.publication(request_key='explicit-tiktok-distribution-duplicate-key')
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.publication(expected_creator_draft_snapshot_sha256='b'*64)
    def test_request_tags_flags_and_configuration_are_strict(self):
        body=self.publication_body().model_dump(mode='json');self.assertEqual(publication_request(body),self.publication_body())
        for invalid in [None,[],{**body,'schema_version':'native-official-publication-request-v1'},{**body,'schema_version':'unsupported'}]:
            with self.assertRaises(ValueError):publication_request(invalid)
        for invalid in [0,'true']:
            with self.assertRaises(ValidationError):Gates(publish_enabled=invalid)
        with self.assertRaises(ValidationError):TikTokCreate.model_validate({**body,'revision':True})
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_INVALID'):NativeTikTokPublishingFactory(self.factory,owner_enabled='true')
        with self.assertRaisesRegex(WorkflowError,'CURRENT_CREATOR_REQUIRED'):self.publication(expected_configuration_sha256='c'*64)
    def test_cipher_and_configuration_drift_block_current_admission(self):
        value=self.publication();self.approve_publication(value);original=self.path.read_bytes();self.path.write_bytes(original+b'EXPLICIT CIPHER DRIFT')
        with self.assertRaises(WorkflowError):self.official.admission(self.project['id'],value['publication_id'])
        self.path.write_bytes(original);self.distribution.configuration['gates']['publish_enabled']=False
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.distribution.public()
    def test_expired_creator_consent_cannot_create_new_publication_but_history_survives(self):
        self.clock[0]+=timedelta(seconds=601)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_CREATOR_REQUIRED'):self.publication()
        self.assertEqual(self.service.get_draft(self.project['id'],self.draft['draft_id']),self.draft)
    def test_cancelled_creator_blocks_admission_and_preserves_original_evidence(self):
        value=self.publication();self.approve_publication(value)
        self.service.cancel(self.project['id'],self.check['check_id'],CreatorAction(expected_snapshot_sha256=self.check['snapshot_sha256']),principal=self.principal)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_CREATOR_REQUIRED'):self.official.admission(self.project['id'],value['publication_id'])
        self.assertEqual(self.official.get(self.project['id'],value['publication_id'])['snapshot'],value['snapshot'])
    def test_expired_grant_requires_explicit_prepared_renewal_without_new_init(self):
        value=self.publication();self.approve_publication(value,valid_for_seconds=60);self.clock[0]+=timedelta(seconds=61)
        with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.official.admission(self.project['id'],value['publication_id'])
        renewal=Renew(expected_snapshot_sha256=value['snapshot_sha256'],expected_dispatch_version=1,acknowledged_official_publication=True,request_key='explicit-tiktok-admission-renewal-key')
        first=self.official.renew(self.project['id'],value['publication_id'],renewal,principal=self.principal);again=self.official.renew(self.project['id'],value['publication_id'],renewal,principal=self.principal)
        self.assertFalse(first['replayed']);self.assertTrue(again['replayed']);self.assertEqual(first['approval_id'],again['approval_id'])
        admitted=self.official.admission(self.project['id'],value['publication_id']);self.assertEqual(admitted[3]['version'],2);self.assertEqual(admitted[0]['snapshot'],value['snapshot']);self.assertEqual(len(self.wire),2)
    def test_current_owner_revocation_blocks_admission_without_private_load(self):
        value=self.publication();self.approve_publication(value);object.__setattr__(self.verifier.registry.tokens[self.principal.token_id],'enabled',False)
        with patch.object(connection,'load_token',side_effect=AssertionError('No private load')):
            with self.assertRaisesRegex(WorkflowError,'CURRENT_OWNER_GRANT_REQUIRED'):self.official.admission(self.project['id'],value['publication_id'])
        self.assertEqual(self.official.get(self.project['id'],value['publication_id'])['snapshot'],value['snapshot'])
    def test_final_bytes_and_document_drift_block_admission(self):
        value=self.publication();self.approve_publication(value);path=self.store.root/'jobs'/self.job['id']/'final.mp4';original=path.read_bytes();path.write_bytes(original+b'EXPLICIT FINAL DRIFT')
        with self.assertRaises(WorkflowError):self.official.admission(self.project['id'],value['publication_id'])
        path.write_bytes(original);self.fixture_document_drift()
        with self.assertRaises(WorkflowError):self.official.admission(self.project['id'],value['publication_id'])
    def test_cold_keyless_history_keeps_original_draft_cost_links(self):
        value=self.publication();self.approve_publication(value);expected=self.official.get(self.project['id'],value['publication_id'])
        with patch.object(connection,'load_token',side_effect=AssertionError('Cold history must not decrypt')):
            store=Store(self.root);publications=NativePublications(store,self.capabilities,workspace_id=self.workspace);accounts=NativeOfficialAccounts(store,workspace_id=self.workspace)
            cold=NativeOfficialPublications(store,publications,accounts);self.assertIsNone(cold.tiktok_creators)
            self.assertEqual(cold.get(self.project['id'],value['publication_id']),expected)
        self.assertEqual(len(self.wire),2)
    def test_rehashed_public_snapshot_cannot_replace_its_draft_id(self):
        value=self.publication()
        with self.store.transaction() as con:row=dict(self.official.row(con,self.project['id'],value['publication_id']))
        snapshot=copy.deepcopy(value['snapshot']);snapshot['request']['creator_draft_id']='ntpd_'+'d'*32;row['snapshot_json']=json.dumps(snapshot);row['snapshot_sha256']=digest(snapshot);row['request_fingerprint']=digest(snapshot['request'])
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.official.read(row)
    def test_completed_dry_run_must_use_exact_reviewed_draft_metadata(self):
        payload=NativePublicationCreate(revision=self.project['revision'],final_job_id=self.job['id'],platform='tiktok',metadata={'title':'Explicit different metadata fixture','privacy':'private'},request_key='explicit-tiktok-different-metadata-dry-run')
        parent,_=self.publications.create(self.project['id'],payload,actor=self.principal.token_id)
        self.publications.approve(self.project['id'],parent['publication_id'],NativePublishApproval(expected_fingerprint=parent['request_fingerprint'],expected_artifact_sha256=parent['snapshot']['final_sha256'],acknowledged=True),actor=self.principal.token_id)
        parent=self.publications.process()
        with self.assertRaisesRegex(WorkflowError,'FINAL_OR_METADATA_CHANGED'):self.publication(dry_run_publication_id=parent['publication_id'],expected_dry_run_snapshot_sha256=parent['snapshot_sha256'])
    def test_original_creator_response_cost_proof_cannot_be_replaced(self):
        value=self.publication()
        with self.store.transaction() as con:con.execute('UPDATE native_tiktok_creator_responses SET response_sha256=? WHERE check_id=?',('f'*64,self.check['check_id']))
        with patch.object(connection,'load_token',side_effect=AssertionError('History must not decrypt')):
            with self.assertRaises(WorkflowError):self.official.get(self.project['id'],value['publication_id'])
            with self.assertRaises(WorkflowError):self.approve_publication(value)
    def test_tagged_route_rejects_unknown_schema_and_checks_owner_before_body(self):
        handler=SimpleNamespace(server=SimpleNamespace(official_publications=self.official),auth_session=SimpleNamespace(principal=self.principal));url='/api/projects/'+self.project['id']+'/official-publications'
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):official_publication_routes.post(handler,url,{'schema_version':'unsupported'})
        handler.auth_session=None
        with self.assertRaisesRegex(WorkflowError,'HUMAN_OWNER'):official_publication_routes.post(handler,url,object())
        handler.auth_session=SimpleNamespace(principal=self.principal)
        value=official_publication_routes.post(handler,url,self.publication_body().model_dump(mode='json'));self.assertEqual(value['snapshot']['target']['platform'],'tiktok');self.assertFalse(value['idempotent_replay'])
    def test_registry_binds_creator_config_defaults_off_and_detects_file_drift(self):
        path=self.folder/'private'/'distribution.json';registry=DistributionRegistry(version=1,workspace_id=self.workspace,bindings=[{'profile_id':self.target.profile_id,'expected_creator_configuration_sha256':self.factory.sha256,
            'gates':{'publish_enabled':True,'external_execution_enabled':True,'owner_gate_enabled':True}}]);path.write_text(registry.model_dump_json(),encoding='utf-8')
        with patch.object(connection,'load_token',side_effect=AssertionError('Registry must not decrypt')):
            disabled=load(path,self.service);enabled=load(path,self.service,owner_enabled=True)
            self.assertEqual(disabled[self.target.profile_id].public()['status'],'NOT_CONFIGURED');self.assertEqual(enabled[self.target.profile_id].public()['status'],'CONFIGURED')
            path.write_bytes(path.read_bytes()+b' ')
            with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):enabled[self.target.profile_id].check()
            with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_INVALID'):load(path,object())
    def test_revoked_grant_blocks_worker_and_intent_before_session_credential_cost_or_wire(self):
        value=self.publication();self.approve_publication(value);vault=SessionVault(self.official,directory=self.folder/'private'/'sessions');worker=NativeOfficialPublicationWorker(self.official,vault)
        with self.store.transaction() as con:before=con.execute('SELECT COUNT(*) FROM native_cost_operations').fetchone()[0]
        from services.windows_native.official_publication_models import Action
        self.official.revoke(self.project['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        with patch.object(connection,'load_token',side_effect=AssertionError('No publishing decrypt')),patch.object(vault,'load',side_effect=AssertionError('No session load')):
            with self.assertRaisesRegex(WorkflowError,'NOT_DISPATCHABLE'):worker.step(self.project['id'],value['publication_id'],1)
            with self.assertRaisesRegex(WorkflowError,'NOT_DISPATCHABLE'):self.official.begin_intent(self.project['id'],value['publication_id'],1,'init')
        with self.store.transaction() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM native_cost_operations').fetchone()[0],before)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM native_official_publish_intents').fetchone()[0],0)
        self.assertEqual(len(self.wire),2);self.assertEqual(self.official.state(self.project['id'],value['publication_id'])['dispatch']['phase'],'prepared')

if __name__=='__main__':unittest.main()
