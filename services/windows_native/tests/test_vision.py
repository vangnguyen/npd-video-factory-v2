"""Real local frame PNGs; semantic objects/OCR are explicit fixture predictions only."""
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid
from PIL import Image
from pydantic import ValidationError
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.media import ingest_media
from services.windows_native.media_frame_analysis import view,frame_path
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
from services.windows_native.vision import NativeVision
from services.windows_native.vision_models import NativeVisionRequest
from services.windows_native.vision_provider import NativeFixtureVisionProvider


class NativeVisionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'source'
        self.config=Config(data_root=self.root,secret_file=Path(self.temp.name)/'private'/'absent-key.env',assemblyai_secret_file=Path(self.temp.name)/'private'/'absent-asr.dpapi')
        self.store=Store(self.root);source=Path(self.temp.name)/'explicit-owned-image.png';Image.new('RGB',(320,240),(42,137,242)).save(source)
        asset=ingest_media(self.config,source,'image/png','EXPLICIT SYNTHETIC FRAME FIXTURE',rights_confirmed=True,illustration=True)
        self.project=self.store.create('Generic AI education fixture','','media');self.project=self.store.append_media(self.project['id'],self.project['revision'],asset)
        job=self.store.enqueue(self.project['id'],self.project['revision'],'media_frames',uuid.uuid4().hex);job=self.store.claim()
        result=Pipeline(self.config).run(job,lambda _:None);self.store.finish(job,result=result);self.project=self.store.get(self.project['id'])
        self.frames=view(self.store,self.project['id']);self.service=NativeVision(self.store,self.config)

    def tearDown(self):self.temp.cleanup()

    def payload(self,**changes):
        return NativeVisionRequest.model_validate({'revision':self.project['revision'],'observation_ids':[self.frames['observations'][0]['observation_id']],
            'provider_mode':'fixture','fixture_acknowledged':True,'request_key':'native-vision-owned-fixture-key',**changes})

    def create(self,**changes):return self.service.create(self.project['id'],self.payload(**changes),actor='fixture-owner')[0]

    def test_structured_generic_fixture_keeps_real_pixels_separate_and_crop_attention_bound(self):
        before=self.store.get(self.project['id']);value=self.create();done=self.service.process();self.assertEqual(done['status'],'succeeded')
        result=done['result'];self.assertTrue(result['mock']);self.assertFalse(result['semantic_inference_performed']);self.assertFalse(result['automatic_planning_eligible'])
        asset=result['assets'][0];self.assertEqual(len(asset['frames'][0]['objects']),2);self.assertEqual(asset['frames'][0]['ocr'][0]['language'],'vi')
        self.assertIn('MẪU',asset['frames'][0]['ocr'][0]['text']);self.assertFalse(asset['provenance']['semantic_model_saw_pixels'])
        self.assertEqual(asset['frames'][0]['evidence_frame_reference'],asset['source_frame_evidence'][0]['reference'])
        self.assertEqual({plan['aspect_ratio'] for plan in asset['reframe_plans']},{'9:16','16:9','1:1','4:5'})
        self.assertTrue(all(plan['fallback']=='center_crop' and plan['needs_attention'] and plan['confidence']==0 for plan in asset['reframe_plans']))
        self.assertFalse(asset['tracking_available']);self.assertIsNone(asset['broll_relevance']);self.assertEqual(self.store.get(self.project['id']),before)
        self.assertEqual(view(self.store,self.project['id']),self.frames)

    def test_official_default_has_no_mock_fallback_or_dispatch(self):
        with patch.object(NativeFixtureVisionProvider,'analyze',side_effect=AssertionError('No mock fallback')):
            row=self.create(provider_mode='official',fixture_acknowledged=False);self.assertEqual(row['status'],'not_configured')
            self.assertIsNone(row['result']);self.assertIsNone(self.service.process())

    def test_concurrency_idempotency_and_restart_preserve_exact_one_result(self):
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(lambda _:self.service.create(self.project['id'],self.payload(),actor='fixture-owner'),range(2)))
        self.assertEqual(sum(not replay for _,replay in rows),1)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.service.process(),range(2)))
        self.assertEqual(sum(value is not None for value in results),1);saved=self.service.get(self.project['id'],rows[0][0]['vision_id'])
        restored=NativeVision(Store(self.root),self.config);self.assertEqual(restored.get(self.project['id'],saved['vision_id']),saved)
        value,replay=restored.create(self.project['id'],self.payload(),actor='another-fixture-owner');self.assertTrue(replay);self.assertEqual(value['result'],saved['result'])
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.create(provider_mode='official',fixture_acknowledged=False)

    def test_revision_change_fails_before_provider(self):
        value=self.create()
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET revision=revision+1 WHERE id=?',(self.project['id'],));self.store.version(con,self.project['id'])
        with patch.object(NativeFixtureVisionProvider,'analyze',side_effect=AssertionError('No stale dispatch')):
            self.assertEqual(self.service.process()['status'],'failed')

    def test_actual_frame_corruption_fails_before_provider(self):
        self.create();frame=self.frames['observations'][0]['frames'][0];frame_path(self.root,frame).write_bytes(b'EXPLICIT CORRUPTED FIXTURE FRAME')
        with patch.object(NativeFixtureVisionProvider,'analyze',side_effect=AssertionError('No corrupted source dispatch')):
            done=self.service.process();self.assertEqual(done['status'],'failed');self.assertIsNone(done['result'])

    def test_cancel_is_terminal_and_completion_event_failure_rolls_back_result(self):
        row=self.create();cancelled=self.service.cancel(self.project['id'],row['vision_id'],fingerprint=row['request_fingerprint'],actor='fixture-owner')
        self.assertEqual(cancelled['status'],'cancelled');self.assertIsNone(self.service.process())
        same=self.service.cancel(self.project['id'],row['vision_id'],fingerprint=row['request_fingerprint'],actor='fixture-owner')
        self.assertEqual(same,cancelled);self.assertEqual(len(self.service.get(self.project['id'],row['vision_id'])['events']),2)
        self.create(request_key='native-vision-event-failure-fixture');original=self.service.event
        def fail(con,value,action,actor,**evidence):
            if action=='vision.fixture.completed':raise RuntimeError('EXPLICIT COMMIT FAILURE FIXTURE')
            return original(con,value,action,actor,**evidence)
        with patch.object(self.service,'event',fail):done=self.service.process()
        self.assertEqual(done['status'],'failed');self.assertIsNone(done['result']);self.assertIsNone(done['result_sha256'])
        self.assertEqual(self.service.get(self.project['id'],done['vision_id'])['events'][0]['action'],'vision.intent.failed')

    def test_rehashed_result_cannot_relabel_actual_frame_or_claim_real_inference(self):
        row=self.create();done=self.service.process();saved=copy.deepcopy(done['result'])
        for field in ['frame','provider','provenance','crop']:
            result=copy.deepcopy(saved);asset=result['assets'][0]
            if field=='frame':asset['frames'][0]['evidence_frame_reference']='fixture://wrong-frame'
            elif field=='provider':asset['provider']='fixture-spoofed'
            elif field=='provenance':asset['provenance']['semantic_model_saw_pixels']=True
            else:asset['reframe_plans'][0]['aspect_ratio']=asset['reframe_plans'][1]['aspect_ratio']
            with self.store.transaction() as con:con.execute('UPDATE native_vision_intents SET result_sha256=?,result_json=? WHERE vision_id=?',
                (digest(result),json.dumps(result),row['vision_id']))
            with self.subTest(field=field),self.assertRaisesRegex(WorkflowError,'RESULT_EVIDENCE_INVALID'):
                self.service.get(self.project['id'],row['vision_id'])

    def test_wrong_provider_frame_reference_is_rejected_without_partial_result(self):
        value=self.create();original=NativeFixtureVisionProvider.analyze
        async def wrong(provider,*args,**kwargs):
            result=await original(provider,*args,**kwargs)
            return replace(result,frames=(replace(result.frames[0],evidence_frame_reference='explicit-wrong-fixture-reference'),))
        with patch.object(NativeFixtureVisionProvider,'analyze',wrong):done=self.service.process()
        self.assertEqual(done['status'],'failed');self.assertIsNone(done['result']);self.assertEqual(done['failure_code'],'NATIVE_VISION_FIXTURE_PROVIDER_REQUIRED')

    def test_result_and_snapshot_tamper_scope_and_cursor_fail_closed(self):
        values=[self.create(request_key='native-vision-page-fixture-'+str(i)) for i in range(3)]
        for _ in values:self.service.process()
        first=self.service.page(self.project['id'],limit=2);second=self.service.page(self.project['id'],limit=2,cursor=first['next_cursor'])
        self.assertEqual(len({row['vision_id'] for row in first['items']+second['items']}),3)
        other=NativeVision(self.store,self.config,workspace_id='wsp_other_fixture');self.assertEqual(other.page(self.project['id'])['items'],[])
        with self.assertRaisesRegex(WorkflowError,'CURSOR_INVALID'):other.page(self.project['id'],cursor=first['next_cursor'])
        with self.store.transaction() as con:con.execute("UPDATE native_vision_intents SET result_json='{}' WHERE vision_id=?",(values[0]['vision_id'],))
        with self.assertRaisesRegex(WorkflowError,'RESULT_EVIDENCE_INVALID'):self.service.get(self.project['id'],values[0]['vision_id'])

    def test_strict_fixture_ack_revision_and_observation_binding(self):
        for change in [{'revision':True},{'fixture_acknowledged':False},{'fixture_acknowledged':1},{'observation_ids':[]},
            {'observation_ids':['not-an-observation']},{'publish_enabled':True},{'provider_mode':'official'}]:
            with self.subTest(fields=list(change)),self.assertRaises(ValidationError):self.payload(**change)
        with self.assertRaisesRegex(WorkflowError,'OBSERVATION_NOT_FOUND'):
            self.create(observation_ids=['mfo_'+'f'*24])

    def test_pending_vision_blocks_backup_and_cancelled_history_restores_exact(self):
        from services.windows_native.backup import create_backup,restore_backup
        row=self.create();archive=Path(self.temp.name)/'vision-backup.zip'
        with self.assertRaisesRegex(WorkflowError,'BACKUP_SOURCE_HAS_ACTIVE_OPERATIONS'):create_backup(self.config,archive)
        self.assertFalse(archive.exists())
        self.service.cancel(self.project['id'],row['vision_id'],fingerprint=row['request_fingerprint'],actor='fixture-owner')
        expected=self.service.get(self.project['id'],row['vision_id']);receipt=create_backup(self.config,archive)
        self.assertEqual(receipt['database_status']['workflow.sqlite3']['counts']['native_vision_intents'],1)
        destination=Path(self.temp.name)/'restored-vision';restore_backup(archive,destination,expected_sha256=receipt['sha256'])
        restored=NativeVision(Store(destination),replace(self.config,data_root=destination));self.assertEqual(restored.get(self.project['id'],row['vision_id']),expected)
        for frame in self.frames['observations'][0]['frames']:self.assertTrue(frame_path(destination,frame).is_file())

    def test_native_vision_imports_without_api_framework_database_or_gpu(self):
        source="from services.windows_native.vision import NativeVision; import sys; assert not any(n.startswith(('sqlalchemy','fastapi','torch','vieneu')) for n in sys.modules)"
        subprocess.run([sys.executable,'-c',source],check=True,capture_output=True,timeout=30)


if __name__=='__main__':unittest.main()
