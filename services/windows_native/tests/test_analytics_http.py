import unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_publications import render_fixture


class NativeAnalyticsHTTPTests(unittest.TestCase):
    setUp=access_fixture.NativeAccessHTTPTests.setUp
    tearDown=access_fixture.NativeAccessHTTPTests.tearDown
    stop_server=access_fixture.NativeAccessHTTPTests.stop_server
    start_server=access_fixture.NativeAccessHTTPTests.start_server
    request=access_fixture.NativeAccessHTTPTests.request
    account=access_fixture.NativeAccessHTTPTests.account

    def prepared(self):
        project,job=render_fixture(self.server.store);service=self.server.publications
        pub,_=service.create(project['id'],NativePublicationCreate(revision=project['revision'],final_job_id=job['id'],platform='youtube',
            metadata={'title':'EXPLICIT HTTP ANALYTICS FIXTURE'},request_key='native-http-analytics-publication-fixture'),actor='fixture-editor')
        service.approve(project['id'],pub['publication_id'],NativePublishApproval(expected_fingerprint=pub['request_fingerprint'],
            expected_artifact_sha256=pub['snapshot']['final_sha256'],acknowledged=True),actor='fixture-owner');service.process()
        return project,{'publication_id':pub['publication_id'],'provider_mode':'fixture','fixture_profile':'insufficient_data',
            'fixture_acknowledged':True,'request_key':'native-http-analytics-fixture-key'},'/api/projects/'+project['id']+'/analytics'

    def test_owner_explicit_fixture_history_is_no_store_and_viewer_reads_without_actions(self):
        project,body,path=self.prepared();before=self.server.store.get(project['id'])
        status,row,headers=self.request('POST',path,body);self.assertEqual(status,200);self.assertEqual(row['actor_ref'],'explicit-fixture')
        self.assertEqual(headers['Cache-Control'],'no-store');route=path+'/'+row['sync_id']
        status,done,_=self.request('POST',route+'/process',{'expected_fingerprint':row['request_fingerprint']})
        self.assertEqual(status,200);self.assertEqual(done['status'],'succeeded');self.assertTrue(done['snapshot']['mock'])
        self.assertIsNone(done['snapshot']['metrics']['watch_time']);self.assertIsNone(done['snapshot']['features']['publishing_time'])
        self.account('viewer');self.assertEqual(self.request('GET',route)[0],200)
        self.assertEqual(self.request('GET','/api/analytics/overview?limit=1')[1]['items'][0]['snapshot_id'],done['snapshot_id'])
        with patch.object(Handler,'read_body',side_effect=AssertionError('No unauthorized analytics body read')):
            self.assertEqual(self.request('POST',path,body)[0],403)
        self.assertEqual(self.server.store.get(project['id']),before);self.assertEqual(self.pipeline.calls,0)

    def test_editor_csrf_scope_fixture_ack_and_official_no_fallback_guards(self):
        project,body,path=self.prepared();self.account('editor')
        with patch.object(Handler,'read_body',side_effect=AssertionError('No editor fixture generation')):
            self.assertEqual(self.request('POST',path,body)[0],403)
        self.account('owner');self.assertEqual(self.request('POST',path,body,{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('POST',path,{**body,'fixture_acknowledged':False})[0],400)
        self.assertEqual(self.request('POST',path,{**body,'actor_ref':'spoofed-owner'})[0],400)
        official={**body,'provider_mode':'official','fixture_profile':None,'fixture_acknowledged':False}
        status,row,_=self.request('POST',path,official);self.assertEqual(status,200);self.assertEqual(row['status'],'not_configured')
        self.assertIsNone(self.request('GET',path+'/'+row['sync_id'])[1]['snapshot'])
        self.assertEqual(self.request('GET',path.replace(project['id'],self.project['id'])+'/'+row['sync_id'])[0],404)
        self.assertEqual(self.request('GET',path+'?limit=101')[0],400);self.assertEqual(self.request('GET',path+'?limit=1&limit=2')[0],400)
        self.assertEqual(self.request('GET','/api/analytics/providers')[1]['external_calls_enabled'],False)
        self.assertTrue(self.request('GET','/api/session')[1]['capabilities']['native_analytics_review'])


if __name__=='__main__':unittest.main()
