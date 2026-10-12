import copy,unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.channel_profiles import catalog
from services.windows_native.tests import test_access_http as fixture

class ChannelRegistryHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account
    def body(self):
        profile=copy.deepcopy(catalog()['profiles'][0]);profile.update(profile_ref='http-owned@1',name='HTTP owner profile');profile['niche_profile'].update(target_audience='Khán giả riêng',tone='Giải thích có kiểm chứng')
        return {'profile_key':'http-owned','action':'save','expected_revision':0,'expected_binding_sha256':None,'profile':profile,'request_key':'http-owner-profile-request1'}
    def test_owner_saves_editor_selects_frozen_override_and_archive_never_changes_project(self):
        self.account('owner');status,value,_=self.request('POST','/api/channel-profiles/admin',self.body());self.assertEqual(status,200);first=value['item']
        self.assertEqual(self.request('GET','/api/channel-profiles/admin')[0],200)
        self.account('editor');status,project,_=self.request('POST','/api/projects',{'name':'Registry HTTP project','prompt':'Owned manual input','channel_profile_ref':'http-owned@1'});self.assertEqual(status,201)
        self.assertEqual(project['document']['content_profile']['target_audience'],'Khán giả riêng');self.assertEqual(project['document']['content_profile']['tone'],'Giải thích có kiểm chứng')
        self.assertEqual(self.pipeline.calls,0);self.account('owner')
        status,_,_=self.request('POST','/api/channel-profiles/admin',{'profile_key':'http-owned','action':'archive','expected_revision':first['revision'],'expected_binding_sha256':first['binding_sha256'],'request_key':'http-owner-profile-archive1'});self.assertEqual(status,200)
        self.assertEqual(self.request('GET','/api/projects/'+project['id'])[1],project)
        self.assertEqual(self.request('POST','/api/projects',{'name':'Archived profile','prompt':'Owned','channel_profile_ref':'http-owned@1'})[0],409)
    def test_editor_reviewer_viewer_denied_before_management_body_or_history_read(self):
        for role in ['editor','reviewer','viewer']:
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Nonowner body must not be consumed')):
                self.assertEqual(self.request('POST','/api/channel-profiles/admin',self.body())[0],403)
            self.assertEqual(self.request('GET','/api/channel-profiles/admin')[0],403)
            self.assertEqual(self.request('GET','/api/channel-profiles/admin/http-owned/history')[0],403)
            self.assertEqual(self.request('GET','/api/channel-profiles')[0],200)
    def test_csrf_origin_malformed_and_enablement_fail_atomically(self):
        self.account('owner');before=self.server.channel_registry.page()
        for headers in [{'X-VF-CSRF':'wrong'},{'Origin':'https://hostile.invalid'}]:self.assertEqual(self.request('POST','/api/channel-profiles/admin',self.body(),headers)[0],403)
        body=self.body();body['profile']['publishing_profile']['enabled']=True
        self.assertEqual(self.request('POST','/api/channel-profiles/admin',body)[0],400)
        self.assertEqual(self.server.channel_registry.page(),before)
        self.assertEqual(self.request('GET','/api/channel-profiles/admin/http-owned/history?limit=0')[0],400)

if __name__=='__main__':unittest.main()
