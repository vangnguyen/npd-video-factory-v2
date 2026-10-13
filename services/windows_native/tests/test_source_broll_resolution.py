"""Actual owned source/media bytes; provider and human evidence explicit fixtures."""
import copy,json,unittest,uuid,concurrent.futures,time,io
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
import httpx
from services.windows_native import source_broll as broll
from services.windows_native import auto_edit_timeline as timeline
from services.windows_native.source_broll_resolution import NativeSourceBrollResolution
from services.windows_native.source_broll_resolution_models import Create,Step,Apply
from services.windows_native.stock import NativeStock
from services.windows_native.stock_registry import StockFactory,StockCredential
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_worker import NativeGenerationWorker
from services.windows_native.media import ingest_media
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.store import Store
from services.windows_native.tests import test_source_broll as fixture
from services.windows_native.tests.test_stock import photo,pixels


class SourceBrollResolutionTests(unittest.TestCase):
    setUp=fixture.SourceBrollTests.setUp
    tearDown=fixture.SourceBrollTests.tearDown
    save_analysis=fixture.SourceBrollTests.save_analysis
    real_source=fixture.SourceBrollTests.real_source
    image=fixture.SourceBrollTests.image
    workspace='wsp_source_broll_resolution_fixture'

    def engine(self,wire=None):
        factory=StockFactory('pexels',StockCredential(api_key='explicit-source-resolution-fixture',enabled=True),
            owner_enabled=True,transport=httpx.MockTransport(wire)) if wire else None
        self.stock=NativeStock(self.store,self.config,workspace_id=self.workspace,factories={'pexels':factory} if factory else {})
        self.generation=NativeGenerationWorker(NativeGenerationQueue(self.store,workspace_id=self.workspace),self.config)
        self.service=NativeSourceBrollResolution(self.store,self.config,self.stock,self.generation,workspace_id=self.workspace)
        self.addCleanup(self.stock.close);self.addCleanup(self.generation.close)
        return self.service

    def plan(self):
        self.project=broll.create(self.store,self.config,self.project['id'],self.project['revision'],{
            'expected_version':self.project['document']['canonical_timeline']['version']},resolver_context=self.service.planning_context())
        return self.project['document']['source_broll_plans'][-1]

    def start(self,record):
        return self.service.create(self.project['id'],Create(revision=self.project['revision'],
            expected_timeline_version=self.project['document']['canonical_timeline']['version'],media_plan_id=record['plan']['media_plan_id'],
            expected_plan_version=record['plan']['version'],expected_plan_sha256=record['sha256'],
            item_ids=[record['plan']['items'][0]['media_plan_item_id']],fixture_acknowledged=True,
            request_key='source-resolution-create-'+uuid.uuid4().hex),actor='fixture-editor')[0]

    def step(self,session,key=None):
        self.service.step(self.project['id'],session['resolution_id'],Step(revision=session['state']['expected']['revision'],
            expected_resolution_version=session['version'],request_key=key or 'source-resolution-step-'+uuid.uuid4().hex),actor='fixture-editor')
        self.project=self.store.get(self.project['id'])
        return self.service.get(self.project['id'],session['resolution_id'])

    def test_user_asset_priority_resolves_plan_and_explicitly_places_same_canonical_without_provider(self):
        source=self.real_source();asset=self.image();self.engine();record=self.plan()
        before=copy.deepcopy(self.store.get(self.project['id']));sha=file_sha(source);session=self.start(record)
        self.assertEqual(self.store.get(self.project['id']),before)
        with patch.object(self.stock,'create',side_effect=AssertionError('User asset needs no provider')):
            session=self.step(session)
        self.assertEqual(session['state']['status'],'ready')
        current=self.store.get(self.project['id']);self.assertEqual(current['document']['canonical_timeline'],before['document']['canonical_timeline'])
        self.assertIsNone(current['approval']);self.assertEqual(current['document']['media_analysis'],before['document']['media_analysis'])
        payload=Apply(revision=current['revision'],expected_resolution_version=session['version'],
            expected_timeline_version=1,acknowledged=True,request_key='source-resolution-apply-'+uuid.uuid4().hex)
        receipt,replay=self.service.apply(self.project['id'],session['resolution_id'],payload,actor='fixture-editor')
        self.assertFalse(replay);self.assertTrue(receipt['human_preview_required']);self.assertFalse(receipt['video_approval_granted'])
        after=self.store.get(self.project['id']);self.assertIsNone(after['approval'])
        snapshot=after['document']['canonical_timeline']['snapshot'];original=before['document']['canonical_timeline']['snapshot']
        self.assertEqual(snapshot['duration_seconds'],original['duration_seconds'])
        self.assertEqual([t for t in snapshot['tracks'] if t['kind']!='broll'],[t for t in original['tracks'] if t['kind']!='broll'])
        clips=[c for t in snapshot['tracks'] if t['kind']=='broll' for c in t['clips']]
        self.assertTrue(clips);self.assertTrue(all(c['metadata']['native_asset_id']==asset['id'] for c in clips))
        self.assertFalse(any(c['metadata']['publishing_allowed'] or c['metadata']['production_eligible'] for c in clips))
        self.assertEqual(self.service.apply(self.project['id'],session['resolution_id'],payload,actor='fixture-editor'),(receipt,True))
        self.assertEqual(self.store.get(self.project['id']),after);self.assertEqual(file_sha(source),sha)

    def test_missing_all_providers_preserves_source_and_records_each_fallback(self):
        self.real_source();self.engine();record=self.plan();before=copy.deepcopy(self.store.get(self.project['id']))
        session=self.start(record)
        for _ in range(10):
            if session['state']['status']=='unresolved':break
            session=self.step(session)
        self.assertEqual(session['state']['status'],'unresolved')
        self.assertEqual(self.store.get(self.project['id']),before)
        item=next(iter(session['state']['items'].values()))
        self.assertEqual([v['tier'] for v in item['attempts']],['user_asset','licensed_stock','licensed_stock','licensed_stock','internal_library','ai_image','ai_video'])
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_stock_jobs').fetchone()[0],0)
        self.assertEqual(session['snapshot']['unsupported_resolution_tiers'],[{'tier':'motion_graphic','status':'NOT_CONFIGURED',
            'reason':'SOURCE_RESOLVER_UNSUPPORTED_OPTIONAL_TAIL','provider_calls':0}])

    def test_foreign_project_edit_fails_without_creating_child_or_changing_timeline(self):
        self.real_source();self.engine();record=self.plan();session=self.start(record)
        self.project=self.store.save(self.project['id'],self.project['revision'],prompt='Explicit unrelated edit fixture')
        before=copy.deepcopy(self.project)
        with self.assertRaises(WorkflowError):self.step(session)
        self.assertEqual(self.store.get(self.project['id']),before)

    def mock_stock(self,source):
        self.wire_calls=[]
        video={'id':11,'duration':3,'width':320,'height':240,'url':'https://www.pexels.com/video/explicit-fixture-11/',
            'user':{'name':'EXPLICIT SYNTHETIC PROVIDER VECTOR'},'video_files':[{'id':11,'width':320,'height':240,
            'file_type':'video/mp4','quality':'hd','link':'https://videos.pexels.com/video-files/11/explicit-fixture.mp4'}]}
        def wire(request):
            self.wire_calls.append((request.url.host,request.url.path))
            if request.url.path=='/v1/videos/search':return httpx.Response(200,json={'videos':[video]})
            if request.url.path=='/v1/videos/videos/11':return httpx.Response(200,json=video)
            if request.url.host=='videos.pexels.com':return httpx.Response(200,content=source.read_bytes(),headers={'Content-Type':'video/mp4'})
            if request.url.path=='/v1/search':return httpx.Response(200,json={'photos':[photo()]})
            if request.url.path=='/v1/photos/11':return httpx.Response(200,json=photo())
            if request.url.host=='images.pexels.com':return httpx.Response(200,content=pixels(),headers={'Content-Type':'image/png'})
            raise AssertionError('Unexpected explicit stock vector')
        self.engine(wire)

    def drive(self,session,limit=30):
        for _ in range(limit):
            if session['state']['status'] in {'ready','unresolved','needs_rights_review','needs_approval','recovery_required'}:return session
            session=self.step(session)
            self.stock.process()
        self.fail('Resolution failed to reach a bounded terminal/attention state')

    def library_asset(self):
        path=self.root/'library-owned.png';Image.new('RGB',(320,240),(45,85,140)).save(path)
        raw=ingest_media(self.config,path,'image/png','Xin chào source owner library.png',rights_confirmed=True,illustration=True)
        raw.update(explicit_fixture=True,source_type='internal_library',rights_status='owned',license='owner-created-synthetic-pixels',
            provider='explicit-local-owner-fixture',production_eligible=False,source_reference='fixture-owned:'+raw['id'])
        owner=self.store.create('Separate library fixture','','media')
        self.store.append_media(owner['id'],owner['revision'],raw)
        return raw

    def test_mock_stock_download_is_not_promoted_and_falls_back_to_owned_library_canonical(self):
        source=self.real_source();library=self.library_asset();self.mock_stock(source);record=self.plan();session=self.start(record)
        original=copy.deepcopy(self.project['document']['canonical_timeline']);raw_asr=copy.deepcopy(self.project['document']['media_analysis'])
        session=self.drive(session)
        self.assertEqual(session['state']['status'],'ready');self.assertGreaterEqual(len(self.wire_calls),3)
        item=next(iter(session['state']['items'].values()))
        self.assertEqual(item['selected_asset_id'],library['id'])
        self.assertTrue(any(value['status']=='RIGHTS_NOT_CLEARED' for value in item['attempts']))
        current=self.store.get(self.project['id']);stock=[a for a in current['document']['assets'] if a.get('source_type')=='stock']
        self.assertEqual(len(stock),1);self.assertEqual(stock[0]['rights_status'],'unknown');self.assertFalse(stock[0]['production_eligible'])
        self.assertEqual(current['document']['canonical_timeline'],original);self.assertEqual(current['document']['media_analysis'],raw_asr)
        request=Apply(revision=current['revision'],expected_resolution_version=session['version'],expected_timeline_version=1,
            acknowledged=True,request_key='source-library-apply-'+uuid.uuid4().hex)
        self.service.apply(self.project['id'],session['resolution_id'],request,actor='fixture-editor')
        applied=self.store.get(self.project['id']);self.assertIsNone(applied['approval'])
        clips=[c for t in applied['document']['canonical_timeline']['snapshot']['tracks'] if t['kind']=='broll' for c in t['clips']]
        self.assertTrue(clips);self.assertTrue(all(c['metadata']['native_asset_id']==library['id'] for c in clips))
        self.assertFalse(any(c['metadata']['publishing_allowed'] or c['metadata']['production_eligible'] for c in clips))

    def test_mock_unknown_rights_output_never_becomes_ready_when_no_safe_fallback_exists(self):
        source=self.real_source();self.mock_stock(source);record=self.plan();session=self.drive(self.start(record))
        self.assertEqual(session['state']['status'],'needs_rights_review')
        current=self.store.get(self.project['id'])
        request=Apply(revision=current['revision'],expected_resolution_version=session['version'],expected_timeline_version=1,
            acknowledged=True,request_key='source-unknown-apply-'+uuid.uuid4().hex)
        with self.assertRaisesRegex(WorkflowError,'NOT_READY'):
            self.service.apply(self.project['id'],session['resolution_id'],request,actor='fixture-editor')
        self.assertEqual(self.store.get(self.project['id']),current)

    def test_restart_and_concurrent_admission_keep_one_frozen_child_and_one_request_receipt(self):
        source=self.real_source();self.mock_stock(source);record=self.plan();session=self.start(record)
        session=self.step(session) # user assets exhausted; next transition admits search
        request=Step(revision=session['state']['expected']['revision'],expected_resolution_version=session['version'],
            request_key='source-resolution-concurrent-search-key')
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            replies=list(pool.map(lambda _:self.service.step(self.project['id'],session['resolution_id'],request,actor='fixture-editor'),range(3)))
        self.assertEqual(sum(not replay for _,replay in replies),1)
        self.assertEqual(len({digest(reply) for reply,_ in replies}),1)
        old=self.service.get(self.project['id'],session['resolution_id']);self.assertEqual(old['state']['status'],'waiting_provider')
        factory=self.stock.factories['pexels'];self.stock.close();self.generation.close()
        self.store=Store(self.root);self.stock=NativeStock(self.store,self.config,workspace_id=self.workspace,factories={'pexels':factory})
        self.generation=NativeGenerationWorker(NativeGenerationQueue(self.store,workspace_id=self.workspace),self.config)
        self.service=NativeSourceBrollResolution(self.store,self.config,self.stock,self.generation,workspace_id=self.workspace)
        self.addCleanup(self.stock.close);self.addCleanup(self.generation.close)
        self.assertEqual(self.service.get(self.project['id'],session['resolution_id']),old)
        self.assertEqual(self.service.step(self.project['id'],session['resolution_id'],request,actor='fixture-editor'),(replies[0][0],True))
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_stock_jobs').fetchone()[0],1)
        self.assertEqual(self.wire_calls,[])
        self.stock.process();current=self.service.get(self.project['id'],session['resolution_id']);current=self.step(current)
        self.assertEqual(len(next(iter(current['state']['items'].values()))['children']),2)

    def test_lost_import_reply_recovers_exact_owned_receipt_without_duplicate_bytes_or_dispatch(self):
        source=self.real_source();self.mock_stock(source);record=self.plan();session=self.start(record)
        for _ in range(12):
            if next(iter(session['state']['items'].values()))['phase']=='import_pending':break
            session=self.step(session);self.stock.process()
        self.assertEqual(next(iter(session['state']['items'].values()))['phase'],'import_pending')
        before=self.store.get(self.project['id']);calls=copy.deepcopy(self.wire_calls)
        with patch.object(self.service,'save_transition',side_effect=WorkflowError('EXPLICIT_LOST_IMPORT_REPLY')):
            with self.assertRaisesRegex(WorkflowError,'LOST_IMPORT_REPLY'):self.step(session)
        imported=self.store.get(self.project['id']);self.assertEqual(imported['revision'],before['revision']+1)
        raw=imported['document']['assets'][-1];sha=file_sha(self.root/'assets'/raw['id'])
        session=self.step(session)
        self.assertEqual(self.wire_calls,calls);self.assertEqual(file_sha(self.root/'assets'/raw['id']),sha)
        self.assertEqual(self.store.get(self.project['id']),imported)
        item=next(iter(session['state']['items'].values()));self.assertTrue(item['had_rights_unknown'])
        self.assertEqual(item['phase'],'choose');self.assertEqual(item['import_receipt']['asset_id'],raw['id'])
        self.assertEqual(len([a for a in imported['document']['assets'] if a.get('source_type')=='stock']),1)

    def test_apply_receipt_failure_rolls_back_canonical_and_session_then_exact_retry_is_safe(self):
        self.real_source();self.image();self.engine();session=self.step(self.start(self.plan()))
        before=self.store.get(self.project['id']);saved=self.service.get(self.project['id'],session['resolution_id'])
        request=Apply(revision=before['revision'],expected_resolution_version=session['version'],expected_timeline_version=1,
            acknowledged=True,request_key='source-resolution-atomic-apply-key')
        with patch.object(self.service,'persist',side_effect=WorkflowError('EXPLICIT_RECEIPT_WRITE_FAILURE')):
            with self.assertRaisesRegex(WorkflowError,'RECEIPT_WRITE_FAILURE'):
                self.service.apply(self.project['id'],session['resolution_id'],request,actor='fixture-editor')
        self.assertEqual(self.store.get(self.project['id']),before)
        self.assertEqual(self.service.get(self.project['id'],session['resolution_id']),saved)
        receipt,_=self.service.apply(self.project['id'],session['resolution_id'],request,actor='fixture-editor')
        self.assertEqual(receipt['status'],'applied_review_required');self.assertIsNone(self.store.get(self.project['id'])['approval'])
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):
            self.service.apply(self.project['id'],session['resolution_id'],request.model_copy(update={'replace_plan_clips':True}),actor='fixture-editor')

    def test_provider_configuration_and_physical_source_drift_do_not_admit_or_rewrite_history(self):
        source=self.real_source();self.mock_stock(source);session=self.start(self.plan());session=self.step(session)
        before=self.store.get(self.project['id']);history=self.service.get(self.project['id'],session['resolution_id'])
        self.stock.factories['pexels'].credential.api_key='changed-explicit-test-key'
        with self.assertRaises(WorkflowError):self.step(session)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.service.get(self.project['id'],session['resolution_id']),history)
        self.stock.factories['pexels'].credential.api_key='explicit-source-resolution-fixture'
        original=source.read_bytes();source.write_bytes(b'EXPLICIT CORRUPT OWNED TEST MEDIA')
        try:
            with self.assertRaises(WorkflowError):self.step(session)
            self.assertEqual(self.store.get(self.project['id']),before)
        finally:source.write_bytes(original)
        self.assertEqual(self.wire_calls,[])

    def test_server_configured_priority_selects_library_before_user_asset_and_freezes_all_required_tiers(self):
        self.real_source();user=self.image();library=self.library_asset();self.engine()
        priority=['internal_library','user_asset','licensed_stock','ai_video','ai_image']
        self.project=broll.create(self.store,self.config,self.project['id'],self.project['revision'],{'expected_version':1},
            resolver_context=self.service.planning_context(resolver_priority=priority))
        record=self.project['document']['source_broll_plans'][-1];self.assertEqual(record['plan']['configuration']['resolver_priority'],priority)
        session=self.start(record);self.assertEqual(session['snapshot']['priority'],priority)
        self.assertEqual(session['snapshot']['unsupported_resolution_tiers'],[])
        session=self.step(session);session=self.step(session)
        self.assertEqual(session['state']['status'],'ready')
        self.assertEqual(next(iter(session['state']['items'].values()))['selected_asset_id'],library['id'])
        self.assertNotEqual(library['id'],user['id']);self.assertIsNone(self.store.get(self.project['id'])['approval'])
        before=self.store.get(self.project['id'])
        for invalid in (['user_asset'],['user_asset']*5,['motion_graphic',*priority]):
            with self.assertRaisesRegex(WorkflowError,'RESOLVER_CONTEXT_INVALID'):
                broll.create(self.store,self.config,self.project['id'],before['revision'],{'expected_version':1},
                    resolver_context=self.service.planning_context(resolver_priority=invalid))
        self.assertEqual(self.store.get(self.project['id']),before)

    def generation_engine(self):
        from services.windows_native.generation_registry import GenerationFactory,GenerationCredential
        self.engine();self.clock=[time.time()];self.generation.close();self.generation_calls=[]
        def wire(request):raise AssertionError('No bridge/network request in explicit generation fixture')
        factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token='explicit-source-resolution-generation-fixture-32',
            enabled=True),owner_enabled=True,transport=httpx.MockTransport(wire))
        self.generation=NativeGenerationWorker(NativeGenerationQueue(self.store,workspace_id=self.workspace,factory=factory,clock=lambda:self.clock[0]),self.config)
        self.service=NativeSourceBrollResolution(self.store,self.config,self.stock,self.generation,workspace_id=self.workspace)
        self.addCleanup(self.generation.close)

    def generation_admission(self):
        session=self.start(self.plan())
        for _ in range(10):
            if next(iter(session['state']['items'].values()))['phase']=='generation_wait':break
            session=self.step(session)
        self.assertEqual(next(iter(session['state']['items'].values()))['phase'],'generation_wait')
        return session

    def test_unknown_generation_outcome_requires_explicit_child_recovery_and_never_resubmits(self):
        from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider
        from services.windows_native.generation_models import GenerationRecovery
        self.real_source();self.generation_engine();session=self.generation_admission()
        async def unknown(adapter,payload):self.generation_calls.append('create');raise TimeoutError('EXPLICIT UNKNOWN OUTCOME VECTOR')
        with patch.object(ComfyUIBridgeGenerationProvider,'generate',unknown):self.generation.process()
        session=self.step(session);self.assertEqual(session['state']['status'],'recovery_required')
        unchanged=self.store.get(self.project['id']);child=next(iter(session['state']['items'].values()))['children'][-1]
        with self.assertRaisesRegex(WorkflowError,'ATTENTION_REQUIRED'):self.step(session)
        self.assertEqual(self.generation_calls,['create']);self.assertEqual(self.store.get(self.project['id']),unchanged)
        self.generation.queue.recover(self.project['id'],child['id'],GenerationRecovery(expected_fingerprint=child['fingerprint'],
            acknowledged=True,request_key='explicit-source-child-read-recovery-key'),actor='fixture-editor')
        session=self.step(session);self.assertEqual(session['state']['status'],'waiting_provider')
        self.assertEqual(len(next(iter(session['state']['items'].values()))['children']),1)
        self.assertEqual(self.generation_calls,['create']);self.assertEqual(self.store.get(self.project['id']),unchanged)
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_generation_jobs').fetchone()[0],1)

    def test_fixture_generated_image_is_decoded_imported_but_unknown_rights_force_video_fallback(self):
        from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider
        from services.windows_native.generation_models import GenerationCreate
        from services.windows_native.tests.test_generation_media import NativeGenerationMediaTests
        self.real_source();self.generation_engine();session=self.generation_admission();before=copy.deepcopy(self.project['document']['canonical_timeline'])
        binding=next(iter(session['state']['items'].values()))['children'][-1];job=self.generation.get(self.project['id'],binding['id'])
        def pixels(size=(360,640)):
            buffer=io.BytesIO();Image.new('RGB',size,(45,85,140)).save(buffer,format='PNG');return buffer.getvalue()
        helper=SimpleNamespace(service=self.generation.queue,factory=self.generation.queue.factory,
            payload=GenerationCreate.model_validate({**job['snapshot']['request'],'request_key':'explicit-output-fixture-request-key'}),pixels=pixels)
        output=replace(NativeGenerationMediaTests.output(helper,job,pixels(),width=360,height=640),orientation='portrait')
        async def generate(adapter,payload):
            self.generation_calls.append('create')
            await adapter.on_job({'schema_version':'comfyui-generation-observation-v1','phase':'polled','provider_job_id':output.provider_job_id,
                'workspace_id':self.workspace,'workflow_id':job['snapshot']['selection']['workflow_id'],
                'workflow_version':job['snapshot']['selection']['workflow_version'],'status':'succeeded','progress':100})
            return output
        with patch.object(ComfyUIBridgeGenerationProvider,'generate',generate):self.generation.process()
        self.assertEqual(self.generation.get(self.project['id'],binding['id'])['status'],'succeeded')
        session=self.step(session);self.assertEqual(next(iter(session['state']['items'].values()))['phase'],'import_pending')
        session=self.step(session);session=self.step(session)
        value=next(iter(session['state']['items'].values()));self.assertEqual(value['tier_index'],4);self.assertTrue(value['had_rights_unknown'])
        self.assertEqual(value['attempts'][-1]['status'],'RIGHTS_NOT_CLEARED')
        current=self.store.get(self.project['id']);raw=current['document']['assets'][-1]
        self.assertEqual(raw['source_type'],'ai_generated');self.assertEqual(raw['rights_status'],'unknown');self.assertTrue(raw['explicit_fixture'])
        self.assertFalse(raw['production_eligible']);self.assertEqual(file_sha(self.root/'assets'/raw['id']),raw['sha256'])
        self.assertEqual(current['document']['canonical_timeline'],before);self.assertIsNone(current['approval'])
        self.assertEqual(self.generation_calls,['create']);self.assertEqual(len(self.generation.queue.costs.summary(self.project['id'])['records']),1)
        session=self.step(session);newbinding=next(iter(session['state']['items'].values()))['children'][-1]
        self.assertNotEqual(newbinding['id'],binding['id']);self.assertEqual(self.generation.get(self.project['id'],newbinding['id'])['snapshot']['request']['parameters']['modality'],'video')


class ReviewedDerivativeResolutionTests(unittest.TestCase):
    def test_reviewed_original_bytes_are_immutable_and_derivative_never_claims_new_asset_vision(self):
        from services.windows_native.tests.test_source_broll_vision import SourceBrollVisionTests
        v=SourceBrollVisionTests('test_reviewed_mock_retains_lineage_without_changing_semantic_scores_or_source_timeline')
        v.setUp();self.addCleanup(v.tearDown);self.addCleanup(v.doCleanups)
        row=v.complete();v.create(row);record=copy.deepcopy(v.project['document']['source_broll_plans'][-1])
        original=copy.deepcopy(v.project);stock=NativeStock(v.store,v.config,workspace_id=v.workspace)
        generation=NativeGenerationWorker(NativeGenerationQueue(v.store,workspace_id=v.workspace),v.config)
        self.addCleanup(stock.close);self.addCleanup(generation.close)
        service=NativeSourceBrollResolution(v.store,v.config,stock,generation,workspace_id=v.workspace,official_vision=lambda:v.official)
        request=Create(revision=v.project['revision'],expected_timeline_version=1,media_plan_id=record['plan']['media_plan_id'],
            expected_plan_version=record['plan']['version'],expected_plan_sha256=record['sha256'],
            item_ids=[record['plan']['items'][0]['media_plan_item_id']],fixture_acknowledged=True,
            request_key='reviewed-source-resolution-derivative-key')
        session,replay=service.create(v.project['id'],request,actor='fixture-editor');self.assertFalse(replay)
        current=v.store.get(v.project['id']);self.assertEqual(current['document']['source_broll_plans'][-2],record)
        self.assertEqual(current['document']['canonical_timeline'],original['document']['canonical_timeline'])
        self.assertEqual(current['document']['media_analysis'],original['document']['media_analysis']);self.assertEqual(len(v.calls),1)
        derivative=session['snapshot']['plan'];p=derivative['provenance'];history=p['inherited_reviewed_source_history']
        self.assertEqual(history['original_plan'],record['plan']);self.assertEqual(history['original_plan_sha256'],record['sha256'])
        self.assertFalse(history['new_asset_semantic_review_performed']);self.assertTrue(history['source_intent_recommendation_only'])
        self.assertNotIn('reviewed_vision',p);self.assertNotIn('reviewed_input',p);self.assertFalse(p['semantic_vision_used_for_new_assets'])
        self.assertIsNone(derivative['vision_analysis_id']);self.assertNotEqual(derivative['media_plan_id'],record['plan']['media_plan_id'])
        self.assertEqual(derivative['items'][0]['broll'],record['plan']['items'][0]['broll'])
        service.step(v.project['id'],session['resolution_id'],Step(revision=current['revision'],expected_resolution_version=1,
            request_key='reviewed-source-resolution-step-key'),actor='fixture-editor')
        session=service.get(v.project['id'],session['resolution_id']);self.assertEqual(session['state']['status'],'ready')
        current=v.store.get(v.project['id']);self.assertEqual(current['document']['source_broll_plans'][-3],record)
        self.assertEqual(v.official.get(v.project['id'],row['vision_id']),row);self.assertEqual(len(v.calls),1)
        self.assertIsNone(current['approval'])
        self.assertEqual(service.create(v.project['id'],request,actor='fixture-editor'),(session,True))


if __name__=='__main__':unittest.main()
