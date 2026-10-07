"""Real local synthetic footage + saved ASR fixtures; no provider or Owner acceptance."""
import copy,json
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.source_variants import SourceVariants,Create,catalog
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native import source_linked_edit
from services.windows_native.tests import test_source_broll as fixture

class SourceVariantTests(unittest.TestCase):
    setUp=fixture.SourceBrollTests.setUp
    tearDown=fixture.SourceBrollTests.tearDown
    real_source=fixture.SourceBrollTests.real_source
    save_analysis=fixture.SourceBrollTests.save_analysis
    image=fixture.SourceBrollTests.image
    create_plan=fixture.SourceBrollTests.create_plan
    select=fixture.SourceBrollTests.select
    apply=fixture.SourceBrollTests.apply

    def payload(self,**values):
        return Create.model_validate({'revision':self.project['revision'],'expected_version':self.project['shot_timeline']['version'],
            'profile_refs':[item['profile_ref'] for item in catalog()['profiles']],'request_key':'source-variant-explicit-fixture-key',**values})

    def create(self,**values):
        service=SourceVariants(self.store);return service,service.create(self.project['id'],self.payload(**values),actor='fixture-editor')

    def database(self):
        with self.store.transaction() as con:return {table:[tuple(row) for row in con.execute('SELECT * FROM '+table+' ORDER BY rowid')] for table in ['projects','project_versions','events','native_source_variant_batches']}

    def test_six_profiles_reuse_source_transcript_and_audio_decisions_without_master_or_approval_mutation(self):
        path=self.real_source();before=self.store.get(self.project['id']);versions=self.store.versions(self.project['id']);source_sha=file_sha(path)
        service,(batch,replay)=self.create();self.assertFalse(replay);self.assertEqual(len(batch['result']['variants']),6)
        for item in batch['result']['variants']:
            child=timeline.view(self.store,item['project_id']);snapshot=child['shot_timeline']['snapshot'];profile=item['profile']
            self.assertEqual((snapshot['width'],snapshot['height'],snapshot['aspect_ratio']),(profile['width'],profile['height'],profile['aspect_ratio']))
            self.assertIsNone(child['approval']);self.assertEqual(child['jobs'],[]);self.assertEqual(child['document']['assets'],before['document']['assets'])
            self.assertEqual(child['document']['auto_edit_analyses'][0]['analysis']['transcript']['segments'][0]['text'],'Xin chào.')
            for track in snapshot['tracks']:
                for clip in track['clips']:
                    if track['type']=='video' and not track['disabled'] and not clip['disabled']:
                        self.assertEqual(clip['metadata']['reframe']['aspect_ratio'],profile['aspect_ratio']);self.assertTrue(clip['metadata']['reframe']['needs_attention'])
            self.assertEqual(snapshot['metadata']['source_variant']['master_document_sha256'],digest(before['document']))
            with self.assertRaisesRegex(WorkflowError,'HUMAN_APPROVAL'):self.store.enqueue(child['id'],child['revision'],'render','fixture-no-approval-'+child['id'])
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.store.versions(self.project['id']),versions);self.assertEqual(file_sha(path),source_sha)
        self.assertEqual(SourceVariants(self.store).page(self.project['id'])['items'][0],batch)

    def test_concurrent_replay_and_later_master_edit_preserve_original_batch(self):
        self.real_source();service=SourceVariants(self.store);payload=self.payload()
        with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(lambda _:service.create(self.project['id'],payload,actor='fixture-editor'),range(2)))
        self.assertEqual(sum(not replay for _,replay in values),1);before=values[0][0]
        source=self.project['shot_timeline']['snapshot'];clip=next(track for track in source['tracks'] if track['kind']=='source')['clips'][0]
        self.project=source_linked_edit.edit(self.store,self.project['id'],self.project['revision'],{'expected_version':self.project['shot_timeline']['version'],
            'operation':{'type':'trim','clip_id':clip['clip_id'],'source_start':0,'source_end':1.3}})
        replayed,replay=service.create(self.project['id'],payload,actor='fixture-editor');self.assertTrue(replay);self.assertEqual(replayed,before)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):service.create(self.project['id'],self.payload(),actor='fixture-editor')

    def test_bad_source_leaves_no_partial_drafts(self):
        path=self.real_source();service=SourceVariants(self.store);before=self.database();path.write_bytes(b'EXPLICIT CORRUPTION')
        with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED'):service.create(self.project['id'],self.payload(),actor='fixture-editor')
        self.assertEqual(self.database(),before)

    def test_locked_visual_track_is_not_silently_unlocked_for_variant_derivation(self):
        self.real_source();document=copy.deepcopy(self.project['document']);snapshot=document['canonical_timeline']['snapshot']
        next(track for track in snapshot['tracks'] if track['kind']=='source')['locked']=True;document['canonical_timeline']['sha256']=digest(snapshot)
        with self.store.transaction() as con:
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document),self.project['id']));self.store.version(con,self.project['id'])
        self.project=timeline.view(self.store,self.project['id']);service=SourceVariants(self.store);before=self.database()
        with self.assertRaisesRegex(WorkflowError,'UNLOCK_VISUAL_TRACK'):service.create(self.project['id'],self.payload(),actor='fixture-editor')
        self.assertEqual(self.database(),before)

    def test_missing_or_corrupt_initial_child_history_rejects_rehashed_batch_membership(self):
        self.real_source();service,(batch,_)=self.create();identifier=batch['result']['variants'][0]['project_id']
        with self.store.transaction() as con:con.execute("UPDATE project_versions SET document='{}' WHERE project_id=? AND revision=1",(identifier,))
        with self.assertRaisesRegex(WorkflowError,'CHILD_HISTORY_CHANGED'):service.page(self.project['id'])

    def test_completion_event_failure_rolls_back_all_six_children_and_history(self):
        self.real_source();service=SourceVariants(self.store);before=self.database();original=self.store.event
        def fail(con,project,action,payload):
            if action=='source_variant_batch_created_unapproved':raise RuntimeError('EXPLICIT ATOMIC COMMIT FAILURE')
            return original(con,project,action,payload)
        with patch.object(self.store,'event',fail),self.assertRaises(RuntimeError):service.create(self.project['id'],self.payload(),actor='fixture-editor')
        self.assertEqual(self.database(),before)

    def test_broll_geometry_rebinds_and_generic_duplicate_cannot_impersonate_variant_membership(self):
        self.real_source();asset=self.image();plan=self.create_plan();item=plan['items'][0];plan=self.select(plan,item,asset);self.apply(plan,item)
        service,(batch,_)=self.create();child=timeline.view(self.store,batch['result']['variants'][0]['project_id'])
        visual=[clip for track in child['shot_timeline']['snapshot']['tracks'] if track['type']=='video' for clip in track['clips'] if not clip['disabled']]
        self.assertGreater(len(visual),1);self.assertTrue(all(clip['metadata']['reframe']['aspect_ratio']=='16:9' for clip in visual))
        duplicate=self.store.duplicate(child['id'],child['revision']);self.assertNotIn('source_variant',duplicate['shot_timeline']['snapshot']['metadata'])
        self.assertEqual(len(service.page(self.project['id'])['items']),1)

    def test_scope_cursor_rehashed_profile_and_strict_requests_fail_closed(self):
        self.real_source();service,(first,_)=self.create(request_key='source-variant-page-fixture-one')
        self.create(request_key='source-variant-page-fixture-two',profile_refs=['youtube-shorts@1']);page=service.page(self.project['id'],limit=1)
        self.assertEqual(len(service.page(self.project['id'],limit=1,cursor=page['next_cursor'])['items']),1)
        other=SourceVariants(self.store,workspace_id='wsp_other_fixture');self.assertEqual(other.page(self.project['id'])['items'],[])
        with self.assertRaisesRegex(WorkflowError,'CURSOR_INVALID'):other.page(self.project['id'],cursor=page['next_cursor'])
        result=copy.deepcopy(first['result']);result['variants'][0]['profile']['platform']='facebook'
        with self.store.transaction() as con:con.execute('UPDATE native_source_variant_batches SET result_json=?,result_sha256=? WHERE batch_id=?',(json.dumps(result),digest(result),first['batch_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):service.page(self.project['id'])
        for values in [{'revision':True},{'expected_version':True},{'profile_refs':[]},{'profile_refs':['youtube-shorts@1']*2},{'publish_enabled':True},{'crop_policy':'automatic_tracking'}]:
            with self.subTest(fields=list(values)),self.assertRaises(ValidationError):self.payload(**values)
        with self.assertRaisesRegex(WorkflowError,'PROFILE_UNKNOWN'):self.create(request_key='source-variant-unknown-fixture',profile_refs=['not-configured@1'])


if __name__=='__main__':unittest.main()
