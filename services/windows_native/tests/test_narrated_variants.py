"""Atomic family edits and actual child preview/render; explicit synthetic PCM."""
import base64,copy,json,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native.tests import test_narration as fixture
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.narration import apply,load_reference,page
from services.windows_native.narrated_variants import NativeNarratedVariants,catalog
from services.windows_native.narrated_variants_models import Create,Derivation
from services.windows_native.pipeline import Pipeline
from services.windows_native.store import Store

class NarratedVariantsTests(unittest.TestCase):
    setUp=fixture.NarrationTests.setUp;tearDown=fixture.NarrationTests.tearDown
    start=fixture.NarrationTests.start;finish=fixture.NarrationTests.finish;body=fixture.NarrationTests.body;audible=fixture.NarrationTests.audible
    def ready(self,refs=None):
        self.source,self.out,self.result=self.finish();self.project=apply(self.store,self.project['id'],self.source['id'],self.body(self.result))
        self.service=NativeNarratedVariants(self.store)
        return Create(revision=self.project['revision'],expected_version=self.project['shot_timeline']['version'],
            expected_prepared_reference_sha256=digest(self.project['document']['prepared_narration']),profile_refs=refs or ['social-square@1'],request_key='explicit-narrated-variant-key')
    def create(self,payload=None):return self.service.create(self.project['id'],payload or self.ready(),actor='EXPLICIT FIXTURE')[0]
    def child(self,batch,index=0):return self.store.get(batch['result']['variants'][index]['project_id'])
    def resolve(self,child):
        with self.store.transaction() as con:return load_reference(self.store,con,child['id'],child['document'])
    def test_six_formats_preserve_master_canonical_voice_and_start_unapproved_without_jobs(self):
        payload=self.ready([p['profile_ref'] for p in catalog()['profiles']]);before=self.store.get(self.project['id']);batch=self.create(payload)
        self.assertEqual(len(batch['result']['variants']),6);self.assertEqual(self.store.get(self.project['id']),before)
        for descriptor in batch['result']['variants']:
            child=self.store.get(descriptor['project_id']);self.assertIsNone(child['approval']);self.assertEqual(child['jobs'],[])
            frame=child['document']['canonical_timeline']['snapshot'];self.assertEqual((frame['width'],frame['height']),(descriptor['profile']['width'],descriptor['profile']['height']))
            self.assertEqual(self.resolve(child)[0]['id'],self.source['id']);self.assertEqual(child['document']['proposal'],before['document']['proposal'])
        self.assertEqual(len(self.service.page(self.project['id'])['items']),1)
    def test_exact_replay_survives_master_edit_and_conflicting_key_never_creates_more_children(self):
        payload=self.ready();batch=self.create(payload);shot=self.project['shot_timeline']['shots'][0]
        self.store.mutate_shots(self.project['id'],self.project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'on_screen_text':'New visual fixture'}})
        replay,exact=self.service.create(self.project['id'],payload,actor='OTHER FIXTURE');self.assertTrue(exact);self.assertEqual(replay,batch)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.service.create(self.project['id'],payload.model_copy(update={'profile_refs':['youtube-shorts@1']}),actor='EXPLICIT')
        self.assertEqual(self.resolve(self.child(batch))[0]['id'],self.source['id'])
    def test_parallel_same_request_creates_one_family_and_child(self):
        payload=self.ready()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.service.create(self.project['id'],payload,actor='EXPLICIT'),range(2)))
        self.assertEqual(sorted(r[1] for r in results),[False,True]);self.assertEqual(results[0][0],results[1][0]);self.assertEqual(len(self.service.page(self.project['id'])['items']),1)
    def test_nested_family_resolves_original_pcm_without_transferring_intermediate_approval(self):
        batch=self.create(self.ready());child=self.child(batch);state=self.store.shot_view(child['id'])
        body=Create(revision=state['revision'],expected_version=state['shot_timeline']['version'],expected_prepared_reference_sha256=digest(state['document']['prepared_narration']),
            profile_refs=['youtube-landscape@1'],request_key='explicit-nested-narration-family-fixture')
        family,_=self.service.create(child['id'],body,actor='EXPLICIT');grandchild=self.store.get(family['result']['variants'][0]['project_id'])
        self.assertEqual(self.resolve(grandchild)[0]['id'],self.source['id']);self.assertIsNone(grandchild['approval']);self.assertEqual(grandchild['jobs'],[])
        self.assertEqual(grandchild['document']['prepared_narration']['derivation']['master_project_id'],child['id'])
        self.assertEqual(grandchild['document']['prepared_narration']['derivation']['source_project_id'],self.project['id'])
    def test_failed_second_child_rolls_back_entire_family_and_events(self):
        payload=self.ready(['youtube-shorts@1','social-square@1'])
        with self.store.transaction() as con:before={table:con.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ['projects','project_versions','events','native_narrated_variant_batches']}
        from services.windows_native.media_frame_analysis import rebind_records
        calls=[]
        def fail_second(*args):
            calls.append(True)
            if len(calls)==2:raise WorkflowError('EXPLICIT SECOND CHILD FAILURE FIXTURE')
            return rebind_records(*args)
        with patch('services.windows_native.media_frame_analysis.rebind_records',side_effect=fail_second),self.assertRaisesRegex(WorkflowError,'SECOND CHILD FAILURE'):
            self.service.create(self.project['id'],payload,actor='EXPLICIT')
        with self.store.transaction() as con:self.assertEqual(before,{table:con.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in before})
    def test_stale_revision_timeline_reference_unknown_profile_and_strict_input_fail_atomically(self):
        payload=self.ready();before=self.store.get(self.project['id'])
        for changes in [{'revision':payload.revision-1},{'expected_version':99},{'expected_prepared_reference_sha256':'0'*64},{'profile_refs':['unknown@1']}]:
            with self.assertRaises(WorkflowError):self.service.create(self.project['id'],payload.model_copy(update=changes),actor='EXPLICIT')
            self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.service.page(self.project['id'])['items'],[])
        for changes in [{'revision':True},{'expected_version':True},{'profile_refs':[]},{'profile_refs':['social-square@1']*2},{'actor':'forged'},{'publish_enabled':True}]:
            with self.assertRaises(ValidationError):Create.model_validate({**payload.model_dump(),**changes})
    def test_foreign_copy_forged_derivation_numeric_flags_and_voice_change_cannot_borrow_pcm(self):
        payload=self.ready();batch=self.create(payload);child=self.child(batch);other=self.store.create('Unrelated explicit fixture','No providers')
        with self.assertRaisesRegex(WorkflowError,'REFERENCE_INVALID'):
            with self.store.transaction() as con:load_reference(self.store,con,other['id'],child['document'])
        duplicate=self.store.duplicate(child['id'],child['revision']);self.assertNotIn('prepared_narration',duplicate['document'])
        for key,value in [('source_project_id','f'*32),('workspace_id','wsp_foreign'),('approval_inherited',0),('new_inference_calls',False)]:
            document=copy.deepcopy(child['document']);document['prepared_narration']['derivation'][key]=value
            with self.assertRaises(WorkflowError):
                with self.store.transaction() as con:load_reference(self.store,con,child['id'],document)
        shot=self.store.shot_view(child['id'])['shot_timeline']['shots'][0]
        changed=self.store.mutate_shots(child['id'],child['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'narration':'Changed words.'}})
        with self.assertRaisesRegex(WorkflowError,'REFERENCE_INVALID'):self.resolve(changed)
    def test_rehashed_batch_cannot_change_frozen_profile_or_master_history(self):
        payload=self.ready();batch=self.create(payload)
        with self.store.transaction() as con:
            result=copy.deepcopy(batch['result']);result['variants'][0]['profile']['width']=1920
            con.execute('UPDATE native_narrated_variant_batches SET result_json=?,result_sha256=? WHERE batch_id=?',(json.dumps(result),digest(result),batch['batch_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_CHANGED'):self.service.page(self.project['id'])
        with self.assertRaises(WorkflowError):self.resolve(self.child(batch))
    def test_child_rights_authority_clears_and_corrupted_source_audio_blocks_reuse(self):
        payload=self.ready()
        batch=self.create(payload);child=self.child(batch)
        (self.out/'voice.wav').write_bytes(b'EXPLICIT CORRUPTION FIXTURE')
        with self.assertRaisesRegex(WorkflowError,'CHECKPOINT_ARTIFACT_CHANGED'):self.resolve(child)
    def test_valid_project_scoped_rights_wire_fixture_is_not_inherited(self):
        from services.windows_native.tests import test_narration_rights as rights_fixture
        case=rights_fixture.NarrationRightsTests();case.setUp()
        try:
            case.ready();case.grant();master=case.store.shot_view(case.project['id']);service=NativeNarratedVariants(case.store)
            payload=Create(revision=master['revision'],expected_version=master['shot_timeline']['version'],
                expected_prepared_reference_sha256=digest(master['document']['prepared_narration']),profile_refs=['social-square@1'],request_key='explicit-narrated-rights-wire-fixture')
            batch,_=service.create(master['id'],payload,actor='explicit-unit-owner-fixture');child=case.store.get(batch['result']['variants'][0]['project_id'])
            self.assertNotIn('narration_rights_exceptions',child['document']);self.assertFalse(child['document']['narration_rights_exceptions_origin']['authority_transferred'])
            self.assertIsNone(case.service.page(child['id'])['active_exception']);self.assertEqual(case.service.page(child['id'])['provenance']['source_project_id'],master['id'])
        finally:case.tearDown()
    def test_scoped_cursor_and_restart_use_immutable_family_proofs(self):
        payload=self.ready();first=self.create(payload);self.create(payload.model_copy(update={'request_key':'second-narrated-variant-key'}))
        page1=self.service.page(self.project['id'],limit=1);self.assertIsNotNone(page1['next_cursor'])
        page2=self.service.page(self.project['id'],limit=1,cursor=page1['next_cursor']);self.assertIsNone(page2['next_cursor']);self.assertNotEqual(page1['items'][0]['batch_id'],page2['items'][0]['batch_id'])
        other=self.store.create('Other fixture','No provider')
        with self.assertRaisesRegex(WorkflowError,'CURSOR_INVALID'):self.service.page(other['id'],cursor=page1['next_cursor'])
        reopened=NativeNarratedVariants(Store(self.root));self.assertEqual(len(reopened.page(self.project['id'])['items']),2)
        for value in ['invalid',base64.urlsafe_b64encode(json.dumps(['wsp_native_local',self.project['id'],'arbitrary']).encode()).decode()]:
            with self.assertRaises(WorkflowError):reopened.page(self.project['id'],cursor=value)
    def test_square_child_requires_own_audible_preview_and_approval_then_renders_exact_source_pcm(self):
        payload=self.ready();batch=self.create(payload);child=self.child(batch)
        with self.assertRaises(WorkflowError):self.store.approve(child['id'],child['revision'],'EXPLICIT FIXTURE',True)
        preview=self.audible(child);self.assertEqual(preview['audio_mode'],'measured_scene_narration_full_effects_preview')
        child=self.store.approve(child['id'],child['revision'],'EXPLICIT CHILD FIXTURE',True)
        self.store.enqueue(child['id'],child['revision'],'render',uuid.uuid4().hex);job=self.store.claim()
        with patch('services.windows_native.pipeline.verify_runtime'),patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No new inference')):
            rendered=Pipeline(self.config).run(job,lambda _:None)
        self.assertTrue(rendered['qc']['passed']);self.assertEqual(file_sha(self.root/'jobs'/job['id']/'voice.wav'),file_sha(self.out/'voice.wav'))
        receipt=json.loads((self.root/'jobs'/job['id']/'voice-reuse.json').read_bytes());self.assertEqual(receipt['source_project_id'],self.project['id']);self.assertEqual(receipt['target_project_id'],child['id'])
        self.assertEqual(receipt['new_inference_calls'],0);self.assertFalse(receipt['approval_inherited']);self.assertEqual(page(self.store,child['id'])['derived_narration']['source_result']['plan']['project_id'],self.project['id'])
