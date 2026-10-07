"""Actual local bytes/SQLite with explicit official API wire mocks; no provider account."""
from copy import deepcopy
import io,json,tempfile,threading,time,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
import httpx
from PIL import Image
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.pipeline import Config
from services.windows_native.stock import NativeStock
from services.windows_native.stock_registry import StockFactory,StockCredential,load
from services.windows_native.stock_models import StockSearch,StockDownload,StockImport
from services.windows_native.store import Store
from services.windows_native.server import Runner
from services.windows_native.observability import Observer
from services.windows_native.tests.test_workflow import proposal
from services.windows_native.source_broll import shared_assets


def pixels():
    buffer=io.BytesIO();Image.new('RGB',(320,240),(18,80,140)).save(buffer,format='PNG');return buffer.getvalue()


def photo():
    return {'id':11,'width':640,'height':360,'url':'https://www.pexels.com/photo/explicit-fixture-11/',
        'photographer':'EXPLICIT FIXTURE CREATOR','alt':'EXPLICIT SYNTHETIC TECHNOLOGY FIXTURE',
        'src':{'original':'https://images.pexels.com/photos/11/explicit-fixture.png'}}


class StockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'state';self.store=Store(self.root);self.config=Config(data_root=self.root)
        self.project=self.store.create('EXPLICIT STOCK FIXTURE','EXPLICIT TECHNOLOGY SEARCH FIXTURE');self.calls=[];self.clock=[time.time()]
        self.transport=httpx.MockTransport(self.wire);self.factory=StockFactory('pexels',StockCredential(api_key='explicit-fixture-key',enabled=True),owner_enabled=True,transport=self.transport)
        self.service=NativeStock(self.store,self.config,workspace_id='wsp_stock_fixture',factories={'pexels':self.factory},clock=lambda:self.clock[0])

    def tearDown(self):self.service.close();self.temp.cleanup()

    def wire(self,request):
        self.calls.append((request.url.host,request.url.path))
        if request.url.host=='api.pexels.com':self.assertEqual(request.headers['Authorization'],'explicit-fixture-key')
        else:self.assertNotIn('Authorization',request.headers)
        if request.url.path=='/v1/search':return httpx.Response(200,json={'photos':[photo()]})
        if request.url.path=='/v1/photos/11':return httpx.Response(200,json=photo())
        if request.url.host=='images.pexels.com':return httpx.Response(200,content=pixels(),headers={'Content-Type':'image/png'})
        raise AssertionError('Unexpected explicit wire fixture')

    def search_payload(self,**changes):
        return StockSearch(revision=self.project['revision'],provider='pexels',query='Công nghệ AI',media_type='image',orientation='landscape',limit=3,
            fixture_acknowledged=True,request_key='native-stock-search-fixture-key',**changes)

    def search(self):
        value,_=self.service.create(self.project['id'],self.search_payload(),actor='fixture-owner');self.service.process();return self.service.get(self.project['id'],value['stock_id'])

    def download(self,parent=None):
        parent=parent or self.search();candidate=parent['result']['candidates'][0]
        payload=StockDownload(revision=self.project['revision'],search_id=parent['stock_id'],candidate_id=candidate['candidate_id'],
            expected_result_sha256=parent['result_sha256'],expected_candidate_sha256=digest(candidate),fixture_acknowledged=True,request_key='native-stock-download-fixture-key')
        value,_=self.service.create(self.project['id'],payload,actor='fixture-owner');self.service.process();return self.service.get(self.project['id'],value['stock_id']),payload

    def attach_payload(self,value):
        return StockImport(revision=self.project['revision'],expected_fingerprint=value['request_fingerprint'],expected_asset_sha256=value['result']['asset']['sha256'],
            acknowledged=True,request_key='native-stock-import-fixture-key')

    def test_default_disabled_missing_configuration_never_calls_or_fabricates_candidates(self):
        empty=NativeStock(self.store,self.config,workspace_id='wsp_stock_fixture')
        request=self.search_payload().model_copy(update={'external_acknowledged':True,'fixture_acknowledged':False})
        value,_=empty.create(self.project['id'],request,actor='fixture-owner');self.assertEqual(value['status'],'not_configured');self.assertIsNone(empty.process())
        self.assertIsNone(value['result']);self.assertEqual(self.calls,[]);self.assertFalse(empty.providers()['ui_enablement_supported'])

    def test_search_and_scope_cache_preserve_project_and_do_not_invent_semantics_or_licensed_fixture(self):
        before=self.store.get(self.project['id']);value=self.search();self.assertEqual(value['status'],'succeeded');self.assertEqual(value['result']['actual_provider_calls'],0)
        self.assertEqual(value['result']['fixture_wire_attempts'],1);candidate=value['result']['candidates'][0];self.assertTrue(candidate['provenance']['fixture'])
        self.assertIsNone(candidate['semantic_score']);self.assertFalse(candidate['production_eligible']);self.assertEqual(self.store.get(self.project['id']),before)
        second,_=self.service.create(self.project['id'],self.search_payload().model_copy(update={'request_key':'native-stock-second-cached-search'}),actor='fixture-owner')
        self.service.process();self.assertEqual(self.service.get(self.project['id'],second['stock_id'])['result']['fixture_wire_attempts'],0);self.assertEqual(len(self.calls),1)
        replay,hit=self.service.create(self.project['id'],self.search_payload(),actor='fixture-owner');self.assertTrue(hit);self.assertEqual(replay,value)
        with self.assertRaises(WorkflowError):self.service.create(self.project['id'],self.search_payload().model_copy(update={'query':'Changed query'}),actor='fixture-owner')

    def test_download_rebinds_provider_identity_and_fully_decodes_bytes_before_explicit_idempotent_attachment(self):
        before=self.store.get(self.project['id']);value,_=self.download();asset=value['result']['asset'];self.assertEqual(value['status'],'succeeded')
        self.assertEqual((asset['width'],asset['height']),(320,240));self.assertEqual(value['result']['provider_metadata']['width'],640)
        self.assertEqual(asset['rights_status'],'unknown');self.assertEqual(asset['source_type'],'stock');self.assertFalse(asset['production_eligible']);self.assertTrue(asset['needs_attention'])
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(asset['source_sha256'],__import__('hashlib').sha256(pixels()).hexdigest())
        path,selected=self.service.asset_file(self.project['id'],value['stock_id']);self.assertEqual(file_sha(path),asset['sha256'])
        payload=self.attach_payload(value);receipt=self.service.attach(self.project['id'],value['stock_id'],payload,actor='fixture-editor')
        current=self.store.get(self.project['id']);self.assertEqual(current['revision'],before['revision']+1);self.assertIsNone(current['approval'])
        self.assertEqual(current['document']['assets'],[asset]);self.assertFalse(receipt['rights_independently_verified']);self.assertEqual(len(self.calls),3)
        projected=next(iter(shared_assets(current,self.config).values()))
        self.assertEqual(projected.provenance['source_type'],'stock');self.assertEqual(projected.provenance['rights_status'],'unknown')
        self.assertEqual(projected.provenance['provider'],'pexels');self.assertTrue(projected.provenance['fixture']);self.assertFalse(projected.provenance['production_eligible'])
        replay=self.service.attach(self.project['id'],value['stock_id'],payload,actor='fixture-editor');self.assertTrue(replay['idempotent_replay']);self.assertEqual(self.store.get(self.project['id']),current)
        costs=self.service.costs.summary(self.project['id']);self.assertEqual(len(costs['records']),2)
        self.assertTrue(all(not operation['paid'] and operation['actual_cost'] is None for operation in costs['records']))

    def test_changed_bytes_and_selection_fail_before_project_mutation_or_download(self):
        parent=self.search();candidate=parent['result']['candidates'][0]
        bad=StockDownload(revision=self.project['revision'],search_id=parent['stock_id'],candidate_id=candidate['candidate_id'],expected_result_sha256='0'*64,
            expected_candidate_sha256=digest(candidate),fixture_acknowledged=True,request_key='native-stock-forged-selection-key')
        with self.assertRaises(WorkflowError):self.service.create(self.project['id'],bad,actor='fixture-owner')
        self.assertEqual(len(self.calls),1);value,_=self.download(parent);before=self.store.get(self.project['id'])
        path=self.root/'assets'/value['result']['asset']['id'];path.write_bytes(path.read_bytes()+b'EXPLICIT CORRUPTION')
        with self.assertRaises(WorkflowError):self.service.attach(self.project['id'],value['stock_id'],self.attach_payload(value),actor='fixture-editor')
        self.assertEqual(self.store.get(self.project['id']),before)

    def test_import_journal_failure_rolls_back_project_history_and_receipt(self):
        value,_=self.download();before=self.store.get(self.project['id']);versions=self.store.versions(self.project['id'])
        with patch.object(self.service,'event',side_effect=RuntimeError('EXPLICIT JOURNAL FAILURE')):
            with self.assertRaises(RuntimeError):self.service.attach(self.project['id'],value['stock_id'],self.attach_payload(value),actor='fixture-editor')
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.store.versions(self.project['id']),versions)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_stock_imports').fetchone()[0],0)

    def test_rate_limit_backoff_cancel_and_expired_worker_lease_are_fenced(self):
        attempts=[]
        def throttle(request):attempts.append(1);return httpx.Response(429,headers={'Retry-After':'15'})
        self.factory.transport=httpx.MockTransport(throttle)
        value,_=self.service.create(self.project['id'],self.search_payload(),actor='fixture-owner');self.service.process();value=self.service.get(self.project['id'],value['stock_id'])
        self.assertEqual(value['status'],'retry_scheduled');self.assertEqual(value['next_at'],self.clock[0]+15);self.assertIsNone(self.service.process())
        cancelled=self.service.cancel(self.project['id'],value['stock_id'],fingerprint=value['request_fingerprint'],actor='fixture-owner');self.assertEqual(cancelled['status'],'cancelled')
        self.clock[0]+=100;self.assertIsNone(self.service.process());self.assertEqual(len(attempts),1)
        pending,_=self.service.create(self.project['id'],self.search_payload().model_copy(update={'request_key':'native-stock-expired-worker-key'}),actor='fixture-owner')
        with self.store.transaction() as con:con.execute("UPDATE native_stock_jobs SET status='running',claim_id='explicit-old-claim',lease_until=?,attempts=1 WHERE stock_id=?",(self.clock[0]-1,pending['stock_id']))
        self.service.process();expired=self.service.get(self.project['id'],pending['stock_id']);self.assertEqual(expired['status'],'retry_scheduled');self.assertEqual(expired['failure_code'],'NATIVE_STOCK_WORKER_INTERRUPTED')

    def test_other_project_core_job_is_not_held_by_slow_stock_provider(self):
        entered=threading.Event();release=threading.Event()
        def wait(request):entered.set();release.wait(5);return httpx.Response(200,json={'photos':[photo()]})
        self.factory.transport=httpx.MockTransport(wait);self.service.create(self.project['id'],self.search_payload(),actor='fixture-owner')
        thread=threading.Thread(target=self.service.process);thread.start();self.assertTrue(entered.wait(3))
        try:
            other=self.store.create('EXPLICIT INDEPENDENT CORE FIXTURE','EXPLICIT INPUT');self.store.enqueue(other['id'],other['revision'],'content','native-stock-core-independent-key')
            class Pipeline:
                def run(self,*args):return {'proposal':proposal(),'explicit_mock_core_result':True}
            start=time.monotonic();self.assertTrue(Runner(self.store,Pipeline()).run_one());self.assertLess(time.monotonic()-start,1.5)
            self.assertEqual(self.store.get(other['id'])['jobs'][0]['status'],'awaiting_review')
        finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive())

    def test_rehashed_fixture_promotion_root_binding_and_strict_ack_fail_closed(self):
        with self.assertRaises(WorkflowError):self.service.create(self.project['id'],self.search_payload().model_copy(update={'fixture_acknowledged':False}),actor='fixture-owner')
        with self.assertRaises(WorkflowError):NativeStock(self.store,self.config,workspace_id='wsp_other_fixture')
        value=self.search()
        with self.store.transaction() as con:
            result=deepcopy(value['result']);result['mock']=False;con.execute('UPDATE native_stock_jobs SET result_json=?,result_sha256=? WHERE stock_id=?',(json.dumps(result),digest(result),value['stock_id']))
        with self.assertRaises(WorkflowError):self.service.get(self.project['id'],value['stock_id'])

    def test_protected_registry_is_inert_rejects_duplicates_scope_and_state_paths(self):
        location=Path(self.temp.name)/'protected-fixture-stock.json';value={'version':1,'native_workspace_id':'wsp_stock_fixture','pexels':{'api_key':'explicit-fixture-key','enabled':True}}
        location.write_text(json.dumps(value));factories=load(location,self.root,'wsp_stock_fixture');self.assertFalse(factories['pexels'].enabled)
        enabled=load(location,self.root,'wsp_stock_fixture',owner_enabled=True);self.assertTrue(enabled['pexels'].enabled);self.assertEqual(self.calls,[])
        with self.assertRaises(WorkflowError):load(location,self.root,'wsp_foreign_fixture',owner_enabled=True)
        location.write_text('{"version":1,"version":1,"native_workspace_id":"wsp_stock_fixture"}')
        with self.assertRaises(WorkflowError):load(location,self.root,'wsp_stock_fixture')
        inside=self.root/'unsafe-fixture.json';inside.write_text(json.dumps(value))
        with self.assertRaises(WorkflowError):load(inside,self.root,'wsp_stock_fixture')

    def test_pixabay_image_and_pexels_video_use_same_native_intake_with_real_local_decode(self):
        def pix_wire(request):
            if request.url.host=='pixabay.com':
                self.assertEqual(request.url.params['key'],'explicit-pixabay-fixture-key')
                return httpx.Response(200,json={'hits':[{'id':31,'user':'EXPLICIT PIXABAY FIXTURE','pageURL':'https://pixabay.com/photos/explicit-fixture-31/',
                    'webformatURL':'https://cdn.pixabay.com/photo/explicit-fixture.png','webformatWidth':640,'webformatHeight':360,'tags':'EXPLICIT SYNTHETIC FIXTURE'}]})
            return httpx.Response(200,content=pixels(),headers={'Content-Type':'image/png'})
        factory=StockFactory('pixabay',StockCredential(api_key='explicit-pixabay-fixture-key',enabled=True),owner_enabled=True,transport=httpx.MockTransport(pix_wire))
        self.service.factories['pixabay']=factory;search=self.search_payload().model_copy(update={'provider':'pixabay','request_key':'native-pixabay-image-search-key'})
        parent,_=self.service.create(self.project['id'],search,actor='fixture-owner');self.service.process();parent=self.service.get(self.project['id'],parent['stock_id'])
        image,_=self.download(parent);self.assertEqual(image['result']['asset']['provider'],'pixabay');self.assertEqual(image['result']['asset']['width'],320)
        source=Path(self.temp.name)/'explicit-synthetic-stock-video.mp4'
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=1',
            '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
        movie=source.read_bytes();metadata={'id':21,'width':640,'height':360,'duration':1.,'url':'https://www.pexels.com/video/explicit-fixture-21/',
            'user':{'name':'EXPLICIT LOCAL SYNTHETIC PIXELS'},'video_files':[{'width':640,'height':360,'file_type':'video/mp4','link':'https://videos.pexels.com/video-files/21/explicit-fixture.mp4'}]}
        def video_wire(request):
            if request.url.path=='/v1/videos/search':return httpx.Response(200,json={'videos':[metadata]})
            if request.url.path=='/v1/videos/videos/21':return httpx.Response(200,json=metadata)
            return httpx.Response(200,content=movie,headers={'Content-Type':'video/mp4'})
        self.factory.transport=httpx.MockTransport(video_wire)
        parent,_=self.service.create(self.project['id'],self.search_payload().model_copy(update={'media_type':'video','request_key':'native-pexels-video-search-key'}),actor='fixture-owner')
        self.service.process();parent=self.service.get(self.project['id'],parent['stock_id']);candidate=parent['result']['candidates'][0]
        request=StockDownload(revision=self.project['revision'],search_id=parent['stock_id'],candidate_id=candidate['candidate_id'],expected_result_sha256=parent['result_sha256'],
            expected_candidate_sha256=digest(candidate),fixture_acknowledged=True,request_key='native-pexels-video-download-key')
        value,_=self.service.create(self.project['id'],request,actor='fixture-owner');self.service.process();video=self.service.get(self.project['id'],value['stock_id'])
        self.assertEqual(video['status'],'succeeded');self.assertEqual(video['result']['asset']['kind'],'video');self.assertEqual(video['result']['asset']['width'],320)
        self.assertAlmostEqual(video['result']['asset']['duration_seconds'],1,places=2);self.assertTrue(video['result']['full_native_media_validation_passed'])
        self.assertEqual(video['result']['asset']['rights_status'],'unknown');self.assertEqual(video['result']['asset']['source_sha256'],file_sha(source))

    def test_valid_magic_with_broken_pixels_never_registers_asset_or_project_change(self):
        def broken(request):
            if request.url.host=='api.pexels.com':return self.wire(request)
            return httpx.Response(200,content=b'\x89PNG\r\n\x1a\nEXPLICIT INVALID PIXEL PAYLOAD',headers={'Content-Type':'image/png'})
        self.factory.transport=httpx.MockTransport(broken);before=self.store.get(self.project['id']);parent=self.search();value,_=self.download(parent)
        self.assertEqual(value['status'],'failed');self.assertIsNone(value['result']);self.assertEqual(self.store.get(self.project['id']),before)
        self.assertEqual(list((self.root/'assets').iterdir()),[])


if __name__=='__main__':unittest.main()
