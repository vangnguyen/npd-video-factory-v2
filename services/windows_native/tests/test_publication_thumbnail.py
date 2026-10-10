"""Real local PNG/final QC with synthetic source rights and human decisions only."""
import copy,unittest,uuid
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests import test_render_thumbnail_rights as fixture
from services.windows_native.tests import test_render_vision as render_fixture
from services.windows_native.tests import test_publications as publication_fixture
from services.windows_native.publications import NativePublications
from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
from services.windows_native.publication_thumbnail import NativePublicationThumbnailBinding
from services.windows_native.render_thumbnail_rights import NativeRenderThumbnailRights
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.costs import CostLedger
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.server import Runner
from services.windows_native.pipeline import Pipeline


class NativePublicationThumbnailTests(unittest.TestCase):
    runtime=fixture.NativeRenderThumbnailRightsTests.runtime
    bridge=fixture.NativeRenderThumbnailRightsTests.bridge
    request=fixture.NativeRenderThumbnailRightsTests.request
    response=fixture.NativeRenderThumbnailRightsTests.response
    payload=fixture.NativeRenderThumbnailRightsTests.payload
    choose=fixture.NativeRenderThumbnailRightsTests.choose
    change_owner=fixture.NativeRenderThumbnailRightsTests.change_owner
    review=fixture.NativeRenderThumbnailRightsTests.review
    grant=fixture.NativeRenderThumbnailRightsTests.grant
    revoke=fixture.NativeRenderThumbnailRightsTests.revoke

    @classmethod
    def setUpClass(cls):
        cls.original=render_fixture.source_fixture.NativeSourceRenderTests('test_real_source_worker_qc_checkpoint_keeps_media_immutable_and_requires_final_review')
        cls.original.setUp();f=cls.original
        # Explicit owned test-source declaration precedes analysis, timeline and render.
        # No accepted/source artifact or rendered snapshot is rewritten to pass a gate.
        f.asset.update(rights_status='owned',license='explicit-synthetic-owned-thumbnail-publication-fixture')
        f.real_source();f.config.secret_file=f.root/'absent-key';f.config.assemblyai_secret_file=f.root/'absent-asr'
        CostLedger(f.store).set_budget(f.project['id'],f.project['revision'],'1000');f.project=f.store.get(f.project['id'])
        manager=PreviewManager(f.config,f.store)
        try:
            manager.generate(f.project['id'],f.project['revision']);assert f.wait(manager)['status']=='READY'
        finally:manager.close()
        f.project=f.store.approve(f.project['id'],f.project['revision'],'EXPLICIT SYNTHETIC SOURCE REVIEW — NOT OWNER UAT',True)
        job=f.store.enqueue(f.project['id'],f.project['revision'],'render',uuid.uuid4().hex)
        assert Runner(f.store,Pipeline(f.config)).run_one();cls.original_job=f.store.get_job(job['id']);assert cls.original_job['status']=='succeeded'

    @classmethod
    def tearDownClass(cls):cls.original.tearDown()
    def setUp(self):
        fixture.NativeRenderThumbnailRightsTests.setUp(self)
        self.store.review_render(self.job['id'],self.job['revision'],'EXPLICIT SYNTHETIC FINAL REVIEW — NOT OWNER UAT',True,'approve')
        self.job=self.store.get_job(self.job['id']);self.project=self.store.get(self.project['id'])
        self.publications=NativePublications(self.store,publication_fixture.CAPABILITIES,workspace_id=self.workspace,clock=lambda:self.clock[0])
        self.publications.bind_render_thumbnail_rights(self.rights)
    def tearDown(self):fixture.NativeRenderThumbnailRightsTests.tearDown(self)
    def intent(self,**changes):
        return NativePublicationCreate.model_validate({'revision':self.project['revision'],'final_job_id':self.job['id'],'platform':'youtube',
            'metadata':{'title':'EXPLICIT SYNTHETIC THUMBNAIL DRY RUN','privacy':'private','thumbnail_asset_id':self.selected['thumbnail_asset_id']},
            'request_key':'explicit-publication-thumbnail-key',**changes})
    def create_publication(self,**changes):return self.publications.create(self.project['id'],self.intent(**changes),actor='EXPLICIT SYNTHETIC EDITOR')[0]
    def approve_publication(self,row):
        return self.publications.approve(self.project['id'],row['publication_id'],NativePublishApproval(expected_fingerprint=row['request_fingerprint'],
            expected_artifact_sha256=row['snapshot']['final_sha256'],acknowledged=True),actor='EXPLICIT SYNTHETIC PUBLISH REVIEW — NOT OWNER UAT')

    def test_missing_exception_blocks_but_optional_thumbnail_preserves_legacy_validation_shape(self):
        blocked=self.create_publication();v=blocked['snapshot']['validation']
        self.assertEqual(blocked['status'],'blocked');self.assertEqual(v['rights']['status'],'passed')
        self.assertEqual(v['attention'],['NATIVE_PUBLICATION_THUMBNAIL_CURRENT_OWNER_EXCEPTION_REQUIRED']);self.assertNotIn('thumbnail',v)
        legacy=self.create_publication(metadata={'title':'Legacy explicit dry run'},request_key='explicit-publication-without-thumbnail')
        self.assertEqual(legacy['status'],'awaiting_publish_approval');self.assertNotIn('thumbnail',legacy['snapshot']['validation'])
        unbound=NativePublications(self.store,publication_fixture.CAPABILITIES)
        other=unbound.create(self.project['id'],self.intent(request_key='explicit-unbound-thumbnail-key'),actor='fixture')[0]
        self.assertEqual(other['snapshot']['validation']['attention'],['NATIVE_THUMBNAIL_PUBLICATION_BINDING_NOT_CONFIGURED'])

    def test_finite_exception_and_separate_final_publish_reviews_enable_only_idempotent_dry_run(self):
        project=self.store.get(self.project['id']);job=self.store.get_job(self.job['id']);cost=self.service.costs.summary(self.project['id'])
        path=self.root/'jobs'/self.job['id']/self.frame['evidence_frame_reference'];original=file_sha(path);grant=self.grant()
        with patch.object(self.vault,'key',side_effect=AssertionError('NO PROVIDER KEY')):
            row=self.create_publication();self.assertEqual(row['status'],'awaiting_publish_approval')
            proof=row['snapshot']['validation']['thumbnail'];self.assertEqual(proof['owner_exception']['override_id'],grant['override_id'])
            self.assertEqual(proof['image']['sha256'],original);self.assertEqual(proof['image']['rights_status'],'unknown');self.assertIsNone(proof['image']['license'])
            for k in ('official_thumbnail_transport_configured','rights_independently_verified','publishing_authorized','provider_authorized','source_asset_rights_granted','final_video_approved','owner_uat_accepted'):
                self.assertIs(proof[k],False)
            self.assertIsNone(self.publications.process());self.approve_publication(row)
            done=self.publications.process(project=self.project['id'],identity=row['publication_id'],fingerprint=row['request_fingerprint'])
            self.assertEqual(done['status'],'dry_run_succeeded');self.assertTrue(done['receipt']['mock']);self.assertFalse(done['receipt']['external_action']);self.assertIsNone(done['receipt']['remote_post_id'])
            self.assertEqual(self.publications.create(self.project['id'],self.intent(),actor='fixture')[0],done)
            self.assertEqual(self.publications.process(project=self.project['id'],identity=row['publication_id'],fingerprint=row['request_fingerprint']),done)
        self.assertEqual(self.store.get(self.project['id']),project);self.assertEqual(self.store.get_job(self.job['id']),job)
        self.assertEqual(self.service.costs.summary(self.project['id']),cost);self.assertEqual(file_sha(path),original);self.assertEqual(self.calls,[])

    def test_revoke_invalidates_queued_review_without_changing_original_snapshot_or_replaying(self):
        grant=self.grant();row=self.create_publication();original=copy.deepcopy(row['snapshot']);self.approve_publication(row);self.revoke(grant)
        done=self.publications.process();self.assertEqual(done['status'],'blocked');self.assertIsNone(done['receipt'])
        self.assertEqual(done['failure_code'],'NATIVE_PUBLICATION_VALIDATION_FAILED');self.assertEqual(done['snapshot'],original)
        self.assertEqual(self.publications.create(self.project['id'],self.intent(),actor='fixture')[0],done);self.assertIsNone(self.publications.process())

    def test_expiry_owner_rotation_and_new_local_only_grant_invalidate_prior_approval(self):
        for action in ('expiry','owner','local'):
            original_verifier=self.verifier;original_clock=self.clock[0]
            self.grant(request_key='explicit-thumbnail-grant-'+action);row=self.create_publication(request_key='explicit-thumbnail-publication-'+action)
            if action=='expiry':self.clock[0]+=timedelta(days=8)
            if action=='owner':self.change_owner(enabled=False)
            if action=='local':self.grant(request_key='explicit-thumbnail-local-grant',allow_publishing_review=False)
            with self.assertRaisesRegex(WorkflowError,'VALIDATION_FAILED'):self.approve_publication(row)
            self.assertEqual(self.publications.get(self.project['id'],row['publication_id'])['snapshot'],row['snapshot'])
            self.verifier=original_verifier;self.clock[0]=original_clock
        self.assertEqual(self.calls,[])

    def test_changed_final_binding_corrupt_png_and_project_edit_fail_without_granting_source_or_final_approval(self):
        self.grant();job=copy.deepcopy(self.job);job['id']='a'*32
        with self.assertRaisesRegex(WorkflowError,'FINAL_BINDING_CHANGED'):self.publications.thumbnail_review(job,self.intent().metadata)
        row=self.create_publication();path=self.root/'jobs'/self.job['id']/self.frame['evidence_frame_reference'];data=path.read_bytes();path.write_bytes(b'EXPLICIT ISOLATED CORRUPTION')
        with self.assertRaises(WorkflowError):self.approve_publication(row)
        path.write_bytes(data);self.store.review_render(self.job['id'],self.job['revision'],'EXPLICIT SYNTHETIC REJECTION',False,'reject','Fixture rejection')
        with self.assertRaises(WorkflowError):self.create_publication(request_key='explicit-rejected-final-key')
        self.assertEqual(self.thumbnails.get(self.project['id'],self.selected['thumbnail_asset_id']),self.selected)

    def test_owner_revoked_during_physical_png_read_is_checked_again_before_passing(self):
        self.grant();original=self.thumbnails.image
        def image(*a,**kw):
            result=original(*a,**kw);self.change_owner(enabled=False);return result
        with patch.object(self.thumbnails,'image',side_effect=image):row=self.create_publication()
        self.assertEqual(row['status'],'blocked');self.assertNotIn('thumbnail',row['snapshot']['validation']);self.assertIsNone(row['approval'])
        self.assertEqual(row['snapshot']['validation']['attention'],['NATIVE_THUMBNAIL_RIGHTS_CURRENT_OWNER_REQUIRED']);self.assertEqual(self.calls,[])

    def test_default_off_current_reader_can_read_history_but_cannot_reapprove_and_scope_cannot_be_rebound(self):
        self.grant();row=self.create_publication();off=NativeRenderThumbnailRights(self.thumbnails)
        reader=NativePublications(self.store,publication_fixture.CAPABILITIES);reader.bind_render_thumbnail_rights(off)
        self.assertEqual(reader.get(self.project['id'],row['publication_id']),self.publications.get(self.project['id'],row['publication_id']))
        with reader.store.transaction() as con:
            with self.assertRaisesRegex(WorkflowError,'VALIDATION_FAILED'):reader.revalidate(con,reader.get_row(con,self.project['id'],row['publication_id']))
        self.publications.bind_render_thumbnail_rights(self.rights)
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.publications.bind_render_thumbnail_rights(off)
        with self.assertRaises(WorkflowError):NativePublicationThumbnailBinding(self.store,'wsp_foreign',self.rights)
        binding=self.publications._thumbnail_binding;binding.workspace='wsp_foreign'
        with self.assertRaises(WorkflowError):self.publications.thumbnail_review(self.job,self.intent().metadata)


if __name__=='__main__':unittest.main()
