"""Real human HTTP/SQLite/worker with explicit cached PCM, no inference/UAT."""
import json,unittest,uuid
from unittest.mock import patch
from services.windows_native.tests import test_access_http as fixture
from services.windows_native.tests.test_shot_production import voice
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.contracts import file_sha,write_json
from services.windows_native.hardening import Artifacts
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import Handler

class NarrationHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp;tearDown=fixture.NativeAccessHTTPTests.tearDown
    start_server=fixture.NativeAccessHTTPTests.start_server;stop_server=fixture.NativeAccessHTTPTests.stop_server
    request=fixture.NativeAccessHTTPTests.request;account=fixture.NativeAccessHTTPTests.account
    def base(self,identifier=None):return '/api/projects/'+(identifier or self.project['id'])+'/narration'
    def prepared(self):
        proposal={'narration':'Xin chào. Cảm ơn.','visual_brief':[{'scene':1,'visual':'First fixture','on_screen_text':'Chào','narration_excerpt':'Xin chào.'},
            {'scene':2,'visual':'Second fixture','on_screen_text':'Cảm ơn','narration_excerpt':'Cảm ơn.'}],'facts_needing_source':['Authored explicit fixture']}
        current=self.server.store.save(self.project['id'],self.project['revision'],proposal=proposal)
        shot=self.server.store.shot_view(current['id'])['shot_timeline']['shots'][0]
        current=self.server.store.mutate_shots(current['id'],current['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'requested_duration':None}})
        current=self.server.store.set_brand(current['id'],current['revision'],'vang-nguyen','personal-30',duration_mode=FIT_NARRATION_POLICY)
        current=self.server.store.approve(current['id'],current['revision'],'EXPLICIT SIGNED FIXTURE',True);self.project=current
        self.account('editor');body={'revision':current['revision'],'kind':'narration','request_key':uuid.uuid4().hex}
        status,job,_=self.request('POST','/api/projects/'+current['id']+'/jobs',body);self.assertEqual(status,200,job)
        self.assertEqual(self.request('POST','/api/projects/'+current['id']+'/jobs',body)[1]['id'],job['id'])
        out=self.config.data_root/'jobs'/job['id'];out.parent.mkdir(exist_ok=True);voice(out);write_json(out/'tts-plan.json',{'explicit_synthetic_pcm_fixture':True})
        Artifacts(out,job).commit('tts',[out/'voice.wav',out/'voice.json',out/'tts-plan.json']);self.server.runner.pipeline=Pipeline(self.config)
        self.assertTrue(self.server.runner.run_one());finished=self.server.store.get_job(job['id']);self.assertEqual(finished['status'],'succeeded',finished)
        return finished,out

    def test_viewer_reads_measured_history_and_actual_audio_with_no_write_authority(self):
        job,out=self.prepared();self.account('viewer');status,page,_=self.request('GET',self.base());self.assertEqual(status,200,page)
        self.assertEqual(page['items'][0]['result'],job['result']);status,audio,_=self.request('GET',self.base()+'/'+job['id']+'/audio')
        self.assertEqual(status,200);self.assertEqual(audio,(out/'voice.wav').read_bytes())
        with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized body must not be read')):
            self.assertEqual(self.request('POST',self.base()+'/'+job['id']+'/apply',{'result':'injected'})[0],403)

    def test_editor_explicitly_applies_current_plan_and_approval_is_cleared(self):
        job,out=self.prepared();body={'revision':self.project['revision'],'expected_plan_sha256':job['result']['plan_sha256'],'acknowledged':True}
        status,updated,_=self.request('POST',self.base()+'/'+job['id']+'/apply',body);self.assertEqual(status,200,updated);self.assertIsNone(updated['approval'])
        self.assertEqual(updated['document']['prepared_narration']['voice_audio_sha256'],file_sha(out/'voice.wav'))
        self.assertEqual(self.request('POST',self.base()+'/'+job['id']+'/apply',body)[0],409)
        self.assertEqual(self.request('POST','/api/projects/'+updated['id']+'/jobs',{'revision':updated['revision'],'kind':'render','request_key':uuid.uuid4().hex})[0],409)

    def test_csrf_and_foreign_project_fail_before_voice_or_timing_changes(self):
        job,out=self.prepared();before=self.server.store.get(self.project['id']);body={'revision':before['revision'],'expected_plan_sha256':job['result']['plan_sha256'],'acknowledged':True}
        self.assertEqual(self.request('POST',self.base()+'/'+job['id']+'/apply',body,headers={'X-VF-CSRF':'wrong'})[0],403)
        other=self.server.store.create('Other fixture','No provider')
        self.assertEqual(self.request('GET',self.base(other['id'])+'/'+job['id']+'/audio')[0],404)
        self.assertEqual(self.request('POST',self.base(other['id'])+'/'+job['id']+'/apply',{**body,'revision':other['revision']})[0],404)
        self.assertEqual(self.server.store.get(self.project['id']),before)

    def test_corrupted_checkpoint_refuses_history_audio_apply_and_resume_without_inference(self):
        job,out=self.prepared();(out/'narration-plan.json').write_bytes(b'EXPLICIT CORRUPTION FIXTURE')
        self.assertEqual(self.request('GET',self.base())[0],409);self.assertEqual(self.request('GET',self.base()+'/'+job['id']+'/audio')[0],409)
        self.assertEqual(self.request('POST',self.base()+'/'+job['id']+'/apply',{'revision':self.project['revision'],'expected_plan_sha256':job['result']['plan_sha256'],'acknowledged':True})[0],409)
        self.assertEqual(self.pipeline.calls,0)
