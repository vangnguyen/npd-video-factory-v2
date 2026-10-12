"""Observed delayed PCM clock plus explicit ASR mock; no genuine speech acceptance."""
import argparse,asyncio,json,subprocess,sys,tempfile,uuid,zipfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
from services.windows_native.media import ingest_media,media_path
from services.windows_native import asr,auto_edit_analysis
from services.windows_native.server import Runner
from services.windows_native.contracts import file_sha,digest
from services.windows_native.tests.test_asr import FixtureTransport,KEY
from app.audio_waveform import measure_waveform

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cold-state',type=Path);args=parser.parse_args()
    if args.cold_state:
        saved=json.loads((args.output/'expected.json').read_text(encoding='utf-8'));store=Store(args.cold_state);project=store.get(saved['project_id'])
        assert project['document']==saved['document'] and auto_edit_analysis.view(store,saved['project_id'])==saved['view']
        asset=project['document']['assets'][0];record=asr.analysis_for_asset(project['document'],asset);assert record and record['provider_pcm_transcript']
        assert store.get_job(saved['asr_job_id'])['status']=='succeeded'
        print(json.dumps({'new_process':True,'mapped_and_original_transcripts_exact':True,'view_exact':True,'provider_calls':0,'jobs_created':0}));return
    out=args.output.resolve();out.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='vf-source-audio-clock-',dir='C:/') as temporary:
        owned=Path(temporary);config=Config(data_root=owned/'state',runtime_root=owned/'runtime',secret_file=owned/'secrets/absent-openai.env',assemblyai_secret_file=owned/'secrets/absent-assemblyai.dpapi')
        store=Store(config.data_root);source=owned/'delayed-tone.mp4'
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=10:d=2',
            '-itsoffset','0.5','-f','lavfi','-i','sine=frequency=440:duration=1','-map','0:v:0','-map','1:a:0','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-t','2',str(source)],check=True,capture_output=True,timeout=30)
        asset=ingest_media(config,source,'video/mp4','Delayed generated tone; ASR fixture only',rights_confirmed=True,illustration=True)
        project=store.create('Source audio clock rehearsal','','media');project=store.append_media(project['id'],1,asset);before=file_sha(media_path(config,asset['id']))
        original_analyze=asr.analyze;FixtureTransport.calls=[];FixtureTransport.fail_observe_once=True;FixtureTransport.invalid_timing=False;FixtureTransport.fail_upload=False
        with patch.object(asr.connection,'status',return_value={'connected':True,'fixture':True}),patch.object(asr.connection,'load_credential',return_value=KEY),\
            patch.object(asr,'analyze',side_effect=lambda c,j,o,s:original_analyze(c,j,o,s,transport_factory=FixtureTransport)):
            queued=store.enqueue(project['id'],project['revision'],'asr',uuid.uuid4().hex);Runner(store,Pipeline(config)).run_one();assert store.get_job(queued['id'])['status']=='failed'
            store.resume(queued['id']);Runner(store,Pipeline(config)).run_one();assert store.get_job(queued['id'])['status']=='succeeded'
        assert FixtureTransport.calls.count(('POST','/v2/upload'))==1 and FixtureTransport.calls.count(('POST','/v2/transcript'))==1
        project=store.get(project['id']);record=project['document']['media_analysis'][0];offset=record['audio']['decoded_source_clock']['source_start_seconds'];assert offset>.45
        assert record['provider_pcm_transcript']['segments'][0]['words'][0]['start_seconds']==0.
        assert record['transcript']['segments'][0]['words'][0]['start_seconds']==offset
        waveform=asyncio.run(measure_waveform(media_path(config,asset['id']),executable=str(config.ffmpeg_bin/'ffmpeg.exe'),duration_seconds=asset['duration_seconds']))
        assert waveform['bins'][0]['start_seconds']>.45
        store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex);Runner(store,Pipeline(config)).run_one();project=store.get(project['id']);view=auto_edit_analysis.view(store,project['id'])
        assert view['analyses'][0]['analysis']['transcript']['segments'][0]['words'][0]['start_seconds']==offset
        assert file_sha(media_path(config,asset['id']))==before and project['approval'] is None and 'canonical_timeline' not in project['document']
        for filename,value in [('project.json',project),('analysis.json',view),('waveform.json',waveform),('mapped-transcript.json',record['transcript']),('provider-pcm-transcript.json',record['provider_pcm_transcript']),('audio-clock.json',record['audio'])]:
            (out/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'source.mp4').write_bytes(media_path(config,asset['id']).read_bytes())
        directory=store.root/'jobs'/queued['id']/'analysis'/asset['id']
        (out/'speech.wav').write_bytes((directory/'speech.wav').read_bytes());(out/'speech-clock.log').write_bytes((directory/'speech-clock.log').read_bytes())
        expected={'project_id':project['id'],'asr_job_id':queued['id'],'document':project['document'],'view':view}
        (out/'expected.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
        archive=out/'owned-source-audio-state.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(store.root.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(store.root).as_posix())
        with tempfile.TemporaryDirectory(prefix='vf-source-audio-cold-',dir='C:/') as fresh:
            restored=Path(fresh)
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None
                for member in z.infolist():assert (restored/member.filename).resolve().is_relative_to(restored.resolve())
                z.extractall(restored)
            cold=json.loads(subprocess.check_output([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--output',str(out),'--cold-state',str(restored)],text=True))
        (out/'cold.json').write_text(json.dumps(cold,indent=2),encoding='utf-8')
    evidence={'schema_version':'native-source-audio-clock-rehearsal-v1','project_id':project['id'],'asr_job_id':queued['id'],'source_sha256':before,
        'observed_pcm_source_offset_seconds':offset,'provider_pcm_first_word_seconds':0.,'mapped_first_word_source_seconds':offset,'waveform_first_bin_source_seconds':waveform['bins'][0]['start_seconds'],
        'mock_upload_dispatches':1,'mock_create_dispatches':1,'explicit_mock_observation_resume':True,'provider_calls':0,'paid_calls':0,'genuine_ASR':False,'real_Vision':False,
        'generated_tone_not_speech':True,'Owner_UAT':False,'cold':cold,'backup_sha256':file_sha(archive),'source_unchanged':True,'timeline_unchanged':True,'approval_created':False,'owned_roots_cleaned':True}
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print('SOURCE_AUDIO_CLOCK_MOCK_ASR_RESUME_AND_COLD_RESTORE_PASS')

if __name__=='__main__':main()
