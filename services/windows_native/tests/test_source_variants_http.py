"""Actual scoped Native HTTP; synthetic local video and saved ASR fixtures only."""
from dataclasses import replace
import json,subprocess,unittest,uuid
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.media import ingest_media
from services.windows_native import auto_edit_analysis as analysis,auto_edit_timeline as timeline
from services.windows_native.tests.test_auto_edit_analysis import saved_asr
from services.windows_native.tests import test_access_http as fixture

class SourceVariantHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def prepared(self):
        config=replace(self.config,ffmpeg_bin=Config().ffmpeg_bin);source=config.data_root/'explicit-http-variant-source.mp4'
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=3',
            '-f','lavfi','-i','sine=frequency=880:duration=3','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-t','3',str(source)],check=True,capture_output=True,timeout=30)
        asset=ingest_media(config,source,'video/mp4','EXPLICIT SYNTHETIC HTTP VARIANT FIXTURE',rights_confirmed=True,illustration=False)
        store=self.server.store;project=store.create('Generic HTTP source variant fixture','','media');project=store.append_media(project['id'],project['revision'],asset)
        with store.transaction() as con:
            document=project['document'];document['media_analysis']=[saved_asr(asset)]
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document),project['id']));store.version(con,project['id'])
        project=store.get(project['id']);job=store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex);job=store.claim()
        store.finish(job,result=Pipeline(config).run(job,lambda _:None));current=analysis.view(store,project['id']);selected=current['analyses'][0]['analysis']
        project=timeline.create(store,project['id'],current['revision'],{'analysis_id':selected['analysis_id'],'transcript_id':selected['transcript']['transcript_id']})
        return project,{'revision':project['revision'],'expected_version':project['shot_timeline']['version'],'profile_refs':['youtube-shorts@1','social-square@1'],
            'request_key':'native-http-variant-fixture-key'},'/api/projects/'+project['id']+'/variants'

    def test_editor_creation_and_viewer_reads_keep_independent_approval_boundary(self):
        project,body,path=self.prepared();self.account('editor');before=self.server.store.get(project['id'])
        status,created,headers=self.request('POST',path,body);self.assertEqual(status,200);self.assertEqual(created['actor_ref'],'explicit-fixture')
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(len(created['result']['variants']),2)
        self.assertTrue(self.request('POST',path,body)[1]['idempotent_replay']);self.assertEqual(self.server.store.get(project['id']),before)
        self.account('viewer');self.assertEqual(self.request('GET',path+'?limit=1')[0],200)
        child=created['result']['variants'][0]['project_id'];self.assertIsNone(self.request('GET','/api/projects/'+child)[1]['approval'])
        with patch.object(Handler,'read_body',side_effect=AssertionError('No viewer creation body read')):
            self.assertEqual(self.request('POST',path,body)[0],403)
        self.assertEqual(self.pipeline.calls,0);self.assertEqual(self.request('GET','/native-variants.mjs')[0],200)

    def test_csrf_strict_profiles_current_versions_and_page_scope_are_enforced(self):
        project,body,path=self.prepared();self.assertEqual(self.request('POST',path,body,{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('POST',path,body,{'Origin':'https://hostile.example'})[0],403)
        for fields in [{'revision':True},{'expected_version':True},{'profile_refs':[]},{'actor_ref':'forged-owner'},{'publish_enabled':True}]:
            self.assertEqual(self.request('POST',path,{**body,**fields})[0],400)
        self.assertEqual(self.request('POST',path,{**body,'profile_refs':['unknown@1']})[0],400)
        self.assertEqual(self.request('POST',path,{**body,'expected_version':99})[0],409)
        for query in ['limit=101','limit=1&limit=2','cursor=invalid','unknown=value']:
            self.assertEqual(self.request('GET',path+'?'+query)[0],400)
        self.assertEqual(self.request('GET',path.replace(project['id'],'f'*32))[0],404)
        self.assertEqual(len(self.request('GET','/api/auto-edit/variant-profiles')[1]['profiles']),6)
        self.assertTrue(self.request('GET','/api/session')[1]['capabilities']['native_source_variants'])


if __name__=='__main__':unittest.main()
