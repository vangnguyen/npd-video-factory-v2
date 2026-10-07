"""Authenticated frame files and local measurements in a temporary HTTP workspace."""
import unittest
import uuid
from dataclasses import replace
from services.windows_native.tests import test_phase10_http as fixture
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.contracts import file_sha
from services.windows_native.media_frame_analysis import view,frame_path


class MediaFrameHTTPTests(unittest.TestCase):
    setUp=fixture.Phase10HTTPTests.setUp
    tearDown=fixture.Phase10HTTPTests.tearDown
    start_server=fixture.Phase10HTTPTests.start_server
    stop_server=fixture.Phase10HTTPTests.stop_server
    request=fixture.Phase10HTTPTests.request
    api=fixture.Phase10HTTPTests.api
    database_state=fixture.Phase10HTTPTests.database_state

    def test_authenticated_job_and_frame_file_are_project_scoped_and_checksum_bound(self):
        endpoint='/api/projects/'+self.project['id']+'/media-frames'
        before=self.database_state()
        self.assertEqual(self.api('GET',endpoint,headers={'Cookie':''})[0],401)
        status,value=self.api('GET',endpoint);self.assertEqual(status,200);self.assertEqual(value['observations'],[])
        self.assertEqual(self.database_state(),before)
        body={'revision':self.project['revision'],'kind':'media_frames','request_key':uuid.uuid4().hex}
        for headers,status in [({'Cookie':''},401),({'X-VF-CSRF':'bad'},403),({'Origin':'https://foreign.invalid'},403)]:
            self.assertEqual(self.api('POST','/api/projects/'+self.project['id']+'/jobs',body,headers)[0],status)
        self.assertEqual(self.database_state(),before)
        status,queued=self.api('POST','/api/projects/'+self.project['id']+'/jobs',body);self.assertEqual(status,200,queued)
        self.assertEqual(self.api('POST','/api/projects/'+self.project['id']+'/jobs',body)[1]['id'],queued['id'])
        job=self.server.store.claim()
        config=replace(self.config,ffmpeg_bin=Config().ffmpeg_bin)
        result=Pipeline(config).run(job,lambda stage:None);self.server.store.finish(job,result=result)
        status,bundle=self.api('GET',endpoint);self.assertEqual(status,200,bundle)
        frame=bundle['observations'][0]['frames'][0];url=endpoint+'/'+frame['frame_id']+'/image'
        status,raw,headers=self.request('GET',url);self.assertEqual(status,200)
        self.assertEqual(headers['Content-Type'],'image/png');self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(raw,frame_path(self.config.data_root,frame).read_bytes())
        self.assertEqual(self.api('GET',url,headers={'Cookie':''})[0],401)
        unrelated=self.server.store.create('Unrelated','','media')
        self.assertEqual(self.api('GET','/api/projects/'+unrelated['id']+'/media-frames/'+frame['frame_id']+'/image')[0],404)
        self.assertEqual(self.api('GET',endpoint+'/mfr_'+('f'*24)+'/image')[0],404)
        self.assertEqual(file_sha(self.config.data_root/'assets'/self.asset['id']),self.asset['sha256'])
        self.assertIsNone(self.server.store.get(self.project['id'])['approval'])
        frame_path(self.config.data_root,frame).write_bytes(b'Corrupt test frame')
        self.assertEqual(self.api('GET',url)[0],409)


if __name__=='__main__':unittest.main()
