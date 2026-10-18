"""Compiled approval inputs over SQLite; explicit tone fixtures, no human or provider acceptance."""
import copy,json,unittest
from services.windows_native.tests import test_dialogue_audio as fixtures
from services.windows_native.dialogue_binding import NativeDialogueCompiler,specification,validate,inputs
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.contracts import WorkflowError,digest,PROFILE_SHA

class DialogueBindingTests(unittest.TestCase):
    setUp=fixtures.DialogueAudioTests.setUp
    tearDown=fixtures.DialogueAudioTests.tearDown
    cast=fixtures.DialogueAudioTests.cast
    save_cast=fixtures.DialogueAudioTests.save_cast

    def compiler(self):return NativeDialogueCompiler(self.store,self.library,self.providers)
    def fit(self):
        project=self.store.get(self.project['id'])
        return self.store.set_brand(project['id'],project['revision'],'vang-nguyen','personal-30',duration_mode=FIT_NARRATION_POLICY)
    def body(self,**changes):
        project=self.store.get(self.project['id'])
        return {'revision':project['revision'],'expected_version':(project['document'].get('compiled_dialogue') or {}).get('version',0),
            'request_key':'explicit-compile-'+str(project['revision']),**changes}
    def compile(self):
        self.fit();return self.compiler().compile(self.project['id'],self.body(),actor_ref='EXPLICIT COMPILE FIXTURE — NOT UAT')

    def test_spec_pins_two_explicit_voices_provider_and_script_without_dispatch_or_approval(self):
        result=self.compile();project=self.store.get(self.project['id']);record=validate(project['document'],self.library,providers=self.providers,project_id=project['id'])
        self.assertEqual(record,result['specification']);self.assertEqual(len(record['voice_bindings']),2)
        self.assertNotEqual(record['profile_sha256'],PROFILE_SHA);self.assertEqual(record['provider_evidence_modes'],{'explicit-fixture':'explicit-mock'})
        self.assertIsNone(project['approval']);self.assertFalse(result['human_approval_granted']);self.assertEqual(self.adapter.calls,[])
        # Compiling alone must not remove the old execution fence.
        with self.assertRaisesRegex(WorkflowError,'DRAMA_DIALOGUE_AUDIO_REQUIRED'):self.store.approve(project['id'],project['revision'],'EXPLICIT FIXTURE',True)

    def test_visual_duration_crop_and_output_edits_keep_voice_inputs_but_dialogue_change_stales_spec(self):
        self.compile();project=self.store.shot_view(self.project['id']);before=specification(project['document'])
        shot=project['shot_timeline']['shots'][0]
        changed=self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'duration':45,'on_screen_text':'New visible title'}})
        self.assertEqual(specification(changed['document']),before)
        configuration=copy.deepcopy(self.configuration);configuration['lines'][0]['pause_after_seconds']=.3;self.save_cast(configuration)
        with self.assertRaisesRegex(WorkflowError,'SPECIFICATION_STALE'):specification(self.store.get(project['id'])['document'])
        self.assertEqual(self.adapter.calls,[])

    def test_provider_signature_or_evidence_mode_change_cannot_reuse_compiled_approval(self):
        self.compile();document=self.store.get(self.project['id'])['document'];self.adapter.configuration_sha256='2'*64
        with self.assertRaisesRegex(WorkflowError,'PROVIDER_CONFIGURATION_CHANGED'):validate(document,self.library,providers=self.providers)
        self.adapter.configuration_sha256='1'*64;self.adapter.evidence_mode='local-real'
        with self.assertRaisesRegex(WorkflowError,'PROVIDER_CONFIGURATION_CHANGED'):validate(document,self.library,providers=self.providers)
        self.assertEqual(self.adapter.calls,[])

    def test_voice_version_revocation_or_foreign_project_rejected(self):
        self.compile();document=self.store.get(self.project['id'])['document']
        with self.assertRaisesRegex(WorkflowError,'SCOPE_CHANGED'):validate(document,self.library,project_id='0'*32)
        voice=self.voices[0];self.library.update(voice['voice_id'],{'expected_version':1,'request_key':'explicit-compiled-voice-revoke',
            'definition':{**voice['definition'],'rights_status':'blocked'}},actor_ref='EXPLICIT FIXTURE')
        with self.assertRaisesRegex(WorkflowError,'VOICE_BINDING_CHANGED'):validate(document,self.library)
        self.assertEqual(self.adapter.calls,[])

    def test_missing_rights_paid_or_unsupported_adapter_blocks_compile_without_document_change(self):
        self.fit();before=self.store.get(self.project['id']);self.adapter.paid=True
        with self.assertRaisesRegex(WorkflowError,'PAID_PROVIDER_NOT_ENABLED'):self.compiler().compile(self.project['id'],self.body(),actor_ref='FIXTURE')
        self.assertEqual(self.store.get(self.project['id']),before)
        self.adapter.paid=False;self.adapter.validate=lambda *_:(_ for _ in ()).throw(WorkflowError('EXPLICIT_UNSUPPORTED'))
        with self.assertRaisesRegex(WorkflowError,'EXPLICIT_UNSUPPORTED'):self.compiler().compile(self.project['id'],self.body(),actor_ref='FIXTURE')
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.adapter.calls,[])

    def test_exact_retry_after_project_edit_returns_historical_receipt_without_rewind(self):
        self.fit();compiler=self.compiler();body=self.body();first=compiler.compile(self.project['id'],body,actor_ref='FIXTURE')
        replay=compiler.compile(self.project['id'],body,actor_ref='FIXTURE');self.assertTrue(replay['idempotent_replay']);self.assertTrue(replay['current_for_project'])
        project=self.store.shot_view(self.project['id']);shot=project['shot_timeline']['shots'][0]
        self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'on_screen_text':'Changed later title'}})
        before=self.store.get(project['id']);replay=compiler.compile(project['id'],body,actor_ref='FIXTURE')
        self.assertFalse(replay['current_for_project']);self.assertEqual(replay['specification'],first['specification']);self.assertEqual(self.store.get(project['id']),before)
        with self.assertRaisesRegex(WorkflowError,'KEY_CONFLICT'):compiler.compile(project['id'],{**body,'expected_version':1},actor_ref='FIXTURE')

    def test_script_mismatch_inactive_narrator_and_bad_take_are_explicit(self):
        config=copy.deepcopy(self.configuration);config['lines'][0]['text']='Not in the canonical shot.';self.save_cast(config)
        with self.assertRaisesRegex(WorkflowError,'CANONICAL_SCRIPT_BINDING_CHANGED'):self.compile()
        self.save_cast(self.configuration);document=copy.deepcopy(self.store.get(self.project['id'])['document'])
        document['dialogue_delivery_takes']={fixtures.LINE_A:'not-a-take'}
        with self.assertRaisesRegex(WorkflowError,'TAKES_INVALID'):inputs(document)
        document['dialogue_delivery_takes']={fixtures.LINE_A:'take_'+'3'*32};self.assertEqual(inputs(document)['delivery_takes'],document['dialogue_delivery_takes'])
        self.assertEqual(self.adapter.calls,[])

    def test_fixed_template_cannot_create_long_silent_dialogue_export(self):
        with self.assertRaisesRegex(WorkflowError,'FIT_NARRATION_TEMPLATE_REQUIRED'):self.compiler().compile(self.project['id'],self.body(),actor_ref='FIXTURE')
        self.assertNotIn('compiled_dialogue',self.store.get(self.project['id'])['document']);self.assertEqual(self.adapter.calls,[])

    def test_manifest_tamper_and_approval_race_rejected(self):
        self.compile();document=copy.deepcopy(self.store.get(self.project['id'])['document']);document['compiled_dialogue']['profile_sha256']=PROFILE_SHA
        with self.assertRaisesRegex(WorkflowError,'SPECIFICATION_CHANGED'):specification(document)
        record=document['compiled_dialogue'];record['sha256']=digest({k:v for k,v in record.items() if k!='sha256'})
        with self.assertRaisesRegex(WorkflowError,'SPECIFICATION_CHANGED'):specification(document)
        body=self.body();before=self.store.get(self.project['id']);calls=[]
        def revoked():
            calls.append(True)
            if len(calls)>1:raise WorkflowError('EXPLICIT_WRITER_REVOKED')
        with self.assertRaisesRegex(WorkflowError,'WRITER_REVOKED'):self.compiler().compile(self.project['id'],body,actor_ref='FIXTURE',authorization_check=revoked)
        self.assertEqual(self.store.get(self.project['id']),before)

    def test_backup_restore_retains_compiler_receipt_and_pinned_inputs(self):
        from dataclasses import replace
        from services.windows_native.backup import create_backup,restore_backup
        from services.windows_native.pipeline import Config
        from services.windows_native.store import Store
        from services.windows_native.voice_library import NativeVoiceLibrary
        self.compile();config=replace(self.config,secret_file=self.base/'secrets/absent',assemblyai_secret_file=self.base/'secrets/absent-asr')
        archive=self.base/'compile.zip';backup=create_backup(config,archive);self.assertEqual(backup['database_status']['workflow.sqlite3']['counts']['native_dialogue_compiles'],1)
        restored=Config.load(restore_backup(archive,self.base/'restored',expected_sha256=backup['sha256'])['runtime_config_path'])
        store=Store(restored.data_root);document=store.get(self.project['id'])['document']
        self.assertEqual(validate(document,NativeVoiceLibrary(store),providers=self.providers),specification(document));self.assertEqual(self.adapter.calls,[])
