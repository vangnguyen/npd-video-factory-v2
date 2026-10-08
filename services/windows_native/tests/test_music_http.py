"""Real local music bytes and signed HTTP role boundaries; no Owner legal/UAT."""
import http.client,json,threading,unittest
from unittest.mock import patch
from services.windows_native.tests import test_source_music as fixture,test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as identity
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.contracts import file_sha
from services.windows_native.source_assets import canonical_assets
from services.windows_native.rights_override import rights_sha

class MusicHTTPTests(unittest.TestCase):
    setUp_parent=fixture.SourceMusicTests.setUp
    tearDown_parent=fixture.SourceMusicTests.tearDown
    real_source=fixture.SourceMusicTests.real_source
    save_analysis=fixture.SourceMusicTests.save_analysis
    music=fixture.SourceMusicTests.music
    request=access_fixture.NativeAccessHTTPTests.request
    account=access_fixture.NativeAccessHTTPTests.account
    def setUp(self):
        self.setUp_parent();self.real_source();self.asset=self.music();self.raw,data=identity('owner')
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),'wsp_native_fixture')
        self.server=LocalServer(0,self.config,start_worker=False,access=access);self.cookie,session=access.login(self.raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tearDown_parent()
    def upload(self,fade='0.25',project=None,extra=None):
        project=project or self.project;raw=(self.root/'originals'/self.asset['original_id']).read_bytes()
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        connection.request('POST',f"/api/projects/{project['id']}/music",raw,headers={
            'Cookie':'vf_native_session='+self.cookie,'X-VF-CSRF':self.csrf,'Content-Type':'audio/wav',
            'X-VF-Revision':str(project['revision']),'X-VF-Rights':'confirmed','X-VF-Music-Loop-Crossfade':fade,**(extra or {})})
        response=connection.getresponse();value=json.loads(response.read());connection.close();return response.status,value
    def test_real_music_upload_overlap_and_invalid_headers_legacy_csrf_do_not_create_assets(self):
        before={p.name:file_sha(p) for d in ('assets','originals') for p in (self.root/d).iterdir() if p.is_file()}
        for fade in ['NaN','1.1','0.1234','0.75']:
            self.assertEqual(self.upload(fade)[0],400)
        legacy=self.store.create('Legacy fixture','No canonical source')
        self.assertEqual(self.upload(project=legacy)[0],400);self.assertEqual(self.upload(extra={'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual({p.name:file_sha(p) for d in ('assets','originals') for p in (self.root/d).iterdir() if p.is_file()},before)
        self.account('editor');status,self.project=self.upload();self.assertEqual(status,201)
        clips=self.project['document']['canonical_timeline']['snapshot']['tracks'][-1]['clips']
        self.assertEqual([c['timeline_start'] for c in clips],[0,.75,1.5,2.25]);self.assertIsNone(self.project['approval'])
    def test_music_id_owner_declaration_exception_revoke_and_role_guards_before_body(self):
        status,self.project=self.upload('0');self.assertEqual(status,201)
        music=self.project['document']['music'];base=f"/api/projects/{self.project['id']}"
        body={'revision':self.project['revision'],'asset_sha256':music['sha256'],'claimed_source_type':'user_upload','claimed_rights':'owned',
            'provider':'explicit-owner-fixture','source_reference':'upload://'+music['original_id'],'acknowledged':True,'request_key':'music-http-declare-fixture'}
        self.assertEqual(self.request('POST',base+'/rights/'+music['id'],body)[0],200)
        current=self.store.get(self.project['id']);asset=next(a for a in canonical_assets(current['document']) if a['id']==music['id'])
        request={'revision':current['revision'],'asset_sha256':music['sha256'],'expected_rights_sha256':rights_sha(asset),'action':'grant',
            'reason':'EXPLICIT SYNTHETIC OWNER EXCEPTION, NO LEGAL CLEARANCE','evidence_reference':'document://music-http-fixture',
            'valid_days':7,'allow_publishing_review':True,'acknowledged':True,'request_key':'music-http-grant-fixture'}
        self.assertEqual(self.request('POST',base+'/rights-overrides/'+music['id'],request)[0],403)
        self.server.rights_overrides.enabled=True;status,grant,_=self.request('POST',base+'/rights-overrides/'+music['id'],request);self.assertEqual(status,200)
        self.assertFalse(grant['record']['rights_independently_verified']);self.assertFalse(grant['record']['publishing_authorized'])
        for role in ('viewer','editor','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized music-rights body must not be read')):
                self.assertEqual(self.request('POST',base+'/rights/'+music['id'],body)[0],403)
                self.assertEqual(self.request('POST',base+'/rights-overrides/'+music['id'],request)[0],403)
            self.assertEqual(self.request('GET',base+'/rights')[0],200)
        self.account('owner');current=self.store.get(self.project['id']);self.server.rights_overrides.enabled=False
        status,receipt,_=self.request('POST',base+'/rights-overrides/'+music['id'],{**request,'revision':current['revision'],'action':'revoke',
            'override_id':grant['record']['override_id'],'expected_override_sha256':grant['record']['sha256'],
            'allow_publishing_review':False,'request_key':'music-http-revoke-fixture'})
        self.assertEqual(status,200);self.assertEqual(receipt['record']['request']['action'],'revoke')
        self.assertEqual(self.store.get(self.project['id'])['document']['music']['rights_status'],'unknown')

if __name__=='__main__':unittest.main()
