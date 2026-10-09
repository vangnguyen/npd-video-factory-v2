"""Original/recovered rendered-QC factory with temporary synthetic private keys."""
import argparse,asyncio,base64,hashlib,json,re,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from services.windows_native.contracts import file_sha
from services.windows_native.store import Store
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
from services.windows_native.render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
from services.windows_native.render_vision_registry import NativeRenderVisionFactory
from services.windows_native.tests.test_render_vision_registry import profile
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_google_oauth_operations import journals


def run(args):
    root,restored,out=args.state_root.resolve(),args.restore_root.resolve(),args.output.resolve()
    for path in (root,restored):
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-[a-z0-9-]+',path.name) or not path.is_dir():raise ValueError('Existing owned fixture root required')
    if root==restored or out.exists() or out==ROOT or ROOT in out.parents or out in (root,restored) or root in out.parents or restored in out.parents:
        raise ValueError('Fresh external evidence required')
    proofs=[]
    for directory in (root,restored):
        store=Store(directory);before=journals(store);bridge=NativeRenderEvidenceFrameExtractor(store,config_for(directory),args.project_id,args.job_id)
        binding=bridge.binding();assert binding['matches_current_project_document'];wires=[];observations=[];fences=[]
        with tempfile.TemporaryDirectory() as private:
            vault=NativeVisionKeyVault(Path(private),directory,'wsp_native_local')
            receipt=vault.save(PrivateVisionKey(workspace_id='wsp_native_local',credential_alias='explicit-render-vision-key',
                api_key='sk-explicit-synthetic-render-vision-not-a-real-key'))
            def mock(request):
                body=json.loads(request.content);assert body['store'] is False
                images=[v for v in body['input'][0]['content'] if v['type']=='input_image']
                shas=[hashlib.sha256(base64.b64decode(v['image_url'].split(',',1)[1],validate=True)).hexdigest() for v in images]
                assert shas==[v['sha256'] for v in binding['record']['observation']['frames']]
                wires.append({'image_sha256':shas,'input_image_count':len(images),'explicit_in_process_mock':True,'external_dispatches':0})
                return httpx.Response(200,json=response_payload(bridge.max_frames))
            factory=NativeRenderVisionFactory(profile(receipt),vault,operator_enabled=True,transport=httpx.MockTransport(mock))
            public=factory.public();assert public['mock'] and public['status']=='CONFIGURED' and not public['provider_authorized']
            def fence():fences.append('explicit_mock_controller_fence_not_real_owner_consent')
            provider=factory.provider(bridge,admission_guard=fence,response_observer=observations.append)
            result=asyncio.run(provider.analyze(directory/'jobs'/args.job_id/'final.mp4',metadata=bridge.input_metadata(),scenes=[],
                asset_id=binding['render_artifact_id'],checksum_sha256=binding['record']['observation']['rendered_video_sha256'],
                sample_interval_seconds=binding['record']['observation']['sampling_interval_seconds']))
            assert result.provenance['mock_tested'] and not result.provenance['real_provider_tested'] and len(wires)==len(observations)==1
            assert observations[0].mock_transport and not observations[0].billing_invoice_verified and len(fences)>2
            proofs.append({'binding':binding,'public_configuration':public,'mock_wires':wires,'mock_guard_calls':len(fences),
                'original_response_observation':observations[0].model_dump(mode='json'),'mock_provider_provenance':result.provenance})
        assert journals(store)==before
    assert proofs[0]['binding']==proofs[1]['binding']
    assert proofs[0]['mock_wires']==proofs[1]['mock_wires']
    out.mkdir(parents=True);write(out/'original-and-restored-factory.json',proofs)
    sources=('services/windows_native/render_vision_registry.py','services/windows_native/tests/test_render_vision_registry.py',
        'services/windows_native/render_vision_frame_bridge.py','scripts/north_star_render_vision_factory.py')
    write(out/'evidence.json',{'status':'PASS','original_and_restored_bindings_pngs_and_pts_exact':True,'all_original_journals_unchanged':True,
        'protocol_mock_requests':2,'external_dispatches':0,'paid_operations':0,'source_asset_consent_reused':False,
        'temporary_synthetic_private_keys_destroyed':True,'real_provider_tested':False,'owner_consent_controller_implemented':False,
        'request_result_cost_journal_implemented':False,'live_credentials_read':False,'owner_uat_accepted':False,'production_deployed':False,
        'source_sha256':{p:file_sha(ROOT/p) for p in sources}})
    print(json.dumps({'status':'PASS','original_and_restored_input_frames':8,'protocol_mock_requests':2,'external_dispatches':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state-root',type=Path,required=True);parser.add_argument('--restore-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--project-id',required=True);parser.add_argument('--job-id',required=True);run(parser.parse_args())
