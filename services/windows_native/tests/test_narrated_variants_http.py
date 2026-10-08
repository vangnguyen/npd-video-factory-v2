"""Signed family and source-audio routes over real SQLite/HTTP, no new inference."""
import unittest
from unittest.mock import patch
from services.windows_native.tests import test_narration_http as fixture
from services.windows_native.narration import apply
from services.windows_native.contracts import digest
from services.windows_native.server import Handler

class NarratedVariantsHTTPTests(unittest.TestCase):
    setUp=fixture.NarrationHTTPTests.setUp;tearDown=fixture.NarrationHTTPTests.tearDown
    start_server=fixture.NarrationHTTPTests.start_server;stop_server=fixture.NarrationHTTPTests.stop_server
    request=fixture.NarrationHTTPTests.request;account=fixture.NarrationHTTPTests.account;prepared=fixture.NarrationHTTPTests.prepared
    def ready(self):
        job,out=self.prepared();master=apply(self.server.store,self.project['id'],job['id'],{'revision':self.project['revision'],'expected_plan_sha256':job['result']['plan_sha256'],'acknowledged':True})
        body={'revision':master['revision'],'expected_version':master['shot_timeline']['version'],'expected_prepared_reference_sha256':digest(master['document']['prepared_narration']),
            'profile_refs':['social-square@1'],'request_key':'explicit-signed-narrated-variant-fixture'}
        return master,job,out,body,'/api/projects/'+master['id']+'/narrated-variants'
    def test_editor_create_viewer_family_and_exact_derived_audio_no_foreign_audio_authority(self):
        master,job,out,body,path=self.ready();before=self.server.store.get(master['id']);status,created,headers=self.request('POST',path,body)
        self.assertEqual(status,200,created);self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(created['actor_ref'],'explicit-fixture')
        self.assertTrue(self.request('POST',path,body)[1]['idempotent_replay']);self.assertEqual(self.server.store.get(master['id']),before)
        child=created['result']['variants'][0]['project_id'];audio_path='/api/projects/'+child+'/narration/'+job['id']+'/audio';self.account('viewer')
        status,page,_=self.request('GET','/api/projects/'+child+'/narration');self.assertEqual(status,200,page);self.assertEqual(page['items'],[])
        self.assertEqual(page['derived_narration']['source_result']['plan']['project_id'],master['id'])
        status,audio,headers=self.request('GET',audio_path);self.assertEqual(status,200);self.assertEqual(audio,(out/'voice.wav').read_bytes());self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.request('GET',path+'?limit=1')[0],200)
        with patch.object(Handler,'read_body',side_effect=AssertionError('No viewer mutation body read')):self.assertEqual(self.request('POST',path,body)[0],403)
        other=self.server.store.create('Other explicit fixture','No providers');self.assertEqual(self.request('GET',audio_path.replace(child,other['id']))[0],404)
        self.assertEqual(self.request('GET','/api/narrated/variant-profiles')[0],200);self.assertEqual(self.request('GET','/native-narrated-variants.mjs')[0],200);self.assertEqual(self.pipeline.calls,0)
    def test_narration_original_derived_and_family_reads_require_valid_session_and_origin(self):
        master,job,out,body,path=self.ready();created=self.request('POST',path,body)[1];child=created['result']['variants'][0]['project_id']
        routes=[path,'/api/narrated/variant-profiles']+[f'/api/projects/{identifier}/narration{suffix}' for identifier in [master['id'],child] for suffix in ['',f'/{job["id"]}/audio']]
        for route in routes:
            self.assertEqual(self.request('GET',route,headers={'Cookie':''})[0],401,route)
            self.assertEqual(self.request('GET',route,headers={'Origin':'https://hostile.invalid'})[0],403,route)
    def test_csrf_strict_body_expected_binding_and_cursor_never_enqueue_provider_work(self):
        master,job,out,body,path=self.ready();self.assertEqual(self.request('POST',path,body,{'X-VF-CSRF':'wrong'})[0],403)
        for fields in [{'revision':True},{'actor':'forged'},{'publish_enabled':True},{'profile_refs':[]}]:self.assertEqual(self.request('POST',path,{**body,**fields})[0],400)
        for fields in [{'expected_version':99},{'expected_prepared_reference_sha256':'0'*64}]:self.assertEqual(self.request('POST',path,{**body,**fields})[0],409)
        for query in ['limit=101','limit=1&limit=2','cursor=invalid','unknown=value']:self.assertEqual(self.request('GET',path+'?'+query)[0],400)
        self.assertTrue(self.request('GET','/api/session')[1]['capabilities']['native_narrated_variants']);self.assertEqual(len(self.server.store.get(master['id'])['jobs']),1)
