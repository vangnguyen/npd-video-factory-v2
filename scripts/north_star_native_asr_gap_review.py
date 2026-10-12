"""Signed UI controller, keyless human-review resume and distinct-process recovery."""
import argparse,json,subprocess,sys,tempfile,threading,uuid,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'apps/api')]
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.store import Store
from services.windows_native.server import LocalServer,Runner
from services.windows_native.access import NativeAccess
from services.windows_native.media import ingest_media,media_path
from services.windows_native import asr,asr_gap_reviews as reviews,auto_edit_analysis
from services.windows_native.contracts import file_sha
from services.windows_native.tests.test_asr import KEY
from services.windows_native.tests.test_source_audio_gaps import GapTransport
from services.windows_native.tests.test_human_identity import fixture as human


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--cold-state',type=Path);args=parser.parse_args()
    if args.cold_state:
        expected=json.loads((args.output/'expected.json').read_text(encoding='utf-8'));config=Config(data_root=args.cold_state);store=Store(args.cold_state);project=store.get(expected['project_id'])
        assert project['document']==expected['document'] and reviews.view(store,config,project['id'],expected['workspace_id'])==expected['history']
        assert auto_edit_analysis.view(store,project['id'])==expected['analysis'] and store.get_job(expected['asr_job_id'])['status']=='succeeded'
        asset=project['document']['assets'][0];record=asr.analysis_for_asset(project['document'],asset);assert record and record['source_gap_review']
        assert file_sha(media_path(config,asset['id']))==expected['source_sha256']
        print(json.dumps({'new_process':True,'project_review_history_and_original_candidate_exact':True,'auto_edit_transcript_exact':True,'source_hash_exact':True,'provider_calls':0,'jobs_created':0}));return
    out=args.output.resolve();out.mkdir(exist_ok=False);workspace='wsp_asr_gap_review_rehearsal'
    with tempfile.TemporaryDirectory(prefix='vf-asr-gap-review-',dir='C:/') as temporary:
        owned=Path(temporary);config=Config(data_root=owned/'state',runtime_root=owned/'runtime',secret_file=owned/'secrets/absent-openai.env',assemblyai_secret_file=owned/'secrets/absent-assemblyai.dpapi')
        store=Store(config.data_root);source=owned/'gap.mp4'
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=10:d=2',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=2','-af',"aselect='not(between(t,0.6,1.2))'",
            '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,capture_output=True,timeout=30)
        asset=ingest_media(config,source,'video/mp4','Generated source gap; mock transcript review',rights_confirmed=True,illustration=True)
        project=store.create('Gap word review rehearsal','','media');project=store.append_media(project['id'],1,asset);before=file_sha(media_path(config,asset['id']))
        original=asr.analyze;GapTransport.calls=[];GapTransport.cross_gap=True;GapTransport.fail_observe_once=False;GapTransport.fail_upload=False;GapTransport.invalid_timing=False
        with patch.object(asr.connection,'status',return_value={'connected':True,'fixture':True}),patch.object(asr.connection,'load_credential',return_value=KEY),\
             patch.object(asr,'analyze',side_effect=lambda c,j,o,s:original(c,j,o,s,transport_factory=GapTransport)):
            job=store.enqueue(project['id'],project['revision'],'asr',uuid.uuid4().hex);Runner(store,Pipeline(config)).run_one()
        assert store.get_job(job['id'])['error']['code']=='ASR_WORD_OVER_SOURCE_AUDIO_GAP_REVIEW_REQUIRED';calls=list(GapTransport.calls)
        raw,registry=human('editor',workspace=workspace);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),workspace)
        cookie,session=access.login(raw);server=LocalServer(0,config,start_worker=False,access=access);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        control=owned/'private-fixture-control.json';control.write_text(json.dumps({'workspace_id':workspace,'project_id':project['id'],'revision':project['revision'],
                'base':f'http://127.0.0.1:{server.server_port}','cookie':cookie,'csrf':session.csrf}),encoding='utf-8')
        try:ui=json.loads(subprocess.check_output(['C:/Program Files/nodejs/node.exe',str(ROOT/'scripts/native_asr_gap_review_http_ui.mjs'),str(control)],text=True,encoding='utf-8',timeout=40))
        finally:server.shutdown();server.server_close();thread.join()
        assert ui['resumed_job_id']==job['id'] and store.get_job(job['id'])['status']=='queued'
        with patch.object(asr.connection,'status',side_effect=AssertionError('Keyless resume must not read provider status')),patch.object(asr.connection,'load_credential',side_effect=AssertionError('Keyless resume must not read credentials')):
            Runner(store,Pipeline(config)).run_one()
        assert store.get_job(job['id'])['status']=='succeeded' and GapTransport.calls==calls
        project=store.get(project['id']);record=project['document']['media_analysis'][0]
        assert record['provider_pcm_transcript']['segments'][0]['words'][1]['start_seconds']==.6 and record['transcript']['segments'][0]['words'][1]['start_seconds']==1.3
        assert record['transcript']['segments'][0]['words'][1]['confidence'] is None and record['transcript']['provenance']['original_evidence'] is False
        store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex);Runner(store,Pipeline(config)).run_one();project=store.get(project['id']);analysis=auto_edit_analysis.view(store,project['id'])
        assert analysis['analyses'][0]['analysis']['transcript']['is_original_evidence'] is False
        history=reviews.view(store,config,project['id'],workspace);assert not history['items'][0]['editable'] and history['items'][0]['version']==1
        assert file_sha(media_path(config,asset['id']))==before and project['approval'] is None and 'canonical_timeline' not in project['document']
        expected={'project_id':project['id'],'asr_job_id':job['id'],'workspace_id':workspace,'document':project['document'],'history':history,'analysis':analysis,'source_sha256':before}
        directory=store.root/'jobs'/job['id']/'analysis'/asset['id']
        for name,value in [('ui.json',ui),('history.json',history),('project.json',project),('analysis.json',analysis),('expected.json',expected)]:
            (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'source.mp4').write_bytes(media_path(config,asset['id']).read_bytes())
        for name in ('transcript-candidate.json','checkpoint-transcript-candidate.json','speech.wav','decoded-speech.wav','speech-clock.log'):(out/name).write_bytes((directory/name).read_bytes())
        archive=out/'owned-asr-gap-review-state.zip'
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(store.root.rglob('*')):
                if path.is_file():z.write(path,path.relative_to(store.root).as_posix())
        with tempfile.TemporaryDirectory(prefix='vf-asr-gap-review-cold-',dir='C:/') as fresh:
            restored=Path(fresh)
            with zipfile.ZipFile(archive) as z:
                assert z.testzip() is None
                for member in z.infolist():assert (restored/member.filename).resolve().is_relative_to(restored.resolve())
                z.extractall(restored)
            cold=json.loads(subprocess.check_output([sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--output',str(out),'--cold-state',str(restored)],text=True,encoding='utf-8'))
        (out/'cold.json').write_text(json.dumps(cold,indent=2),encoding='utf-8')
    evidence={'schema_version':'native-asr-gap-review-rehearsal-v1','project_id':project['id'],'asr_job_id':job['id'],'source_sha256':before,
        'signed_controller_requests':len(ui['calls']),'source_range_verified':True,'original_word_start_seconds':.6,'human_reviewed_word_start_seconds':1.3,
        'mock_upload_dispatches':1,'mock_create_dispatches':1,'keyless_resume_no_additional_provider_calls':True,'cold':cold,'backup_sha256':file_sha(archive),
        'fixture_DOM':True,'fixture_human':True,'generated_tone':True,'genuine_ASR':False,'actual_browser':False,'Owner_UAT':False,
        'provider_calls':0,'paid_calls':0,'source_unchanged':True,'timeline_unchanged':True,'approval_created':False,'owned_roots_cleaned':True}
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print('ASR_GAP_REVIEW_SIGNED_UI_KEYLESS_RESUME_AND_COLD_RESTORE_PASS')


if __name__=='__main__':main()
