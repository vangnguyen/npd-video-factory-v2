"""Owned child exits during/after actual local render; never signals Owner approval."""
import json,os,subprocess,sys,unittest,uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests import test_manual_delivery as fixture
from services.windows_native.store import Store
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Runner
from services.windows_native.contracts import file_sha


class ExportRenderRecoveryTests(unittest.TestCase):
    setUpClass=classmethod(fixture.ManualDeliveryTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.ManualDeliveryTests.tearDownClass.__func__)
    setUp=fixture.ManualDeliveryTests.setUp
    tearDown=fixture.ManualDeliveryTests.tearDown

    def interrupted(self,phase):
        saved=self.store.get(self.project['id']);job=self.store.enqueue(saved['id'],saved['revision'],'render','render-recovery-'+uuid.uuid4().hex)
        config_path=Path(self.temp.name)/'owned-render-recovery.json'
        config_path.write_text(json.dumps(replace(self.config,secret_file=Path(self.temp.name)/'absent-provider',assemblyai_secret_file=Path(self.temp.name)/'absent-asr').dump()),encoding='utf-8')
        code='''import os,sys
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
c=Config.load(sys.argv[1]);s=Store(c.data_root);job=s.claim()
def stage(name):
    s.stage(job['id'],name)
    if sys.argv[2]=='during' and name=='source_canonical_audio_mux':os._exit(87)
Pipeline(c).run(job,stage)
os._exit(88)
'''
        child=subprocess.run([sys.executable,'-X','utf8','-c',code,str(config_path),phase],capture_output=True,timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertEqual(child.returncode,87 if phase=='during' else 88,child.stderr.decode('utf-8',errors='replace'))
        self.store=Store(self.root);self.store.recover();held=self.store.get_job(job['id'])
        self.assertEqual(held['status'],'interrupted');self.assertEqual(self.store.get(saved['id'])['document'],saved['document'])
        directory=self.root/'jobs'/job['id'];self.assertEqual((directory/'checkpoint-render.json').exists(),phase=='after')
        self.assertEqual(self.service.page(saved['id'])['items'],[])
        self.assertEqual(self.store.resume(job['id'])['id'],job['id'])
        return job,directory

    def finalize(self,job):
        done=self.store.get_job(job['id']);self.assertEqual(done['status'],'succeeded',done['error'])
        self.assertIsNone(done['final_review'])
        self.store.review_render(job['id'],done['revision'],'AUTOMATED RESTART FINAL REVIEW — NOT OWNER UAT',True,'approve')
        from services.windows_native.manual_delivery import DeliveryCreate
        payload=DeliveryCreate(revision=done['revision'],render_job_id=job['id'],expected_video_sha256=done['result']['qc']['final_sha256'],
            cover=False,request_key='recovered-render-export-request')
        delivery=self.service.create(self.project['id'],payload)
        self.assertEqual(self.service.create(self.project['id'],payload)['export_id'],delivery['export_id'])
        self.assertEqual(len(self.service.page(self.project['id'])['items']),1)
        self.assertEqual(file_sha(self.root/'jobs'/self.job_id/'final.mp4'),self.video_hash)

    def test_real_exit_during_render_restarts_in_new_attempt_and_keeps_partial_private(self):
        job,directory=self.interrupted('during');attempts=list((directory/'attempts').iterdir());self.assertEqual(len(attempts),1)
        partial=attempts[0]/'final.mp4';checksum=file_sha(partial)
        self.assertFalse((directory/'final.mp4').exists())
        self.assertTrue(Runner(self.store,Pipeline(self.config)).run_one());self.assertEqual(file_sha(partial),checksum)
        self.assertEqual(len(list((directory/'attempts').iterdir())),2);self.finalize(job)

    def test_real_exit_after_render_reuses_checkpoint_without_rendering_twice(self):
        job,directory=self.interrupted('after');checksum=file_sha(directory/'final.mp4')
        with patch('services.windows_native.source_render.command_run',side_effect=AssertionError('Completed render must not execute again')):
            self.assertTrue(Runner(self.store,Pipeline(self.config)).run_one())
        self.assertEqual(file_sha(directory/'final.mp4'),checksum);self.finalize(job)


if __name__=='__main__':unittest.main()
