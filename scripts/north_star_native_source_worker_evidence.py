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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--evidence-dir',type=Path,required=True)
    args=parser.parse_args();root=args.data_root.resolve();out=args.evidence_dir.resolve()
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
        'analysis_id':analysis['analysis_id'],'transcript_id':analysis['transcript']['transcript_id'],'aspect_ratio':'4:5'})
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
        durable_json(out/'transcript.json',analysis['transcript'])
        durable_json(out/'scene-analysis.json',analysis['scenes'])
        durable_json(out/'highlight-analysis.json',analysis['highlights'])
        durable_json(out/'silence-decisions.json',analysis['silence_decisions'])
        durable_json(out/'asset-provenance.json',{'explicit_fixture':True,'assets':project['document']['assets'],
            'source_kind':'generated synthetic testsrc + tone','speech_recognition':'saved ASR fixture; no inference'})
        durable_json(out/'project.json',store.get(project['id']))
        durable_json(out/'job-events.json',events)
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-ss','0.35',
            '-i',str(out/'final.mp4'),'-frames:v','1',str(out/'caption-frame.png')],check=True,capture_output=True,timeout=30)
        for directory in ('assets','originals'):
            for item in (root/directory).iterdir():
                if item.is_file() and file_sha(item)!=source_hashes[item.name]:raise AssertionError('Immutable source changed')
        receipt={'schema':'native-source-worker-evidence-v1','explicit_fixture':True,'synthetic_media':True,
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
