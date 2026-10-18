"""Fault injection only in newly created synthetic temp exports, never accepted media."""
import json
import unittest
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests import test_manual_delivery as fixture
from services.windows_native.manual_delivery import NativeManualDelivery,RecreatePackage
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.store import Store


class SimulatedProcessExit(BaseException):pass


class DeliveryRecoveryTests(unittest.TestCase):
    setUpClass=classmethod(fixture.ManualDeliveryTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.ManualDeliveryTests.tearDownClass.__func__)
    setUp=fixture.ManualDeliveryTests.setUp
    tearDown=fixture.ManualDeliveryTests.tearDown
    request=fixture.ManualDeliveryTests.request
    create=fixture.ManualDeliveryTests.create
    count=fixture.ManualDeliveryTests.count

    def recreate_request(self,done):
        return RecreatePackage(expected_manifest_sha256=done['manifest_sha256'],request_key='explicit-recreate-package-fixture')

    def crash_handoff(self,row,stage):
        self.original_handoff(row,stage);raise SimulatedProcessExit()

    def test_exact_completed_request_is_reconciled_even_after_later_project_edits(self):
        done=self.create(cover=False);old_hash=file_sha(Path(done['output_location'])/'delivery-package.zip')
        self.store.save(self.project['id'],self.project['revision'],prompt='A new revision must not hide the old successful receipt')
        with patch.object(self.service,'build',side_effect=AssertionError('No duplicate generation')):
            replay=self.create(cover=False)
        self.assertEqual(replay['export_id'],done['export_id']);self.assertFalse(replay['current_for_project']);self.assertTrue(replay['idempotent_replay'])
        self.assertEqual(file_sha(Path(done['output_location'])/'delivery-package.zip'),old_hash);self.assertEqual(self.count(),1)

    def test_crash_after_handoff_restarts_from_custody_hashes_without_rebuilding(self):
        self.original_handoff=self.service.handoff
        with patch.object(self.service,'handoff',side_effect=self.crash_handoff):
            with self.assertRaises(SimulatedProcessExit):self.create(cover=False)
        held=self.service.page(self.project['id'])['items'][0];self.assertEqual(held['status'],'preparing')
        self.service=NativeManualDelivery(Store(self.root),self.config)
        with patch.object(self.service,'build',side_effect=AssertionError('No second package')):done=self.create(cover=False)
        self.assertEqual(done['export_id'],held['export_id']);self.assertEqual(done['status'],'ready');self.assertEqual(self.count(),1)

    def test_tampered_handoff_manifest_is_not_blessed_during_restart(self):
        self.original_handoff=self.service.handoff
        with patch.object(self.service,'handoff',side_effect=self.crash_handoff):
            with self.assertRaises(SimulatedProcessExit):self.create(cover=False)
        held=self.service.page(self.project['id'])['items'][0];path=Path(held['output_location'])/'delivery-manifest.json'
        data=json.loads(path.read_bytes());data['width']=1920;path.write_text(json.dumps(data),encoding='utf-8')
        self.service=NativeManualDelivery(Store(self.root),self.config)
        with self.assertRaisesRegex(WorkflowError,'MANIFEST_CHANGED'):self.create(cover=False)
        self.assertEqual(self.service.page(self.project['id'])['items'][0]['status'],'failed')

    def test_lost_zip_recreates_as_new_delivery_from_pinned_files_and_old_version(self):
        original=self.create(cover=False);folder=Path(original['output_location']);video_sha=file_sha(folder/'final-video.mp4');manifest_sha=file_sha(folder/'delivery-manifest.json')
        (folder/'delivery-package.zip').write_bytes(b'owned synthetic corrupt ZIP, retain for diagnosis')
        self.store.save(self.project['id'],self.project['revision'],prompt='Current project differs; old export stays historical')
        done=self.service.recreate(self.project['id'],original['export_id'],self.recreate_request(original))
        self.assertNotEqual(done['export_id'],original['export_id']);self.assertFalse(done['current_for_project']);self.assertEqual(done['manifest']['recreated_from_export_id'],original['export_id'])
        self.assertEqual(file_sha(Path(done['output_location'])/'final-video.mp4'),video_sha)
        self.assertEqual(file_sha(folder/'delivery-manifest.json'),manifest_sha);self.assertTrue((folder/'delivery-package.zip').read_bytes().startswith(b'owned synthetic'))
        replay=self.service.recreate(self.project['id'],original['export_id'],self.recreate_request(original));self.assertEqual(replay['export_id'],done['export_id']);self.assertEqual(self.count(),2)

    def test_recreate_crash_reconciles_one_new_version(self):
        original=self.create(cover=False);request=self.recreate_request(original);self.original_handoff=self.service.handoff
        with patch.object(self.service,'handoff',side_effect=self.crash_handoff):
            with self.assertRaises(SimulatedProcessExit):self.service.recreate(self.project['id'],original['export_id'],request)
        self.service=NativeManualDelivery(Store(self.root),self.config)
        with patch('services.windows_native.manual_delivery.shutil.copyfile',side_effect=AssertionError('No duplicate recreation')):
            done=self.service.recreate(self.project['id'],original['export_id'],request)
        self.assertEqual(done['status'],'ready');self.assertEqual(self.count(),2)

    def test_unavailable_folder_is_actionable_and_new_export_preserves_quarantined_files(self):
        done=self.create(cover=False);folder=Path(done['output_location']);quarantine=folder.with_name('owned-fixture-quarantine-'+done['export_id'])
        self.assertTrue(folder.resolve().is_relative_to(self.root.resolve()));self.assertTrue(quarantine.resolve().is_relative_to(self.root.resolve()))
        folder.rename(quarantine)
        self.assertEqual(self.service.page(self.project['id'])['items'][0]['availability'],'missing')
        with self.assertRaisesRegex(WorkflowError,'OUTPUT_UNAVAILABLE'):self.create(cover=False)
        new=self.create(cover=False,request_key='explicit-new-after-unavailable-key');self.assertNotEqual(new['export_id'],done['export_id'])
        self.assertEqual(file_sha(quarantine/'final-video.mp4'),self.video_hash)

    def test_collision_never_replaces_unknown_existing_output(self):
        handoff=self.service.handoff
        def collision(row,stage):
            target=self.service.directory(row);target.mkdir();(target/'KEEP.txt').write_text('owned collision fixture')
            handoff(row,stage)
        with patch.object(self.service,'handoff',side_effect=collision):
            with self.assertRaisesRegex(WorkflowError,'WRITE_FAILED'):self.create(cover=False)
        failed=self.service.page(self.project['id'])['items'][0];self.assertEqual((Path(failed['output_location'])/'KEEP.txt').read_text(),'owned collision fixture')
        with self.assertRaisesRegex(WorkflowError,'OUTPUT_UNAVAILABLE'):self.create(cover=False)
        self.assertEqual(self.count(),1)

    def test_resume_from_history_without_browser_storage_and_abandon_keeps_custody(self):
        self.original_handoff=self.service.handoff
        with patch.object(self.service,'handoff',side_effect=self.crash_handoff):
            with self.assertRaises(SimulatedProcessExit):self.create(cover=False)
        held=self.service.page(self.project['id'])['items'][0]
        self.service=NativeManualDelivery(Store(self.root),self.config)
        done=self.service.resume(self.project['id'],held['export_id']);self.assertEqual(done['status'],'ready')
        with self.assertRaisesRegex(WorkflowError,'CANNOT_ABANDON'):self.service.abandon(self.project['id'],done['export_id'])
        with patch('services.windows_native.manual_delivery.shutil.copyfile',side_effect=OSError('owned write failure')):
            with self.assertRaises(WorkflowError):self.create(cover=False,request_key='explicit-abandon-failed-key')
        failed=next(v for v in self.service.page(self.project['id'])['items'] if v['status']=='failed')
        abandoned=self.service.abandon(self.project['id'],failed['export_id']);self.assertEqual(abandoned['status'],'abandoned')
        with self.assertRaisesRegex(WorkflowError,'ABANDONED'):self.service.resume(self.project['id'],failed['export_id'])
        with self.assertRaisesRegex(WorkflowError,'ABANDONED'):self.create(cover=False,request_key='explicit-abandon-failed-key')
        self.assertEqual(file_sha(Path(done['output_location'])/'final-video.mp4'),self.video_hash)

    def test_backup_restore_includes_export_copy_cover_metadata_and_files(self):
        from services.windows_native.backup import create_backup,restore_backup,database_status
        from services.windows_native.pipeline import Config
        done=self.create(cover=True);archive=Path(self.temp.name)/'owned-export-backup.zip';destination=Path(self.temp.name)/'restored-export'
        receipt=create_backup(self.config,archive);counts=receipt['database_status']['workflow.sqlite3']['counts']
        self.assertEqual(counts['native_manual_exports'],1);self.assertEqual(counts['native_delivery_copy'],0)
        restored=restore_backup(archive,destination,expected_sha256=receipt['sha256'])
        config=Config.load(restored['runtime_config_path']);service=NativeManualDelivery(Store(destination),config)
        recovered=service.get(self.project['id'],done['export_id']);self.assertEqual(recovered['manifest'],done['manifest'])
        self.assertEqual(file_sha(service.file(self.project['id'],done['export_id'],'final-video.mp4')),self.video_hash)
        self.assertEqual(database_status(destination/'workflow.sqlite3')['active_operations'],0)

    def test_real_owned_child_exit_after_handoff_releases_lease_and_reconciles(self):
        config_path=Path(self.temp.name)/'owned-child-config.json';request_path=Path(self.temp.name)/'owned-child-request.json'
        config_path.write_text(json.dumps(replace(self.config,secret_file=Path(self.temp.name)/'absent-provider',assemblyai_secret_file=Path(self.temp.name)/'absent-asr').dump()),encoding='utf-8')
        request_path.write_text(self.request(cover=False).model_dump_json(),encoding='utf-8')
        code='''import os,sys
from pathlib import Path
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.manual_delivery import NativeManualDelivery,DeliveryCreate
c=Config.load(sys.argv[1]);s=NativeManualDelivery(Store(c.data_root),c)
handoff=s.handoff
def crash(row,stage):
    handoff(row,stage)
    os._exit(86)
s.handoff=crash
s.create(sys.argv[3],DeliveryCreate.model_validate_json(Path(sys.argv[2]).read_bytes()))
'''
        result=subprocess.run([sys.executable,'-X','utf8','-c',code,str(config_path),str(request_path),self.project['id']],
            capture_output=True,timeout=90,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertEqual(result.returncode,86,result.stderr.decode('utf-8',errors='replace'))
        held=self.service.page(self.project['id'])['items'][0];self.assertEqual(held['status'],'preparing')
        self.service=NativeManualDelivery(Store(self.root),self.config)
        done=self.service.resume(self.project['id'],held['export_id']);self.assertEqual(done['status'],'ready');self.assertEqual(self.count(),1)
