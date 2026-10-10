"""Owned synthetic Mode A media editor/controller/render/restore evidence.

Neither fixture speech, a signed fixture human nor fake DOM accepts Owner UAT.
No provider is called. All temporary fixtures are owned and exported with a
verified recovery backup before their ordinary test teardown.
"""
import argparse,copy,json,shutil,subprocess,sys,threading,time,uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
REPO=Path(__file__).resolve().parents[1];sys.path.insert(0,str(REPO))
from services.windows_native.tests.test_narrated_media_tracks import NarratedMediaTracksTests,prepare
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer
from services.windows_native.pipeline import Pipeline
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.store import Store
from services.windows_native.source_media_tracks import catalog
from services.windows_native.narrated_media_mix import validate_bundle,verify
from services.windows_native.hardening import durable_json
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.costs import CostLedger

def files(root):
    return {p.relative_to(root).as_posix():file_sha(p) for name in ('assets','originals') for p in (root/name).rglob('*') if p.is_file()}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--evidence-dir',type=Path,required=True);out=parser.parse_args().evidence_dir.resolve()
    if out.exists() or out==REPO or REPO in out.parents:raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True);case=NarratedMediaTracksTests();server=manager=None
    try:
        prepare(case);original=files(case.root);voice_sha=file_sha(case.voice_out/'voice.wav')
        raw,data=human_fixture('editor',workspace=case.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),case.workspace)
        server=LocalServer(0,case.config,start_worker=False,access=access);cookie,session=access.login(raw)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();current=case.store.get(case.project['id'])
        context=case.owned/'narrated-signed-controller-context.json'
        durable_json(context,{'fixture_human':True,'origin':'http://127.0.0.1:'+str(server.server_port),'workspace_id':case.workspace,
            'project':{'id':current['id'],'revision':current['revision']},'cookie':cookie,'csrf':session.csrf})
        run=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(REPO/'scripts/native_source_media_tracks_http_ui.mjs'),str(context)],capture_output=True,check=True,timeout=60)
        controller=json.loads(run.stdout);durable_json(out/'signed-controller.json',controller)
        if len(controller['requests'])!=6 or controller['timeline_mode']!='narrated' or len(controller['imports'])!=3:raise AssertionError('Expected actual Mode A controller flow')
        server.shutdown();server.server_close();thread.join();server=None
        current=case.store.get(current['id']);before=copy.deepcopy(current['document']);manager=PreviewManager(case.config,case.store)
        manager.generate(current['id'],current['revision']);deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            preview=manager.status(current['id'])
            if preview['status'] not in {'QUEUED','RUNNING'}:break
            time.sleep(.1)
        if preview['status']!='READY':raise AssertionError(preview.get('error') or preview['status'])
        current=case.store.approve(current['id'],current['revision'],'AUTOMATED SYNTHETIC FIXTURE — NOT OWNER UAT',True)
        case.store.enqueue(current['id'],current['revision'],'render',uuid.uuid4().hex);job=case.store.claim()
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No new inference allowed')):result=Pipeline(case.config).run(job,lambda _:None)
        case.store.finish(job,result=result);render=case.store.get_job(job['id']);jobdir=case.root/'jobs'/job['id']
        if not result['qc']['passed'] or result['qc']['human_final_video_accepted'] or case.store.get(current['id'])['document']!=before:raise AssertionError('Full QC/immutable project contract')
        try:case.store.final_video(job['id'])
        except WorkflowError as error:
            if error.code!='HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED':raise
        else:raise AssertionError('Final human review gate bypassed')
        preview_path=manager.video_path(current['id'],preview['timeline_version']);previewdir=preview_path.parent
        if file_sha(previewdir/'narrated-mix.wav')!=file_sha(jobdir/'narrated-mix.wav') or file_sha(previewdir/'subtitles.ass')!=file_sha(jobdir/'subtitles.ass'):raise AssertionError('Preview/final PCM or ASS differs')
        validate_bundle(case.config,before,jobdir)
        for name in ('final.mp4','timeline.json','timeline-render.json','subtitles.json','subtitles.ass','narrated-mix.wav','narrated-media-mix.json',
                'narrated-audio-filter.txt','audio-balance.json','audio-stem-manifest.json','audio-reference-filter.txt','audio-music-filter.txt',
                'audio-reference.f32le','audio-music.f32le','audio-final.f32le','render-manifest.json','ffprobe.json','checkpoint-render.json',
                'render-frame-qc.json','source-media-imports.json','full-qc-report.json','transport-qc-report.json','voice.wav','voice.json','tts-plan.json','voice-reuse.json'):
            shutil.copyfile(jobdir/name,out/name)
        shutil.copyfile(jobdir/'qc-report.json',out/'qc.json');shutil.copytree(jobdir/'fonts',out/'fonts');shutil.copytree(jobdir/'render-frame-qc',out/'render-frame-qc')
        for path in (REPO/'services/windows_native/fonts').glob('*'):
            if path.suffix!='.ttf':shutil.copyfile(path,out/'fonts'/path.name)
        shutil.copyfile(preview_path,out/'preview.mp4');durable_json(out/'preview.json',preview)
        durable_json(out/'narration-plan.json',case.result);durable_json(out/'cost.json',CostLedger(case.store).summary(current['id']))
        durable_json(out/'project.json',case.store.get(current['id']));durable_json(out/'job.json',render)
        from services.windows_native.source_assets import canonical_assets
        durable_json(out/'asset-provenance.json',{'assets':canonical_assets(before),'explicit_synthetic_fixture':True,'measured_narration_synthetic_PCM_not_speech':True})
        with case.store.transaction() as con:
            durable_json(out/'job-events.json',[{**dict(r),'payload':json.loads(r['payload'])} for r in con.execute('SELECT * FROM events WHERE project_id=? ORDER BY id',(current['id'],))])
        for name in ('preview','final'):
            subprocess.run([str(case.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-ss','0.35','-i',str(out/(name+'.mp4')),
                '-frames:v','1',str(out/(name+'-caption-frame.png'))],capture_output=True,check=True,timeout=30)
        manager.close();manager=None;page=catalog(case.store,current['id'],case.workspace)
        backup=create_backup(case.config,out/'backup.zip');destination=case.owned/'restored';restore=restore_backup(backup['backup_path'],destination,expected_sha256=backup['sha256'])
        restored=Store(destination);config=replace(case.config,data_root=destination)
        if catalog(restored,current['id'],case.workspace)!=page:raise AssertionError('Restored canonical editor differs')
        verify(config,restored.get(current['id'])['document']);validate_bundle(config,restored.get(current['id'])['document'],destination/'jobs'/job['id'])
        with restored.transaction() as con:restored.verified_render(job['id'],con)
        if files(case.root)!=original or file_sha(case.voice_out/'voice.wav')!=voice_sha:raise AssertionError('Original media or prepared voice changed')
        for name in ('assets','originals'):shutil.copytree(case.root/name,out/name)
        durable_json(out/'backup-restore.json',{'backup':backup,'restore':restore,'catalog_equal':True,'physical_origins_and_render_resolved_after_restore':True,
            'temporary_original_and_restore_removed_after_export':True})
        receipt={'schema_version':'native-narrated-media-tracks-render-proof-v1','synthetic_tones_not_speech':True,'synthetic_measured_narration_fixture':True,
            'saved_ASR_fixture':False,'signed_human_fixture':True,'fake_DOM':True,'project_id':current['id'],'job_id':job['id'],'actual_uploads':3,
            'signed_controller_requests':6,'imports':3,'timeline_version':before['canonical_timeline']['version'],'actual_waveform_measurement':True,
            'actual_preview_render_and_full_QC':True,'matching_preview_final_PCM_sha256':file_sha(jobdir/'narrated-mix.wav'),
            'matching_preview_final_ASS_sha256':file_sha(jobdir/'subtitles.ass'),'immutable_source_media':original,'original_prepared_voice_sha256':voice_sha,
            'source_project_document_unchanged':True,'backup_restore_passed':True,'final_download_blocked_without_final_review':True,
            'human_final_video_accepted':False,'real_provider_calls':0,'new_ASR_or_TTS_calls':0,'paid_calls':0,'browser_rendered':False,
            'owner_UAT':False,'genuine_speech_quality_accepted':False,'publishing_enabled':False,'production_deployed':False,
            'complete_artifact_B_acceptance':False,'owned_temporary_data_cleaned_after_export':True,
            'exports':{p.relative_to(out).as_posix():file_sha(p) for p in out.rglob('*') if p.is_file()}}
        durable_json(out/'evidence.json',receipt);print(json.dumps({k:v for k,v in receipt.items() if k not in {'exports','immutable_source_media'}},ensure_ascii=False))
    finally:
        if server is not None:server.shutdown();server.server_close()
        if manager is not None:manager.close()
        if hasattr(case,'temp'):case.temp.cleanup()

if __name__=='__main__':main()
