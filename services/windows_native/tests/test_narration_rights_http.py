"""Actual signed HTTP guard fixtures; no real Owner voice/legal decision."""
import unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.tests import test_access_http as fixture

class NarrationRightsHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account
    def test_default_disabled_read_no_mutation_and_owner_only_before_body(self):
        path='/api/projects/'+self.project['id']+'/narration-rights';before=self.server.store.get(self.project['id'])
        status,page,headers=self.request('GET',path);self.assertEqual(status,200);self.assertFalse(page['enabled']);self.assertIsNone(page['provenance']);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.request('POST',path,{},headers={'X-VF-CSRF':'wrong'})[0],403)
        for role in ('viewer','editor','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body must not be read')):self.assertEqual(self.request('POST',path,{})[0],403)
            self.assertEqual(self.request('GET',path)[0],200)
        self.assertEqual(self.server.store.get(self.project['id']),before)
    def test_owner_actor_is_bound_and_browser_flags_are_rejected(self):
        path='/api/projects/'+self.project['id']+'/narration-rights'
        with patch.object(self.server.narration_rights,'record',return_value={'explicit_wire_fixture':True}) as record:
            self.assertEqual(self.request('POST',path,{'actor':'spoofed-owner'})[0],200);self.assertEqual(record.call_args.kwargs['actor'],'explicit-fixture')
        self.assertEqual(self.request('POST',path,{'enabled':True})[0],400)
        self.assertEqual(self.request('GET',path+'?enabled=true')[0],404)
