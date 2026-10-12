"""Real gap-preserving proxy/final PCM and QC; mock speech/review, no Owner UAT."""
import argparse,array,json,math,subprocess,sys,tempfile,time,uuid,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.server import Runner
from services.windows_native import asr,auto_edit_analysis,auto_edit_timeline as timeline,source_settings
from services.windows_native.source_preview import resolve_assets
from services.windows_native.contracts import WorkflowError,file_sha


def extract(path,target):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        for member in z.infolist():assert (target/member.filename).resolve().is_relative_to(target.resolve())
        z.extractall(target)


def pcm_windows(config,path):
    data=subprocess.check_output([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-i',str(path),'-map','0:a:0','-ac','1','-ar','48000','-f','s16le','-'],timeout=30)
    samples=array.array('h');samples.frombytes(data)
    def rms(a,b):
        values=samples[round(a*48000):round(b*48000)];assert len(values)==round((b-a)*48000)
        return math.sqrt(sum(float(v)**2 for v in values)/len(values))/32768
    windows={'before_gap':rms(.2,.3),'inside_gap':rms(.8,.9),'gap_tail':rms(1.16,1.20),
             'resumed_audio_edge':rms(1.23,1.25),'after_gap':rms(1.35,1.45),'late_audio':rms(1.8,1.9)}
    assert all(windows[k]<.001 for k in ('inside_gap','gap_tail')) and all(windows[k]>.02 for k in ('before_gap','resumed_audio_edge','after_gap','late_audio'))
    return {'frames':len(samples),'sample_rate':48000,'source_missing_interval_seconds':[.64,1.216],'rms_windows':windows,'generated_tone_not_speech':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--input-bundle',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cold-state',type=Path);args=parser.parse_args()
    if args.cold_state:
        expected=json.loads((args.output/'expected.json').read_text(encoding='utf-8'));config=Config(data_root=args.cold_state);store=Store(args.cold_state);project=store.get(expected['project_id']);job=store.get_job(expected['render_job_id'])
        assert project['document']==expected['document'] and job['result']==expected['result']
        with patch('services.windows_native.source_render.command_run',side_effect=AssertionError('No replay on verified checkpoint')):
            assert Pipeline(config).run(job,lambda _:None)==expected['result']
        assets=resolve_assets(config,project)[1];assert {i:asset.checksum_sha256 for i,(asset,path) in assets.items()}==expected['source_hashes']
        assert (store.root/'jobs'/job['id']/'source-audio-clocks.json').is_file()
        print(json.dumps({'new_process':True,'document_timeline_originals_and_render_checkpoint_exact':True,'no_reencode':True,'provider_calls':0,'jobs_created':0}));return
    out=args.output.resolve();out.mkdir(exist_ok=False)
    assert args.input_bundle and args.input_bundle.is_file()
    with tempfile.TemporaryDirectory(prefix='vf-source-gap-render-',dir='C:/') as temporary:
        owned=Path(temporary);state=owned/'state';state.mkdir();extract(args.input_bundle,state)
        config=Config(data_root=state,runtime_root=owned/'runtime',secret_file=owned/'secrets/absent-openai.env',assemblyai_secret_file=owned/'secrets/absent-assemblyai.dpapi');store=Store(state)
        projects=store.list();assert len(projects)==1;project=store.get(projects[0]['id']);asset=project['document']['assets'][0]
        record=asr.analysis_for_asset(project['document'],asset);assert record and record['source_gap_review']
        view=auto_edit_analysis.view(store,project['id']);analysis=view['analyses'][0]['analysis']
        project=timeline.create(store,project['id'],project['revision'],{'analysis_id':analysis['analysis_id'],'transcript_id':analysis['transcript']['transcript_id'],'source_window':[0,2],'aspect_ratio':'9:16'})
        version=project['document']['canonical_timeline']['version'];project=source_settings.configure(store,project['id'],project['revision'],{'expected_version':version,'preview_mode':'final_effects','subtitle_template_ref':'karaoke-gold@v1'})
        before_hashes={i:file_sha(path) for i,(asset,path) in resolve_assets(config,project)[1].items()}
        manager=PreviewManager(config,store)
        try:
            manager.generate(project['id'],project['revision']);deadline=time.monotonic()+150
            while True:
                preview=manager.status(project['id'])
                if preview['status'] not in {'QUEUED','RUNNING'}:break
                assert time.monotonic()<deadline;time.sleep(.05)
            assert preview['status']=='READY',preview.get('error');preview_path=manager.video_path(project['id'],preview['timeline_version'])
            preview_pcm=pcm_windows(config,preview_path);(out/'preview.mp4').write_bytes(preview_path.read_bytes())
        finally:manager.close()
        project=store.approve(project['id'],project['revision'],'AUTOMATED GAP RENDER REVIEW FIXTURE — NOT OWNER UAT',True)
        job=store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex)
        with patch('services.windows_native.pipeline.verify_runtime',side_effect=AssertionError('No TTS inference')):
            Runner(store,Pipeline(config)).run_one()
        job=store.get_job(job['id'])
        if job['status']!='succeeded':
            (out/'failed-job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding='utf-8')
            with zipfile.ZipFile(out/'failed-owned-state.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
                for path in sorted(store.root.rglob('*')):
                    if path.is_file():z.write(path,path.relative_to(store.root).as_posix())
            reports=[]
            for path in (store.root/'jobs'/job['id']).rglob('qc-report.json'):reports.append(json.loads(path.read_bytes()))
            (out/'failed-qc-reports.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
            raise AssertionError({'job':job.get('error'),'qc_failures':[r.get('failures') for r in reports]})
        assert job['result']['qc']['passed'] and job['result']['provider_calls']==job['result']['tts_calls']==0
        directory=store.root/'jobs'/job['id'];final=directory/'final.mp4';final_pcm=pcm_windows(config,final)
        try:store.final_video(job['id'])
        except WorkflowError as error:assert error.code=='HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED'
        else:raise AssertionError('Final human review must remain required')
        project=store.get(project['id']);assert {i:file_sha(path) for i,(asset,path) in resolve_assets(config,project)[1].items()}==before_hashes
        clocks=json.loads((directory/'source-audio-clocks.json').read_text(encoding='utf-8'));assert any(not v['clock']['contiguous'] for v in clocks['assets'].values())
        expected={'project_id':project['id'],'render_job_id':job['id'],'document':project['document'],'result':job['result'],'source_hashes':before_hashes}
        values={'project.json':project,'timeline.json':project['document']['canonical_timeline'],'analysis.json':view,'preview-manifest.json':preview,
                'pcm-check.json':{'preview':preview_pcm,'final':final_pcm},'expected.json':expected}
        for name,value in values.items():(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        for name in ('final.mp4','qc-report.json','source-audio-clocks.json','canonical-audio-mux.json','audio-analysis.json','render-manifest.json','subtitles.json','cost.json'):(out/name).write_bytes((directory/name).read_bytes())
        archive=out/'owned-source-gap-render-state.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(store.root.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(store.root).as_posix())
        with tempfile.TemporaryDirectory(prefix='vf-source-gap-render-cold-',dir='C:/') as fresh:
            restored=Path(fresh);extract(archive,restored)
            cold=json.loads(subprocess.check_output([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--output',str(out),'--cold-state',str(restored)],text=True,encoding='utf-8'))
        (out/'cold.json').write_text(json.dumps(cold,indent=2),encoding='utf-8')
    evidence={'schema_version':'native-source-gap-render-rehearsal-v1','project_id':project['id'],'render_job_id':job['id'],'qc_passed':True,
        'preview_and_final_source_gap_and_late_audio_verified':True,'preview_pcm':preview_pcm,'final_pcm':final_pcm,'source_hashes_unchanged':True,
        'ASR_and_human_review_fixtures':True,'generated_tone':True,'Owner_UAT':False,'human_final_review_required':True,'cold':cold,
        'backup_sha256':file_sha(archive),'provider_calls':0,'paid_calls':0,'local_TTS_inferences':0,'production_deployed':False,'published':False,'owned_roots_cleaned':True}
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print('SOURCE_GAP_EFFECTS_PREVIEW_FINAL_QC_AND_COLD_RESTORE_PASS')


if __name__=='__main__':main()
