"""Actual Native SQLite/human HTTP and owned image bytes; no external AI/UAT."""
import json,uuid,unittest
from unittest.mock import patch
from PIL import Image
import httpx
from services.windows_native.tests import test_access_http as fixture
from services.windows_native.server import Handler
from services.windows_native.contracts import file_sha,digest
from services.windows_native.generation_registry import GenerationFactory,GenerationCredential
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_worker import NativeGenerationWorker


class StudioMediaPlannerTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def base(self,project=None):return '/api/projects/'+(project or self.project['id'])+'/media-plans'

    def create(self,options=None):
        current=self.server.store.shot_view(self.project['id'])
        status,value,_=self.request('POST',self.base(),{'revision':current['revision'],'expected_timeline_version':current['shot_timeline']['version'],'options':options or {}})
        self.assertEqual(status,200,value);self.page=value;return value['items'][-1]

    def action(self,record):
        return {'revision':self.server.store.get(self.project['id'])['revision'],'expected_plan_version':record['plan']['version'],'expected_plan_sha256':record['sha256']}

    def image(self,**extra):
        path=self.config.data_root/'assets'/(uuid.uuid4().hex+'.jpg');Image.new('RGB',(320,240),(15,140,220)).save(path)
        asset={'id':path.name,'sha256':file_sha(path),'kind':'image','filename':'Technology AI educational alternative.jpg','rights_confirmed':True,'illustration':True,**extra}
        current=self.server.store.get(self.project['id']);self.server.store.append_media(self.project['id'],current['revision'],asset);return asset

    def test_create_saves_frozen_real_inputs_keeps_timeline_and_deduplicates_without_provider_calls(self):
        self.account('editor');before=self.server.store.shot_view(self.project['id']);record=self.create();plan=record['plan'];after=self.server.store.shot_view(self.project['id'])
        self.assertEqual(before['shot_timeline']['snapshot'],after['shot_timeline']['snapshot']);self.assertEqual(before['shot_timeline']['version'],after['shot_timeline']['version'])
        self.assertNotIn('canonical_timeline',after['document']);self.assertIsNone(after['approval']);self.assertEqual(after['revision'],before['revision']+1)
        self.assertEqual(plan['input']['script_sha256'],digest(before['document']['proposal']));self.assertEqual(plan['input']['assets'][self.asset['id']]['sha256'],file_sha(self.config.data_root/'assets'/self.asset['id']))
        self.assertTrue(record['input_current']);self.assertTrue(all(value['estimated_cost_vnd'] is None for value in plan['items']));self.assertFalse(plan['semantic_vision_used'])
        self.assertTrue(all(value['confidence'] is None for item in plan['items'] for value in item['candidates']));self.assertEqual(plan['external_dispatches'],0);self.assertEqual(self.pipeline.calls,0)
        self.assertTrue(all(value['status']=='NOT_CONFIGURED' for value in plan['input']['provider_availability']['generation']['items']))
        self.assertEqual(self.create(),record);self.assertEqual(self.server.store.shot_view(self.project['id']),after)

    def test_select_and_apply_mutate_the_same_shot_snapshot_and_legacy_projections_atomically(self):
        self.account('editor');other=self.image();record=self.create();shot=record['plan']['items'][0]['shot_id'];before=self.server.store.shot_view(self.project['id'])
        status,page,_=self.request('POST',self.base()+'/'+record['plan']['media_plan_id']+'/select',{**self.action(record),'shot_id':shot,'asset_id':other['id'],'expected_asset_sha256':other['sha256']})
        self.assertEqual(status,200,page);selected=page['items'][-1];self.assertEqual(selected['plan']['version'],2)
        self.assertEqual(self.server.store.shot_view(self.project['id'])['shot_timeline']['snapshot'],before['shot_timeline']['snapshot'])
        status,applied,_=self.request('POST',self.base()+'/'+selected['plan']['media_plan_id']+'/apply',{**self.action(selected),'acknowledged':True,'shot_ids':[shot]})
        self.assertEqual(status,200,applied);current=self.server.store.shot_view(self.project['id']);cards=current['shot_timeline']['shots']
        self.assertEqual(cards[0]['asset_id'],other['id']);self.assertEqual(cards[1:],before['shot_timeline']['shots'][1:]);self.assertEqual(current['document']['scene_media'][0]['asset_id'],other['id'])
        receipt=applied['items'][-1]['plan']['application'];self.assertEqual(receipt['timeline_sha256'],current['document']['canonical_timeline']['sha256']);self.assertFalse(receipt['automatic_render'])
        self.assertEqual(receipt['scope']['voice_dependency_shot_ids'],[]);self.assertEqual(receipt['scope']['visual_dependency_shot_ids'],[shot]);self.assertIsNone(current['approval']);self.assertEqual(current['jobs'],[])
        self.assertFalse(applied['items'][-1]['input_current']);self.assertEqual(self.pipeline.calls,0)
        self.assertEqual(self.request('POST',self.base()+'/'+selected['plan']['media_plan_id']+'/apply',{**self.action(selected),'acknowledged':True,'shot_ids':[shot]})[0],409)

    def test_unknown_restricted_and_changed_bytes_cannot_be_selected_or_applied(self):
        self.account('editor');unknown=self.image(source_type='stock',rights_status='unknown',license='unknown',provider='explicit-fixture',production_eligible=False)
        record=self.create();item=record['plan']['items'][0];self.assertFalse(next(value for value in item['candidates'] if value['asset_id']==unknown['id'])['selectable'])
        body={**self.action(record),'shot_id':item['shot_id'],'asset_id':unknown['id'],'expected_asset_sha256':unknown['sha256']};before=self.server.store.get(self.project['id'])
        self.assertEqual(self.request('POST',self.base()+'/'+record['plan']['media_plan_id']+'/select',body)[0],409);self.assertEqual(self.server.store.get(self.project['id']),before)
        (self.config.data_root/'assets'/self.asset['id']).write_bytes(b'changed isolated fixture bytes')
        self.assertEqual(self.request('POST',self.base()+'/'+record['plan']['media_plan_id']+'/apply',{**self.action(record),'acknowledged':True,'shot_ids':[item['shot_id']]})[0],409)
        status,page,_=self.request('GET',self.base());self.assertEqual(status,200);self.assertFalse(page['items'][0]['input_current']);self.assertEqual(page['unavailable_reason'],'SOURCE_MEDIA_CHANGED_OR_MISSING')
        self.assertEqual(self.server.store.get(self.project['id']),before)

    def test_revision_plan_hash_input_and_foreign_identity_fail_without_mutation(self):
        self.account('editor');record=self.create();item=record['plan']['items'][0];path=self.base()+'/'+record['plan']['media_plan_id']+'/select'
        body={**self.action(record),'shot_id':item['shot_id'],'asset_id':self.asset['id'],'expected_asset_sha256':self.asset['sha256']};before=self.server.store.get(self.project['id'])
        for change in [{'revision':before['revision']-1},{'expected_plan_version':9},{'expected_plan_sha256':'0'*64},{'expected_asset_sha256':'0'*64}]:self.assertEqual(self.request('POST',path,{**body,**change})[0],409)
        self.assertEqual(self.server.store.get(self.project['id']),before)
        other=self.server.store.create('Foreign scope','No provider');self.assertEqual(self.request('POST',self.base(other['id'])+'/'+record['plan']['media_plan_id']+'/select',{**body,'revision':other['revision']})[0],404)
        current=self.server.store.mutate_shots(self.project['id'],before['revision'],{'type':'update','shot_id':item['shot_id'],'values':{'visual':'Changed canonical storyboard'}})
        self.assertEqual(self.request('POST',path,{**body,'revision':current['revision']})[0],409);self.assertFalse(self.request('GET',self.base())[1]['items'][0]['input_current'])

    def test_protected_provider_availability_and_budget_are_saved_without_network_or_authority(self):
        self.account('editor');factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token='explicit-media-plan-fixture-token-32',enabled=True),owner_enabled=True,
            transport=httpx.MockTransport(lambda request:(_ for _ in ()).throw(AssertionError('Planner must not call providers'))))
        self.server.generation=NativeGenerationWorker(NativeGenerationQueue(self.server.store,workspace_id=self.server.publications.workspace_id,factory=factory),self.config)
        current=self.server.store.get(self.project['id']);CostLedger=__import__('services.windows_native.costs',fromlist=['CostLedger']).CostLedger;CostLedger(self.server.store).set_budget(self.project['id'],current['revision'],'0')
        record=self.create({'resolver_priority':['ai_image','user_asset'],'aspect_ratio':'4:5'});plan=record['plan']
        self.assertEqual(plan['input']['budget']['remaining_known_budget_vnd'],'0');self.assertFalse(plan['input']['budget']['planning_authorizes_payment'])
        self.assertTrue(all(item['strategy']=='ai_image' and item['estimated_cost_vnd'] is None and item['needs_approval'] and item['status']=='requires_provider' and item['target_aspect_ratio']=='4:5' for item in plan['items']))
        self.assertTrue(all(item['fallback']==['user_asset'] for item in plan['items']));self.assertEqual(self.pipeline.calls,0)
        current=self.server.store.get(self.project['id']);self.assertEqual(current['jobs'],[]);self.assertEqual(self.server.generation.page(self.project['id'])['total'],0)
        self.server.generation=NativeGenerationWorker(NativeGenerationQueue(self.server.store,workspace_id=self.server.publications.workspace_id),self.config)
        self.assertFalse(self.request('GET',self.base())[1]['items'][0]['input_current'])

    def test_revise_query_is_versioned_and_cannot_claim_motion_graphic_implemented(self):
        self.account('editor');record=self.create();item=record['plan']['items'][0]
        status,page,_=self.request('POST',self.base()+'/'+record['plan']['media_plan_id']+'/revise',{**self.action(record),'shot_id':item['shot_id'],'strategy':'motion_graphic','query':'AI technology explanation','generation_prompt':'Original diagram, Vietnamese typography'})
        self.assertEqual(status,200,page);updated=page['items'][0]['plan'];self.assertEqual(updated['version'],2);self.assertEqual(updated['items'][0]['status'],'requires_implementation')
        self.assertIsNone(updated['items'][0]['selected_asset_id']);self.assertEqual(updated['items'][0]['query'],'AI technology explanation')
        self.assertEqual(self.request('POST',self.base()+'/'+updated['media_plan_id']+'/apply',{**self.action(page['items'][0]),'acknowledged':True,'shot_ids':[item['shot_id']]})[0],400)

    def test_human_roles_csrf_extra_fields_and_body_limits_keep_no_provider_route(self):
        for role in ['viewer','reviewer']:
            self.account(role);self.assertEqual(self.request('GET',self.base())[0],200)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body must not be read')):
                for suffix in ['', '/nmp_'+'0'*32+'/select','/nmp_'+'0'*32+'/revise','/nmp_'+'0'*32+'/apply']:self.assertEqual(self.request('POST',self.base()+suffix,{})[0],403)
        self.account('editor');current=self.server.store.shot_view(self.project['id']);body={'revision':current['revision'],'expected_timeline_version':current['shot_timeline']['version']}
        self.assertEqual(self.request('POST',self.base(),body,{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('POST',self.base(),body,{'Cookie':'','Authorization':'Bearer explicit-service-fixture'})[0],401)
        for extra in [{'provider':'unapproved'},{'result':{}},{'graph':{}},{'max_ai_cost_vnd':'10000'}]:self.assertEqual(self.request('POST',self.base(),{**body,**extra})[0],400)
        self.assertEqual(self.request('POST',self.base(),{**body,'options':{'resolver_priority':['ai_image','ai_image']}})[0],400)
        self.assertEqual(self.request('GET',self.base()+'?provider=private')[0],400);self.assertEqual(self.request('GET','/native-media-planner.mjs')[0],200)

    def test_duplicate_requires_new_project_plan_and_immutable_history_reopens(self):
        self.account('editor');record=self.create();original=self.server.store.get(self.project['id']);duplicate=self.server.store.duplicate(self.project['id'],original['revision'])
        self.assertNotIn('studio_media_plans',duplicate['document']);self.assertTrue(duplicate['document']['studio_media_plan_origin']['new_plan_required'])
        self.assertEqual(self.server.store.get(self.project['id']),original)
        self.assertEqual(self.server.media_planner.page(duplicate['id'])['items'],[])
        from services.windows_native.store import Store
        reopened=Store(self.config.data_root);self.assertEqual(reopened.get(self.project['id']),original)
        with reopened.transaction() as con:
            versions=[json.loads(row[0]) for row in con.execute('SELECT document FROM project_versions WHERE project_id=? ORDER BY revision',(self.project['id'],))]
        self.assertEqual(versions[-1]['studio_media_plans'][-1]['sha256'],record['sha256']);self.assertTrue(all('studio_media_plans' not in value for value in versions[:-1]))

    def test_batch_apply_with_one_missing_shot_rolls_back_every_change(self):
        self.account('editor');record=self.create();before=self.server.store.get(self.project['id'])
        status,_,_=self.request('POST',self.base()+'/'+record['plan']['media_plan_id']+'/apply',{**self.action(record),'acknowledged':True,
            'shot_ids':[record['plan']['items'][0]['shot_id'],'shot_'+'0'*32]})
        self.assertEqual(status,400);self.assertEqual(self.server.store.get(self.project['id']),before)
        self.assertNotIn('canonical_timeline',before['document'])

    def test_missing_script_and_source_mode_preserve_existing_footage_workflow(self):
        empty=self.server.store.create('Empty storyboard','No provider');status,page,_=self.request('GET',self.base(empty['id']))
        self.assertEqual(status,200);self.assertEqual(page['unavailable_reason'],'STUDIO_MEDIA_PLAN_SCRIPT_REQUIRED');self.assertIsNone(page['input'])
        self.assertEqual(self.request('POST',self.base(empty['id']),{'revision':empty['revision'],'expected_timeline_version':0})[0],400)
        # An explicit source-mode marker is inspected before any invented storyboard analysis.
        with self.server.store.transaction() as con:
            project=self.server.store.editable(con,self.project['id'],self.project['revision']);doc=project['document']
            doc['canonical_timeline']={'snapshot':{'metadata':{'native_auto_edit_schema':'native-auto-edit-timeline-v1'}}}
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(doc),project['id']));self.server.store.version(con,project['id'])
        status,page,_=self.request('GET',self.base());self.assertEqual(status,200);self.assertEqual(page['unavailable_reason'],'STUDIO_MEDIA_PLAN_USE_SOURCE_BROLL')

    def test_plan_history_hash_changes_and_size_limits_are_rejected(self):
        self.account('editor');record=self.create();before=self.server.store.get(self.project['id'])
        from services.windows_native import studio_media_planner as planner
        with patch.object(planner,'MAX_PLAN_BYTES',1):
            self.assertEqual(self.request('POST',self.base(),{'revision':before['revision'],'expected_timeline_version':0,'options':{'preferred_media_type':'image'}})[0],400)
        self.assertEqual(self.server.store.get(self.project['id']),before)
        with self.server.store.transaction() as con:
            doc=before['document'];doc['studio_media_plans'][0]['plan']['items'][0]['query']='tampered isolated fixture'
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(doc),self.project['id']));self.server.store.version(con,self.project['id'])
        self.assertEqual(self.request('GET',self.base())[0],409)
