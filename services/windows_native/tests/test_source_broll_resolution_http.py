"""Actual loopback auth/CSRF routes; injected orchestration receipt is fixture."""
import unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.tests import test_access_http as fixture


class SourceBrollResolutionHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def base(self):
        return '/api/projects/'+self.project['id']+'/auto-edit/broll-resolutions'

    def test_read_is_zero_provider_no_mutation_and_query_is_rejected(self):
        before=self.server.store.get(self.project['id'])
        self.account('viewer')
        status,page,headers=self.request('GET',self.base())
        self.assertEqual(status,200); self.assertEqual(page['items'],[])
        self.assertEqual(page['provider_calls'],0); self.assertFalse(page['publishing_enabled'])
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.request('GET',self.base()+'?limit=1')[0],400)
        self.assertEqual(self.server.store.get(self.project['id']),before)
        self.assertEqual(self.request('GET','/api/projects/'+'f'*32+'/auto-edit/broll-resolutions')[0],404)

    def test_read_only_and_editor_provider_step_denied_before_body(self):
        paths=[self.base(),self.base()+'/nbr_'+'a'*32+'/step',self.base()+'/nbr_'+'a'*32+'/apply']
        for role in ('viewer','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized body consumed')):
                for path in paths:self.assertEqual(self.request('POST',path,{})[0],403)
        self.account('editor')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Editor cannot admit provider work')):
            self.assertEqual(self.request('POST',paths[1],{})[0],403)

    def test_csrf_same_origin_and_unknown_fields_precede_engine(self):
        base=self.base()
        with patch.object(self.server.source_broll_resolution,'create',side_effect=AssertionError('Invalid create admitted')):
            self.assertEqual(self.request('POST',base,{}, {'X-VF-CSRF':'wrong'})[0],403)
            self.assertEqual(self.request('POST',base,{}, {'Origin':'https://foreign.example'})[0],403)
            self.assertEqual(self.request('POST',base,{'download_url':'https://foreign.example/media'})[0],400)
            self.assertEqual(self.request('POST',base,{}, {'X-VF-Role':'owner','Cookie':''})[0],401)

    def test_explicit_owner_step_editor_apply_actor_and_replay_receipt(self):
        identity='nbr_'+'a'*32; body={'revision':self.project['revision'],
            'expected_resolution_version':1,'request_key':'explicit-source-broll-http-key'}
        def transition(project,resolution,payload,*,actor):
            self.assertEqual(project,self.project['id']);self.assertEqual(resolution,identity)
            self.assertEqual(actor,'explicit-fixture')
            return {'explicit_fixture':True,'automatic_video_approval':False,'publishing_enabled':False},True
        with patch.object(self.server.source_broll_resolution,'step',side_effect=transition) as step:
            status,receipt,headers=self.request('POST',self.base()+'/'+identity+'/step',body)
            self.assertEqual(status,200); self.assertTrue(receipt['idempotent_replay'])
            self.assertEqual(headers['Cache-Control'],'no-store'); step.assert_called_once()
        self.account('editor')
        with patch.object(self.server.source_broll_resolution,'apply',side_effect=transition) as apply:
            path=self.base()+'/'+identity+'/apply'
            self.assertEqual(self.request('POST',path,{**body,'expected_timeline_version':1,'acknowledged':False})[0],400)
            self.assertEqual(self.request('POST',path,{**body,'expected_timeline_version':1,'acknowledged':True})[0],200)
            apply.assert_called_once()


if __name__=='__main__':unittest.main()
