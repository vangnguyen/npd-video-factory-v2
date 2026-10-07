"""Actual local media/ASR fixture and scoped Owner exception, not legal acceptance."""
from datetime import datetime,timedelta,timezone
import unittest
from PIL import Image
from services.windows_native.tests import test_source_broll as fixture
from services.windows_native.media import ingest_media
from services.windows_native.rights_override import NativeRightsOverrides,rights_sha
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native.contracts import WorkflowError


class NativeRightsOverrideBrollTests(unittest.TestCase):
    setUp=fixture.SourceBrollTests.setUp
    tearDown=fixture.SourceBrollTests.tearDown
    save_analysis=fixture.SourceBrollTests.save_analysis
    real_source=fixture.SourceBrollTests.real_source
    wait=fixture.SourceBrollTests.wait
    create_plan=fixture.SourceBrollTests.create_plan
    select=fixture.SourceBrollTests.select
    apply=fixture.SourceBrollTests.apply

    def test_local_exception_allows_explicit_unknown_rights_placement_then_expiry_blocks_reapply(self):
        self.real_source();source=self.root/'explicit-owned-local-exception-fixture.png';Image.new('RGB',(320,240),(55,90,110)).save(source)
        asset=ingest_media(self.config,source,'image/png','EXPLICIT SYNTHETIC LOCAL EXCEPTION',rights_confirmed=True,illustration=False)
        self.project=self.store.append_media(self.project['id'],self.project['revision'],asset)
        clock=[datetime.now(timezone.utc)];service=NativeRightsOverrides(self.store,enabled=True,clock=lambda:clock[0])
        receipt=service.record(self.project['id'],asset['id'],{'revision':self.project['revision'],'asset_sha256':asset['sha256'],'expected_rights_sha256':rights_sha(asset),
            'action':'grant','reason':'EXPLICIT SYNTHETIC LOCAL PLACEMENT DECISION FIXTURE','evidence_reference':'document://explicit-local-fixture',
            'valid_days':1,'allow_publishing_review':False,'acknowledged':True,'request_key':'native-local-broll-exception-fixture-key'},actor='explicit-owner-fixture')
        self.project=timeline.view(self.store,self.project['id']);plan=self.create_plan();item=plan['items'][0];plan=self.select(plan,item,asset)
        provenance=plan['media_assets'][-1];self.assertEqual(provenance['rights_status'],'unknown');self.assertFalse(provenance['publishing_allowed'])
        self.assertEqual(provenance['provenance']['owner_rights_override']['sha256'],receipt['record']['sha256']);self.apply(plan,item)
        old=timeline.view(self.store,self.project['id']);self.assertTrue(any(track['clips'] for track in old['shot_timeline']['snapshot']['tracks'] if track['kind']=='broll'))
        clock[0]+=timedelta(days=1)
        with self.assertRaisesRegex(WorkflowError,'MEDIA_RIGHTS_CONFIRMATION_REQUIRED'):self.apply(plan,item,replace_plan_clips=True)
        self.assertEqual(timeline.view(self.store,self.project['id']),old)
