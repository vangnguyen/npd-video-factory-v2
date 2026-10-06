"""Verify actual Native outputs and preserve release/restart state without approvals."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import PROFILE_SHA,digest,file_sha,normalize,write_json
from services.windows_native.hardening import Artifacts
from services.windows_native.intelligence_lineage import projection
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.media import verify_selected_files
from services.windows_native.editor import validate_plan
from services.windows_native.pipeline import Config
from services.windows_native.store import Store

REPO=Path(__file__).resolve().parents[1];EVIDENCE=REPO/'evidence/post-mvp-roadmap/phase-9/9k'
spec=importlib.util.spec_from_file_location('checkpoint_integrity',REPO/'scripts/phase9k-verify-checkpoint.py')
integrity=importlib.util.module_from_spec(spec);spec.loader.exec_module(integrity)


def read(path): return json.loads(path.read_bytes())


def protected_release(config,store,service,production):
    baseline=read(EVIDENCE.parent/'release-baseline.json')
    original=read(EVIDENCE/'owner-authorization.json');media=read(EVIDENCE/'owner-media-authorization.json')
    for video in baseline['final_videos']: assert file_sha(video['path'])==video['sha256']
    for name,sha in baseline['accepted_evidence'].items(): assert file_sha(EVIDENCE.parent.parent/'phase-8'/name)==sha
    for package in baseline['dependencies']: assert importlib.metadata.version(package['name'])==package['version']
    for backup in [baseline['backup'],*original['backups'],*media['backups']]: assert file_sha(backup['path'])==backup['sha256']
    accepted=integrity.rows_preserved(baseline['backup']['path'],store.db)
    owner=integrity.rows_preserved(original['backups'][0]['path'],store.db)
    permitted={c['project_id'] for c in production['cases']}
    before=media['backups'][0]['path']
    with sqlite3.connect(before) as con:
        previous_ids={r[0] for r in con.execute('SELECT id FROM projects')}-permitted
        names=[r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('projects','sqlite_sequence')")]
    previous=integrity.rows_preserved(before,store.db,names)
    previous.update(integrity.rows_preserved(before,store.db,['projects'],previous_ids))
    ci=integrity.rows_preserved(media['backups'][1]['path'],service.store.db)
    git=Config().git
    assert subprocess.check_output([str(git),'rev-parse','internal-production-v1^{}'],cwd=REPO,text=True).strip()==baseline['head_sha']
    return {'accepted_phase8_videos_unchanged':10,'phase8_evidence_unchanged':True,'runtime_dependencies_unchanged':True,
        'accepted_release_rows_preserved':accepted,'pre_task_owner_rows_preserved':owner,
        'pre_media_rows_preserved_except_five_authorized_project_updates':previous,'pre_media_intelligence_rows_preserved':ci,
        'release_marker_unchanged':True}


def verify():
    config=Config();store=Store(config.data_root);service=IntelligenceService(config,store)
    production=read(EVIDENCE/'production-approval-manifest.json');jobs=read(EVIDENCE/'real-production-jobs.json')
    auth=read(EVIDENCE/'owner-media-authorization.json');review=read(EVIDENCE/'storyboard-media-review/review-manifest.json')
    assert file_sha(EVIDENCE/'owner-media-authorization.json')==production['owner_authorization_sha256']
    assert file_sha(EVIDENCE/'owner-media-decision.txt')==auth['owner_message_sha256']
    assert file_sha(EVIDENCE/'storyboard-media-review/review-manifest.json')==auth['review_manifest_sha256']
    assert file_sha(EVIDENCE/'storyboard-media-review-bundle.md')==auth['review_bundle_sha256']==review['review_bundle_sha256']
    assert len(production['cases'])==len(jobs['cases'])==5
    get=integrity.http_reader();health=get('/api/health');assert health['status']=='ready'
    cases=[]
    for approved,item,reviewed in zip(production['cases'],jobs['cases'],review['cases']):
        assert approved['case']==item['case']==reviewed['case']
        number=item['case'];folder=EVIDENCE/f'case-{number:02}';job=store.get_job(item['job_id']);p=store.get(item['project_id'])
        assert job['kind']=='render' and job['status']=='succeeded' and job['error'] is None
        assert job['project_id']==p['id']==approved['project_id'] and p['revision']==job['revision']==approved['revision']==9
        assert digest(p['document'])==approved['project_document_sha256'] and p['approval']==approved['approval']
        assert job['snapshot']=={'document':p['document'],'approval':p['approval']} and digest(job['snapshot'])==approved['snapshot_sha256']
        assert p['approval']['source']=='human_user_reply_in_codex' and p['approval']['review_reference']['authorization_sha256']==production['owner_authorization_sha256']
        assert p['script_review']['current'] and p['script_review']['review_id']==approved['script_review_id']
        assert hashlib.sha256(p['document']['proposal']['narration'].encode('utf-8')).hexdigest()==approved['script_sha256']
        assert job['final_review'] is None,'Final human decision is still outstanding at this checkpoint'
        assert file_sha(folder/'storyboard-reviewed-v3.json')==reviewed['storyboard_sha256']
        assert file_sha(folder/'asset-lineage-reviewed-proposal.json')==reviewed['asset_lineage_sha256']
        verify_selected_files(config,p['document']);validate_plan(p['document'])
        bundle=service.bundle(approved['research_lineage']['research_run_id']);service.verify_sources(bundle['sources'],bundle['findings'])
        lineage=projection(job['snapshot']['document']);assert lineage==approved['research_lineage']
        out=config.data_root/'jobs'/job['id'];artifacts=Artifacts(out,job)
        assert artifacts.load('tts') and artifacts.load('render')
        voice=read(out/'voice.json');render=read(out/'render-manifest.json');timeline=read(out/'timeline.json');probe=read(out/'ffprobe.json');qc=read(out/'qc-report.json')
        assert not (out/'fixture-voice-scene-projection.json').exists() and (out/'attempts/tts-000/tts-status.json').is_file()
        assert read(out/'attempts/tts-000/tts-status.json')['status']=='pass'
        assert voice['network_blocked'] is True and voice['speed']==1 and voice['profile_sha256']==PROFILE_SHA and voice['inference_calls']>0 and voice['retries']==0
        assert voice['audio_sha256']==file_sha(out/'voice.wav') and normalize(' '.join(u['text'] for u in voice['units']))==normalize(p['document']['proposal']['narration'])
        assert render['approval']==p['approval'] and render['voice_sha256']==voice['audio_sha256'] and render['music'] is None
        assert render['edit_plan_sha256']==digest(p['document']['edit_plan']) and timeline['metadata']['content_intelligence']==lineage
        assert qc==job['result']['qc'] and qc['passed'] and len(qc['checks'])==11 and all(qc['checks'].values())
        assert qc['final_sha256']==file_sha(out/'final.mp4') and not qc['human_final_video_accepted'] and not qc['published']
        assert abs(float(probe['format']['duration'])-qc['duration_seconds'])<.001
        for native,original,scene in zip(approved['native_assets'],reviewed['assets'],render['scenes']):
            assert file_sha(original['path'])==original['sha256']==native['source_sha256']
            assert file_sha(config.data_root/'originals'/native['original_id'])==native['source_sha256']
            assert native['provenance']['owner_authorization_sha256']==production['owner_authorization_sha256']
            assert scene['asset_id']==native['id'] and scene['source_sha256']==native['sha256']
            assert scene['motion']=='none' and scene['crop_strategy']=='contain' and scene['source_start']==0
        api=get('/api/projects/'+p['id']);assert api['document']==p['document'] and api['approval']==p['approval'] and api['script_review']==p['script_review']
        api_job=next(j for j in api['jobs'] if j['id']==job['id'])
        assert api_job['status']=='succeeded' and api_job['result']['qc']==qc
        api_artifacts=get('/api/jobs/'+job['id']+'/artifacts')
        assert api_artifacts['job_id']==job['id'] and api_artifacts['qc']==qc and api_artifacts['final_review'] is None
        duration_target=read(folder/'storyboard-reviewed-v3.json')['duration_target']
        limits=[int(value) for value in re.findall(r'\d+',duration_target)]
        assert 1<=len(limits)<=2
        target_met=limits[0]<=qc['duration_seconds']<=limits[-1]
        cases.append({'case':number,'project_id':p['id'],'revision':9,'job_id':job['id'],'snapshot_sha256':digest(job['snapshot']),
            'script_version':2,'script_sha256':approved['script_sha256'],'research_lineage':lineage,'final_mp4':str(out/'final.mp4'),
            'final_sha256':qc['final_sha256'],'voice_sha256':voice['audio_sha256'],'voice_duration_seconds':voice['duration_seconds'],
            'video_duration_seconds':qc['duration_seconds'],'actual_local_tts_inference_calls':voice['inference_calls'],
            'duration_target':duration_target,'duration_target_met':target_met,
            'duration_review':'WITHIN_TARGET' if target_met else 'BELOW_TARGET_OWNER_ACCEPT_OR_REVISION_REQUIRED',
            'qc_checks':qc['checks'],'artifact_integrity':'PASS','provenance':'PASS','live_studio_api_reopen':'PASS',
            'human_script_review':'OWNER_APPROVED','human_media_review':'OWNER_APPROVED','human_final_watch_listen':'PENDING'})
    protected=protected_release(config,store,service,production)
    tables={name:integrity.table_snapshot(config.data_root/name) for name in ['workflow.sqlite3','intelligence.sqlite3']}
    return {'captured_at':datetime.now(timezone.utc).isoformat(),'health':health,'tables':tables,'cases':cases,
        'protected_release':protected,'actual_new_videos':5,'actual_new_local_tts_calls':sum(c['actual_local_tts_inference_calls'] for c in cases),
        'human_script_approvals':5,'human_storyboard_media_approvals':5,'human_final_video_approvals':0,
        'actual_paid_provider_calls_this_production_step':0,'fixture_videos_counted':0,'INTERNAL_PRODUCTION_READY':'YES','CONTENT_INTELLIGENCE_READY':'NO'}


def copy_exact(source,target):
    if target.exists(): assert file_sha(target)==file_sha(source),'Preserve previous output; conflicting artifact '+str(target)
    else: shutil.copyfile(source,target)


def export():
    from PIL import Image,ImageDraw,ImageFont
    result=verify();config=Config()
    for case in result['cases']:
        number=case['case'];folder=EVIDENCE/f'case-{number:02}';out=config.data_root/'jobs'/case['job_id']
        for name in ['final.mp4','ffprobe.json','qc-report.json','voice.json','tts-plan.json','subtitles.ass','timeline.json','input.json']:
            copy_exact(out/name,folder/name)
        copy_exact(out/'render-manifest.json',folder/'native-render-manifest.json')
        write_json(folder/'render-manifest.json',{'status':'REAL_NATIVE_RENDER_AWAITING_HUMAN_FINAL_REVIEW',
            'job_id':case['job_id'],'project_id':case['project_id'],'revision':9,'final_mp4':str(folder/'final.mp4'),
            'final_sha256':case['final_sha256'],'native_manifest_path':str(out/'render-manifest.json'),
            'native_manifest_sha256':file_sha(out/'render-manifest.json'),'research_lineage':case['research_lineage'],
            'actual_native_manifest':read(out/'render-manifest.json'),'ffprobe_status':'PASS','technical_checks':case['qc_checks'],
            'artifact_integrity':'PASS','human_final_watch_listen':'PENDING','published':False})
        acceptance=read(folder/'acceptance.json');acceptance.update(new_video_generated=True,technical_video_pass=True,
            artifact_integrity='PASS',provenance='PASS',actual_render_job_id=case['job_id'],final_sha256=case['final_sha256'],
            actual_video_duration_seconds=case['video_duration_seconds'],duration_target=case['duration_target'],
            duration_target_met=case['duration_target_met'],duration_review=case['duration_review'],
            human_watch_listen_decision=None,CONTENT_INTELLIGENCE_READY='NO')
        write_json(folder/'acceptance.json',acceptance)
        render=read(out/'render-manifest.json');images=[];samples=[]
        storyboard=read(folder/'storyboard.json')
        storyboard.update(version=5,status='OWNER_APPROVED_RENDERED_AWAITING_FINAL_REVIEW',production_dispatched=True,
            actual_render_job_id=case['job_id'],timing_measured=True,actual_video_duration_seconds=case['video_duration_seconds'],
            actual_voice_duration_seconds=case['voice_duration_seconds'],final_sha256=case['final_sha256'],
            duration_target_met=case['duration_target_met'],duration_review=case['duration_review'],
            measured_scenes=[{k:scene[k] for k in ('scene','start','end','asset_id')} for scene in render['scenes']])
        write_json(folder/'storyboard.json',storyboard)
        for scene in render['scenes']:
            cues=[c for c in render['captions'] if c['start']>=scene['start'] and c['end']<=scene['end']]
            cue=cues[len(cues)//2] if cues else None
            seconds=(cue['start']+cue['end'])/2 if cue else (scene['start']+scene['end'])/2
            target=folder/f'actual-scene-{scene["scene"]:02}.png'
            if not target.exists():
                subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-loglevel','error','-nostdin','-n',
                    '-ss',f'{seconds:.5f}','-i',str(out/'final.mp4'),'-frames:v','1',str(target)],check=True,capture_output=True,timeout=30)
            with Image.open(target) as frame: images.append(frame.convert('RGB').resize((270,480),Image.Resampling.LANCZOS))
            samples.append({'scene':scene['scene'],'seconds':seconds,'path':str(target),'sha256':file_sha(target),'actual_mp4_sha256':case['final_sha256']})
        sheet=Image.new('RGB',(1350,532),'#09211f');draw=ImageDraw.Draw(sheet)
        face=ImageFont.truetype(r'C:\Windows\Fonts\seguisb.ttf',25)
        draw.text((20,10),f'Ca {number:02} · Video Native thực tế · {case["video_duration_seconds"]:.2f}s · Chờ bạn xem/nghe',font=face,fill='#fcf9f1')
        for index,picture in enumerate(images):sheet.paste(picture,(index*270,52))
        target=folder/'actual-video-contact-sheet.png'
        if not target.exists(): sheet.save(target)
        write_json(folder/'actual-video-frames.json',{'origin':'Frames extracted from the actual new Native MP4','samples':samples,
            'contact_sheet_sha256':file_sha(target),'human_watch_listen':'PENDING'})
    lines=['# Phase 9K — Xem/nghe năm video thực tế','',
        'PHASE9K_FINAL_HUMAN_WATCH_LISTEN_REVIEW_REQUIRED','',
        'Cả năm video mới dùng đúng lời đọc v2 và 25 hình/cách dựng đã duyệt. Giọng Thùy Dung được tạo mới tại PC, giữ tốc độ preset. '
        'Kiểm tra kỹ thuật và hash đạt; video cuối vẫn chờ Owner xem/nghe. Phụ đề dùng thời gian câu đo được và ước lượng theo cụm; không có word alignment.','']
    lines += ['**Thời lượng thực tế:** 01 và 08 nằm trong mục tiêu. Bản 02 dài 40,47 giây so với mục tiêu 45–60 giây; '
        '04 dài 36,04 giây và 06 dài 36,74 giây so với mục tiêu 45 giây. Lời đọc đã duyệt và tốc độ giọng được giữ nguyên. '
        'Khi xem/nghe, Owner cần xác nhận chấp nhận thời lượng này hoặc chỉ rõ bản cần sửa. QC kỹ thuật không thay thế quyết định đó.','']
    for case in result['cases']:
        folder=EVIDENCE/f'case-{case["case"]:02}'
        lines += [f'## Ca {case["case"]:02} · {case["video_duration_seconds"]:.2f} giây','',
            f'Mục tiêu: {case["duration_target"]}. '+('Trong mục tiêu.' if case['duration_target_met'] else 'Ngắn hơn mục tiêu; chờ Owner chấp nhận hoặc yêu cầu sửa.'),'',
            f'[Mở MP4](<{(folder/"final.mp4").as_posix()}>) · [Mở trong Studio](http://127.0.0.1:8026/?project={case["project_id"]})','',
            f'![Năm cảnh trích từ video thực tế](<{(folder/"actual-video-contact-sheet.png").as_posix()}>)','',
            f'MP4 SHA256 `{case["final_sha256"]}`. Job `{case["job_id"]}`. ffprobe/QC: 11/11 PASS. Quyết định xem/nghe: PENDING.','']
    lines += ['Sau khi xem và nghe đủ cả năm video, Owner có thể trả lời “Đã xem/nghe và duyệt video Phase 9K: 01, 02, 04, 06, 08 cho Windows Native”. '
        'Hoặc nêu ca/thời điểm cần sửa. Quyết định sẽ gắn với đúng hash MP4 trong bộ này. Không có xuất bản bên ngoài.','',
        'INTERNAL_PRODUCTION_READY = YES','','CONTENT_INTELLIGENCE_READY = NO','']
    (EVIDENCE/'final-video-review-bundle.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    write_json(EVIDENCE/'final-video-review-manifest.json',{'status':'PHASE9K_FINAL_HUMAN_WATCH_LISTEN_REVIEW_REQUIRED',
        'review_bundle_sha256':file_sha(EVIDENCE/'final-video-review-bundle.md'),'production_approval_manifest_sha256':file_sha(EVIDENCE/'production-approval-manifest.json'),
        'cases':result['cases'],'new_real_native_videos':5,'human_final_approvals':0,'published':False})
    write_json(EVIDENCE/'actual-production-verification.json',result)
    print(json.dumps({'actual_new_videos':5,'ffprobe_qc':'5/5 PASS','artifact_integrity':'5/5 PASS',
        'actual_local_tts_inference_calls':result['actual_new_local_tts_calls'],'human_final_approvals':0,'durations':{c['case']:c['video_duration_seconds'] for c in result['cases']}},ensure_ascii=False),flush=True)


def restart_checkpoint(stage):
    result=verify();result['stage']=stage
    if stage in {'after-restart','fresh-process-reopen'}:
        before=read(EVIDENCE/'real-video-before-restart.json')
        assert result['tables']==before['tables'],'Persisted rows changed between process checkpoints'
        assert result['cases']==before['cases'],'Video/lineage state changed between process checkpoints'
        result['actual_restart_verified']=stage=='after-restart'
        result['fresh_process_reopen_verified']=True
        for case in result['cases']:
            acceptance=read(EVIDENCE/f'case-{case["case"]:02}'/'acceptance.json')
            acceptance.update(project_state_persistence='PASS',fresh_process_reopen='PASS',
                actual_server_restart='PASS' if stage=='after-restart' else 'NOT_PERFORMED_POLICY_BLOCKED')
            write_json(EVIDENCE/f'case-{case["case"]:02}'/'acceptance.json',acceptance)
    else: result['actual_restart_verified']=False
    write_json(EVIDENCE/('real-video-'+stage+'.json'),result)
    print(json.dumps({'stage':stage,'actual_new_videos':5,'artifact_and_provenance':'5/5 PASS',
        'phase8_preserved':'10/10','actual_restart_verified':result['actual_restart_verified'],'human_final_approvals':0}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['export','before-restart','after-restart','fresh-process-reopen'])
    action=parser.parse_args().action
    export() if action=='export' else restart_checkpoint(action)
