"""Actual Native counter cohort workflow, explicit synthetic providers/media only."""
import copy,json,unittest
from datetime import timedelta
from unittest.mock import patch
import httpx
from services.windows_native.tests import test_meta_analytics as analytics_fixture
from services.windows_native.tests import test_meta_publish_worker as publisher_fixture
from services.windows_native.official_winners import NativeOfficialWinners
from services.windows_native.official_winner_models import Create
from services.windows_native.official_learning import NativeOfficialLearning
from services.windows_native.official_learning_models import Create as LearningCreate
from services.windows_native.official_accounts import Verify
from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
from services.windows_native.channel_profiles import select
from services.windows_native.contracts import digest,WorkflowError
from app.analytics_channel_policy import WinnerChannelPolicy


class MetaWinnerFixture:
    def __init__(self,platform):
        outer=self;self.counts={'likes':4,'comments':0,'shares':2,'saved':3};self.hook='explicit-list-hook'
        original=publisher_fixture.admission_fixture.render_fixture
        def render(store,**kwargs):
            project=kwargs.pop('project',None) or store.create('EXPLICIT META COUNTER COHORT — NO OWNER UAT','','media',
                channel_profile=select('ai-education-reference@1'))
            project=copy.deepcopy(project);project['document']['analytics_features']={'hook_type':outer.hook}
            return original(store,project=project,**kwargs)
        class Case(analytics_fixture.NativeMetaAnalyticsTests):
            def receive(case,request):
                response=super().receive(request)
                if platform=='instagram_reels' and request.url.path.endswith('/insights'):
                    data=response.json()
                    for row in data['data']:
                        if row['name'] in outer.counts:row['values'][0]['value']=outer.counts[row['name']]
                    return httpx.Response(response.status_code,json=data)
                return response
        self.case=Case('test_scoped_meta_collection_keeps_null_timing_costs_and_protocol_mock_labels');self.case.PLATFORM=platform
        with patch.object(publisher_fixture.admission_fixture,'render_fixture',side_effect=render):self.case.setUp()
        self.c=self.case.c;self.render=render;self.original_publish_handler=self.c.connection.client.wire.transport.handler
        self.case.views=1000;self.first=self.case.run_collection();self.winners=NativeOfficialWinners(self.case.analytics)
        self.anchor=self.first
    def close(self):self.case.tearDown()
    def peer(self,index,*,positive=False):
        c=self.c;c.clock[0]+=timedelta(seconds=1)
        self.hook='explicit-question-hook' if positive else 'explicit-list-hook'
        c.project,c.job=self.render(c.store,final_bytes=('EXPLICIT DISTINCT NONPLAYABLE META COHORT '+str(index)).encode())
        parent,_=c.publications.create(c.project['id'],NativePublicationCreate(revision=c.project['revision'],final_job_id=c.job['id'],
            platform=self.case.PLATFORM,metadata={'title':'EXPLICIT SYNTHETIC COHORT '+str(index),'privacy':'public'},
            request_key='explicit-meta-counter-cohort-parent-'+str(index)),actor=c.principal.token_id)
        c.publications.approve(c.project['id'],parent['publication_id'],NativePublishApproval(expected_fingerprint=parent['request_fingerprint'],
            expected_artifact_sha256=parent['snapshot']['final_sha256'],acknowledged=True),actor=c.principal.token_id)
        c.parent=c.publications.process();c.finish_sent=False;c.mutations=[]
        def publish(request):
            response=self.original_publish_handler(request)
            text=response.text.replace('34567',str(30000+index)).replace('45678',str(40000+index))
            return httpx.Response(response.status_code,json=json.loads(text))
        c.connection.client.wire.transport.handler=publish
        reader=c.accounts.factories[self.case.account.account_ref]
        c.accounts.factories[self.case.account.account_ref]=c.connection
        try:
            c.accounts.create(c.project['id'],self.case.account.account_ref,
                Verify(revision=c.project['revision'],expected_configuration_sha256=c.connection.sha256,
                    acknowledged_read_only=True,request_key='explicit-meta-cohort-account-'+str(index)),actor=c.principal.token_id)
            c.check=c.accounts.process()
            publisher=publisher_fixture.MetaPublishWorkerTests('test_exact_original_video_one_async_job_phase_order_nullable_costs_and_private_history')
            publisher.PLATFORM=self.case.PLATFORM
            with patch.object(publisher_fixture,'fixture',return_value=c):publisher.setUp()
            self.case.completed=publisher.complete()
        finally:c.accounts.factories[self.case.account.account_ref]=reader
        self.case.project=c.project;self.case.remote=self.case.completed['receipt']['remote_post_id']
        self.counts={'likes':40 if positive else 4,'comments':0,'shares':20 if positive else 2,'saved':30 if positive else 3}
        self.anchor=self.case.run_collection(request_key='explicit-meta-counter-cohort-read-'+str(index))
        return self.anchor
    def assessment(self):
        weights={k:0.0 for k in WinnerChannelPolicy().weights};weights.update(engagement=.4,shares=.3,saves=.3)
        policy=WinnerChannelPolicy(minimum_peer_posts=3,minimum_weight_coverage=.5,weights=weights)
        body=Create(sync_id=self.anchor['sync_id'],expected_result_sha256=digest(self.anchor['result']),policy=policy,
            acknowledged_recommendation_only=True,acknowledged_protocol_mock=True,request_key='explicit-meta-counter-winner-key')
        return self.winners.create(self.anchor['project_id'],body,principal=self.c.principal)[0],body


class MetaWinnerTests(unittest.TestCase):
    PLATFORM='instagram_reels'
    def setUp(self):self.f=MetaWinnerFixture(self.PLATFORM)
    def tearDown(self):self.f.close()
    def test_sparse_source_is_insufficient_and_metric_definition_is_frozen(self):
        value,_=self.f.assessment();scope=value['snapshot']['candidate']['scope']
        self.assertEqual(scope['counter_comparison_schema'],'native-meta-counter-comparison-scope-v1')
        self.assertEqual(scope['api_version'],'v24.0');self.assertEqual(len(scope['metric_definition_sha256']),64)
        self.assertEqual(value['assessment']['state'],'insufficient_data');self.assertIsNone(value['assessment']['score'])
        self.assertEqual(value['assessment']['basis'],'matching_native_official_meta_counter_scope')
        self.assertTrue(all(f['evidence']['comparison']=='matching_meta_counter_scope' for f in value['assessment']['factors']))
        self.assertFalse(value['assessment']['channel_baseline_verified']);self.assertFalse(value['assessment']['view_velocity_supported'])
        self.assertIn('Cumulative counters',value['assessment']['limitations'][0])
    def test_distinct_post_cohort_has_explainable_scores_without_invented_watch_time_or_provider_calls(self):
        for i in range(1,4):self.f.peer(i,positive=i==3)
        project=self.f.c.store.get(self.f.anchor['project_id']);wire=self.f.case.calls.copy()
        costs=self.f.case.analytics.costs.summary(self.f.anchor['project_id'])
        value,body=self.f.assessment();a=value['assessment']
        self.assertEqual(value['peer_count'],3);self.assertEqual(len({p['remote_post_id'] for p in value['snapshot']['peers']}),3)
        self.assertEqual(a['state'],'winner_candidate' if self.PLATFORM=='instagram_reels' else 'insufficient_data')
        self.assertEqual(a['score'],100.0 if self.PLATFORM=='instagram_reels' else None)
        for factor in ('view_velocity','retention','completion','ctr','revenue_efficiency'):
            self.assertIsNone(next(v for v in a['factors'] if v['factor']==factor)['score'])
        self.assertIsNone(a['actual_publication_time']);self.assertFalse(value['real_audience_observation'])
        self.assertFalse(value['automatic_action']);self.assertFalse(value['publishing_enabled'])
        replay,hit=self.f.winners.create(value['project_id'],body,principal=self.f.c.principal)
        self.assertTrue(hit);self.assertEqual(replay,value);self.assertEqual(self.f.case.calls,wire)
        self.assertEqual(self.f.case.analytics.costs.summary(value['project_id']),costs)
        self.assertEqual(self.f.c.store.get(value['project_id']),project)
    def test_changed_metric_identity_is_incompatible_and_rehashed_history_cannot_substitute_it(self):
        self.f.peer(1);value,_=self.f.assessment();candidate=value['snapshot']['candidate']
        altered=copy.deepcopy(candidate);altered['remote_post_id']='99999';altered['scope']['api_version']='v25.0'
        self.assertFalse(self.f.winners.compatible(candidate,altered))
        altered['scope']=copy.deepcopy(candidate['scope']);altered['scope']['metric_definition_sha256']='0'*64
        self.assertFalse(self.f.winners.compatible(candidate,altered))
        snapshot=copy.deepcopy(value['snapshot']);snapshot['candidate']['scope']['api_version']='v25.0'
        with self.f.c.store.transaction() as con:
            con.execute('UPDATE native_official_winner_assessments SET snapshot_json=?,snapshot_sha256=? WHERE assessment_id=?',
                (json.dumps(snapshot),digest(snapshot),value['assessment_id']))
        with self.assertRaises(WorkflowError):self.f.winners.get(value['project_id'],value['assessment_id'])
    def test_unverified_genuine_semantics_cannot_be_promoted_by_counter_scores(self):
        # Pure policy input only: no result relabeling or persistence as audience data.
        with self.f.c.store.transaction() as con:candidate=self.f.winners.proof(con,self.f.anchor['project_id'],self.f.anchor['sync_id'])
        candidate=copy.deepcopy(candidate);candidate['scope']['mock']=False
        peers=[{**copy.deepcopy(candidate),'result_snapshot_id':'noam_'+str(i)*32} for i in range(1,4)]
        policy=WinnerChannelPolicy(minimum_peer_posts=3,minimum_weight_coverage=.5)
        outcome=self.f.winners.assessment(candidate,peers,policy,False)
        self.assertEqual(outcome['state'],'insufficient_data');self.assertIsNone(outcome['score'])
        self.assertFalse(outcome['channel_baseline_verified']);self.assertIn('not real-provider verified',outcome['limitations'][-1])
    def test_counter_learning_uses_distinct_post_groups_and_keeps_mock_time_and_missing_watch_time_separate(self):
        rows=[]
        for i in range(1,9):
            self.f.peer(i,positive=i>=6);rows.append(self.f.assessment()[0])
        anchor=rows[-1];learning=NativeOfficialLearning(self.f.winners)
        body=LearningCreate(assessment_id=anchor['assessment_id'],expected_assessment_sha256=anchor['snapshot_sha256'],
            acknowledged_recommendation_only=True,acknowledged_protocol_mock=True,request_key='explicit-meta-counter-learning-key')
        before=self.f.case.calls.copy();value,hit=learning.create(anchor['project_id'],body,principal=self.f.c.principal)
        self.assertFalse(hit);self.assertEqual(value['observation_count'],6 if self.PLATFORM=='instagram_reels' else 0)
        self.assertEqual(value['status'],'recommendations_available' if self.PLATFORM=='instagram_reels' else 'insufficient_data')
        self.assertTrue(value['mock']);self.assertFalse(value['real_audience_observation']);self.assertFalse(value['automatic_action'])
        self.assertEqual(value['snapshot']['scope']['winner_algorithm_version'],'winner-meta-counter-assessment-v1')
        self.assertTrue(all(o['features']['publishing_window'] is None for o in value['snapshot']['observations']))
        self.assertEqual(self.f.case.calls,before);self.assertEqual(learning.get(value['project_id'],value['learning_id']),value)
        from services.windows_native.pipeline import Config
        from services.windows_native.intelligence_service import IntelligenceService
        from services.windows_native.analytics import NativeAnalytics
        from services.windows_native.trend_radar import NativeTrendRadar
        from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
        from services.windows_native.qualified_learning_feedback import NativeQualifiedLearningFeedback,Create as FeedbackCreate,CONSUMERS
        intelligence=IntelligenceService(Config(data_root=self.f.c.root),self.f.c.store,idea_provider=FixtureIdeas())
        legacy=NativeAnalytics(self.f.c.store,self.f.c.publications)
        radar=NativeTrendRadar(intelligence,legacy,workspace=self.f.c.workspace,clock=lambda:self.f.c.clock[0])
        feedback=NativeQualifiedLearningFeedback(learning,radar)
        projected,hit=feedback.create(FeedbackCreate(project_id=value['project_id'],learning_id=value['learning_id'],
            expected_learning_sha256=value['snapshot_sha256'],channel_profile_ref='ai-education-reference@1',platform=self.PLATFORM,
            acknowledged_recommendation_only=True,acknowledged_protocol_mock=True,request_key='explicit-meta-counter-projection-key'),principal=self.f.c.principal)
        self.assertFalse(hit);self.assertEqual(projected['payload']['source_binding']['learning_sha256'],value['snapshot_sha256'])
        self.assertEqual(set(projected['payload']['consumers']),set(CONSUMERS));self.assertFalse(projected['payload']['automatic_application'])
        self.assertEqual(feedback.get(projected['id']),projected);self.assertEqual(self.f.case.calls,before)


class FacebookWinnerTests(MetaWinnerTests):
    PLATFORM='facebook'
