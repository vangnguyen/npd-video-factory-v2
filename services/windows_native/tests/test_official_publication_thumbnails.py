"""Real local rendered PNG and synthetic rights/accounts/decisions/wire only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
import hashlib,json,unittest
from unittest.mock import patch
import httpx
from services.windows_native.tests import test_publication_thumbnail as fixture
from services.windows_native.tests import test_official_publications as official_fixture
from services.windows_native.publications import NativePublications
from services.windows_native.official_accounts import NativeOfficialAccounts,Verify
from services.windows_native.official_account_registry import Account,AccountFactory
from services.windows_native.official_publication_registry import PublishingFactory
from services.windows_native.official_publication_models import Profile,Gates,Create,Approve,Action,Renew
from services.windows_native.official_publications import NativeOfficialPublications
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_thumbnails import ThumbnailTicket
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.store import Store
from app.analytics_official import AnalyticsOAuthCredential,YT_READ,YT_ANALYTICS
from app.publishing_credentials import PublishingOAuthCredential,UPLOAD,READ
from app.publishing_models import PublishingTargetBinding
from app.publishing_wire import OfficialHTTPClient
from app.youtube_upload import UNIT,VideoObservation


class OfficialThumbnailWorkerTests(unittest.TestCase):
    runtime=fixture.NativePublicationThumbnailTests.runtime
    bridge=fixture.NativePublicationThumbnailTests.bridge
    request=fixture.NativePublicationThumbnailTests.request
    response=fixture.NativePublicationThumbnailTests.response
    payload=fixture.NativePublicationThumbnailTests.payload
    choose=fixture.NativePublicationThumbnailTests.choose
    change_owner=fixture.NativePublicationThumbnailTests.change_owner
    review=fixture.NativePublicationThumbnailTests.review
    grant=fixture.NativePublicationThumbnailTests.grant
    revoke=fixture.NativePublicationThumbnailTests.revoke
    intent=fixture.NativePublicationThumbnailTests.intent
    create_publication=fixture.NativePublicationThumbnailTests.create_publication
    approve_publication=fixture.NativePublicationThumbnailTests.approve_publication
    @classmethod
    def setUpClass(cls):fixture.NativePublicationThumbnailTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.NativePublicationThumbnailTests.tearDownClass.__func__(cls)
    def setUp(self):
        fixture.NativePublicationThumbnailTests.setUp(self);self.folder=self.root.parent;self.wire=[];self.ack=0;self.mode=None
        caps=json.loads(official_fixture.CAPABILITIES.read_bytes());caps['platforms']['youtube']['verification_state']='owner_verified_for_live'
        caps['notice']='EXPLICIT SYNTHETIC PLATFORM FIXTURE — NOT OWNER VERIFICATION';self.caps=self.folder/'explicit-platform.json';self.caps.write_text(json.dumps(caps),encoding='utf-8')
        self.publications=NativePublications(self.store,self.caps,workspace_id=self.workspace,clock=lambda:self.clock[0]);self.publications.bind_render_thumbnail_rights(self.rights)
        self.exception=self.grant();parent=self.create_publication();self.approve_publication(parent);self.parent=self.publications.process();assert self.parent['status']=='dry_run_succeeded'
        self.target=PublishingTargetBinding(workspace_id=self.workspace,profile_id='ppf_official_thumbnail_fixture',profile_version=1,platform='youtube',provider_key='youtube-data-api-publishing',target_account_id='UC_EXPLICIT_THUMBNAIL_FIXTURE',credential_binding_sha256='a'*64)
        account=Account(account_ref='npac_'+'b'*32,target=self.target,credential_alias='explicit-thumbnail-account',token_file=str(self.folder/'secrets'/'explicit.dpapi'),read_enabled=True)
        read=AnalyticsOAuthCredential(self.target,self.clock[0]+timedelta(hours=1),frozenset({YT_READ,YT_ANALYTICS}),'EXPLICIT-READ-THUMBNAIL-FIXTURE-0123456789')
        self.account_factory=AccountFactory(account,self.root,self.workspace,owner_read_enabled=True,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'items':[{'id':self.target.target_account_id}]})),resolver=lambda _:read)
        self.accounts=NativeOfficialAccounts(self.store,workspace_id=self.workspace,factories={account.account_ref:self.account_factory},clock=lambda:self.clock[0])
        self.accounts.create(self.project['id'],account.account_ref,Verify(revision=self.project['revision'],expected_configuration_sha256=self.account_factory.sha256,acknowledged_read_only=True,request_key='explicit-thumbnail-account-proof'),actor=self.principal.token_id);self.account_check=self.accounts.process()
        self.credential=PublishingOAuthCredential(self.target,self.clock[0]+timedelta(hours=1),frozenset({UPLOAD,READ}),'EXPLICIT-UPLOAD-THUMBNAIL-FIXTURE-0123456789')
        self.profile=Profile(target=self.target,category_id='27',made_for_kids=False,contains_synthetic_media=True,chunk_size=UNIT)
        self.client=OfficialHTTPClient('youtube',transport=httpx.MockTransport(self.publish_response))
        self.publish_factory=PublishingFactory(self.profile,self.root,self.workspace,gates=Gates(publish_enabled=True,external_execution_enabled=True,owner_gate_enabled=True),client=self.client,resolver=lambda _:self.credential)
        self.journal=NativeOfficialPublications(self.store,self.publications,self.accounts,factories={self.target.profile_id:self.publish_factory},identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])
        self.sessions=SessionVault(self.journal,self.folder/'private-upload-sessions');self.worker=NativeOfficialPublicationWorker(self.journal,self.sessions)
    def tearDown(self):fixture.NativePublicationThumbnailTests.tearDown(self)
    def publish_response(self,request):
        self.wire.append({'method':request.method,'path':request.url.path,'bytes':len(request.content),'body_sha256':hashlib.sha256(request.content).hexdigest()})
        if request.url.path=='/youtube/v3/channels':return httpx.Response(200,json={'items':[{'id':self.target.target_account_id}]})
        if request.url.path=='/upload/youtube/v3/thumbnails/set':
            self.assertEqual(hashlib.sha256(request.content).hexdigest(),self.selected['snapshot']['image']['sha256']);self.assertEqual(request.url.params['videoId'],'FIXTURE0001')
            if self.mode=='timeout':raise httpx.ReadTimeout('EXPLICIT PRIVATE RESPONSE LOSS',request=request)
            if self.mode=='429':return httpx.Response(429,headers={'Retry-After':'60'},json={'error':{'message':'EXPLICIT'}})
            if self.mode=='expire':self.clock[0]+=timedelta(seconds=901)
            if self.mode=='owner':self.change_owner(enabled=False)
            if self.mode=='revoke':self.journal.revoke(self.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256']),principal=self.principal)
            if self.mode=='edit':self.store.save(self.project['id'],self.project['revision'],prompt='EXPLICIT LATE EDIT')
            if self.mode=='malformed':return httpx.Response(200,json={'kind':'youtube#thumbnailSetResponse','items':[]})
            return httpx.Response(200,json={'kind':'youtube#thumbnailSetResponse','items':[{'default':{'url':'https://i.ytimg.com/vi/FIXTURE0001/default.jpg'}}]})
        if request.method=='POST':return httpx.Response(200,headers={'Location':'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=EXPLICIT-PRIVATE-THUMBNAIL-FIXTURE'})
        if request.method=='PUT':
            self.ack+=len(request.content)
            if self.ack==self.value['snapshot']['final_bytes']:return httpx.Response(200,json={'id':'FIXTURE0001'})
            return httpx.Response(308,headers={'Range':f'bytes=0-{self.ack-1}'})
        if request.url.path=='/youtube/v3/videos':return httpx.Response(200,json={'items':[{'id':'FIXTURE0001','status':{'uploadStatus':'processed','privacyStatus':'private'},'processingDetails':{'processingStatus':'succeeded'}}]})
        raise AssertionError('Unexpected explicit fixture endpoint')
    def body(self,**changes):
        return Create.model_validate({'revision':self.project['revision'],'dry_run_publication_id':self.parent['publication_id'],'expected_dry_run_snapshot_sha256':self.parent['snapshot_sha256'],
            'account_check_id':self.account_check['check_id'],'profile_id':self.target.profile_id,'expected_configuration_sha256':self.publish_factory.sha256,'request_key':'explicit-official-thumbnail-key',**changes})
    def create_official(self,**changes):
        self.value=self.journal.create(self.project['id'],self.body(**changes),principal=self.principal)[0]
        self.journal.approve(self.project['id'],self.value['publication_id'],Approve(expected_snapshot_sha256=self.value['snapshot_sha256'],acknowledged_official_publication=True),principal=self.principal)
        return self.value
    def state(self):return self.journal.state(self.project['id'],self.value['publication_id'])
    def poll(self):return self.worker.poll_processing(self.project['id'],self.value['publication_id'],self.state()['dispatch']['version'])
    def upload(self):
        self.create_official();self.worker.step(self.project['id'],self.value['publication_id'],self.state()['dispatch']['version'])
        for _ in range(20):
            if self.state()['dispatch']['phase']=='uploaded':return
            self.worker.step(self.project['id'],self.value['publication_id'],self.state()['dispatch']['version'])
        raise AssertionError('Bounded fixture upload')
    def posts(self):return [r for r in self.wire if r['path']=='/upload/youtube/v3/thumbnails/set']
    def test_original_thumbnail_is_sent_once_and_processing_receipt_requires_separate_next_poll(self):
        original=self.store.get(self.project['id']);self.upload();before=self.state();self.assertEqual(before['thumbnail_stage']['status'],'not_started');self.assertIsNone(before['receipt'])
        after=self.poll();self.assertEqual(after['status'],'queued');self.assertEqual(after['thumbnail_stage']['status'],'response_received');self.assertIsNone(after['receipt'])
        self.assertEqual(len(self.posts()),1);done=self.poll();self.assertEqual(done['status'],'completed');self.assertTrue(done['mock_publication_complete']);self.assertFalse(done['published'])
        self.assertEqual(len(self.posts()),1);self.assertEqual(self.store.get(self.project['id']),original);self.assertFalse(done['thumbnail_stage']['remote_image_bytes_verified'])
        costs=[r for r in self.worker.costs.summary(self.project['id'])['records'] if r['operation'].startswith('publish_thumbnail_set.')]
        self.assertEqual(len(costs),1);self.assertEqual(costs[0]['status'],'response_received');self.assertIsNone(costs[0]['actual_cost']);self.assertFalse(costs[0]['external_call']);self.assertFalse(costs[0]['paid'])
        self.assertNotIn(self.credential.token,json.dumps(done));self.assertNotIn('upload_id',json.dumps(done))
    def test_processing_cannot_skip_requested_thumbnail_even_through_direct_journal_call(self):
        self.upload()
        with self.assertRaisesRegex(WorkflowError,'THUMBNAIL_CONFIRMATION_REQUIRED'):
            self.journal.record_processing(self.project['id'],self.value['publication_id'],self.state()['dispatch']['version'],VideoObservation('processed','private',None),'a'*64)
        self.assertIsNone(self.journal.get(self.project['id'],self.value['publication_id'])['receipt']);self.assertEqual(self.posts(),[])
    def test_timeout_has_no_replay_after_new_worker_or_renewal_and_preserves_uploaded_video(self):
        self.upload();before=self.state()['dispatch'];self.mode='timeout'
        with self.assertRaises(WorkflowError):self.poll()
        state=self.state();self.assertEqual(state['thumbnail_stage']['status'],'outcome_unknown');self.assertEqual(state['dispatch']['remote_post_id'],before['remote_post_id']);self.assertEqual(state['dispatch']['acknowledged_bytes'],before['total_bytes'])
        worker=NativeOfficialPublicationWorker(self.journal,self.sessions);worker.recover();calls=len(self.wire)
        with self.assertRaises(WorkflowError):worker.poll_processing(self.project['id'],self.value['publication_id'],state['dispatch']['version'])
        with self.assertRaisesRegex(WorkflowError,'THUMBNAIL_UNKNOWN_REVIEW_REQUIRED'):
            self.journal.renew(self.project['id'],self.value['publication_id'],Renew(expected_snapshot_sha256=self.value['snapshot_sha256'],expected_dispatch_version=state['dispatch']['version'],acknowledged_official_publication=True,request_key='explicit-unknown-renewal'),principal=self.principal)
        self.assertEqual(len(self.wire),calls);self.assertEqual(len(self.posts()),1)
    def test_known_invalid_response_is_retained_unconfirmed_without_replay(self):
        self.upload();self.mode='malformed'
        with self.assertRaises(WorkflowError):self.poll()
        state=self.state();self.assertEqual(state['thumbnail_stage']['status'],'outcome_unknown');self.assertRegex(state['thumbnail_stage']['response_sha256'],r'^[a-f0-9]{64}$');self.assertIsNone(state['receipt'])
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.posts()),1)
    def test_rate_limited_thumbnail_post_is_not_replayed_or_claimed_complete(self):
        self.upload();self.mode='429'
        with self.assertRaises(WorkflowError):self.poll()
        state=self.state();self.assertEqual(state['thumbnail_stage']['status'],'outcome_unknown');self.assertRegex(state['thumbnail_stage']['response_sha256'],r'^[a-f0-9]{64}$');self.assertIsNone(state['receipt'])
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.posts()),1)
    def test_one_concurrent_claim_is_durable_and_restart_marks_unknown_without_credentials(self):
        self.upload();version=self.state()['dispatch']['version']
        def begin(_):
            try:return self.journal.thumbnails.begin(self.project['id'],self.value['publication_id'],version)
            except WorkflowError as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(begin,range(2)))
        self.assertEqual(sum(type(v) is ThumbnailTicket for v in results),1);self.assertEqual(self.posts(),[])
        self.journal.revoke(self.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256']),principal=self.principal)
        facts=database_status(self.store.db);self.assertEqual(facts['counts']['native_official_publish_thumbnails'],1);self.assertEqual(facts['active_operations'],1)
        with self.assertRaisesRegex(WorkflowError,'BACKUP_SOURCE_HAS_ACTIVE_OPERATIONS'):create_backup(self.config,self.folder/'pending-stage.zip')
        with patch.object(self.publish_factory,'credential',side_effect=AssertionError('NO RECOVERY KEY')):
            self.assertEqual(self.worker.recover()['recovered_thumbnail_intents'],1);self.assertEqual(self.worker.recover()['recovered_thumbnail_intents'],0)
        self.assertEqual(self.state()['thumbnail_stage']['status'],'outcome_unknown');self.assertIsNone(self.state()['receipt'])
        self.assertEqual(database_status(self.store.db)['active_operations'],0)
    def test_current_thumbnail_exception_revoked_before_claim_sends_no_provider_request(self):
        self.upload();self.revoke(self.exception);before=len(self.wire)
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.wire),before);self.assertEqual(self.posts(),[]);self.assertEqual(self.state()['thumbnail_stage']['status'],'not_started')
    def test_original_png_corruption_or_stale_version_never_sends_thumbnail(self):
        self.upload();before=len(self.wire)
        with self.assertRaises(WorkflowError):self.worker.poll_processing(self.project['id'],self.value['publication_id'],self.state()['dispatch']['version']+1)
        path=self.root/'jobs'/self.job['id']/self.frame['evidence_frame_reference'];data=path.read_bytes();path.write_bytes(b'EXPLICIT CORRUPTED PNG')
        try:
            with self.assertRaises(WorkflowError):self.poll()
        finally:path.write_bytes(data)
        self.assertEqual(len(self.wire),before);self.assertEqual(self.posts(),[])
    def test_known_response_after_expired_consent_is_preserved_without_receipt_or_resend(self):
        self.upload();self.mode='expire';done=self.poll();self.assertEqual(done['status'],'review_required');self.assertEqual(done['thumbnail_stage']['status'],'response_received');self.assertIsNone(done['receipt'])
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.posts()),1)
    def test_known_response_after_owner_revocation_is_preserved_without_authority(self):
        self.upload();self.mode='owner';done=self.poll();self.assertEqual(done['status'],'review_required');self.assertEqual(done['thumbnail_stage']['status'],'response_received');self.assertFalse(done['published'])
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.posts()),1)
    def test_known_response_after_explicit_publish_revocation_does_not_restore_a_grant(self):
        self.upload();self.mode='revoke';done=self.poll();self.assertEqual(done['status'],'review_required');self.assertEqual(done['thumbnail_stage']['status'],'response_received');self.assertIsNone(done['receipt'])
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.posts()),1)
    def test_late_response_cannot_approve_a_new_canonical_document(self):
        self.upload();original=self.value['snapshot'];self.mode='edit';done=self.poll();self.assertEqual(done['status'],'review_required');self.assertEqual(done['snapshot'],original);self.assertIsNone(done['receipt'])
        with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(len(self.posts()),1)
    def test_owner_revoked_by_final_key_read_is_fenced_before_the_thumbnail_post(self):
        self.upload();original=self.publish_factory.credential;reads=[0]
        def credential(**kwargs):
            resolved=original(**kwargs);reads[0]+=1
            if reads[0]==5:self.change_owner(enabled=False)
            return resolved
        with patch.object(self.publish_factory,'credential',side_effect=credential):
            with self.assertRaises(WorkflowError):self.poll()
        self.assertEqual(reads[0],5);self.assertEqual(self.posts(),[]);self.assertIsNone(self.state()['receipt'])
    def test_owner_metadata_override_cannot_inherit_omitted_or_foreign_thumbnail_authority(self):
        legacy=self.create_publication(metadata={'title':'Explicit legacy parent'},request_key='explicit-legacy-parent');self.approve_publication(legacy);self.parent=self.publications.process()
        original=self.selected['thumbnail_asset_id'];value=self.create_official(metadata={'title':'Explicit owner override','thumbnail_asset_id':original})
        self.assertEqual(value['snapshot']['thumbnail']['thumbnail_asset_id'],original);self.assertEqual(value['snapshot']['metadata_source'],'explicit_owner_request')
        self.journal.revoke(self.project['id'],value['publication_id'],Action(expected_snapshot_sha256=value['snapshot_sha256']),principal=self.principal)
        with self.assertRaises(WorkflowError):self.journal.create(self.project['id'],self.body(metadata={'title':'Foreign thumbnail','thumbnail_asset_id':'ast_rthumb_'+'f'*32},request_key='explicit-foreign-thumbnail'),principal=self.principal)
    def test_keyless_backup_recovery_keeps_original_stage_receipt_png_and_journals(self):
        self.upload();self.poll();done=self.poll();png=self.root/'jobs'/self.job['id']/self.frame['evidence_frame_reference'];original=file_sha(png)
        with self.store.transaction() as con:expected=[dict(r) for r in con.execute('SELECT * FROM native_official_publish_thumbnails')]
        backup=self.folder/'public-stage.zip';proof=create_backup(self.config,backup);recovered=self.folder/'restored';restore_backup(backup,recovered,expected_sha256=proof['sha256'])
        self.assertEqual(proof['database_status']['workflow.sqlite3']['counts']['native_official_publish_thumbnails'],1)
        store=Store(recovered);publications=NativePublications(store,official_fixture.CAPABILITIES,workspace_id=self.workspace);accounts=NativeOfficialAccounts(store,workspace_id=self.workspace)
        journal=NativeOfficialPublications(store,publications,accounts)
        self.assertEqual(journal.get(self.project['id'],self.value['publication_id']),done);self.assertEqual(file_sha(recovered/'jobs'/self.job['id']/self.frame['evidence_frame_reference']),original)
        with store.transaction() as con:self.assertEqual([dict(r) for r in con.execute('SELECT * FROM native_official_publish_thumbnails')],expected)
        self.assertEqual(journal.recover()['recovered_thumbnail_intents'],0)
    def test_changed_original_image_response_or_remote_binding_cannot_support_a_receipt(self):
        self.upload();self.poll();done=self.poll()
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_official_publish_thumbnails').fetchone();result=json.loads(row['result_json']);result['original_image']['sha256']='a'*64
            con.execute('UPDATE native_official_publish_thumbnails SET result_json=?,result_sha256=?',(json.dumps(result),digest(result)))
        with self.assertRaisesRegex(WorkflowError,'RECEIPT_CHANGED'):self.journal.get(self.project['id'],self.value['publication_id'])
        self.assertTrue(done['mock_publication_complete'])


if __name__=='__main__':unittest.main()
