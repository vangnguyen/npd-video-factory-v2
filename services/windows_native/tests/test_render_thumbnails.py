"""Original decoded render PNG selection, immutable provenance and no new authority."""
import copy,hashlib,json,sqlite3,unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native.tests import test_render_vision as fixture
from services.windows_native.render_thumbnails import NativeRenderThumbnails,Create
from services.windows_native.render_vision_models import RenderAction
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.store import Store
from services.windows_native.render_vision import NativeRenderVision

class NativeRenderThumbnailTests(unittest.TestCase):
    runtime=fixture.NativeRenderVisionTests.runtime
    bridge=fixture.NativeRenderVisionTests.bridge
    request=fixture.NativeRenderVisionTests.request
    response=fixture.NativeRenderVisionTests.response
    @classmethod
    def setUpClass(cls):fixture.NativeRenderVisionTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.NativeRenderVisionTests.tearDownClass.__func__(cls)
    def setUp(self):
        fixture.NativeRenderVisionTests.setUp(self)
        self.thumbnails=NativeRenderThumbnails(self.store,self.config,render_vision=self.service)
        self.binding=self.bridge().binding();self.frame=next(f for f in self.binding['record']['observation']['frames'] if not f['pixel_facts']['black_sample'])
    def tearDown(self):fixture.NativeRenderVisionTests.tearDown(self)
    def payload(self,**changes):
        return Create.model_validate({'revision':self.project['revision'],'render_job_id':self.job['id'],'expected_render_input_sha256':digest(self.binding),
            'frame_id':self.frame['frame_id'],'expected_frame_sha256':self.frame['sha256'],'acknowledged_thumbnail':True,
            'request_key':'explicit-render-thumbnail-fixture-key',**changes})
    def choose(self,**changes):return self.thumbnails.create(self.project['id'],self.payload(**changes),actor='Explicit synthetic thumbnail review, not Owner UAT')[0]
    def original_vision(self):
        row=self.service.create(self.project['id'],self.request(),principal=self.principal)[0]
        done=self.service.process(self.project['id'],row['vision_id'],RenderAction(expected_snapshot_sha256=row['snapshot_sha256']))
        assert done['status']=='succeeded'
        return done,{'vision_id':done['vision_id'],'expected_snapshot_sha256':done['snapshot_sha256'],
            'expected_result_sha256':done['result_sha256'],'acknowledged_protocol_mock':True}

    def test_manual_original_png_selection_keeps_project_approval_jobs_media_and_cost_exact_without_private_key(self):
        original=self.store.get(self.project['id']);job=self.store.get_job(self.job['id']);cost=self.service.costs.summary(self.project['id'])
        files={str(p.relative_to(self.root)):p.read_bytes() for base in ('assets','jobs') for p in (self.root/base).rglob('*') if p.is_file()}
        with patch.object(self.vault,'key',side_effect=AssertionError('NO THUMBNAIL KEY')):
            selected=self.choose();pixels,snapshot=self.thumbnails.image(self.project['id'],selected['thumbnail_asset_id'])
        self.assertEqual(hashlib.sha256(pixels).hexdigest(),self.frame['sha256']);self.assertEqual(pixels[:8],b'\x89PNG\r\n\x1a\n')
        self.assertEqual(snapshot,selected['snapshot']);self.assertIsNone(snapshot['reviewed_vision']);self.assertEqual(snapshot['image']['rights_status'],'unknown')
        self.assertIsNone(snapshot['image']['license']);self.assertFalse(snapshot['publishing_authorized']);self.assertFalse(snapshot['final_video_approved'])
        self.assertEqual(self.store.get(self.project['id']),original);self.assertEqual(self.store.get_job(self.job['id']),job)
        self.assertEqual(self.service.costs.summary(self.project['id']),cost);self.assertEqual(self.calls,[])
        self.assertEqual({str(p.relative_to(self.root)):p.read_bytes() for base in ('assets','jobs') for p in (self.root/base).rglob('*') if p.is_file()},files)

    def test_original_mock_result_is_referenced_with_separate_ack_no_new_call_or_semantic_or_publish_authority(self):
        original,review=self.original_vision();selected=self.choose(reviewed_vision=review)
        self.assertEqual(selected['snapshot']['reviewed_vision']['response_id'],original['response_id'])
        self.assertEqual(selected['snapshot']['reviewed_vision']['cost_operation_id'],original['cost_operation_id'])
        self.assertTrue(selected['snapshot']['reviewed_vision']['mock']);self.assertFalse(selected['snapshot']['reviewed_vision']['semantic_inference_performed'])
        self.assertFalse(selected['snapshot']['reviewed_vision']['confidence_calibrated']);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.service.get(self.project['id'],original['vision_id']),original)
        for changes in ({'acknowledged_protocol_mock':False},{'expected_result_sha256':'0'*64},{'expected_snapshot_sha256':'0'*64}):
            with self.assertRaisesRegex(WorkflowError,'ORIGINAL_VISION_REQUIRED'):self.choose(reviewed_vision={**review,**changes},request_key='explicit-bad-review-'+digest(changes)[:20])
        self.assertEqual(len(self.calls),1)

    def test_raw_ack_and_source_asset_or_extra_authority_cannot_become_thumbnail_review(self):
        raw=self.payload().model_dump(mode='json')
        for changes in ({'acknowledged_thumbnail':1},{'acknowledged_thumbnail':False},{'revision':True},{'frame_id':'mfr_'+'a'*24},
            {'acknowledged_external_image_analysis':True},{'publishing_authorized':True},{'api_key':'NO CLIENT KEY'},
            {'reviewed_vision':{'vision_id':'nvoi_'+'a'*32,'expected_snapshot_sha256':'0'*64,'expected_result_sha256':'0'*64}}):
            with self.assertRaises(ValidationError):Create.model_validate({**raw,**changes})

    def test_stale_project_foreign_render_frame_sha_and_input_sha_are_rejected(self):
        for changes in ({'render_job_id':'0'*32},{'frame_id':'rqf_'+'0'*24},{'expected_frame_sha256':'0'*64},{'expected_render_input_sha256':'0'*64}):
            with self.assertRaises(WorkflowError):self.choose(**changes)
        self.store.save(self.project['id'],self.project['revision'],prompt='EXPLICIT NEW DOCUMENT')
        with self.assertRaisesRegex(WorkflowError,'STALE_VERSION'):self.choose()
        self.assertEqual(self.calls,[])

    def test_concurrent_idempotency_is_one_original_selection_and_changed_request_conflicts(self):
        payload=self.payload()
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:self.thumbnails.create(self.project['id'],payload,actor='Explicit fixture'),range(2)))
        self.assertEqual(sum(not replay for _,replay in rows),1);self.assertEqual(rows[0][0],rows[1][0])
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.choose(expected_frame_sha256='0'*64)
        self.assertEqual(len(self.thumbnails.page(self.project['id'])['items']),1)

    def test_original_history_and_png_survive_new_project_version_without_transferring_current_review(self):
        payload=self.payload();selected=self.choose();self.store.save(self.project['id'],self.project['revision'],prompt='EXPLICIT LATER PROJECT')
        self.assertEqual(self.thumbnails.get(self.project['id'],selected['thumbnail_asset_id']),selected)
        self.assertEqual(self.thumbnails.create(self.project['id'],payload,actor='Another fixture')[0],selected)
        pixels,_=self.thumbnails.image(self.project['id'],selected['thumbnail_asset_id']);self.assertEqual(hashlib.sha256(pixels).hexdigest(),self.frame['sha256'])
        with self.assertRaises(WorkflowError):self.choose(revision=self.project['revision']+1,request_key='explicit-new-version-key')

    def test_changed_or_missing_physical_png_blocks_use_but_original_readonly_history_remains(self):
        selected=self.choose();path=self.root/'jobs'/self.job['id']/self.frame['evidence_frame_reference'];original=path.read_bytes()
        path.write_bytes(original+b'EXPLICIT CORRUPTION')
        self.assertEqual(self.thumbnails.get(self.project['id'],selected['thumbnail_asset_id']),selected)
        with self.assertRaises(WorkflowError):self.thumbnails.image(self.project['id'],selected['thumbnail_asset_id'])
        path.unlink()
        self.assertEqual(self.thumbnails.get(self.project['id'],selected['thumbnail_asset_id']),selected)
        with self.assertRaises(WorkflowError):self.thumbnails.image(self.project['id'],selected['thumbnail_asset_id'])

    def test_rehashed_raw_authority_extra_key_and_foreign_connection_fail_closed(self):
        selected=self.choose();raw=copy.deepcopy(selected['snapshot'])
        for changes in ({'publishing_authorized':True},{'canonical_timeline_mutated':0},{'paid_operations':False},{'api_key':'PRIVATE'}):
            altered={**raw,**changes}
            with self.store.transaction() as con:con.execute('UPDATE native_render_thumbnails SET snapshot_json=?,snapshot_sha256=?',(json.dumps(altered),digest(altered)))
            with self.assertRaises(WorkflowError):self.thumbnails.get(self.project['id'],selected['thumbnail_asset_id'])
        with self.store.transaction() as con:con.execute('UPDATE native_render_thumbnails SET snapshot_json=?,snapshot_sha256=?',(json.dumps(raw),digest(raw)))
        with closing(sqlite3.connect(Path(self.temp.name)/'foreign.db')) as con:
            con.execute('BEGIN IMMEDIATE')
            with self.assertRaisesRegex(WorkflowError,'SCOPE_INVALID'):self.thumbnails.get(self.project['id'],selected['thumbnail_asset_id'],con=con)

    def test_remounted_or_malformed_workspace_marker_blocks_original_history(self):
        selected=self.choose();marker=self.root/'.vf-auth-workspace.json'
        for text in ('EXPLICIT INVALID JSON',json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':'foreign-workspace'})):
            marker.write_text(text,encoding='utf-8')
            with self.assertRaisesRegex(WorkflowError,'SCOPE_INVALID'):self.thumbnails.get(self.project['id'],selected['thumbnail_asset_id'])

    def test_bounded_history_cursor_cannot_cross_project_or_workspace(self):
        self.choose();self.choose(request_key='explicit-second-thumbnail-key');first=self.thumbnails.page(self.project['id'],limit=1)
        second=self.thumbnails.page(self.project['id'],limit=1,cursor=first['next_cursor']);self.assertIsNone(second['next_cursor'])
        self.assertNotEqual(first['items'][0]['thumbnail_asset_id'],second['items'][0]['thumbnail_asset_id'])
        for changes in ({'limit':True},{'limit':101},{'cursor':'bad'}):
            with self.assertRaises(WorkflowError):self.thumbnails.page(self.project['id'],**changes)
        with self.assertRaises(WorkflowError):self.thumbnails.page('0'*32,limit=1,cursor=first['next_cursor'])
        with self.assertRaises(WorkflowError):self.thumbnails.get('0'*32,first['items'][0]['thumbnail_asset_id'])

    def test_public_backup_keyless_restore_preserves_original_selection_response_journal_and_png(self):
        vision,review=self.original_vision();selected=self.choose(reviewed_vision=review)
        self.assertEqual(database_status(self.store.db)['active_operations'],0)
        archive=Path(self.temp.name)/'public-thumbnails.zip';backup=create_backup(self.config,archive);restored=Path(self.temp.name)/'restored'
        restore_backup(archive,restored,expected_sha256=backup['sha256']);store=Store(restored);config=replace(self.config,data_root=restored)
        history=NativeRenderVision(store,config);reader=NativeRenderThumbnails(store,config,render_vision=history)
        self.assertEqual(reader.get(self.project['id'],selected['thumbnail_asset_id']),selected)
        self.assertEqual(history.get(self.project['id'],vision['vision_id']),vision)
        pixels,_=reader.image(self.project['id'],selected['thumbnail_asset_id']);self.assertEqual(hashlib.sha256(pixels).hexdigest(),self.frame['sha256'])
        self.assertEqual(len(self.calls),1)

if __name__=='__main__':unittest.main()
