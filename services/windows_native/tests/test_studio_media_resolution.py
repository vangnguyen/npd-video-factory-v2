"""Actual scoped HTTP/SQLite admission; explicit stock wire fixtures, no GPU/UAT."""
import json,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import httpx
from services.windows_native.tests import test_studio_media_planner as helpers
from services.windows_native.tests.test_stock import photo,pixels
from services.windows_native.server import Handler
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.studio_media_resolution import NativeStudioMediaResolution,Generate,Search
from services.windows_native.generation_registry import GenerationFactory,GenerationCredential
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_worker import NativeGenerationWorker
from services.windows_native.stock import NativeStock
from services.windows_native.stock_registry import StockFactory,StockCredential
from services.windows_native.costs import CostLedger


class StudioMediaResolutionTests(unittest.TestCase):
    setUp=helpers.StudioMediaPlannerTests.setUp
    tearDown=helpers.StudioMediaPlannerTests.tearDown
    stop_server=helpers.StudioMediaPlannerTests.stop_server
    start_server=helpers.StudioMediaPlannerTests.start_server
    request=helpers.StudioMediaPlannerTests.request
    account=helpers.StudioMediaPlannerTests.account
    base=helpers.StudioMediaPlannerTests.base
    create=helpers.StudioMediaPlannerTests.create
    action=helpers.StudioMediaPlannerTests.action

    def configured(self,kind='generation'):
        self.calls=[]
        def wire(request):
            self.calls.append(str(request.url))
            if request.url.path=='/v1/search':return httpx.Response(200,json={'photos':[photo()]})
            if request.url.path=='/v1/photos/11':return httpx.Response(200,json=photo())
            if request.url.host=='images.pexels.com':return httpx.Response(200,content=pixels(),headers={'Content-Type':'image/png'})
            raise AssertionError('No generation dispatch in admission tests')
        transport=httpx.MockTransport(wire)
        if kind=='generation':
            factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token='explicit-resolution-fixture-token-32',enabled=True),owner_enabled=True,transport=transport)
            self.server.generation=NativeGenerationWorker(NativeGenerationQueue(self.server.store,workspace_id=self.server.publications.workspace_id,factory=factory),self.config)
        else:
            factory=StockFactory('pexels',StockCredential(api_key='explicit-resolution-stock-fixture',enabled=True),owner_enabled=True,transport=transport)
            self.server.stock=NativeStock(self.server.store,self.config,workspace_id=self.server.publications.workspace_id,factories={'pexels':factory})
        self.server.media_resolution=NativeStudioMediaResolution(self.server.media_planner,self.server.generation,self.server.stock)

    def resolve_path(self,record,action):return self.base()+'/'+record['plan']['media_plan_id']+'/resolve/'+action
    def body(self,record,**extra):return {**self.action(record),'shot_id':record['plan']['items'][0]['shot_id'],'fixture_acknowledged':True,'request_key':'explicit-resolution-request-key-01',**extra}
    def gen_plan(self):self.configured();return self.create({'resolver_priority':['ai_image','user_asset']})
    def page_path(self):return '/api/projects/'+self.project['id']+'/media-resolutions'
    def count(self,table):
        with self.server.store.transaction() as con:return con.execute('SELECT count(*) FROM '+table).fetchone()[0]

    def test_generation_is_atomically_bound_to_saved_plan_and_replays_exactly_after_project_edit(self):
        self.account('editor');record=self.gen_plan();before=self.server.store.get(self.project['id']);body=self.body(record,seed=19)
        status,value,_=self.request('POST',self.resolve_path(record,'generate'),body);self.assertEqual(status,200,value)
        binding,child=value['binding'],value['child'];self.assertEqual(child['status'],'queued');self.assertEqual(child['snapshot']['request']['parameters']['prompt'],record['plan']['items'][0]['generation_prompt'])
        self.assertEqual(binding['plan_sha256'],record['sha256']);self.assertEqual(binding['child_id'],child['generation_id']);self.assertEqual(self.count('native_media_resolutions'),1)
        self.assertEqual(self.server.store.get(self.project['id'])['document'],before['document']);self.assertEqual(self.calls,[]);self.assertEqual(CostLedger(self.server.store).summary(self.project['id'])['attempted_operations'],0)
        self.server.store.mutate_shots(self.project['id'],before['revision'],{'type':'update','shot_id':binding['shot_id'],'values':{'visual':'Later explicit edit fixture'}})
        status,replay,_=self.request('POST',self.resolve_path(record,'generate'),body);self.assertEqual(status,200,replay);self.assertTrue(replay.pop('idempotent_replay'))
        value.pop('idempotent_replay');self.assertEqual(replay,value);self.assertEqual(self.count('native_generation_jobs'),1)
        status,error,_=self.request('POST',self.resolve_path(record,'generate'),{**body,'seed':20});self.assertEqual(status,409);self.assertEqual(error['code'],'STUDIO_MEDIA_RESOLUTION_IDEMPOTENCY_CONFLICT')

    def test_concurrent_duplicate_admission_rolls_back_the_losing_child(self):
        record=self.gen_plan();payload=Generate.model_validate(self.body(record));service=self.server.media_resolution;barrier=threading.Barrier(2);original=self.server.generation.queue.create
        def before_admission(*args,**kwargs):barrier.wait(timeout=10);return original(*args,**kwargs)
        with patch.object(self.server.generation.queue,'create',side_effect=before_admission),ThreadPoolExecutor(max_workers=2) as pool:
            pending=[pool.submit(service.create,self.project['id'],record['plan']['media_plan_id'],payload,actor='explicit-concurrent-fixture') for _ in range(2)]
            results=[value.result(timeout=20) for value in pending]
        self.assertEqual({value[0]['binding']['resolution_id'] for value in results}, {results[0][0]['binding']['resolution_id']})
        self.assertEqual(sorted(value[1] for value in results),[False,True]);self.assertEqual(self.count('native_generation_jobs'),1);self.assertEqual(self.count('native_media_resolutions'),1)
        self.assertEqual(self.count('native_generation_events'),1);self.assertEqual(self.calls,[])

    def test_plan_race_inside_admission_rolls_back_job_and_event(self):
        record=self.gen_plan();original=self.server.media_planner.bound;count=[0]
        def changing(*args):
            count[0]+=1
            if count[0]==2:raise WorkflowError('EXPLICIT_FIXTURE_PLAN_RACE')
            return original(*args)
        with patch.object(self.server.media_planner,'bound',side_effect=changing):
            status,error,_=self.request('POST',self.resolve_path(record,'generate'),self.body(record))
        self.assertEqual(status,409);self.assertEqual(error['code'],'EXPLICIT_FIXTURE_PLAN_RACE');self.assertEqual(self.count('native_generation_jobs'),0)
        self.assertEqual(self.count('native_generation_events'),0);self.assertEqual(self.count('native_media_resolutions'),0);self.assertEqual(self.calls,[])

    def test_stock_callback_rollback_and_existing_asset_refuse_without_dispatch(self):
        self.configured('stock');record=self.create({'resolver_priority':['licensed_stock','user_asset'],'preferred_media_type':'image'});original=self.server.media_planner.bound;calls=[0]
        def race(*args):
            calls[0]+=1
            if calls[0]==2:raise WorkflowError('EXPLICIT_FIXTURE_STOCK_PLAN_RACE')
            return original(*args)
        with patch.object(self.server.media_planner,'bound',side_effect=race):
            self.assertEqual(self.request('POST',self.resolve_path(record,'search'),self.body(record,provider='pexels'))[0],409)
        self.assertEqual(self.count('native_stock_jobs'),0);self.assertEqual(self.count('native_stock_events'),0);self.assertEqual(self.count('native_media_resolutions'),0)
        selected=self.create({'resolver_priority':['user_asset']})
        status,error,_=self.request('POST',self.resolve_path(selected,'generate'),self.body(selected));self.assertEqual(status,409)
        self.assertEqual(error['code'],'STUDIO_MEDIA_RESOLUTION_EXISTING_ASSET_AVAILABLE');self.assertEqual(self.calls,[])

    def test_stock_resolution_download_import_and_replan_keep_unknown_rights_and_no_auto_timeline(self):
        self.configured('stock');record=self.create({'resolver_priority':['licensed_stock','user_asset'],'preferred_media_type':'image'})
        status,search,_=self.request('POST',self.resolve_path(record,'search'),self.body(record,provider='pexels'));self.assertEqual(status,200,search)
        self.assertEqual(self.calls,[]);self.server.stock.process();search=self.request('GET',self.page_path()+'/'+search['binding']['resolution_id'])[1]
        child=search['child'];candidate=child['result']['candidates'][0]
        body={**self.action(record),'parent_resolution_id':search['binding']['resolution_id'],'expected_result_sha256':child['result_sha256'],
            'candidate_id':candidate['candidate_id'],'expected_candidate_sha256':digest(candidate),'fixture_acknowledged':True,'request_key':'explicit-resolution-download-key'}
        status,download,_=self.request('POST',self.resolve_path(record,'download'),body);self.assertEqual(status,200,download);self.server.stock.process()
        download=self.request('GET',self.page_path()+'/'+download['binding']['resolution_id'])[1];self.assertEqual(download['child']['status'],'succeeded');before=self.server.store.shot_view(self.project['id'])
        child=download['child'];asset=child['result']['asset'];path=self.page_path()+'/'+download['binding']['resolution_id']+'/import'
        body={'revision':before['revision'],'expected_binding_sha256':download['binding_sha256'],'expected_fingerprint':child['request_fingerprint'],
            'expected_asset_sha256':asset['sha256'],'acknowledged':True,'request_key':'explicit-resolution-import-key'}
        self.account('editor');status,attached,_=self.request('POST',path,body);self.assertEqual(status,200,attached);self.assertTrue(attached['replan_required'])
        current=self.server.store.shot_view(self.project['id']);self.assertEqual(current['shot_timeline']['snapshot'],before['shot_timeline']['snapshot']);self.assertIsNone(current['approval'])
        self.assertEqual(current['revision'],before['revision']+1);self.assertEqual(asset['rights_status'],'unknown');self.assertFalse(asset['production_eligible']);self.assertEqual(len(self.calls),3)
        status,replay,_=self.request('POST',path,body);self.assertEqual(status,200,replay);self.assertTrue(replay['import_receipt']['idempotent_replay']);self.assertEqual(self.server.store.shot_view(self.project['id']),current)
        new=self.create({'resolver_priority':['licensed_stock','user_asset'],'preferred_media_type':'image'})
        imported=[candidate for item in new['plan']['items'] for candidate in item['candidates'] if candidate['asset_id']==asset['id']]
        self.assertTrue(imported);self.assertTrue(all(not value['selectable'] for value in imported));self.assertFalse(attached['automatic_timeline_apply'])

    def test_role_csrf_origin_and_client_graph_guards_preserve_existing_stock_permissions(self):
        record=self.gen_plan();path=self.resolve_path(record,'generate');body=self.body(record)
        self.account('editor');self.assertEqual(self.request('POST',path,body,{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('POST',path,body,{'Origin':'http://hostile.example'})[0],403)
        for field in ['workflow','graph','provider_url','asset','estimated_cost_vnd']:
            self.assertEqual(self.request('POST',path,{**body,field:'forged'})[0],400)
        for role in ['editor','reviewer','viewer']:
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized stock body was read')):
                self.assertEqual(self.request('POST',self.resolve_path(record,'search'),{})[0],403)
                self.assertEqual(self.request('POST',self.resolve_path(record,'download'),{})[0],403)
                if role!='editor':self.assertEqual(self.request('POST',path,body)[0],403)
            self.assertEqual(self.request('GET',self.page_path())[0],200)
        self.assertEqual(self.count('native_generation_jobs'),0);self.assertEqual(self.calls,[])

    def test_plan_hash_revision_provider_and_finite_budget_changes_refuse_before_admission(self):
        record=self.gen_plan();body=self.body(record);path=self.resolve_path(record,'generate')
        for change in [{'revision':body['revision']-1},{'expected_plan_sha256':'0'*64},{'expected_plan_version':9},{'fixture_acknowledged':False}]:
            self.assertIn(self.request('POST',path,{**body,**change})[0],[400,409])
        current=self.server.store.get(self.project['id']);CostLedger(self.server.store).set_budget(current['id'],current['revision'],'1000')
        self.assertEqual(self.request('POST',path,{**body,'revision':current['revision']+1})[0],409)
        new=self.create({'resolver_priority':['ai_image']});status,error,_=self.request('POST',self.resolve_path(new,'generate'),self.body(new))
        self.assertEqual(status,409);self.assertEqual(error['code'],'STUDIO_MEDIA_RESOLUTION_BUDGET_APPROVAL_REQUIRED');self.assertEqual(self.count('native_generation_jobs'),0)

    def test_resolution_scope_immutable_hash_and_child_binding_are_checked(self):
        record=self.gen_plan();status,value,_=self.request('POST',self.resolve_path(record,'generate'),self.body(record));self.assertEqual(status,200,value)
        foreign=self.server.store.create('Foreign fixture','No production');identity=value['binding']['resolution_id']
        self.assertEqual(self.request('GET','/api/projects/'+foreign['id']+'/media-resolutions/'+identity)[0],404)
        with self.server.store.transaction() as con:
            forged={**value['binding'],'child_request_sha256':'0'*64}
            con.execute('UPDATE native_media_resolutions SET binding_json=?,binding_sha256=? WHERE resolution_id=?',(json.dumps(forged),digest(forged),identity))
        status,error,_=self.request('GET',self.page_path()+'/'+identity);self.assertEqual(status,409);self.assertEqual(error['code'],'STUDIO_MEDIA_RESOLUTION_CHILD_CHANGED')

    def test_stock_download_rejects_a_search_from_a_revised_plan_without_a_second_provider_request(self):
        self.configured('stock');record=self.create({'resolver_priority':['licensed_stock'],'preferred_media_type':'image'})
        status,parent,_=self.request('POST',self.resolve_path(record,'search'),self.body(record,provider='pexels'));self.assertEqual(status,200,parent);self.server.stock.process()
        parent=self.request('GET',self.page_path()+'/'+parent['binding']['resolution_id'])[1];candidate=parent['child']['result']['candidates'][0]
        item=record['plan']['items'][0];status,page,_=self.request('POST',self.base()+'/'+record['plan']['media_plan_id']+'/revise',
            {**self.action(record),'shot_id':item['shot_id'],'strategy':'stock_image','query':'Different saved query','generation_prompt':item['generation_prompt']});self.assertEqual(status,200,page)
        latest=page['items'][-1];status,error,_=self.request('POST',self.resolve_path(latest,'download'),{**self.action(latest),'parent_resolution_id':parent['binding']['resolution_id'],
            'expected_result_sha256':parent['child']['result_sha256'],'candidate_id':candidate['candidate_id'],'expected_candidate_sha256':digest(candidate),
            'fixture_acknowledged':True,'request_key':'explicit-revised-plan-download-key'})
        self.assertEqual(status,409);self.assertEqual(error['code'],'STUDIO_MEDIA_RESOLUTION_PARENT_CHANGED');self.assertEqual(len(self.calls),1);self.assertEqual(self.count('native_stock_jobs'),1)

    def test_missing_generation_provider_records_not_configured_without_fabricating_a_result(self):
        record=self.create();item=record['plan']['items'][0]
        status,page,_=self.request('POST',self.base()+'/'+record['plan']['media_plan_id']+'/revise',{**self.action(record),'shot_id':item['shot_id'],
            'strategy':'ai_image','query':'Explicit unavailable provider','generation_prompt':'Explicit unavailable illustration'});self.assertEqual(status,200,page);latest=page['items'][-1]
        status,value,_=self.request('POST',self.resolve_path(latest,'generate'),self.body(latest,external_acknowledged=True,fixture_acknowledged=False));self.assertEqual(status,200,value)
        self.assertEqual(value['child']['status'],'not_configured');self.assertIsNone(value['child']['result']);self.assertIsNone(self.server.generation.process())
        self.assertEqual(CostLedger(self.server.store).summary(self.project['id'])['attempted_operations'],0)

    def test_generation_video_over_provider_limit_is_not_silently_shortened(self):
        self.configured();current=self.server.store.shot_view(self.project['id']);shot=current['shot_timeline']['shots'][0]
        self.server.store.mutate_shots(self.project['id'],current['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'duration':31}})
        record=self.create({'resolver_priority':['ai_video']});self.assertEqual(record['plan']['items'][0]['duration_seconds'],31)
        status,error,_=self.request('POST',self.resolve_path(record,'generate'),self.body(record));self.assertEqual(status,400);self.assertEqual(error['code'],'STUDIO_MEDIA_RESOLUTION_VIDEO_DURATION_UNSUPPORTED')
        self.assertEqual(self.count('native_generation_jobs'),0);self.assertEqual(self.calls,[])
