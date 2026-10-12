"""CPU-only dense motion/scene clocks; no speech/provider or full Mode B claim."""
import argparse,json,subprocess,sys,tempfile,uuid,zipfile
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.contracts import file_sha
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
from services.windows_native.media import ingest_media,media_path
from services.windows_native import auto_edit_analysis as analysis
from services.windows_native.tests.test_decoded_frame_sampling import DecodedFrameSamplingTests


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cold-state',type=Path);args=parser.parse_args()
    if args.cold_state:
        store=Store(args.cold_state);expected=json.loads((args.output/'expected.json').read_text(encoding='utf-8'))
        for item in expected:
            assert store.get(item['project_id'])['document']==item['document']
            assert analysis.view(store,item['project_id'])==item['view']
            assert store.get_job(item['job_id'])['status']=='succeeded'
        print(json.dumps({'new_process':True,'projects':len(expected),'views_exact':True,'jobs_created':0,'provider_calls':0}));return
    out=args.output.resolve();out.mkdir(exist_ok=False);cases=[];expected=[]
    with tempfile.TemporaryDirectory(prefix='vf-dense-visual-',dir='C:/') as temporary:
        owned=Path(temporary);config=Config(data_root=owned/'state',runtime_root=owned/'runtime',secret_file=owned/'secrets/absent-openai.env',assemblyai_secret_file=owned/'secrets/absent-assemblyai.dpapi')
        store=Store(config.data_root);context=SimpleNamespace(root=owned,store=store,config=config);DecodedFrameSamplingTests.vfr(context)
        sources=[('vfr',context.project,context.asset)]
        shot=owned/'offset-shot.mp4'
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','color=c=black:s=320x240:r=30:d=1',
            '-f','lavfi','-i','color=c=white:s=320x240:r=30:d=1','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[v]',
            '-map','[v]','-c:v','libx264','-pix_fmt','yuv420p','-output_ts_offset','4',str(shot)],check=True,capture_output=True,timeout=30)
        asset=ingest_media(config,shot,'video/mp4','Offset shot explicit local source',rights_confirmed=True,illustration=True)
        project=store.create('Dense shot clock fixture','','media');project=store.append_media(project['id'],1,asset);sources.append(('offset-shot',project,asset))
        for name,project,asset in sources:
            directory=out/name;directory.mkdir();source=media_path(config,asset['id']);before=file_sha(source)
            queued=store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex);job=store.claim();assert job['id']==queued['id']
            result=Pipeline(config).run(job,lambda _:None);store.finish(job,result=result);view=analysis.view(store,project['id']);project=store.get(project['id'])
            value=view['analyses'][0]['analysis'];visual=value['provenance']['media_signals']['visual'];assert visual['decoded_pts_verified'] and value['provenance']['provider_calls']==0
            probe=json.loads(subprocess.check_output([str(config.ffmpeg_bin/'ffprobe.exe'),'-v','error','-show_frames','-show_streams','-show_format',
                '-select_streams','v:0','-show_entries','frame=pts:stream=time_base:format=start_time','-of','json',str(source)]))
            origin=float(probe['format']['start_time']);tb=Fraction(probe['streams'][0]['time_base']);actual=[float(int(v['pts'])*tb)-origin for v in probe['frames']]
            assert all(any(abs(frame['timestamp_seconds']-timestamp)<1e-9 for timestamp in actual) for frame in visual['frames'])
            assert file_sha(source)==before and project['approval'] is None and 'canonical_timeline' not in project['document'] and value['transcript'] is None
            check={'independent_ffprobe':True,'all_motion_samples_match_decoded_source_pts':True,'container_start_seconds':origin,
                'sample_times':[f['timestamp_seconds'] for f in visual['frames']],'actual_source_times':actual,
                'source_unchanged':True,'timeline_unchanged':True,'ASR_called':False,'semantic_vision':False}
            if name=='offset-shot':
                boundaries=[s['start_seconds'] for s in value['scenes']][1:];assert boundaries==[1.]
                check['normalized_scene_boundary_seconds']=boundaries
            for filename,item in [('analysis.json',view),('visual.json',visual),('independent-check.json',check),('project.json',project)]:
                (directory/filename).write_text(json.dumps(item,ensure_ascii=False,indent=2),encoding='utf-8')
            (directory/'source.mp4').write_bytes(source.read_bytes())
            cases.append({'case':name,'project_id':project['id'],'job_id':job['id'],'source_sha256':before,'check':check})
            expected.append({'project_id':project['id'],'job_id':job['id'],'document':project['document'],'view':view})
        (out/'expected.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
        archive=out/'owned-dense-state.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(store.root.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(store.root).as_posix())
        with tempfile.TemporaryDirectory(prefix='vf-dense-cold-',dir='C:/') as fresh:
            restored=Path(fresh)
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None
                for member in z.infolist():assert (restored/member.filename).resolve().is_relative_to(restored.resolve())
                z.extractall(restored)
            cold=json.loads(subprocess.check_output([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--output',str(out),'--cold-state',str(restored)],text=True))
        (out/'cold.json').write_text(json.dumps(cold,indent=2),encoding='utf-8')
    evidence={'schema_version':'native-dense-visual-clock-rehearsal-v1','cases':cases,'cold':cold,'backup_sha256':file_sha(archive),
        'provider_calls':0,'paid_calls':0,'ASR':False,'semantic_Vision':False,'Owner_UAT':False,'scope':'motion and scene clock only; audio and full Mode A/B remain open','owned_roots_cleaned':True}
    (out/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8');print('DENSE_VISUAL_SCENE_CLOCK_AND_COLD_RESTORE_PASS')

if __name__=='__main__':main()
