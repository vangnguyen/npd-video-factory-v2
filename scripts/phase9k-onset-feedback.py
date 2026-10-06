"""Record the actual Owner's eight onset complaints against three current MP4s."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import digest, file_sha, write_json
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.pipeline import Config, REPO, verify_runtime
from services.windows_native.store import Store

EVIDENCE = REPO / 'evidence/post-mvp-roadmap/phase-9/9k'
CURRENT = EVIDENCE / 'audio-repair-01'
NEXT = EVIDENCE / 'audio-repair-02'
WORDS = 'Các từ có âm giọng bị lỗi xuất hiện ở đầu mỗi câu: \nCa 01: Ngày 23 tháng 4, đây là bước, bạn muốn tìm hiểu\nCa 02: Theo, điều đáng theo dõi, \nCa 04: Thứ hai, thứ ba, bạn muốn làm rõ'
NAMED = {1: {2: 'Ngày 23 tháng 4', 4: 'đây là bước', 5: 'bạn muốn tìm hiểu'},
         2: {2: 'Theo', 4: 'điều đáng theo dõi'},
         4: {3: 'Thứ hai', 4: 'thứ ba', 5: 'bạn muốn làm rõ'}}


def main():
    config = Config(); store = Store(config.data_root)
    target = NEXT / 'owner-onset-feedback.json'
    assert not target.exists(), 'Inspect any partial recording before repeating decisions'
    NEXT.mkdir(exist_ok=True)
    current = json.loads((CURRENT / 'review-manifest.json').read_bytes())
    verify_runtime(config)
    with sqlite3.connect(store.db) as con:
        assert con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0] == 0
    cases = []
    for c in current['cases']:
        p = store.get(c['project_id']); j = store.get_job(c['job_id'])
        assert p['revision'] == j['revision'] == 11 and j['status'] == 'succeeded' and j['final_review'] is None
        assert p['document'] == j['snapshot']['document'] and p['approval'] == j['snapshot']['approval']
        assert file_sha(CURRENT / f'case-{c["case"]:02}' / 'final.mp4') == c['final_sha256']
        voice = json.loads((CURRENT / f'case-{c["case"]:02}' / 'voice.json').read_bytes())
        onsets = []
        for scene, phrase in NAMED.get(c['case'], {}).items():
            unit = next(u for u in voice['units'] if u['scene'] == scene)
            onsets.append({'phrase': phrase, 'scene': scene, 'unit_index': unit['index'], 'unit_text': unit['text'],
                           'raw_voice_activity_start_seconds': unit['activity_start_seconds'],
                           'mp4_onset_seconds': round(unit['activity_start_seconds'] + 1.1, 6)})
        cases.append({'case': c['case'], 'project_id': p['id'], 'job_id': j['id'], 'job_revision': 11,
                      'snapshot_sha256': digest(j['snapshot']), 'final_sha256': c['final_sha256'],
                      'voice_sha256': voice['audio_sha256'], 'named_onsets': onsets,
                      'owner_current_version_decision': 'REVISION_REQUIRED' if onsets else 'PENDING'})
    frozen = {p.relative_to(EVIDENCE).as_posix(): file_sha(p) for p in EVIDENCE.rglob('*')
              if p.is_file() and NEXT not in p.parents and p.name not in
              {'phase9k-final-review.md', 'phase9k-handoff-matrix.md', 'real-production-checkpoint.md'}}
    backups = []
    for name in ('workflow', 'intelligence'):
        backup = Path('C:/NPD-Video-Factory/post-mvp-validation') / f'owner-before-phase9k-onset-02-{name}-20261006.sqlite3'
        assert not backup.exists(), 'Preserve existing backup'
        with sqlite3.connect(config.data_root / f'{name}.sqlite3') as source, sqlite3.connect(backup) as dest:
            source.backup(dest)
        backups.append({'path': str(backup), 'sha256': file_sha(backup)})
    receipt = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'source': 'Direct human user message in this Codex chat',
               'owner_message': WORDS, 'classification': 'OWNER_AUDIO_ONSET_REVISION_REQUIRED',
               'artifact_binding_basis': 'Most recent five audio-repair-01 MP4s presented for Owner listening in this chat',
               'earlier_all_five_repair_scope': 'Nhiều/cả 5 video — kiểm tra toàn bộ',
               'named_case_count': 3, 'named_onset_count': 8, 'cases': cases,
               'human_full_watch_claimed': False, 'human_audio_accepted': False, 'final_video_approved': False,
               'publishing_approved': False, 'backups': backups, 'frozen_prior_evidence': frozen,
               'baseline_head_sha': subprocess.check_output([str(config.git), 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()}
    write_json(target, receipt)
    decisions = []
    for c in cases:
        if not c['named_onsets']: continue
        phrases = ', '.join(s['phrase'] for s in c['named_onsets'])
        p = store.review_render(c['job_id'], 11, 'Owner — chỉ rõ lỗi đầu câu qua Codex', False, 'reject',
                                f'Lỗi âm giọng đầu câu: {phrases}. Owner feedback SHA256: {file_sha(target)}')
        assert p['revision'] == 12 and p['approval'] is None
        j = store.get_job(c['job_id'])
        assert j['final_review']['decision'] == 'reject' and j['final_review']['artifact_sha256'] == c['final_sha256']
        assert j['final_review']['snapshot_sha256'] == c['snapshot_sha256']
        decisions.append({'case': c['case'], 'project_revision': 12, 'job_id': j['id'], 'decision': j['final_review']})
    spec = importlib.util.spec_from_file_location('checks', REPO / 'scripts/phase9k-production-acceptance.py')
    checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
    other_ids = {c['project_id'] for c in cases if not c['named_onsets']}
    with sqlite3.connect(backups[0]['path']) as con:
        other_ids |= {r[0] for r in con.execute('SELECT id FROM projects')} - {c['project_id'] for c in cases}
    with sqlite3.connect(backups[0]['path']) as con:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('projects','sqlite_sequence')")]
    preserved = checks.integrity.rows_preserved(backups[0]['path'], store.db, tables)
    preserved.update(checks.integrity.rows_preserved(backups[0]['path'], store.db, ['projects'], other_ids))
    service = IntelligenceService(config, store)
    ci = checks.integrity.rows_preserved(backups[1]['path'], service.store.db)
    release = checks.protected_release(config, store, service, current)
    for name, sha in frozen.items(): assert file_sha(EVIDENCE / name) == sha
    write_json(NEXT / 'owner-negative-decisions.json', {'source_feedback_sha256': file_sha(target), 'decisions': decisions,
               'other_current_cases': [{'case': c['case'], 'revision': store.get(c['project_id'])['revision'],
                                       'final_review': store.get_job(c['job_id'])['final_review']}
                                      for c in cases if not c['named_onsets']],
               'pre_feedback_rows_preserved': preserved, 'intelligence_rows_preserved': ci,
               'accepted_release': release, 'frozen_prior_file_count': len(frozen), 'frozen_prior_files_unchanged': True,
               'native_test_or_render_dispatches': 0, 'human_accepted_final_videos': 0})
    print(json.dumps({'named_onsets': 8, 'real_negative_decisions': len(decisions), 'projects_requiring_revision': [1, 2, 4],
                      'cases_06_08_still_pending': True, 'release_unchanged': True, 'human_accepted_final_videos': 0}), flush=True)


if __name__ == '__main__': main()
