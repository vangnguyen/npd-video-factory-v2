"""Owned contracts and official feed-wire fixtures; never audience/Owner acceptance."""
import asyncio,copy,json,tempfile,threading,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from app.trend_providers import TrendSourceProvider,TrendProviderRegistry
from services.windows_native.trend_radar import NativeTrendRadar,VIEWS
from services.windows_native.trend_radar_models import CollectRequest,RefreshRequest,HandoffRequest,SignalEvidence,ClusterPolicy,LearningRequest
from services.windows_native.trend_radar_engine import similarity,clusters
from services.windows_native.trend_radar_providers import ApprovedFeedProvider,FeedConfig,registry
from services.windows_native.trend_radar_learning import create as learn
from services.windows_native.trend_radar_lineage import validate as lineage
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.analytics import NativeAnalytics
from services.windows_native.publications import NativePublications
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
from services.windows_native.tests.test_intelligence_engines import receipt
from services.windows_native.research import PublicWebResearchProvider
from services.windows_native.tests.test_publications import CAPABILITIES
from services.windows_native.tests import test_access_http as http

class FixtureProvider(TrendSourceProvider):
    provider_key='fixture-radar';display_name='EXPLICIT OWNED TREND FIXTURE';source_type='fixture';status='healthy';authorized_access=True;config_ref='fixture:owned-radar-v1'
    def __init__(self,now):
        self.calls=0;self.values=[SignalEvidence(source=s,source_reference='https://example.com/ai-'+s,observed_at=now,topic='AI educational video',
            format='vertical_short',language='vi',country='VN',views=10000,likes=600,creator_count=3,content_count=10,velocity=85,acceleration=65,
            evidence_summary='Explicit synthetic trend input; not provider/audience acceptance') for s in ('youtube','tiktok')]
    async def collect_signals(self,request):self.calls+=1;return self.values[:request.limit]
    async def search_topic(self,topic,request):return await self.collect_signals(request)
    async def get_topic_metrics(self,topic):return {'views':None}
    async def get_content_reference(self,reference):return {'reference_only':True,'download_allowed':False}

class RadarTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.config=Config(data_root=self.root);self.production=Store(self.root)
        def education_receipt(_):
            value=receipt();value['html']=value['html'].replace('housing','AI educational video');return value
        self.intelligence=IntelligenceService(self.config,self.production,research_provider=PublicWebResearchProvider(self.root/'research-sources',fetch=education_receipt),idea_provider=FixtureIdeas())
        self.analytics=NativeAnalytics(self.production,NativePublications(self.production,CAPABILITIES));self.now=datetime.now(timezone.utc);self.provider=FixtureProvider(self.now)
        self.radar=NativeTrendRadar(self.intelligence,self.analytics,workspace='wsp_native_local',providers=TrendProviderRegistry([self.provider]),clock=lambda:self.now)
        self.original=self.production.create('PRESERVED RADAR OWNER FIXTURE','No calls')
    def tearDown(self):self.radar.close();self.temp.cleanup()
    def collect(self,**changes):return self.radar.collect(CollectRequest(provider_key='fixture-radar',fixture_acknowledged=True,request_key=uuid.uuid4().hex,**changes),actor='explicit-fixture-owner')
    def refresh(self,**changes):return self.radar.refresh(RefreshRequest(channel_profile_ref='ai-education-reference@1',request_key=uuid.uuid4().hex,**changes),actor='explicit-fixture-editor')
    def ready(self):
        value=self.collect();self.assertTrue(self.radar.process());self.refresh();return self.radar.page()['items'][0]
    def handoff(self,item,**changes):return self.radar.handoff(HandoffRequest(assessment_id=item['id'],expected_sha256=item['sha256'],acknowledged=True,request_key=uuid.uuid4().hex,**changes),actor='explicit-fixture-editor')
    def test_default_providers_are_not_configured_without_fixture_fallback_or_calls(self):
        default=NativeTrendRadar(self.intelligence,self.analytics,workspace='wsp_native_local')
        self.assertFalse(default.states()['automatic_collection_enabled']);self.assertTrue(all(v['status']=='not_configured' for v in default.states()['providers']))
        v=default.collect(CollectRequest(provider_key='youtube-data-api',request_key=uuid.uuid4().hex),actor='fixture-owner')
        self.assertEqual(v['payload']['status'],'not_configured');self.assertFalse(default.process());self.assertEqual(v['payload']['provider_calls'],0)
        with self.assertRaisesRegex(WorkflowError,'FIXTURE_ACK'):self.radar.collect(CollectRequest(provider_key='fixture-radar',request_key=uuid.uuid4().hex),actor='fixture-owner')
        self.assertEqual(self.provider.calls,0)
    def test_collection_exact_retry_conflict_cache_and_missing_metrics(self):
        payload=CollectRequest(provider_key='fixture-radar',fixture_acknowledged=True,request_key=uuid.uuid4().hex)
        first=self.radar.collect(payload,actor='fixture-owner');self.assertEqual(self.radar.collect(payload,actor='fixture-owner'),first);self.assertTrue(self.radar.process())
        final=self.radar.get(first['id']);self.assertEqual(final['payload']['status'],'succeeded');self.assertEqual(self.provider.calls,1)
        self.assertEqual(self.radar.collect(payload,actor='fixture-owner'),final)
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY'):self.radar.collect(payload.model_copy(update={'query':'different'}),actor='fixture-owner')
        cached=self.collect();self.assertEqual(cached['payload']['status'],'cached');self.assertEqual(cached['payload']['signal_ids'],final['payload']['signal_ids']);self.assertFalse(self.radar.process())
        raw=self.radar.get(final['payload']['signal_ids'][0],'signal')['payload'];self.assertIsNone(raw['signal']['shares']);self.assertIsNone(raw['signal']['saves']);self.assertEqual(raw['raw_signal_hash'],digest(raw['signal']))
        self.assertEqual(self.production.get(self.original['id']),self.original)
    def test_restart_queued_runs_once_running_is_marked_interrupted_without_replay(self):
        queued=self.collect();reopened=NativeTrendRadar(self.intelligence,self.analytics,workspace='wsp_native_local',providers=self.radar.providers,clock=lambda:self.now)
        reopened.recover();self.assertTrue(reopened.process());self.assertEqual(self.provider.calls,1)
        second=self.collect(refresh=True)
        with self.radar.store.transaction() as con:self.radar.put('collection',{**second['payload'],'status':'running'},con,second['id'],second)
        reopened.recover();self.assertEqual(reopened.get(second['id'])['payload']['status'],'failed');self.assertFalse(reopened.process());self.assertEqual(self.provider.calls,1)
    def test_configuration_change_future_observation_and_cancel_do_not_create_signals(self):
        value=self.collect();self.provider.config_ref='fixture:changed';self.radar.process();self.assertEqual(self.radar.get(value['id'])['payload']['failure_code'],'TREND_PROVIDER_CONFIGURATION_CHANGED');self.assertEqual(self.provider.calls,0)
        self.provider.values=[v.model_copy(update={'observed_at':self.now+timedelta(hours=1)}) for v in self.provider.values]
        value=self.collect(refresh=True);self.radar.process();self.assertEqual(self.radar.get(value['id'])['payload']['failure_code'],'TREND_FUTURE_OBSERVATION_INVALID')
        third=self.collect(refresh=True);self.radar.cancel(third['id'],third['version'],actor='fixture-owner');self.assertFalse(self.radar.process())
        with self.radar.store.transaction() as con:self.assertEqual(self.radar.records('signal',con),[])
    def test_concurrent_queue_claim_and_cancel_running_refuse_late_commit(self):
        entered=threading.Event();release=threading.Event();original=self.provider.collect_signals
        async def paused(request):entered.set();await asyncio.to_thread(release.wait,3);return await original(request)
        value=self.collect()
        with patch.object(self.provider,'collect_signals',side_effect=paused),ThreadPoolExecutor(max_workers=2) as pool:
            future=pool.submit(self.radar.process);self.assertTrue(entered.wait(2));self.assertFalse(self.radar.process())
            running=self.radar.get(value['id']);self.radar.cancel(value['id'],running['version'],actor='fixture-owner');release.set();self.assertTrue(future.result())
        self.assertEqual(self.radar.get(value['id'])['payload']['status'],'cancelled')
        with self.radar.store.transaction() as con:self.assertEqual(self.radar.records('signal',con),[])
    def test_semantic_entity_keyword_and_temporal_evidence_is_explicit(self):
        item=self.ready();signals=self.radar.detail(item['id'])['signals'];a,b=copy.deepcopy(signals)
        a['payload']['signal'].update(topic='Film making',entities=['OpenAI'],embedding=[1,0],embedding_model='explicit-embedding-fixture')
        b['payload']['signal'].update(topic='AI cinema',entities=['OpenAI'],embedding=[.9,.1],embedding_model='explicit-embedding-fixture')
        evidence=similarity(a,b,ClusterPolicy());self.assertTrue(evidence['available']['semantic']);self.assertEqual(evidence['semantic_model'],'explicit-embedding-fixture');self.assertGreater(evidence['score'],.34)
        self.assertEqual(len(clusters([a,b],ClusterPolicy(),self.now)),1)
        b['payload']['signal']['observed_at']=(self.now-timedelta(days=8)).isoformat();self.assertEqual(similarity(a,b,ClusterPolicy())['score'],0);self.assertEqual(len(clusters([a,b],ClusterPolicy(),self.now)),2)
        for embedding in [[float('nan'),1],[float('inf'),1],[0,0],[1e100,1]]:
            with self.assertRaises(ValidationError):SignalEvidence.model_validate({**a['payload']['signal'],'embedding':embedding})
    def test_stable_family_and_lifecycle_history_never_reappear_from_old_filtered_estimate(self):
        item=self.ready();identity=item['payload']['cluster_id'];self.assertEqual(len(self.radar.page(view='breakout')['items']),1)
        self.now+=timedelta(days=1);self.provider.values=[v.model_copy(update={'observed_at':self.now,'velocity':-10,'acceleration':-10}) for v in self.provider.values]
        self.collect(refresh=True);self.radar.process();self.refresh();current=self.radar.page()['items'][0]
        self.assertEqual(current['payload']['cluster_id'],identity);self.assertEqual(current['payload']['cluster_snapshot']['payload']['lifecycle'],'declining')
        self.assertEqual(len(self.radar.detail(identity)['history']),2);self.assertEqual(self.radar.page(view='breakout')['items'],[])
        self.assertEqual(item['payload']['cluster_snapshot']['payload']['lifecycle'],'breakout')
    def test_configured_weights_filters_views_and_contexts_remain_independent(self):
        self.ready();self.assertEqual(set(VIEWS),set(self.radar.states()['views']))
        for view in VIEWS:self.assertTrue(self.radar.page(view=view)['estimated'])
        self.assertEqual(self.radar.page(platform='news_rss')['items'],[]);self.assertEqual(self.radar.page(country='US')['items'],[])
        self.refresh(business_objective='conversion',weights={'velocity':0,'acceleration':0,'channel_fit':10})
        self.assertEqual(len(self.radar.page(objective='conversion')['items']),1);self.assertEqual(self.radar.page(niche='real_estate')['items'],[])
        with self.assertRaisesRegex(WorkflowError,'PAGE_INVALID'):self.radar.page(view='fabricated')
    def test_exact_handoff_atomic_retry_original_flow_guided_channel_and_lineage(self):
        item=self.ready();payload=HandoffRequest(assessment_id=item['id'],expected_sha256=item['sha256'],acknowledged=True,request_key=uuid.uuid4().hex)
        handoff=self.radar.handoff(payload,actor='fixture-editor');self.assertEqual(self.radar.handoff(payload,actor='fixture-editor'),handoff)
        bundle=self.intelligence.bundle(handoff['payload']['research_run_id']);context=bundle['run']['context']['trend_radar'];self.assertEqual(lineage(context)['trend_cluster_id'],item['payload']['cluster_id'])
        self.assertEqual(bundle['operations'],[]);self.assertEqual(self.production.get(self.original['id']),self.original)
        for action in ('research','ideas'):
            self.intelligence.enqueue(bundle['run']['id'],bundle['run']['version'],action,uuid.uuid4().hex);self.assertTrue(self.intelligence.run_one());bundle=self.intelligence.bundle(bundle['run']['id'])
        idea=bundle['ideas'][0];self.intelligence.select(idea['id'],idea['version'],bundle['opportunity']['version'],'EXPLICIT HUMAN FIXTURE');bundle=self.intelligence.bundle(bundle['run']['id'])
        brief=self.intelligence.approve_brief(bundle['brief']['id'],bundle['brief']['version'],'EXPLICIT HUMAN FIXTURE',True)
        project=self.intelligence.send(brief['id'],brief['version'],production_quality=True,narrated_workflow=True)
        self.assertEqual(project['document']['channel_profile']['profile']['profile_ref'],'ai-education-reference@1');self.assertEqual(project['document']['niche'],'technology');self.assertIsNone(project['approval']);self.assertEqual(project['jobs'],[])
        self.assertEqual(project['document']['content_intelligence']['run']['context']['trend_radar'],context)
        tampered=copy.deepcopy(context);tampered['signals'][0]['payload']['signal']['views']=999
        with self.assertRaisesRegex(WorkflowError,'LINEAGE_INVALID'):lineage(tampered)
    def test_handoff_conflicts_and_failure_roll_back_research_and_opportunity(self):
        item=self.ready()
        with self.assertRaisesRegex(WorkflowError,'BINDING_CHANGED'):self.radar.handoff(HandoffRequest(assessment_id=item['id'],expected_sha256='0'*64,acknowledged=True,request_key=uuid.uuid4().hex),actor='fixture-editor')
        before=self.intelligence.store.list('ResearchRun');original=self.intelligence.create
        def failed(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('EXPLICIT AFTER-CREATE COMMIT FAILURE')
        with patch.object(self.intelligence,'create',side_effect=failed):
            with self.assertRaises(RuntimeError):self.handoff(item)
        self.assertEqual(self.intelligence.store.list('ResearchRun'),before)
        with self.radar.store.transaction() as con:self.assertEqual(self.radar.records('handoff',con),[])
        for ack in (False,1,'true'):
            with self.assertRaises(ValidationError):HandoffRequest(assessment_id=item['id'],expected_sha256=item['sha256'],acknowledged=ack,request_key=uuid.uuid4().hex)
    def test_workspace_history_and_checksum_tampering_are_closed(self):
        item=self.ready();other=NativeTrendRadar(self.intelligence,self.analytics,workspace='wsp_other_fixture',providers=self.radar.providers)
        self.assertEqual(other.page()['items'],[])
        with self.assertRaisesRegex(WorkflowError,'NOT_FOUND'):other.detail(item['id'])
        with self.radar.store.transaction() as con:
            value=self.radar.get(item['id'],con=con);value['payload']['score']['total_score']=100
            con.execute('UPDATE records SET document=? WHERE id=?',(json.dumps(value),item['id']))
        with self.assertRaisesRegex(WorkflowError,'INTEGRITY'):self.radar.page()
    def test_native_learning_empty_snapshot_scope_and_no_official_fallback(self):
        self.ready();value=learn(self.radar,LearningRequest(channel_profile_ref='ai-education-reference@1',provider_mode='fixture',fixture_acknowledged=True,request_key=uuid.uuid4().hex),actor='fixture-owner')
        self.assertEqual(value['payload']['observations'],[]);self.assertTrue(all(v['state']=='insufficient_data' for v in value['payload']['recommendations']))
        self.refresh(learning_snapshot_id=value['id']);self.assertIsNone(self.radar.page()['items'][0]['payload']['ranking']['history_adjustment_points'])
        with self.assertRaisesRegex(WorkflowError,'SCOPE_MISMATCH'):self.refresh(learning_snapshot_id=value['id'],platform='tiktok')
        official=learn(self.radar,LearningRequest(channel_profile_ref='ai-education-reference@1',request_key=uuid.uuid4().hex),actor='fixture-owner');self.assertEqual(official['payload']['status'],'not_configured');self.assertEqual(official['payload']['provider_calls'],0)
    def test_bound_full_qc_projection_uses_measurements_and_rejects_wrong_document_or_pcm_final(self):
        from services.windows_native.publication_qc import project
        doc={'explicit_measured_fixture':True};qc={'passed':True,'final_sha256':'a'*64,'checks':{'full_production_qc':True},'full_quality':{
            'schema_version':'native-storyboard-full-qc-v1','status':'passed','document_sha256':digest(doc),'final_sha256':'a'*64,'full_production_qc':{
                'status':'passed','checksum_sha256':'a'*64,'width':1080,'height':1920,'video_codec':'h264','audio_codec':'aac','duration_seconds':9.433,'fps':30,'sample_rate':48000}}}
        job={'snapshot':{'document':doc},'result':{'qc':qc}};self.assertEqual(project(job)['width'],1080);self.assertEqual(project(job)['duration_seconds'],9.433)
        for mutation in (lambda v:v['snapshot']['document'].update(changed=True),lambda v:v['result']['qc']['full_quality']['full_production_qc'].update(checksum_sha256='0'*64),lambda v:v['result']['qc']['full_quality'].update(status='failed_qc')):
            bad=copy.deepcopy(job);mutation(bad)
            with self.assertRaisesRegex(WorkflowError,'FULL_QC_BINDING'):project(bad)
    def seed_analytics(self,family,profile,index):
        from services.windows_native.channel_profiles import select
        from services.windows_native.tests.test_publications import render_fixture
        from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
        from services.windows_native.analytics_models import NativeAnalyticsRequest
        p=self.production.create('EXPLICIT HISTORY FIXTURE '+str(index),'Authored annotations',channel_profile=select('ai-education-reference@1'))
        with self.production.transaction() as con:
            doc=p['document'];doc['analytics_features']={'trend_cluster_id':family,'hook_type':'fixture-hook-'+profile}
            con.execute('UPDATE projects SET document=?,revision=revision+1 WHERE id=?',(json.dumps(doc),p['id']));self.production.version(con,p['id'])
        p,job=render_fixture(self.production,project=self.production.get(p['id']))
        pub=self.analytics.publications;value,_=pub.create(p['id'],NativePublicationCreate(revision=p['revision'],final_job_id=job['id'],platform='youtube',metadata={'title':'EXPLICIT NONPLAYABLE HISTORY FIXTURE'},request_key=uuid.uuid4().hex),actor='fixture-editor')
        pub.approve(p['id'],value['publication_id'],NativePublishApproval(expected_fingerprint=value['request_fingerprint'],expected_artifact_sha256=value['snapshot']['final_sha256'],acknowledged=True),actor='fixture-owner');pub.process()
        sync,_=self.analytics.create(p['id'],NativeAnalyticsRequest(publication_id=value['publication_id'],provider_mode='fixture',fixture_acknowledged=True,fixture_profile=profile,request_key=uuid.uuid4().hex),actor='fixture-owner')
        original=self.analytics.provider.collect
        async def matched_fixture_coverage(context):
            from dataclasses import replace
            result=await original(context)
            # Explicit synthetic null-revenue variants give independent controls
            # the same factor coverage; product compatibility is not relaxed.
            return replace(result,metrics=result.metrics.model_copy(update={'revenue':None,'rpm':None}))
        with patch.object(self.analytics.provider,'collect',side_effect=matched_fixture_coverage):self.analytics.process()
        return self.analytics.get(p['id'],sync['sync_id'])
    def test_frozen_distinct_post_learning_changes_recommendation_only_and_keeps_history(self):
        item=self.ready();family=item['payload']['cluster_id'];records=[]
        for i in range(6):records.append(self.seed_analytics(family if i<3 else 'explicit-other-family','winner_candidate' if i<3 else 'underperforming',i))
        value=learn(self.radar,LearningRequest(channel_profile_ref='ai-education-reference@1',provider_mode='fixture',fixture_acknowledged=True,request_key=uuid.uuid4().hex),actor='fixture-owner')
        self.assertEqual(len(value['payload']['observations']),6);self.assertTrue(value['payload']['scope']['mock']);before=copy.deepcopy(value)
        family_groups=next(v for v in value['payload']['recommendations'] if v['dimension']=='trend_family')['groups'];positive=next(v for v in family_groups if v['value']==family)
        self.assertEqual(positive['state'],'recommendation_candidate');self.assertEqual(positive['sample_count'],3);self.assertEqual(positive['control_count'],3)
        self.refresh(learning_snapshot_id=value['id']);rank=self.radar.page()['items'][0]['payload']['ranking'];self.assertGreater(rank['history_adjustment_points'],0);self.assertFalse(rank['autonomous_execution'])
        self.assertEqual(self.radar.get(value['id']),before);self.assertEqual(self.production.get(self.original['id']),self.original)
        self.assertEqual({v['features']['publishing_time'] for v in [r['snapshot'] for r in records]},{None})
    def test_mock_learning_cannot_rank_real_signals_and_corrupt_history_is_refused(self):
        self.ready();value=learn(self.radar,LearningRequest(channel_profile_ref='ai-education-reference@1',provider_mode='fixture',fixture_acknowledged=True,request_key=uuid.uuid4().hex),actor='fixture-owner')
        provider=FixtureProvider(self.now);provider.provider_key='rss-wire-fixture';provider.source_type='news_rss';self.radar.providers=TrendProviderRegistry([provider])
        self.radar.collect(CollectRequest(provider_key=provider.provider_key,request_key=uuid.uuid4().hex),actor='fixture-owner');self.radar.process()
        with self.assertRaisesRegex(WorkflowError,'MOCK_HISTORY'):self.refresh(learning_snapshot_id=value['id'])
        seeded=self.seed_analytics('explicit-family','winner_candidate',0)
        with self.production.transaction() as con:con.execute('UPDATE native_analytics_snapshots SET snapshot_sha256=? WHERE snapshot_id=?',('0'*64,seeded['snapshot']['snapshot_id']))
        with self.assertRaisesRegex(WorkflowError,'EVIDENCE_INVALID'):learn(self.radar,LearningRequest(channel_profile_ref='ai-education-reference@1',provider_mode='fixture',fixture_acknowledged=True,request_key=uuid.uuid4().hex),actor='fixture-owner')

class FeedTests(unittest.TestCase):
    def config(self):return FeedConfig(provider_key='rss-owned-fixture',display_name='EXPLICIT RSS WIRE FIXTURE',feed_url='https://example.com/feed.xml',owner_access_approved=True,language='vi',country='VN')
    def test_rss_and_atom_dates_quotes_null_metrics_and_no_media_download(self):
        from app.trend_models import TrendCollectionRequest
        for raw in ['<rss><channel><item><title>AI educational video</title><link>https://example.com/news</link><pubDate>Thu, 01 Oct 2026 01:00:00 GMT</pubDate><enclosure url="https://example.com/creator.mp4"/></item></channel></rss>',
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>AI educational video</title><link href="https://example.com/news"/><published>2026-10-01T01:00:00Z</published></entry></feed>']:
            fetch=lambda _: {'html':raw,'requested_url':'https://example.com/feed.xml','final_url':'https://example.com/feed.xml','raw_sha256':digest(raw)}
            provider=ApprovedFeedProvider(self.config(),fetch=fetch,clock=lambda:datetime(2026,10,8,tzinfo=timezone.utc));values=asyncio.run(provider.collect_signals(TrendCollectionRequest(provider_key=provider.provider_key)))
            self.assertEqual(len(values),1);value=values[0];self.assertEqual(value.published_at,datetime(2026,10,1,1,tzinfo=timezone.utc));self.assertEqual(value.observed_at,datetime(2026,10,8,tzinfo=timezone.utc))
            self.assertTrue(all(getattr(value,k) is None for k in ('views','likes','comments','shares','saves','velocity','acceleration')));self.assertFalse(asyncio.run(provider.get_content_reference(str(value.source_reference)))['download_allowed'])
    def test_feed_registry_workspace_enablement_public_reference_and_unsafe_xml(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'approved.json';path.write_text(json.dumps({'schema_version':'native-trend-feed-registry-v1','workspace_id':'wsp_native_local','feeds':[self.config().model_dump(mode='json')]}))
            with self.assertRaisesRegex(WorkflowError,'ENABLEMENT'):registry(path,workspace='wsp_native_local')
            with self.assertRaisesRegex(WorkflowError,'WORKSPACE'):registry(path,workspace='wsp_other_fixture',owner_enabled=True)
            self.assertTrue(registry(path,workspace='wsp_native_local',owner_enabled=True).get(self.config().provider_key).authorized_access)
        for url in ('http://example.com/feed','https://name:secret@example.com/feed','https://example.com/feed?token=secret'):
            with self.assertRaises(WorkflowError):ApprovedFeedProvider(self.config().model_copy(update={'feed_url':url}))
        provider=ApprovedFeedProvider(self.config(),fetch=lambda _: {'html':'<!DOCTYPE rss [<!ENTITY a SYSTEM "file:///private">]><rss/>'})
        from app.trend_models import TrendCollectionRequest
        with self.assertRaisesRegex(WorkflowError,'XML_UNSAFE'):asyncio.run(provider.collect_signals(TrendCollectionRequest()))

class RadarHTTPTests(unittest.TestCase):
    setUp=http.NativeAccessHTTPTests.setUp;tearDown=http.NativeAccessHTTPTests.tearDown
    start_server=http.NativeAccessHTTPTests.start_server;stop_server=http.NativeAccessHTTPTests.stop_server;request=http.NativeAccessHTTPTests.request;account=http.NativeAccessHTTPTests.account
    def test_existing_auth_csrf_role_scope_static_no_spoof_or_automatic_provider(self):
        self.account('viewer');self.assertEqual(self.request('GET','/trends')[0],200);self.assertEqual(self.request('GET','/api/trends/radar')[0],200)
        for path in ('/api/trends/collectons','/api/trends/collections','/api/trends/refresh','/api/trends/handoff','/api/trends/learning'):self.assertEqual(self.request('POST',path,{})[0],403)
        self.account('editor');self.assertEqual(self.request('POST','/api/trends/collections',{})[0],403)
        status,value,_=self.request('POST','/api/trends/refresh',{'channel_profile_ref':'ai-education-reference@1','request_key':uuid.uuid4().hex,'actor_ref':'FORGED'});self.assertEqual(status,400)
        status,value,_=self.request('POST','/api/trends/refresh',{'channel_profile_ref':'ai-education-reference@1','request_key':uuid.uuid4().hex});self.assertEqual(status,200,value);self.assertEqual(value['payload']['actor_ref'],'explicit-fixture');self.assertEqual(value['payload']['assessment_ids'],[])
        self.account('owner');status,value,_=self.request('POST','/api/trends/collections',{'provider_key':'youtube-data-api','request_key':uuid.uuid4().hex});self.assertEqual(status,200);self.assertEqual(value['payload']['status'],'not_configured')
        self.assertEqual(self.request('POST','/api/trends/refresh',{},headers={'X-VF-CSRF':'wrong'})[0],403);self.assertEqual(self.request('GET','/api/trends/radar?view=a&view=b')[0],400)
        self.assertEqual(self.request('GET','/api/trends/radar?offset=-1')[0],400);self.assertEqual(self.pipeline.calls,0)
