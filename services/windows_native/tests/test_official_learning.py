"""Descriptive synthetic protocol cohorts; no real audience or Owner acceptance."""
import copy,json,subprocess,sys,unittest
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native.tests.test_official_winners import OfficialWinnerFixture
from services.windows_native.tests.test_publications import render_fixture
from services.windows_native.channel_profiles import select
from services.windows_native.official_winner_models import Create as WinnerCreate
from services.windows_native.official_learning import NativeOfficialLearning,TABLES
from services.windows_native.official_learning_models import Create
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.backup import database_status

class OfficialLearningFixture(OfficialWinnerFixture):
    def configured_render(self,store,**kwargs):
        project=kwargs.pop('project',None) or store.create('EXPLICIT SYNTHETIC LEARNING COHORT','','media',channel_profile=select(self.reference))
        project=copy.deepcopy(project);project['document']['analytics_features']={'hook_type':getattr(self,'next_hook',None)}
        return render_fixture(store,project=project,**kwargs)
    def setUp(self):
        self.next_hook=None;super().setUp();self.learning=NativeOfficialLearning(self.winners);self.anchor_assessment=self.assess()
    def cohort_learning(self):
        observations=[]
        for i in range(2,8):
            self.next_hook='explicit-question-hook' if i<5 else 'explicit-list-hook';value=self.peer(i)
            if i<5:
                self.metric_values=[1000,40,2.4,50,4,10,10];value=self.run_collection(request_key='explicit-positive-learning-read-'+str(i))
            observations.append(value)
        assessments=[]
        for i,observation in enumerate(observations):
            body=WinnerCreate(sync_id=observation['sync_id'],expected_result_sha256=digest(observation['result']),acknowledged_recommendation_only=True,
                acknowledged_protocol_mock=True,request_key='explicit-learning-source-assessment-'+str(i))
            assessments.append(self.winners.create(observation['project_id'],body,principal=self.principal)[0])
        self.anchor_assessment=assessments[0];self.learning_project=self.anchor_assessment['project_id'];self.learning_sources=assessments;return assessments
    def learning_body(self,**changes):
        return Create.model_validate({'assessment_id':self.anchor_assessment['assessment_id'],'expected_assessment_sha256':self.anchor_assessment['snapshot_sha256'],
            'acknowledged_recommendation_only':True,'acknowledged_protocol_mock':True,'request_key':'explicit-native-learning-snapshot-key',**changes})
    def learn(self,**changes):return self.learning.create(self.anchor_assessment['project_id'],self.learning_body(**changes),principal=self.principal)[0]

class OfficialLearningTests(OfficialLearningFixture,unittest.TestCase):
    def test_sparse_snapshot_remains_insufficient_and_runs_no_provider_cost_media_operation(self):
        wire=self.read_wire.copy();project=self.store.get(self.anchor_project);costs=self.analytics.costs.summary(self.anchor_project)
        value=self.learn();self.assertEqual(value['status'],'insufficient_data');self.assertEqual(value['observation_count'],0)
        self.assertTrue(all(d['state']=='insufficient_data' for d in value['dimensions']));self.assertTrue(value['mock']);self.assertFalse(value['real_audience_observation'])
        self.assertFalse(value['automatic_action']);self.assertEqual(wire,self.read_wire);self.assertEqual(project,self.store.get(self.anchor_project));self.assertEqual(costs,self.analytics.costs.summary(self.anchor_project))
        self.assertEqual(self.learning.get(self.anchor_project,value['learning_id']),value)
    def test_six_distinct_qualified_mock_posts_generate_only_descriptive_hook_association(self):
        self.cohort_learning();wire=self.read_wire.copy();value=self.learn();self.assertEqual(value['observation_count'],6);self.assertEqual(value['status'],'recommendations_available')
        groups=next(d for d in value['dimensions'] if d['dimension']=='hook')['groups'];positive=next(g for g in groups if g['value']=='explicit-question-hook')
        self.assertEqual(positive['sample_count'],3);self.assertEqual(positive['control_count'],3);self.assertEqual(positive['state'],'recommendation_candidate');self.assertGreater(positive['score_difference'],10)
        self.assertEqual(len({o['remote_post_sha256'] for o in value['snapshot']['observations']}),6);self.assertTrue(value['mock']);self.assertFalse(value['real_audience_observation'])
        self.assertTrue(all(o['features']['publishing_window'] is None for o in value['snapshot']['observations']));self.assertEqual(wire,self.read_wire)
        unsupported=copy.deepcopy(self.anchor_assessment);unsupported['snapshot']['candidate']['features']['hook_type']='X'*1001
        self.assertIsNone(self.learning.observation(unsupported))
    def test_exact_concurrent_key_replay_and_policy_conflict_do_not_duplicate(self):
        def run(_):return self.learning.create(self.anchor_project,self.learning_body(),principal=self.principal)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(len({r[0]['learning_id'] for r in results}),1);self.assertEqual(sum(r[1] for r in results),1)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):self.learn(policy={'minimum_score_difference':20})
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[0]).fetchone()[0],1);self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[1]).fetchone()[0],1)
    def test_later_insufficient_post_does_not_revive_older_score_or_change_original_learning(self):
        self.cohort_learning();original=self.learn();target=self.learning_sources[1];candidate=target['snapshot']['candidate']
        self.project=self.store.get(target['project_id']);self.job=self.store.get_job(candidate['features']['evidence']['render_job_id']);self.completed=self.service.get(target['project_id'],target['publication_id'])
        self.rows=False;observation=self.run_collection(request_key='explicit-later-insufficient-learning-read')
        body=WinnerCreate(sync_id=observation['sync_id'],expected_result_sha256=digest(observation['result']),acknowledged_recommendation_only=True,acknowledged_protocol_mock=True,request_key='explicit-later-insufficient-learning-assessment')
        newest=self.winners.create(target['project_id'],body,principal=self.principal)[0];self.assertEqual(newest['assessment']['state'],'insufficient_data')
        current=self.learn(request_key='explicit-learning-after-insufficient-source');self.assertEqual(current['observation_count'],5)
        self.assertFalse(any(d['state']=='recommendations_available' for d in current['dimensions']));self.assertGreaterEqual(current['snapshot']['excluded_rows']['duplicate_remote_post'],1)
        self.assertEqual(self.learning.get(original['project_id'],original['learning_id']),original)
    def test_duplicate_assessments_policy_or_mock_report_scope_do_not_inflate_or_mix_evidence(self):
        self.cohort_learning();anchor=self.anchor_assessment;candidate=anchor['snapshot']['candidate']
        duplicate=WinnerCreate(sync_id=anchor['sync_id'],expected_result_sha256=candidate['result_sha256'],acknowledged_recommendation_only=True,acknowledged_protocol_mock=True,request_key='explicit-duplicate-same-learning-post')
        self.winners.create(anchor['project_id'],duplicate,principal=self.principal);value=self.learn();self.assertEqual(value['observation_count'],6);self.assertGreaterEqual(value['snapshot']['excluded_rows']['duplicate_remote_post'],1)
        for field,change in [('mock',False),('source_kind','official_provider'),('query',{'start_date':'2026-09-01','end_date':'2026-10-07','include_revenue':False}),('target_binding_sha256','f'*64),('niche','real_estate')]:
            foreign=copy.deepcopy(anchor);foreign['snapshot']['candidate']['scope'][field]=change;self.assertFalse(self.learning.compatible(anchor,foreign))
        different=duplicate.model_copy(update={'policy':duplicate.policy.model_copy(update={'minimum_views':600}),'request_key':'explicit-different-winner-policy-learning-source'})
        self.winners.create(anchor['project_id'],different,principal=self.principal)
        current=self.learn(request_key='explicit-learning-after-different-policy');self.assertEqual(current['observation_count'],6);self.assertGreaterEqual(current['snapshot']['excluded_rows']['incompatible_policy'],1)
    def test_selected_frozen_observation_or_assessment_reference_mutations_fail_closed(self):
        self.cohort_learning();value=self.learn();identity=value['learning_id'];project=value['project_id']
        with self.store.transaction() as con:original=tuple(con.execute('SELECT snapshot_json,snapshot_sha256 FROM '+TABLES[0]+' WHERE learning_id=?',(identity,)).fetchone())
        for mutate in (lambda s:s['selected_assessments'][0].update(snapshot_sha256='f'*64),lambda s:s['observations'][0]['features'].update(hook='fabricated-hook'),
            lambda s:s['selected_assessments'][0]['observation'].update(score=0),lambda s:s['selected_assessments'].append(s['selected_assessments'][0])):
            changed=json.loads(original[0]);mutate(changed)
            with self.store.transaction() as con:con.execute('UPDATE '+TABLES[0]+' SET snapshot_json=?,snapshot_sha256=? WHERE learning_id=?',(json.dumps(changed),digest(changed),identity))
            with self.assertRaises(WorkflowError):self.learning.get(project,identity)
        with self.store.transaction() as con:con.execute('UPDATE '+TABLES[0]+' SET snapshot_json=?,snapshot_sha256=? WHERE learning_id=?',(*original,identity))
        self.assertEqual(self.learning.get(project,identity),value)
    def test_strict_model_mock_expected_assessment_and_future_observation_fail_closed(self):
        for change in ({'acknowledged_recommendation_only':1},{'acknowledged_protocol_mock':1},{'policy':{'minimum_group_posts':True}},{'policy':{'maximum_posts':5}},{'automatic_action':True},{'token':'NEVER'}):
            with self.assertRaises(ValidationError):self.learning_body(**change)
        with self.assertRaisesRegex(WorkflowError,'MOCK_ACK_REQUIRED'):self.learn(acknowledged_protocol_mock=False)
        with self.assertRaisesRegex(WorkflowError,'ASSESSMENT_CHANGED'):self.learn(expected_assessment_sha256='f'*64)
        self.clock[0]-=timedelta(seconds=1)
        with self.assertRaisesRegex(WorkflowError,'FUTURE_OBSERVATION'):self.learn()
    def test_owner_recheck_after_selection_rolls_back_without_provider_dispatch(self):
        original=self.learning.selection;wire=self.read_wire.copy()
        def revoke(*args):
            result=original(*args);object.__setattr__(self.verifier.registry.tokens[self.principal.token_id],'enabled',False);return result
        with patch.object(self.learning,'selection',side_effect=revoke),self.assertRaisesRegex(WorkflowError,'OWNER_REQUIRED'):self.learn()
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM '+TABLES[0]).fetchone()[0],0)
        self.assertEqual(wire,self.read_wire)
    def test_history_after_edit_archive_expiry_and_provider_removal_reuses_original_frozen_sources(self):
        value=self.learn();wire=self.read_wire.copy()
        self.store.archive(self.anchor_project,self.store.get(self.anchor_project)['revision'],True);self.accounts.factories.clear();self.service.factories.clear();self.clock[0]+=timedelta(days=2)
        self.assertEqual(NativeOfficialLearning(self.winners).get(self.anchor_project,value['learning_id']),value);self.assertEqual(wire,self.read_wire)
        with self.assertRaises(WorkflowError):self.learn(request_key='explicit-expired-owner-new-learning-key')
    def test_rehashed_dimension_scope_anchor_or_qualification_mutations_are_rejected(self):
        value=self.learn();identity=value['learning_id']
        with self.store.transaction() as con:original=tuple(con.execute('SELECT snapshot_json,snapshot_sha256 FROM '+TABLES[0]+' WHERE learning_id=?',(identity,)).fetchone())
        for mutate in (lambda s:s['dimensions'][0].update(state='recommendations_available'),lambda s:s['scope'].update(mock=False),
            lambda s:s.update(anchor_candidate_sha256='f'*64),lambda s:s.update(automatic_action=True),lambda s:s.update(winner_factor_basis_sha256='f'*64)):
            changed=json.loads(original[0]);mutate(changed)
            with self.store.transaction() as con:con.execute('UPDATE '+TABLES[0]+' SET snapshot_json=?,snapshot_sha256=? WHERE learning_id=?',(json.dumps(changed),digest(changed),identity))
            with self.assertRaises(WorkflowError):self.learning.get(self.anchor_project,identity)
        with self.store.transaction() as con:con.execute('UPDATE '+TABLES[0]+' SET snapshot_json=?,snapshot_sha256=? WHERE learning_id=?',(*original,identity))
        self.assertEqual(self.learning.get(self.anchor_project,identity),value)
        with self.store.transaction() as con:con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        with self.assertRaises(WorkflowError):self.learning.get(self.anchor_project,identity)
    def test_scoped_bounded_pages_and_backup_journals_have_no_active_learning_work(self):
        for i in range(3):self.learn(request_key='explicit-learning-page-key-'+str(i))
        first=self.learning.page(self.anchor_project,limit=2,publication=self.anchor_publication['publication_id']);self.assertTrue(first['truncated']);self.assertEqual(len(first['items']),2)
        self.assertEqual(len(self.learning.page(self.anchor_project,limit=2,publication=self.anchor_publication['publication_id'],cursor=first['next_cursor'])['items']),1)
        other=self.store.create('Other learning fixture','','media')
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):self.learning.get(other['id'],first['items'][0]['learning_id'])
        for kw in ({'limit':True},{'limit':0},{'limit':101},{'cursor':'[]'},{'cursor':first['next_cursor']}):
            with self.assertRaisesRegex(WorkflowError,'PAGE_INVALID'):self.learning.page(self.anchor_project,**kw)
        status=database_status(self.store.db);self.assertEqual(status['counts'][TABLES[0]],3);self.assertEqual(status['counts'][TABLES[1]],3);self.assertEqual(status['active_operations'],0)
    def test_cold_import_needs_no_orm_or_provider_sdk_and_runtime_rebinding_is_refused(self):
        code="import sys;from services.windows_native.official_learning import NativeOfficialLearning;from app.learning_models import LearningPolicy;assert 'sqlalchemy' not in sys.modules;assert LearningPolicy().minimum_group_posts==3;print('PURE_NATIVE_LEARNING_IMPORT_PASS')"
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);self.assertIn('PURE_NATIVE_LEARNING_IMPORT_PASS',result.stdout)
        self.learning.workspace='wsp_foreign'
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_CHANGED'):self.learn()

if __name__=='__main__':unittest.main()
