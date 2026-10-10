"""Actual Windows DPAPI and strict inert registry; provider wires are absent."""
import json,unittest
from datetime import timedelta
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native import tiktok_connection as connection
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.tests.test_tiktok_creators import TikTokCreatorFixture,TOKEN

class TikTokConnectionTests(TikTokCreatorFixture,unittest.TestCase):
    def test_real_dpapi_is_distinct_scoped_non_overwriting_and_secret_free(self):
        raw=self.path.read_bytes();self.assertTrue(raw.startswith(connection.PREFIX));self.assertNotIn(TOKEN.encode(),raw)
        credential=connection.load_token(self.path,self.root,self.target,self.token.credential_alias);self.assertEqual(credential.token,TOKEN);self.assertNotIn(TOKEN,repr(credential))
        with self.assertRaises(WorkflowError):connection.save_token(self.path,self.root,self.token)
        self.assertEqual(self.path.read_bytes(),raw);self.assertFalse(list(self.path.parent.glob('*.part')))
        for value in (self.receipt,self.factory.public()):self.assertNotIn(TOKEN,json.dumps(value));self.assertNotIn(str(self.path),json.dumps(value))
    def test_prefix_foreign_target_alias_and_changed_cipher_are_rejected(self):
        with self.assertRaises(WorkflowError):connection.load_token(self.path,self.root,self.target.model_copy(update={'target_account_id':'FOREIGN'}),self.token.credential_alias)
        with self.assertRaises(WorkflowError):connection.load_token(self.path,self.root,self.target,'foreign-alias')
        altered=self.folder/'private'/'other-format.dpapi';altered.write_bytes(b'ANOTHER-SCOPE\n'+self.path.read_bytes())
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Wrong prefix must not decrypt')):
            with self.assertRaises(WorkflowError):connection.load_token(altered,self.root,self.target,self.token.credential_alias)
            with self.assertRaises(WorkflowError):self.factory.credential(now=self.clock[0],expected_cipher_sha256='f'*64)
    def test_strict_scopes_raw_flags_paths_and_aware_expiry(self):
        raw=self.token.model_dump(mode='json')
        for change in ({'scopes':['video.publish','video.list']},{'expires_at':'2026-10-10T12:00:00'},{'token':'secret\ninvalid-token-credential'}):
            with self.assertRaises(ValidationError):connection.AccessToken.model_validate({**raw,**change})
        for change in ({'creator_reads_enabled':1},{'token_file':str(self.root/'tokens.dpapi')}):
            if 'token_file' in change:
                with self.assertRaises(WorkflowError):connection.NativeTikTokFactory(self.binding.model_copy(update=change),self.root,self.workspace)
            else:
                with self.assertRaises(ValidationError):connection.Binding.model_validate({**self.binding.model_dump(mode='json'),**change})
        for change in ({'api_client_audited':1},{'media_location':'server'},{'chunk_size':True}):
            with self.assertRaises(ValidationError):connection.Profile.model_validate({**self.binding.profile.model_dump(mode='json'),**change})
    def test_protected_registry_load_does_not_decrypt_and_changed_registry_is_fenced(self):
        path=self.folder/'private'/'registry.json';data={'schema_version':'native-tiktok-publishing-registry-v1','version':1,'workspace_id':self.workspace,'bindings':[self.binding.model_dump(mode='json')]}
        path.write_text(json.dumps(data),encoding='utf-8')
        with patch.object(connection,'load_token',side_effect=AssertionError('Startup must not decrypt')):
            factories=connection.load(path,self.root,self.workspace);self.assertEqual(factories[self.target.profile_id].public()['status'],'NOT_CONFIGURED')
            enabled=connection.load(path,self.root,self.workspace,owner_read_enabled=True);self.assertEqual(enabled[self.target.profile_id].public()['status'],'READ_CONFIGURED')
        path.write_text(json.dumps({**data,'version':2}),encoding='utf-8')
        with self.assertRaises(WorkflowError):enabled[self.target.profile_id].public()
        path.write_text('{"version":1,"version":1}',encoding='utf-8')
        with self.assertRaises(WorkflowError):connection.load(path,self.root,self.workspace)
    def test_factory_client_target_and_workspace_mutation_fail_before_private_read(self):
        self.factory.client.network_enabled=True
        with patch.object(connection,'load_token',side_effect=AssertionError('Changed transport must not decrypt')):
            with self.assertRaises(WorkflowError):self.factory.credential(now=self.clock[0],expected_cipher_sha256=file_sha(self.path))
        with self.assertRaises(WorkflowError):connection.NativeTikTokFactory(self.binding,self.root,'foreign-workspace')

if __name__=='__main__':unittest.main()
