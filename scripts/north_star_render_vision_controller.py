"""Original finite rendered-QC journals and keyless public recovery; mocks only."""
import argparse,base64,hashlib,json,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.backup import create_backup,restore_backup,database_status
from services.windows_native.contracts import digest,file_sha
from services.windows_native.render_vision import NativeRenderVision,TABLES
from services.windows_native.render_vision_models import RenderAnalyze,RenderAction
from services.windows_native.render_vision_registry import NativeRenderVisionFactory
from services.windows_native.render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_render_vision_registry import profile
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
from scripts.north_star_google_oauth_operations import journals
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_render_frame_recovery import owned,snapshot as media_snapshot


def reopen(args):
    out=args.output.resolve();store=Store(owned(args.restore_root));reader=NativeRenderVision(store,config_for(store.root))
    assert reader.states()['profiles']==[] and not reader.states()['enabled']
    expected=json.loads((out/'expected-history.json').read_bytes())
    for row in expected:assert reader.get(row['project_id'],row['vision_id'])==row
    assert journals(store)==json.loads((out/'expected-journals.json').read_bytes())
    assert media_snapshot(store.root)==json.loads((out/'expected-media.json').read_bytes())
    assert database_status(store.db)['active_operations']==0 and reader.recover()==0
    write(out/('new-process-replay.json' if args.reopen else 'in-process-replay.json'),{
        'status':'PASS','original_intents_responses_costs_events_projects_render_checkpoints_png_pts_exact':True,
        'history_requires_current_credentials_profiles_or_owner':False,'finite_consent_renewed':False,'requests_replayed':0,
        'external_dispatches':0,'paid_operations':0,'real_provider_tested':False,'owner_uat_accepted':False})
    print(json.dumps({'status':'PASS','keyless_history':len(expected),'external_dispatches':0}))


def run(args):
    root=owned(args.state_root,True);restored=owned(args.restore_root,True);out=args.output.resolve()
    if root==restored or out.exists() or out==ROOT or ROOT in out.parents or out==root or root in out.parents or out==restored or restored in out.parents:
        raise ValueError('Fresh external fixture/evidence roots required')
    if file_sha(args.input_bundle)!=args.expected_input_sha256:raise ValueError('Original input backup checksum required')
    out.mkdir(parents=True);write(out/'prior-restore.json',restore_backup(args.input_bundle,root,expected_sha256=args.expected_input_sha256))
    store=Store(root);config=config_for(root);bridge=NativeRenderEvidenceFrameExtractor(store,config,args.project_id,args.job_id)
    binding=bridge.binding();original_project=store.get(args.project_id);original_media=media_snapshot(root);expected=[];wires=[]
    raw,data=human_fixture('owner',workspace='wsp_native_local');verifier=[HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)]
    principal=verifier[0].verify('Bearer '+raw);clock=[datetime.now(timezone.utc)];mode=[None];pending=[None]
    def owner(enabled):
        value=verifier[0].registry.model_dump(mode='json');value['tokens'][principal.token_id]['enabled']=enabled
        verifier[0]=HumanAuthVerifier(HumanAuthRegistry.model_validate(value),max_token_ttl_seconds=86400)
    def mock(request):
        body=json.loads(request.content);assert body['store'] is False and str(request.url)=='https://api.openai.com/v1/responses'
        images=[i for i in body['input'][0]['content'] if i['type']=='input_image']
        shas=[hashlib.sha256(base64.b64decode(i['image_url'].split(',',1)[1],validate=True)).hexdigest() for i in images]
        assert shas==[v['sha256'] for v in binding['record']['observation']['frames']]
        wires.append({'mode':mode[0],'image_sha256':shas,'wire_request_sha256':hashlib.sha256(request.content).hexdigest(),'mock':True})
        payload=response_payload(len(images))
        if mode[0]=='revoke':owner(False)
        if mode[0]=='timeout':raise httpx.ReadTimeout('sk-explicit-private-error-must-not-be-recorded',request=request)
        if mode[0]=='invalid':payload['output'][0]['content'][0]['text']='EXPLICIT INVALID MOCK RESPONSE'
        if mode[0]=='cancel':runtime.cancel(args.project_id,pending[0]['vision_id'],RenderAction(expected_snapshot_sha256=pending[0]['snapshot_sha256']),principal=principal)
        if mode[0]=='recover':assert runtime.recover()==1
        return httpx.Response(200,json=payload)
    with tempfile.TemporaryDirectory() as private:
        vault=NativeVisionKeyVault(Path(private),root,'wsp_native_local')
        receipt=vault.save(PrivateVisionKey(workspace_id='wsp_native_local',credential_alias='explicit-render-vision-key',api_key='sk-explicit-synthetic-render-controller-not-real'))
        factory=NativeRenderVisionFactory(profile(receipt),vault,operator_enabled=True,transport=httpx.MockTransport(mock))
        runtime=NativeRenderVision(store,config,factories={factory.profile.profile_id:factory},enabled=True,identity_provider=lambda:verifier[0],clock=lambda:clock[0])
        for kind in ('success','revoke','timeout','invalid','cancel','recover'):
            owner(True);mode[0]=kind
            payload=RenderAnalyze(revision=original_project['revision'],render_job_id=args.job_id,profile_id=factory.profile.profile_id,
                expected_configuration_sha256=factory.sha256,expected_render_input_sha256=digest(binding),acknowledged_rendered_frame_analysis=True,
                acknowledged_protocol_mock=True,max_operation_cost_vnd='500',request_key='explicit-render-controller-'+kind)
            row,replay=runtime.create(args.project_id,payload,principal=principal);assert not replay and row['status']=='approved';pending[0]=row
            done=runtime.process(args.project_id,row['vision_id'],RenderAction(expected_snapshot_sha256=row['snapshot_sha256']))
            expected_status='succeeded' if kind=='success' else 'outcome_unknown' if kind=='timeout' else 'cancelled' if kind=='cancel' else 'review_required'
            assert done['status']==expected_status,(kind,done['status'],done['failure_code'])
            count=len(wires);assert runtime.process(args.project_id,row['vision_id'],RenderAction(expected_snapshot_sha256=row['snapshot_sha256']))==done and len(wires)==count
            assert store.get(args.project_id)==original_project
            if done['result']:assert not done['result']['semantic_inference_performed'] and done['result']['decoded_render_pts_verified']
            if done['response']:assert done['response']['request_sha256']==wires[-1]['wire_request_sha256']
            expected.append(done)
        costs=runtime.costs.summary(args.project_id)
        added=[c for c in costs['records'] if c['operation'].startswith('render-vision.')]
        assert len(added)==6 and all(c['actual_cost'] is None and not c['paid'] and not c['external_call'] for c in added)
    assert not Path(private).exists();assert len(wires)==6 and sum(r['response'] is not None for r in expected)==5
    current_media=media_snapshot(root);assert all(current_media[k]==original_media[k] for k in ('projects','files','records','successful_renders'))
    write(out/'original-project.json',original_project);write(out/'original-render-input.json',binding);write(out/'expected-history.json',expected)
    write(out/'mock-wire-summary.json',wires);write(out/'cost-summary.json',costs);write(out/'expected-journals.json',journals(store));write(out/'expected-media.json',current_media)
    backup=create_backup(config,out/'public-render-vision-controller.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-render-vision-controller.zip',restored,expected_sha256=backup['sha256']))
    reopen(args)
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--restore-root',str(restored),'--output',str(out),'--reopen'],capture_output=True,check=True,timeout=120)
    assert 'PASS' in result.stdout.decode()
    sources=('services/windows_native/render_vision.py','services/windows_native/render_vision_models.py',
        'services/windows_native/render_vision_frame_bridge.py','services/windows_native/backup.py',
        'services/windows_native/tests/test_render_vision.py','scripts/north_star_render_vision_controller.py')
    write(out/'evidence.json',{'schema_version':'native-render-vision-controller-rehearsal-v1','status':'PASS',
        'source_sha256':{s:file_sha(ROOT/s) for s in sources},'protocol_mock_requests':6,'finite_one_use_intents':6,'complete_responses':5,
        'mock_results':1,'mock_cost_operations':6,'original_timeline_projects_media_checkpoints_png_pts_exact':True,
        'all_original_journals_keyless_new_process_restore_exact':True,'public_backup_sha256':backup['sha256'],
        'new_process_stdout':result.stdout.decode().strip(),'temporary_synthetic_private_keys_destroyed':True,
        'source_asset_consent_reused':False,'external_dispatches':0,'paid_operations':0,'live_credentials_read':False,
        'semantic_inference_performed':False,'hard_qc_replaced':False,'owner_uat_accepted':False,'signed_http_or_ui_integrated':False,
        'real_provider_tested':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','protocol_mock_requests':6,'complete_responses':5,'public_backup_sha256':backup['sha256']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input-bundle',type=Path);parser.add_argument('--expected-input-sha256')
    parser.add_argument('--state-root',type=Path);parser.add_argument('--restore-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--project-id');parser.add_argument('--job-id');parser.add_argument('--reopen',action='store_true');args=parser.parse_args()
    if args.reopen:reopen(args)
    else:run(args)
