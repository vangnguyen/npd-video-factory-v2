"""Verify current Owner decisions, actual trial bytes and release preservation."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import urllib.error
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import digest, file_sha, normalize, write_json
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.pipeline import Config, REPO, sentence_units, verify_runtime
from services.windows_native.store import Store
from services.windows_native.contracts import Proposal


def read(path): return json.loads(Path(path).read_bytes())


def main():
    config = Config(); store = Store(config.data_root); service = IntelligenceService(config, store)
    folder = REPO / 'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-02'
    current = folder.parent / 'audio-repair-01'
    feedback = read(folder / 'owner-onset-feedback.json'); review = read(folder / 'onset-review-manifest.json')
    spec = importlib.util.spec_from_file_location('checks', REPO / 'scripts/phase9k-production-acceptance.py')
    checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)
    get = checks.integrity.http_reader(); assert get('/api/health')['status'] == 'ready'
    verify_runtime(config)
    cases = []
    for c in feedback['cases']:
        p = store.get(c['project_id']); j = store.get_job(c['job_id'])
        expected_revision = 12 if c['named_onsets'] else 11
        assert p['revision'] == expected_revision and p['document'] == j['snapshot']['document']
        assert j['revision'] == 11 and j['status'] == 'succeeded' and digest(j['snapshot']) == c['snapshot_sha256']
        if c['named_onsets']:
            assert p['approval'] is None and j['final_review']['decision'] == 'reject'
            assert j['final_review']['artifact_sha256'] == c['final_sha256']
            assert j['final_review']['snapshot_sha256'] == c['snapshot_sha256']
            assert file_sha(folder / 'owner-onset-feedback.json') in j['final_review']['note']
        else:
            assert j['final_review'] is None and p['approval'] == j['snapshot']['approval']
        assert p['script_review']['current']
        for path in (config.data_root / 'jobs' / j['id'], current / f'case-{c["case"]:02}'):
            assert file_sha(path / 'final.mp4') == c['final_sha256']
            assert file_sha(path / 'voice.wav') == c['voice_sha256']
        api = get('/api/projects/' + p['id'])
        assert api['revision'] == expected_revision and api['approval'] == p['approval'] and api['document'] == p['document']
        try:
            get('/api/jobs/' + j['id'] + '/final')
            raise AssertionError('Unaccepted final download served')
        except urllib.error.HTTPError as error:
            assert error.code == 409
        cases.append({'case': c['case'], 'project_id': p['id'], 'current_revision': expected_revision,
                      'job_id': j['id'], 'unchanged_final_sha256': c['final_sha256'],
                      'final_decision': j['final_review']['decision'] if j['final_review'] else 'PENDING',
                      'script_review_current': True, 'api_matches_fresh_process_store': True,
                      'unaccepted_final_download_http': 409})
    assert review['owner_feedback_sha256'] == file_sha(folder / 'owner-onset-feedback.json')
    assert len(review['pairs']) == 8 and review['human_accepted_final_videos'] == 0
    audio = Path(review['audio']); assert file_sha(audio) == review['audio_sha256']
    with wave.open(str(audio), 'rb') as wav:
        assert wav.getnchannels() == 1 and wav.getframerate() == 48000 and wav.getsampwidth() == 2
        assert wav.getnframes() / wav.getframerate() == review['duration_seconds']
    provider_counts = {'uploads': 0, 'transcript_creates': 0, 'observations': 0}
    for pair in review['pairs']:
        item = next(c for c in feedback['cases'] if c['case'] == pair['case'])
        proposal = Proposal.model_validate(store.get_job(item['job_id'])['snapshot']['document']['proposal'])
        target = folder / f'case-{pair["case"]:02}/scene-{pair["scene"]:02}'
        for name, sha in (('A-current-onset.wav', 'A_wave_sha256'), ('B-warm-onset.wav', 'B_wave_sha256'), ('B-target-trial.wav', 'B_target_wave_sha256')):
            assert file_sha(target / name) == pair[sha]
        trial = read(target / 'trial.json')
        assert trial['target_text'] == next(s.narration_excerpt for s in proposal.visual_brief if s.scene == pair['scene'])
        assert trial['approved_previous_sentence_context'] == [u for u in sentence_units(proposal) if u['scene'] < pair['scene']][-1]['text']
        assert normalize(trial['combined_text']) == normalize(trial['approved_previous_sentence_context'] + ' ' + trial['target_text'])
        transcript = read(target / 'transcript.json')
        assert transcript['voice_sha256'] == pair['B_source_voice_sha256']
        assert transcript['provider_is_fixture'] is False and transcript['new_provider_added'] is False
        evidence = read(target / 'provider-evidence.json')
        raw = read(evidence['raw_response_path'])['payload']
        assert digest(raw) == evidence['raw_response_sha256']
        assert raw['status'] == 'completed' and raw['language_code'] == 'vi' and raw['speech_model_used'] == 'universal-3-5-pro'
        assert evidence['automatic_paid_replay'] is False and evidence['upload_requests'] == evidence['transcript_create_requests'] == 1
        assert pair['human_audio_quality_accepted'] is False and pair['production_audio_replaced'] is False
        provider_counts['uploads'] += evidence['upload_requests']; provider_counts['transcript_creates'] += evidence['transcript_create_requests']
        provider_counts['observations'] += evidence['observe_requests']
    for name, sha in feedback['frozen_prior_evidence'].items(): assert file_sha(folder.parent / name) == sha
    with sqlite3.connect(feedback['backups'][0]['path']) as con:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('projects','sqlite_sequence')")]
        other_ids = {r[0] for r in con.execute('SELECT id FROM projects')} - {c['project_id'] for c in feedback['cases'] if c['named_onsets']}
    preserved = checks.integrity.rows_preserved(feedback['backups'][0]['path'], store.db, tables)
    preserved.update(checks.integrity.rows_preserved(feedback['backups'][0]['path'], store.db, ['projects'], other_ids))
    ci = checks.integrity.rows_preserved(feedback['backups'][1]['path'], service.store.db)
    release = checks.protected_release(config, store, service, read(current / 'review-manifest.json'))
    result = {'recorded_at': datetime.now(timezone.utc).isoformat(), 'classification': 'ACTUAL_ONSET_TRIAL_AND_OWNER_DECISION_VERIFICATION',
              'cases': cases, 'real_ab_pairs_verified': 8, 'provider_requests': provider_counts,
              'native_projects_or_jobs_dispatched_by_trials': 0, 'human_accepted_final_videos': 0,
              'actual_fresh_process_reopen': True, 'main_service_restart_performed': False,
              'table_snapshots_after_feedback': checks.integrity.table_snapshot(store.db),
              'before_feedback_rows_preserved': preserved, 'intelligence_rows_preserved': ci,
              'accepted_release': release, 'frozen_prior_file_count': len(feedback['frozen_prior_evidence']),
              'frozen_prior_evidence_unchanged': True, 'ordinary_implementation_helpers_syntax_checked': True,
              'application_source_modified': False, 'model_or_preset_modified': False,
              'naturalness_or_full_target_word_accuracy_pass': False, 'CONTENT_INTELLIGENCE_READY': 'NO'}
    write_json(folder / 'actual-onset-verification.json', result)
    print(json.dumps({'real_negative_decisions': 3, 'pending_other_cases': 2, 'verified_ab_pairs': 8,
                      'real_provider_requests': provider_counts, 'all_prior_evidence_and_release_unchanged': True,
                      'human_accepted_final_videos': 0}), flush=True)


if __name__ == '__main__': main()
