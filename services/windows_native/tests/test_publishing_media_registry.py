"""Protected operator manifest/lazy SDK and private custody, without provider calls."""
import copy,json,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from services.windows_native.publishing_media_registry import load
from services.windows_native.publishing_media_delivery import save_credential
from services.windows_native.contracts import WorkflowError
from app.publishing_media_delivery import S3SDKDeliveryWire,StorageProfile


class PublishingMediaRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name);self.root=self.folder/'state';self.root.mkdir()
        self.path=self.folder/'private'/'media-registry.json';self.path.parent.mkdir()
        self.workspace='wsp_media_registry_fixture';self.profile=StorageProfile('https://storage-fixture.invalid','vf-media-fixture','us-east-1','publishing-media-fixture')
        self.value={'schema_version':'native-publishing-media-registry-v1','version':1,'workspace_id':self.workspace,'enabled':True,
            'storage_profile':dict(self.profile.__dict__),'lease_directory':str(self.folder/'private'/'leases')}
    def tearDown(self):self.temp.cleanup()
    def write(self,value=None):self.path.write_text(json.dumps(self.value if value is None else value),encoding='utf8')
    def test_manifest_and_owner_flag_are_both_required_without_startup_sdk_or_key_reads(self):
        self.write()
        with patch.object(S3SDKDeliveryWire,'client',side_effect=AssertionError('No startup SDK')):
            with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No startup key decode')):
                factory=load(self.path,self.root,self.workspace);self.assertFalse(factory.enabled);self.assertFalse(factory.wire.network_enabled)
                self.assertEqual(factory.public()['status'],'NOT_CONFIGURED');self.assertFalse(factory.public()['url_returned'])
                missing=load(self.path,self.root,self.workspace,owner_enabled=True);self.assertEqual(missing.public()['status'],'NOT_CONFIGURED')
                self.assertFalse(missing.public()['real_provider_tested'])
        self.value['enabled']=False;self.write();self.assertFalse(load(self.path,self.root,self.workspace,owner_enabled=True).enabled)
    def test_protected_cipher_and_expiry_are_hashed_but_never_decrypted_at_startup(self):
        expiry=datetime.now(timezone.utc)+timedelta(hours=2);credential=self.folder/'private'/'s3.dpapi'
        save_credential(credential,self.root,{'schema_version':'native-publishing-s3-credential-v1','workspace_id':self.workspace,
            'storage_profile_sha256':self.profile.sha256,'credential_alias':self.profile.credential_alias,'expires_at':expiry,
            'access_key':'EXPLICIT-LOCAL-MOCK-ACCESS','secret_key':'EXPLICIT-LOCAL-MOCK-SECRET'})
        self.value.update(credential_file=str(credential),credential_expires_at=expiry.isoformat(),estimated_operation_cost_vnd=1);self.write()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No startup key decode')):
            factory=load(self.path,self.root,self.workspace,owner_enabled=True);self.assertEqual(factory.public()['status'],'CONFIGURED')
        self.assertIsNotNone(factory.cipher_sha256);self.assertNotIn('MOCK-SECRET',json.dumps(factory.public()))
    def test_changed_manifest_cannot_dispatch_with_original_configuration(self):
        self.write();factory=load(self.path,self.root,self.workspace);self.value['enabled']=False;self.write()
        with self.assertRaisesRegex(WorkflowError,'REGISTRY_CHANGED'):factory.check()
    def test_duplicate_unknown_boolean_expiry_workspace_and_provider_fields_are_rejected(self):
        for change in ({'enabled':1},{'version':True},{'version':2},{'workspace_id':'wsp_foreign_fixture'},{'token':'PRIVATE BODY'},
            {'credential_expires_at':False},{'credential_expires_at':'2026-10-10T14:00:00'},{'estimated_operation_cost_vnd':True}):
            self.write({**self.value,**change})
            with self.assertRaises(WorkflowError):load(self.path,self.root,self.workspace)
        self.path.write_text('{"enabled":true,"enabled":false}',encoding='utf8')
        with self.assertRaises(WorkflowError):load(self.path,self.root,self.workspace)
    def test_http_arbitrary_path_or_credential_query_cannot_become_storage_endpoint(self):
        for endpoint in ('http://storage.invalid','https://name:secret@storage.invalid','https://storage.invalid/arbitrary','https://storage.invalid/?token=private'):
            value=copy.deepcopy(self.value);value['storage_profile']['endpoint_url']=endpoint;self.write(value)
            with self.assertRaises(WorkflowError):load(self.path,self.root,self.workspace)
    def test_manifest_and_private_paths_inside_state_are_rejected(self):
        inside=self.root/'media-registry.json';self.write();inside.write_bytes(self.path.read_bytes())
        with self.assertRaises(WorkflowError):load(inside,self.root,self.workspace)
        for field in ('lease_directory','credential_file'):
            value={**self.value,field:str(self.root/'unprotected')}
            if field=='credential_file':value['credential_expires_at']=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
            self.write(value)
            with self.assertRaises(WorkflowError):load(self.path,self.root,self.workspace)


if __name__=='__main__':unittest.main()
