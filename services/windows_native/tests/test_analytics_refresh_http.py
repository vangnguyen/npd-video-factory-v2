from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.tests import test_analytics_http as fixtures


class NativeAnalyticsRefreshHTTPTests(unittest.TestCase):
    setUp=fixtures.NativeAnalyticsHTTPTests.setUp
    tearDown=fixtures.NativeAnalyticsHTTPTests.tearDown
    stop_server=fixtures.NativeAnalyticsHTTPTests.stop_server
    start_server=fixtures.NativeAnalyticsHTTPTests.start_server
    request=fixtures.NativeAnalyticsHTTPTests.request
    account=fixtures.NativeAnalyticsHTTPTests.account
    prepared=fixtures.NativeAnalyticsHTTPTests.prepared

    def policy(self):
        project,body,path=self.prepared()
        return project,{**body,'first_run_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
            'enabled':True,'acknowledged_read_only':True,'max_runs':2},path.replace('/analytics','/analytics-refresh')

    def test_signed_owner_recurring_worker_history_cancel_and_no_store(self):
        project,body,path=self.policy();before=self.server.store.get(project['id'])
        status,row,headers=self.request('POST',path,body);self.assertEqual(status,200)
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(row['created_by'],'explicit-fixture')
        self.assertTrue(self.request('POST',path,body)[1]['idempotent_replay'])
        status,tick,_=self.request('POST',path+'/tick',{});self.assertEqual(status,200);self.assertEqual(len(tick['created_sync_ids']),1)
        self.assertTrue(self.server.runner.run_one());sync=tick['created_sync_ids'][0]
        snapshot=self.request('GET',path.replace('/analytics-refresh','/analytics')+'/'+sync)[1]['snapshot']
        self.assertEqual(snapshot['evidence']['refresh_occurrence']['plan_id'],row['plan_id']);self.assertIsNone(snapshot['metrics']['revenue'])
        status,disabled,_=self.request('POST',path+'/'+row['plan_id']+'/state',{'expected_revision':1,'enabled':False})
        self.assertEqual(status,200);self.assertEqual(disabled['revision'],2)
        self.assertEqual(self.request('GET',path)[1]['items'][0]['status'],'paused')
        self.assertEqual(self.request('GET',path+'/'+row['plan_id'])[1]['occurrences'][0]['sync_id'],sync)
        self.assertEqual(self.server.store.get(project['id']),before);self.assertEqual(self.pipeline.calls,0)
        self.assertTrue(self.request('GET','/api/session')[1]['capabilities']['native_analytics_refresh'])

    def test_rbac_csrf_strict_scope_and_official_disabled(self):
        project,body,path=self.policy()
        for role in ['viewer','reviewer','editor']:
            self.account(role)
            self.assertEqual(self.request('GET',path)[0],200)
            with patch.object(Handler,'read_body',side_effect=AssertionError('No unauthorized policy body read')):
                for route in [path,path+'/tick',path+'/narp_'+'b'*32+'/state']:self.assertEqual(self.request('POST',route,body)[0],403)
        self.account('owner');self.assertEqual(self.request('POST',path,body,{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('POST',path,{**body,'fixture_acknowledged':False})[0],400)
        self.assertEqual(self.request('POST',path,{**body,'actor_ref':'spoofed-owner'})[0],400)
        official={**body,'provider_mode':'official','fixture_acknowledged':False,'fixture_profile':'normal','enabled':False}
        status,row,_=self.request('POST',path,official);self.assertEqual(status,200);self.assertEqual(row['status'],'not_configured')
        self.assertEqual(self.request('POST',path+'/'+row['plan_id']+'/state',{'expected_revision':1,'enabled':True,'acknowledged_read_only':True})[0],409)
        self.assertEqual(self.request('GET',path.replace(project['id'],self.project['id'])+'/'+row['plan_id'])[0],404)
        self.assertEqual(self.request('GET',path+'?limit=101')[0],400);self.assertEqual(self.request('GET',path+'?limit=1&limit=2')[0],400)
        self.assertEqual(self.request('POST',path+'/tick',{'at':'spoofed-clock'})[0],400)


if __name__=='__main__':unittest.main()
