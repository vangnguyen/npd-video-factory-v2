"""Explicit new takes and project/series casting reuse. No real voices or UAT."""
import copy,unittest
from services.windows_native.tests import test_dialogue_runtime as runtime
from services.windows_native.tests import test_dialogue_audio as audio
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.dialogue_takes import NativeDialogueTakes
from services.windows_native.drama_series import NativeDramaSeries

class DialogueReuseTests(unittest.TestCase):
    setUp=runtime.DialogueRuntimeTests.setUp
    tearDown=runtime.DialogueRuntimeTests.tearDown
    cast=runtime.DialogueRuntimeTests.cast
    save_cast=runtime.DialogueRuntimeTests.save_cast
    compile=runtime.DialogueRuntimeTests.compile
    approved_job=runtime.DialogueRuntimeTests.approved_job
    prepare=runtime.DialogueRuntimeTests.prepare

    def take(self,**changes):
        project=self.store.get(self.project['id'])
        return {'revision':project['revision'],'expected_casting_sha256':project['document']['drama_casting']['sha256'],
            'request_key':'explicit-new-take-'+str(project['revision']),'line_ids':[audio.LINE_A],**changes}
    def series_body(self,**changes):
        project=self.store.get(self.project['id'])
        return {'revision':project['revision'],'request_key':'explicit-series-save-'+str(project['revision']),'expected_version':0,'name':'Bộ phim fixture',**changes}

    def test_server_generated_new_take_reuses_other_actor_and_requires_new_compilation_approval(self):
        _,_,out=self.prepare();original=file_sha(out/'voice.wav');service=NativeDialogueTakes(self.store,self.library);body=self.take();done=service.create(self.project['id'],body,actor_ref='FIXTURE')
        self.assertEqual(set(done['takes']),{audio.LINE_A});self.assertRegex(done['takes'][audio.LINE_A],r'^take_[a-f0-9]{32}$')
        project=self.store.get(self.project['id']);self.assertIsNone(project['approval'])
        with self.assertRaisesRegex(WorkflowError,'SPECIFICATION_STALE'):self.store.approve(project['id'],project['revision'],'FIXTURE',True,purpose='narration')
        self.compile();_,_,new=self.prepare();self.assertEqual(len(self.adapter.calls),3);self.assertEqual(self.adapter.calls[-1]['line_id'],audio.LINE_A)
        self.assertEqual(file_sha(out/'voice.wav'),original);self.assertNotEqual(file_sha(new/'voice.wav'),original)

    def test_take_exact_retry_after_later_edit_keeps_nonce_and_does_not_rewind(self):
        service=NativeDialogueTakes(self.store,self.library);body=self.take();one=service.create(self.project['id'],body,actor_ref='FIXTURE')
        self.assertTrue(service.create(self.project['id'],body,actor_ref='FIXTURE')['idempotent_replay'])
        project=self.store.shot_view(self.project['id']);self.store.mutate_shots(project['id'],project['revision'],{'type':'update',
            'shot_id':project['shot_timeline']['shots'][0]['shot_id'],'values':{'on_screen_text':'Later visual edit'}})
        before=self.store.get(project['id']);replay=service.create(project['id'],body,actor_ref='FIXTURE')
        self.assertFalse(replay['current_for_project']);self.assertEqual(replay['takes'],one['takes']);self.assertEqual(self.store.get(project['id']),before)
        with self.assertRaisesRegex(WorkflowError,'KEY_CONFLICT'):service.create(project['id'],{**body,'line_ids':[audio.LINE_B]},actor_ref='FIXTURE')

    def test_unknown_duplicate_disabled_or_injected_takes_fail_before_mutation(self):
        service=NativeDialogueTakes(self.store,self.library);before=self.store.get(self.project['id'])
        for changes in ({'line_ids':['line_'+'f'*32]},{'line_ids':[audio.LINE_A,audio.LINE_A]},{'revision':True},{'take':'take_'+'1'*32}):
            with self.subTest(changes=changes),self.assertRaises(WorkflowError):service.create(self.project['id'],self.take(**changes),actor_ref='FIXTURE')
            self.assertEqual(self.store.get(self.project['id']),before)
        service.create(self.project['id'],self.take(),actor_ref='FIXTURE');configuration=copy.deepcopy(self.configuration);configuration['lines'][0]['enabled']=False;self.save_cast(configuration)
        self.assertEqual(self.store.get(self.project['id'])['document']['dialogue_delivery_takes'],{})
        with self.assertRaisesRegex(WorkflowError,'ACTIVE_DIALOGUE_LINE_REQUIRED'):service.create(self.project['id'],self.take(),actor_ref='FIXTURE')

    def test_series_copy_has_no_lines_or_approval_and_voice_can_appear_in_other_films(self):
        service=NativeDramaSeries(self.store,self.library);before=self.store.get(self.project['id']);saved=service.write(self.project['id'],self.series_body(),actor_ref='FIXTURE')
        self.assertEqual(self.store.get(self.project['id']),before);series=saved['series'];self.assertEqual(series['configuration']['lines'],[])
        other=self.store.create('Another film','No inference');result=service.write(other['id'],{'revision':other['revision'],'request_key':'explicit-series-other-film',
            'series_id':series['series_id'],'version':series['version'],'expected_sha256':series['sha256']},apply=True,actor_ref='FIXTURE')
        self.assertFalse(result['approval_inherited']);self.assertIsNone(self.store.get(other['id'])['approval'])
        self.assertEqual(result['casting']['configuration']['casting'],self.configuration['casting']);self.assertFalse(result['casting']['configuration']['narrator_enabled'])
        self.assertTrue(all('character_id' not in v['definition'] for v in self.library.page()['items']));self.assertEqual(self.adapter.calls,[])

    def test_series_versions_and_idempotency_preserve_historical_casting(self):
        service=NativeDramaSeries(self.store,self.library);body=self.series_body();first=service.write(self.project['id'],body,actor_ref='FIXTURE')['series'];old=copy.deepcopy(first)
        self.assertTrue(service.write(self.project['id'],body,actor_ref='FIXTURE')['idempotent_replay'])
        newbody=self.series_body(series_id=first['series_id'],expected_version=1,request_key='explicit-series-version-two',name='Bộ phim đổi tên')
        second=service.write(self.project['id'],newbody,actor_ref='FIXTURE')['series'];self.assertEqual(second['version'],2)
        self.assertEqual(service.page()['items'],[second])
        with self.store.transaction() as con:self.assertEqual(service.record(con,first['series_id'],1),old)
        with self.assertRaisesRegex(WorkflowError,'SERIES_VERSION_CHANGED'):service.write(self.project['id'],{**newbody,'request_key':'explicit-series-stale-version'},actor_ref='FIXTURE')
        with self.assertRaisesRegex(WorkflowError,'KEY_CONFLICT'):service.write(self.project['id'],{**body,'name':'Different request'},actor_ref='FIXTURE')

    def test_series_cannot_drop_existing_unmatched_character_lines_or_refresh_voice_rights(self):
        service=NativeDramaSeries(self.store,self.library);series=service.write(self.project['id'],self.series_body(),actor_ref='FIXTURE')['series']
        configuration=copy.deepcopy(self.configuration);newid='chr_'+'e'*32;configuration['characters'][0]['character_id']=newid
        configuration['casting'][0]['character_id']=newid;configuration['lines'][0]['character_id']=newid;self.save_cast(configuration)
        project=self.store.get(self.project['id']);body={'revision':project['revision'],'request_key':'explicit-incompatible-series-apply',
            'series_id':series['series_id'],'version':series['version'],'expected_sha256':series['sha256']}
        with self.assertRaisesRegex(WorkflowError,'CHARACTER_REVIEW_REQUIRED'):service.write(project['id'],body,apply=True,actor_ref='FIXTURE')
        self.assertEqual(self.store.get(project['id']),project);self.assertEqual(self.adapter.calls,[])

    def test_writer_revocation_rolls_back_take_and_series(self):
        before=self.store.get(self.project['id'])
        for callback in (lambda authorized:NativeDialogueTakes(self.store,self.library).create(self.project['id'],self.take(),actor_ref='FIXTURE',authorization_check=authorized),
            lambda authorized:NativeDramaSeries(self.store,self.library).write(self.project['id'],self.series_body(),actor_ref='FIXTURE',authorization_check=authorized)):
            calls=[]
            def authorized():
                calls.append(True)
                if len(calls)>1:raise WorkflowError('EXPLICIT_WRITER_REVOKED')
            with self.assertRaisesRegex(WorkflowError,'WRITER_REVOKED'):callback(authorized)
            self.assertEqual(self.store.get(self.project['id']),before)

    def test_backup_restore_preserves_takes_series_and_receipts(self):
        from dataclasses import replace
        from services.windows_native.backup import create_backup,restore_backup
        from services.windows_native.pipeline import Config
        from services.windows_native.store import Store
        from services.windows_native.voice_library import NativeVoiceLibrary
        takes=NativeDialogueTakes(self.store,self.library).create(self.project['id'],self.take(),actor_ref='FIXTURE')
        series=NativeDramaSeries(self.store,self.library).write(self.project['id'],self.series_body(),actor_ref='FIXTURE')['series']
        config=replace(self.config,secret_file=self.base/'private/absent',assemblyai_secret_file=self.base/'private/absent-asr');archive=self.base/'series.zip'
        backup=create_backup(config,archive);counts=backup['database_status']['workflow.sqlite3']['counts']
        self.assertEqual((counts['native_dialogue_takes'],counts['native_drama_series'],counts['native_drama_series_writes']),(1,1,1))
        restored=Config.load(restore_backup(archive,self.base/'restored',expected_sha256=backup['sha256'])['runtime_config_path']);store=Store(restored.data_root);library=NativeVoiceLibrary(store)
        self.assertEqual(NativeDramaSeries(store,library).page()['items'],[series]);self.assertEqual(store.get(self.project['id'])['document']['dialogue_delivery_takes'],takes['takes'])
