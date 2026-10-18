"""Real local media and synthetic human approvals; never records Owner UAT."""
import copy
import json
import shutil
import tempfile
import unittest
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner
from services.windows_native.store import Store
from services.windows_native.manual_delivery import NativeManualDelivery,DeliveryCreate,CaptionSave,srt
from services.windows_native.tests import test_source_render as fixture


class ManualDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original=fixture.NativeSourceRenderTests('test_real_source_worker_qc_checkpoint_keeps_media_immutable_and_requires_final_review')
        f=cls.original;f.setUp();f.review_fixture()
        job=f.store.enqueue(f.project['id'],f.project['revision'],'render',uuid.uuid4().hex)
        assert Runner(f.store,Pipeline(f.config)).run_one()
        cls.job_id=job['id'];job=f.store.get_job(job['id']);assert job['status']=='succeeded',job.get('error')
        f.store.review_render(job['id'],job['revision'],'AUTOMATED LOCAL EXPORT FIXTURE — NOT OWNER ACCEPTANCE',True,'approve')

    @classmethod
    def tearDownClass(cls):cls.original.tearDown()

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'state'
        shutil.copytree(self.original.root,self.root)
        self.store=Store(self.root);self.config=replace(self.original.config,data_root=self.root)
        self.service=NativeManualDelivery(self.store,self.config);self.project=self.store.get(self.original.project['id'])
        self.job=self.store.get_job(self.job_id);self.video_hash=self.job['result']['qc']['final_sha256']

    def tearDown(self):self.temp.cleanup()

    def request(self,**changes):
        return DeliveryCreate.model_validate({'revision':self.project['revision'],'render_job_id':self.job_id,
            'expected_video_sha256':self.video_hash,'request_key':'explicit-manual-delivery-fixture',**changes})

    def create(self,**changes):return self.service.create(self.project['id'],self.request(**changes))

    def count(self):
        with self.store.transaction() as con:return con.execute('SELECT COUNT(*) FROM native_manual_exports').fetchone()[0]

    def test_actual_approved_mp4_qc_cover_srt_caption_zip_manifest_and_exact_replay(self):
        original=copy.deepcopy(self.store.get(self.project['id']))
        variants={'master':{'title':'Cần Giờ','caption':'Vang Nguyễn giới thiệu.','hashtags':'#CanGio','cta':'Tìm hiểu thêm'},
            'tiktok':{'caption':'Bản dành cho TikTok'}}
        saved=self.service.save_copy(self.project['id'],CaptionSave(expected_version=0,request_key='explicit-caption-fixture-key',variants=variants))
        result=self.create(caption_version=saved['version']);self.assertEqual(result['status'],'ready')
        self.assertFalse(result['externally_posted']);self.assertTrue(result['integrity_checked']);self.assertTrue(result['current_for_project'])
        manifest=result['manifest'];self.assertEqual((manifest['width'],manifest['height']),(1080,1920))
        self.assertEqual(manifest['video_sha256'],self.video_hash);self.assertEqual(manifest['qc_result'],'passed')
        directory=Path(result['output_location']);self.assertEqual(file_sha(directory/'final-video.mp4'),self.video_hash)
        self.assertIn('subtitle.srt',manifest['files']);self.assertIn('cover.jpg',manifest['files'])
        self.assertIn('Cần Giờ',(directory/'title.txt').read_text(encoding='utf-8'))
        self.assertEqual(json.loads((directory/'cover-provenance.json').read_bytes())['video_sha256'],self.video_hash)
        with zipfile.ZipFile(directory/'delivery-package.zip') as z:
            self.assertIsNone(z.testzip());self.assertEqual(set(z.namelist()),set(manifest['files'])|{'delivery-manifest.json'})
        replay=self.create(caption_version=saved['version']);self.assertEqual(replay['export_id'],result['export_id']);self.assertTrue(replay['idempotent_replay'])
        self.assertEqual(self.count(),1);self.assertEqual(self.store.get(self.project['id']),original)

    def test_no_unapproved_or_hash_stale_or_wrong_orientation_delivery(self):
        for changes,code in [({'profile':'landscape'},'CANVAS_MISMATCH'),({'expected_video_sha256':'0'*64},'VERSION_CHANGED'),({'revision':self.project['revision']+1},'VERSION_CHANGED')]:
            with self.subTest(changes=changes),self.assertRaisesRegex(WorkflowError,code):self.create(**changes)
        with self.store.transaction() as con:con.execute('DELETE FROM render_reviews WHERE job_id=?',(self.job_id,))
        with self.assertRaisesRegex(WorkflowError,'HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED'):self.create()
        self.assertEqual(self.count(),0)

    def test_filename_validation_rejects_paths_reserved_and_collision_names(self):
        for filename in ['../final.mp4','C:\\video.mp4','CON.mp4','lpt1.mp4','aux.backup.mp4','file .mp4','.hidden.mp4','video.mp4 ','video.MP4']:
            with self.subTest(filename=filename),self.assertRaises(ValidationError):self.request(filename=filename)

    def test_copy_cas_idempotency_and_history_do_not_mutate_video_approval(self):
        original=self.store.get(self.project['id'])
        payload=CaptionSave(expected_version=0,request_key='explicit-caption-history-key',variants={'master':{'caption':'Bản đầu'}})
        one=self.service.save_copy(self.project['id'],payload);self.assertEqual(one['version'],1)
        self.assertTrue(self.service.save_copy(self.project['id'],payload)['idempotent_replay'])
        with self.assertRaisesRegex(WorkflowError,'KEY_CONFLICT'):
            self.service.save_copy(self.project['id'],CaptionSave.model_validate({**payload.model_dump(),'variants':{'master':{'caption':'Đổi nội dung'}}}))
        with self.assertRaisesRegex(WorkflowError,'VERSION_CHANGED'):
            self.service.save_copy(self.project['id'],payload.model_copy(update={'request_key':'explicit-caption-new-stale-key'}))
        two=self.service.save_copy(self.project['id'],CaptionSave(expected_version=1,request_key='explicit-caption-new-good-key',variants={'master':{'caption':'Bản sau'}}))
        self.assertEqual(two['version'],2);self.assertEqual(len(self.service.copies(self.project['id'])['items']),2)
        self.assertEqual(self.store.get(self.project['id']),original)

    def test_restart_and_lost_response_reconcile_one_export_without_rebuild(self):
        done=self.create(cover=False,separate_subtitle=False)
        self.service=NativeManualDelivery(Store(self.root),self.config)
        with patch.object(self.service,'build',side_effect=AssertionError('No duplicate rendering or packaging')):
            self.assertEqual(self.create(cover=False,separate_subtitle=False)['export_id'],done['export_id'])
        with self.store.transaction() as con:con.execute("UPDATE native_manual_exports SET status='preparing' WHERE export_id=?",(done['export_id'],))
        self.service=NativeManualDelivery(Store(self.root),self.config)
        with patch.object(self.service,'build',side_effect=AssertionError('Reconcile exact handoff bytes')):
            self.assertEqual(self.create(cover=False,separate_subtitle=False)['status'],'ready')
        self.assertEqual(self.count(),1)

    def test_disk_full_and_partial_stage_are_recoverable_same_key(self):
        with patch('services.windows_native.manual_delivery.shutil.disk_usage',return_value=shutil._ntuple_diskusage(10,10,0)):
            with self.assertRaisesRegex(WorkflowError,'DISK_SPACE_REQUIRED'):self.create(cover=False)
        self.assertEqual(self.service.page(self.project['id'])['items'][0]['status'],'failed')
        done=self.create(cover=False);self.assertEqual(done['status'],'ready');self.assertEqual(self.count(),1)
        self.assertTrue(list((self.root/'deliveries'/self.project['id']).glob('.partial-*')))

    def test_output_directory_write_error_retains_source_and_request(self):
        with patch('services.windows_native.manual_delivery.shutil.copyfile',side_effect=OSError('synthetic private disk message')):
            with self.assertRaisesRegex(WorkflowError,'EXPORT_WRITE_FAILED'):self.create(cover=False)
        self.assertEqual(file_sha(self.root/'jobs'/self.job_id/'final.mp4'),self.video_hash)
        self.assertEqual(self.count(),1);self.assertEqual(self.service.page(self.project['id'])['items'][0]['error_code'],'EXPORT_WRITE_FAILED')
        self.assertEqual(self.create(cover=False)['status'],'ready')

    def test_corrupted_or_missing_delivery_cannot_download_and_never_replaces_file(self):
        result=self.create(cover=False);path=Path(result['output_location'])/'final-video.mp4';path.write_bytes(b'corrupted')
        for action in [lambda:self.create(cover=False),lambda:self.service.file(self.project['id'],result['export_id'],'final-video.mp4')]:
            with self.assertRaisesRegex(WorkflowError,'EXPORT_FILE_CHANGED'):action()
        self.assertEqual(path.read_bytes(),b'corrupted');self.assertEqual(self.count(),1)

    def test_same_filename_new_request_is_new_immutable_version_and_stale_history_is_labeled(self):
        first=self.create(cover=False);original=Path(first['output_location'])/'final-video.mp4'
        second=self.create(cover=False,request_key='explicit-new-export-version-key')
        self.assertNotEqual(second['export_id'],first['export_id']);self.assertEqual(file_sha(original),self.video_hash)
        self.store.save(self.project['id'],self.project['revision'],prompt='Later project change, earlier delivery retained')
        old=self.service.get(self.project['id'],first['export_id']);self.assertFalse(old['current_for_project'])
        self.assertEqual(old['approval_state'],'approved_at_export')
        self.assertEqual(file_sha(self.service.file(self.project['id'],first['export_id'],'final-video.mp4')),self.video_hash)
        with self.assertRaisesRegex(WorkflowError,'STALE|READY'):self.create(cover=False,request_key='explicit-stale-export-new-key')

    def test_foreign_project_and_unknown_file_cannot_escape_delivery(self):
        done=self.create(cover=False)
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.service.get('0'*32,done['export_id'])
        for name in ['../workflow.sqlite3','delivery-manifest.json/../workflow.sqlite3','voice.wav']:
            with self.assertRaisesRegex(WorkflowError,'FILE_NOT_FOUND'):self.service.file(self.project['id'],done['export_id'],name)

    def test_srt_vietnamese_and_invalid_timing(self):
        self.assertIn('00:00:00,100 --> 00:00:01,200\nVang Nguyễn',srt([{'start_seconds':.1,'end_seconds':1.2,'text':'Vang Nguyễn'}],2))
        for cue in [{'start':1,'end':.5,'text':'x'},{'start':0,'end':3,'text':'x'},{'start':0,'end':1,'text':'bad --> injection'}]:
            with self.assertRaisesRegex(WorkflowError,'TIMING_INVALID'):srt([cue],2)

    def test_concurrent_duplicate_request_has_one_immutable_output(self):
        payload=self.request(cover=False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.service.create(self.project['id'],payload),range(2)))
        self.assertEqual(results[0]['export_id'],results[1]['export_id']);self.assertEqual(self.count(),1)
        self.assertEqual(sum(r['idempotent_replay'] for r in results),1)

    def test_revoked_writer_after_io_cannot_commit_ready_delivery(self):
        allowed=[True];build=self.service.build
        def revoke(*args):build(*args);allowed[0]=False
        def authorized():
            if not allowed[0]:raise WorkflowError('NATIVE_AUTH_FORBIDDEN',403)
        with patch.object(self.service,'build',side_effect=revoke):
            with self.assertRaisesRegex(WorkflowError,'AUTH_FORBIDDEN'):
                self.service.create(self.project['id'],self.request(cover=False),authorization_check=authorized)
        self.assertEqual(self.service.page(self.project['id'])['items'][0]['status'],'failed')
        allowed[0]=True
        self.assertEqual(self.service.create(self.project['id'],self.request(cover=False),authorization_check=authorized)['status'],'ready')
