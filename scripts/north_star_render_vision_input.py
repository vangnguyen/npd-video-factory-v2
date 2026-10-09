"""Original render PNG/provider-protocol binding on source and restored fixtures."""
import argparse,asyncio,base64,hashlib,json,re,sys
from dataclasses import asdict
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from app.openai_vision_provider import OpenAIVisionProvider
from services.windows_native.render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
from services.windows_native.store import Store
from services.windows_native.contracts import file_sha
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_google_oauth_operations import journals


def run(args):
    root,restored,out=args.state_root.resolve(),args.restore_root.resolve(),args.output.resolve()
    for value in (root,restored):
        if value.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-[a-z0-9-]+',value.name) or not value.is_dir():raise ValueError('Existing owned original/recovered fixture required')
    if root==restored or out.exists() or out==ROOT or ROOT in out.parents or out in (root,restored) or root in out.parents or restored in out.parents:
        raise ValueError('Fresh external evidence required')
    expected=[];calls=[]
    for directory in (root,restored):
        store=Store(directory);before=journals(store)
        bridge=NativeRenderEvidenceFrameExtractor(store,config_for(directory),args.project_id,args.job_id,workspace_id=args.workspace)
        binding=bridge.binding();observation=binding['record']['observation']
        frames=asyncio.run(bridge.extract(directory/'jobs'/args.job_id/'final.mp4',metadata=bridge.input_metadata(),scenes=[],
            asset_id=binding['render_artifact_id'],sample_interval_seconds=observation['sampling_interval_seconds']))
        actual=[{'timestamp_seconds':frame.timestamp_seconds,'sha256':frame.sha256,'bytes':len(frame.payload),
            'reference':frame.evidence_frame_reference,'actual_png_payload_sha256':hashlib.sha256(frame.payload).hexdigest()} for frame in frames]
        assert all(a['sha256']==a['actual_png_payload_sha256'] for a in actual)
        if directory==root:
            def mock(request):
                body=json.loads(request.content);assert body['store'] is False
                images=[item for item in body['input'][0]['content'] if item['type']=='input_image'];assert len(images)==len(frames)
                shas=[hashlib.sha256(base64.b64decode(v['image_url'].split(',',1)[1],validate=True)).hexdigest() for v in images]
                assert shas==[frame.sha256 for frame in frames]
                calls.append({'explicit_in_process_mock_transport':True,'image_count':len(images),'image_sha256':shas,'store':False,
                    'external_dispatches':0,'actual_paid_cost':None})
                return httpx.Response(200,json=response_payload(bridge.max_frames))
            provider=OpenAIVisionProvider(credential_alias='explicit-synthetic-render-vision-fixture',credential_resolver=lambda _: 'contract-key-not-real',
                frame_extractor=bridge,transport=httpx.MockTransport(mock),allow_zero_cost_contract_test=True)
            result=asyncio.run(provider.analyze(directory/'jobs'/args.job_id/'final.mp4',metadata=bridge.input_metadata(),scenes=[],
                asset_id=binding['render_artifact_id'],checksum_sha256=observation['rendered_video_sha256'],sample_interval_seconds=observation['sampling_interval_seconds']))
            protocol={'explicit_protocol_mock':True,'semantic_inference_performed':False,'real_provider_tested':False,
                'provenance':result.provenance,'frames':[asdict(frame) for frame in result.frames]}
            assert result.provenance['mock_tested'] is True and result.provenance['real_provider_tested'] is False
            assert result.provenance['source_checksum']==observation['rendered_video_sha256']
            assert [f.evidence_frame_reference for f in result.frames]==[frame.evidence_frame_reference for frame in frames]
        assert journals(store)==before
        expected.append({'binding':binding,'actual_input_frames':actual})
    assert expected[0]==expected[1] and len(calls)==1
    out.mkdir(parents=True);write(out/'original-and-restored-input.json',expected[0]);write(out/'protocol-mock-result.json',protocol)
    write(out/'protocol-mock-wires.json',calls)
    sources=('services/windows_native/render_vision_frame_bridge.py','services/windows_native/render_frame_qc.py',
        'services/windows_native/tests/test_render_vision_frame_bridge.py','scripts/north_star_render_vision_input.py')
    write(out/'evidence.json',{'status':'PASS','workspace_id':args.workspace,'project_id':args.project_id,'job_id':args.job_id,
        'original_and_recovered_binding_actual_pngs_and_pts_exact':True,'all_original_journals_unchanged':True,
        'matches_current_project_document':binding['matches_current_project_document'],'protocol_mock_requests':1,
        'new_frame_extraction_or_render':False,'existing_png_pixels_revalidated':True,'external_dispatches':0,'paid_operations':0,
        'separate_purpose_owner_controller_implemented':False,'real_provider_admission_configured':False,
        'source_asset_consent_reused':False,'semantic_inference_performed':False,'owner_uat_accepted':False,'production_deployed':False,
        'source_sha256':{p:file_sha(ROOT/p) for p in sources}})
    print(json.dumps({'status':'PASS','original_and_restored_input_frames':len(frames),'protocol_mock_requests':1,'external_dispatches':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state-root',type=Path,required=True);parser.add_argument('--restore-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--project-id',required=True);parser.add_argument('--job-id',required=True)
    parser.add_argument('--workspace',default='wsp_native_local');run(parser.parse_args())
