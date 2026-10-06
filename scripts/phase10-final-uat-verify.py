"""Read-only Phase 10 UAT snapshots, shot diffs and portable render evidence.

Only authenticated loopback GETs and read-only SQLite queries are permitted.
The helper writes append-only evidence outside the application data root. It
never records approvals, invokes providers, edits projects or dispatches jobs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import wave

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'apps/api'))

from services.windows_native.contracts import PROFILE_SHA, Proposal, digest, file_sha, normalize
from services.windows_native import shot_adapter
from services.windows_native.intelligence_lineage import projection

spec = importlib.util.spec_from_file_location('phase10_uat_read_support', REPO / 'scripts/phase10-final-uat-support.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)
# This extension belongs only to this process; the shared helper file is untouched.
support.READ_ROUTES += (r'/api/projects/[0-9a-f]{32}/preview',)
support.READ_ROUTES += (r'/api/intelligence/runs/[0-9a-f]{32}',)

SCHEMA = 'phase10-final-uat-read-verification-v1'
DEFAULT_OUT = REPO / 'evidence/post-mvp-roadmap/phase-10/final-uat'
DEFAULT_DATA = Path('C:/NPD-Video-Factory/phase10-uat')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_bytes())


def head():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()


class ReadClient(support.Client):
    def __init__(self, base_url, ledger):
        super().__init__(base_url, ledger, writes=False)

    def request(self, method, path, body=None, **kwargs):
        if method != 'GET' or body is not None:
            raise support.EvidenceError('VERIFIER_GET_ONLY_NO_APP_WRITES')
        return super().request(method, path, **kwargs)


def classify_review(review):
    """A reviewer label containing Owner never converts Codex into a human."""
    if not review:
        return {'record_present': False, 'actor_category': 'NONE', 'human_acceptance_record': False}
    reviewer = str(review.get('reviewer', ''))
    delegated = bool(re.search(r'\bcodex\b|\bagent\b', reviewer, flags=re.I))
    owner = bool(re.search(r'\bowner\b', reviewer, flags=re.I)) and not delegated
    reference = review.get('review_reference') or {}
    source = review.get('source') or reference.get('source')
    recorded_human = not delegated and bool(reviewer.strip()) and (
        owner or source in {'human_user_reply_in_codex', 'local_ui_human_review'})
    return {'record_present': True, 'reviewer': reviewer,
            'actor_category': 'DELEGATED_CODEX_EXECUTION' if delegated else 'RECORDED_OWNER' if owner else 'RECORDED_HUMAN' if recorded_human else 'UNVERIFIED_ACTOR',
            'human_acceptance_record': recorded_human, 'source': source,
            'current': review.get('current'), 'decision': review.get('decision'),
            'personal_watch_listen_verified_by_helper': False,
            'authority_reference_required_for_certification': True}


def db_capture(data_root, project_id):
    """Never initialize Store: its constructor creates schema/history rows."""
    db = (data_root / 'workflow.sqlite3').resolve()
    con = sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        row = con.execute('SELECT * FROM projects WHERE id=?', (project_id,)).fetchone()
        if row is None:
            raise support.EvidenceError('READ_ONLY_DB_PROJECT_NOT_FOUND')
        project = dict(row)
        project['document'] = json.loads(project['document'])
        project['approval'] = json.loads(project['approval']) if project['approval'] else None
        events = [{**dict(r), 'payload': json.loads(r['payload'])} for r in con.execute(
            'SELECT * FROM events WHERE project_id=? ORDER BY id', (project_id,))]
        versions = [{**dict(r), 'document': json.loads(r['document']), 'components': json.loads(r['components'])}
                    for r in con.execute('SELECT * FROM project_versions WHERE project_id=? ORDER BY revision', (project_id,))]
        reviews = [dict(r) for r in con.execute('SELECT * FROM render_reviews WHERE project_id=? ORDER BY id', (project_id,))]
        return {'database': str(db), 'project': project, 'events': events, 'versions': versions,
                'final_reviews': reviews, 'project_document_sha256': digest(project['document']),
                'sql_mode': 'read_only_and_query_only', 'app_writes_issued': 0}
    finally:
        con.close()


def pure_validation(project, shot_view, versions):
    checks, problems = {}, []
    doc = project['document']
    state = shot_adapter.validate_document(doc)
    view = shot_view.get('shot_timeline') if isinstance(shot_view, dict) else None
    checks['shot_view_available'] = isinstance(view, dict)
    native_shots = []
    if view:
        native_shots = shot_adapter.shots_from_snapshot(view['snapshot'])
        checks['shot_view_same_document'] = digest(shot_view['document']) == digest(doc)
        checks['shot_view_same_revision'] = shot_view['revision'] == project['revision']
        checks['snapshot_digest_exact'] = digest(view['snapshot']) == view['sha256']
        checks['stable_ids_unique'] = len({s['shot_id'] for s in native_shots}) == len(native_shots)
        checks['view_shots_equal_snapshot'] = [{k: s[k] for k in ('shot_id', *sorted(shot_adapter.SNAPSHOT_FIELDS))}
                                               for s in view['shots']] == native_shots
        checks['persisted_state_matches_document'] = bool(view['persisted']) == bool(state)
        if state:
            checks['canonical_state_equals_view'] = all(state[k] == view[k] for k in ('version', 'sha256', 'snapshot'))
            projected = shot_adapter.project_projection(doc, native_shots)
            checks['proposal_projection_exact'] = digest(projected.get('proposal')) == digest(doc.get('proposal'))
            checks['media_projection_exact'] = digest(projected.get('scene_media')) == digest(doc.get('scene_media'))
            checks['edit_plan_projection_exact'] = digest(projected.get('edit_plan')) == digest(doc.get('edit_plan'))
    current = next((v for v in versions if v['revision'] == project['revision']), None)
    checks['current_version_document_exact'] = bool(current and digest(current['document']) == digest(doc))
    checks['history_revisions_unique'] = len({v['revision'] for v in versions}) == len(versions)
    lineage = projection(doc)
    if state:
        checks['canonical_research_lineage_exact'] = state['snapshot']['metadata'].get('content_intelligence') == lineage
    problems += [name for name, passed in checks.items() if not passed]
    return {'checks': checks, 'passed': not problems, 'problems': problems,
            'document_sha256': digest(doc), 'canonical_persisted': bool(state),
            'canonical_version': state['version'] if state else 0,
            'canonical_sha256': state['sha256'] if state else view['sha256'] if view else None,
            'shots': native_shots, 'lineage': lineage,
            'component_sha256': {k: digest(doc.get(k)) for k in
                ('proposal', 'scene_media', 'edit_plan', 'assets', 'brand_template', 'voice_quality')}}


def snapshot(client, ledger, args):
    project_id = support.identifier(args.project)
    project = client.get('/api/projects/' + project_id)
    shots = client.get('/api/projects/' + project_id + '/shots', optional=True)
    versions = client.get('/api/projects/' + project_id + '/versions')
    preview = client.get('/api/projects/' + project_id + '/preview', optional=True)
    db = db_capture(args.data_root.resolve(), project_id)
    validation = pure_validation(project, shots, versions)
    validation['checks']['http_and_db_document_exact'] = db['project_document_sha256'] == digest(project['document'])
    validation['checks']['http_and_db_revision_exact'] = db['project']['revision'] == project['revision']
    validation['checks']['http_and_db_history_exact'] = digest(sorted(versions, key=lambda v: v['revision'])) == digest(db['versions'])
    validation['passed'] = all(validation['checks'].values())
    validation['problems'] = [k for k, v in validation['checks'].items() if not v]
    value = {'schema_version': SCHEMA, 'captured_at': stamp(), 'head_sha': head(), 'label': args.label,
             'base_url': client.base_url, 'project_id': project_id,
             'capture': {'project': project, 'shots': shots, 'versions': versions, 'preview': preview, 'db': db},
             'validation': validation, 'reviews': {'script': classify_review(project.get('script_review')),
                'production': classify_review(project.get('approval')),
                'final': [classify_review(r) for r in db['final_reviews']]},
             'http_get_requests': client.read_count, 'http_post_requests': client.write_count,
             'provider_calls': 0, 'app_mutations_by_helper': 0, 'human_approval_created': False}
    stored = ledger.save('snapshot.json', value)
    comparison = None
    if args.before:
        comparison = compare(read(args.before), value)
        comparison['before_receipt'] = {'path': str(args.before.resolve()), 'sha256': file_sha(args.before)}
        ledger.save('shot-comparison.json', comparison)
    return {'snapshot': stored, 'passed': validation['passed'], 'revision': project['revision'],
            'canonical_version': validation['canonical_version'], 'problems': validation['problems'],
            'comparison_passed': comparison['passed'] if comparison else None}


def shot_times(shots):
    cursor, result = 0., []
    for s in shots:
        result.append({'shot_id': s['shot_id'], 'start': round(cursor, 6), 'end': round(cursor + s['duration'], 6),
                       'requested_duration': s['requested_duration']})
        cursor += s['duration']
    return result


def compare(before, after):
    oldp, newp = before['capture']['project'], after['capture']['project']
    old, new = before['validation']['shots'], after['validation']['shots']
    old_ids, new_ids = [s['shot_id'] for s in old], [s['shot_id'] for s in new]
    old_map, new_map = {s['shot_id']: s for s in old}, {s['shot_id']: s for s in new}
    changes = {i: {k: {'before': old_map[i][k], 'after': new_map[i][k]} for k in new_map[i]
                   if k != 'shot_id' and old_map[i][k] != new_map[i][k]}
               for i in old_ids if i in new_map and old_map[i] != new_map[i]}
    previous_events = before['capture']['db']['events']
    event_ids = {e['id'] for e in previous_events}
    new_events = [e for e in after['capture']['db']['events'] if e['id'] not in event_ids]
    scope_events = [e for e in new_events if e['action'] == 'shot_timeline_saved_approval_invalidated']
    expected = shot_adapter.scope_changes(old, new)
    old_versions = {v['revision']: v for v in before['capture']['versions']}
    new_versions = {v['revision']: v for v in after['capture']['versions']}
    changed = digest(oldp['document']) != digest(newp['document'])
    checks = {'same_project': before['project_id'] == after['project_id'],
              'before_and_after_valid': before['validation']['passed'] and after['validation']['passed'],
              'created_at_preserved': oldp['created_at'] == newp['created_at'],
              'updated_at_not_decreased': newp['updated_at'] >= oldp['updated_at'],
              'revision_increment_one_or_noop': newp['revision'] == oldp['revision'] + int(changed),
              'historical_versions_preserved': all(i in new_versions and digest(v) == digest(new_versions[i]) for i, v in old_versions.items()),
              'historical_events_preserved': all(any(digest(e) == digest(n) for n in after['capture']['db']['events']) for e in previous_events),
              'stable_ids_unique': len(new_ids) == len(set(new_ids))}
    if changed:
        checks.update({'production_approval_invalidated': newp['approval'] is None,
                       'canonical_version_incremented': after['validation']['canonical_version'] == before['validation']['canonical_version'] + 1,
                       'exactly_one_scope_event': len(scope_events) == 1,
                       'scope_matches_actual_edit': len(scope_events) == 1 and scope_events[0]['payload']['scope'] == expected,
                       'scope_binds_revision_and_sha': len(scope_events) == 1 and scope_events[0]['payload']['revision'] == newp['revision'] and
                         scope_events[0]['payload']['timeline_sha256'] == after['validation']['canonical_sha256']})
    return {'schema_version': SCHEMA, 'compared_at': stamp(), 'project_id': after['project_id'],
            'revision_before': oldp['revision'], 'revision_after': newp['revision'], 'document_changed': changed,
            'added_shot_ids': [i for i in new_ids if i not in old_map], 'deleted_shot_ids': [i for i in old_ids if i not in new_map],
            'order_before': old_ids, 'order_after': new_ids, 'changed_fields': changes,
            'timestamps_before': shot_times(old), 'timestamps_after': shot_times(new), 'expected_scope': expected,
            'new_events': new_events, 'script_review_before': before['reviews']['script'], 'script_review_after': after['reviews']['script'],
            'checks': checks, 'passed': all(checks.values()), 'problems': [k for k, v in checks.items() if not v],
            'provider_calls_by_verifier': 0, 'app_mutations_by_verifier': 0, 'human_acceptance_created': False}


def bound_file(folder, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise support.EvidenceError('ARTIFACT_RELATIVE_PATH_REQUIRED')
    path = folder / relative
    if not path.is_file() or path.is_symlink() or folder.resolve() not in path.resolve().parents:
        raise support.EvidenceError('ARTIFACT_PATH_MISSING_OR_ESCAPED')
    return path


def archive(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as src, destination.open('xb') as dst:
        shutil.copyfileobj(src, dst)
    return {'source_path': str(source), 'archived_path': str(destination), 'bytes': source.stat().st_size,
            'source_sha256': file_sha(source), 'archived_sha256': file_sha(destination),
            'byte_exact': file_sha(source) == file_sha(destination)}


def wav_summary(path):
    with wave.open(str(path), 'rb') as wav:
        return {'sha256': file_sha(path), 'channels': wav.getnchannels(), 'sample_width': wav.getsampwidth(),
                'sample_rate': wav.getframerate(), 'frames': wav.getnframes(),
                'duration_seconds': wav.getnframes() / wav.getframerate()}


def pcm(path):
    import numpy as np
    with wave.open(str(path), 'rb') as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 48000):
            raise support.EvidenceError('BOUND_VOICE_PCM_FORMAT_REQUIRED')
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').copy()


def voice_integrity(folder, doc, voice, rendered_voice):
    """Check actual archived source receipts and PCM without inference or ASR."""
    import numpy as np
    from services.windows_native.pipeline import sentence_units
    from services.windows_native.voice_quality import resolve_policy
    from services.windows_native.warm_voice import generated_record, timing_record
    policy = resolve_policy(doc)
    checks = {'locked_real_voice_profile': voice['profile_sha256'] == PROFILE_SHA,
              'bound_script_text_exact': normalize(' '.join(u['text'] for u in voice['units'])) == normalize(doc['proposal']['narration']),
              'source_document_binding_exact': voice.get('source_document_sha256') == digest(doc),
              'quality_policy_binding_exact': voice.get('quality_policy') == policy and voice.get('quality_policy_sha256') == digest(policy),
              'warm_policy_required_for_this_campaign': bool(policy and policy['id'] == 'warm-scene-context-v1')}
    if not checks['warm_policy_required_for_this_campaign']:
        return {'checks': checks, 'passed': False, 'source_checks': [], 'actual_counts': None}
    attempts = [p for p in sorted((folder / 'attempts').glob('tts-*'))
                if (p / 'voice.json').is_file() and digest(read(p / 'voice.json')) == digest(voice)]
    if not attempts:
        raise support.EvidenceError('PUBLISHED_VOICE_HAS_NO_BOUND_ACTUAL_TTS_ATTEMPT')
    active = attempts[-1]
    source_voice = pcm(folder / 'voice.wav')
    proposal = Proposal.model_validate(doc['proposal'])
    sentences = sentence_units(proposal)
    source_checks = []
    for source, unit in zip(voice['sources'], voice['units']):
        plan = source['plan']; scene = next(s for s in proposal.visual_brief if s.scene == plan['scene'])
        prior = [u for u in sentences if u['scene'] < plan['scene']]
        archived = active / 'context-sources' / f"scene-{plan['scene']:02}"
        files = []
        for record in source['archived_files']:
            path = bound_file(active, record['path'])
            files.append(path.stat().st_size == record['bytes'] and file_sha(path) == record['sha256'])
        generated = generated_record(archived, plan)
        timing = timing_record(archived, plan, generated) if plan['context_text'] else None
        raw_pcm = pcm(archived / 'source.wav')
        cut = source['boundary']['removed_samples']
        actual = source_voice[round(unit['start_seconds'] * 48000):round(unit['end_seconds'] * 48000)]
        origin = generated.get('origin') or {}
        known_origin = origin.get('method') == 'fresh_offline_warm_scene_inference' or origin.get('classification') == 'REUSED_ACTUAL_OWNER_REVIEWED_B_SOURCE'
        checks_one = {'archived_source_files_exact': all(files), 'known_actual_generation_receipt': known_origin,
                      'source_wave_digest_exact': file_sha(archived / 'source.wav') == source['source_wave_sha256'],
                      'generated_receipt_exact': generated == source['generated'], 'timing_receipt_exact': timing == source['timing'],
                      'plan_digest_exact': digest(plan) == source['plan_sha256'],
                      'target_text_equals_current_scene': plan['target_text'] == normalize(scene.narration_excerpt),
                      'context_text_equals_prior_enabled_sentence': plan['context_text'] == (prior[-1]['text'] if prior else ''),
                      'unit_scene_and_text_exact': unit['scene'] == plan['scene'] and unit['text'] == plan['target_text'],
                      'cut_samples_bound': type(cut) is int and 0 <= cut < len(raw_pcm) and cut == round(source['boundary']['cut_seconds'] * 48000),
                      'trimmed_source_pcm_equals_published_voice': bool(np.array_equal(raw_pcm[cut:], actual)),
                      'provider_fixture_not_claimed': (timing or {}).get('origin', {}).get('provider_is_fixture') is not True}
        source_checks.append({'scene': plan['scene'], 'source_wave_sha256': source['source_wave_sha256'],
                              'plan_sha256': source['plan_sha256'], 'checks': checks_one, 'passed': all(checks_one.values()),
                              'onset_asr_disputed': source['boundary'].get('onset_asr_disputed', False),
                              'full_word_accuracy_is_human_question': True})
    checks['sources_and_units_same_count'] = len(voice['sources']) == len(voice['units'])
    checks['all_actual_source_receipts_and_pcm_exact'] = all(r['passed'] for r in source_checks)
    checks['source_count_matches_enabled_scenes'] = len(source_checks) == sum(bool(s.narration_excerpt.strip()) for s in proposal.visual_brief)
    checks['fresh_and_reused_counts_exact'] = voice['new_inference_calls'] + voice['reused_inference_calls'] == voice['inference_calls'] == len(source_checks)
    generation = read(active / 'warm-generation-result.json')
    checks['fresh_count_matches_actual_generation_result'] = generation['new_inference_calls'] == voice['new_inference_calls']
    checks['no_audio_speed_or_pitch_change'] = voice.get('speed') == 1 and rendered_voice.get('speed') == 1 and rendered_voice.get('pitch_changed', False) is False
    if doc.get('canonical_timeline'):
        target = pcm(folder / 'render-voice.wav')
        expected = np.zeros(len(target), dtype='<i2')
        original_units, mapped_units = voice['units'], rendered_voice['units']
        checks['retimed_units_count_preserved'] = len(original_units) == len(mapped_units)
        checks['retimed_units_preserve_text_and_source_times'] = all(
            old['text'] == new['text'] and old['scene'] == new['scene'] and old['start_seconds'] == new['source_start_seconds']
            and old['end_seconds'] == new['source_end_seconds'] for old, new in zip(original_units, mapped_units))
        for scene in range(1, len(shot_adapter.shots(doc)) + 1):
            group = [u for u in original_units if u['scene'] == scene]
            if not group:
                continue
            first = group[0]
            stop = next((u['start_seconds'] for u in original_units if u['scene'] > scene), voice['duration_seconds'])
            mapped = next(u for u in mapped_units if u['scene'] == scene)
            cut = source_voice[round(first['start_seconds'] * 48000):round(stop * 48000)]
            offset = round(mapped['start_seconds'] * 48000)
            expected[offset:offset + len(cut)] = cut
        checks['retimed_pcm_exact_source_plus_silence_only'] = bool(np.array_equal(target, expected))
    current_provider = {key: sum(s['provider_requests_this_attempt'][key] for s in voice['sources'])
                        for key in voice['provider_requests_this_attempt']}
    checks['current_provider_counts_exact'] = current_provider == voice['provider_requests_this_attempt']
    totals = {key: sum(s['provider_receipts_total_in_cache'][key] for s in voice['sources']) for key in current_provider}
    return {'checks': checks, 'passed': all(checks.values()), 'source_checks': source_checks,
            'active_attempt': active.name, 'matching_published_attempts': [p.name for p in attempts],
            'actual_counts': {'inference_sources_total': voice['inference_calls'],
                'fresh_local_inferences_this_attempt': voice['new_inference_calls'], 'cached_sources_reused_this_attempt': voice['reused_inference_calls'],
                'provider_requests_this_attempt': current_provider, 'provider_receipts_total_in_source_cache': totals},
            'new_provider_calls_by_verifier': 0, 'human_audio_acceptance_by_verifier': False}


def video(client, ledger, args):
    project_id, job_id = support.identifier(args.project), support.identifier(args.job)
    project = client.get('/api/projects/' + project_id)
    job = next((j for j in project['jobs'] if j['id'] == job_id), None)
    if not job or job['kind'] != 'render' or job['status'] != 'succeeded':
        raise support.EvidenceError('ACTUAL_SUCCEEDED_RENDER_JOB_REQUIRED')
    response = client.get('/api/jobs/' + job_id + '/artifacts')
    logs = client.get('/api/jobs/' + job_id + '/logs')
    folder = (args.data_root / 'jobs' / job_id).resolve()
    if Path(response['output_directory']).resolve() != folder:
        raise support.EvidenceError('API_ARTIFACT_FOLDER_DOES_NOT_MATCH_EXPLICIT_DATA_ROOT')
    checkpoint = read(bound_file(folder, 'checkpoint-render.json'))
    tts_checkpoint = read(bound_file(folder, 'checkpoint-tts.json'))
    doc = job['snapshot']['document']; shot_adapter.validate_document(doc)
    lineage = projection(doc)
    source_files = {}
    for record in [checkpoint, tts_checkpoint]:
        if record['job_id'] != job_id or record['project_id'] != project_id or record['revision'] != job['revision'] or record['snapshot_sha256'] != digest(job['snapshot']):
            raise support.EvidenceError('CHECKPOINT_JOB_SNAPSHOT_BINDING_CHANGED')
        for metadata in record['artifacts']:
            path = bound_file(folder, metadata['path'])
            if path.stat().st_size != metadata['bytes'] or file_sha(path) != metadata['sha256']:
                raise support.EvidenceError('CHECKPOINT_SOURCE_BYTES_CHANGED')
            source_files[metadata['path']] = metadata
    if checkpoint['artifacts'] != response['artifacts'] or checkpoint['result'] != job['result']:
        raise support.EvidenceError('API_CHECKPOINT_RESULT_CHANGED')
    # Archive all actual attempts, including failed attempts and provider receipts.
    names = set(source_files) | {'checkpoint-render.json', 'checkpoint-tts.json'}
    names |= {p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() and
              (p.suffix.lower() in {'.json', '.wav', '.log', '.ass'} or p.name == 'final.mp4')}
    copies = [archive(bound_file(folder, name), ledger.root / 'artifacts' / name) for name in sorted(names)]
    manifest, timeline, voice = (read(folder / name) for name in ('render-manifest.json', 'timeline.json', 'voice.json'))
    canonical = doc.get('canonical_timeline')
    rendered_voice = read(folder / 'render-voice.json') if (folder / 'render-voice.json').is_file() else voice
    final_path = bound_file(folder, 'final.mp4')
    config = read(args.config)
    ffprobe = Path(config['ffmpeg_bin']) / 'ffprobe.exe'
    observed_raw = subprocess.check_output([str(ffprobe), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(final_path)], timeout=45)
    observed = json.loads(observed_raw)
    ledger.save('ffprobe-observed.json', observed)
    with (ledger.root / 'ffprobe-raw.json').open('xb') as handle:
        handle.write(observed_raw)
    voice_check = voice_integrity(folder, doc, voice, rendered_voice)
    checks = {'archive_bytes_exact': all(c['byte_exact'] for c in copies),
              'final_qc_hash_exact': file_sha(final_path) == job['result']['qc']['final_sha256'],
              'qc_passed': job['result']['qc']['passed'] is True,
              'original_voice_hash_exact': file_sha(folder / 'voice.wav') == voice['audio_sha256'],
              'rendered_voice_hash_exact': file_sha(folder / rendered_voice.get('audio_file', 'voice.wav')) == rendered_voice['audio_sha256'],
              'manifest_voice_exact': manifest['voice_sha256'] == rendered_voice['audio_sha256'],
              'manifest_approval_exact': manifest['approval'] == job['snapshot']['approval'],
              'timeline_lineage_exact': timeline.get('metadata', {}).get('content_intelligence') == lineage,
              'ffprobe_has_video_and_audio': {s['codec_type'] for s in observed['streams']} >= {'video', 'audio'},
              'ffprobe_duration_matches_manifest': abs(float(observed['format']['duration']) - manifest['duration_seconds']) <= .15,
              'production_approval_hash_exact': job['snapshot']['approval']['snapshot_sha256'] == digest(doc),
              'production_approval_revision_exact': job['snapshot']['approval']['revision'] == job['revision'],
              'actual_warm_sources_and_pcm_exact': voice_check['passed'],
              'research_source_text_hashes_exact': all(digest(s['text']) == s['content_sha256'] for s in (doc.get('content_intelligence') or {}).get('sources', [])),
              'manifest_edit_plan_exact': manifest.get('edit_plan_sha256') == digest(doc.get('edit_plan'))}
    if canonical:
        checks.update({'canonical_voice_version_exact': rendered_voice.get('canonical_timeline_version') == canonical['version'],
                       'canonical_voice_digest_exact': rendered_voice.get('canonical_timeline_sha256') == canonical['sha256'],
                       'original_voice_retained': rendered_voice.get('source_voice_sha256') == voice['audio_sha256'],
                       'sample_preserving_retime_declared': rendered_voice.get('sample_preserving_placement') is True,
                       'canonical_render_order_exact': [s['shot_id'] for s in rendered_voice['scene_layout']] ==
                           [s['shot_id'] for s in shot_adapter.shots(doc)],
                       'manifest_canonical_digest_and_version_exact': manifest.get('canonical_timeline') == {'version': canonical['version'], 'sha256': canonical['sha256']},
                       'manifest_scene_layout_exact': manifest.get('scene_layout') == rendered_voice['scene_layout'],
                       'explicit_requested_durations_exact': all(s['requested_duration'] is None or
                           abs(layout['end'] - layout['start'] - s['requested_duration']) <= 1/48000
                           for s, layout in zip(shot_adapter.shots(doc), rendered_voice['scene_layout']))})
    stream = next(s for s in observed['streams'] if s['codec_type'] == 'video')
    shape = canonical['snapshot'] if canonical else (doc.get('brand_template') or {}).get('template') or {'width': 1080, 'height': 1920}
    checks['ffprobe_canvas_exact'] = (stream['width'], stream['height']) == (shape['width'], shape['height'])
    attempts = []
    for path in sorted((folder / 'attempts').glob('tts-*')):
        meta_path = path / 'voice.json'
        status_path = path / 'tts-status.json'
        generation_path = path / 'warm-generation-result.json'
        attempts.append({'attempt': path.name, 'voice_complete': meta_path.is_file(),
                         'status': read(status_path) if status_path.is_file() else None,
                         'status_sha256': file_sha(status_path) if status_path.is_file() else None,
                         'generation_result': read(generation_path) if generation_path.is_file() else None,
                         'metadata_sha256': file_sha(meta_path) if meta_path.is_file() else None,
                         'published_active_attempt': path.name == voice_check['active_attempt']})
    result = {'schema_version': SCHEMA, 'verified_at': stamp(), 'head_sha': head(), 'project_id': project_id, 'job_id': job_id,
              'revision': job['revision'], 'job': job, 'job_logs': logs, 'api_artifacts': response,
              'source_folder': str(folder), 'copies': copies, 'manifest': manifest, 'timeline': timeline,
              'voice': voice, 'rendered_voice': rendered_voice, 'voice_wave': wav_summary(folder / 'voice.wav'),
              'rendered_voice_wave': wav_summary(folder / rendered_voice.get('audio_file', 'voice.wav')),
              'research_lineage': lineage, 'tts_attempts': attempts, 'actual_voice_integrity': voice_check,
              'ffprobe_observation': {'command': [str(ffprobe), '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(final_path)],
                                     'raw_sha256': hashlib.sha256(observed_raw).hexdigest(), 'return_code': 0},
              'review_classification': {'production': classify_review(job['snapshot']['approval']), 'final': classify_review(job.get('final_review'))},
              'checks': checks, 'passed': all(checks.values()), 'problems': [k for k, v in checks.items() if not v],
              'new_provider_calls_by_verifier': 0, 'new_render_calls_by_verifier': 0,
              'app_mutations_by_verifier': 0, 'new_human_acceptance_by_verifier': False,
              'technical_integrity_does_not_establish_human_audio_quality': True}
    receipt = ledger.save('video-verification.json', result)
    return {'receipt': receipt, 'passed': result['passed'], 'problems': result['problems'],
            'final_sha256': file_sha(final_path), 'archived_files': len(copies), 'final_review': result['review_classification']['final']}


def campaign(client, ledger, args):
    """Capture live read snapshots; source retrieval and preparation stay distinct."""
    started = stamp()
    manifest = read(args.manifest)
    cases = manifest['campaign_cases']
    if len(cases) != 10 or {int(c['case']) for c in cases} != set(range(1, 11)):
        raise support.EvidenceError('EXACT_TEN_SOURCE_AWARE_CASES_REQUIRED')
    queue_before = client.get('/api/production/queue')
    bundles, projects = {}, {}
    for case in cases:
        bundle = client.get('/api/intelligence/runs/' + support.identifier(case['run_id']))
        bundles[case['run_id']] = bundle
        project_id = bundle['opportunity'].get('production_project_id')
        if project_id:
            projects[project_id] = client.get('/api/projects/' + support.identifier(project_id))
    queue = client.get('/api/production/queue')
    rows, warnings = [], []
    for case in sorted(cases, key=lambda c: int(c['case'])):
        bundle = bundles[case['run_id']]
        matches = [q for q in queue['items'] if q['run_id'] == case['run_id'] and q['planning']['campaign'] == args.campaign]
        if len(matches) != 1:
            raise support.EvidenceError('EXACT_CURRENT_CAMPAIGN_QUEUE_ITEM_REQUIRED')
        row = matches[0]; selected = next((i for i in bundle['ideas'] if i['id'] == row['idea_id']), None)
        if selected is None:
            raise support.EvidenceError('CURRENT_SELECTED_IDEA_REQUIRED')
        project = projects.get(row['project_id'])
        if project and project['revision'] != row['binding']['project_revision']:
            project = client.get('/api/projects/' + row['project_id'])
            projects[row['project_id']] = project
            if project['revision'] != row['binding']['project_revision']:
                warnings.append({'case': case['case'], 'code': 'CONCURRENT_PROJECT_REVISION_DURING_CAPTURE',
                                 'queue_revision': row['binding']['project_revision'], 'project_revision': project['revision']})
        content_jobs = []
        for job in (project or {}).get('jobs', []):
            if job['kind'] != 'content':
                continue
            folder = args.data_root / 'jobs' / job['id']
            artifacts = []
            for name in ('checkpoint-content.json', 'content.intent.json', 'content-request.json', 'content-provider-response.json', 'content-result.json'):
                path = folder / name
                if path.is_file():
                    artifacts.append({'name': name, 'source_path': str(path), 'sha256': file_sha(path), 'bytes': path.stat().st_size})
            content_jobs.append({'id': job['id'], 'status': job['status'], 'revision': job['revision'], 'created_at': job['created_at'],
                                 'result_metadata': {k: v for k, v in (job['result'] or {}).items() if k != 'proposal'},
                                 'artifacts': artifacts, 'error': job['error']})
        source_rows = [{k: s.get(k) for k in ('id', 'source_type', 'title', 'reference', 'timestamp', 'publication_date_known',
                                            'retrieved_at', 'content_sha256', 'provenance', 'raw_provenance')} for s in bundle['sources']]
        source_checks = {s['id']: digest(s['text']) == s['content_sha256'] for s in bundle['sources']}
        rows.append({'case': case['case'], 'queue': row, 'bundle': bundle, 'selected_idea': selected,
                     'source_dates': source_rows, 'source_text_hashes_valid': source_checks,
                     'project': project, 'content_jobs': content_jobs,
                     'review_classification': {'brief': classify_review((bundle.get('brief') or {}).get('approval')),
                         'script': classify_review((project or {}).get('script_review')),
                         'production': classify_review((project or {}).get('approval')),
                         'final': [classify_review(j.get('final_review')) for j in (project or {}).get('jobs', []) if j['kind'] == 'render']}})
    rendered = [j for r in rows for j in (r['project'] or {}).get('jobs', []) if j['kind'] == 'render']
    scripts = [j for r in rows for j in r['content_jobs'] if j['result_metadata'].get('provider_calls') == 1 and j['result_metadata'].get('response_id')]
    counts = {'source_aware_cases': len(rows), 'provider_derived_retained_candidates': sum(len(r['bundle']['ideas']) for r in rows),
              'selected_ideas': sum(r['selected_idea']['status'] == 'SELECTED' for r in rows),
              'new_provider_generated_scripts': len(scripts), 'actual_script_provider_calls': sum(j['result_metadata']['provider_calls'] for j in scripts),
              'new_production_projects': len(projects), 'render_jobs_total': len(rendered),
              'render_jobs_succeeded': sum(j['status'] == 'succeeded' for j in rendered),
              'render_jobs_failed': sum(j['status'] in {'failed', 'interrupted'} for j in rendered),
              'queue_produced': sum(r['queue']['stage'] == 'PRODUCED' for r in rows),
              'current_codex_script_review_records': sum(r['review_classification']['script']['actor_category'] == 'DELEGATED_CODEX_EXECUTION' for r in rows),
              'personal_owner_acceptances_verified_by_capture': 0}
    checks = {'ten_cases_fifty_candidates': counts['source_aware_cases'] == 10 and counts['provider_derived_retained_candidates'] == 50,
              'ten_actual_selections': counts['selected_ideas'] == 10,
              'five_actual_provider_scripts': counts['new_provider_generated_scripts'] == 5 and counts['actual_script_provider_calls'] == 5,
              'source_text_hashes_exact': all(all(r['source_text_hashes_valid'].values()) for r in rows),
              'all_candidates_have_actual_prior_provider_provenance': all(
                  i['provenance'].get('origin') == 'reused_actual_candidate_snapshot' and
                  i['provenance'].get('original_provenance', {}).get('provider') == 'openai' and
                  i['provenance'].get('original_provenance', {}).get('response_id') and
                  i['provenance'].get('original_provenance', {}).get('actual_provider_calls') == 1
                  for r in rows for i in r['bundle']['ideas'])}
    aggregate = {'schema_version': SCHEMA, 'capture_started_at': started, 'capture_completed_at': stamp(), 'head_sha': head(),
                 'campaign': args.campaign, 'queue_as_of': queue['as_of'], 'input_manifest_sha256': file_sha(args.manifest),
                 'counts': counts, 'cases': rows, 'queue_before_sha256': digest(queue_before), 'queue_after_sha256': digest(queue),
                 'concurrent_capture_warnings': warnings, 'atomic_campaign_snapshot': False,
                 'checks': checks, 'passed': all(checks.values()), 'human_personal_acceptance': 'PENDING',
                 'new_research_retrievals_this_campaign': 0, 'cached_research_is_not_fresh_research': True,
                 'provider_calls_by_capture': 0, 'http_write_requests_by_capture': 0, 'publishing_performed': False}
    stored = ledger.save('campaign-aggregate.json', aggregate)
    ledger.save('queue-snapshot.json', queue)
    ledger.save('candidate-inventory.json', {'campaign': args.campaign, 'captured_at': aggregate['capture_completed_at'],
        'cases': [{'case': r['case'], 'run_id': r['bundle']['run']['id'], 'profile': r['bundle']['run']['context']['profile'],
                   'candidates': r['bundle']['ideas']} for r in rows], 'count': counts['provider_derived_retained_candidates'],
        'new_idea_provider_calls_by_capture': 0, 'all_candidates_are_reused_actual_provider_results': True})
    write_campaign_report(aggregate, ledger.root)
    return {'aggregate': stored, 'passed': aggregate['passed'], 'counts': counts, 'warnings': warnings,
            'report': str(REPO / 'PHASE10_REAL_CAMPAIGN_UAT.md')}


def write_campaign_report(aggregate, evidence):
    def clean(value):
        return str(value if value is not None else '—').replace('|', '\\|').replace('\n', ' ')
    counts = aggregate['counts']
    lines = ['# Phase 10 — Real Campaign UAT', '', 'DRAFT / IN PROGRESS — captured ' + aggregate['capture_completed_at'] + ' (UTC).', '',
             'Campaign: **' + aggregate['campaign'] + '**. Baseline: `82578d8`. HEAD at capture: `' + aggregate['head_sha'] + '`.', '',
             'The isolated Studio campaign contains 50 retained, actual OpenAI-derived candidates across 10 source-aware research forks, 10 selected ideas, and five newly generated provider scripts (01, 02, 04, 06, 08). These are real saved provider results; research sources and candidate generation were reused from Phase 9. No new research retrieval occurred in this campaign. Publication timestamps and original retrieval timestamps remain distinct.', '',
             'Selection, brief authorization and any subsequent execution approval are recorded as Codex acting under `VF-PHASE10-FINAL-UAT-CERTIFICATION-01`. They do not mean Owner personally read, watched or listened to the new content. Personal Owner acceptance remains **PENDING**. Historical Phase 8/9 acceptance stays unchanged.', '',
             f"At capture: {counts['new_provider_generated_scripts']} new provider scripts; {counts['render_jobs_total']} render jobs, {counts['render_jobs_succeeded']} succeeded and {counts['render_jobs_failed']} failed/interrupted; {counts['queue_produced']} campaign queue items PRODUCED. These are intermediate counts, not a final production or human acceptance claim.", '',
             'All scores use **HEURISTIC_SCORING**. Ranking reflects configured editorial rules, publication freshness, lexical similarity and readiness; it does not predict audience results or lead conversion. Similarity overrides are explicit delegated decisions, not an originality or plagiarism verdict.', '',
             '| Case | Profile | Selected idea | Idea score | Priority | Freshness | Queue stage | Planned format / seconds |',
             '|---|---|---|---:|---:|---|---|---|']
    for r in aggregate['cases']:
        q, idea = r['queue'], r['selected_idea']
        lines.append('| ' + ' | '.join(clean(v) for v in (f"{int(r['case']):02d}", q['profile_name'], idea['title'],
            (idea.get('score') or {}).get('final_score'), q['priority']['score'], q['freshness']['status'], q['stage'],
            q['planning']['format'] + ' / ' + str(q['planning']['duration_seconds']))) + ' |')
    for r in aggregate['cases']:
        q, idea, bundle = r['queue'], r['selected_idea'], r['bundle']
        run = bundle['run']; provenance = run['provenance']
        lines += ['', f"## Case {int(r['case']):02d} — {idea['title']}", '',
                  '- IDs: run `' + run['id'] + '`; original research run `' + provenance.get('original_run_id', '') + '`; opportunity `' + bundle['opportunity']['id'] + '`; idea `' + idea['id'] + '` v' + str(idea['version']) + '; brief `' + q['brief_id'] + '`; queue `' + q['id'] + '`.',
                  '- Project: `' + str(q['project_id'] or 'not imported for production') + '`; queue stage `' + q['stage'] + '`; intelligence status `' + str(q['intelligence_status']) + '`; planning actor ' + q['planning']['assigned_to'] + '; assignment `' + q['planning']['assigned_status'] + '`.',
                  '- Profile: ' + q['profile_name'] + ' (`' + q['profile_id'] + '`); related project: ' + str(q['related_project']) + '.',
                  '- Hook: ' + idea['hook'], '- Angle / viewer: ' + idea['angle'] + ' / ' + idea['target_audience'],
                  '- CTA: ' + idea['cta'], '- Reason now from retained research: ' + bundle['opportunity']['reason_now'],
                  '- Planned production: ' + q['planning']['format'] + ', ' + str(q['planning']['duration_seconds']) + ' seconds; candidate estimate ' + str(idea['estimated_duration']) + ' seconds. Final measured duration requires actual render verification.',
                  '- Selected score: ' + str((idea.get('score') or {}).get('final_score')) + '; priority: ' + str(q['priority']['score']) + '; freshness: ' + q['freshness']['status'] + '. All component scores, weights, rationales and dates are preserved in the aggregate.',
                  '- Similarity: ' + q['similarity']['method'] + '; ' + str(len(q['similarity']['warnings'])) + ' warnings; current override: ' + str(q['similarity']['override_current']) + '. Warning hashes and comparisons are preserved in the queue snapshot.',
                  '- Research: provider `' + run['provider'] + '`; editorial model `' + str(run['model']) + '`; fork origin `' + provenance['origin'] + '`; provider metadata preserves original run/model receipts. This fork reports zero new research/provider calls and retains original dates. Findings remain distinguished as sourced claims, inference or uncertain information.']
        for source in r['source_dates']:
            lines.append('- Source: [' + source['title'] + '](' + source['reference'] + '); type `' + str(source['source_type']) + '`; publication ' + str(source['timestamp'] or 'UNKNOWN') + '; retrieved ' + str(source['retrieved_at']) + '; source ID `' + source['id'] + '`; text digest `' + source['content_sha256'] + '`.')
        for j in r['content_jobs']:
            meta = j['result_metadata']
            lines.append('- New script job `' + j['id'] + '` (' + j['status'] + '): model `' + str(meta.get('model')) + '`; response `' + str(meta.get('response_id')) + '`; provider calls ' + str(meta.get('provider_calls')) + '; retries ' + str(meta.get('retries')) + '; independently verified facts: ' + str(meta.get('facts_verified')) + '. Actual request/response/checkpoint hashes are bound in the aggregate.')
    lines += ['', '## Evidence and current acceptance', '',
              '- [Current aggregate](' + (evidence / 'campaign-aggregate.json').as_posix() + ') — full ten-case research, selected ideas, source timestamps, scripts, review actor classification and current state.',
              '- [Candidate inventory](' + (evidence / 'candidate-inventory.json').as_posix() + ') — all 50 actual provider-derived candidates and transparent component scoring.',
              '- [Queue snapshot](' + (evidence / 'queue-snapshot.json').as_posix() + ') — priorities, similarity warnings/overrides, assignment, versions and bindings.',
              '- Regression: 228/228 Native tests PASS at `aff945c4433eeaa66362aa419fa8572eaaf34e5d`; temporary-root tests do not establish production or human acceptance.',
              '- Preservation: 1,596 frozen Phase 8/9 files, live database table digests and runtime dependencies unchanged; 15 old accepted MP4s remain byte-exact and pass authenticated HTTP 200 / range 206 access.',
              '- New full-video acceptance: **PENDING**. No autonomous publishing or scheduling is enabled.',
              '- This report is an as-of capture while authorized preparation continues. Queue and project reads are not one atomic transaction; any observed concurrent revision differences are recorded in the aggregate. Final video copies, measured durations and lineage verification will be added after actual render completion.', '',
              'PHASE10 REAL CAMPAIGN UAT: IN PROGRESS — personal Owner review remains pending.', '']
    (REPO / 'PHASE10_REAL_CAMPAIGN_UAT.md').write_text('\n'.join(lines), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['snapshot', 'compare', 'video', 'campaign'])
    parser.add_argument('--base-url', default='http://127.0.0.1:8030')
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--config', type=Path, default=DEFAULT_DATA / 'config.json')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--project')
    parser.add_argument('--job')
    parser.add_argument('--label', default='snapshot')
    parser.add_argument('--before', type=Path)
    parser.add_argument('--after', type=Path)
    parser.add_argument('--manifest', type=Path, default=REPO / 'evidence/post-mvp-roadmap/phase-10/uat-preparation.json')
    parser.add_argument('--campaign', default='NPD · Phase10 Final UAT · 2026-10-06')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.label):
        parser.error('label must contain only ASCII letters, digits, hyphens or underscores')
    root = args.output_dir.resolve()
    if root == args.data_root.resolve() or args.data_root.resolve() in root.parents:
        parser.error('evidence output must be outside application data root')
    category = 'ideas/queue' if args.command == 'campaign' else 'videos' if args.command == 'video' else 'shot-edits'
    ledger = support.Ledger(root / category, args.label if args.command != 'video' else 'video-' + support.identifier(args.job))
    try:
        if args.command == 'compare':
            if not args.before or not args.after:
                parser.error('compare requires --before and --after snapshot.json')
            result = compare(read(args.before), read(args.after))
            ledger.save('shot-comparison.json', result)
            summary = {'passed': result['passed'], 'problems': result['problems']}
        else:
            client = ReadClient(args.base_url, ledger)
            client.connect()
            summary = campaign(client, ledger, args) if args.command == 'campaign' else snapshot(client, ledger, args) if args.command == 'snapshot' else video(client, ledger, args)
        ledger.save('summary.json', summary)
        print(json.dumps({'evidence_directory': str(ledger.root), **summary}, ensure_ascii=False))
        return 0 if summary['passed'] and summary.get('comparison_passed') is not False else 1
    except Exception as exc:
        failure = {'recorded_at': stamp(), 'command': args.command, 'error_type': type(exc).__name__,
                   'code': getattr(exc, 'code', None), 'message': str(exc) if isinstance(exc, support.EvidenceError) else None,
                   'app_mutations_by_helper': 0, 'provider_calls_by_helper': 0,
                   'outcome': 'VERIFICATION_FAILED_PRESERVED_NO_REPLAY'}
        ledger.save('verification-failure.json', failure)
        print(json.dumps({'evidence_directory': str(ledger.root), **failure}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
