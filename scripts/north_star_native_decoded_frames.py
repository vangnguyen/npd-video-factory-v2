"""Fresh CPU-only decoded-source clock evidence; never full Mode B acceptance."""
import argparse,copy,json,os,sqlite3,subprocess,sys,tempfile,zipfile
from contextlib import closing
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.contracts import file_sha
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
from services.windows_native import media_frame_analysis as frames
from services.windows_native.media import ingest_media,media_path
from services.windows_native.vision import NativeVision
from services.windows_native.vision_models import NativeVisionRequest
from services.windows_native.vision_frame_bridge import NativeEvidenceFrameExtractor
from services.windows_native.tests.test_decoded_frame_sampling import DecodedFrameSamplingTests


def check_source(config,asset,observation):
    path=media_path(config,asset['id'])
    data=json.loads(subprocess.check_output([str(config.ffmpeg_bin/'ffprobe.exe'),'-v','error','-protocol_whitelist','file,pipe',
        '-select_streams','v:0','-show_frames','-show_streams','-show_format','-show_entries','frame=pts:stream=time_base:format=start_time','-of','json',str(path)]))
    origin=float(data['format']['start_time']);tb=Fraction(data['streams'][0]['time_base'])
    actual=[float(int(frame['pts'])*tb)-origin for frame in data['frames']]
    assert all(any(abs(frame['timestamp_seconds']-time)<1e-9 for time in actual) for frame in observation['frames'])
    return {'independent_ffprobe':True,'container_start_seconds':origin,'stream_time_base':str(tb),'all_decoded_source_times':actual,
        'sample_times':[f['timestamp_seconds'] for f in observation['frames']],'every_sample_matches_actual_source_frame':True,
        'desired_sampling_grid_is_not_decoded_time':[f['timestamp_seconds'] for f in observation['frames']]!=observation['decoded_clock_evidence']['requested_times']}


def cold(state,expected):
    store=Store(state);config=Config(data_root=state)
    for item in expected:
        project=store.get(item['project_id']);assert project['document']==item['document'] and project['approval'] is None
        bundle=frames.view(store,item['project_id']);assert bundle['observations']==item['observations']
        job=store.get_job(item['job_id']);assert job['status']=='succeeded'
        for observation in bundle['observations']:frames.verify_clock(state,observation)
    return {'new_process':True,'projects':len(expected),'original_jobs_and_clock_artifacts_verified':True,'provider_calls':0,'jobs_created':0}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cold-state',type=Path);args=parser.parse_args()
    if args.cold_state:
        expected=json.loads((args.output/'expected-projects.json').read_text(encoding='utf-8'))
        print(json.dumps(cold(args.cold_state,expected)));return
    out=args.output.resolve();out.mkdir(exist_ok=False);evidence=[];expected=[]
    with tempfile.TemporaryDirectory(prefix='vf-decoded-source-',dir='C:/') as temporary:
        owned=Path(temporary);config=Config(data_root=owned/'state',runtime_root=owned/'runtime',secret_file=owned/'secrets/absent-openai.env',assemblyai_secret_file=owned/'secrets/absent-assemblyai.dpapi')
        store=Store(config.data_root);context=SimpleNamespace(root=owned,config=config,store=store)
        DecodedFrameSamplingTests.vfr(context)
        cases=[('vfr',context.project,context.asset)]
        offset=owned/'offset-source.mp4'
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=10:d=2',
            '-c:v','libx264','-pix_fmt','yuv420p','-output_ts_offset','4',str(offset)],check=True,capture_output=True,timeout=30)
        asset=ingest_media(config,offset,'video/mp4','Known nonzero-start local source',rights_confirmed=True,illustration=True)
        project=store.create('Offset clock rehearsal','','media');project=store.append_media(project['id'],1,asset);cases.append(('offset',project,asset))
        for name,project,asset in cases:
            directory=out/name;directory.mkdir();before=copy.deepcopy(project['document']);source=media_path(config,asset['id']);source_sha=file_sha(source)
            queued=store.enqueue(project['id'],project['revision'],'media_frames',uuid.uuid4().hex);job=store.claim();assert queued['id']==job['id']
            result=Pipeline(config).run(job,lambda _:None);store.finish(job,result=result);project=store.get(project['id']);bundle=frames.view(store,project['id']);observation=bundle['observations'][0]
            assert file_sha(source)==source_sha and project['document'].get('canonical_timeline')==before.get('canonical_timeline') and project['approval'] is None
            probe=check_source(config,asset,observation);assert result['provider_calls']==0
            service=NativeVision(store,config);selected=service.sources(project,NativeVisionRequest(revision=project['revision'],observation_ids=[observation['observation_id']],request_key='clock-rehearsal-no-provider'))[0]
            binding=NativeEvidenceFrameExtractor(store.root,config,project['id'],selected).binding();assert binding['decoded_pts_verified'] is True
            for filename,value in [('asset.json',asset),('observations.json',bundle),('independent-clock-check.json',probe),('vision-input-binding.json',binding),('project.json',project)]:
                (directory/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            (directory/'source.mp4').write_bytes(source.read_bytes())
            for frame in observation['frames']:(directory/Path(frame['reference']).name).write_bytes(frames.frame_path(store.root,frame).read_bytes())
            for field in ('reference','log_reference'):
                filename=Path(observation['decoded_clock_evidence'][field]).name
                (directory/filename).write_bytes((store.root/'jobs'/job['id']/filename).read_bytes())
            expected.append({'project_id':project['id'],'job_id':job['id'],'document':project['document'],'observations':bundle['observations']})
            evidence.append({'case':name,'project_id':project['id'],'job_id':job['id'],'source_sha256':source_sha,'sample_count':len(observation['frames']),
                'independent_clock_check':probe,'timeline_unchanged':True,'approval':None,'confidence':None,'semantic_inference_performed':False})
        (out/'expected-projects.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
        archive=out/'owned-clock-state.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(store.root.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(store.root).as_posix())
        with tempfile.TemporaryDirectory(prefix='vf-decoded-restore-',dir='C:/') as fresh:
            restored=Path(fresh)
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None
                for member in z.infolist():assert (restored/member.filename).resolve().is_relative_to(restored.resolve())
                z.extractall(restored)
            proof=json.loads(subprocess.check_output([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--output',str(out),'--cold-state',str(restored)],text=True))
        (out/'cold-process.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
    value={'schema_version':'native-decoded-source-clock-rehearsal-v1','cases':evidence,'cold_recovery':proof,
        'backup_sha256':file_sha(archive),'provider_calls':0,'paid_calls':0,'real_ASR':False,'real_semantic_Vision':False,'Owner_UAT':False,
        'scope':'source pixel clock and Vision input only; not original A/B/C','owned_temporary_roots_cleaned':True,'historical_or_accepted_artifacts_replaced':False}
    (out/'evidence.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');print('DECODED_SOURCE_CLOCK_REHEARSAL_AND_COLD_RESTORE_PASS')


if __name__=='__main__':main()
