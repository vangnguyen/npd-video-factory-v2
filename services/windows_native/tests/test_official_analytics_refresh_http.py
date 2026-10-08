"""Actual signed HTTP/Runner tests; explicit synthetic source/account wires."""
import unittest,json
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests.test_official_analytics_http import OfficialAnalyticsHTTPFixture
from services.windows_native.tests.test_official_analytics_refresh import OfficialRefreshFixture
from services.windows_native.official_analytics_refresh import NativeOfficialAnalyticsRefresh
from services.windows_native.server import LocalServer,Handler
from services.windows_native.contracts import WorkflowError

class OfficialRefreshHTTPFixture(OfficialAnalyticsHTTPFixture):
    refresh_payload=OfficialRefreshFixture.refresh_payload
    def setUp(self):
        super().setUp();self.refresh=NativeOfficialAnalyticsRefresh(self.analytics,enabled=True)
        self.server.official_analytics_refresh=self.server.runner.official_analytics_refresh=self.refresh
        self.refresh_base='/api/projects/'+self.project['id']+'/official-analytics-refresh'
    def create_refresh_http(self,**changes):
        self.refresh_request=self.refresh_payload(**changes).model_dump(mode='json')
        status,value,headers=self.request('POST',self.refresh_base,self.refresh_request)
        self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');self.saved_plan=value;return value

class OfficialRefreshHTTPTests(OfficialRefreshHTTPFixture,unittest.TestCase):
    def test_actual_studio_module_parent_and_html_bytes_are_served_without_provider_or_session_enablement(self):
        root=Path(__file__).resolve().parents[3]/'apps'/'studio-web'
        session_before=self.request('GET','/api/session')[1]
        for name in ('native-official-refresh.mjs','native.html','native.mjs'):
            status,value,headers=self.request('GET','/'+name)
            self.assertEqual(status,200);self.assertEqual(value,(root/name).read_bytes())
            self.assertNotIn(self.read_credential.token.encode(),value)
        self.assertEqual(self.request('GET','/api/session')[1],session_before)
        self.assertNotIn('native_official_analytics_refresh',session_before['capabilities'])
        self.assertEqual(self.read_wire,[]);self.assertFalse(self.server.runner.run_one())
    def test_signed_creation_is_inert_runner_appends_two_original_snapshots_and_source_events(self):
        self.assertFalse(self.server.runner.run_one());runtime=self.request('GET','/api/connections/official-analytics-refresh')[1]
        self.assertTrue(runtime['enabled']);self.assertFalse(runtime['default_enabled']);self.assertFalse(runtime['publishing_enabled'])
        before=self.server.store.get(self.project['id']);plan=self.create_refresh_http(max_runs=2);self.assertEqual(plan['run_count'],0);self.assertEqual(self.read_wire,[])
        self.assertTrue(self.server.runner.run_one());first=self.request('GET',self.refresh_base+'/'+plan['plan_id'])[1]
        self.assertEqual(first['run_count'],1);self.assertEqual(first['occurrences'][0]['sync']['status'],'succeeded');self.assertEqual(len(self.read_wire),3)
        self.assertFalse(self.server.runner.run_one());self.clock[0]+=timedelta(seconds=60);self.assertTrue(self.server.runner.run_one());self.assertTrue(self.server.runner.run_one());self.assertFalse(self.server.runner.run_one())
        value=self.request('GET',self.refresh_base+'/'+plan['plan_id'])[1];self.assertEqual(value['status'],'completed');self.assertEqual(len(self.read_wire),6)
        self.assertEqual(first['occurrences'][0]['sync'],value['occurrences'][0]['sync']);self.assertEqual(before,self.server.store.get(self.project['id']))
        events=self.server.bridge.page(limit=100)['items'];analytics=[e for e in events if e['envelope']['payload'].get('source_type')=='analytics'];self.assertEqual(len(analytics),2)
        self.assertTrue(all(e['envelope']['payload']['mock'] and not e['envelope']['payload']['real_audience_observation'] for e in analytics));self.assertNotIn(self.read_credential.token,json.dumps(value))
    def test_owner_role_and_csrf_are_checked_before_body_or_credential_read(self):
        for role in ('editor','reviewer','viewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO FORBIDDEN BODY')):
                self.assertEqual(self.request('POST',self.refresh_base,{})[0],403)
                self.assertEqual(self.request('POST',self.refresh_base+'/noap_'+'a'*32+'/cancel',{})[0],403)
            self.assertEqual(self.request('GET',self.refresh_base)[0],200)
            self.assertEqual(self.request('GET','/api/connections/official-analytics-refresh')[0],403)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('NO MISSING CSRF BODY')):
            self.assertEqual(self.request('POST',self.refresh_base,{}, {'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.read_wire,[])
    def test_raw_fields_unknown_authority_and_conflicting_keys_refuse(self):
        body=self.refresh_payload().model_dump(mode='json')
        for changes in ({'acknowledged_background_reads':1},{'max_runs':True},{'enabled':True},{'authority':{}},{'token':'NEVER'},{'endpoint':'https://untrusted.invalid'},{'deadline':'2026-10-01T00:00:00'}):
            self.assertEqual(self.request('POST',self.refresh_base,{**body,**changes})[0],400)
        value=self.create_refresh_http();self.assertTrue(self.request('POST',self.refresh_base,self.refresh_request)[1]['idempotent_replay'])
        self.assertEqual(self.request('POST',self.refresh_base,{**self.refresh_request,'max_runs':4})[0],409);self.assertEqual(value['run_count'],0);self.assertEqual(self.read_wire,[])
    def test_cancellation_exact_version_requires_explicit_pending_choice_and_preserves_records(self):
        value=self.create_refresh_http();path=self.refresh_base+'/'+value['plan_id']+'/cancel'
        body={'expected_policy_sha256':value['policy_sha256'],'expected_version':value['version'],'cancel_pending_read':True}
        self.assertEqual(self.request('POST',path,{**body,'cancel_pending_read':1})[0],400)
        self.assertEqual(self.request('POST',path,{**body,'expected_policy_sha256':'f'*64})[0],409)
        self.assertTrue(self.server.runner.run_one());self.assertEqual(self.request('POST',path,body)[0],409)
        current=self.request('GET',self.refresh_base+'/'+value['plan_id'])[1];done=self.request('POST',path,{**body,'expected_version':current['version']})[1]
        self.assertEqual(done['status'],'cancelled');self.assertFalse(self.server.runner.run_one());self.assertEqual(len(self.read_wire),3)
        self.assertEqual(done['occurrences'][0]['sync']['status'],'succeeded')
    def test_bounded_scoped_history_and_default_disabled_restart_no_reads(self):
        value=self.create_refresh_http();self.account('viewer')
        for query in ('?limit=0','?limit=101','?limit=1&limit=2','?cursor=[]','?token=NEVER','?publication=npub_'+'a'*32):self.assertEqual(self.request('GET',self.refresh_base+query)[0],400)
        other=self.server.store.create('Other finite refresh fixture','','media');base='/api/projects/'+other['id']+'/official-analytics-refresh'
        self.assertEqual(self.request('GET',base+'/'+value['plan_id'])[0],404);self.assertEqual(self.request('GET',self.refresh_base+'/'+value['plan_id']+'?token=NEVER')[0],400)
        with LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.server.access) as disabled:
            self.assertFalse(disabled.official_analytics_refresh.states()['enabled']);self.assertFalse(disabled.runner.run_one())
            self.assertEqual(disabled.official_analytics_refresh.get(self.project['id'],value['plan_id'])['run_count'],0)
        self.assertEqual(self.read_wire,[])
    def test_unsafe_flag_relationships_refuse_before_socket_and_startup_token_resolve(self):
        options=({'official_analytics_refresh_enabled':1},{'official_analytics_refresh_enabled':True},
            {'official_analytics_refresh_enabled':True,'official_analytics_enabled':True,'access':self.server.access})
        for values in options:
            with (patch('services.windows_native.server.ThreadingHTTPServer.__init__',side_effect=AssertionError('NO UNSAFE SOCKET')),
                patch('services.windows_native.official_account_registry.token_load',side_effect=AssertionError('NO STARTUP TOKEN'))):
                with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,**values)
        self.assertEqual(self.read_wire,[])
