"""Authenticated Owner-only exception fixtures, never actual legal clearance."""
import unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.rights_override import rights_sha
from services.windows_native.tests import test_access_http as fixture


class NativeRightsOverrideHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def payload(self):return {'revision':self.project['revision'],'asset_sha256':self.asset['sha256'],'expected_rights_sha256':rights_sha(self.asset),
        'action':'grant','reason':'EXPLICIT SYNTHETIC OWNER OVERRIDE HTTP FIXTURE','evidence_reference':'document://explicit-fixture',
        'valid_days':7,'allow_publishing_review':False,'acknowledged':True,'request_key':'native-owner-override-http-fixture-key'}

    def test_default_disabled_and_roles_before_body_csrf_no_browser_enablement(self):
        base='/api/projects/'+self.project['id']+'/rights-overrides';before=self.server.store.get(self.project['id'])
        status,page,_=self.request('GET',base);self.assertEqual(status,200);self.assertFalse(page['enabled'])
        self.assertFalse(page['publishing_enabled']);self.assertEqual(page['history'],[])
        self.assertEqual(self.request('POST',base+'/'+self.asset['id'],self.payload())[0],403)
        self.assertEqual(self.request('POST',base+'/'+self.asset['id'],{**self.payload(),'enabled':True})[0],400)
        self.assertEqual(self.request('POST',base+'/'+self.asset['id'],self.payload(),{'X-VF-CSRF':'wrong'})[0],403)
        for role in ('viewer','editor','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized override body not read')):
                self.assertEqual(self.request('POST',base+'/'+self.asset['id'],self.payload())[0],403)
            self.assertEqual(self.request('GET',base)[0],200)
        self.assertEqual(self.server.store.get(self.project['id']),before)

    def test_explicit_fixture_enablement_bound_actor_unknown_rights_history_and_replay(self):
        # Test-only injection. The live server/CLI remains default-disabled.
        self.server.rights_overrides.enabled=True;base='/api/projects/'+self.project['id']+'/rights-overrides';before=self.server.store.get(self.project['id'])
        status,value,headers=self.request('POST',base+'/'+self.asset['id'],self.payload());self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(value['record']['actor_ref'],'explicit-fixture');self.assertFalse(value['record']['publishing_authorized'])
        current=self.server.store.get(self.project['id']);self.assertIsNone(current['approval']);self.assertEqual(current['document']['assets'],before['document']['assets'])
        status,replay,_=self.request('POST',base+'/'+self.asset['id'],self.payload());self.assertEqual(status,200);self.assertTrue(replay['idempotent_replay'])
        self.account('viewer');status,page,_=self.request('GET',base);self.assertEqual(status,200);self.assertEqual(len(page['history']),1)
        self.assertEqual(page['items'][0]['asset_sha256'],self.asset['sha256']);self.assertEqual(page['items'][0]['active_override'],value['record'])
