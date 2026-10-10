"""Local DPAPI/SQLite with explicit S3/Meta/Owner/platform/nonplayable media fixtures."""
import copy,json,unittest
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests import test_meta_distribution as meta_fixture
from services.windows_native.tests.media_delivery_fixture import FixtureStore
from services.windows_native.publishing_media_delivery import NativePublishingMediaDelivery,NativeMediaDeliveryFactory,Create,save_credential,LEASE_PREFIX,LEASE_ENTROPY
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.store import Store
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_models import Action
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_native_analytics_refresh import settings
from app.publishing_media_delivery import StorageProfile

class NativeMediaDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.c=meta_fixture.MetaAdmissionTests('test_separate_owner_grant_binds_current_account_dry_run_final_and_metadata_without_wire');self.c.setUp()
        self.publication=self.c.create();self.c.approve(self.publication)
        self.profile=StorageProfile('https://storage-fixture.invalid','vf-media-fixture','us-east-1','publishing-media-fixture')
        self.storage=FixtureStore(self.profile,lambda:self.c.clock[0]);self.directory=self.c.folder/'private'/'media-leases'
        self.factory=NativeMediaDeliveryFactory(self.profile,self.c.root,self.c.workspace,enabled=True,directory=self.directory,wire=self.storage.wire,clock=lambda:self.c.clock[0])
        self.service=NativePublishingMediaDelivery(self.c.service,factory=self.factory)
    def tearDown(self):self.c.tearDown()
    def body(self,**changes):return Create.model_validate({'publication_id':self.publication['publication_id'],'expected_publication_snapshot_sha256':self.publication['snapshot_sha256'],
        'expected_configuration_sha256':self.factory.sha256,'acknowledged_external_media_delivery':True,'request_key':'explicit-media-delivery-fixture-key',**changes})
    def create(self,body=None):return self.service.create(self.c.project['id'],body or self.body(),principal=self.c.principal)[0]
    def process(self,value):return self.service.process(self.c.project['id'],value['delivery_id'])
    def test_exact_approved_final_is_readback_verified_private_and_every_wire_has_nullable_cost(self):
        before=self.c.store.get(self.c.project['id']);value=self.create();result=self.process(value);self.assertEqual(result['status'],'succeeded',result['failure_code'])
        self.assertEqual(self.storage.puts,1);self.assertEqual(len(result['operations']),6);self.assertFalse(result['publishing_authority']);self.assertFalse(result['url_returned'])
        self.assertNotIn('X-Amz-',json.dumps(result));self.assertEqual(self.c.store.get(self.c.project['id']),before);self.assertEqual(len(self.c.calls),2)
        costs=[r for r in self.service.costs.summary(self.c.project['id'])['records'] if r['provider']=='s3-publishing-media']
        self.assertEqual(len(costs),6);self.assertTrue(all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs))
        private=self.directory/(result['lease_ref']+'.dpapi');self.assertTrue(private.read_bytes().startswith(LEASE_PREFIX));self.assertNotIn(b'X-Amz-',private.read_bytes())
        replay,exact=self.service.create(self.c.project['id'],self.body(),principal=self.c.principal);self.assertTrue(exact);self.assertEqual(replay['snapshot'],result['snapshot'])
        with self.assertRaisesRegex(WorkflowError,'NO_AUTOMATIC_REPLAY'):self.process(value)
    def test_unknown_write_requires_new_explicit_read_only_reconciliation_not_a_second_put(self):
        self.storage.lose_reply=True;old=self.process(self.create());self.assertEqual(old['status'],'outcome_unknown');self.assertEqual(self.storage.puts,1)
        with self.assertRaisesRegex(WorkflowError,'EXISTING_REVIEW_REQUIRED'):self.create(self.body(request_key='explicit-media-new-key-no-review'))
        self.storage.lose_reply=False;value=self.create(self.body(reconcile_delivery_id=old['delivery_id'],request_key='explicit-media-read-only-recovery-key'))
        result=self.process(value);self.assertEqual(result['status'],'succeeded',result['failure_code']);self.assertEqual(self.storage.puts,1)
        self.assertTrue(all(o['operation']!='put_object' for o in result['operations']));self.assertEqual(self.service.get(self.c.project['id'],old['delivery_id'])['status'],'outcome_unknown')
    def test_consent_expiry_after_known_write_keeps_fact_and_blocks_more_reads_or_signing(self):
        self.storage.after_put=lambda:self.c.clock.__setitem__(0,self.c.clock[0]+timedelta(seconds=61))
        value=self.create(self.body(valid_for_seconds=60));result=self.process(value);self.assertEqual(result['status'],'outcome_unknown')
        self.assertEqual(len(self.storage.calls),2);self.assertEqual(result['operations'][-1]['status'],'response_received');self.assertIsNone(result['lease_ref'])
    def test_current_project_edit_stops_before_storage(self):
        value=self.create()
        with self.c.store.transaction() as con:
            document=copy.deepcopy(self.c.project['document']);document['prompt']='Explicit later edit'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document),self.c.project['id']));self.c.store.version(con,self.c.project['id'])
        result=self.process(value);self.assertEqual(result['status'],'failed');self.assertEqual(self.storage.calls,[])
    def test_final_byte_corruption_stops_before_storage(self):
        value=self.create()
        with self.c.store.transaction() as con:_,_,path=self.c.service.revalidate(con,self.c.service.row(con,self.c.project['id'],self.publication['publication_id']))
        path.write_bytes(b'EXPLICIT LATER CORRUPTION OF OWNED TEST FIXTURE')
        result=self.process(value);self.assertEqual(result['status'],'failed');self.assertEqual(self.storage.calls,[])
    def test_owner_grant_revocation_stops_before_storage(self):
        value=self.create();self.c.service.revoke(self.c.project['id'],self.publication['publication_id'],Action(expected_snapshot_sha256=self.publication['snapshot_sha256']),principal=self.c.principal)
        result=self.process(value);self.assertEqual(result['status'],'failed');self.assertEqual(self.storage.calls,[])
    def test_private_consumer_resolves_only_exact_mock_scope_and_current_owner_without_new_wire(self):
        result=self.process(self.create());self.assertEqual(result['status'],'succeeded',result['failure_code']);before=list(self.storage.calls)
        lease=self.service.resolve_for_consumer(self.c.project['id'],result['delivery_id'],publication_snapshot_sha256=self.publication['snapshot_sha256'],consumer_mock=True)
        self.assertEqual(lease.object.scope.final_sha256,self.publication['snapshot']['final_sha256']);self.assertNotIn('X-Amz-',repr(lease));self.assertEqual(self.storage.calls,before)
        for changes in ({'consumer_mock':False},{'consumer_mock':1},{'publication_snapshot_sha256':'f'*64}):
            with self.assertRaisesRegex(WorkflowError,'CONSUMER_BINDING_CHANGED'):
                self.service.resolve_for_consumer(self.c.project['id'],result['delivery_id'],**{'publication_snapshot_sha256':self.publication['snapshot_sha256'],'consumer_mock':True,**changes})
        self.c.service.revoke(self.c.project['id'],self.publication['publication_id'],Action(expected_snapshot_sha256=self.publication['snapshot_sha256']),principal=self.c.principal)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Reject before decrypt')):
            with self.assertRaises(WorkflowError):self.service.resolve_for_consumer(self.c.project['id'],result['delivery_id'],publication_snapshot_sha256=self.publication['snapshot_sha256'],consumer_mock=True)
        self.assertEqual(self.storage.calls,before);self.assertEqual(self.service.get(self.c.project['id'],result['delivery_id']),result)
    def test_private_lease_corruption_and_elapsed_url_are_rejected_without_network(self):
        result=self.process(self.create(self.body(ttl_seconds=60)));self.assertEqual(result['status'],'succeeded',result['failure_code'])
        args={'publication_snapshot_sha256':self.publication['snapshot_sha256'],'consumer_mock':True,'minimum_valid_seconds':1}
        path=self.directory/(result['lease_ref']+'.dpapi');raw=path.read_bytes();path.write_bytes(raw+b'EXPLICIT FIXTURE CORRUPTION')
        with self.assertRaisesRegex(WorkflowError,'PRIVATE_LEASE_UNAVAILABLE'):self.service.resolve_for_consumer(self.c.project['id'],result['delivery_id'],**args)
        path.write_bytes(raw);self.c.clock[0]+=timedelta(seconds=61)
        with self.assertRaisesRegex(WorkflowError,'PRIVATE_LEASE_UNAVAILABLE'):self.service.resolve_for_consumer(self.c.project['id'],result['delivery_id'],**args)
        self.assertEqual(self.storage.puts,1)
    def test_rehashed_snapshot_secret_fields_or_removed_delivery_cost_evidence_are_rejected(self):
        result=self.process(self.create());self.assertEqual(result['status'],'succeeded',result['failure_code'])
        with self.c.store.transaction() as con:con.execute('DELETE FROM native_publishing_media_operations WHERE delivery_id=?',(result['delivery_id'],))
        with self.assertRaisesRegex(WorkflowError,'COST_EVIDENCE_CHANGED'):self.service.get(self.c.project['id'],result['delivery_id'])
        snapshot=copy.deepcopy(result['snapshot']);snapshot['url']='EXPLICIT PRIVATE URL FIELD FIXTURE'
        with self.c.store.transaction() as con:con.execute('UPDATE native_publishing_media_deliveries SET snapshot_json=?,snapshot_sha256=? WHERE delivery_id=?',(json.dumps(snapshot),digest(snapshot),result['delivery_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.service.get(self.c.project['id'],result['delivery_id'])
    def test_factory_disabled_and_explicit_ack_role_config_and_mocks_are_separate(self):
        for change in ({'acknowledged_external_media_delivery':1},{'url':'https://foreign.invalid'},{'max_external_cost_vnd':True},{'ttl_seconds':True}):
            with self.assertRaises(ValueError):Create.model_validate({**self.body().model_dump(mode='json'),**change})
        disabled=NativeMediaDeliveryFactory(self.profile,self.c.root,self.c.workspace,directory=self.directory,wire=self.storage.wire)
        service=NativePublishingMediaDelivery(self.c.service,factory=disabled)
        value,_=service.create(self.c.project['id'],self.body(expected_configuration_sha256=disabled.sha256),principal=self.c.principal)
        self.assertEqual(value['status'],'not_configured');self.assertEqual(self.storage.calls,[])
        with self.assertRaises(WorkflowError):self.create(self.body(expected_configuration_sha256='f'*64))
        self.factory.enabled=False
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.factory.public()
    def test_restart_marks_unknown_without_loading_credentials_or_replaying_storage(self):
        value=self.create()
        with self.c.store.transaction() as con:con.execute("UPDATE native_publishing_media_deliveries SET status='running' WHERE delivery_id=?",(value['delivery_id'],))
        cold=NativePublishingMediaDelivery(self.c.service);self.assertEqual(cold.recover(),1);self.assertEqual(self.storage.calls,[])
        result=cold.get(self.c.project['id'],value['delivery_id']);self.assertEqual(result['status'],'outcome_unknown')
        ref=self.create(self.body(reconcile_delivery_id=value['delivery_id'],request_key='explicit-missing-object-read-only-recovery'))
        recovered=self.process(ref);self.assertEqual(recovered['status'],'failed');self.assertEqual(self.storage.puts,0)
    def test_restart_settles_original_known_response_after_cost_receipt_interruption_without_replay(self):
        value=self.create();settle=self.service.costs.settle
        def interrupted(identifier,**fields):
            with self.c.store.transaction() as con:operation=con.execute('SELECT operation FROM native_cost_operations WHERE id=?',(identifier,)).fetchone()[0]
            if operation.endswith('_put_object'):raise RuntimeError('Explicit write cost receipt outage')
            return settle(identifier,**fields)
        with patch.object(self.service.costs,'settle',side_effect=interrupted):
            with self.assertRaisesRegex(WorkflowError,'COST_EVIDENCE_CHANGED'):self.process(value)
        before=list(self.storage.calls);self.assertEqual(self.storage.puts,1)
        cold=NativePublishingMediaDelivery(self.c.service)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No recovery decrypt')):self.assertEqual(cold.recover(),0)
        result=cold.get(self.c.project['id'],value['delivery_id']);self.assertEqual(result['status'],'outcome_unknown')
        self.assertEqual(result['operations'][-1]['status'],'response_received');self.assertEqual(self.storage.calls,before)
        recovery=self.create(self.body(reconcile_delivery_id=value['delivery_id'],request_key='explicit-after-known-write-cost-recovery'))
        self.assertEqual(self.process(recovery)['status'],'succeeded');self.assertEqual(self.storage.puts,1)
    def test_rehashed_cost_source_or_publication_authority_claim_is_rejected(self):
        result=self.process(self.create());self.assertEqual(result['status'],'succeeded',result['failure_code'])
        with self.c.store.transaction() as con:con.execute('UPDATE native_publishing_media_operations SET request_sha256=? WHERE operation_id=?',('f'*64,result['operations'][0]['operation_id']))
        with self.assertRaisesRegex(WorkflowError,'COST_EVIDENCE_CHANGED'):self.service.get(self.c.project['id'],result['delivery_id'])
        snapshot=copy.deepcopy(result['snapshot']);snapshot['publishing_authority']=True
        with self.c.store.transaction() as con:con.execute('UPDATE native_publishing_media_deliveries SET snapshot_json=?,snapshot_sha256=? WHERE delivery_id=?',(json.dumps(snapshot),digest(snapshot),result['delivery_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.service.get(self.c.project['id'],result['delivery_id'])
    def test_cancel_before_send_allows_new_request_and_cancels_no_remote_resource(self):
        value=self.create();cancelled=self.service.cancel(self.c.project['id'],value['delivery_id'],principal=self.c.principal)
        self.assertEqual(cancelled['status'],'cancelled');self.assertEqual(self.storage.calls,[])
        replacement=self.create(self.body(request_key='explicit-replacement-after-unsent-cancel'));self.assertNotEqual(value['delivery_id'],replacement['delivery_id'])
    def test_public_backup_and_cold_history_exclude_signed_url_and_private_lease(self):
        result=self.process(self.create());self.assertEqual(result['status'],'succeeded',result['failure_code'])
        self.c.service.cancel(self.c.project['id'],self.publication['publication_id'],Action(expected_snapshot_sha256=self.publication['snapshot_sha256']),principal=self.c.principal)
        receipt=create_backup(settings(self.c.root),self.c.folder/'public-backup.zip');restored=self.c.folder/'restored-media';restore_backup(self.c.folder/'public-backup.zip',restored,expected_sha256=receipt['sha256'])
        store=Store(restored);accounts=NativeOfficialAccounts(store,workspace_id=self.c.workspace);pub=NativePublications(store,self.c.caps,workspace_id=self.c.workspace)
        journal=NativeOfficialPublications(store,pub,accounts);cold=NativePublishingMediaDelivery(journal)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No cold decrypt')):
            self.assertEqual(cold.get(self.c.project['id'],result['delivery_id']),result)
        self.assertFalse((restored/'private').exists());self.assertEqual(database_status(store.db)['active_operations'],0)
    def test_scoped_storage_credential_is_dpapi_protected_and_default_startup_never_decrypts(self):
        path=self.c.folder/'private'/'s3-credential.dpapi';expiry=self.c.clock[0]+timedelta(hours=1)
        receipt=save_credential(path,self.c.root,{'workspace_id':self.c.workspace,'storage_profile_sha256':self.profile.sha256,'credential_alias':self.profile.credential_alias,
            'expires_at':expiry.isoformat(),'access_key':'EXPLICIT-S3-FIXTURE-ACCESS-KEY','secret_key':'EXPLICIT-S3-FIXTURE-SECRET-KEY'})
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No startup decrypt')):
            factory=NativeMediaDeliveryFactory(self.profile,self.c.root,self.c.workspace,directory=self.directory,credential_file=path,credential_expires_at=expiry)
            self.assertEqual(factory.public()['status'],'NOT_CONFIGURED');self.assertIsNone(factory.wire.clients)
        self.assertNotIn('EXPLICIT-S3-FIXTURE',json.dumps(receipt));self.assertNotIn(b'EXPLICIT-S3-FIXTURE',path.read_bytes())
        other=NativeMediaDeliveryFactory(self.profile,self.c.folder/'separate-native-state',self.c.workspace,directory=self.directory,wire=self.storage.wire)
        current=NativeMediaDeliveryFactory(self.profile,self.c.root,self.c.workspace,directory=self.directory,wire=self.storage.wire)
        self.assertNotEqual(other.sha256,current.sha256)
