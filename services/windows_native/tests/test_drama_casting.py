"""Project casting drafts over real SQLite; no voice synthesis or Owner acceptance."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError
from services.windows_native.voice_library import NativeVoiceLibrary
from services.windows_native.drama_casting import NativeDramaCasting,require_execution_ready
from services.windows_native.tests.test_voice_library import definition

CHAR_A='chr_'+'a'*32;CHAR_B='chr_'+'b'*32;NARRATOR='chr_'+'c'*32

class DramaCastingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.root=self.base/'state';self.store=Store(self.root)
        self.library=NativeVoiceLibrary(self.store);self.service=NativeDramaCasting(self.store,self.library)
        self.voices=[self.library.create({'request_key':'explicit-cast-voice-key-'+str(i),'definition':definition(provider_voice_id='fixture-'+str(i))},actor_ref='EXPLICIT FIXTURE') for i in (1,2)]
        self.project=self.store.create('Drama draft fixture','No inference or real voice')
    def tearDown(self):self.temp.cleanup()
    def config(self):
        return {'characters':[{'character_id':CHAR_A,'name':'An'},{'character_id':CHAR_B,'name':'Bình'}],
            'casting':[{'character_id':character,'voice_id':voice['voice_id'],'voice_version':voice['version'],'voice_sha256':voice['definition_sha256']} for character,voice in zip((CHAR_A,CHAR_B),self.voices)],
            'lines':[{'line_id':'line_'+'d'*32,'character_id':CHAR_A,'text':'Vang Nguyễn giới thiệu.'},
                {'line_id':'line_'+'e'*32,'character_id':CHAR_B,'text':'Vinhomes Saigon Park.'}]}
    def body(self,**changes):
        p=self.store.get(self.project['id']);v=self.service.view(p['id'])['casting']
        return {'revision':p['revision'],'expected_version':v['version'] if v else 0,'request_key':'explicit-project-cast-key','configuration':self.config(),**changes}
    def save(self,body=None):return self.service.save(self.project['id'],body or self.body(),actor_ref='EXPLICIT TEST CASTING — NOT UAT')

    def test_two_characters_explicit_cast_narrator_disabled_and_revision_invalidations(self):
        before=self.store.get(self.project['id']);result=self.save();after=self.store.get(self.project['id'])
        self.assertEqual(after['revision'],before['revision']+1);self.assertIsNone(after['approval']);self.assertIsNone(after['document']['proposal'])
        self.assertFalse(result['casting']['configuration']['narrator_enabled']);self.assertFalse(result['per_line_tts_ready'])
        self.assertEqual(len(result['casting']['configuration']['casting']),2);self.assertEqual(after['jobs'],[])
        self.assertEqual([v['revision'] for v in self.store.versions(self.project['id'])],[2,1])
        self.assertFalse(any('character_id' in v['definition'] for v in self.library.page()['items']))

    def test_one_global_voice_can_be_reused_by_another_character_in_another_film(self):
        first=self.save();other=self.store.create('Other film','No generation');config=self.config();config['characters'][0]['name']='Another character'
        saved=self.service.save(other['id'],{'revision':other['revision'],'expected_version':0,'request_key':'explicit-other-film-key','configuration':config},actor_ref='fixture')
        self.assertEqual(saved['casting']['configuration']['casting'][0]['voice_id'],first['casting']['configuration']['casting'][0]['voice_id'])
        self.assertEqual(len(self.library.page()['items']),2)

    def test_unassigned_cast_is_a_draft_and_never_auto_selects_voice(self):
        config=self.config();config['casting']=[];result=self.save(self.body(configuration=config))
        self.assertEqual(result['casting']['configuration']['casting'],[]);self.assertFalse(result['per_line_tts_ready']);self.assertEqual(result['provider_calls'],0)

    def test_strict_unknown_duplicate_references_and_changed_voice_hash_rollback(self):
        original=self.store.get(self.project['id']);cases=[]
        bad=self.config();bad['casting'].append(copy.deepcopy(bad['casting'][0]));cases.append(bad)
        bad=self.config();bad['lines'][0]['character_id']=NARRATOR;cases.append(bad)
        bad=self.config();bad['narrator_enabled']=True;cases.append(bad)
        bad=self.config();bad['lines'][0]['speed']=True;cases.append(bad)
        bad=self.config();bad['lines'][0]['pause_after_seconds']=float('nan');cases.append(bad)
        bad=self.config();bad['casting'][0]['voice_sha256']='0'*64;cases.append(bad)
        bad=self.config();bad['lines'][0]['shot_id']='shot_'+'f'*32;cases.append(bad)
        for config in cases:
            with self.subTest(config=config),self.assertRaises(WorkflowError):self.save(self.body(configuration=config))
            self.assertEqual(self.store.get(self.project['id']),original)

    def test_CAS_replay_after_later_edit_does_not_restore_old_revision_or_approval(self):
        body=self.body();done=self.save(body);later=self.store.save(self.project['id'],done['project_revision_at_write'],prompt='Later draft')
        replay=self.save(body);self.assertTrue(replay['idempotent_replay']);self.assertFalse(replay['current_for_project']);self.assertEqual(self.store.get(self.project['id']),later)
        changed=self.config();changed['characters'][0]['name']='Changed character'
        with self.assertRaisesRegex(WorkflowError,'REQUEST_KEY_CONFLICT'):self.save({**body,'configuration':changed})
        with self.assertRaisesRegex(WorkflowError,'CASTING_VERSION_CHANGED'):self.save(self.body(expected_version=0,request_key='explicit-stale-cast-new-key'))

    def test_changed_library_version_requires_explicit_reselection_in_cast(self):
        voice=self.voices[0];self.library.update(voice['voice_id'],{'expected_version':1,'request_key':'explicit-voice-version-change','definition':{**voice['definition'],'display_name':'new display'}},actor_ref='fixture')
        before=self.store.get(self.project['id'])
        with self.assertRaisesRegex(WorkflowError,'VOICE_BINDING_CHANGED'):self.save()
        self.assertEqual(self.store.get(self.project['id']),before)

    def test_incomplete_drama_cannot_dispatch_legacy_single_voice_via_approval_or_worker(self):
        result=self.save();project=self.store.get(self.project['id'])
        for purpose in ('narration','production'):
            with self.assertRaisesRegex(WorkflowError,'DIALOGUE_AUDIO_REQUIRED'):self.store.approve(project['id'],project['revision'],'EXPLICIT FIXTURE NOT UAT',True,purpose=purpose)
        from services.windows_native.pipeline import Pipeline
        for kind in ('narration','render'):
            with self.assertRaisesRegex(WorkflowError,'DIALOGUE_AUDIO_REQUIRED'):
                Pipeline(object()).run({'kind':kind,'snapshot':{'document':project['document']}},lambda _:None)
        self.assertEqual(self.store.get(project['id'])['jobs'],[]);self.assertFalse((self.root/'jobs').exists());self.assertIsNone(require_execution_ready({}))

    def test_revoked_writer_does_not_create_revision_receipt_or_casting(self):
        before=self.store.get(self.project['id']);calls=[]
        def authorized():
            calls.append(True)
            if len(calls)==2:raise WorkflowError('EXPLICIT_CAST_AUTH_REVOKED')
        with self.assertRaisesRegex(WorkflowError,'AUTH_REVOKED'):self.service.save(self.project['id'],self.body(),actor_ref='fixture',authorization_check=authorized)
        self.assertEqual(self.store.get(self.project['id']),before)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_drama_writes').fetchone()[0],0)

    def test_actual_backup_restore_keeps_project_cast_and_global_voice_separate(self):
        self.save();before=self.service.view(self.project['id'])
        from services.windows_native.pipeline import Config
        from services.windows_native.backup import create_backup,restore_backup
        config=Config(data_root=self.root,runtime_root=self.base/'runtime',secret_file=self.base/'private'/'absent-key',assemblyai_secret_file=self.base/'private'/'absent-asr')
        archive=self.base/'casting.zip';backup=create_backup(config,archive);self.assertEqual(backup['database_status']['workflow.sqlite3']['counts']['native_drama_writes'],1)
        restore_backup(archive,self.base/'restored',expected_sha256=backup['sha256']);store=Store(self.base/'restored');library=NativeVoiceLibrary(store)
        self.assertEqual(NativeDramaCasting(store,library).view(self.project['id']),before);self.assertEqual(len(library.page()['items']),2)

if __name__=='__main__':unittest.main()
