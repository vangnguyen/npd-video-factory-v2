"""Real owned SQLite and backup; voice definitions are explicit fixtures, no TTS."""
import copy,json,tempfile,unittest
from pathlib import Path
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError
from services.windows_native.voice_library import NativeVoiceLibrary

def definition(**changes):
    return {'display_name':'Giọng kiểm thử','provider':'explicit-fixture','model':'not-a-real-model','provider_voice_id':'fixture-A','locale':'vi-VN',**changes}

class VoiceLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.root=self.base/'state'
        self.store=Store(self.root);self.library=NativeVoiceLibrary(self.store)
    def tearDown(self):self.temp.cleanup()
    def create(self,**changes):return self.library.create({'request_key':'explicit-voice-create-key','definition':definition(**changes)},actor_ref='EXPLICIT TEST OWNER — NOT UAT')
    def update(self,voice,**changes):return self.library.update(voice['voice_id'],{'request_key':'explicit-voice-update-key','expected_version':voice['version'],
        'definition':{**voice['definition'],**changes}},actor_ref='EXPLICIT TEST OWNER — NOT UAT')
    def counts(self):
        with self.store.transaction() as con:return tuple(con.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('native_voice_versions','native_voice_writes'))

    def test_default_rights_unknown_restart_and_no_generation_claim(self):
        first=self.create();self.assertEqual(first['definition']['rights_status'],'unknown');self.assertFalse(first['human_voice_uat_complete'])
        self.assertEqual(first['provider_execution'],'NOT_CONFIGURED_BY_LIBRARY');self.assertEqual(self.counts(),(1,1))
        replay=self.create();self.assertTrue(replay['idempotent_replay']);self.assertEqual(replay['voice_id'],first['voice_id'])
        restarted=NativeVoiceLibrary(Store(self.root));self.assertEqual(restarted.get(first['voice_id'])['definition_sha256'],first['definition_sha256'])
        with self.assertRaisesRegex(WorkflowError,'RIGHTS_CONFIRMATION_REQUIRED'):restarted.get(first['voice_id'],for_generation=True)
        self.assertFalse(restarted.page()['inference_dispatched'])

    def test_versions_CAS_exact_replay_and_immutable_historical_metadata(self):
        first=self.create();second=self.update(first,display_name='Tên mới');self.assertEqual(second['version'],2)
        self.assertEqual(self.library.get(first['voice_id'],version=1)['definition'],first['definition'])
        self.assertEqual(self.update(first,display_name='Tên mới')['version'],2)
        with self.assertRaisesRegex(WorkflowError,'REQUEST_KEY_CONFLICT'):self.update(first,display_name='Changed same key')
        with self.assertRaisesRegex(WorkflowError,'VERSION_CHANGED'):
            self.library.update(first['voice_id'],{'expected_version':1,'request_key':'different-stale-voice-key','definition':second['definition']},actor_ref='fixture')
        self.assertEqual(self.counts(),(2,2))

    def test_rights_declared_is_recorded_as_declaration_only_and_revocation_blocks_old_version(self):
        first=self.create(rights_status='owner_declared',license='Fixture license only',source_reference='fixture://preset',permission_reference='explicit fixture declaration')
        record=self.library.get(first['voice_id'],for_generation=True);self.assertFalse(record['rights_independently_verified'])
        self.update(first,rights_status='blocked')
        with self.assertRaisesRegex(WorkflowError,'RIGHTS_CONFIRMATION_REQUIRED'):self.library.get(first['voice_id'],for_generation=True)
        with self.assertRaisesRegex(WorkflowError,'VERSION_CHANGED'):self.library.get(first['voice_id'],version=1,for_generation=True)

    def test_reference_needs_explicit_consent_and_never_accepts_client_paths(self):
        record=self.create(source_type='licensed_reference',reference_asset_id='ast_explicit_fixture',reference_sha256='a'*64,
            rights_status='owner_declared',license='Fixture only',source_reference='fixture://reference',permission_reference='fixture human declaration')
        with self.assertRaisesRegex(WorkflowError,'REFERENCE_CONSENT_REQUIRED'):self.library.get(record['voice_id'],for_generation=True)
        self.update(record,cloning_consent=True);self.assertEqual(self.library.get(record['voice_id'],for_generation=True)['provider_execution'],'NOT_CONFIGURED_BY_LIBRARY')

    def test_closed_strict_definition_cannot_permanently_assign_a_character_or_store_credentials(self):
        for changes in [{'character_id':'GLOBAL-CHARACTER'},{'api_key':'not-a-real-key'},{'reference_asset_id':'C:/private/reference.wav'},
            {'cloning_consent':'true'},{'rights_status':'owner_declared'},{'display_name':' '},{'provider':'https://private.invalid'}]:
            with self.subTest(changes=changes),self.assertRaisesRegex(WorkflowError,'REQUEST_INVALID'):self.create(**changes)
        self.assertEqual(self.counts(),(0,0))

    def test_scope_cannot_be_rebound_and_foreign_workspace_cannot_read_library(self):
        first=self.create();self.library.workspace='wsp_foreign'
        with self.assertRaisesRegex(WorkflowError,'WORKSPACE_INVALID'):self.library.get(first['voice_id'])
        with self.assertRaisesRegex(WorkflowError,'WORKSPACE_INVALID'):NativeVoiceLibrary(self.store,workspace_id='wsp_foreign')
        self.library.workspace='wsp_native_local';self.assertEqual(self.library.get(first['voice_id'])['version'],1)
        marker=self.root/'.vf-auth-workspace.json';marker.write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':'wsp_foreign'}))
        with self.assertRaisesRegex(WorkflowError,'WORKSPACE_INVALID'):self.library.page()

    def test_revoked_writer_during_transaction_creates_no_versions_or_receipts(self):
        calls=[]
        def authorized():
            calls.append(True)
            if len(calls)==2:raise WorkflowError('EXPLICIT_FIXTURE_AUTH_REVOKED')
        with self.assertRaisesRegex(WorkflowError,'AUTH_REVOKED'):
            self.library.create({'request_key':'explicit-revoked-voice-key','definition':definition()},actor_ref='fixture',authorization_check=authorized)
        self.assertEqual(self.counts(),(0,0))

    def test_changed_definition_bytes_fail_hash_verification(self):
        first=self.create()
        with self.store.transaction() as con:con.execute('UPDATE native_voice_versions SET definition_json=?',(json.dumps(definition(display_name='changed behind version')),))
        with self.assertRaisesRegex(WorkflowError,'LIBRARY_CHANGED'):self.library.get(first['voice_id'])

    def test_backup_restore_retains_library_versions_and_write_receipts(self):
        from services.windows_native.pipeline import Config
        from services.windows_native.backup import create_backup,restore_backup
        first=self.create();second=self.update(first,display_name='Updated fixture')
        config=Config(data_root=self.root,runtime_root=self.base/'runtime',secret_file=self.base/'private'/'absent-key',assemblyai_secret_file=self.base/'private'/'absent-asr')
        archive=self.base/'voices.zip';receipt=create_backup(config,archive);counts=receipt['database_status']['workflow.sqlite3']['counts']
        self.assertEqual((counts['native_voice_versions'],counts['native_voice_writes']),(2,2))
        restored=restore_backup(archive,self.base/'restored',expected_sha256=receipt['sha256']);new=NativeVoiceLibrary(Store(self.base/'restored'))
        self.assertEqual(new.get(first['voice_id'])['definition_sha256'],second['definition_sha256'])
        self.assertEqual(new.get(first['voice_id'],version=1)['definition_sha256'],first['definition_sha256'])

if __name__=='__main__':unittest.main()
