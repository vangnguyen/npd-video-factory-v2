"""Actual video/PNG/CPU/SQLite/DPAPI; saved ASR and every Vision call are mocks."""
import copy,json,tempfile,threading,unittest,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import httpx
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.tests import test_source_broll as broll_fixture,test_access_http as http_fixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_vision_registry import profile
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native import source_broll as broll,auto_edit_timeline as timeline,source_broll_vision as reviewed
from services.windows_native.pipeline import Pipeline
from services.windows_native.vision import NativeVision
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
from services.windows_native.vision_registry import NativeVisionFactory
from services.windows_native.official_vision import NativeOfficialVision
from services.windows_native.official_vision_models import Analyze,Action
from services.windows_native.media_frame_analysis import view as frame_view,frame_path
from services.windows_native.auto_edit_analysis import asset_reference
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.store import Store
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler


class SourceBrollVisionTests(unittest.TestCase):
    setUpSource=broll_fixture.SourceBrollTests.setUp
    tearDown=broll_fixture.SourceBrollTests.tearDown
    real_source=broll_fixture.SourceBrollTests.real_source
    save_analysis=broll_fixture.SourceBrollTests.save_analysis
    image=broll_fixture.SourceBrollTests.image
    http=http_fixture.NativeAccessHTTPTests.request

    def setUp(self):
        self.setUpSource();self.source_path=self.real_source();self.support=self.image()
        job=self.store.enqueue(self.project['id'],self.project['revision'],'media_frames',uuid.uuid4().hex);job=self.store.claim()
        self.store.finish(job,result=Pipeline(self.config).run(job,lambda _:None));self.project=timeline.view(self.store,self.project['id'])
        self.frames=frame_view(self.store,self.project['id']);self.workspace='wsp_reviewed_source_broll_fixture';self.calls=[];self.clock=[datetime.now(timezone.utc)]
        (self.root/'.vf-auth-workspace.json').write_text(json.dumps({'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}))
        self.raw,data=human_fixture('owner',workspace=self.workspace);self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
        self.principal=self.verifier.verify('Bearer '+self.raw)
        private=tempfile.TemporaryDirectory();self.addCleanup(private.cleanup)
        self.vault=NativeVisionKeyVault(Path(private.name)/'private',self.root,self.workspace)
        receipt=self.vault.save(PrivateVisionKey(workspace_id=self.workspace,credential_alias='explicit-source-broll',api_key='sk-explicit-synthetic-source-broll-not-real'))
        def response(request):
            self.calls.append(str(request.url));body=json.loads(request.content);count=sum(v['type']=='input_image' for v in body['input'][0]['content'])
            return httpx.Response(200,json=response_payload(count))
        self.factory=NativeVisionFactory(profile(receipt),self.vault,operator_enabled=True,transport=httpx.MockTransport(response))
        self.official=NativeOfficialVision(NativeVision(self.store,self.config,workspace_id=self.workspace),
            factories={self.factory.profile.profile_id:self.factory},enabled=True,identity_provider=lambda:self.verifier,clock=lambda:self.clock[0])
        self.official.costs.set_budget(self.project['id'],self.project['revision'],'1000');self.project=timeline.view(self.store,self.project['id'])

    def complete(self,main=False):
        self.project=timeline.view(self.store,self.project['id']);asset=self.asset if main else self.support
        observation=next(v for v in self.frames['observations'] if v['asset_id']==asset['id'])
        row,_=self.official.create(self.project['id'],Analyze(revision=self.project['revision'],profile_id=self.factory.profile.profile_id,
            expected_configuration_sha256=self.factory.sha256,observation_id=observation['observation_id'],acknowledged_external_image_analysis=True,
            acknowledged_protocol_mock=True,max_operation_cost_vnd='500',request_key='source-broll-reviewed-'+uuid.uuid4().hex),principal=self.principal)
        return self.official.process(self.project['id'],row['vision_id'],Action(expected_snapshot_sha256=row['snapshot_sha256']))

    def ref(self,row,**changes):return {'vision_id':row['vision_id'],'expected_snapshot_sha256':row['snapshot_sha256'],'expected_result_sha256':row['result_sha256'],
        'acknowledged_reviewed_result':True,'acknowledged_protocol_mock':True,**changes}

    def create(self,row=None,**changes):
        body={'expected_version':self.project['shot_timeline']['version'],**({'reviewed_vision':[self.ref(row)]} if row else {}),**changes}
        self.project=broll.create(self.store,self.config,self.project['id'],self.project['revision'],body,official_vision=lambda:self.official)
        return self.project['document']['source_broll_plans'][-1]['plan']

    def selection(self,plan):return {'expected_version':self.project['shot_timeline']['version'],'media_plan_id':plan['media_plan_id'],
        'expected_plan_version':plan['version'],'item_id':plan['items'][0]['media_plan_item_id'],'asset_id':asset_reference(self.support)}

    def test_reviewed_mock_retains_lineage_without_changing_semantic_scores_or_source_timeline(self):
        row=self.complete();baseline=self.create();before=copy.deepcopy(self.project['document']['canonical_timeline']);plan=self.create(row)
        p=plan['provenance'];self.assertEqual(p['algorithm'],reviewed.ALGORITHM);self.assertFalse(p['semantic_vision_used'])
        self.assertEqual(p['reviewed_vision']['items'][0]['response_sha256'],row['response']['response_sha256'])
        self.assertEqual(p['reviewed_vision']['items'][0]['cost_operation_id'],row['cost_operation_id']);self.assertIsNone(plan['vision_analysis_id'])
        for a,b in zip(plan['items'],baseline['items'],strict=True):
            candidates=copy.deepcopy(a['provenance']['supporting_candidates'])
            for candidate in candidates:candidate.pop('reviewed_vision',None)
            self.assertEqual(candidates,b['provenance']['supporting_candidates']);self.assertEqual(a['broll']['search_query'],b['broll']['search_query'])
            self.assertEqual(a['broll']['confidence'],b['broll']['confidence'])
        self.assertEqual(self.project['document']['canonical_timeline'],before);saved=copy.deepcopy(self.project);self.create(row)
        self.assertEqual(self.project,saved);self.assertEqual(len(self.calls),1)

    def test_manual_select_apply_preserves_source_audio_tracks_bytes_and_original_result(self):
        row=self.complete();plan=self.create(row);before=copy.deepcopy(self.project['shot_timeline']['snapshot']);source_sha=file_sha(self.source_path)
        self.project=broll.select(self.store,self.config,self.project['id'],self.project['revision'],self.selection(plan))
        plan=self.project['document']['source_broll_plans'][-1]['plan']
        self.project=broll.apply(self.store,self.config,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'media_plan_id':plan['media_plan_id'],'expected_plan_version':plan['version'],
            'item_ids':[plan['items'][0]['media_plan_item_id']]})
        after=self.project['shot_timeline']['snapshot'];self.assertEqual(before['duration_seconds'],after['duration_seconds'])
        for track in before['tracks']:
            if track['kind']!='broll':self.assertEqual(track,next(v for v in after['tracks'] if v['track_id']==track['track_id']))
        self.assertTrue(any(track['kind']=='broll' and track['clips'] for track in after['tracks']));self.assertIsNone(self.project['approval'])
        self.assertEqual(file_sha(self.source_path),source_sha);self.assertEqual(self.official.get(self.project['id'],row['vision_id']),row);self.assertEqual(len(self.calls),1)

    def test_missing_changed_source_and_pngs_remain_keyless_history_but_block_current_selection(self):
        row=self.complete();plan=self.create(row);saved=copy.deepcopy(self.project)
        for frame in row['snapshot']['input_binding']['source_frame_evidence']:
            frame_path(self.root,frame).unlink()
        (self.root/'assets'/self.support['id']).unlink();self.source_path.unlink()
        self.clock[0]+=timedelta(hours=4)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO HISTORY KEY ACCESS')):
            reopened=Store(self.root);self.assertEqual(timeline.view(reopened,self.project['id']),saved)
        with self.assertRaises(WorkflowError):broll.select(self.store,self.config,self.project['id'],self.project['revision'],self.selection(plan))
        self.assertEqual(self.store.get(self.project['id'])['document'],saved['document']);self.assertEqual(len(self.calls),1)

    def test_rehashed_mock_candidate_and_frozen_analysis_promotions_are_rejected(self):
        row=self.complete();self.create(row);original=copy.deepcopy(self.project['document'])
        for mutate in (lambda p:p['provenance']['reviewed_vision']['items'][0].update(mock=False,semantic_inference_performed=True),
            lambda p:p['items'][0]['provenance']['supporting_candidates'][0].update(score_basis='claimed genuine semantic ranking'),
            lambda p:p['provenance']['reviewed_input']['analysis']['scenes'][0].update(confidence=.99),
            lambda p:p['provenance']['reviewed_vision'].update(mock_present=1),
            lambda p:p['provenance']['reviewed_input']['assets'][asset_reference(self.support)]['provenance']['pixel_quality_summary'].update(heuristic_quality_score=.99)):
            doc=copy.deepcopy(original);record=doc['source_broll_plans'][-1];mutate(record['plan']);record['sha256']=digest(record['plan'])
            with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),self.project['id']))
            with self.assertRaises(WorkflowError):timeline.view(self.store,self.project['id'])
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(original),self.project['id']))
        self.assertEqual(timeline.view(self.store,self.project['id']),self.project);self.assertEqual(len(self.calls),1)

    def test_raw_review_duplicate_hash_and_foreign_refs_refuse_without_new_plan(self):
        row=self.complete();before=self.store.get(self.project['id'])
        for change in ({'acknowledged_reviewed_result':1},{'acknowledged_protocol_mock':False},{'expected_result_sha256':'0'*64}):
            with self.assertRaises(WorkflowError):self.create(row,reviewed_vision=[self.ref(row,**change)])
        with self.assertRaises(WorkflowError):self.create(row,reviewed_vision=[self.ref(row),self.ref(row)])
        other=self.store.duplicate(self.project['id'],self.project['revision'])
        with self.assertRaises(WorkflowError):broll.create(self.store,self.config,other['id'],other['revision'],{
            'expected_version':other['document']['canonical_timeline']['version'],'reviewed_vision':[self.ref(row)]},official_vision=lambda:self.official)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(len(self.calls),1)

    def test_rehashed_and_recomputed_plan_cannot_forge_original_asset_attribution(self):
        row=self.complete();self.create(row);original=copy.deepcopy(self.project['document']);key=asset_reference(self.support)
        for change in ({'license':'invented-commercial-license'},{'rights_status':'licensed'},{'fixture':False},
                       {'source_reference':'https://invented.example/license'},{'generation_provenance':{'fixture':False,'model':'invented'}}):
            doc=copy.deepcopy(original);record=doc['source_broll_plans'][-1];plan=record['plan'];p=plan['provenance']
            p['reviewed_input']['assets'][key]['provenance'].update(change);assets=reviewed.restore_assets(p['reviewed_input']['assets'])
            from app.auto_edit_models import AutoEditAnalysisRead
            from app.media_intelligence_models import MediaPlanRequest
            analysis=AutoEditAnalysisRead.model_validate(p['reviewed_input']['analysis']);configuration=MediaPlanRequest.model_validate(plan['configuration'])
            plan['fingerprint']=digest({'algorithm':reviewed.ALGORITHM,'analysis':analysis.model_dump(mode='json'),'configuration':configuration.model_dump(mode='json'),
                'assets':{k:{'sha256':a.checksum_sha256,'filename':a.filename,'provenance':a.provenance} for k,a in assets.items()},'reviewed_vision':p['reviewed_vision']})
            plan['items']=[v.model_dump(mode='json') for v in reviewed.items(plan['media_plan_id'],plan['fingerprint'],analysis,assets,configuration,p['reviewed_vision'])]
            record['sha256']=digest(plan)
            with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),self.project['id']))
            with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_BROLL_REVIEWED_VISION_INVALID'):timeline.view(self.store,self.project['id'])
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(original),self.project['id']))
        self.assertEqual(timeline.view(self.store,self.project['id']),self.project);self.assertEqual(len(self.calls),1)

    def test_main_transcript_edit_blocks_reuse_and_keeps_original_plan_readable(self):
        from services.windows_native import auto_edit_analysis as analysis
        row=self.complete(main=True);self.create(row);saved=copy.deepcopy(self.project['document']['source_broll_plans'])
        transcript=broll.context(self.project)[1].transcript
        analysis.edit_transcript(self.store,self.project['id'],self.project['revision'],transcript.analysis_id,{
            'expected_version':transcript.version,'expected_timeline_version':self.project['shot_timeline']['version'],
            'segments':[{'segment_id':transcript.segments[0].segment_id,'text':'Explicit edited transcript fixture.'}]})
        self.project=timeline.view(self.store,self.project['id']);before=copy.deepcopy(self.project)
        with self.assertRaises(WorkflowError):self.create(row)
        self.assertEqual(self.store.get(self.project['id'])['document'],before['document'])
        self.assertEqual(self.project['document']['source_broll_plans'],saved);self.assertEqual(len(self.calls),1)

    def test_rehashed_selected_media_cannot_claim_rights_payment_or_different_placement(self):
        row=self.complete();plan=self.create(row)
        self.project=broll.select(self.store,self.config,self.project['id'],self.project['revision'],self.selection(plan));original=copy.deepcopy(self.project['document'])
        for mutate in (lambda p:p['media_assets'][0].update(license='invented commercial permission'),
                       lambda p:p['media_assets'][0].update(publishing_allowed=True,production_eligible=True),
                       lambda p:p['items'][0]['provenance'].update(confidence_calibrated=True),
                       lambda p:p.update(provider_status={'semantic_vision':'CONFIGURED'})):
            doc=copy.deepcopy(original);record=doc['source_broll_plans'][-1];mutate(record['plan']);record['sha256']=digest(record['plan'])
            with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),self.project['id']))
            with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_BROLL_REVIEWED_VISION_INVALID'):timeline.view(self.store,self.project['id'])
        with self.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(original),self.project['id']))
        self.assertEqual(timeline.view(self.store,self.project['id']),self.project);self.assertEqual(len(self.calls),1)

    def test_original_exception_is_attribution_only_after_expiry_and_disabled_reopen(self):
        from PIL import Image
        from services.windows_native.media import ingest_media
        from services.windows_native.rights_override import NativeRightsOverrides,rights_sha
        path=self.root/'explicit-owned-exception.png';Image.new('RGB',(320,240),(55,90,110)).save(path)
        asset=ingest_media(self.config,path,'image/png','EXPLICIT SYNTHETIC EXCEPTION FIXTURE',rights_confirmed=True,illustration=False)
        self.project=self.store.append_media(self.project['id'],self.project['revision'],asset)
        service=NativeRightsOverrides(self.store,workspace_id=self.workspace,enabled=True,clock=lambda:self.clock[0])
        receipt=service.record(self.project['id'],asset['id'],{'revision':self.project['revision'],'asset_sha256':asset['sha256'],
            'expected_rights_sha256':rights_sha(asset),'action':'grant','reason':'EXPLICIT SYNTHETIC LOCAL PLACEMENT DECISION FIXTURE',
            'evidence_reference':'document://explicit-local-fixture','valid_days':1,'allow_publishing_review':False,'acknowledged':True,
            'request_key':'source-broll-reviewed-local-exception-fixture'},actor='explicit-owner-fixture')
        row=self.complete();plan=self.create(row);key=asset_reference(asset)
        self.assertEqual(plan['provenance']['reviewed_input']['assets'][key]['provenance']['owner_rights_override'],receipt['record'])
        saved=copy.deepcopy(self.project);self.clock[0]+=timedelta(days=2)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO HISTORY KEY ACCESS')):
            self.assertEqual(timeline.view(Store(self.root),self.project['id']),saved)
        self.assertIsNone(service.active(self.project['document'],self.project['id'],asset))
        body=self.selection(plan);body['asset_id']=key
        with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_BROLL_INPUT_CHANGED'):
            broll.select(self.store,self.config,self.project['id'],self.project['revision'],body)
        self.assertEqual(timeline.view(self.store,self.project['id']),saved);self.assertEqual(len(self.calls),1)

    def test_duplicate_preserves_original_review_history_without_transfer_and_keeps_clip_edits(self):
        row=self.complete();plan=self.create(row)
        self.project=broll.select(self.store,self.config,self.project['id'],self.project['revision'],self.selection(plan))
        plan=self.project['document']['source_broll_plans'][-1]['plan']
        self.project=broll.apply(self.store,self.config,self.project['id'],self.project['revision'],{
            'expected_version':self.project['shot_timeline']['version'],'media_plan_id':plan['media_plan_id'],'expected_plan_version':plan['version'],
            'item_ids':[plan['items'][0]['media_plan_item_id']]})
        before=copy.deepcopy(self.project);child=self.store.duplicate(self.project['id'],self.project['revision'])
        self.assertEqual(child['document']['source_broll_plans'],[]);archive=child['document']['source_broll_inherited_reviewed_history']
        self.assertEqual([v['original_record'] for v in archive],before['document']['source_broll_plans'])
        self.assertTrue(all(v['authority_transferred'] is False and v['new_plan_required'] is True for v in archive))
        clips=[c for t in child['shot_timeline']['snapshot']['tracks'] if t['kind']=='broll' for c in t['clips']]
        self.assertTrue(clips);self.assertTrue(all(c['metadata']['inherited_reviewed_vision']['authority_transferred'] is False for c in clips))
        self.assertIsNone(child['approval']);self.assertEqual(timeline.view(self.store,self.project['id']),before)
        baseline=broll.create(self.store,self.config,child['id'],child['revision'],{'expected_version':1})
        self.assertEqual(baseline['document']['source_broll_plans'][-1]['plan']['provenance']['algorithm'],broll.ALGORITHM)
        self.assertEqual(self.official.get(self.project['id'],row['vision_id']),row);self.assertEqual(len(self.calls),1)

    def test_reviewed_main_mock_cannot_replace_scene_semantics_or_confidence(self):
        row=self.complete(main=True);baseline=self.create();plan=self.create(row)
        self.assertIsNone(plan['vision_analysis_id']);self.assertFalse(plan['provenance']['semantic_vision_used'])
        self.assertEqual([v['broll']['search_query'] for v in plan['items']],[v['broll']['search_query'] for v in baseline['items']])
        self.assertEqual([v['broll']['confidence'] for v in plan['items']],[v['broll']['confidence'] for v in baseline['items']]);self.assertEqual(len(self.calls),1)

    def test_signed_editor_admits_reviewed_broll_but_viewer_cannot_write_or_analyse(self):
        row=self.complete();raw,data=human_fixture('editor',workspace=self.workspace)
        identity=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        self.server=LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=identity)
        self.cookie,session=identity.login(raw);self.csrf=session.csrf;thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        try:
            route='/api/projects/'+self.project['id']+'/auto-edit/broll'
            body={'revision':self.project['revision'],'action':'create','payload':{'expected_version':self.project['shot_timeline']['version'],'reviewed_vision':[self.ref(row)]}}
            status,value,_=self.http('POST',route,body);self.assertEqual(status,200,value)
            self.assertEqual(value['document']['source_broll_plans'][-1]['plan']['provenance']['algorithm'],reviewed.ALGORITHM)
            raw,data=human_fixture('viewer',workspace=self.workspace);self.server.access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
            self.server.access.bind_root(self.root);self.cookie,session=self.server.access.login(raw);self.csrf=session.csrf
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO FORBIDDEN BROLL BODY')):self.assertEqual(self.http('POST',route,body)[0],403)
            self.assertEqual(self.http('GET','/api/projects/'+self.project['id'])[0],200)
        finally:self.server.shutdown();self.server.server_close();thread.join()
        self.assertEqual(len(self.calls),1)

    def test_pure_nonmock_ranking_vector_does_not_become_an_admitted_provider_result(self):
        # Exercise calculation only. Altered mock fields are not stored or
        # admitted by validate_saved/original Vision, and certify no provider.
        row=self.complete();plan=self.create(row);value=copy.deepcopy(plan['provenance']['reviewed_vision'])
        synthetic=value['items'][0];synthetic['mock']=False;synthetic['semantic_inference_performed']=True
        synthetic['frames'][0]['caption']='Neural network education';assets=reviewed.restore_assets(plan['provenance']['reviewed_input']['assets'])
        candidates=plan['items'][0]['provenance']['supporting_candidates']
        result=reviewed.rank(candidates,assets,value,'neural');self.assertEqual(result[0]['relevance_score'],1.)
        self.assertEqual(result[0]['quality_score'],.5);self.assertIsNone(result[0]['confidence'])
        self.assertTrue(self.official.get(self.project['id'],row['vision_id'])['result']['mock']);self.assertEqual(len(self.calls),1)
