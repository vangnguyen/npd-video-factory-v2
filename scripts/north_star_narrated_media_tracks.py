"""Owned synthetic Mode A media editor/controller/render/restore evidence.

Neither fixture speech, a signed fixture human nor fake DOM accepts Owner UAT.
No provider is called. All temporary fixtures are owned and exported with a
verified recovery backup before their ordinary test teardown.
"""
import argparse,copy,json,shutil,subprocess,sys,threading,time,traceback,uuid
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
from services.windows_native.shot_preview import PreviewManager,render_narration
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
    parser=argparse.ArgumentParser();parser.add_argument('--evidence-dir',type=Path,required=True);parser.add_argument('--timeline-editor',action='store_true');parser.add_argument('--source-video-captions',action='store_true');parser.add_argument('--video-timeline',action='store_true');parser.add_argument('--visual-properties',action='store_true');parser.add_argument('--sfx',action='store_true');args=parser.parse_args();out=args.evidence_dir.resolve()
    if args.sfx and (args.timeline_editor or args.source_video_captions or args.video_timeline or args.visual_properties):parser.error('--sfx uses a separate component fixture')
    if args.visual_properties and not args.video_timeline:parser.error('--visual-properties requires --video-timeline')
    if out.exists() or out==REPO or REPO in out.parents:raise ValueError('Fresh external evidence directory required')
    out.mkdir(parents=True);case=NarratedMediaTracksTests();case.short_owned_root=args.video_timeline or args.sfx;server=manager=None
    try:
        if args.source_video_captions or args.video_timeline:
            from services.windows_native.tests.test_source_caption_mapping import prepare as mapping_prepare
            mapping_prepare(case)
        else:prepare(case)
        original=files(case.root);voice_sha=file_sha(case.voice_out/'voice.wav')
        raw,data=human_fixture('editor',workspace=case.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),case.workspace)
        server=LocalServer(0,case.config,start_worker=False,access=access);cookie,session=access.login(raw)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();current=case.store.get(case.project['id'])
        context=case.owned/'narrated-signed-controller-context.json'
        durable_json(context,{'fixture_human':True,'origin':'http://127.0.0.1:'+str(server.server_port),'workspace_id':case.workspace,
            'project':{'id':current['id'],'revision':current['revision']},'cookie':cookie,'csrf':session.csrf,
            **({'source_video_asset_id':case.video['id'],'source_video_asset_sha256':case.video['sha256']} if args.source_video_captions or args.video_timeline else {})})
        run=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(REPO/'scripts/native_source_media_tracks_http_ui.mjs'),str(context)],capture_output=True,check=True,timeout=60)
        controller=json.loads(run.stdout);durable_json(out/'signed-controller.json',controller)
        if len(controller['requests'])!=6 or controller['timeline_mode']!='narrated' or len(controller['imports'])!=3:raise AssertionError('Expected actual Mode A controller flow')
        sfx_controller=None
        if args.sfx:
            from north_star_sfx_fixture import run_sfx_controller
            original,sfx_controller=run_sfx_controller(case,server,cookie,session.csrf,context,out,original)
            from services.windows_native.narrated_timeline_editor import view as sfx_view
            durable_json(out/'timeline-editor.json',sfx_view(case.store,current['id'],case.workspace))
        if args.source_video_captions:
            from services.windows_native.source_media_tracks import add_subtitles
            from services.windows_native.shot_adapter import validate_document
            before_mapping=case.store.shot_view(current['id']);manual=[t for t in before_mapping['document']['canonical_timeline']['snapshot']['tracks'] if t['kind']=='subtitles'];shot=before_mapping['shot_timeline']['shots'][0]
            changed=case.store.mutate_shots(current['id'],before_mapping['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'source_start':.2}})
            if [t for t in changed['document']['canonical_timeline']['snapshot']['tracks'] if t['kind']=='subtitles']!=manual:raise AssertionError('Explicit human layout reflowed')
            new_import=add_subtitles(case.store,current['id'],case.subtitle_body(timebase='source',source_video_asset_id=case.video['id'],source_video_asset_sha256=case.video['sha256']),actor_ref='OWNED SYNTHETIC FIXTURE explicit source remapping')
            following=case.store.shot_view(current['id']);history=copy.deepcopy(following['document']['source_media_track_imports']);audio=[t for t in following['document']['canonical_timeline']['snapshot']['tracks'] if t['type']=='audio'];shot=following['shot_timeline']['shots'][0]
            looped=case.store.mutate_shots(current['id'],following['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'source_start':1.5}})
            validate_document(looped['document'])
            if looped['document']['source_media_track_imports']!=history or [t for t in looped['document']['canonical_timeline']['snapshot']['tracks'] if t['type']=='audio']!=audio:raise AssertionError('Mapping reflow changed import history or audio')
            actual_captions=catalog(case.store,current['id'],case.workspace)['captions']
            if [(c['timeline_start'],c['duration']) for c in actual_captions]!=[(0,.5),(.6,.9),(1.7,.9),(2.9,.4)]:raise AssertionError('Actual source-loop caption clocks differ')
            durable_json(out/'source-video-caption-mapping.json',{'schema_version':'native-source-video-caption-reflow-proof-v1','synthetic_moving_video':True,
                'video_asset':case.video,'selected_video_SHA_verified':True,'source_time_mapping_controller':controller['subtitles']['mutation'],
                'human_layout_preserved_after_source_trim':True,'explicit_new_mapping_service_import':new_import,'new_mapping_import_via_HTTP':False,
                'before_reflow':following['document']['canonical_timeline'],'after_reflow':looped['document']['canonical_timeline'],
                'reflow_caption_intervals':actual_captions,'import_history_unchanged':True,'audio_tracks_unchanged':True,
                'no_word_timestamp_inference':True,'provider_calls':0,'paid_calls':0,'browser_rendered':False,'owner_UAT':False})
        if args.video_timeline:
            from services.windows_native.narrated_timeline_editor import view as editor_view
            durable_json(context,{'fixture_human':True,'origin':'http://127.0.0.1:'+str(server.server_port),'workspace_id':case.workspace,
                'project':case.store.get(current['id']),'cookie':cookie,'csrf':session.csrf,'visual_properties':args.visual_properties})
            run=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(REPO/'scripts/native_narrated_video_http_ui.mjs'),str(context)],capture_output=True,check=True,timeout=90)
            editor_controller=json.loads(run.stdout);durable_json(out/'video-controller.json',editor_controller)
            durable_json(out/'timeline-editor.json',editor_view(case.store,current['id'],case.workspace))
        elif args.timeline_editor:
            from services.windows_native.narrated_timeline_editor import view as editor_view
            editor_context=case.owned/'timeline-controller-context.json'
            durable_json(editor_context,{'fixture_human':True,'origin':'http://127.0.0.1:'+str(server.server_port),'workspace_id':case.workspace,
                'project':case.store.get(current['id']),'cookie':cookie,'csrf':session.csrf})
            edit_run=subprocess.run([r'C:\Program Files\nodejs\node.exe',str(REPO/'scripts/native_narrated_timeline_http_ui.mjs'),str(editor_context)],capture_output=True,check=True,timeout=90)
            editor_controller=json.loads(edit_run.stdout)
            if len(editor_controller['requests'])!=9 or not editor_controller['undo_redo_exact_snapshot']:raise AssertionError('Canonical editor controller evidence incomplete')
            durable_json(out/'timeline-controller.json',editor_controller);durable_json(out/'timeline-editor.json',editor_view(case.store,current['id'],case.workspace))
        server.shutdown();server.server_close();thread.join();server=None
        current=case.store.get(current['id']);before=copy.deepcopy(current['document']);manager=PreviewManager(case.config,case.store)
        def diagnosed_preview(*values):
            try:return render_narration(*values)
            except Exception:
                (out/'preview-error.txt').write_text(traceback.format_exc(),encoding='utf-8')
                folder=values[3]
                for path in folder.rglob('*.log'):
                    target=out/'failed-preview'/path.relative_to(folder);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
                raise
        with patch('services.windows_native.shot_preview.render_narration',side_effect=diagnosed_preview):
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
        export_names=('final.mp4','timeline.json','timeline-render.json','subtitles.json','subtitles.ass','narrated-mix.wav','narrated-media-mix.json',
                'narrated-audio-filter.txt','audio-balance.json','audio-stem-manifest.json','audio-reference-filter.txt','audio-music-filter.txt',
                'audio-reference.f32le','audio-music.f32le','audio-final.f32le','render-manifest.json','ffprobe.json','checkpoint-render.json',
                'render-frame-qc.json','source-media-imports.json','full-qc-report.json','transport-qc-report.json','voice.wav','voice.json','tts-plan.json','voice-reuse.json')
        if args.video_timeline:
            from services.windows_native.narrated_video_render import artifact_names as visual_names
            export_names+=visual_names(jobdir)
        for name in export_names:
            (out/name).parent.mkdir(parents=True,exist_ok=True)
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
        if (args.timeline_editor or args.video_timeline) and editor_view(restored,current['id'],case.workspace)!=editor_view(case.store,current['id'],case.workspace):raise AssertionError('Restored undo/redo history differs')
        verify(config,restored.get(current['id'])['document']);validate_bundle(config,restored.get(current['id'])['document'],destination/'jobs'/job['id'])
        with restored.transaction() as con:restored.verified_render(job['id'],con)
        if files(case.root)!=original or file_sha(case.voice_out/'voice.wav')!=voice_sha:raise AssertionError('Original media or prepared voice changed')
        for name in ('assets','originals'):shutil.copytree(case.root/name,out/name)
        durable_json(out/'backup-restore.json',{'backup':backup,'restore':restore,'catalog_equal':True,'physical_origins_and_render_resolved_after_restore':True,
            'temporary_original_and_restore_removed_after_export':True})
        receipt={'schema_version':'native-narrated-media-tracks-render-proof-v1','synthetic_tones_not_speech':True,'synthetic_measured_narration_fixture':True,
            'saved_ASR_fixture':False,'signed_human_fixture':True,'fake_DOM':True,'project_id':current['id'],'job_id':job['id'],'actual_uploads':(4 if args.source_video_captions or args.video_timeline else 3)+int(args.sfx),
            'signed_controller_requests':6,'imports':(4 if args.source_video_captions else 3)+int(args.sfx),'timeline_version':before['canonical_timeline']['version'],'actual_waveform_measurement':True,
            'source_video_captions':args.source_video_captions,'actual_source_trim_and_loop_reflow':args.source_video_captions,
            'actual_preview_render_and_full_QC':True,'matching_preview_final_PCM_sha256':file_sha(jobdir/'narrated-mix.wav'),
            'matching_preview_final_ASS_sha256':file_sha(jobdir/'subtitles.ass'),'immutable_source_media':original,'original_prepared_voice_sha256':voice_sha,
            'source_project_document_unchanged':True,'backup_restore_passed':True,'final_download_blocked_without_final_review':True,
            'human_final_video_accepted':False,'real_provider_calls':0,'new_ASR_or_TTS_calls':0,'paid_calls':0,'browser_rendered':False,
            'owner_UAT':False,'genuine_speech_quality_accepted':False,'publishing_enabled':False,'production_deployed':False,
            'complete_artifact_B_acceptance':False,'owned_temporary_data_cleaned_after_export':True,
            'canonical_editor_controller_requests':len(editor_controller['requests']) if args.timeline_editor or args.video_timeline else 0,
            'canonical_undo_redo_exact_snapshot':args.timeline_editor or args.video_timeline,
            'canonical_editor_history_exact_after_restore':args.timeline_editor or args.video_timeline,
            'canonical_video_render':args.video_timeline,'video_editing_controller':args.video_timeline,
            'actual_SFX_media_card':args.sfx,'sfx_controller_requests':len(sfx_controller['requests']) if sfx_controller else 0,
            'actual_shared_visual_properties_widget':args.visual_properties,
            'exports':{p.relative_to(out).as_posix():file_sha(p) for p in out.rglob('*') if p.is_file()}}
        durable_json(out/'evidence.json',receipt);print(json.dumps({k:v for k,v in receipt.items() if k not in {'exports','immutable_source_media'}},ensure_ascii=False))
    finally:
        if server is not None:server.shutdown();server.server_close()
        if manager is not None:manager.close()
        if hasattr(case,'temp'):case.temp.cleanup()

if __name__=='__main__':main()
