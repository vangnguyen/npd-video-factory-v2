"""Authenticated Native Vision contracts; real local PNGs, explicit semantic fixtures."""
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid
from PIL import Image
from services.windows_native.server import Handler
from services.windows_native.media import ingest_media
from services.windows_native.media_frame_analysis import view
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.tests import test_access_http as fixture
from services.windows_native.vision_provider import NativeFixtureVisionProvider


class NativeVisionHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def prepared(self):
        config=replace(self.config,ffmpeg_bin=Config().ffmpeg_bin)
        source=Path(self.temp.name)/'explicit-http-source.png';Image.new('RGB',(320,240),(20,130,240)).save(source)
        asset=ingest_media(config,source,'image/png','EXPLICIT HTTP FRAME FIXTURE',rights_confirmed=True,illustration=True)
        project=self.server.store.create('Generic HTTP Vision fixture','','media');project=self.server.store.append_media(project['id'],project['revision'],asset)
        job=self.server.store.enqueue(project['id'],project['revision'],'media_frames',uuid.uuid4().hex);job=self.server.store.claim()
        self.server.store.finish(job,result=Pipeline(config).run(job,lambda _:None));project=self.server.store.get(project['id'])
        frames=view(self.server.store,project['id'])
        return project,{'revision':project['revision'],'observation_ids':[frames['observations'][0]['observation_id']],
            'provider_mode':'fixture','fixture_acknowledged':True,'request_key':'native-http-vision-fixture-key'},'/api/projects/'+project['id']+'/vision'

    def test_owner_fixture_and_viewer_read_preserve_project_and_cpu_observations(self):
        project,body,path=self.prepared();before=self.server.store.get(project['id'])
        status,row,headers=self.request('POST',path,body);self.assertEqual(status,200);self.assertEqual(row['actor_ref'],'explicit-fixture')
        self.assertEqual(headers['Cache-Control'],'no-store');route=path+'/'+row['vision_id']
        status,done,_=self.request('POST',route+'/process',{'expected_fingerprint':row['request_fingerprint']});self.assertEqual(status,200)
        self.assertEqual(done['status'],'succeeded');self.assertFalse(done['result']['semantic_inference_performed'])
        self.assertEqual(self.request('GET',path+'?limit=1')[1]['items'][0]['result_sha256'],done['result_sha256'])
        self.account('viewer');self.assertEqual(self.request('GET',route)[0],200)
        with patch.object(Handler,'read_body',side_effect=AssertionError('No unauthorized Vision body read')):
            for action in ['', '/'+row['vision_id']+'/process','/'+row['vision_id']+'/cancel']:
                self.assertEqual(self.request('POST',path+action,body)[0],403)
        self.assertEqual(self.server.store.get(project['id']),before);self.assertEqual(self.pipeline.calls,0)
        self.assertEqual(self.request('GET','/native-vision.mjs')[0],200)

    def test_editor_csrf_scope_strict_ack_and_official_not_configured(self):
        project,body,path=self.prepared();self.account('editor')
        with patch.object(Handler,'read_body',side_effect=AssertionError('No editor mock inference')):
            self.assertEqual(self.request('POST',path,body)[0],403)
        self.account('owner');self.assertEqual(self.request('POST',path,body,{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('POST',path,body,{'Origin':'https://hostile.example'})[0],403)
        for fields in [{'fixture_acknowledged':False},{'fixture_acknowledged':1},{'actor_ref':'spoofed-owner'},{'revision':True}]:
            self.assertEqual(self.request('POST',path,{**body,**fields})[0],400)
        with patch.object(NativeFixtureVisionProvider,'analyze',side_effect=AssertionError('No official fallback')):
            status,row,_=self.request('POST',path,{**body,'provider_mode':'official','fixture_acknowledged':False})
            self.assertEqual(status,200);self.assertEqual(row['status'],'not_configured');self.assertIsNone(row['result'])
            self.assertIsNone(self.server.vision.process())
        self.assertEqual(self.request('GET',path.replace(project['id'],self.project['id'])+'/'+row['vision_id'])[0],404)
        for query in ['limit=101','limit=1&limit=2','cursor=bad','unknown=value']:
            self.assertEqual(self.request('GET',path+'?'+query)[0],400)
        capabilities=self.request('GET','/api/session')[1]['capabilities']
        self.assertTrue(capabilities['native_vision_review']);self.assertFalse(capabilities['native_official_vision'])


if __name__=='__main__':unittest.main()
