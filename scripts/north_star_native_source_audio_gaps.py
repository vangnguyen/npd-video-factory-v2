"""Real source gap/PCM proof and mock-ASR known resume; no speech acceptance."""
import argparse,asyncio,hashlib,json,subprocess,sys,tempfile,uuid,wave,zipfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
from services.windows_native.media import ingest_media,media_path
from services.windows_native import asr,auto_edit_analysis
from services.windows_native.server import Runner
from services.windows_native.contracts import file_sha
from services.windows_native.tests.test_asr import KEY
from services.windows_native.tests.test_source_audio_gaps import GapTransport
from app.audio_waveform import measure_waveform


def pcm_proof(directory,metadata):
    plan=metadata['explicit_gap_padding']['plan'];segments=[];gaps=[]
    with wave.open(str(directory/'decoded-speech.wav'),'rb') as raw,wave.open(str(directory/'speech.wav'),'rb') as padded:
        assert raw.getnframes()==plan['decoded_pcm_samples'] and padded.getnframes()==plan['normalized_pcm_samples']
        for segment in plan['segments']:
            raw.setpos(segment['pcm_start_sample']);padded.setpos(segment['normalized_pcm_start_sample']);count=segment['pcm_end_sample']-segment['pcm_start_sample']
            original=raw.readframes(count);normalized=padded.readframes(count);assert original==normalized
            segments.append({'decoded_start':segment['pcm_start_sample'],'normalized_start':segment['normalized_pcm_start_sample'],'sample_count':count,'identical_pcm_sha256':hashlib.sha256(original).hexdigest()})
        for gap in plan['gaps']:
            padded.setpos(gap['pcm_start_sample']);count=gap['pcm_end_sample']-gap['pcm_start_sample'];value=padded.readframes(count)
            assert value==b'\0'*(count*2)
            gaps.append({'normalized_start':gap['pcm_start_sample'],'sample_count':count,'explicit_zero_pcm_sha256':hashlib.sha256(value).hexdigest()})
    return {'segments':segments,'gaps':gaps,'decoded_samples':plan['decoded_pcm_samples'],'normalized_samples':plan['normalized_pcm_samples'],
            'inserted_samples':plan['inserted_silence_samples'],'no_time_scale_change':True,'source_media_not_edited':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cold-state',type=Path);args=parser.parse_args()
    if args.cold_state:
        expected=json.loads((args.output/'expected.json').read_text(encoding='utf-8'));store=Store(args.cold_state);project=store.get(expected['project_id'])
        assert project['document']==expected['document'] and auto_edit_analysis.view(store,project['id'])==expected['view']
        asset=project['document']['assets'][0];record=asr.analysis_for_asset(project['document'],asset);assert record and record['audio']['explicit_gap_padding']
        directory=store.root/'jobs'/expected['asr_job_id']/'analysis'/asset['id'];assert pcm_proof(directory,record['audio'])==expected['pcm_proof']
        assert file_sha(media_path(Config(data_root=store.root),asset['id']))==expected['source_sha256'] and store.get_job(expected['asr_job_id'])['status']=='succeeded'
        print(json.dumps({'new_process':True,'original_mapped_transcripts_and_view_exact':True,'decoded_and_normalized_PCM_exact':True,'source_hash_exact':True,'provider_calls':0,'jobs_created':0}));return
    out=args.output.resolve();out.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='vf-source-audio-gap-',dir='C:/') as temporary:
        owned=Path(temporary);config=Config(data_root=owned/'state',runtime_root=owned/'runtime',secret_file=owned/'secrets/absent-openai.env',assemblyai_secret_file=owned/'secrets/absent-assemblyai.dpapi')
        store=Store(config.data_root);source=owned/'gap.mp4'
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=10:d=2',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=2','-af',"aselect='not(between(t,0.6,1.2))'",
            '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,capture_output=True,timeout=30)
        asset=ingest_media(config,source,'video/mp4','Generated source audio gap; mock words only',rights_confirmed=True,illustration=True)
        project=store.create('Source audio gap rehearsal','','media');project=store.append_media(project['id'],1,asset);before=file_sha(media_path(config,asset['id']))
        original_analyze=asr.analyze;GapTransport.calls=[];GapTransport.cross_gap=False;GapTransport.fail_observe_once=True;GapTransport.fail_upload=False;GapTransport.invalid_timing=False
        with patch.object(asr.connection,'status',return_value={'connected':True,'fixture':True}),patch.object(asr.connection,'load_credential',return_value=KEY),\
            patch.object(asr,'analyze',side_effect=lambda c,j,o,s:original_analyze(c,j,o,s,transport_factory=GapTransport)):
            queued=store.enqueue(project['id'],project['revision'],'asr',uuid.uuid4().hex);Runner(store,Pipeline(config)).run_one();assert store.get_job(queued['id'])['status']=='failed'
            store.resume(queued['id']);Runner(store,Pipeline(config)).run_one();assert store.get_job(queued['id'])['status']=='succeeded',store.get_job(queued['id']).get('error')
        assert GapTransport.calls.count(('POST','/v2/upload'))==GapTransport.calls.count(('POST','/v2/transcript'))==1
        project=store.get(project['id']);record=project['document']['media_analysis'][0];directory=store.root/'jobs'/queued['id']/'analysis'/asset['id'];proof=pcm_proof(directory,record['audio'])
        waveform=asyncio.run(measure_waveform(media_path(config,asset['id']),executable=str(config.ffmpeg_bin/'ffmpeg.exe'),duration_seconds=asset['duration_seconds']))
        assert waveform['method']=='ffmpeg-mono-pcm-peak-rms-v3'
        for gap in waveform['missing_audio_intervals']:assert all(b['end_seconds']<=gap['start_seconds'] or b['start_seconds']>=gap['end_seconds'] for b in waveform['bins'])
        probe=json.loads(subprocess.check_output([str(config.ffmpeg_bin/'ffprobe.exe'),'-v','error','-protocol_whitelist','file,pipe','-select_streams','a:0','-show_frames','-show_entries','frame=pts,nb_samples','-of','json',str(source)]))
        independent=[{'before':a['pts']+a['nb_samples'],'after':b['pts']} for a,b in zip(probe['frames'],probe['frames'][1:]) if b['pts']-a['pts']-a['nb_samples']>1]
        assert independent==[{'before':g['source_start_sample'],'after':g['source_end_sample']} for g in record['audio']['decoded_source_clock']['gaps']]
        store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex);Runner(store,Pipeline(config)).run_one();project=store.get(project['id']);view=auto_edit_analysis.view(store,project['id'])
        assert view['analyses'][0]['analysis']['transcript']['segments'][0]['words'][1]['start_seconds']==1.3
        assert file_sha(media_path(config,asset['id']))==before and project['approval'] is None and 'canonical_timeline' not in project['document']
        expected={'project_id':project['id'],'asr_job_id':queued['id'],'document':project['document'],'view':view,'pcm_proof':proof,'source_sha256':before}
        exports={'project.json':project,'analysis.json':view,'waveform.json':waveform,'mapped-transcript.json':record['transcript'],'provider-pcm-transcript.json':record['provider_pcm_transcript'],
                 'audio-clock.json':record['audio'],'pcm-proof.json':proof,'independent-ffprobe.json':{'frames':probe,'gaps':independent},'expected.json':expected}
        for name,value in exports.items():(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'source.mp4').write_bytes(media_path(config,asset['id']).read_bytes())
        for name in ('decoded-speech.wav','speech.wav','speech-clock.log'):(out/name).write_bytes((directory/name).read_bytes())
        archive=out/'owned-source-audio-gap-state.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(store.root.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(store.root).as_posix())
        with tempfile.TemporaryDirectory(prefix='vf-source-audio-gap-cold-',dir='C:/') as fresh:
            restored=Path(fresh)
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None
                for member in z.infolist():assert (restored/member.filename).resolve().is_relative_to(restored.resolve())
                z.extractall(restored)
            cold=json.loads(subprocess.check_output([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--output',str(out),'--cold-state',str(restored)],text=True))
        (out/'cold.json').write_text(json.dumps(cold,indent=2),encoding='utf-8')
    evidence={'schema_version':'native-source-audio-gap-rehearsal-v1','project_id':project['id'],'asr_job_id':queued['id'],'source_sha256':before,'pcm_proof':proof,'independent_source_gap_samples':independent,
              'waveform_gaps_measured_not_synthesized':True,'original_and_provider_input_WAV_retained':True,'explicit_known_job_resume':True,'mock_upload_dispatches':1,'mock_create_dispatches':1,
              'cold':cold,'backup_sha256':file_sha(archive),'generated_tone_not_speech':True,'genuine_ASR':False,'provider_calls':0,'paid_calls':0,'Owner_UAT':False,'source_unchanged':True,'timeline_unchanged':True,'approval_created':False,'owned_roots_cleaned':True}
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print('SOURCE_AUDIO_GAP_PCM_MOCK_ASR_RESUME_AND_COLD_RESTORE_PASS')


if __name__=='__main__':main()
