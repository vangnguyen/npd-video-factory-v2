"""Real loopback transport; authoring only, no provider or Owner acceptance."""
import hashlib,http.client,json,tempfile,threading,unittest
from pathlib import Path
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer

class DramaWorkflowHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();base=Path(self.temp.name)
        self.server=LocalServer(0,Config(data_root=base/'data',runtime_root=base/'absent-runtime',secret_file=base/'secrets/absent-secret',assemblyai_secret_file=base/'secrets/absent-asr'),start_worker=False)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,method,path,body=None,csrf=True):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=15)
        con.request(method,path,body=json.dumps(body) if body else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+self.server.session,**({'X-VF-CSRF':self.server.csrf} if csrf else {})})
        r=con.getresponse();raw=r.read();status=r.status;con.close();return status,json.loads(raw)
    def test_visible_choices_create_empty_drama_and_author_script_without_jobs(self):
        status,choices=self.request('GET','/api/production-workflows');self.assertEqual(status,200)
        self.assertEqual([v['kind'] for v in choices['choices']],['standard','drama','source'])
        status,p=self.request('POST','/api/projects',{'name':'Phim HTTP nháp','prompt':'','input_kind':'script','workflow_kind':'drama','output_format':'9:16'});self.assertEqual(status,201)
        status,r=self.request('POST','/api/projects/'+p['id']+'/drama-script',{'revision':1,'request_key':'http-drama-script-0001','text':'(An mở cửa.)\nAn: Xin chào.\nBình: Chào bạn.','confirm_characters':True});self.assertEqual((status,r['provider_calls'],r['human_approval_granted']),(200,0,False))
        current=self.server.store.get(p['id']);self.assertEqual(len(current['document']['drama_casting']['configuration']['characters']),2);self.assertEqual(current['jobs'],[]);self.assertIsNone(current['approval'])
        status,info=self.request('GET','/api/app-info');self.assertEqual(status,200);self.assertEqual(Path(info['application_source']),Path(__file__).resolve().parents[3]);self.assertEqual(info['platform_api_publishing'],'DEFERRED')
    def test_new_write_uses_existing_csrf_boundary(self):
        p=self.server.store.create('HTTP drama','',workflow_kind='drama')
        status,_=self.request('POST','/api/projects/'+p['id']+'/drama-script',{'revision':1,'request_key':'http-drama-denied-01','text':'An: Xin chào.'},csrf=False)
        self.assertIn(status,(401,403));self.assertEqual(self.server.store.get(p['id'])['revision'],1)

    def test_drama_script_decision_round_trips_reopens_and_stales_when_draft_changes(self):
        p=self.server.store.create('Script review HTTP fixture','',workflow_kind='drama')
        path='/api/projects/'+p['id'];text='An: Xin chào.\nBình: Chào bạn.'
        status,_=self.request('POST',path+'/drama-script',{'revision':1,'request_key':'drama-http-review-script-01','text':text,'confirm_characters':True})
        self.assertEqual(status,200)
        _,p=self.request('GET',path)
        sha=hashlib.sha256(p['document']['proposal']['narration'].encode()).hexdigest()
        status,p=self.request('POST',path+'/script-review',{'revision':p['revision'],'reviewer':'EXPLICIT HTTP FIXTURE','acknowledged':True,'script_sha256':sha})
        self.assertEqual(status,200);self.assertTrue(p['script_review']['current'])
        self.assertIsNone(p['approval']);self.assertEqual(p['jobs'],[])
        _,reopened=self.request('GET',path)
        self.assertEqual(reopened['script_review'],p['script_review'])
        status,_=self.request('POST',path+'/drama-script',{'revision':p['revision'],'request_key':'drama-http-review-script-02','text':text+'\nAn: Hẹn gặp lại.','confirm_characters':False})
        self.assertEqual(status,200)
        _,draft=self.request('GET',path)
        self.assertFalse(draft['script_review']['current'])
        self.assertIsNone(draft['approval']);self.assertEqual(draft['jobs'],[])
