"""Record the real Owner reply for exact full B videos; never publish or render."""
import argparse
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import canonical, digest, file_sha
from services.windows_native.hardening import Artifacts
from services.windows_native.intelligence_lineage import projection
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.pipeline import Config, REPO
from services.windows_native.store import Store

BASE = REPO / 'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03'
OUT = BASE / 'final-acceptance'
QUESTION = ('Bạn hãy xem/nghe [5 video giọng B mới](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03/review-bundle.md), '
            'rồi xác nhận duyệt 01, 02, 04, 06, 08 làm bản cuối hoặc nêu ca/đoạn cần sửa. '
            'Ca 02 (39,61s), 04 (34,62s), 06 (35,48s) ngắn hơn mục tiêu, nên cần xác nhận cả thời lượng. '
            'Task 9K yêu cầu nghiệm thu video đầy đủ; “Giọng B đạt” đã được ghi cho 8 mẫu đầu câu.')


def read(path): return json.loads(Path(path).read_bytes())


def preserve(path, value):
    raw = canonical(value); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): assert path.read_bytes() == raw, 'Immutable receipt changed: ' + str(path)
    else:
        with path.open('xb') as handle: handle.write(raw)


spec = importlib.util.spec_from_file_location('warm_production', REPO / 'scripts/phase9k-warm-production.py')
warm = importlib.util.module_from_spec(spec); spec.loader.exec_module(warm)
integrity = warm.checks.integrity


def freeze(path):
    return [{'path': str(p), 'sha256': file_sha(p), 'bytes': p.stat().st_size}
            for p in sorted(path.rglob('*')) if p.is_file() and OUT not in p.parents]


def backup(path, label):
    saved = Path('C:/NPD-Video-Factory/post-mvp-validation') / ('before-phase9k-final-' + label + '-' + uuid.uuid4().hex + '.sqlite3')
    with saved.open('xb'): pass
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(saved) as dst: src.backup(dst)
    assert integrity.table_snapshot(saved) == integrity.table_snapshot(path)
    return {'path': str(saved), 'sha256': file_sha(saved), 'table_snapshots': integrity.table_snapshot(saved)}


def record():
    config = Config(); store = Store(config.data_root); service = IntelligenceService(config, store)
    target = OUT / 'owner-final-authorization.json'
    if not target.exists():
        before = warm.verify()  # Full canonical/provenance checks before any decisions.
        assert before['human_final_video_approvals'] == 0
        preserve(OUT / 'before-final-verification.json', before)
        cases = []
        for c in before['cases']:
            bundle = service.bundle(c['research_lineage']['research_run_id'])
            assert bundle['opportunity']['status'] == 'IN_PRODUCTION'
            assert bundle['opportunity']['production_project_id'] == c['project_id']
            cases.append({**c, 'opportunity_before': bundle['opportunity'],
                          'native_artifact_files': freeze(config.data_root / 'jobs' / c['job_id'])})
        authorization = {'recorded_at': datetime.now(timezone.utc).isoformat(),
            'source': 'human_user_reply_in_codex', 'owner_message_exact': 'Duyệt',
            'question_exact': QUESTION, 'question_reply_scope': 'FIVE_EXACT_FULL_B_MP4S_AND_DISCLOSED_DURATION_EXCEPTIONS',
            'full_watch_listen_acknowledgement_in_context': True,
            'owner_accepted_full_video_results': True, 'owner_accepted_duration_exceptions': [2, 4, 6],
            'not_an_objective_ASR_word_accuracy_certification': True,
            'review_bundle_sha256': file_sha(BASE / 'review-bundle.md'),
            'review_manifest_sha256': file_sha(BASE / 'review-manifest.json'),
            'before_verification_sha256': file_sha(OUT / 'before-final-verification.json'),
            'application_head_at_recording': subprocess.check_output([str(config.git), 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
            'cases': cases, 'frozen_review_evidence': freeze(BASE),
            'backups': {'workflow': backup(store.db, 'workflow'), 'intelligence': backup(service.store.db, 'intelligence')},
            'publishing_approved': False, 'new_provider_calls': 0, 'new_tts_or_render_calls': 0}
        preserve(target, authorization)
    authorization = read(target)
    assert authorization['owner_message_exact'] == 'Duyệt' and authorization['question_exact'] == QUESTION
    assert [c['case'] for c in authorization['cases']] == [1, 2, 4, 6, 8]
    for entry in authorization['frozen_review_evidence']:
        assert file_sha(entry['path']) == entry['sha256']
    note = ('Owner trả lời “Duyệt” cho yêu cầu xem/nghe đúng năm MP4 B đầy đủ và xác nhận thời lượng đã báo, '
            'gồm ngoại lệ 02/04/06. Human reply receipt SHA256 ' + file_sha(target) + '. Không cho phép publishing.')
    reviews = []
    for c in authorization['cases']:
        job = store.get_job(c['job_id'])
        assert job['status'] == 'succeeded' and job['revision'] == c['revision']
        assert digest(job['snapshot']) == c['snapshot_sha256']
        assert file_sha(config.data_root / 'jobs' / job['id'] / 'final.mp4') == c['final_sha256']
        store.review_render(job['id'], job['revision'], 'Owner — duyệt video B đầy đủ qua Codex', True, 'approve', note)
        reviews.append({'case': c['case'], **store.final_video(job['id'])['final_review']})
    preserve(OUT / 'native-final-decisions.json', {'owner_authorization_sha256': file_sha(target), 'reviews': reviews,
             'human_final_video_approvals': 5, 'new_tts_or_render_calls': 0, 'published': False})
    queue = []
    for c in authorization['cases']:
        opportunity = service.bundle(c['research_lineage']['research_run_id'])['opportunity']
        old = c['opportunity_before']
        assert opportunity['id'] == old['id'] and opportunity['status'] == 'PRODUCED'
        assert opportunity['version'] == old['version'] + 1
        fields = {'version', 'updated_at', 'status'}
        assert {k: v for k, v in opportunity.items() if k not in fields} == {k: v for k, v in old.items() if k not in fields}
        queue.append({'case': c['case'], 'opportunity': opportunity})
    preserve(OUT / 'produced-opportunities.json', {'cases': queue, 'produced': 5, 'published': False})
    print(json.dumps({'human_final_approvals_recorded': 5, 'opportunity_status_PRODUCED': 5, 'new_provider_render_calls': 0}))


def verified_state():
    config = Config(); store = Store(config.data_root); service = IntelligenceService(config, store)
    authorization = read(OUT / 'owner-final-authorization.json'); decisions = read(OUT / 'native-final-decisions.json')
    assert decisions['owner_authorization_sha256'] == file_sha(OUT / 'owner-final-authorization.json')
    for entry in authorization['frozen_review_evidence']:
        assert file_sha(entry['path']) == entry['sha256'], 'Historical reviewed evidence changed'
    for name, sha in read(BASE / 'owner-B-approval.json')['frozen_prior_evidence'].items(): assert file_sha(REPO / name) == sha
    get = integrity.http_reader(); assert get('/api/health')['status'] == 'ready'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open('http://127.0.0.1:8026/api/session', timeout=10) as response: response.read()
    cases = []
    for c, d in zip(authorization['cases'], decisions['reviews']):
        job = store.final_video(c['job_id']); p = store.get(c['project_id']); out = config.data_root / 'jobs' / job['id']
        assert job['final_review'] == {k: v for k, v in d.items() if k != 'case'}
        assert p['document'] == job['snapshot']['document'] and p['approval'] == job['snapshot']['approval']
        assert p['revision'] == c['revision'] and p['script_review']['current']
        assert digest(job['snapshot']) == c['snapshot_sha256'] and projection(p['document']) == c['research_lineage']
        assert job['final_review']['artifact_sha256'] == c['final_sha256']
        for entry in c['native_artifact_files']: assert file_sha(entry['path']) == entry['sha256']
        assert Artifacts(out, job).load('tts') and Artifacts(out, job).load('render')
        bundle = service.bundle(c['research_lineage']['research_run_id']); service.verify_sources(bundle['sources'], bundle['findings'])
        opportunity = bundle['opportunity']; assert opportunity['status'] == 'PRODUCED' and opportunity['production_project_id'] == p['id']
        assert get('/api/jobs/' + job['id'] + '/artifacts')['final_review'] == job['final_review']
        url = 'http://127.0.0.1:8026/api/jobs/' + job['id'] + '/final'
        with opener.open(url, timeout=30) as response:
            served = hashlib.sha256(response.read()).hexdigest(); code = response.status
            disposition = response.headers.get('Content-Disposition', '')
        assert code == 200 and served == c['final_sha256'] and 'attachment' in disposition
        req = urllib.request.Request(url, headers={'Range': 'bytes=100-199'})
        with opener.open(req, timeout=10) as response: ranged = response.read(); range_code = response.status
        with (out / 'final.mp4').open('rb') as video: video.seek(100); expected = video.read(100)
        assert range_code == 206 and ranged == expected
        cases.append({'case': c['case'], 'project_id': p['id'], 'job_id': job['id'], 'revision': p['revision'],
            'final_sha256': served, 'snapshot_sha256': c['snapshot_sha256'], 'final_review': job['final_review'],
            'video_duration_seconds': c['video_duration_seconds'], 'duration_exception_accepted': c['case'] in [2, 4, 6],
            'research_lineage': c['research_lineage'], 'opportunity_id': opportunity['id'], 'opportunity_version': opportunity['version'],
            'opportunity_status': opportunity['status'], 'final_HTTP_200_byte_exact': True, 'final_range_seek': 'PASS'})
    backups = authorization['backups']
    for b in backups.values(): assert file_sha(b['path']) == b['sha256']
    workflow = integrity.rows_preserved(backups['workflow']['path'], store.db)
    allowed = {c['opportunity_before']['id'] for c in authorization['cases']}
    with sqlite3.connect(backups['intelligence']['path']) as con: retained_ids = {r[0] for r in con.execute('SELECT id FROM records')} - allowed
    intelligence = integrity.rows_preserved(backups['intelligence']['path'], service.store.db, ['versions', 'decisions', 'operations'])
    intelligence.update(integrity.rows_preserved(backups['intelligence']['path'], service.store.db, ['records'], retained_ids))
    baseline = read(BASE.parent.parent / 'release-baseline.json')
    for v in baseline['final_videos']: assert file_sha(v['path']) == v['sha256']
    for name, sha in baseline['accepted_evidence'].items(): assert file_sha(BASE.parent.parent.parent / 'phase-8' / name) == sha
    assert subprocess.check_output([str(config.git), 'rev-parse', 'internal-production-v1^{}'], cwd=REPO, text=True).strip() == baseline['head_sha']
    assert len(cases) == 5
    return {'cases': cases, 'workflow_old_rows_preserved': workflow, 'intelligence_old_rows_preserved_except_five_status_updates': intelligence,
            'five_opportunity_changes_only_status_version_updated_at': True,
            'table_snapshots': {'workflow': integrity.table_snapshot(store.db), 'intelligence': integrity.table_snapshot(service.store.db)},
            'ten_accepted_phase8_videos_evidence_and_tag_unchanged': True,
            'frozen_prior_evidence_unchanged': len(read(BASE / 'owner-B-approval.json')['frozen_prior_evidence']),
            'owner_final_video_approvals': 5, 'produced_opportunities': 5,
            'main_service_restarted': False, 'new_provider_calls': 0, 'new_tts_or_render_calls': 0, 'published': False,
            'INTERNAL_PRODUCTION_READY': 'YES', 'CONTENT_INTELLIGENCE_READY': 'YES'}


def verify():
    result = verified_state()
    preserve(OUT / 'final-verification.json', result)
    rows = ['# Năm video B đã được Owner duyệt', '',
        'Reply “Duyệt” xác nhận đúng năm MP4 đầy đủ đã gửi và thời lượng thực tế, gồm các ngoại lệ 02/04/06. '
        'Quyết định Native đã lưu theo MP4/snapshot SHA; năm cơ hội ở trạng thái PRODUCED. Không xuất bản.', '']
    for c in result['cases']:
        folder = BASE / f"case-{c['case']:02}"
        rows += [f"- Ca {c['case']:02} · {c['video_duration_seconds']:.3f}s · [MP4 đã duyệt]({(folder / 'final.mp4').as_posix()}) · "
                 f"[Tải bản cuối trong Studio](http://127.0.0.1:8026/api/jobs/{c['job_id']}/final)"]
    rows += ['', 'CONTENT_INTELLIGENCE_READY = YES', '']
    target = OUT / 'accepted-videos.md'
    data = '\n'.join(rows).encode('utf-8')
    if target.exists(): assert target.read_bytes() == data
    else: target.write_bytes(data)
    print(json.dumps({'final_download_and_range_checks': 5, 'final_approvals': 5, 'produced': 5, 'CONTENT_INTELLIGENCE_READY': 'YES'}))


def persistence():
    current = verified_state(); previous = read(OUT / 'final-verification.json')
    assert current == previous, 'Accepted state changed after fresh process reopen'
    preserve(OUT / 'accepted-fresh-process-persistence.json', {'same_accepted_state_and_table_snapshots': True,
        'fresh_process_reopen': 'PASS', 'main_service_restart_performed': False,
        'owner_final_video_approvals': 5, 'CONTENT_INTELLIGENCE_READY': 'YES'})
    print(json.dumps({'accepted_fresh_process_reopen': 'PASS', 'main_service_restart_performed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=('record', 'verify', 'persistence'))
    globals()[parser.parse_args().action]()
