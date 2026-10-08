"""Actual Windows DPAPI/ACL tests with synthetic session URIs; no upload calls."""
from datetime import timedelta
import json,os,unittest
from unittest.mock import patch
from services.windows_native.tests.test_official_publication_dispatch import OfficialDispatchFixture
from services.windows_native.official_publication_sessions import SessionVault,PREFIX,ENTROPY
from services.windows_native.official_account_tokens import ENTROPY as TOKEN_ENTROPY
from services.windows_native.assemblyai_connection import _dpapi
from services.windows_native.contracts import WorkflowError,file_sha
from app.youtube_upload import UploadSession

@unittest.skipUnless(os.name=='nt','Actual Windows DPAPI session protection')
class OfficialSessionTests(OfficialDispatchFixture,unittest.TestCase):
    def session(self):return UploadSession('https://www.googleapis.com/upload/youtube/v3/videos?upload_id=EXPLICIT-PRIVATE-FIXTURE',self.value['snapshot']['final_bytes'])
    def row(self):
        with self.store.transaction() as con:return dict(con.execute('SELECT * FROM native_official_publish_sessions').fetchone())
    def test_private_uri_is_dpapi_sealed_and_opaque_receipt_survives_restart(self):
        ticket=self.init();receipt=self.vault.save(ticket,self.session());row=self.row();path=self.vault.path(receipt['session_ref']);raw=path.read_bytes()
        self.assertTrue(raw.startswith(PREFIX));self.assertNotIn(self.session().uri.encode(),raw);self.assertNotIn(self.credential.token.encode(),raw)
        restarted=SessionVault(self.journal(self.factory),self.vault.directory);loaded=restarted.load(self.project['id'],self.value['publication_id']);self.assertEqual(loaded,self.session())
        self.assertEqual(self.state()['private_session_ref'],receipt['session_ref']);self.assertEqual(self.state()['phase'],'uploading')
        self.assertNotIn(self.session().uri,json.dumps(receipt));self.assertNotIn('upload_id',json.dumps(row));self.assertNotIn(str(path),json.dumps(receipt))
        self.assertNotIn('BUILTIN',self.acl(path));self.assertNotIn('Authenticated Users',self.acl(path))
    def acl(self,path):
        import subprocess
        return subprocess.check_output(['icacls',str(path)],encoding='utf-8',errors='replace')
    def test_startup_and_status_do_not_decrypt_or_create_private_files(self):
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No startup decryption')):
            vault=SessionVault(self.service,self.folder/'absent-private-directory');self.assertEqual(vault.public()['status'],'CONFIGURED');self.assertFalse(vault.directory.exists())
            absent=SessionVault(self.service);self.assertEqual(absent.public()['status'],'NOT_CONFIGURED')
        with self.assertRaisesRegex(WorkflowError,'NOT_CONFIGURED'):absent.save(self.init(),self.session())
    def test_source_state_relative_mounts_and_later_mount_mutation_are_rejected(self):
        for path in (self.root/'sessions',self.root,'relative-sessions'):
            with self.assertRaises(WorkflowError):SessionVault(self.service,path)
        self.vault.directory=self.folder/'other-secrets'
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.vault.public()
    def test_wrong_workspace_project_size_or_noninit_ticket_cannot_register_or_load(self):
        ticket=self.init()
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):self.vault.save(ticket,UploadSession(self.session().uri,self.session().total_bytes+1))
        self.vault.save(ticket,self.session())
        with self.assertRaises(WorkflowError):self.vault.save(ticket,self.session())
        with self.assertRaisesRegex(WorkflowError,'UNAVAILABLE'):self.vault.load('f'*32,self.value['publication_id'])
        with self.assertRaisesRegex(WorkflowError,'REQUEST_INVALID'):self.vault.save(self.chunk(),self.session())
        self.assertEqual(len(self.calls),1)
    def test_cipher_corruption_missing_file_and_changed_domain_are_sanitized(self):
        self.register();row=self.row();path=self.vault.path(row['session_ref']);raw=path.read_bytes()
        with self.assertRaises(Exception):_dpapi(raw[len(PREFIX):],decrypt=True,entropy=TOKEN_ENTROPY)
        path.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
        with self.assertRaisesRegex(WorkflowError,'^NATIVE_OFFICIAL_SESSION_UNAVAILABLE$'):self.vault.load(self.project['id'],self.value['publication_id'])
        path.unlink()
        with self.assertRaisesRegex(WorkflowError,'UNAVAILABLE'):self.vault.load(self.project['id'],self.value['publication_id'])
    def test_expiry_and_current_grant_revocation_prevent_uri_release(self):
        self.vault.save(self.init(),self.session(),ttl_seconds=60);self.clock[0]+=timedelta(seconds=61)
        with self.assertRaisesRegex(WorkflowError,'UNAVAILABLE'):self.vault.load(self.project['id'],self.value['publication_id'])
        self.clock[0]-=timedelta(seconds=61)
        object.__setattr__(self.verifier.registry.tokens[self.principal.token_id],'enabled',False)
        with self.assertRaisesRegex(WorkflowError,'UNAVAILABLE'):self.vault.load(self.project['id'],self.value['publication_id'])
    def test_rehashed_cipher_with_rebound_scope_or_numeric_safety_flag_is_rejected(self):
        self.register();row=self.row();path=self.vault.path(row['session_ref']);original=path.read_bytes()
        envelope=json.loads(_dpapi(original[len(PREFIX):],decrypt=True,entropy=ENTROPY))
        for key,value in (('mock',1),('total_bytes',True),('project_id','f'*32),('target_binding_sha256','f'*64)):
            parsed=json.loads(json.dumps(envelope));parsed['binding'][key]=value
            path.write_bytes(PREFIX+_dpapi(json.dumps(parsed).encode(),entropy=ENTROPY))
            with self.store.transaction() as con:con.execute('UPDATE native_official_publish_sessions SET cipher_sha256=?',(file_sha(path),))
            with self.assertRaisesRegex(WorkflowError,'UNAVAILABLE'):self.vault.load(self.project['id'],self.value['publication_id'])
    def test_expiry_during_encryption_retains_known_session_but_authorizes_no_more_bytes(self):
        ticket=self.init();original=_dpapi
        def changed(value,**kwargs):
            raw=original(value,**kwargs);self.clock[0]+=timedelta(seconds=901);return raw
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=changed):
            receipt=self.vault.save(ticket,self.session());self.assertTrue(receipt['needs_current_approval'])
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_publish_sessions').fetchone()[0],1)
        self.assertEqual(len(list(self.vault.directory.glob('*.dpapi'))),1);self.assertEqual(list(self.vault.directory.glob('*.part')),[])
        self.assertEqual(self.service.get(self.project['id'],self.value['publication_id'])['status'],'review_required')
        with self.assertRaisesRegex(WorkflowError,'UNAVAILABLE'):self.vault.load(self.project['id'],self.value['publication_id'])
        with self.assertRaises(WorkflowError):self.chunk()
        self.assertEqual(self.service.recover()['recovered_intents'],0);self.assertEqual(self.state()['phase'],'uploading');self.assertEqual(len(self.calls),1)

if __name__=='__main__':unittest.main()
