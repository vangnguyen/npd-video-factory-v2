"""Native supporting-media fixtures: actual bytes, explicit saved ASR, no UAT."""
import copy
import unittest
from PIL import Image
from services.windows_native import source_broll as broll
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native import auto_edit_analysis as analysis
from services.windows_native.auto_edit_analysis import asset_reference
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.media import ingest_media
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.tests import test_source_preview as fixture


class SourceBrollTests(unittest.TestCase):
    setUp=fixture.NativeSourcePreviewTests.setUp
    tearDown=fixture.NativeSourcePreviewTests.tearDown
    save_analysis=fixture.NativeSourcePreviewTests.save_analysis
    real_source=fixture.NativeSourcePreviewTests.real_source
    wait=fixture.NativeSourcePreviewTests.wait

    def image(self,rights_confirmed=True):
        path=self.root/'blue-support.png';Image.new('RGB',(320,240),(10,25,180)).save(path)
        item=ingest_media(self.config,path,'image/png','Xin chào supporting.png',rights_confirmed=True,illustration=True)
        # Simulate an unverified historical record; current intake rejects it.
        item['rights_confirmed']=rights_confirmed
        item['explicit_fixture']=True
        self.project=self.store.append_media(self.project['id'],self.project['revision'],item)
        self.project=timeline.view(self.store,self.project['id'])
        return item

    def create_plan(self):
        self.project=broll.create(self.store,self.config,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version']})
        return self.project['document']['source_broll_plans'][-1]['plan']

    def select(self,plan,item,asset):
        self.project=broll.select(self.store,self.config,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'media_plan_id':plan['media_plan_id'],
            'expected_plan_version':plan['version'],'item_id':item['media_plan_item_id'],'asset_id':asset_reference(asset)})
        return self.project['document']['source_broll_plans'][-1]['plan']

    def apply(self,plan,item,**values):
        self.project=broll.apply(self.store,self.config,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'media_plan_id':plan['media_plan_id'],
            'expected_plan_version':plan['version'],'item_ids':[item['media_plan_item_id']],**values})

    def test_saved_plan_keeps_source_when_no_support_and_deduplicates_without_timeline_mutation(self):
        self.real_source();before=copy.deepcopy(self.project['document']['canonical_timeline']);plan=self.create_plan()
        self.assertEqual(self.project['document']['canonical_timeline'],before)
        self.assertTrue(all(item['source_asset_id'] is None for item in plan['items']))
        self.assertTrue(all(item['provenance']['fallback_keeps_original_footage'] for item in plan['items']))
        self.assertEqual(plan['configuration']['resolver_priority'][:5],['user_asset','licensed_stock','internal_library','ai_image','ai_video'])
        self.assertEqual(plan['provider_status']['semantic_vision'],'NOT_CONFIGURED')
        before=copy.deepcopy(self.project);self.create_plan();self.assertEqual(self.project,before)

    def test_manual_selection_placement_proxy_and_restore_preserve_source_audio(self):
        source=self.real_source();asset=self.image();before=copy.deepcopy(self.project);source_hash=file_sha(source)
        plan=self.create_plan();item=plan['items'][0]
        self.assertTrue(item['provenance']['supporting_candidates'])
        self.assertIsNone(item['provenance']['supporting_candidates'][0]['confidence'])
        plan=self.select(plan,item,asset);self.assertEqual(plan['version'],2)
        self.assertFalse(plan['media_assets'][-1]['publishing_allowed']);self.apply(plan,item)
        snapshot=self.project['shot_timeline']['snapshot'];old=before['shot_timeline']['snapshot']
        self.assertEqual(snapshot['duration_seconds'],old['duration_seconds'])
        for track in old['tracks']:
            if track['kind']=='broll':continue
            self.assertEqual(next(value for value in snapshot['tracks'] if value['track_id']==track['track_id'])['clips'],track['clips'])
        clips=[clip for track in snapshot['tracks'] if track['kind']=='broll' for clip in track['clips']]
        self.assertTrue(clips);self.assertTrue(all(clip['kind']=='image' and clip['source_end'] is None and clip['volume']==0 for clip in clips))
        manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
            self.assertTrue(set(clip['clip_id'] for clip in clips)<=set(value['manifest']['rendered_clip_ids']))
        finally:manager.close()
        applied=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_BROLL_PLACEMENT_INVALID'):self.apply(plan,item)
        self.assertEqual(timeline.view(self.store,self.project['id']),applied)
        self.project=timeline.restore(self.store,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'restore_revision':before['revision']})
        self.assertEqual(self.project['shot_timeline']['snapshot'],old);self.assertEqual(file_sha(source),source_hash)

    def test_stale_plan_transcript_and_changed_asset_reject_without_mutation(self):
        self.real_source();asset=self.image();plan=self.create_plan();item=plan['items'][0]
        selected=self.select(plan,item,asset);before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_BROLL_PLAN_VERSION_CHANGED'):self.apply(plan,item)
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        path=self.root/'assets'/asset['id'];path.write_bytes(b'explicit corrupt isolated image fixture')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED_OR_MISSING'):self.apply(selected,item)
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        bundle=analysis.view(self.store,self.project['id']);transcript=bundle['analyses'][0]['analysis']['transcript']
        analysis.edit_transcript(self.store,self.project['id'],bundle['revision'],transcript['analysis_id'],{
            'expected_version':transcript['version'],'expected_timeline_version':self.project['shot_timeline']['version'],
            'segments':[{'segment_id':transcript['segments'][0]['segment_id'],'text':'Vang Nguyễn.'}]})
        self.project=timeline.view(self.store,self.project['id']);before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_BROLL_TRANSCRIPT_CHANGED'):self.apply(selected,item)
        self.assertEqual(timeline.view(self.store,self.project['id']),before)

    def test_unknown_rights_foreign_selection_and_forged_body_reject_atomically(self):
        self.real_source();asset=self.image(False);plan=self.create_plan();item=plan['items'][0];before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'MEDIA_RIGHTS_CONFIRMATION_REQUIRED'):self.select(plan,item,asset)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_BROLL_SELECTION_INVALID'):
            self.select(plan,item,{**asset,'id':'f'*32+'.png'})
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_BROLL_REQUEST_INVALID'):
            broll.create(self.store,self.config,self.project['id'],self.project['revision'],{'expected_version':1,'provider':'fake'})
        self.assertEqual(timeline.view(self.store,self.project['id']),before)

    def test_placement_follows_split_speed_and_lock_then_explicit_replace(self):
        from services.windows_native.source_linked_edit import edit
        self.real_source();asset=self.image();plan=self.create_plan();item=plan['items'][0];plan=self.select(plan,item,asset)
        clip=self.project['shot_timeline']['shots'][0]['shot_id']
        def linked(operation):
            self.project=edit(self.store,self.project['id'],self.project['revision'],{
                'expected_version':self.project['shot_timeline']['version'],'operation':operation})
        linked({'type':'split','clip_id':clip,'at_seconds':1.3})
        linked({'type':'set_clip_properties','clip_id':clip,'speed':2})
        target=next(t for t in self.project['shot_timeline']['snapshot']['tracks'] if t['kind']=='broll')
        def lock(value):
            self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{
                'expected_version':self.project['shot_timeline']['version'],
                'operations':[{'type':'set_track_state','track_id':target['track_id'],'locked':value}]})
        lock(True);before=copy.deepcopy(self.project)
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_BROLL_PLACEMENT_INVALID'):self.apply(plan,item)
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        lock(False);self.apply(plan,item)
        source=[c for t in self.project['shot_timeline']['snapshot']['tracks'] if t['kind']=='source' for c in t['clips']]
        bclips=[c for t in self.project['shot_timeline']['snapshot']['tracks'] if t['kind']=='broll' for c in t['clips']]
        self.assertGreaterEqual(len(bclips),1)
        for bclip in bclips:
            start,end=bclip['metadata']['placement_source_window'];s=next(c for c in source if c['source_start']<=start and c['source_end']>=end)
            self.assertAlmostEqual(bclip['timeline_start'],s['timeline_start']+(start-s['source_start'])/s['speed'],places=5)
            self.assertAlmostEqual(bclip['duration'],(end-start)/s['speed'],places=5)
        old_ids={c['clip_id'] for c in bclips};self.apply(plan,item,replace_plan_clips=True)
        current=[c for t in self.project['shot_timeline']['snapshot']['tracks'] if t['kind']=='broll' for c in t['clips']]
        self.assertEqual(len(current),len(bclips));self.assertFalse(old_ids&{c['clip_id'] for c in current})


if __name__=='__main__':unittest.main()
