"""Grant-selected worker with nonplayable synthetic QC/media/Owner fixtures."""
import asyncio,json,unittest
from urllib.parse import urlencode
import httpx
from app.google_oauth_protocol import GoogleOAuthTokenClient
from app.publishing_credentials import READ,UPLOAD
from services.windows_native.contracts import WorkflowError
from services.windows_native.google_oauth_vault import NativeGoogleOAuthVault,PrivateClient
from services.windows_native.google_oauth_operations import NativeGoogleOAuthOperations,Slot,Start
from services.windows_native.google_oauth_selections import NativeGoogleOAuthSelections,Select,Revoke
from services.windows_native.official_publication_registry import PublishingFactory,OAuthBinding
from services.windows_native.official_publication_worker import NativeOfficialPublicationWorker
from services.windows_native.official_publication_sessions import SessionVault
from services.windows_native.official_publication_models import Action
from services.windows_native.tests.test_official_publication_dispatch import OfficialDispatchFixture
from services.windows_native.tests import test_official_publication_worker as worker_fixture
from services.windows_native.tests.test_google_oauth_protocol import client,TOKEN,REFRESH,SECRET,CODE


class SelectedOAuthWorkerTests(OfficialDispatchFixture,unittest.TestCase):
    def response(self,request):
        self.assertEqual(request.headers['authorization'],'Bearer '+TOKEN)
        return worker_fixture.OfficialWorkerTests.response(self,request)
    step=worker_fixture.OfficialWorkerTests.step
    poll=worker_fixture.OfficialWorkerTests.poll
    upload=worker_fixture.OfficialWorkerTests.upload

    def setUp(self):
        super().setUp();self.wire=[];self.ack=0;self.processing='processed';self.privacy='private';self.mode=None
        # Retain and explicitly cancel the fixture's previous unstarted intent.
        self.service.cancel(self.project['id'],self.value['publication_id'],Action(expected_snapshot_sha256=self.value['snapshot_sha256']),principal=self.principal)
        self.client.transport.handler=self.response
        profile=self.factory.profile
        self.oauth_vault=NativeGoogleOAuthVault(self.folder/'private-selected-google-grants',self.root,self.workspace)
        private=PrivateClient(target=self.target,purpose='publishing',credential_alias='explicit-selected-google-worker',client_id=client('publishing').client_id,scopes=sorted([READ,UPLOAD]),client_secret=SECRET)
        receipt=self.oauth_vault.save_client(private);slot=Slot(slot_id='ngos_'+'c'*32,target=self.target,client=receipt,client_id=private.client_id,scopes=private.scopes)
        binding=OAuthBinding(credential_source='google_oauth_selection',profile=profile,credential_alias=private.credential_alias,google_oauth_slot_id=slot.slot_id,gates=self.factory.gates)
        self.factory=PublishingFactory(profile,self.root,self.workspace,binding=binding,gates=binding.gates,client=self.client);self.service=self.journal(self.factory)
        token_client=GoogleOAuthTokenClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'access_token':TOKEN,'refresh_token':REFRESH,'expires_in':3600,'token_type':'Bearer','scope':' '.join(private.scopes)})))
        self.oauth=NativeGoogleOAuthOperations(self.service,self.oauth_vault,slots={slot.slot_id:slot},client=token_client,enabled=True)
        start,_=self.oauth.start(self.project['id'],Start(revision=self.project['revision'],slot_id=slot.slot_id,expected_configuration_sha256=slot.client.configuration_sha256,
            acknowledged_credential_operation=True,acknowledged_protocol_mock=True,redirect_uri='http://127.0.0.1:18047/oauth/google/callback',request_key='explicit-selected-worker-grant'),principal=self.principal)
        flow=self.oauth_vault.authorization(start['snapshot']['authorization_receipt'])
        grant=asyncio.run(self.oauth.exchange(self.project['id'],start['authorization_id'],urlencode({'state':flow.state,'code':CODE}),principal=self.principal,expected_snapshot_sha256=start['snapshot_sha256']))
        self.assertEqual(grant['status'],'succeeded')
        self.selections=NativeGoogleOAuthSelections(self.oauth,enabled=True,client=self.client);self.factory.resolver.attach(self.selections)
        selection,_=self.selections.create(self.project['id'],Select(revision=self.project['revision'],source_operation_id=grant['operation_id'],expected_result_sha256=grant['result_sha256'],
            acknowledged_account_access=True,acknowledged_credential_selection=True,acknowledged_protocol_mock=True,request_key='explicit-selected-worker-channel'),principal=self.principal)
        self.selection=asyncio.run(self.selections.verify(self.project['id'],selection['selection_id'],principal=self.principal,expected_snapshot_sha256=selection['snapshot_sha256']))
        self.assertEqual(self.selection['status'],'active');self.assertEqual(self.factory.credential(now=self.clock[0]).token,TOKEN)
        self.value=self.create(self.body(request_key='explicit-selected-worker-publication'));self.approve(self.value)
        self.vault=SessionVault(self.service,self.folder/'private-selected-worker-sessions');self.worker=NativeOfficialPublicationWorker(self.service,self.vault)

    def test_selected_grant_drives_worker_and_separate_approval_and_mock_receipt(self):
        before=self.store.get(self.project['id']);self.upload();result=self.poll();self.assertEqual(result['status'],'completed')
        self.assertFalse(result['published']);self.assertTrue(result['mock_publication_complete']);self.assertTrue(result['receipt']['mock']);self.assertFalse(result['receipt']['external_action'])
        self.assertEqual(len([r for r in self.wire if r['method'] in ('POST','PUT')]),4);self.assertEqual(self.store.get(self.project['id']),before)
        public=json.dumps([result,self.selection,self.wire])
        for secret in (TOKEN,REFRESH,SECRET,CODE):self.assertNotIn(secret,public)

    def test_local_selection_revoke_between_init_and_chunk_blocks_worker(self):
        self.step();before=len(self.wire)
        self.selections.revoke(self.project['id'],self.selection['selection_id'],Revoke(expected_snapshot_sha256=self.selection['snapshot_sha256']),principal=self.principal)
        with self.assertRaises(WorkflowError):self.step()
        self.assertEqual(len(self.wire),before);self.assertEqual(self.ack,0);self.assertFalse(self.factory.public()['credential_present'])


if __name__=='__main__':unittest.main()
