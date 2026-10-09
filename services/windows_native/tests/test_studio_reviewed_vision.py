"""Signed local HTTP/current CPU PNGs; every provider observation is explicit mock."""
import copy,json,unittest
from unittest.mock import patch
from services.windows_native.tests.test_official_vision_http import OfficialVisionHTTPFixture
from services.windows_native.tests.test_workflow import proposal
from services.windows_native.contracts import digest,WorkflowError
from services.windows_native.server import LocalServer,Handler
from services.windows_native.access import NativeAccess
from services.windows_native.tests.test_phase10_http import NoProviderPipeline


class StudioReviewedVisionTests(OfficialVisionHTTPFixture,unittest.TestCase):
    def setUp(self):
        super().setUp()
        asset=self.project['document']['assets'][0]
        draft=proposal('AI technology education')
        for scene in draft['visual_brief']:scene['visual']='EXPLICIT SYNTHETIC FRAME FIXTURE'
        self.project=self.store.save(self.project['id'],self.project['revision'],proposal=draft,
            scene_media=[{'scene':i+1,'asset_id':asset['id']} for i in range(3)])
        self.plan_base='/api/projects/'+self.project['id']+'/media-plans'

    def reviewed(self,row,**changes):
        return {'vision_id':row['vision_id'],'expected_snapshot_sha256':row['snapshot_sha256'],
            'expected_result_sha256':row['result_sha256'],'acknowledged_reviewed_result':True,
            'acknowledged_protocol_mock':True,**changes}

    def body(self,refs):
        current=self.server.store.shot_view(self.project['id'])
        return {'revision':current['revision'],'expected_timeline_version':current['shot_timeline']['version'],'reviewed_vision':refs}

    def complete(self):return self.process_http(self.create_http())

    def plan(self,row):
        status,value,_=self.http('POST',self.plan_base,self.body([self.reviewed(row)]))
        self.assertEqual(status,200,value);return value

    def action(self,record):
        return {'revision':self.store.get(self.project['id'])['revision'],'expected_plan_version':record['plan']['version'],
            'expected_plan_sha256':record['sha256']}

    def test_editor_explicit_plan_reuses_original_mock_without_ranking_dispatch_or_consent_renewal(self):
        row=self.complete();self.account('editor');before=self.store.shot_view(self.project['id'])
        baseline=self.server.media_planner.context
        with self.server.store.transaction() as con:
            context,_=baseline(con,before)
            baseline_candidates=self.server.media_planner.candidates(context,'EXPLICIT SYNTHETIC FRAME FIXTURE')
        value=self.plan(row);record=value['items'][-1];plan=record['plan'];review=plan['input']['reviewed_vision'];item=review['items'][0]
        self.assertEqual(plan['schema_version'],'native-storyboard-media-plan-v2');self.assertTrue(record['input_current'])
        self.assertEqual(plan['algorithm'],'native-storyboard-media-planner-v3');self.assertFalse(plan['semantic_vision_used'])
        self.assertTrue(review['mock_present']);self.assertEqual(item['response_sha256'],row['response']['response_sha256'])
        self.assertEqual(item['cost_operation_id'],row['cost_operation_id']);self.assertEqual(item['original_deadline'],row['snapshot']['deadline'])
        with self.server.store.transaction() as con:
            ranked=self.server.media_planner.candidates(plan['input'],'EXPLICIT SYNTHETIC FRAME FIXTURE')
        self.assertEqual([(v.relevance_score,v.quality_score,v.score_basis) for v in ranked],
            [(v.relevance_score,v.quality_score,v.score_basis) for v in baseline_candidates])
        self.assertTrue(all(v.confidence is None for v in ranked))
        self.assertEqual(before['shot_timeline']['snapshot'],self.store.shot_view(self.project['id'])['shot_timeline']['snapshot'])
        self.assertEqual(len(self.calls),1);self.assertEqual(self.pipeline.calls,0);self.assertEqual(self.official.get(self.project['id'],row['vision_id']),row)
        self.assertEqual(self.plan(row),value)

    def test_revise_recomputes_saved_candidates_then_explicit_apply_uses_canonical_timeline(self):
        row=self.complete();self.account('editor');page=self.plan(row);record=page['items'][-1];item=record['plan']['items'][0]
        status,page,_=self.http('POST',self.plan_base+'/'+record['plan']['media_plan_id']+'/revise',{
            **self.action(record),'shot_id':item['shot_id'],'strategy':'user_asset','query':'unmatched testing query','generation_prompt':'Original educational visual'})
        self.assertEqual(status,200,page);record=page['items'][-1];candidate=record['plan']['items'][0]['candidates'][0]
        self.assertEqual(candidate['relevance_score'],0);self.assertIsNone(record['plan']['items'][0]['selected_asset_id'])
        status,page,_=self.http('POST',self.plan_base+'/'+record['plan']['media_plan_id']+'/select',{
            **self.action(record),'shot_id':item['shot_id'],'asset_id':candidate['asset_id'],'expected_asset_sha256':candidate['sha256']})
        self.assertEqual(status,200,page);record=page['items'][-1];before=self.store.shot_view(self.project['id'])
        status,page,_=self.http('POST',self.plan_base+'/'+record['plan']['media_plan_id']+'/apply',{
            **self.action(record),'shot_ids':[item['shot_id']],'acknowledged':True})
        self.assertEqual(status,200,page);after=self.store.shot_view(self.project['id']);applied=page['items'][-1]
        self.assertEqual(after['shot_timeline']['version'],before['shot_timeline']['version']+1)
        self.assertEqual(applied['plan']['application']['timeline_sha256'],after['document']['canonical_timeline']['sha256'])
        self.assertFalse(applied['input_current']);self.assertIsNone(after['approval']);self.assertEqual(after['jobs'],before['jobs'])
        self.assertEqual(len(self.calls),1);self.assertEqual(self.pipeline.calls,0)

    def test_roles_origin_and_raw_review_hash_foreign_duplicate_guards_precede_mutation(self):
        row=self.complete();body=self.body([self.reviewed(row)]);before=self.store.get(self.project['id'])
        for role in ('viewer','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO FORBIDDEN PLANNER BODY')):
                self.assertEqual(self.http('POST',self.plan_base,body)[0],403)
        self.account('editor')
        for headers in ({'X-VF-CSRF':'wrong'},{'Origin':'https://untrusted.invalid'}):
            self.assertEqual(self.http('POST',self.plan_base,body,headers)[0],403)
        for change in ({'expected_result_sha256':'0'*64},{'expected_snapshot_sha256':'0'*64},{'acknowledged_protocol_mock':False},
            {'acknowledged_reviewed_result':1},{'acknowledged_reviewed_result':'true'},{'acknowledged_protocol_mock':1},{'result':{}}):
            self.assertIn(self.http('POST',self.plan_base,self.body([self.reviewed(row,**change)]))[0],(400,409))
        self.assertEqual(self.http('POST',self.plan_base,self.body([self.reviewed(row),self.reviewed(row)]))[0],400)
        other=self.store.create('Other project','No provider');foreign={**body,'revision':other['revision'],'expected_timeline_version':0}
        # Scope is refused even if the other project has a compatible storyboard.
        other=self.store.save(other['id'],other['revision'],proposal=proposal())
        foreign['revision']=other['revision']
        self.assertIn(self.http('POST','/api/projects/'+other['id']+'/media-plans',foreign)[0],(400,404,409))
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(len(self.calls),1)

    def test_pending_result_cannot_be_used_as_reviewed_evidence(self):
        row=self.create_http();before=self.store.get(self.project['id'])
        ref=self.reviewed(row,expected_result_sha256='0'*64)
        self.assertEqual(self.http('POST',self.plan_base,self.body([ref]))[0],409)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.calls,[])

    def test_changed_actual_source_blocks_reuse_and_apply_but_exact_history_remains(self):
        row=self.complete();page=self.plan(row);record=page['items'][-1];before=self.store.get(self.project['id'])
        source=self.root/'assets'/row['snapshot']['source']['asset']['id'];source.write_bytes(source.read_bytes()+b'changed owned fixture')
        status,history,_=self.http('GET',self.plan_base);self.assertEqual(status,200,history)
        self.assertEqual(history['items'][-1]['plan'],record['plan']);self.assertFalse(history['items'][-1]['input_current'])
        self.assertEqual(self.http('POST',self.plan_base,self.body([self.reviewed(row)]))[0],409)
        self.assertEqual(self.http('POST',self.plan_base+'/'+record['plan']['media_plan_id']+'/apply',{
            **self.action(record),'shot_ids':[record['plan']['items'][0]['shot_id']],'acknowledged':True})[0],409)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(len(self.calls),1)

    def test_rehashed_mock_projection_and_candidate_promotion_are_rejected(self):
        row=self.complete();page=self.plan(row);original=self.store.get(self.project['id'])['document']
        for mutate in (lambda p:p['input']['reviewed_vision']['items'][0].update(mock=False,semantic_inference_performed=True),
            lambda p:p['input']['reviewed_vision']['items'][0]['frames'][0].update(confidence=.99),
            lambda p:p['items'][0]['candidates'][0].update(score_basis='reviewed_provider_labels_and_uncalibrated_predicted_sample_quality'),
            lambda p:p['items'][0]['candidates'][0]['provenance']['reviewed_vision'].update(mock=False),
            lambda p:p['items'][0]['candidates'][0].update(selectable=1),lambda p:p.update(publishing_enabled=0)):
            doc=copy.deepcopy(original);record=doc['studio_media_plans'][-1];plan=record['plan'];mutate(plan)
            plan['input_sha256']=digest(plan['input']);plan['fingerprint']=digest({'algorithm':plan['algorithm'],'input_sha256':plan['input_sha256'],'options':plan['options']});record['sha256']=digest(plan)
            with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),self.project['id']))
            with self.assertRaises(WorkflowError):self.server.media_planner.page(self.project['id'])
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(original),self.project['id']))
        self.assertEqual(self.server.media_planner.page(self.project['id']),page);self.assertEqual(len(self.calls),1)

    def test_keyless_disabled_fresh_server_reads_original_plan_without_renewing_provider_permission(self):
        row=self.complete();page=self.plan(row);identity=NativeAccess(self.verifier,self.workspace)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO HISTORY KEY ACCESS')):
            server=LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=identity)
            try:
                self.assertEqual(server.media_planner.page(self.project['id']),page)
                self.assertFalse(server.official_vision.states()['enabled']);self.assertFalse(server.runner.run_one())
            finally:server.server_close()
        self.assertEqual(len(self.calls),1);self.assertEqual(self.official.get(self.project['id'],row['vision_id']),row)

    def test_v3_resolution_keeps_existing_unconfigured_path_without_mock_fallback_or_vision_dispatch(self):
        row=self.complete();page=self.plan(row);record=page['items'][-1];shot=record['plan']['items'][0]['shot_id']
        status,page,_=self.http('POST',self.plan_base+'/'+record['plan']['media_plan_id']+'/revise',{
            **self.action(record),'shot_id':shot,'strategy':'ai_image','query':'Original technology visual','generation_prompt':'Original education image'})
        self.assertEqual(status,200,page);record=page['items'][-1];before=self.store.get(self.project['id'])
        route=self.plan_base+'/'+record['plan']['media_plan_id']+'/resolve/generate'
        body={**self.action(record),'shot_id':shot,'fixture_acknowledged':False,'request_key':'reviewed-vision-unconfigured-generation','seed':31}
        status,error,_=self.http('POST',route,body)
        self.assertEqual(status,400);self.assertEqual(error['code'],'NATIVE_GENERATION_SOURCE_ACK_REQUIRED')
        status,value,_=self.http('POST',route,{**body,'external_acknowledged':True})
        self.assertEqual(status,200,value);self.assertEqual(value['child']['status'],'not_configured')
        self.assertEqual(value['binding']['plan_sha256'],record['sha256']);self.assertEqual(self.store.get(self.project['id'])['document'],before['document'])
        self.assertEqual(len(self.calls),1);self.assertEqual(self.pipeline.calls,0)
