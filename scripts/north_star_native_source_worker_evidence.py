"""Retained local-real Native source worker proof; synthetic media and MOCK review.

Never accepts Owner UAT, invokes ASR/TTS, publishes or touches accepted projects.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.windows_native import auto_edit_analysis,auto_edit_timeline
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import Runner
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.store import Store
from services.windows_native.tests.test_auto_edit_analysis import saved_asr


def measure_frames(store,runner,project):
    before=project['document']['canonical_timeline']
    job=store.enqueue(project['id'],project['revision'],'media_frames',uuid.uuid4().hex)
    assert runner.run_one()
    saved=store.get_job(job['id'])
    if saved['status']!='succeeded':raise RuntimeError(saved['error'])
    current=auto_edit_timeline.view(store,project['id'])
    if current['document']['canonical_timeline']!=before:raise AssertionError('Pixel job changed canonical timeline')
    return current,saved


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--evidence-dir',type=Path,required=True)
    parser.add_argument('--edited-timeline',action='store_true')
    parser.add_argument('--music',action='store_true')
    parser.add_argument('--audio-processing',action='store_true')
    parser.add_argument('--broll',action='store_true')
    parser.add_argument('--duplicate-source',action='store_true')
    parser.add_argument('--auto-shorts',action='store_true')
    parser.add_argument('--final-effects-preview',action='store_true')
    parser.add_argument('--manual-reframe',action='store_true')
    parser.add_argument('--media-frames',action='store_true')
    parser.add_argument('--aspect-ratio',choices=('9:16','16:9','1:1','4:5'),default='4:5')
    parser.add_argument('--explicit-fixture-owned-provenance',action='store_true')
    args=parser.parse_args();root=args.data_root.resolve();out=args.evidence_dir.resolve()
    if args.auto_shorts and args.duplicate_source:raise ValueError('Choose one fresh draft derivation per evidence run')
    if root.parent!=Path('C:/') or not root.name.startswith('vf-native-fixture-') or root.exists():
        raise ValueError('Fresh isolated synthetic Native root required')
    if out.exists() or out==ROOT or ROOT in out.parents or out==root or root in out.parents:
        raise ValueError('Fresh external evidence directory required')
    absent=root.parent/(root.name+'-absent-secrets')
    config=Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
    config.validate_data_root();root.mkdir();store=Store(root)
    source=root/'synthetic-tone-NOT-SPEECH.mp4'
    subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n',
        '-f','lavfi','-i','testsrc2=s=320x240:r=30:d=3','-f','lavfi','-i','sine=frequency=880:duration=1',
        '-af','adelay=1000,apad=whole_dur=3','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
        '-c:a','aac','-t','3',str(source)],check=True,capture_output=True,timeout=30)
    asset=ingest_media(config,source,'video/mp4','Explicit synthetic worker source.mp4',rights_confirmed=True,illustration=False)
    if args.explicit_fixture_owned_provenance:
        asset.update(rights_status='owned',license='locally_generated_synthetic_fixture',source_type='synthetic_fixture',
            provider='local-ffmpeg-fixture',source_reference=source.name,
            generation_provenance={'explicit_fixture':True,'workflow':'FFmpeg lavfi testsrc2 and sine',
                'synthetic_tone_not_speech':True,'no_external_media_download':True})
    project=store.create('Source worker — synthetic technology fixture','','media',production_quality=True)
    project=store.append_media(project['id'],project['revision'],asset)
    with store.transaction() as con:
        doc=project['document'];doc['media_analysis']=[saved_asr(asset)]
        con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(doc,ensure_ascii=False),project['id']))
        store.version(con,project['id'])
    project=store.get(project['id']);runner=Runner(store,Pipeline(config))
    job=store.enqueue(project['id'],project['revision'],'auto_edit_analysis',uuid.uuid4().hex)
    assert runner.run_one()
    if store.get_job(job['id'])['status']!='succeeded':raise RuntimeError(store.get_job(job['id'])['error'])
    bundle=auto_edit_analysis.view(store,project['id']);analysis=bundle['analyses'][0]['analysis']
    project=auto_edit_timeline.create(store,project['id'],bundle['revision'],{
        'analysis_id':analysis['analysis_id'],'transcript_id':analysis['transcript']['transcript_id'],'aspect_ratio':args.aspect_ratio})
    if args.edited_timeline:
        from services.windows_native.source_linked_edit import edit as linked_edit
        from services.windows_native.source_settings import configure
        clip=project['shot_timeline']['shots'][0]['shot_id']
        project=linked_edit(store,project['id'],project['revision'],{'expected_version':1,
            'operation':{'type':'trim','clip_id':clip,'source_start':.3,'source_end':2.5}})
        project=linked_edit(store,project['id'],project['revision'],{'expected_version':2,
            'operation':{'type':'split','clip_id':clip,'at_seconds':1.1}})
        project=configure(store,project['id'],project['revision'],{'expected_version':3,
            'aspect_ratio':args.aspect_ratio,'subtitle_template_ref':'karaoke-gold@v1'})
    if args.music:
        from services.windows_native.music import ingest_music
        music_path=root/'explicit-synthetic-music.wav'
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n',
            '-f','lavfi','-i','sine=frequency=220:duration=1','-c:a','pcm_s16le',str(music_path)],
            check=True,capture_output=True,timeout=30)
        music=ingest_music(config,music_path,'audio/wav','Explicit synthetic music.wav',rights_confirmed=True)
        project=store.set_music(project['id'],project['revision'],music)
    if args.audio_processing:
        from services.windows_native.source_settings import configure
        project=configure(store,project['id'],project['revision'],{
            'expected_version':project['shot_timeline']['version'],
            'audio_processing':{'normalize_original_audio':True,'normalize_music':True,'duck_music':True}})
    frame_job=None
    if args.broll:
        from PIL import Image,ImageDraw
        from services.windows_native import source_broll
        image_path=root/'synthetic-broll.png'
        image=Image.new('RGB',(1080,1350),(16,43,98));draw=ImageDraw.Draw(image)
        draw.rounded_rectangle((160,260,920,1090),radius=65,fill=(35,130,170))
        draw.rectangle((230,390,850,480),fill=(210,220,235))
        draw.rectangle((230,550,690,610),fill=(145,195,220))
        draw.ellipse((680,750,820,890),fill=(235,190,55));image.save(image_path)
        supporting=ingest_media(config,image_path,'image/png','Xin chào synthetic supporting.png',rights_confirmed=True,illustration=True)
        supporting['explicit_fixture']=True
        project=store.append_media(project['id'],project['revision'],supporting)
        project=auto_edit_timeline.view(store,project['id'])
        if args.media_frames:project,frame_job=measure_frames(store,runner,project)
        project=source_broll.create(store,config,project['id'],project['revision'],{'expected_version':project['shot_timeline']['version']})
        plan=project['document']['source_broll_plans'][-1]['plan'];item=plan['items'][0]
        project=source_broll.select(store,config,project['id'],project['revision'],{
            'expected_version':project['shot_timeline']['version'],'media_plan_id':plan['media_plan_id'],
            'expected_plan_version':plan['version'],'item_id':item['media_plan_item_id'],
            'asset_id':auto_edit_analysis.asset_reference(supporting)})
        plan=project['document']['source_broll_plans'][-1]['plan']
        project=source_broll.apply(store,config,project['id'],project['revision'],{
            'expected_version':project['shot_timeline']['version'],'media_plan_id':plan['media_plan_id'],
            'expected_plan_version':plan['version'],'item_ids':[item['media_plan_item_id']]})
    parent=None
    if args.media_frames and frame_job is None:project,frame_job=measure_frames(store,runner,project)
    shorts=None
    if args.auto_shorts:
        from services.windows_native.source_shorts import create as create_shorts
        parent=store.get(project['id'])
        shorts=create_shorts(store,config,project['id'],project['revision'],{
            'analysis_id':analysis['analysis_id'],'transcript_id':analysis['transcript']['transcript_id'],
            'expected_version':project['shot_timeline']['version'],'request_key':uuid.uuid4().hex,'count':3,'aspect_ratio':'9:16'})
        project=shorts['projects'][0]
        rebound=auto_edit_analysis.view(store,project['id'])
        analysis=next(item['analysis'] for item in rebound['analyses']
            if item['analysis']['analysis_id']==project['shot_timeline']['snapshot']['metadata']['source_analysis_id'])
    if args.duplicate_source:
        parent=store.get(project['id'])
        project=store.duplicate(project['id'],project['revision'])
        rebound=auto_edit_analysis.view(store,project['id'])
        analysis=next(item['analysis'] for item in rebound['analyses']
            if item['analysis']['analysis_id']==project['shot_timeline']['snapshot']['metadata']['source_analysis_id'])
    if args.manual_reframe:
        from services.windows_native.source_reframe import apply as reframe
        project=reframe(store,project['id'],project['revision'],{
            'expected_version':project['shot_timeline']['version'],'aspect_ratio':'9:16','mode':'manual_override',
            'points':[{'time':0,'x':.2,'y':.5,'zoom':1},{'time':2.9,'x':.8,'y':.5,'zoom':1.1}]})
    if args.final_effects_preview:
        from services.windows_native.source_settings import configure
        project=configure(store,project['id'],project['revision'],{
            'expected_version':project['shot_timeline']['version'],'preview_mode':'final_effects'})
    source_hashes={item.name:file_sha(item) for directory in ('assets','originals')
        for item in (root/directory).iterdir() if item.is_file()}
    manager=PreviewManager(config,store)
    try:
        manager.generate(project['id'],project['revision']);deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            preview=manager.status(project['id'])
            if preview['status'] not in {'QUEUED','RUNNING'}:break
            time.sleep(.1)
        if preview['status']!='READY':raise RuntimeError(preview.get('error') or preview['status'])
        project=store.approve(project['id'],project['revision'],'AUTOMATED SYNTHETIC MOCK REVIEW — NOT OWNER UAT',True)
        before=project['document']
        render=store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex)
        assert runner.run_one()
        render=store.get_job(render['id'])
        if render['status']!='succeeded' or not render['result']['qc']['passed']:raise RuntimeError(render['error'])
        if store.get(project['id'])['document']!=before:raise AssertionError('Worker mutated source project document')
        if parent and store.get(parent['id'])!=parent:raise AssertionError('Duplicate source mutated parent project')
        final_download_blocked=False
        try:store.final_video(render['id'])
        except WorkflowError as error:
            if error.code!='HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED':raise
            final_download_blocked=True
        if not final_download_blocked:raise AssertionError('Final download bypassed explicit final-video review')
        with store.transaction() as con:
            events=[{**dict(value),'payload':json.loads(value['payload'])} for value in con.execute(
                'SELECT * FROM events WHERE project_id=? ORDER BY id',(project['id'],))]
        out.mkdir(parents=True);jobdir=root/'jobs'/render['id']
        for name in ('final.mp4','timeline.json','timeline-render.json','subtitles.json','audio-analysis.json',
                'render-manifest.json','ffprobe.json','cost.json','renderer-receipt.json','checkpoint-render.json'):
            shutil.copyfile(jobdir/name,out/name)
        shutil.copyfile(jobdir/'qc-report.json',out/'qc.json')
        shutil.copyfile(manager.video_path(project['id'],preview['timeline_version']),out/'preview.mp4')
        durable_json(out/'preview.json',preview)
        effects_parity=None;mix_sha=None
        if args.final_effects_preview:
            preview_folder=manager.video_path(project['id'],preview['timeline_version']).parent
            attempts=list((preview_folder/'attempts').glob('effects-preview-*'))
            if len(attempts)!=1:raise AssertionError('Fresh effects preview must have one private attempt')
            attempt=attempts[0]
            for name in ('timeline-render.json','audio-analysis.json','renderer-receipt.json'):
                shutil.copyfile(attempt/name,out/('preview-'+name))
            shutil.copyfile(preview_folder/'render-manifest.json',out/'preview-render-manifest.json')
            pmanifest=json.loads((attempt/'timeline-render.json').read_bytes())
            fmanifest=json.loads((out/'timeline-render.json').read_bytes())
            def effects(manifest):
                # Each derivation assigns fresh cue identities; rendered words,
                # timings and style must match independently of those identities.
                return {'metadata':manifest['metadata'],'subtitles':[{k:v for k,v in cue.items() if k!='cue_id'}
                        for cue in manifest['subtitles']],
                    'subtitle_style':manifest['subtitle_style'],'brand':manifest['brand'],
                    'visual_clips':[{key:value for key,value in clip.items() if key!='uri'}
                        for clip in manifest['visual_clips']]}
            effects_parity=effects(pmanifest)==effects(fmanifest)
            mix_sha=file_sha(Path(pmanifest['audio']['mix_uri']))
            if not effects_parity or mix_sha!=file_sha(Path(fmanifest['audio']['mix_uri'])):
                raise AssertionError('Preview/final effects or canonical PCM mix differ')
            subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-ss','0.35',
                '-i',str(out/'preview.mp4'),'-frames:v','1',str(out/'preview-caption-frame.png')],
                check=True,capture_output=True,timeout=30)
        durable_json(out/'transcript.json',analysis['transcript'])
        durable_json(out/'scene-analysis.json',analysis['scenes'])
        durable_json(out/'highlight-analysis.json',analysis['highlights'])
        durable_json(out/'silence-decisions.json',analysis['silence_decisions'])
        if args.broll:
            durable_json(out/'media-plan.json',project['document']['source_broll_plans'][-1])
        from services.windows_native.source_assets import canonical_assets
        durable_json(out/'asset-provenance.json',{'explicit_fixture':True,'assets':canonical_assets(project['document']),
            'source_kind':'generated synthetic testsrc + tone','speech_recognition':'saved ASR fixture; no inference'})
        durable_json(out/'project.json',store.get(project['id']))
        if parent:durable_json(out/'parent-project.json',parent)
        if shorts:durable_json(out/'auto-shorts.json',shorts)
        if args.manual_reframe:durable_json(out/'reframe-plan.json',project['document']['canonical_timeline']['snapshot']['metadata']['source_reframe_plan'])
        if frame_job:
            from services.windows_native.media_frame_analysis import view as frame_view,frame_path
            frame_bundle=frame_view(store,project['id'])
            durable_json(out/'media-frame-analysis.json',frame_bundle)
            durable_json(out/'media-frame-job.json',frame_job)
            rankings=auto_edit_analysis.view(store,project['id'])
            durable_json(out/'scene-ranking.json',rankings['analyses'][0]['scenes'])
            durable_json(out/'highlight-ranking.json',rankings['analyses'][0]['highlights'])
            for observation in frame_bundle['observations']:
                for frame in observation['frames']:
                    shutil.copyfile(frame_path(root,frame),out/('source-'+frame['frame_id']+'.png'))
        durable_json(out/'job-events.json',events)
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-ss','0.35',
            '-i',str(out/'final.mp4'),'-frames:v','1',str(out/'caption-frame.png')],check=True,capture_output=True,timeout=30)
        for directory in ('assets','originals'):
            for item in (root/directory).iterdir():
                if item.is_file() and file_sha(item)!=source_hashes[item.name]:raise AssertionError('Immutable source changed')
        receipt={'schema':'native-source-worker-evidence-v1','explicit_fixture':True,'synthetic_media':True,
            'requested_aspect_ratio':args.aspect_ratio,'explicit_fixture_owned_provenance':args.explicit_fixture_owned_provenance,
            'linked_source_edits_and_karaoke':bool(args.edited_timeline and not args.auto_shorts),
            'canonical_music_added':any(track['kind']=='music' and track['clips'] for track in project['document']['canonical_timeline']['snapshot']['tracks']),
            'canonical_audio_processing_requested':bool(project['document']['canonical_timeline']['snapshot']['metadata'].get('source_audio_processing')),
            'canonical_supporting_broll_added':any(track['kind']=='broll' and track['clips'] for track in project['document']['canonical_timeline']['snapshot']['tracks']),
            'auto_shorts_drafts_created':bool(shorts),
            'final_effects_preview':bool(preview['manifest'].get('rendering_effects_parity')),
            'explicit_manual_reframe':args.manual_reframe,
            'automatic_subject_tracking_performed':False,
            'local_measured_pixel_frames_saved':bool(frame_job),
            'semantic_vision_provider_status':'NOT_CONFIGURED',
            'semantic_vision_inference_performed':False,
            'matching_preview_final_effects_manifests':effects_parity,
            'matching_preview_final_canonical_pcm_sha256':mix_sha,
            'auto_shorts_generated_count':shorts['batch']['generated_count'] if shorts else None,
            'auto_shorts_requested_count':shorts['batch']['requested_count'] if shorts else None,
            'auto_shorts_rendered_count':1 if shorts else None,
            'source_project_duplicated_with_rebound_evidence':args.duplicate_source,
            'parent_project_id':parent['id'] if parent else None,
            'parent_project_unchanged':bool(parent),
            'saved_asr_fixture':True,'pre_render_human_review':'AUTOMATED MOCK — NOT OWNER UAT',
            'project_id':project['id'],'job_id':render['id'],'local_real_worker':True,'local_real_full_qc':True,
            'timeline_sha256':project['document']['canonical_timeline']['sha256'],
            'immutable_sources':source_hashes,'source_project_document_unchanged':True,
            'final_download_blocked_without_final_review':final_download_blocked,'human_final_video_accepted':False,
            'new_external_provider_calls':0,'new_tts_calls':0,'paid_operations':0,
            'exports':{item.name:file_sha(item) for item in out.iterdir() if item.is_file()},
            'complete_artifact_a_acceptance':False,'ui_acceptance':False,'owner_uat':False,
            'real_provider_acceptance':False,'production_deployed':False,'external_publication':False}
        durable_json(out/'evidence.json',receipt);print(json.dumps(receipt,ensure_ascii=False))
    finally:manager.close()


if __name__=='__main__':main()
