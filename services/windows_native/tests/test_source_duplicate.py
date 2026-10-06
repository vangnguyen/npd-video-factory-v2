"""Independent rebound Source projects; actual synthetic bytes, saved ASR mock."""
import copy
import unittest
from services.windows_native import auto_edit_analysis as analysis,auto_edit_timeline as timeline
from services.windows_native import source_duplicate,source_broll
from services.windows_native.source_linked_edit import edit
from services.windows_native.contracts import WorkflowError,file_sha,digest
from services.windows_native.tests import test_source_broll as fixture


class SourceDuplicateTests(unittest.TestCase):
    setUp=fixture.SourceBrollTests.setUp
    tearDown=fixture.SourceBrollTests.tearDown
    save_analysis=fixture.SourceBrollTests.save_analysis
    real_source=fixture.SourceBrollTests.real_source
    image=fixture.SourceBrollTests.image
    create_plan=fixture.SourceBrollTests.create_plan
    select=fixture.SourceBrollTests.select
    apply=fixture.SourceBrollTests.apply

    def test_rebinds_edited_transcript_and_exact_clip_decisions_without_provider_or_parent_mutation(self):
        path=self.real_source();bundle=analysis.view(self.store,self.project['id']);current=bundle['analyses'][0]['analysis']['transcript']
        analysis.edit_transcript(self.store,self.project['id'],self.project['revision'],current['analysis_id'],{
            'expected_version':1,'expected_timeline_version':1,
            'segments':[{'segment_id':current['segments'][0]['segment_id'],'text':'Vang Nguyễn.'}]})
        self.project=timeline.view(self.store,self.project['id']);before=copy.deepcopy(self.project)
        old_versions=self.store.versions(self.project['id']);checksum=file_sha(path)
        child=self.store.duplicate(self.project['id'],self.project['revision'])
        self.assertNotEqual(child['id'],before['id']);self.assertEqual(child['revision'],1)
        self.assertEqual(child['shot_timeline']['version'],1);self.assertIsNone(child['approval']);self.assertEqual(child['jobs'],[])
        value=analysis.view(self.store,child['id']);self.assertFalse(value['pending_asset_ids'])
        old=before['document']['auto_edit_analyses'][0]['analysis'];new=value['analyses'][0]['analysis']
        self.assertNotEqual(new['analysis_id'],old['analysis_id']);self.assertEqual(new['project_id'],'prj_'+child['id'])
        self.assertEqual(new['transcript']['segments'][0]['text'],'Vang Nguyễn.')
        self.assertEqual(new['transcript']['segments'][0]['words'],[])
        self.assertNotEqual(new['transcript']['transcript_id'],current['transcript_id'])
        self.assertEqual(child['shot_timeline']['snapshot']['metadata']['native_project_id'],child['id'])
        self.assertEqual(child['shot_timeline']['snapshot']['metadata']['transcript_revision']['transcript_id'],new['transcript']['transcript_id'])
        old_source=next(t for t in before['shot_timeline']['snapshot']['tracks'] if t['kind']=='source')
        new_source=next(t for t in child['shot_timeline']['snapshot']['tracks'] if t['kind']=='source')
        for old_clip,new_clip in zip(old_source['clips'],new_source['clips'],strict=True):
            for key in ('source_start','source_end','timeline_start','duration','speed','volume','crop','transform','disabled'):
                self.assertEqual(old_clip[key],new_clip[key])
        clip=new_source['clips'][0]
        edit(self.store,child['id'],child['revision'],{'expected_version':1,
            'operation':{'type':'trim','clip_id':clip['clip_id'],'source_start':0,'source_end':1.3}})
        self.assertEqual(timeline.view(self.store,self.project['id']),before)
        self.assertEqual(self.store.versions(self.project['id']),old_versions);self.assertEqual(file_sha(path),checksum)

    def test_broll_plan_and_provenance_rebind_with_applied_clips_and_remain_selectable(self):
        self.real_source();asset=self.image();plan=self.create_plan();item=plan['items'][0]
        plan=self.select(plan,item,asset);self.apply(plan,item);before=copy.deepcopy(self.project)
        child=self.store.duplicate(self.project['id'],self.project['revision'])
        new=child['document']['source_broll_plans'][-1]['plan']
        self.assertNotEqual(new['media_plan_id'],plan['media_plan_id']);self.assertEqual(new['project_id'],'prj_'+child['id'])
        evidence=new['media_assets'][-1];self.assertFalse(evidence['production_eligible']);self.assertFalse(evidence['publishing_allowed'])
        clips=[c for t in child['shot_timeline']['snapshot']['tracks'] if t['kind']=='broll' for c in t['clips']]
        self.assertTrue(all(c['metadata']['media_plan_id']==new['media_plan_id'] for c in clips))
        item=new['items'][0]
        applied=source_broll.apply(self.store,self.config,child['id'],child['revision'],{'expected_version':1,
            'media_plan_id':new['media_plan_id'],'expected_plan_version':new['version'],
            'item_ids':[item['media_plan_item_id']],'replace_plan_clips':True})
        self.assertEqual(applied['shot_timeline']['version'],2)
        self.assertEqual(timeline.view(self.store,self.project['id']),before)

    def test_corrupt_active_media_or_evidence_prevents_partial_child(self):
        path=self.real_source();before=self.store.list()
        path.write_bytes(b'Corrupt isolated source fixture')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED_OR_MISSING'):
            self.store.duplicate(self.project['id'],self.project['revision'])
        self.assertEqual(self.store.list(),before)
        doc=copy.deepcopy(self.project['document']);doc['auto_edit_analyses'][0]['sha256']='0'*64
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_ANALYSIS_CHANGED'):
            source_duplicate.rebind(doc,self.project['id'],'e'*32,self.project['revision'],'2026-10-07T00:00:00Z')

    def test_stale_saved_analysis_is_not_promoted_to_fresh_measurement(self):
        self.real_source();doc=copy.deepcopy(self.project['document']);doc['media_analysis']=[]
        target='d'*32
        result=source_duplicate.rebind(doc,self.project['id'],target,self.project['revision'],'2026-10-07T00:00:00Z')
        rebound=result['auto_edit_analyses'][0]
        self.assertFalse(rebound['analysis']['provenance']['identity_rebinding']['source_analysis_was_current'])
        self.assertFalse(rebound['analysis']['provenance']['identity_rebinding']['fresh_provider_measurement'])
        self.assertTrue(analysis.pending(result,target))
        asset=result['assets'][0]
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_ANALYSIS_STALE'):
            analysis.validate_record(rebound,target,result,asset)


if __name__=='__main__':unittest.main()
