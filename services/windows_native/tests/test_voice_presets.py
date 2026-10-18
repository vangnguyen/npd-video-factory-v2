"""Pinned installed metadata and bounded queue contracts; no live inference or listening acceptance."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError
from services.windows_native.voice_library import NativeVoiceLibrary
from services.windows_native.voice_presets import licensed_inventory,register_installed,verify_definition
from services.windows_native.voice_auditions import NativeVoiceAuditions,SAMPLE_TEXT

class VoicePresetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.config=Config(data_root=Path(self.temp.name)/'data')
        self.library=NativeVoiceLibrary(Store(self.config.data_root))
    def test_installed_source_license_registration_is_idempotent_and_does_not_recast(self):
        inventory=licensed_inventory(self.config);self.assertEqual(len(inventory),25)
        self.assertEqual(len({v['preset_payload_sha256'] for v in inventory}),25)
        self.assertEqual(len([v for v in inventory if v['metadata']['featured']]),10)
        first=register_installed(self.library,self.config,actor_ref='explicit-owner-task');second=register_installed(self.library,self.config,actor_ref='explicit-owner-task')
        self.assertEqual([v['voice_id'] for v in first['items']],[v['voice_id'] for v in second['items']]);self.assertEqual(len(self.library.page()['items']),25)
        self.assertFalse(first['human_voice_uat_complete']);self.assertFalse(first['existing_castings_changed']);self.assertEqual(first['provider_calls'],0)
    def test_ordinary_create_cannot_claim_internal_source_licensed_rights(self):
        definition=licensed_inventory(self.config)[0]['definition']
        with self.assertRaisesRegex(WorkflowError,'INTERNAL_IMPORT_REQUIRED'):self.library.create({'request_key':'forged-import-0001','definition':definition},actor_ref='ordinary-client')
    def test_changed_license_and_wrong_definition_cannot_reuse_source_permission(self):
        definition=copy.deepcopy(licensed_inventory(self.config)[0]['definition']);definition['provider_voice_id']='Thùy Dung'
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):verify_definition(self.config,definition)
        with patch('services.windows_native.voice_presets.file_sha',return_value='0'*64),self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):licensed_inventory(self.config)
    def test_open_page_never_starts_tts_duplicate_click_returns_same_intent_and_restart_requires_explicit_retry(self):
        records=register_installed(self.library,self.config,actor_ref='explicit-owner-task')['items'];auditions=NativeVoiceAuditions(self.library,self.config)
        with patch.object(auditions,'start') as start:
            self.assertFalse(auditions.page()['inference_dispatched']);start.assert_not_called()
            body={'voice_id':records[0]['voice_id'],'voice_version':1,'kind':'sample'}
            first=auditions.submit(body);second=auditions.submit(body);self.assertEqual(first['sample_id'],second['sample_id']);self.assertEqual(first['text'],SAMPLE_TEXT)
            self.assertEqual(start.call_count,1)
        restored=NativeVoiceAuditions(self.library,self.config);self.assertEqual(restored.page()['items'][0]['state'],'outcome_unknown')
        with patch.object(restored,'start') as start:
            self.assertEqual(restored.submit(body)['state'],'outcome_unknown');start.assert_not_called()
            result=restored.submit({**body,'retry':True});self.assertEqual(result['attempt'],2);start.assert_called_once()
    def test_queue_limit_rejects_eleventh_and_core_job_blocks_dispatch(self):
        records=register_installed(self.library,self.config,actor_ref='explicit-owner-task')['items'];auditions=NativeVoiceAuditions(self.library,self.config)
        with patch.object(auditions,'start'):
            for voice in records[:10]:auditions.submit({'voice_id':voice['voice_id'],'voice_version':1,'kind':'sample'})
            with self.assertRaisesRegex(WorkflowError,'QUEUE_FULL'):auditions.submit({'voice_id':records[10]['voice_id'],'voice_version':1,'kind':'sample'})
        self.assertEqual(len(auditions.page()['items']),10)
