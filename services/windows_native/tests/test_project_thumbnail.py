"""Actual media thumbnail bytes, legacy fallback and signed scope guards."""
import copy,http.client,json,threading,unittest,uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from services.windows_native.tests import test_media_frame_analysis as fixture
from services.windows_native.project_thumbnail import thumbnail
from services.windows_native.media_frame_analysis import frame_path
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from scripts.north_star_official_vision_http import access

class ProjectThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.MediaFrameTests();self.f.setUp();self.path=self.f.real_source()
    def tearDown(self):self.f.tearDown()
    def get(self):
        f=self.f;return thumbnail(f.store,f.config,f.project['id'],f.asset['id'])

    def test_existing_cpu_thumbnail_is_exact_png_without_provider_decode_or_project_mutation(self):
        f=self.f;f.measure();before=f.store.get(f.project['id']);versions=f.store.versions(f.project['id']);sha=file_sha(self.path)
        with patch('subprocess.run',side_effect=AssertionError('NO NEW DECODE')):
            path,basis=self.get()
        self.assertEqual(basis,'saved_cpu_pixel_frame');self.assertEqual(path.suffix,'.png')
        with Image.open(path) as value:self.assertEqual(value.format,'PNG')
        self.assertEqual(f.store.get(f.project['id']),before);self.assertEqual(f.store.versions(f.project['id']),versions);self.assertEqual(file_sha(self.path),sha)

    def test_unmeasured_legacy_video_gets_labeled_placeholder_never_mp4_in_image_response(self):
        f=self.f;before=copy.deepcopy(f.store.get(f.project['id']));path,basis=self.get()
        self.assertEqual(basis,'placeholder_no_measured_thumbnail');self.assertEqual(path.suffix,'.svg');self.assertIn('Chưa có ảnh xem trước',path.read_text(encoding='utf-8'))
        self.assertEqual(f.store.get(f.project['id']),before)

    def test_changed_source_and_corrupt_saved_frame_refuse_without_regeneration(self):
        f=self.f;f.measure();path,_=self.get();saved=path.read_bytes();path.write_bytes(saved+b'corrupt')
        with self.assertRaisesRegex(WorkflowError,'MEDIA_FRAME_ARTIFACT_CHANGED'):self.get()
        path.write_bytes(saved);self.path.write_bytes(self.path.read_bytes()+b'changed-source')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED_OR_MISSING'):self.get()

    def test_scope_foreign_asset_and_nonimage_registered_thumbnail_are_rejected(self):
        f=self.f
        with self.assertRaisesRegex(WorkflowError,'MEDIA_THUMBNAIL_SCOPE_INVALID'):thumbnail(f.store,replace(f.config,data_root=f.root/'foreign'),f.project['id'],f.asset['id'])
        other=f.store.create('Other fixture','','media')
        with self.assertRaisesRegex(WorkflowError,'MEDIA_NOT_IN_PROJECT'):thumbnail(f.store,f.config,other['id'],f.asset['id'])
        document=copy.deepcopy(f.store.get(f.project['id'])['document'])
        next(v for v in document['assets'] if v['id']==f.asset['id'])['thumbnail_id']=f.asset['id']
        with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(document),f.project['id']))
        with self.assertRaisesRegex(WorkflowError,'MEDIA_THUMBNAIL_IMAGE_INVALID'):self.get()

    def test_original_png_and_registered_jpeg_paths_preserve_exact_image_bytes(self):
        f=self.f;path=f.root/'assets'/(uuid.uuid4().hex+'.png');Image.new('RGBA',(320,240),(20,80,90,255)).save(path)
        asset={'id':path.name,'filename':'Owned PNG fixture','kind':'image','sha256':file_sha(path),'rights_confirmed':False,'illustration':False}
        project=f.store.append_media(f.project['id'],f.project['revision'],asset)
        actual,basis=thumbnail(f.store,f.config,project['id'],asset['id']);self.assertEqual(actual,path);self.assertEqual(basis,'original_image')
        thumb=f.root/'assets'/(uuid.uuid4().hex+'.thumb.jpg');Image.new('RGB',(160,120),(20,80,90)).save(thumb)
        document=copy.deepcopy(project['document']);next(v for v in document['assets'] if v['id']==asset['id'])['thumbnail_id']=thumb.name
        with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(document),project['id']))
        actual,basis=thumbnail(f.store,f.config,project['id'],asset['id']);self.assertEqual(actual,thumb);self.assertEqual(basis,'registered_ingest_thumbnail')

    def test_signed_thumbnail_and_range_video_are_distinct_mime_and_unauthenticated_scope_refuses(self):
        f=self.f;f.measure();raw,identity=access();cookie,_=identity.login(raw);pipeline=NoProviderPipeline()
        server=LocalServer(0,f.config,pipeline=pipeline,start_worker=False,access=identity);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(route,**headers):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            connection.request('GET',route,headers={'Cookie':'vf_native_session='+cookie,**headers});reply=connection.getresponse()
            value=(reply.status,reply.read(),dict(reply.getheaders()));connection.close();return value
        base='/api/projects/'+f.project['id']+'/media/'+f.asset['id']
        before=f.store.get(f.project['id'])
        try:
            code,body,headers=request(base+'/thumbnail');self.assertEqual(code,200);self.assertEqual(headers['Content-Type'],'image/png')
            self.assertEqual(headers['X-VF-Thumbnail-Basis'],'saved_cpu_pixel_frame');self.assertEqual(headers['X-VF-Semantic-Inference'],'false')
            self.assertEqual(body,self.get()[0].read_bytes());self.assertEqual(request(base+'/thumbnail',Cookie='')[0],401)
            code,body,headers=request(base,Range='bytes=0-63');self.assertEqual(code,206);self.assertEqual(headers['Content-Type'],'video/mp4');self.assertEqual(body,self.path.read_bytes()[:64])
            self.assertEqual(request('/api/projects/'+'f'*32+'/media/'+f.asset['id']+'/thumbnail')[0],404)
        finally:server.shutdown();server.server_close();thread.join()
        self.assertEqual(f.store.get(f.project['id']),before);self.assertEqual(pipeline.calls,0)
