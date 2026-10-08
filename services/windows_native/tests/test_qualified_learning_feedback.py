"""Synthetic qualified source projection checks; no real account/media acceptance."""
import copy, json, unittest, uuid, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from pydantic import ValidationError
from services.windows_native.tests.test_official_learning import OfficialLearningFixture
from services.windows_native.tests.test_trend_radar import FixtureProvider
from services.windows_native.tests.test_publications import render_fixture
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
from services.windows_native.pipeline import Config
from services.windows_native.analytics import NativeAnalytics
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.trend_radar import NativeTrendRadar
from services.windows_native.trend_radar_models import CollectRequest, RefreshRequest,HandoffRequest
from app.trend_providers import TrendProviderRegistry
from app.subtitle_templates import template_catalog
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.hardening import Artifacts
from services.windows_native.store import now

from services.windows_native import qualified_learning_feedback as module
Create, NativeQualifiedLearningFeedback = module.Create, module.NativeQualifiedLearningFeedback

def render_feature_fixture(store, *, project, subtitle_ref, final_bytes=None):
    """Seed annotations before the explicit mock render/request/artifact are frozen."""
    identifier = uuid.uuid4().hex
    asset = {'id':'explicit_fixture.mp4','kind':'video','filename':'EXPLICIT OWNED RIGHTS FIXTURE',
             'rights_confirmed':True,'rights_status':'owned','license':'explicit-owned-fixture-license'}
    document = {**project['document'], 'assets':[asset], 'canonical_timeline': {'snapshot': {
        'metadata': {'native_auto_edit_schema':'native-auto-edit-timeline-v1','subtitle_template_ref':subtitle_ref},
        'tracks':[{'disabled':False,'clips':[{'disabled':False,'asset_id':'ast_explicit_fixture','metadata':{'native_asset_id':asset['id']}}]}]}}}
    revision = project['revision']+1
    approval = {'revision':revision,'reviewer':'EXPLICIT SYNTHETIC REVIEW — NOT OWNER UAT','acknowledged':True}
    snapshot = {'document':document,'approval':approval}; stamp = now()
    with store.transaction() as con:
        con.execute('UPDATE projects SET revision=?,document=?,approval=? WHERE id=?',(revision,json.dumps(document),json.dumps(approval),project['id']))
        store.version(con,project['id'])
        con.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(identifier,project['id'],revision,'render','running',
                    'explicit_fixture',uuid.uuid4().hex,digest(snapshot),json.dumps(snapshot),None,None,stamp,stamp))
    job = store.get_job(identifier); directory = store.root/'jobs'/identifier; directory.mkdir(parents=True)
    final = directory/'final.mp4'; final.write_bytes(final_bytes if final_bytes is not None else b'EXPLICIT NONPLAYABLE QUALIFIED PLANNING FIXTURE; NO FULL QC')
    result = {'qc':{'passed':True,'width':1080,'height':1920,'duration_seconds':3,'video_codec':'h264','audio_codec':'aac',
             'final_sha256':file_sha(final),'fixture':True,'full_media_qc':False},'review_required':True,'output_directory':str(directory),'provider_calls':0}
    Artifacts(directory,job).commit('render',[final],result); store.finish(job,result=result)
    store.review_render(identifier,revision,'EXPLICIT SYNTHETIC FINAL REVIEW — NOT OWNER UAT',True,'approve')
    return store.get(project['id']),store.get_job(identifier)

class FeedbackFixture(OfficialLearningFixture):
    def configured_render(self, store, **kwargs):
        project = kwargs.pop('project', None) or store.create('EXPLICIT QUALIFIED PLANNING FIXTURE', '', 'media', channel_profile=__import__('services.windows_native.channel_profiles', fromlist=['select']).select(self.reference))
        project = copy.deepcopy(project); positive = getattr(self, 'next_hook', None) == 'explicit-question-hook'
        project['document']['analytics_features'] = {'hook_type': getattr(self, 'next_hook', None),
            'trend_cluster_id': getattr(self,'positive_family','explicit-positive-family') if positive else 'explicit-control-family',
            'visual_strategy': 'explicit-positive-visual' if positive else 'explicit-control-visual',
            'voice_profile': 'explicit-positive-voice' if positive else 'explicit-control-voice'}
        # These are explicit synthetic canonical feature annotations, not observed speech/style quality.
        return render_feature_fixture(store, project=project, subtitle_ref=template_catalog()['templates'][0 if positive else 1]['template_ref'], **kwargs)

    def setUp(self):
        super().setUp(); self.config = Config(data_root=self.root)
        self.intelligence = IntelligenceService(self.config, self.store, idea_provider=FixtureIdeas())
        self.legacy = NativeAnalytics(self.store, self.publications)
        self.radar = NativeTrendRadar(self.intelligence, self.legacy, workspace=self.workspace,
            providers=TrendProviderRegistry([FixtureProvider(self.clock[0])]), clock=lambda: self.clock[0])
        self.feedback = NativeQualifiedLearningFeedback(self.learning, self.radar)
        self.radar.qualified_learning=self.feedback;self.intelligence.qualified_learning=self.feedback;self.store.qualified_learning=self.feedback
        self.saved = self.learn()

    def tearDown(self):
        if hasattr(self, 'radar'): self.radar.close()
        super().tearDown()

    def feedback_body(self, **changes):
        return Create.model_validate({'project_id': self.saved['project_id'], 'learning_id': self.saved['learning_id'],
            'expected_learning_sha256': self.saved['snapshot_sha256'], 'channel_profile_ref': 'ai-education-reference@1',
            'acknowledged_recommendation_only': True, 'acknowledged_protocol_mock': True,
            'request_key': 'explicit-qualified-feedback-projection-key', **changes})

    def project_feedback(self, **changes):
        return self.feedback.create(self.feedback_body(**changes), principal=self.principal)

class QualifiedFeedbackTests(FeedbackFixture, unittest.TestCase):
    def test_sparse_projection_is_source_bound_insufficient_without_wire_cost_media_or_approval(self):
        before = self.store.get(self.saved['project_id']); wire = self.read_wire.copy(); costs = self.analytics.costs.summary(self.saved['project_id'])
        record, replay = self.project_feedback(); p = record['payload']
        self.assertFalse(replay); self.assertEqual(p['status'], 'insufficient_data'); self.assertEqual(p['observation_count'], 0)
        self.assertEqual(p['source_binding']['learning_sha256'], self.saved['snapshot_sha256'])
        self.assertTrue(p['mock']); self.assertFalse(p['real_audience_observation']); self.assertFalse(p['automatic_application'])
        self.assertEqual(p['provider_calls'], 0); self.assertEqual(set(p['consumers']), set(module.CONSUMERS))
        self.assertEqual(self.feedback.get(record['id']), record); self.assertEqual(self.read_wire, wire)
        self.assertEqual(self.store.get(self.saved['project_id']), before); self.assertEqual(self.analytics.costs.summary(self.saved['project_id']), costs)
        self.assertEqual(self.feedback.suggestions(record['id'])['suggestions'], [])

    def test_distinct_qualified_cohort_reaches_all_consumers_with_sample_and_control_evidence(self):
        self.cohort_learning(); self.saved = self.learn(request_key='explicit-qualified-six-post-learning-key')
        wire = self.read_wire.copy(); record, _ = self.project_feedback(); p = record['payload']
        self.assertEqual(p['observation_count'], 6); self.assertEqual(p['status'], 'recommendations_available')
        for name, dimension in [('trend_radar', 'trend_family'), ('idea_engine', 'hook'), ('media_planner', 'visual_strategy'), ('template_recommendations', 'subtitle_style')]:
            d = next(d for d in p['consumers'][name] if d['dimension'] == dimension)
            self.assertEqual(d['state'], 'recommendations_available'); positive = next(g for g in d['groups'] if g['state'] == 'recommendation_candidate')
            self.assertEqual((positive['sample_count'], positive['control_count']), (3, 3)); self.assertEqual(len(positive['snapshot_ids']), 3)
            self.assertEqual(len(positive['control_snapshot_ids']), 3); self.assertFalse(set(positive['snapshot_ids']) & set(positive['control_snapshot_ids']))
        templates = self.feedback.suggestions(record['id']); self.assertTrue(templates['suggestions'])
        self.assertEqual(templates['suggestions'][0]['match_kind'], 'recorded_template_reference')
        self.assertFalse(templates['suggestions'][0]['historical_full_style_verified']); self.assertFalse(templates['automatic_application'])
        self.assertEqual(templates['source_binding'], p['source_binding']); self.assertEqual(wire, self.read_wire)
        frozen = module.context(record); self.assertEqual(frozen['sha256'], digest({k:v for k,v in frozen.items() if k != 'sha256'}))

    def test_strict_raw_acknowledgements_keys_and_foreign_scope_digest_refuse_projection(self):
        for change in ({'acknowledged_recommendation_only': 1}, {'acknowledged_protocol_mock': 1}, {'request_key': 'X/unsafe-feedback-key'}, {'budget': 10}, {'automatic_application': True}):
            with self.assertRaises(ValidationError): self.feedback_body(**change)
        for changes, code in [({'acknowledged_protocol_mock': False}, 'MOCK_ACK'), ({'expected_learning_sha256': 'f'*64}, 'SOURCE_CHANGED'),
            ({'channel_profile_ref': 'real-estate-reference@1'}, 'SCOPE_MISMATCH'), ({'platform': 'tiktok'}, 'SCOPE_MISMATCH')]:
            with self.assertRaises(WorkflowError) as caught: self.project_feedback(**changes)
            if changes.get('channel_profile_ref'): self.assertIn(caught.exception.code, ('CHANNEL_PROFILE_NOT_FOUND','NATIVE_QUALIFIED_LEARNING_SCOPE_MISMATCH'))
            else: self.assertIn(code, caught.exception.code)
        with self.radar.store.transaction() as con: self.assertEqual(self.radar.records('learning', con), [])

    def test_concurrent_exact_key_replay_and_changed_source_conflict_do_not_duplicate(self):
        def run(_): return self.project_feedback()
        with ThreadPoolExecutor(max_workers=2) as pool: values = list(pool.map(run, range(2)))
        self.assertEqual(len({v[0]['id'] for v in values}), 1); self.assertEqual(sum(v[1] for v in values), 1)
        self.saved = self.learn(request_key='explicit-alternate-learning-for-feedback-key')
        with self.assertRaisesRegex(WorkflowError, 'IDEMPOTENCY_CONFLICT'): self.project_feedback()
        with self.radar.store.transaction() as con:
            self.assertEqual(len(self.radar.records('learning', con)), 1)
            self.assertEqual(con.execute("SELECT count(*) FROM decisions WHERE action='human_projected_qualified_channel_learning'").fetchone()[0], 1)

    def test_current_owner_recheck_rolls_back_projection_and_replay_requires_current_owner(self):
        original = module.content
        def revoke(*args):
            result = original(*args); object.__setattr__(self.verifier.registry.tokens[self.principal.token_id], 'enabled', False); return result
        with patch.object(module, 'content', side_effect=revoke), self.assertRaisesRegex(WorkflowError, 'OWNER_REQUIRED'): self.project_feedback()
        with self.radar.store.transaction() as con: self.assertEqual(self.radar.records('learning', con), [])
        object.__setattr__(self.verifier.registry.tokens[self.principal.token_id], 'enabled', True)
        record, _ = self.project_feedback(); object.__setattr__(self.verifier.registry.tokens[self.principal.token_id], 'enabled', False)
        self.assertEqual(self.feedback.get(record['id']), record)
        with self.assertRaisesRegex(WorkflowError, 'OWNER_REQUIRED'): self.project_feedback()

    def test_rehashed_projection_dimensions_source_scope_and_qualifiers_fail_closed(self):
        record, _ = self.project_feedback()
        for mutate in (lambda p:p.update(mock=False), lambda p:p['source_binding'].update(learning_sha256='f'*64),
            lambda p:p['recommendations'][0].update(state='recommendations_available'), lambda p:p['consumers']['idea_engine'][0].update(missing_feature_posts=999),
            lambda p:p.update(automatic_application=True), lambda p:p['scope'].update(target_binding_sha256='f'*64),lambda p:p.pop('schema_version')):
            changed = copy.deepcopy(record); mutate(changed['payload'])
            with self.radar.store.transaction() as con:
                raw = json.dumps(changed); con.execute('UPDATE records SET document=? WHERE id=?', (raw, record['id']))
                con.execute('UPDATE versions SET document=?,sha256=? WHERE id=? AND version=1', (raw, digest(changed), record['id']))
            with self.assertRaises(WorkflowError): self.feedback.get(record['id'])
            with self.assertRaises(WorkflowError): self.radar.get(record['id'],'learning')
        with self.radar.store.transaction() as con:
            raw = json.dumps(record); con.execute('UPDATE records SET document=? WHERE id=?', (raw, record['id']))
            con.execute('UPDATE versions SET document=?,sha256=? WHERE id=? AND version=1', (raw, digest(record), record['id']))
        self.assertEqual(self.feedback.get(record['id']), record)

    def test_original_history_survives_archive_expiry_provider_removal_and_later_learning(self):
        record, _ = self.project_feedback(); self.saved = self.learn(request_key='explicit-later-learning-projection-source')
        self.store.archive(record['payload']['request']['project_id'], self.store.get(record['payload']['request']['project_id'])['revision'], True)
        self.accounts.factories.clear(); self.service.factories.clear(); self.clock[0] += timedelta(days=2)
        self.assertEqual(self.feedback.get(record['id']), record); self.assertEqual(self.feedback.suggestions(record['id'])['projection_sha256'], digest(record))
        with self.assertRaisesRegex(WorkflowError, 'OWNER_REQUIRED'): self.project_feedback(request_key='explicit-expired-projection-owner-key')

    def test_original_response_cost_tamper_refuses_history_without_wire_or_fallback(self):
        record, _ = self.project_feedback(); wire = self.read_wire.copy()
        with self.store.transaction() as con: con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        with self.assertRaises(WorkflowError): self.feedback.get(record['id'])
        self.assertEqual(self.read_wire, wire)

    def test_wrong_workspace_or_rebound_source_configuration_is_refused(self):
        self.radar.workspace = 'wsp_foreign'
        with self.assertRaisesRegex(WorkflowError, 'CONFIGURATION_CHANGED'): self.project_feedback()
        with self.assertRaisesRegex(WorkflowError, 'CONFIGURATION_INVALID'): NativeQualifiedLearningFeedback(self.learning, self.radar)

    def radar_ready(self):
        self.radar.collect(CollectRequest(provider_key='fixture-radar',fixture_acknowledged=True,request_key=uuid.uuid4().hex),actor='EXPLICIT OWNER FIXTURE')
        self.assertTrue(self.radar.process())
        self.radar.refresh(RefreshRequest(channel_profile_ref='ai-education-reference@1',request_key=uuid.uuid4().hex),actor='EXPLICIT EDITOR FIXTURE')
        return self.radar.page()['items'][0]

    def handoff_with_feedback(self,record):
        self.radar.refresh(RefreshRequest(channel_profile_ref='ai-education-reference@1',learning_snapshot_id=record['id'],request_key=uuid.uuid4().hex),actor='EXPLICIT EDITOR FIXTURE')
        item=self.radar.page()['items'][0]
        handoff=self.radar.handoff(HandoffRequest(assessment_id=item['id'],expected_sha256=item['sha256'],acknowledged=True,request_key=uuid.uuid4().hex),actor='EXPLICIT EDITOR FIXTURE')
        return item,self.intelligence.bundle(handoff['payload']['research_run_id'])

    def test_qualified_family_ranks_mock_trends_and_handoff_carries_reviewed_idea_hypotheses(self):
        self.positive_family=self.radar_ready()['payload']['cluster_id'];self.cohort_learning();self.saved=self.learn(request_key='explicit-family-feedback-learning')
        record,_=self.project_feedback();wire=self.read_wire.copy();item,bundle=self.handoff_with_feedback(record)
        self.assertGreater(item['payload']['ranking']['history_adjustment_points'],0)
        self.assertEqual(item['payload']['learning_feedback'],module.context(record));self.assertFalse(item['payload']['ranking']['autonomous_execution'])
        advice=bundle['run']['context']['channel_history_recommendations'];self.assertEqual(advice['dimensions'],record['payload']['consumers']['idea_engine'])
        self.assertTrue(advice['mock']);self.assertFalse(advice['real_audience_observation']);self.assertFalse(advice['automatic_selection'])
        self.assertEqual(bundle['operations'],[]);self.assertEqual(wire,self.read_wire)

    def test_protocol_mock_feedback_refuses_real_signal_ranking_without_a_new_assessment(self):
        self.radar_ready();record,_=self.project_feedback();provider=FixtureProvider(self.clock[0]);provider.provider_key='explicit-rss-mock-wire';provider.source_type='news_rss'
        self.radar.providers=TrendProviderRegistry([provider]);self.radar.collect(CollectRequest(provider_key=provider.provider_key,request_key=uuid.uuid4().hex),actor='EXPLICIT OWNER FIXTURE');self.radar.process()
        with self.radar.store.transaction() as con:before=self.radar.records('assessment',con)
        with self.assertRaisesRegex(WorkflowError,'MOCK_HISTORY_CANNOT_RANK_REAL_SIGNALS'):
            self.radar.refresh(RefreshRequest(channel_profile_ref='ai-education-reference@1',learning_snapshot_id=record['id'],request_key=uuid.uuid4().hex),actor='EXPLICIT EDITOR FIXTURE')
        with self.radar.store.transaction() as con:self.assertEqual(self.radar.records('assessment',con),before)

    def test_removed_qualified_adapter_never_falls_back_to_fixture_learning(self):
        record,_=self.project_feedback();self.radar.qualified_learning=None
        with self.assertRaisesRegex(WorkflowError,'NOT_CONFIGURED'):self.radar.get(record['id'],'learning')
        self.assertEqual(self.feedback.get(record['id']),record)

    def test_intelligence_provider_refuses_changed_source_before_research_dispatch(self):
        self.radar_ready();record,_=self.project_feedback();item,bundle=self.handoff_with_feedback(record)
        self.intelligence.enqueue(bundle['run']['id'],bundle['run']['version'],'research',uuid.uuid4().hex)
        with self.store.transaction() as con:con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        with patch.object(self.intelligence.research_provider,'research',side_effect=AssertionError('Forbidden research dispatch')):
            self.assertTrue(self.intelligence.run_one())
        failed=self.intelligence.bundle(bundle['run']['id']);self.assertEqual(failed['operations'][0]['status'],'FAILED');self.assertEqual(failed['sources'],[])
        self.assertEqual(failed['operations'][0]['error']['code'],'NATIVE_OFFICIAL_ANALYTICS_RESULT_CHANGED')

    def test_read_only_projection_lookup_inside_workflow_write_avoids_inverse_writer_deadlock(self):
        record,_=self.project_feedback();entered=threading.Event();original=self.radar.replay
        def signal(*args):
            result=original(*args);entered.set();return result
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.store.transaction() as source:
                with patch.object(self.radar,'replay',side_effect=signal):
                    future=pool.submit(self.project_feedback,request_key='explicit-contested-feedback-key')
                    self.assertTrue(entered.wait(3));self.assertEqual(self.feedback.get(record['id'],source_con=source),record)
            self.assertFalse(future.result(timeout=15)[1])

    def test_frozen_context_rehash_does_not_change_source_qualified_consumer_evidence(self):
        record,_=self.project_feedback();value=module.context(record)
        for mutate in (lambda v:v['source_binding'].update(learning_sha256='f'*64),lambda v:v['consumers']['idea_engine'][0].update(missing_feature_posts=999),lambda v:v.update(mock=False)):
            changed=copy.deepcopy(value);mutate(changed);changed['sha256']=digest({k:v for k,v in changed.items() if k!='sha256'})
            with self.assertRaises(WorkflowError):module.qualified_context(self.feedback,changed)

    def test_idea_provider_and_storyboard_plan_receive_bound_recommendations_without_applying_them(self):
        from services.windows_native.research import PublicWebResearchProvider
        from services.windows_native.tests.test_intelligence_engines import receipt
        from services.windows_native.tests.test_workflow import proposal
        from services.windows_native.studio_media_planner import NativeStudioMediaPlanner
        from services.windows_native.studio_media_models import Create as PlanCreate
        self.radar_ready();record,_=self.project_feedback();item,bundle=self.handoff_with_feedback(record);seen=[];fixture=FixtureIdeas()
        class Ideas(FixtureIdeas):
            def generate(inner,query,context,findings,sources,out):seen.append(copy.deepcopy(context));return fixture.generate(query,context,findings,sources,out)
        def education_receipt(url):
            value=receipt();value['html']=value['html'].replace('housing','AI educational video');return value
        self.intelligence.research_provider=PublicWebResearchProvider(self.root/'research-sources',fetch=education_receipt);self.intelligence.idea_provider=Ideas()
        for action in ('research','ideas'):
            self.intelligence.enqueue(bundle['run']['id'],bundle['run']['version'],action,uuid.uuid4().hex);self.assertTrue(self.intelligence.run_one());bundle=self.intelligence.bundle(bundle['run']['id'])
            self.assertEqual(bundle['operations'][0]['status'],'SUCCEEDED')
        self.assertEqual(seen[0]['channel_history_recommendations'],module.idea_recommendations(item['payload']['learning_feedback']))
        idea=bundle['ideas'][0];self.intelligence.select(idea['id'],idea['version'],bundle['opportunity']['version'],'EXPLICIT HUMAN FIXTURE')
        bundle=self.intelligence.bundle(bundle['run']['id']);brief=self.intelligence.approve_brief(bundle['brief']['id'],bundle['brief']['version'],'EXPLICIT HUMAN FIXTURE',True)
        project=self.intelligence.send(brief['id'],brief['version'],production_quality=True,narrated_workflow=True)
        project=self.store.save(project['id'],project['revision'],proposal=proposal());view=self.store.shot_view(project['id']);before=copy.deepcopy(view['shot_timeline'])
        planner=NativeStudioMediaPlanner(self.store,self.config,workspace_id=self.workspace,providers=lambda:{'workspace_id':self.workspace,'stock':{'items':[]},'generation':{'items':[]}})
        result=planner.create(project['id'],PlanCreate(revision=project['revision'],expected_timeline_version=view['shot_timeline']['version']))
        saved=result['items'][-1]['plan']['input']['channel_history_recommendations'];self.assertEqual(saved['dimensions'],record['payload']['consumers']['media_planner'])
        self.assertFalse(saved['automatic_application']);self.assertFalse(saved['planning_authorizes_payment']);self.assertEqual(self.store.shot_view(project['id'])['shot_timeline']['snapshot'],before['snapshot'])

if __name__ == '__main__': unittest.main()
