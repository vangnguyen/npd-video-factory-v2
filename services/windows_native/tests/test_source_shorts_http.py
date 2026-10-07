"""Authenticated Native draft contracts; explicit nonplayable HTTP media mock."""
import copy
import unittest
import uuid
from services.windows_native.tests import test_phase10_http as fixture
from services.windows_native.tests.test_auto_edit_analysis import saved_asr
from services.windows_native.auto_edit_analysis import make_analysis
from services.windows_native.contracts import file_sha
from app.auto_edit_models import MediaMetadata
from app.auto_edit_providers import MediaSignals


class SourceShortsHTTPTests(unittest.TestCase):
    setUp=fixture.Phase10HTTPTests.setUp
    tearDown=fixture.Phase10HTTPTests.tearDown
    start_server=fixture.Phase10HTTPTests.start_server
    stop_server=fixture.Phase10HTTPTests.stop_server
    request=fixture.Phase10HTTPTests.request
    api=fixture.Phase10HTTPTests.api
    database_state=fixture.Phase10HTTPTests.database_state

    def test_boundary_initial_media_project_canonical_children_history_and_retry(self):
        store=self.server.store;root=store.create('HTTP Auto Shorts fixture','','media')
        path=self.config.data_root/'assets'/(uuid.uuid4().hex+'.mp4')
        path.write_bytes(b'Explicit nonplayable HTTP source mock; no decode/provider/Owner acceptance')
        asset={'id':path.name,'kind':'video','filename':'HTTP Source mock','sha256':file_sha(path),
            'rights_confirmed':True,'illustration':False,'duration_seconds':3.,'width':320,'height':240,'has_audio':True}
        root=store.append_media(root['id'],root['revision'],asset)
        job=store.enqueue(root['id'],root['revision'],'asr',uuid.uuid4().hex);job=store.claim()
        store.finish(job,result={'media_analysis':[saved_asr(asset)]});root=store.get(root['id'])
        record=make_analysis(root['id'],root['document'],asset,
            MediaMetadata(media_kind='video',detected_content_type='video/mp4',duration_seconds=3.,audio_codec='aac'),
            MediaSignals(((1.,.9),(2.,.9)),(),{'fixture':True,'provider_calls':0}))
        job=store.enqueue(root['id'],root['revision'],'auto_edit_analysis',uuid.uuid4().hex);job=store.claim()
        store.finish(job,result={'auto_edit_analyses':[record]});root=store.get(root['id']);before=copy.deepcopy(root)
        endpoint='/api/projects/'+root['id']+'/auto-edit/shorts'
        body={'revision':root['revision'],'payload':{'analysis_id':record['analysis']['analysis_id'],
            'transcript_id':record['analysis']['transcript']['transcript_id'],'request_key':uuid.uuid4().hex,'count':3}}
        self.assertEqual(self.api('GET',endpoint,headers={'Cookie':''})[0],401)
        self.assertEqual(self.api('GET',endpoint)[1]['batches'],[])
        state=self.database_state()
        for headers,status in [({'Cookie':''},401),({'X-VF-CSRF':'bad'},403),({'Origin':'https://foreign.invalid'},403)]:
            self.assertEqual(self.api('POST',endpoint,body,headers)[0],status)
        self.assertEqual(self.api('POST',endpoint,{**body,'actor_ref':'owner'})[0],400)
        self.assertEqual(self.api('POST',endpoint,{**body,'revision':True})[0],400)
        self.assertEqual(self.database_state(),state)
        status,result=self.api('POST',endpoint,body);self.assertEqual(status,200,result)
        self.assertEqual(result['batch']['generated_count'],3);self.assertEqual(result['batch']['provider_calls'],0)
        self.assertEqual(self.api('POST',endpoint,body)[1],result)
        self.assertEqual(store.get(root['id']),before)
        self.assertEqual(len(self.api('GET',endpoint)[1]['batches']),1)
        for child in result['projects']:
            self.assertIsNone(child['approval']);self.assertEqual(child['jobs'],[])
            self.assertEqual(child['shot_timeline']['snapshot']['height'],1920)
            self.assertTrue(child['shot_timeline']['snapshot']['metadata']['reframe_review']['needs_attention'])


if __name__=='__main__':unittest.main()
