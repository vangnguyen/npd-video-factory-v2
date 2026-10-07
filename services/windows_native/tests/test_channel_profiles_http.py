import unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.tests import test_access_http as fixture

class ChannelProfileHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def test_editor_chooses_profile_at_creation_viewer_reads_and_cannot_create(self):
        self.account('editor');status,value,headers=self.request('GET','/api/channel-profiles');self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(len(value['profiles']),2)
        body={'name':'Explicit HTTP technology profile','prompt':'','input_kind':'media','channel_profile_ref':'ai-education-reference@1'}
        status,project,_=self.request('POST','/api/projects',body);self.assertEqual(status,201);self.assertEqual(project['document']['niche'],'technology')
        self.assertIsNone(project['approval']);self.assertEqual(project['jobs'],[]);self.assertEqual(self.pipeline.calls,0)
        self.account('viewer');self.assertEqual(self.request('GET','/api/channel-profiles')[0],200);self.assertEqual(self.request('GET','/api/projects/'+project['id'])[1]['document'],project['document'])
        with patch.object(Handler,'read_body',side_effect=AssertionError('Viewer never submits creation body')):self.assertEqual(self.request('POST','/api/projects',body)[0],403)
        self.assertEqual(self.request('GET','/native-channel-profiles.mjs')[0],200);self.assertTrue(self.request('GET','/api/session')[1]['capabilities']['native_channel_profiles'])

    def test_csrf_origin_unknown_or_conflicting_profile_fail_without_creation(self):
        before=self.server.store.list();body={'name':'Explicit profile guard','prompt':'','input_kind':'media','channel_profile_ref':'ai-education-reference@1'}
        for headers in [{'X-VF-CSRF':'wrong'},{'Origin':'https://hostile.invalid'}]:self.assertEqual(self.request('POST','/api/projects',body,headers)[0],403)
        for changes in [{'channel_profile_ref':True},{'channel_profile_ref':'unknown@1'},{'content_profile_id':'vietnam-property'}]:
            self.assertEqual(self.request('POST','/api/projects',{**body,**changes})[0],400)
        self.assertEqual(self.server.store.list(),before);self.assertEqual(self.pipeline.calls,0)

if __name__=='__main__':unittest.main()
