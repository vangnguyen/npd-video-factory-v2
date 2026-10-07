"""Authenticated crop contracts; stored analysis/nonplayable source are mocks."""
import unittest
import uuid
from services.windows_native.tests import test_phase10_http as fixture
from services.windows_native.tests.test_auto_edit_analysis import saved_asr
from services.windows_native.auto_edit_analysis import make_analysis
from services.windows_native.auto_edit_timeline import create
from services.windows_native.contracts import file_sha
from app.auto_edit_models import MediaMetadata
from app.auto_edit_providers import MediaSignals


class SourceReframeHTTPTests(unittest.TestCase):
    setUp=fixture.Phase10HTTPTests.setUp
    tearDown=fixture.Phase10HTTPTests.tearDown
    start_server=fixture.Phase10HTTPTests.start_server
    stop_server=fixture.Phase10HTTPTests.stop_server
    request=fixture.Phase10HTTPTests.request
    api=fixture.Phase10HTTPTests.api
    database_state=fixture.Phase10HTTPTests.database_state

    def test_authenticated_center_and_manual_path_bind_same_canonical_timeline(self):
        store=self.server.store;root=store.create('HTTP crop fixture','','media')
        path=self.config.data_root/'assets'/(uuid.uuid4().hex+'.mp4')
        path.write_bytes(b'Explicit nonplayable crop contract fixture')
        asset={'id':path.name,'kind':'video','filename':'Fixture.mp4','sha256':file_sha(path),
            'rights_confirmed':True,'illustration':False,'duration_seconds':3.,'width':320,'height':240,'has_audio':True}
        root=store.append_media(root['id'],root['revision'],asset)
        job=store.enqueue(root['id'],root['revision'],'asr',uuid.uuid4().hex);job=store.claim()
        store.finish(job,result={'media_analysis':[saved_asr(asset)]});root=store.get(root['id'])
        record=make_analysis(root['id'],root['document'],asset,
            MediaMetadata(media_kind='video',detected_content_type='video/mp4',duration_seconds=3.,width=320,height=240,audio_codec='aac'),
            MediaSignals(((1.,.9),(2.,.9)),(),{'fixture':True,'provider_calls':0}))
        job=store.enqueue(root['id'],root['revision'],'auto_edit_analysis',uuid.uuid4().hex);job=store.claim()
        store.finish(job,result={'auto_edit_analyses':[record]});root=store.get(root['id'])
        root=create(store,root['id'],root['revision'],{'analysis_id':record['analysis']['analysis_id'],
            'transcript_id':record['analysis']['transcript']['transcript_id']})
        endpoint='/api/projects/'+root['id']+'/auto-edit/timeline'
        body={'revision':root['revision'],'action':'reframe','payload':{'expected_version':1,'aspect_ratio':'4:5'}}
        before=self.database_state()
        for headers,status in [({'Cookie':''},401),({'X-VF-CSRF':'bad'},403),({'Origin':'https://foreign.invalid'},403)]:
            self.assertEqual(self.api('POST',endpoint,body,headers)[0],status)
        self.assertEqual(self.api('POST',endpoint,{**body,'actor_ref':'owner'})[0],400)
        self.assertEqual(self.api('POST',endpoint,{**body,'revision':True})[0],400)
        self.assertEqual(self.database_state(),before)
        status,project=self.api('POST',endpoint,body);self.assertEqual(status,200,project)
        meta=project['shot_timeline']['snapshot']['metadata'];self.assertTrue(meta['source_reframe_plan']['plan']['needs_attention'])
        self.assertIsNone(meta['source_reframe_plan']['tracking_confidence']);self.assertIsNone(project['approval'])
        self.assertEqual(project['shot_timeline']['snapshot']['aspect_ratio'],'4:5')
        self.assertEqual(self.api('POST',endpoint,body)[0],409)
        body={'revision':project['revision'],'action':'reframe','payload':{'expected_version':2,'aspect_ratio':'1:1',
            'mode':'manual_override','points':[{'time':0,'x':.2,'y':.5},{'time':2.9,'x':.8,'y':.5}]}}
        status,project=self.api('POST',endpoint,body);self.assertEqual(status,200,project)
        self.assertEqual(project['shot_timeline']['version'],3)
        self.assertEqual(project['shot_timeline']['snapshot']['metadata']['source_reframe_plan']['plan']['strategy'],'manual_override')
        self.assertEqual(file_sha(path),asset['sha256'])


if __name__=='__main__':unittest.main()
