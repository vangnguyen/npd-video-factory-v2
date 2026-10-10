"""Signed HTTP with actual uploaded WAV, mock ASR, immutable edit and restart."""
import copy,json,os,subprocess,threading,unittest
from pathlib import Path
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests import test_audio_transcripts as audio_fixture,test_access_http as access_fixture

class AudioTranscriptHTTPTests(unittest.TestCase):
    parent_setup=audio_fixture.AudioTranscriptTests.setUp
    parent_teardown=audio_fixture.AudioTranscriptTests.tearDown
    upload=audio_fixture.AudioTranscriptTests.upload
    run_job=audio_fixture.AudioTranscriptTests.run_job
    collected=audio_fixture.AudioTranscriptTests.collected
    request_body=audio_fixture.AudioTranscriptTests.request_body
    request=access_fixture.NativeAccessHTTPTests.request
    workspace='wsp_audio_transcript_fixture'
    def setUp(self):
        self.parent_setup();self.initial=self.collected();self.base='/api/projects/'+self.project['id']+'/audio-transcripts';self.start_server()
    def start_server(self):
        raw,data=human_fixture('editor',workspace=self.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        self.server=LocalServer(0,self.config,start_worker=False,access=access);self.cookie,session=access.login(raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def stop_server(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def tearDown(self):self.stop_server();self.parent_teardown()
    def account(self,role):
        raw,data=human_fixture(role,workspace=self.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        access.bind_root(self.root);self.server.access=access;self.cookie,session=access.login(raw);self.csrf=session.csrf
    def body(self,row,text='Cần Giờ từ bản chỉnh sửa được yêu cầu.'):
        return {'revision':self.server.store.get(self.project['id'])['revision'],'asset_sha256':row['asset_sha256'],
            'analysis_sha256':row['analysis_sha256'],'edit':self.request_body(row,text)}
    def test_actual_HTTP_editor_saves_reads_restores_and_reopens_without_new_recognition(self):
        status,initial,headers=self.request('GET',self.base);self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(initial,self.initial)
        source=initial['items'][0];calls=list(audio_fixture.fixture.FixtureTransport.calls)
        status,changed,headers=self.request('POST',self.base+'/'+source['asset_id'],self.body(source));self.assertEqual(status,200,changed);self.assertTrue(changed['changed'])
        new=changed['items'][0];self.assertEqual(new['current']['version'],2);self.assertEqual(new['current']['segments'][0]['words'],[]);self.assertEqual(new['original'],source['original'])
        body=self.body(new,source['original']['segments'][0]['text']);body['edit']['base_transcript_id']=source['original']['transcript_id'];body['edit']['segments'][0]['segment_id']=source['original']['segments'][0]['segment_id']
        status,restored,_=self.request('POST',self.base+'/'+source['asset_id'],body);self.assertEqual(status,200,restored);self.assertTrue(restored['changed']);self.assertEqual(restored['items'][0]['current']['version'],3)
        self.stop_server();self.start_server();status,reopened,_=self.request('GET',self.base);self.assertEqual(status,200)
        self.assertEqual(reopened,{k:v for k,v in restored.items() if k!='changed'});self.assertEqual(audio_fixture.fixture.FixtureTransport.calls,calls)
        path=os.environ.get('VF_AUDIO_TRANSCRIPT_HTTP_EVIDENCE')
        if path:
            with Path(path).open('x',encoding='utf-8',newline='\n') as h:json.dump({'schema_version':'native-audio-transcript-owned-HTTP-fixture-v1',
                'fixture_human':True,'mock_ASR':True,'real_provider_calls':0,'browser_rendered':False,'owner_UAT':False,
                'initial':initial,'changed':changed,'restored':restored,'reopened':reopened},h,ensure_ascii=False,indent=2);h.write('\n')
    def test_viewer_reviewer_and_missing_CSRF_are_rejected_before_body(self):
        source=self.initial['items'][0];path=self.base+'/'+source['asset_id'];before=self.server.store.get(self.project['id'])
        for role in ['viewer','reviewer']:
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body must remain unread')):self.assertEqual(self.request('POST',path,{})[0],403)
            self.assertEqual(self.request('GET',self.base)[0],200)
        self.account('editor')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body consumed')):self.assertEqual(self.request('POST',path,{}, {'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.server.store.get(self.project['id']),before)
    def test_wrong_source_unknown_fields_stale_revision_and_queries_never_rewrite(self):
        row=self.initial['items'][0];path=self.base+'/'+row['asset_id'];body=self.body(row);before=self.server.store.get(self.project['id'])
        for extra in [{'asset_sha256':'a'*64},{'analysis_sha256':'a'*64},{'revision':body['revision']-1},{'publish_enabled':True},{'role':'owner'},{'token':'NEVER'}]:
            self.assertIn(self.request('POST',path,{**body,**extra})[0],(400,409))
        self.assertEqual(self.request('GET',self.base+'?token=NEVER')[0],400);self.assertEqual(self.request('POST',self.base,body)[0],403)
        self.assertEqual(self.request('GET','/api/projects/'+'a'*32+'/audio-transcripts')[0],404)
        self.assertEqual(self.server.store.get(self.project['id']),before)
    def test_noop_new_capability_and_module_reads_are_inert(self):
        row=self.initial['items'][0];before=self.server.store.get(self.project['id']);calls=list(audio_fixture.fixture.FixtureTransport.calls)
        status,session,_=self.request('GET','/api/session');self.assertEqual(status,200);self.assertTrue(session['capabilities']['native_audio_transcript_edit'])
        status,module,_=self.request('GET','/native-audio-transcripts.mjs');self.assertEqual(status,200);self.assertIn(b'initializeNativeAudioTranscripts',module)
        status,value,_=self.request('POST',self.base+'/'+row['asset_id'],self.body(row,row['current']['segments'][0]['text']))
        self.assertEqual(status,200,value);self.assertFalse(value['changed']);self.assertEqual(self.server.store.get(self.project['id']),before)
        self.assertEqual(audio_fixture.fixture.FixtureTransport.calls,calls)
    def test_real_controller_over_signed_HTTP_edits_and_restores_original_without_provider_dispatch(self):
        context=self.owned_folder/'controller-context.json';context.write_text(json.dumps({'fixture_human':True,
            'origin':'http://127.0.0.1:'+str(self.server.server_port),'workspace_id':self.workspace,
            'project':{'id':self.project['id'],'revision':self.initial['revision']},'cookie':self.cookie,'csrf':self.csrf}),encoding='utf-8')
        calls=list(audio_fixture.fixture.FixtureTransport.calls)
        repo=Path(__file__).resolve().parents[3]
        p=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(repo/'scripts/native_audio_transcript_http_ui.mjs'),str(context)],capture_output=True,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'));proof=json.loads(p.stdout)
        self.assertEqual(len(proof['requests']),4);self.assertTrue(proof['original_preserved']);self.assertFalse(proof['owner_UAT'])
        self.assertEqual(audio_fixture.fixture.FixtureTransport.calls,calls);current=self.request('GET',self.base)[1]
        self.assertEqual(current['items'][0]['current']['version'],3);self.assertEqual(current['items'][0]['original'],self.initial['items'][0]['original'])
        output=os.environ.get('VF_AUDIO_TRANSCRIPT_CONTROLLER_EVIDENCE')
        if output:
            with Path(output).open('x',encoding='utf-8') as h:json.dump(proof,h,ensure_ascii=False,indent=2);h.write('\n')
