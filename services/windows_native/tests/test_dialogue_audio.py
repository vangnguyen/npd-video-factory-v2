"""Actual PCM/cache/fault tests with explicitly synthetic tone adapters, never real speech."""
import copy,json,os,subprocess,sys,tempfile,unittest,wave
from pathlib import Path
import numpy as np
from services.windows_native.tests.test_shot_production import prepared
from services.windows_native.tests.test_voice_library import definition
from services.windows_native.voice_library import NativeVoiceLibrary
from services.windows_native.drama_casting import NativeDramaCasting
from services.windows_native.dialogue_audio import prepare,measure,recover_interrupted
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.store import Store

CHAR_A='chr_'+'a'*32;CHAR_B='chr_'+'b'*32;LINE_A='line_'+'c'*32;LINE_B='line_'+'d'*32

class ExplicitToneAdapter:
    configuration_sha256='1'*64
    evidence_mode='explicit-mock'
    paid=False
    def __init__(self):self.calls=[];self.failure=None;self.duration=.8;self.mode='tone'
    def validate(self,voice,line):
        if voice['source_type']!='provider_preset' or voice['model']!='not-a-real-model' or line['speed']!=1 or line['style']!='neutral':raise WorkflowError('EXPLICIT_FIXTURE_UNSUPPORTED')
    def synthesize(self,*,text,voice,line,take,request_key,target):
        self.calls.append({'voice':voice['provider_voice_id'],'line_id':line['line_id'],'request_key':request_key,'take':take})
        frequency={'fixture-1':440,'fixture-2':660,'fixture-3':880}[voice['provider_voice_id']]+(50 if take else 0)
        samples=(np.sin(np.arange(round(self.duration*48000))*2*np.pi*frequency/48000)*6000).astype('<i2')
        if self.mode=='silent':samples[:]=0
        if self.mode=='clipped':samples[:]=32767
        if self.mode=='broken':target.write_bytes(b'not WAV')
        else:
            with wave.open(str(target),'wb') as output:
                output.setnchannels(1);output.setsampwidth(2);output.setframerate(8000 if self.mode=='wrong_rate' else 48000);output.writeframes(samples.tobytes())
        if self.failure:raise self.failure
        return {'operation_id':'explicit-mock-operation-'+str(len(self.calls))}

class DialogueAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.root=self.base/'state';self.config,self.store,self.project=prepared(self.root)
        self.library=NativeVoiceLibrary(self.store);self.casting=NativeDramaCasting(self.store,self.library)
        self.voices=[self.library.create({'request_key':'explicit-audio-voice-key-'+str(i),'definition':definition(provider_voice_id='fixture-'+str(i),
            rights_status='owner_declared',license='Fixture only',source_reference='fixture://preset',permission_reference='Synthetic test declaration')},actor_ref='EXPLICIT FIXTURE') for i in (1,2,3)]
        shots=self.store.shot_view(self.project['id'])['shot_timeline']['shots']
        self.configuration={'characters':[{'character_id':CHAR_A,'name':'An'},{'character_id':CHAR_B,'name':'Bình'}],
            'casting':[self.cast(CHAR_A,self.voices[0]),self.cast(CHAR_B,self.voices[1])],
            'lines':[{'line_id':line,'character_id':char,'shot_id':shot['shot_id'],'text':shot['narration']} for line,char,shot in zip((LINE_A,LINE_B),(CHAR_A,CHAR_B),shots)]}
        self.save_cast(self.configuration);self.adapter=ExplicitToneAdapter();self.providers={'explicit-fixture':self.adapter}
    def tearDown(self):self.temp.cleanup()
    def cast(self,char,voice):return {'character_id':char,'voice_id':voice['voice_id'],'voice_version':voice['version'],'voice_sha256':voice['definition_sha256']}
    def save_cast(self,configuration):
        project=self.store.get(self.project['id']);existing=project['document'].get('drama_casting')
        return self.casting.save(project['id'],{'revision':project['revision'],'expected_version':existing['version'] if existing else 0,
            'request_key':'explicit-audio-cast-'+str(project['revision']),'configuration':configuration},actor_ref='AUTOMATED AUDIO FIXTURE — NOT UAT')
    def snapshot(self,**changes):
        document=copy.deepcopy(self.store.get(self.project['id'])['document']);document.update(changes)
        return {'document':document,'approval':{'snapshot_sha256':digest(document),'approval_scope':'narration_only',
            'source':'local_ui_human_review','reviewer':'AUTOMATED FIXTURE — NOT OWNER ACCEPTANCE'}}
    def run_audio(self,name='one',snapshot=None,**kwargs):return prepare(self.config,self.library,snapshot or self.snapshot(),self.providers,self.root/'jobs'/name,**kwargs)
    def cache_path(self,key):
        with self.store.transaction() as con:row=con.execute('SELECT relative_directory FROM native_dialogue_clips WHERE input_sha256=?',(key,)).fetchone()
        return self.root/row[0]

    def test_measured_two_speaker_audio_ignores_requested_target_duration_and_has_no_narrator(self):
        project=self.store.shot_view(self.project['id'])
        for shot in project['shot_timeline']['shots']:
            project=self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'duration':45}})
        result=self.run_audio();self.assertAlmostEqual(result['duration_seconds'],1.75,places=6)
        self.assertEqual([v['character_id'] for v in result['units']],[CHAR_A,CHAR_B]);self.assertEqual([v['scene'] for v in result['units']],[1,2])
        self.assertEqual(result['provider_adapter_calls'],2);self.assertEqual(result['evidence_modes'],['explicit-mock']);self.assertFalse(result['speech_detected'])
        self.assertFalse(result['human_voice_uat_complete']);self.assertIsNone(result['actual_cost'])
        actual=measure(self.root/'jobs/one/voice.wav');self.assertEqual(actual['frames'],84000);self.assertEqual(actual['activity']['trailing_silence_seconds'],0)

    def test_exact_replay_uses_physically_verified_cache_without_adapter_calls(self):
        first=self.run_audio();second=self.run_audio('two')
        self.assertEqual(len(self.adapter.calls),2);self.assertEqual(second['provider_adapter_calls'],0);self.assertEqual(second['reused_line_clips'],2)
        self.assertEqual(first['audio_sha256'],second['audio_sha256'])

    def test_character_voice_change_regenerates_only_affected_line_and_keeps_other_clip_bytes(self):
        first=self.run_audio();old=self.cache_path(first['units'][1]['cache_key'])/'line.wav';old_hash=file_sha(old)
        config=copy.deepcopy(self.configuration);config['casting'][0]=self.cast(CHAR_A,self.voices[2]);self.save_cast(config)
        second=self.run_audio('two');self.assertEqual(len(self.adapter.calls),3);self.assertEqual(self.adapter.calls[-1]['line_id'],LINE_A)
        self.assertEqual(second['units'][1]['cache_key'],first['units'][1]['cache_key']);self.assertEqual(file_sha(old),old_hash)
        self.assertNotEqual(second['profile_sha256'],first['profile_sha256'])

    def test_explicit_new_take_changes_only_target_and_never_replaces_old_cache(self):
        first=self.run_audio();old=self.cache_path(first['units'][0]['cache_key'])/'line.wav';old_hash=file_sha(old)
        snapshot=self.snapshot(dialogue_delivery_takes={LINE_A:'take_'+'1'*32});new=self.run_audio('two',snapshot)
        self.assertEqual(len(self.adapter.calls),3);self.assertEqual(new['reused_line_clips'],1)
        self.assertNotEqual(new['units'][0]['cache_key'],first['units'][0]['cache_key']);self.assertEqual(new['units'][1]['cache_key'],first['units'][1]['cache_key'])
        self.assertEqual(file_sha(old),old_hash)

    def test_changed_cached_pcm_is_rejected_without_rewrite_or_adapter_retry(self):
        first=self.run_audio();path=self.cache_path(first['units'][0]['cache_key'])/'line.wav';path.write_bytes(b'explicit corruption fixture')
        with self.assertRaisesRegex(WorkflowError,'PCM_INVALID|BYTES_CHANGED'):self.run_audio('two')
        self.assertEqual(len(self.adapter.calls),2);self.assertEqual(path.read_bytes(),b'explicit corruption fixture')

    def test_unknown_outcome_retains_intent_and_does_not_repeat_same_request(self):
        self.adapter.failure=TimeoutError('explicit unknown mock response')
        with self.assertRaisesRegex(WorkflowError,'OUTCOME_UNKNOWN'):self.run_audio()
        self.assertEqual(len(self.adapter.calls),1)
        with self.store.transaction() as con:row=con.execute('SELECT * FROM native_dialogue_clips').fetchone()
        self.assertEqual(row['state'],'failed');self.assertTrue((self.root/row['relative_directory']/'request-intent.json').is_file())
        self.adapter.failure=None
        with self.assertRaisesRegex(WorkflowError,'RECOVERY_REQUIRED'):self.run_audio('two')
        self.assertEqual(len(self.adapter.calls),1);self.assertFalse((self.root/'jobs/one/voice.json').exists())

    def test_missing_approval_or_changed_script_blocks_all_calls(self):
        snapshot=self.snapshot();snapshot['approval']=None
        with self.assertRaisesRegex(WorkflowError,'APPROVAL_REQUIRED'):self.run_audio(snapshot=snapshot)
        config=copy.deepcopy(self.configuration);config['lines'][0]['text']='A different approved-looking text.';self.save_cast(config)
        with self.assertRaisesRegex(WorkflowError,'SCRIPT_BINDING_CHANGED'):self.run_audio('two')
        self.assertEqual(self.adapter.calls,[]);self.assertFalse((self.root/'cache').exists())

    def test_paid_adapter_and_output_outside_workspace_are_disabled_before_dispatch(self):
        self.adapter.paid=True
        with self.assertRaisesRegex(WorkflowError,'PAID_PROVIDER_NOT_ENABLED'):self.run_audio()
        self.adapter.paid=False
        with self.assertRaisesRegex(WorkflowError,'OUTPUT_SCOPE_INVALID'):prepare(self.config,self.library,self.snapshot(),self.providers,self.base/'outside')
        self.assertEqual(self.adapter.calls,[]);self.assertFalse((self.base/'outside').exists())

    def test_silence_clipping_wrong_rate_and_broken_wav_cannot_become_ready(self):
        for i,mode in enumerate(('silent','clipped','wrong_rate','broken')):
            self.adapter.mode=mode;snapshot=self.snapshot(dialogue_delivery_takes={LINE_A:'take_'+f'{i:032x}'})
            with self.subTest(mode=mode),self.assertRaises(WorkflowError):self.run_audio(str(i),snapshot)
        with self.store.transaction() as con:self.assertEqual(con.execute("SELECT count(*) FROM native_dialogue_clips WHERE state='ready'").fetchone()[0],0)
        self.assertEqual(len(self.adapter.calls),4)

    def test_revoked_writer_after_inference_cannot_register_clip_or_final_metadata(self):
        calls=[]
        def authorized():
            calls.append(True)
            if len(calls)==5:raise WorkflowError('EXPLICIT_AUDIO_WRITER_REVOKED')
        with self.assertRaisesRegex(WorkflowError,'WRITER_REVOKED'):self.run_audio(authorization_check=authorized)
        self.assertEqual(len(self.adapter.calls),1);self.assertFalse((self.root/'jobs/one/voice.json').exists())
        with self.store.transaction() as con:self.assertEqual(con.execute("SELECT count(*) FROM native_dialogue_clips WHERE state='ready'").fetchone()[0],0)

    def test_evidence_mode_change_cannot_turn_mock_cache_into_real_provider_evidence(self):
        self.run_audio();self.adapter.evidence_mode='local-real'
        with self.assertRaisesRegex(WorkflowError,'BYTES_CHANGED'):self.run_audio('two')
        self.assertEqual(len(self.adapter.calls),2)

    def test_backup_restore_keeps_cache_custody_and_reuses_without_new_adapter_calls(self):
        self.run_audio()
        from dataclasses import replace
        from services.windows_native.backup import create_backup,restore_backup,database_status
        from services.windows_native.pipeline import Config
        config=replace(self.config,secret_file=self.base/'private'/'absent-key',assemblyai_secret_file=self.base/'private'/'absent-asr')
        archive=self.base/'dialogue.zip';backup=create_backup(config,archive);self.assertEqual(backup['database_status']['workflow.sqlite3']['counts']['native_dialogue_clips'],2)
        result=restore_backup(archive,self.base/'restored',expected_sha256=backup['sha256']);restored=Config.load(result['runtime_config_path'])
        library=NativeVoiceLibrary(Store(restored.data_root))
        meta=prepare(restored,library,self.snapshot(),self.providers,restored.data_root/'jobs/restored-new')
        self.assertEqual(meta['reused_line_clips'],2);self.assertEqual(len(self.adapter.calls),2)
        self.assertEqual(database_status(restored.data_root/'workflow.sqlite3')['active_operations'],0)

    def test_oversized_frame_header_is_rejected_before_allocating_frame_payload(self):
        import struct
        from unittest.mock import patch
        path=self.base/'huge-header.wav'
        path.write_bytes(b'RIFF'+struct.pack('<I',0xffffffff)+b'WAVEfmt '+struct.pack('<IHHIIHH',16,1,1,48000,96000,2,16)+b'data'+struct.pack('<I',0xfffffffc))
        with patch.object(wave.Wave_read,'readframes',side_effect=AssertionError('Oversized frame count must not be read')):
            with self.assertRaisesRegex(WorkflowError,'PCM_INVALID'):measure(path)

    def test_total_measured_duration_limit_fails_instead_of_truncating_dialogue(self):
        self.adapter.duration=100
        with self.assertRaisesRegex(WorkflowError,'DURATION_EXCEEDS_LIMIT'):self.run_audio()
        self.assertFalse((self.root/'jobs/one/voice.json').exists());self.assertFalse((self.root/'jobs/one/dialogue-audio.json').exists())
        with self.store.transaction() as con:self.assertEqual(con.execute("SELECT count(*) FROM native_dialogue_clips WHERE state='ready'").fetchone()[0],2)

    def test_voice_revoked_while_other_character_synthesizes_blocks_assembly(self):
        original=self.adapter.synthesize
        def revoke(**kwargs):
            value=original(**kwargs)
            if len(self.adapter.calls)==2:
                voice=self.voices[0];self.library.update(voice['voice_id'],{'expected_version':1,'request_key':'explicit-during-audio-revoke',
                    'definition':{**voice['definition'],'rights_status':'blocked'}},actor_ref='EXPLICIT FIXTURE')
            return value
        self.adapter.synthesize=revoke
        with self.assertRaisesRegex(WorkflowError,'VOICE_VERSION_CHANGED|RIGHTS_CONFIRMATION_REQUIRED'):self.run_audio()
        self.assertFalse((self.root/'jobs/one/voice.wav').exists());self.assertFalse((self.root/'jobs/one/voice.json').exists())

    def test_cache_preparing_state_blocks_offline_backup(self):
        from services.windows_native.backup import database_status,create_backup
        from dataclasses import replace
        original=self.adapter.synthesize
        def inspect(**kwargs):
            self.assertGreater(database_status(self.root/'workflow.sqlite3')['active_operations'],0)
            config=replace(self.config,secret_file=self.base/'private'/'absent-key',assemblyai_secret_file=self.base/'private'/'absent-asr')
            with self.assertRaises(WorkflowError):create_backup(config,self.base/'during-audio.zip')
            return original(**kwargs)
        self.adapter.synthesize=inspect;self.run_audio();self.assertFalse((self.base/'during-audio.zip').exists())

    def test_recovery_does_not_reclassify_a_live_inference_holding_the_lease(self):
        original=self.adapter.synthesize
        def inspect(**kwargs):
            self.assertEqual(recover_interrupted(self.library),{'recovered':0,'active':1,'automatic_provider_calls':0})
            return original(**kwargs)
        self.adapter.synthesize=inspect;self.run_audio()
        self.assertEqual(recover_interrupted(self.library),{'recovered':0,'active':0,'automatic_provider_calls':0})

    def test_real_owned_process_exit_preserves_ambiguous_intent_without_automatic_replay(self):
        from dataclasses import replace
        config_path=self.base/'owned-process-config.json';snapshot_path=self.base/'owned-process-snapshot.json'
        config_path.write_text(json.dumps(replace(self.config,secret_file=self.base/'private'/'absent-key',assemblyai_secret_file=self.base/'private'/'absent-asr').dump()))
        snapshot_path.write_text(json.dumps(self.snapshot(),ensure_ascii=False),encoding='utf-8')
        code='''import json,os,sys
from pathlib import Path
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.voice_library import NativeVoiceLibrary
from services.windows_native.dialogue_audio import prepare
from services.windows_native.tests.test_dialogue_audio import ExplicitToneAdapter
config=Config.load(sys.argv[1]);library=NativeVoiceLibrary(Store(config.data_root));adapter=ExplicitToneAdapter()
adapter.synthesize=lambda **kwargs:os._exit(89)
prepare(config,library,json.loads(Path(sys.argv[2]).read_text(encoding='utf-8')),{'explicit-fixture':adapter},config.data_root/'jobs/owned-exit')
'''
        result=subprocess.run([sys.executable,'-X','utf8','-c',code,str(config_path),str(snapshot_path)],capture_output=True,timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertEqual(result.returncode,89,result.stderr.decode('utf-8',errors='replace'))
        self.assertEqual(recover_interrupted(self.library),{'recovered':1,'active':0,'automatic_provider_calls':0})
        from services.windows_native.backup import database_status
        self.assertEqual(database_status(self.root/'workflow.sqlite3')['active_operations'],0)
        with self.assertRaisesRegex(WorkflowError,'RECOVERY_REQUIRED'):self.run_audio('after-exit')
        self.assertEqual(self.adapter.calls,[])
        done=self.run_audio('new-explicit-take',self.snapshot(dialogue_delivery_takes={LINE_A:'take_'+'9'*32}))
        self.assertEqual(done['provider_adapter_calls'],2);self.assertEqual(done['evidence_modes'],['explicit-mock'])

if __name__=='__main__':unittest.main()
