"""Human/CSRF HTTP stock boundaries with actual pixels and explicit SDK wire mocks."""
import httpx,unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.stock import NativeStock
from services.windows_native.stock_registry import StockFactory,StockCredential
from services.windows_native.stock_models import StockDownload
from services.windows_native.contracts import digest
from services.windows_native.tests import test_access_http as fixture
from services.windows_native.tests.test_stock import photo,pixels


class StockHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def payload(self,fixture_mode=False):
        return {'revision':self.project['revision'],'provider':'pexels','query':'EXPLICIT TECHNOLOGY FIXTURE','media_type':'image','orientation':'landscape',
            'limit':3,'external_acknowledged':not fixture_mode,'fixture_acknowledged':fixture_mode,'request_key':'native-stock-http-search-fixture-key'}

    def test_default_not_configured_no_fake_media_and_owner_boundary_before_body(self):
        base='/api/projects/'+self.project['id']+'/stock';before=self.server.store.get(self.project['id'])
        status,config,_=self.request('GET','/api/stock/providers');self.assertEqual(status,200);self.assertFalse(config['ui_enablement_supported'])
        self.assertTrue(all(row['status']=='NOT_CONFIGURED' for row in config['items']))
        status,row,headers=self.request('POST',base+'/search',self.payload());self.assertEqual(status,200);self.assertEqual(row['status'],'not_configured');self.assertIsNone(row['result'])
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(self.server.store.get(self.project['id']),before)
        for role in ['editor','reviewer','viewer']:
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('No unauthorized stock body read')):
                self.assertEqual(self.request('POST',base+'/search',self.payload())[0],403)
            self.assertEqual(self.request('GET',base)[0],200)
        self.account('owner');self.assertEqual(self.request('POST',base+'/search',{**self.payload(),'download_url':'https://untrusted.example/media'})[0],400)
        self.assertEqual(self.request('POST',base+'/search',self.payload(),{'X-VF-CSRF':'wrong'})[0],403)

    def test_mock_download_editor_attachment_viewer_guard_and_local_file_match(self):
        calls=[]
        def wire(request):
            calls.append(request.url.path)
            if request.url.path=='/v1/search':return httpx.Response(200,json={'photos':[photo()]})
            if request.url.path=='/v1/photos/11':return httpx.Response(200,json=photo())
            return httpx.Response(200,content=pixels(),headers={'Content-Type':'image/png'})
        factory=StockFactory('pexels',StockCredential(api_key='explicit-fixture-key',enabled=True),owner_enabled=True,transport=httpx.MockTransport(wire))
        self.server.stock=NativeStock(self.server.store,self.config,workspace_id=self.server.publications.workspace_id,factories={'pexels':factory})
        base='/api/projects/'+self.project['id']+'/stock';before=self.server.store.get(self.project['id'])
        status,row,_=self.request('POST',base+'/search',self.payload(True));self.assertEqual(status,200);self.server.stock.process()
        status,parent,_=self.request('GET',base+'/'+row['stock_id']);self.assertEqual(status,200);self.assertTrue(parent['result']['mock'])
        candidate=parent['result']['candidates'][0];download={'revision':self.project['revision'],'search_id':parent['stock_id'],'candidate_id':candidate['candidate_id'],
            'expected_result_sha256':parent['result_sha256'],'expected_candidate_sha256':digest(candidate),'fixture_acknowledged':True,'request_key':'native-stock-http-download-fixture-key'}
        status,row,_=self.request('POST',base+'/download',download);self.assertEqual(status,200);self.server.stock.process()
        ready=self.server.stock.get(self.project['id'],row['stock_id']);asset=ready['result']['asset'];self.assertEqual(asset['rights_status'],'unknown')
        body={'revision':self.project['revision'],'expected_fingerprint':ready['request_fingerprint'],'expected_asset_sha256':asset['sha256'],
            'acknowledged':True,'request_key':'native-stock-http-attachment-fixture-key'}
        self.account('viewer');self.assertEqual(self.request('GET',base+'/'+row['stock_id']+'/file')[0],200)
        with patch.object(Handler,'read_body',side_effect=AssertionError('Viewer cannot attach stock')):
            self.assertEqual(self.request('POST',base+'/'+row['stock_id']+'/import',body)[0],403)
        self.account('editor');status,receipt,_=self.request('POST',base+'/'+row['stock_id']+'/import',body);self.assertEqual(status,200)
        self.assertFalse(receipt['rights_independently_verified']);self.assertTrue(receipt['approval_invalidated']);self.assertEqual(receipt['actor_ref'],'explicit-fixture')
        self.assertIsNone(self.server.store.get(self.project['id'])['approval']);self.assertEqual(self.server.store.versions(self.project['id'])[1]['document'],before['document'])
        self.assertEqual(self.request('POST',base+'/'+row['stock_id']+'/import',body)[1]['idempotent_replay'],True);self.assertEqual(len(calls),3)


if __name__=='__main__':unittest.main()
