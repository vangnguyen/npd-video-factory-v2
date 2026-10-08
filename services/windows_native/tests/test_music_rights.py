"""Music intake IDs retain raw unknown rights and explicit project exception scopes."""
import copy,unittest
from services.windows_native.tests import test_source_music as fixture
from services.windows_native.rights import NativeRights
from services.windows_native.rights_override import NativeRightsOverrides,rights_sha,validate_publication_rights
from services.windows_native.source_assets import canonical_assets
from services.windows_native.contracts import WorkflowError,file_sha
from app.publishing_logic import validate_rights
from types import SimpleNamespace

class MusicRightsTests(unittest.TestCase):
    setUp=fixture.SourceMusicTests.setUp
    tearDown=fixture.SourceMusicTests.tearDown
    music=fixture.SourceMusicTests.music
    real_source=fixture.SourceMusicTests.real_source
    save_analysis=fixture.SourceMusicTests.save_analysis
    def prepare(self):
        self.real_source();self.asset=self.music();self.project=self.store.set_music(self.project['id'],self.project['revision'],self.asset)
        self.service=NativeRights(self.store,workspace_id='wsp_native_music_fixture')
        self.overrides=NativeRightsOverrides(self.store,workspace_id=self.service.workspace,enabled=True)
        self.declaration={'revision':self.project['revision'],'asset_sha256':self.asset['sha256'],'claimed_source_type':'user_upload',
            'claimed_rights':'owned','provider':'explicit-owner-fixture','source_reference':'upload://'+self.asset['original_id'],
            'acknowledged':True,'request_key':'native-music-rights-declaration-fixture'}
    def test_physical_music_declaration_exception_revoke_copy_and_corruption(self):
        self.prepare();sha=file_sha(self.root/'assets'/self.asset['id']);canonical=copy.deepcopy(self.project['document']['canonical_timeline'])
        receipt=self.service.declare(self.project['id'],self.asset['id'],self.declaration,actor='explicit-owner-fixture')
        current=self.store.get(self.project['id']);asset=next(a for a in canonical_assets(current['document']) if a['id']==self.asset['id'])
        self.assertFalse(receipt['declaration']['verified']);self.assertEqual(asset['rights_status'],'unknown')
        self.assertEqual(current['document']['canonical_timeline'],canonical);self.assertEqual(current['document']['music']['rights_status'],'unknown')
        self.assertEqual(current['document']['source_music_assets'][0]['rights_status'],'unknown')
        request={'revision':current['revision'],'asset_sha256':sha,'expected_rights_sha256':rights_sha(asset),
            'action':'grant','reason':'EXPLICIT SYNTHETIC MUSIC EXCEPTION, NO LEGAL CLEARANCE','evidence_reference':'document://explicit-music-fixture',
            'valid_days':7,'allow_publishing_review':True,'acknowledged':True,'request_key':'native-music-exception-grant-fixture'}
        granted=self.overrides.record(current['id'],asset['id'],request,actor='explicit-owner-fixture')
        current=self.store.get(current['id']);assets=[a for a in canonical_assets(current['document']) if a['id']==asset['id']]
        raw=validate_rights([SimpleNamespace(asset_id=a['id'],provenance=a) for a in assets]);self.assertEqual(raw.status,'failed')
        self.assertEqual(validate_publication_rights(self.store,current['document'],current['id'],assets,{asset['id']},raw).status,'passed')
        copied=self.store.duplicate(current['id'],current['revision']);self.assertNotIn('media_rights_overrides',copied['document'])
        self.assertNotIn('media_rights_declarations',copied['document']);self.assertIsNone(copied['approval'])
        revoked=self.overrides.record(current['id'],asset['id'],{**request,'revision':current['revision'],'action':'revoke',
            'override_id':granted['record']['override_id'],'expected_override_sha256':granted['record']['sha256'],
            'allow_publishing_review':False,'request_key':'native-music-exception-revoke-fixture'},actor='explicit-owner-fixture')
        doc=self.store.get(current['id'])['document'];self.assertIsNone(self.overrides.active(doc,current['id'],asset,publishing=True))
        self.assertEqual(revoked['record']['asset_id'],asset['id']);self.assertEqual(file_sha(self.root/'assets'/asset['id']),sha)
        path=self.root/'assets'/asset['id'];path.write_bytes(path.read_bytes()+b'EXPLICIT OWNED CORRUPTION FIXTURE')
        with self.assertRaises(WorkflowError):self.service.declare(current['id'],asset['id'],{**self.declaration,
            'revision':self.store.get(current['id'])['revision'],'request_key':'native-corrupted-music-declaration-fixture'},actor='explicit-owner-fixture')
    def test_restricted_music_propagates_and_arbitrary_suffix_rejects(self):
        self.prepare();self.service.declare(self.project['id'],self.asset['id'],{**self.declaration,'claimed_rights':'restricted'},actor='explicit-owner-fixture')
        current=self.store.get(self.project['id']);asset=next(a for a in canonical_assets(current['document']) if a['id']==self.asset['id'])
        self.assertEqual(asset['rights_status'],'restricted')
        self.assertEqual(current['document']['music']['rights_status'],'restricted');self.assertEqual(current['document']['source_music_assets'][0]['rights_status'],'restricted')
        before=copy.deepcopy(current)
        for identifier in ['a'*32+'.music.mp3','a'*32+'.music.wav.exe','../'+'a'*32+'.music.wav']:
            with self.assertRaises(WorkflowError):self.service.declare(current['id'],identifier,{**self.declaration,'revision':current['revision']},actor='explicit-owner-fixture')
        self.assertEqual(self.store.get(current['id']),before)

if __name__=='__main__':unittest.main()
