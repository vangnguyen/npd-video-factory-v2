"""Revision-bound repair of the five real Native videos after actual Owner feedback."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import http.cookiejar
import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import PROFILE_SHA, canonical, digest, file_sha, normalize, write_json
from services.windows_native.editor import validate_plan
from services.windows_native.hardening import Artifacts
from services.windows_native.intelligence_lineage import projection
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.media import verify_selected_files
from services.windows_native.pipeline import Config, profile, verify_runtime
from services.windows_native.store import Store
from services.windows_native.voice_quality import resolve_policy

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / 'evidence/post-mvp-roadmap/phase-9/9k'
REPAIR = EVIDENCE / 'audio-repair-01'
ISSUE = 'Giọng nói giữa các câu không giữ được độ cao âm, bị rè, âm giọng bị xuống thấp'
SCOPE = 'Nhiều/cả 5 video — kiểm tra toàn bộ'
POLICY = 'scene-context-v1'
PARENT_SHA = '9ce137afa8ac62fdb8ce5b35fbba997013adfef3'


def read(path): return json.loads(path.read_bytes())


def load_script(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checks = load_script('old_production_checks', REPO / 'scripts/phase9k-production-acceptance.py')
diagnostics = load_script('signal_diagnostics', REPO / 'scripts/phase9k-audio-diagnostics.py')


def preserve(path, value):
    raw = canonical(value)
    if path.exists():
        assert path.read_bytes() == raw, 'Immutable evidence changed: ' + str(path)
    else:
        with path.open('xb') as dest: dest.write(raw)


def head(config):
    return subprocess.check_output([str(config.git), 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()


def prepare():
    assert not (REPAIR / 'owner-feedback.json').exists(), 'Inspect partial preparation; never repeat negative decisions'
    config = Config(); store = Store(config.data_root)
    original = read(EVIDENCE / 'final-video-review-manifest.json')
    approved = read(EVIDENCE / 'production-approval-manifest.json')
    with sqlite3.connect(store.db) as con:
        assert con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0] == 0
    verify_runtime(config)
    for case in original['cases']:
        job = store.get_job(case['job_id']); p = store.get(case['project_id'])
        assert p['revision'] == job['revision'] == 9 and job['status'] == 'succeeded' and job['final_review'] is None
        assert p['document'] == job['snapshot']['document'] and p['approval'] == job['snapshot']['approval']
        assert file_sha(case['final_mp4']) == case['final_sha256']
        assert file_sha(EVIDENCE / f"case-{case['case']:02}" / 'final.mp4') == case['final_sha256']
        assert p['script_review']['current']
        verify_selected_files(config, p['document']); validate_plan(p['document'])
    frozen = {}
    for path in EVIDENCE.rglob('*'):
        if path.is_file() and REPAIR not in path.parents and path.name not in {
                'phase9k-handoff-matrix.md', 'phase9k-final-review.md', 'real-production-checkpoint.md'}:
            frozen[path.relative_to(EVIDENCE).as_posix()] = file_sha(path)
    backups = []
    for name in ('workflow', 'intelligence'):
        target = Path('C:/NPD-Video-Factory/post-mvp-validation') / f'owner-before-phase9k-audio-repair-01-{name}-20261006.sqlite3'
        assert not target.exists(), 'Existing backups must be preserved'
        with sqlite3.connect(config.data_root / (name + '.sqlite3')) as source, sqlite3.connect(target) as dest:
            source.backup(dest)
        backups.append({'path': str(target), 'sha256': file_sha(target)})
    receipt = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'source': 'Direct human messages in this Codex chat',
               'owner_issue': ISSUE, 'owner_scope_reply': SCOPE,
               'scope_question_item_id': '["request_user_input_async","call_pLbL2oeR4vDsUiv7xtsYIYLD",0]',
               'classification': 'OWNER_AUDIO_QUALITY_REVISION_REQUIRED',
               'scope': 'Repair all five internally; reuse unchanged approved narration/graphics',
               'human_full_watch_claimed': False, 'human_audio_accepted': False, 'final_video_approved': False,
               'publishing_approved': False, 'backups': backups,
               'original_review_manifest_sha256': file_sha(EVIDENCE / 'final-video-review-manifest.json'),
               'original_media_authorization_sha256': file_sha(EVIDENCE / 'owner-media-authorization.json'),
               'frozen_original_evidence': frozen,
               'original_cases': [{k: c[k] for k in ('case', 'project_id', 'revision', 'job_id', 'final_sha256', 'snapshot_sha256')}
                                  for c in original['cases']]}
    preserve(REPAIR / 'owner-feedback.json', receipt)
    prepared = []
    for old, auth in zip(original['cases'], approved['cases']):
        assert old['case'] == auth['case']
        before = store.get(old['project_id']); before_doc = before['document']
        store.review_render(old['job_id'], old['revision'], 'Owner — phản hồi lỗi giọng qua Codex', False, 'reject',
                            ISSUE + ' | Phạm vi: ' + SCOPE + ' | receipt SHA256: ' + file_sha(REPAIR / 'owner-feedback.json'))
        p = store.get(old['project_id'])
        assert p['revision'] == 10 and p['approval'] is None and p['document'] == before_doc
        p = store.set_voice_quality(p['id'], p['revision'], POLICY)
        assert p['revision'] == 11 and p['approval'] is None
        expected = {**before_doc, 'voice_quality': p['document']['voice_quality']}
        assert p['document'] == expected and p['script_review']['current']
        reference = {'source': 'human_user_reply_in_codex', 'scope': 'AUTHORIZED_AUDIO_REPAIR_REUSES_APPROVED_SCRIPT_AND_MEDIA',
                     'owner_feedback_sha256': file_sha(REPAIR / 'owner-feedback.json'),
                     'original_media_authorization_sha256': receipt['original_media_authorization_sha256'],
                     'original_script_review_id': auth['script_review_id'], 'original_render_job_id': old['job_id'],
                     'new_audio_quality_accepted': False, 'final_video_approved': False}
        p = store.approve(p['id'], p['revision'], 'Owner — sửa giọng, dùng lại lời và hình đã duyệt', True, review_reference=reference)
        item = {'case': old['case'], 'project_id': p['id'], 'revision': p['revision'],
                'original_render_job_id': old['job_id'], 'original_final_sha256': old['final_sha256'],
                'script_sha256': auth['script_sha256'], 'script_review_id': auth['script_review_id'],
                'quality_policy': resolve_policy(p['document']), 'document_sha256': digest(p['document']),
                'approval': p['approval'], 'snapshot_sha256': digest({'document': p['document'], 'approval': p['approval']}),
                'research_lineage': projection(p['document'])}
        preserve(REPAIR / f"prepared-case-{item['case']:02}.json", item)
        prepared.append(item)
    preserve(REPAIR / 'production-approval-manifest.json', {'owner_feedback_sha256': file_sha(REPAIR / 'owner-feedback.json'),
             'parent_service_application_sha': PARENT_SHA, 'fresh_tts_child_application_sha': head(config),
             'legacy_render_function_changed': False, 'service_restarted': False, 'cases': prepared,
             'automatic_final_approval': False, 'published': False})
    print(json.dumps({'prepared': len(prepared), 'old_videos_rejected_for_audio_revision': 5,
                      'project_revision': 11, 'same_words_and_media': True, 'human_new_audio_acceptance': 0}), flush=True)


def dispatch():
    config = Config(); store = Store(config.data_root)
    manifest = read(REPAIR / 'production-approval-manifest.json')
    target = REPAIR / 'jobs.json'
    report = read(target) if target.exists() else {'cases': [], 'status': 'RUNNING_REAL_NATIVE_AUDIO_REPAIR',
              'approval_manifest_sha256': file_sha(REPAIR / 'production-approval-manifest.json'),
              'fixture_voice': False, 'publishing': False, 'automatic_final_approval': False}
    assert report['approval_manifest_sha256'] == file_sha(REPAIR / 'production-approval-manifest.json')
    for item in manifest['cases']:
        p = store.get(item['project_id'])
        assert p['revision'] == item['revision'] and p['approval'] == item['approval']
        assert digest(p['document']) == item['document_sha256']
        verify_selected_files(config, p['document']); validate_plan(p['document'])
        key = f"phase9k-audio-repair-01-{p['id']}-{p['revision']}"
        job = store.enqueue(p['id'], p['revision'], 'render', key)
        existing = next((c for c in report['cases'] if c['case'] == item['case']), None)
        if existing:
            assert existing['job_id'] == job['id']
        else:
            report['cases'].append({'case': item['case'], 'project_id': p['id'], 'revision': p['revision'],
                                   'job_id': job['id'], 'request_key': key, 'snapshot_sha256': digest(job['snapshot'])})
            write_json(target, report)
        print(json.dumps({'case': item['case'], 'job_id': job['id'], 'status': job['status']}), flush=True)


def status():
    store = Store(Config().data_root); report = read(REPAIR / 'jobs.json')
    for item in report['cases']:
        job = store.get_job(item['job_id'])
        item.update({k: job[k] for k in ('status', 'stage', 'error', 'result', 'final_review')})
    count = sum(c['status'] == 'succeeded' for c in report['cases'])
    terminal = all(c['status'] in {'succeeded', 'failed', 'interrupted'} for c in report['cases'])
    report.update(successful_jobs=count, terminal=terminal, human_audio_acceptance=0,
                  status='REPAIRED_VIDEOS_AWAIT_OWNER_LISTENING' if count == 5 else
                  'AUDIO_REPAIR_FAILURE_REQUIRES_REVIEW' if terminal else 'RUNNING_REAL_NATIVE_AUDIO_REPAIR')
    write_json(REPAIR / 'jobs.json', report)
    print(json.dumps({'status': report['status'], 'cases': [{k: c[k] for k in ('case', 'job_id', 'status', 'stage', 'error')}
                                                        for c in report['cases']]}, ensure_ascii=False), flush=True)


def verify():
    config = Config(); store = Store(config.data_root); service = IntelligenceService(config, store)
    approved = read(REPAIR / 'production-approval-manifest.json'); report = read(REPAIR / 'jobs.json')
    feedback = read(REPAIR / 'owner-feedback.json')
    assert approved['owner_feedback_sha256'] == file_sha(REPAIR / 'owner-feedback.json')
    assert len(approved['cases']) == len(report['cases']) == 5
    get = checks.integrity.http_reader(); health = get('/api/health'); assert health['status'] == 'ready'
    cases = []
    for auth, item in zip(approved['cases'], report['cases']):
        assert auth['case'] == item['case']
        job = store.get_job(item['job_id']); p = store.get(item['project_id'])
        old = store.get_job(auth['original_render_job_id'])
        assert old['final_review']['decision'] == 'reject' and ISSUE in old['final_review']['note']
        assert old['final_review']['artifact_sha256'] == auth['original_final_sha256']
        assert job['status'] == 'succeeded' and job['error'] is None and job['final_review'] is None
        assert p['revision'] == job['revision'] == auth['revision'] == 11 and p['approval'] == auth['approval']
        assert digest(p['document']) == auth['document_sha256'] and digest(job['snapshot']) == auth['snapshot_sha256']
        assert job['snapshot'] == {'document': p['document'], 'approval': p['approval']}
        assert p['script_review']['current'] and p['script_review']['review_id'] == auth['script_review_id']
        assert hashlib.sha256(p['document']['proposal']['narration'].encode('utf-8')).hexdigest() == auth['script_sha256']
        assert {k: v for k, v in p['document'].items() if k != 'voice_quality'} == old['snapshot']['document']
        verify_selected_files(config, p['document']); validate_plan(p['document'])
        assert projection(p['document']) == projection(old['snapshot']['document']) == auth['research_lineage']
        bundle = service.bundle(auth['research_lineage']['research_run_id']); service.verify_sources(bundle['sources'], bundle['findings'])
        out = config.data_root / 'jobs' / job['id']; artifacts = Artifacts(out, job)
        assert artifacts.load('tts') and artifacts.load('render')
        assert read(out / 'attempts/tts-000/tts-status.json')['status'] == 'pass'
        voice = read(out / 'voice.json'); plan = read(out / 'tts-plan.json'); render = read(out / 'render-manifest.json')
        qc = read(out / 'qc-report.json'); probe = read(out / 'ffprobe.json'); timeline = read(out / 'timeline.json')
        assert voice['profile_sha256'] == PROFILE_SHA and voice['network_blocked'] is True and voice['retries'] == 0 and voice['speed'] == 1
        assert voice['quality_policy'] == plan['quality_policy'] == auth['quality_policy'] == resolve_policy(p['document'])
        assert voice['quality_policy_sha256'] == p['document']['voice_quality']['sha256']
        assert voice['effective_sampling_parameters'] == {k: profile()['parameters'][k]
               for k in ('temperature', 'top_k', 'top_p', 'repetition_penalty', 'max_new_frames')}
        assert voice['pipeline_source_sha256'] == file_sha(REPO / 'services/windows_native/pipeline.py')
        assert voice['audio_sha256'] == file_sha(out / 'voice.wav') and len(voice['units']) == 5
        assert normalize(' '.join(u['text'] for u in voice['units'])) == normalize(p['document']['proposal']['narration'])
        assert render['approval'] == p['approval'] and render['voice_sha256'] == voice['audio_sha256'] and render['music'] is None
        assert timeline['metadata']['content_intelligence'] == auth['research_lineage']
        assert qc == job['result']['qc'] and qc['passed'] and len(qc['checks']) == 11 and all(qc['checks'].values())
        assert qc['final_sha256'] == file_sha(out / 'final.mp4') and not qc['human_final_video_accepted'] and not qc['published']
        assert abs(float(probe['format']['duration']) - qc['duration_seconds']) < .001
        api = get('/api/projects/' + p['id']); assert api['document'] == p['document'] and api['approval'] == p['approval']
        assert next(j for j in api['jobs'] if j['id'] == job['id'])['status'] == 'succeeded'
        api_artifacts = get('/api/jobs/' + job['id'] + '/artifacts')
        assert api_artifacts['qc'] == qc and api_artifacts['final_review'] is None
        target = read(EVIDENCE / f"case-{item['case']:02}" / 'storyboard-reviewed-v3.json')['duration_target']
        limits = [int(v) for v in re.findall(r'\d+', target)]
        analysis = diagnostics.inspect(out / 'voice.wav', out / 'voice.json')
        cases.append({**auth, 'job_id': job['id'], 'final_mp4': str(out / 'final.mp4'),
                      'final_sha256': qc['final_sha256'], 'voice_duration_seconds': voice['duration_seconds'],
                      'video_duration_seconds': qc['duration_seconds'], 'duration_target': target,
                      'duration_target_met': limits[0] <= qc['duration_seconds'] <= limits[-1],
                      'inference_calls': voice['inference_calls'], 'qc_checks': qc['checks'], 'signal_diagnostics': analysis,
                      'human_audio_accepted': False, 'human_final_watch_listen': 'PENDING', 'published': False})
    protected = checks.protected_release(config, store, service, read(EVIDENCE / 'production-approval-manifest.json'))
    for name, sha in feedback['frozen_original_evidence'].items(): assert file_sha(EVIDENCE / name) == sha
    for backup in feedback['backups']: assert file_sha(backup['path']) == backup['sha256']
    permitted = {c['project_id'] for c in cases}
    with sqlite3.connect(feedback['backups'][0]['path']) as con:
        other_ids = {r[0] for r in con.execute('SELECT id FROM projects')} - permitted
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('projects','sqlite_sequence')")]
    preserved = checks.integrity.rows_preserved(feedback['backups'][0]['path'], store.db, tables)
    preserved.update(checks.integrity.rows_preserved(feedback['backups'][0]['path'], store.db, ['projects'], other_ids))
    ci = checks.integrity.rows_preserved(feedback['backups'][1]['path'], service.store.db)
    return {'status': 'REAL_AUDIO_REVISIONS_TECHNICALLY_VERIFIED_HUMAN_LISTENING_PENDING',
            'cases': cases, 'application_sha': approved['fresh_tts_child_application_sha'],
            'active_parent_application_sha': approved['parent_service_application_sha'],
            'new_real_videos': 5, 'human_audio_accepted': 0, 'human_final_approved': 0,
            'audio_metrics_are_not_listening_acceptance': True, 'existing_release': protected,
            'before_repair_rows_preserved_except_five_authorized_projects': preserved,
            'before_repair_intelligence_rows_preserved': ci, 'frozen_original_phase9k_files_unchanged': len(feedback['frozen_original_evidence']),
            'tables': {'workflow': checks.integrity.table_snapshot(store.db), 'intelligence': checks.integrity.table_snapshot(service.store.db)},
            'service_restarted': False, 'publishing': False, 'CONTENT_INTELLIGENCE_READY': 'NO'}


def export():
    from PIL import Image, ImageDraw, ImageFont
    result = verify(); config = Config()
    for case in result['cases']:
        folder = REPAIR / f"case-{case['case']:02}"; folder.mkdir(exist_ok=True)
        out = Path(case['final_mp4']).parent
        for name in ('final.mp4', 'voice.wav', 'voice.json', 'tts-plan.json', 'input.json', 'ffprobe.json', 'qc-report.json',
                     'render-manifest.json', 'timeline.json', 'subtitles.ass'):
            dest = folder / name
            if dest.exists(): assert file_sha(dest) == file_sha(out / name)
            else: shutil.copyfile(out / name, dest)
        write_json(folder / 'acceptance.json', {**case, 'state': 'NEW_AUDIO_PENDING_OWNER_REVIEW',
                   'technical_qc': 'PASS', 'audio_quality': 'REQUIRES_HUMAN_LISTENING', 'CONTENT_INTELLIGENCE_READY': 'NO'})
        images = []; frames = []
        render = read(out / 'render-manifest.json')
        for scene in render['scenes']:
            cues = [c for c in render['captions'] if c['start'] >= scene['start'] and c['end'] <= scene['end']]
            cue = cues[len(cues) // 2] if cues else None
            seconds = (cue['start'] + cue['end']) / 2 if cue else (scene['start'] + scene['end']) / 2
            target = folder / f"scene-{scene['scene']:02}.png"
            if not target.exists():
                subprocess.run([str(config.ffmpeg_bin / 'ffmpeg.exe'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                                '-ss', f'{seconds:.5f}', '-i', str(out / 'final.mp4'), '-frames:v', '1', str(target)],
                               check=True, capture_output=True, timeout=30)
            with Image.open(target) as frame: images.append(frame.convert('RGB').resize((270, 480), Image.Resampling.LANCZOS))
            frames.append({'scene': scene['scene'], 'seconds': seconds, 'sha256': file_sha(target), 'mp4_sha256': case['final_sha256']})
        target = folder / 'contact-sheet.png'
        if not target.exists():
            sheet = Image.new('RGB', (1350, 532), '#09211f'); draw = ImageDraw.Draw(sheet)
            font = ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf', 25)
            draw.text((20, 10), f"Ca {case['case']:02} · Sửa giọng · {case['video_duration_seconds']:.2f}s · Chờ nghe lại", font=font, fill='#fcf9f1')
            for i, frame in enumerate(images): sheet.paste(frame, (i * 270, 52))
            sheet.save(target)
        write_json(folder / 'frames.json', {'actual_mp4_frames': frames, 'contact_sheet_sha256': file_sha(target)})
    lines = ['# Phase 9K — Năm video sửa giọng', '', 'REPAIRED_VIDEOS_AWAIT_OWNER_LISTENING', '',
             'Owner đã báo giọng thay đổi cao độ và bị rè ở nhiều/cả năm bản gốc. Các bản đó được lưu nguyên và ghi yêu cầu sửa giọng; chưa được nghiệm thu.', '',
             'Năm bản mới dùng nguyên lời đọc v2 và 25 hình/cách dựng đã duyệt. TTS đọc liền từng đoạn cảnh, dùng seed cố định; giữ model/preset Thùy Dung, thông số lấy mẫu, tốc độ 1 và 48 kHz. Không chỉnh cao độ, không làm chậm và không thêm bộ lọc âm thanh.', '',
             'Kiểm tra kỹ thuật/hash/lineage đạt. Số đo cao độ là hỗ trợ đối chiếu, không chứng minh đã hết rè hay đã đạt chất lượng nghe. Cần Owner nghe lại từng bản và xác nhận chấp nhận hoặc yêu cầu sửa.', '']
    for case in result['cases']:
        folder = REPAIR / f"case-{case['case']:02}"
        lines += [f"## Ca {case['case']:02} · {case['video_duration_seconds']:.2f} giây", '',
                  f"Mục tiêu: {case['duration_target']}. " + ('Trong mục tiêu.' if case['duration_target_met'] else 'Ngắn hơn mục tiêu; cần Owner chấp nhận thời lượng hoặc yêu cầu sửa.'), '',
                  f"[Mở video mới](<{(folder / 'final.mp4').as_posix()}>) · [Nghe WAV mới](<{(folder / 'voice.wav').as_posix()}>) · [Studio](http://127.0.0.1:8026/?project={case['project_id']})", '',
                  f"[Video gốc để đối chiếu](<{(EVIDENCE / f'case-{case["case"]:02}' / 'final.mp4').as_posix()}>)", '',
                  f"![Năm cảnh trích từ video sửa giọng](<{(folder / 'contact-sheet.png').as_posix()}>)", '',
                  f"MP4 SHA256 `{case['final_sha256']}`; job `{case['job_id']}`. QC 11/11 PASS. Audio/final human acceptance: PENDING.", '']
    lines += ['Sau khi xem/nghe năm video mới, Owner có thể xác nhận duyệt 01, 02, 04, 06, 08, gồm chất lượng giọng và thời lượng; hoặc nêu ca và đoạn cần sửa.', '',
              'INTERNAL_PRODUCTION_READY = YES', '', 'CONTENT_INTELLIGENCE_READY = NO', '']
    (REPAIR / 'review-bundle.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    write_json(REPAIR / 'review-manifest.json', {**result, 'review_bundle_sha256': file_sha(REPAIR / 'review-bundle.md')})
    write_json(REPAIR / 'actual-verification.json', result)
    print(json.dumps({'videos_exported': 5, 'technical_qc': '5/5 PASS', 'human_audio_accepted': 0,
                      'durations': {c['case']: c['video_duration_seconds'] for c in result['cases']}}, ensure_ascii=False), flush=True)


def persistence():
    result = verify(); before = read(REPAIR / 'actual-verification.json')
    assert result['tables'] == before['tables'] and result['cases'] == before['cases']
    write_json(REPAIR / 'fresh-process-persistence.json', {'fresh_process_reopen': 'PASS', 'main_service_restart': 'NOT_PERFORMED',
               'exact_current_projects_jobs_approvals_and_artifacts': 'PASS', 'state': result,
               'human_audio_acceptance': 0, 'CONTENT_INTELLIGENCE_READY': 'NO'})
    print(json.dumps({'fresh_process_reopen': 'PASS', 'same_five_jobs_artifacts_and_lineage': True}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=['prepare', 'dispatch', 'status', 'export', 'persistence'])
    globals()[parser.parse_args().action]()
