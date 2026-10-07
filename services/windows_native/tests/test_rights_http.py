"""Human role/CSRF rights declarations on actual owned image fixtures."""
import unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.tests import test_access_http as fixture


class NativeRightsHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def payload(self):
        return {'revision':self.project['revision'],'asset_sha256':self.asset['sha256'],'claimed_source_type':'user_upload',
            'claimed_rights':'owned','acknowledged':True,'request_key':'native-rights-http-owned-fixture-key'}

    def test_owner_record_invalidates_approval_but_never_verifies_and_viewer_reads_only(self):
        base='/api/projects/'+self.project['id']+'/rights';old=self.server.store.get(self.project['id']);self.assertIsNotNone(old['approval'])
        status,row,headers=self.request('POST',base+'/'+self.asset['id'],self.payload());self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(row['declaration']['actor_ref'],'explicit-fixture');self.assertFalse(row['declaration']['verified'])
        self.assertIsNone(self.server.store.get(self.project['id'])['approval']);self.assertEqual(self.server.store.versions(self.project['id'])[1]['document'],old['document'])
        self.account('viewer');status,page,_=self.request('GET',base);self.assertEqual(status,200);self.assertFalse(page['owner_override_enabled'])
        self.assertTrue(page['unknown_rights_block_publishing'])
        for role in ('viewer','editor','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('No unauthorized rights declaration body read')):
                self.assertEqual(self.request('POST',base+'/'+self.asset['id'],self.payload())[0],403)

    def test_csrf_extra_override_stale_revision_and_unknown_asset_fail_closed(self):
        base='/api/projects/'+self.project['id']+'/rights';before=self.server.store.get(self.project['id'])
        self.assertEqual(self.request('POST',base+'/'+self.asset['id'],self.payload(),{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('POST',base+'/'+self.asset['id'],{**self.payload(),'owner_override':True})[0],400)
        self.assertEqual(self.request('POST',base+'/'+self.asset['id'],{**self.payload(),'revision':1})[0],409)
        self.assertEqual(self.request('POST',base+'/'+'a'*32+'.jpg',self.payload())[0],404)
        self.assertEqual(self.server.store.get(self.project['id']),before)


if __name__=='__main__':unittest.main()
