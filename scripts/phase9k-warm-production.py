"""Apply the Owner-reviewed B voice through the existing Native render lane.

This records production authorization, never a new final-video approval.
Historical evidence and earlier render decisions remain immutable.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import Proposal, PROFILE_SHA, canonical, digest, file_sha, normalize, write_json
from services.windows_native.editor import validate_plan
from services.windows_native.hardening import Artifacts
from services.windows_native.intelligence_lineage import projection
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.media import verify_selected_files
from services.windows_native.pipeline import Config, REPO, profile, verify_runtime
from services.windows_native.store import Store
from services.windows_native.voice_quality import registered_policy, resolve_policy

ROOT = REPO / 'evidence/post-mvp-roadmap/phase-9/9k'
OUT = ROOT / 'audio-repair-03'
PRIOR = ROOT / 'audio-repair-01'
TRIALS = ROOT / 'audio-repair-02'
LOCAL_TRIALS = Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-onset-20261006')
POLICY = 'warm-scene-context-v1'


def read(path): return json.loads(Path(path).read_bytes())


def preserve(path, value):
    data = canonical(value)
    if path.exists(): assert path.read_bytes() == data, 'Immutable receipt changed: ' + str(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle: handle.write(data)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists(): assert file_sha(source) == file_sha(target)
    else: shutil.copyfile(source, target)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


checks = module('production_checks', REPO / 'scripts/phase9k-production-acceptance.py')


def cache():
    """Import the eight real reviewed sources without replaying their providers."""
    from services.windows_native.warm_voice import build_plan, cache_key
    config = Config(); verify_runtime(config)
    owner = read(OUT / 'owner-B-approval.json')
    assert owner['owner_message'] == 'Giọng B đạt'
    reviewed = read(TRIALS / 'onset-review-manifest.json')
    assert file_sha(TRIALS / 'eight-onsets-A-then-B.wav') == reviewed['audio_sha256']
    entries = []
    for pair in reviewed['pairs']:
        case, scene = pair['case'], pair['scene']
        original = LOCAL_TRIALS / f'warm-sentence-case-{case:02}/scene-{scene:02}'
        trial = read(original / 'trial.json'); results = read(original / 'results.json')
        source = original / 'with-context.wav'; transcript = read(original / 'transcript.json')
        proposal = Proposal.model_validate(read(PRIOR / f'case-{case:02}/input.json')['document']['proposal'])
        plans = build_plan(proposal, registered_policy(POLICY))
        plan = next(p for p in plans if p['scene'] == scene)
        assert normalize(trial['target_text']) == plan['target_text']
        assert normalize(trial['approved_previous_sentence_context']) == plan['context_text']
        for key in ('normalized_text', 'phonemes', 'seed', 'effective_parameters', 'sample_rate'):
            plan_key = 'effective_sampling_parameters' if key == 'effective_parameters' else key
            assert trial[key] == plan[plan_key], key
        assert trial['base_voice_profile_sha256'] == PROFILE_SHA
        assert trial['normalization_max_chars_override'] == plan['normalization_max_chars']
        assert results['observed_eos'] and results['network_blocked'] and results['retries'] == 0
        assert file_sha(source) == results['audio_sha256'] == transcript['voice_sha256'] == pair['B_source_voice_sha256']
        assert transcript['trial_sha256'] == file_sha(original / 'trial.json')
        raw = read(original / 'provider/provider-completed.json')['payload']
        assert digest(raw) == transcript['transcript']['provenance']['raw_response_sha256']
        key = cache_key(plan); destination = config.data_root / 'voice-context-cache' / key
        destination.mkdir(parents=True, exist_ok=True)
        origin = {'classification': 'REUSED_ACTUAL_OWNER_REVIEWED_B_SOURCE', 'case': case, 'scene': scene,
                  'original_trial_path': str(original), 'original_trial_sha256': file_sha(original / 'trial.json'),
                  'original_approval_snapshot_sha256': trial['approval_snapshot_sha256'],
                  'owner_B_approval_sha256': file_sha(OUT / 'owner-B-approval.json'),
                  'reviewed_B_onset_wave_sha256': pair['B_wave_sha256'],
                  'reviewed_B_target_wave_sha256': pair['B_target_wave_sha256'],
                  'reviewed_context_cut_seconds': pair['B_context_cut_seconds'],
                  'full_target_word_accuracy_confirmed': False, 'final_video_approved': False}
        preserve(destination / 'plan.json', plan)
        copy(source, destination / 'source.wav')
        preserve(destination / 'generated.json', {'schema_version': 1, 'plan_sha256': key,
                 'source_wave_sha256': file_sha(source), 'duration_seconds': results['duration_seconds'],
                 'observed_eos': True, 'network_blocked': True, 'retries': 0, 'origin': origin})
        preserve(destination / 'timing.json', {'schema_version': 1, 'plan_sha256': key,
                 'source_wave_sha256': file_sha(source), 'transcript': transcript['transcript'],
                 'raw_response': raw, 'origin': origin})
        # Archive portable copies of the actual source and its bound receipts.
        archived = OUT / f'reused-B-sources/case-{case:02}/scene-{scene:02}'
        for name in ('plan.json', 'source.wav', 'generated.json', 'timing.json'):
            copy(destination / name, archived / name)
        for receipt in (original / 'provider').glob('*.json'):
            copy(receipt, destination / 'provider' / receipt.name)
            copy(receipt, archived / 'provider' / receipt.name)
        entries.append({'case': case, 'scene': scene, 'plan_sha256': key,
                        'source_wave_sha256': file_sha(source), 'cache_path': str(destination), 'origin': origin})
    assert len(entries) == 8
    preserve(OUT / 'reused-B-sources.json', {'cases': entries, 'new_local_inferences': 0,
             'new_provider_requests': 0, 'approved_onset_samples_reused': 8,
             'human_full_video_approvals': 0})
    print(json.dumps({'approved_B_sources_imported': 8, 'provider_replay': False}), flush=True)


def prepare():
    config = Config(); store = Store(config.data_root); verify_runtime(config)
    owner = read(OUT / 'owner-B-approval.json'); old = read(PRIOR / 'production-approval-manifest.json')
    target = OUT / 'production-approval-manifest.json'
    assert not target.exists(), 'Inspect any existing preparation before changing revisions again'
    with sqlite3.connect(store.db) as con:
        assert con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0] == 0
    cases = []
    for previous, original in zip(owner['cases'], old['cases']):
        assert previous['case'] == original['case']
        p = store.get(previous['project_id'])
        assert p['revision'] == previous['current_revision'] and digest(p['document']) == previous['current_document_sha256']
        before = p['document']
        p = store.set_voice_quality(p['id'], p['revision'], POLICY)
        assert p['revision'] == previous['current_revision'] + 1 and p['approval'] is None
        assert p['document'] == {**before, 'voice_quality': p['document']['voice_quality']}
        assert p['script_review']['current'] and p['script_review']['review_id'] == previous['script_review_id']
        reference = {'source': 'human_user_reply_in_codex',
                     'scope': 'AUTHORIZED_WARM_VOICE_REPAIR_REUSES_APPROVED_SCRIPT_AND_MEDIA',
                     'owner_B_approval_sha256': file_sha(OUT / 'owner-B-approval.json'),
                     'original_script_review_id': previous['script_review_id'],
                     'original_media_authorization_sha256': file_sha(ROOT / 'owner-media-authorization.json'),
                     'earlier_all_five_audio_repair_sha256': file_sha(PRIOR / 'owner-feedback.json'),
                     'approved_B_onset_samples_only': True, 'full_new_audio_accepted': False,
                     'final_video_approved': False}
        p = store.approve(p['id'], p['revision'], 'Owner — giọng B đạt; dựng lại bằng lời và hình đã duyệt', True,
                          review_reference=reference)
        verify_selected_files(config, p['document']); validate_plan(p['document'])
        item = {**previous, 'revision': p['revision'], 'document_sha256': digest(p['document']),
                'approval': p['approval'], 'snapshot_sha256': digest({'document': p['document'], 'approval': p['approval']}),
                'quality_policy': resolve_policy(p['document']), 'research_lineage': projection(p['document'])}
        assert item['research_lineage'] == previous['research_lineage']
        preserve(OUT / f"prepared-case-{item['case']:02}.json", item); cases.append(item)
    preserve(target, {'owner_B_approval_sha256': file_sha(OUT / 'owner-B-approval.json'),
             'cases': cases, 'active_parent_application_sha': old['parent_service_application_sha'],
             'fresh_tts_child_application_sha': subprocess.check_output([str(config.git), 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
             'renderer_unchanged': True, 'main_service_restarted': False,
             'human_final_video_approvals': 0, 'published': False})
    print(json.dumps({'prepared': 5, 'revisions': {c['case']: c['revision'] for c in cases},
                      'unchanged_approved_words_media': True, 'final_approved': False}), flush=True)


def dispatch():
    config = Config(); store = Store(config.data_root); target = OUT / 'jobs.json'
    production = read(OUT / 'production-approval-manifest.json')
    report = read(target) if target.exists() else {'cases': [], 'status': 'RUNNING_REAL_WARM_VOICE_REPAIR',
              'production_approval_sha256': file_sha(OUT / 'production-approval-manifest.json')}
    for case in production['cases']:
        p = store.get(case['project_id'])
        assert p['revision'] == case['revision'] and p['approval'] == case['approval']
        assert digest(p['document']) == case['document_sha256']
        key = f"phase9k-warm-B-{p['id']}-{p['revision']}"
        job = store.enqueue(p['id'], p['revision'], 'render', key)
        known = next((c for c in report['cases'] if c['case'] == case['case']), None)
        if known: assert known['job_id'] == job['id']
        else:
            report['cases'].append({'case': case['case'], 'project_id': p['id'], 'revision': p['revision'],
                                   'job_id': job['id'], 'request_key': key, 'snapshot_sha256': digest(job['snapshot'])})
            write_json(target, report)
        print(json.dumps({'case': case['case'], 'job_id': job['id'], 'status': job['status']}), flush=True)


def status():
    store = Store(Config().data_root); report = read(OUT / 'jobs.json')
    for c in report['cases']:
        j = store.get_job(c['job_id'])
        c.update({k: j[k] for k in ('status', 'stage', 'error', 'result', 'final_review')})
    done = sum(c['status'] == 'succeeded' for c in report['cases'])
    report.update(successful_jobs=done, terminal=all(c['status'] in {'succeeded','failed','interrupted'} for c in report['cases']),
                  human_final_video_approvals=0, CONTENT_INTELLIGENCE_READY='NO')
    write_json(OUT / 'jobs.json', report)
    print(json.dumps({'cases': [{k: c[k] for k in ('case','job_id','status','stage','error')} for c in report['cases']]}), flush=True)


def resume():
    """Explicitly continue only the known boundary failures after the code repair."""
    config=Config(); store=Store(config.data_root); report=read(OUT/'jobs.json')
    before=[]
    for c in report['cases']:
        job=store.get_job(c['job_id'])
        if job['status']=='succeeded': continue
        assert job['status']=='failed' and job['error']['code']=='WARM_VOICE_UNIQUE_TARGET_ONSET_REQUIRED'
        attempt=config.data_root/'jobs'/job['id']/'attempts/tts-000'
        generation=read(attempt/'warm-generation-result.json')
        assert read(attempt/'warm-generation-status.json')['status']=='pass'
        before.append({'case':c['case'],'job_id':job['id'],'revision':job['revision'],
                       'snapshot_sha256':digest(job['snapshot']),'previous_error':job['error'],
                       'failed_status':read(attempt/'tts-status.json'),
                       'failed_status_sha256':file_sha(attempt/'tts-status.json'),
                       'completed_generation':generation,
                       'failed_attempt_path':str(attempt)})
    assert {c['case'] for c in before}=={1,2,6,8}
    preserve(OUT/'boundary-failure-recovery-before.json',{'cases':before,
             'reason':'Canonical exact-prefix/abbreviation and jointly anchored measured-gap boundary refinement; sources unchanged',
             'automatic_paid_or_local_inference_retry':False,'new_final_approvals':0})
    resumed=[]
    for c in before:
        job=store.resume(c['job_id'])
        assert job['snapshot'] == store.get_job(c['job_id'])['snapshot']
        resumed.append({'case':c['case'],'job_id':job['id'],'revision':job['revision'],'resume_count':job['resume_count'],
                        'snapshot_sha256':digest(job['snapshot'])})
        assert resumed[-1]['snapshot_sha256']==c['snapshot_sha256']
    preserve(OUT/'boundary-failure-recovery-resumed.json',{'cases':resumed,
             'application_sha':subprocess.check_output([str(config.git),'rev-parse','HEAD'],cwd=REPO,text=True).strip(),
             'sources_reused_without_inference_replay':True,'provider_durable_known_outcomes_reused':True,
             'as_yet_unrequested_remaining_timings_may_be_requested_once':True,
             'final_video_approved':False})
    print(json.dumps({'explicit_boundary_recovery_jobs':len(resumed),'same_approved_snapshots':True}),flush=True)


def verify():
    from services.windows_native import warm_voice
    config = Config(); store = Store(config.data_root); service = IntelligenceService(config, store)
    production = read(OUT / 'production-approval-manifest.json'); jobs = read(OUT / 'jobs.json')
    owner = read(OUT / 'owner-B-approval.json')
    assert production['owner_B_approval_sha256'] == file_sha(OUT / 'owner-B-approval.json')
    assert jobs['production_approval_sha256'] == file_sha(OUT / 'production-approval-manifest.json')
    expected_cases = [1, 2, 4, 6, 8]
    for manifest in (production, jobs, owner):
        assert len(manifest['cases']) == 5 and [c['case'] for c in manifest['cases']] == expected_cases
        assert len({c['project_id'] for c in manifest['cases']}) == 5
    assert len({c['job_id'] for c in jobs['cases']}) == 5
    accepted_samples = {(s['case'], s['scene']): s for s in owner['accepted_samples']}
    assert len(accepted_samples) == 8 and owner['human_onset_audio_accepted'] is True
    assert owner['final_video_approved'] is False and owner['full_script_word_accuracy_approved'] is False
    reviewed_samples_verified = set()
    cases = []; new_source_keys = set()
    task_provider = {'upload_requests':0,'transcript_create_requests':0,'observe_requests':0}
    get = checks.integrity.http_reader(); assert get('/api/health')['status'] == 'ready'
    for approved, item in zip(production['cases'], jobs['cases']):
        assert approved['case'] == item['case'] and approved['project_id'] == item['project_id']
        assert approved['revision'] == item['revision'] and approved['snapshot_sha256'] == item['snapshot_sha256']
        job = store.get_job(item['job_id']); p = store.get(item['project_id']); out = config.data_root / 'jobs' / job['id']
        assert job['id'] == item['job_id'] and job['project_id'] == p['id'] == approved['project_id']
        assert job['status'] == 'succeeded' and job['error'] is None and job['final_review'] is None
        assert job['revision'] == p['revision'] == approved['revision']
        assert p['approval'] == job['snapshot']['approval'] == approved['approval']
        assert digest(p['document']) == approved['document_sha256'] and digest(job['snapshot']) == approved['snapshot_sha256']
        assert p['document'] == job['snapshot']['document']
        assert p['script_review']['current'] and p['script_review']['review_id'] == approved['script_review_id']
        assert hashlib.sha256(p['document']['proposal']['narration'].encode('utf-8')).hexdigest() == approved['script_sha256']
        prior = store.get_job(approved['prior_job_id'])
        assert {k:v for k,v in p['document'].items() if k != 'voice_quality'} == {k:v for k,v in prior['snapshot']['document'].items() if k != 'voice_quality'}
        assert prior['final_review'] == approved['prior_final_review']
        assert file_sha(config.data_root / 'jobs' / prior['id'] / 'final.mp4') == approved['prior_final_sha256']
        verify_selected_files(config, p['document']); validate_plan(p['document'])
        assert projection(p['document']) == approved['research_lineage'] == projection(prior['snapshot']['document'])
        artifacts = Artifacts(out, job); assert artifacts.load('tts') and artifacts.load('render')
        voice = read(out / 'voice.json'); plan = read(out / 'tts-plan.json'); render = read(out / 'render-manifest.json')
        qc = read(out / 'qc-report.json'); timeline = read(out / 'timeline.json')
        assert voice['profile_sha256'] == PROFILE_SHA and voice['speed'] == 1 and voice['retries'] == 0
        assert voice['quality_policy'] == approved['quality_policy'] == resolve_policy(p['document'])
        assert voice['audio_sha256'] == file_sha(out / 'voice.wav') == render['voice_sha256']
        assert len(voice['units']) == 5 and normalize(' '.join(u['text'] for u in voice['units'])) == normalize(p['document']['proposal']['narration'])
        proposal = Proposal.model_validate(p['document']['proposal'])
        canonical_plans = warm_voice.build_plan(proposal, voice['quality_policy'])
        assert len(canonical_plans) == len(voice['sources']) == len(plan['units']) == 5
        assert plan['units'] == canonical_plans
        for key in ('quality_policy', 'quality_policy_sha256', 'source_approval',
                    'source_document_sha256', 'pipeline_source_sha256', 'warm_source_sha256', 'sources'):
            assert voice[key] == plan[key]
        assert voice['source_approval'] == p['approval']
        assert voice['source_document_sha256'] == approved['document_sha256']
        assert voice['quality_policy_sha256'] == digest(voice['quality_policy'])
        assert plan['profile_sha256'] == PROFILE_SHA
        attempts = []
        for attempt in sorted((out / 'attempts').glob('tts-*')):
            status_path = attempt / 'tts-status.json'
            assert status_path.is_file(), 'Every actual TTS attempt must retain an explicit status'
            status_value = read(status_path)
            entries = [{'path': f.relative_to(attempt).as_posix(), 'sha256': file_sha(f), 'bytes': f.stat().st_size}
                       for f in sorted(attempt.rglob('*'))
                       if f.is_file() and f.suffix.lower() in {'.json', '.wav', '.log'}]
            generation_path = attempt / 'warm-generation-result.json'
            generation = read(generation_path) if generation_path.is_file() else None
            attempt_voice_path = attempt / 'voice.json'
            attempt_voice = read(attempt_voice_path) if attempt_voice_path.is_file() else None
            attempts.append({'name': attempt.name, 'status': status_value['status'],
                             'code': status_value.get('code'), 'status_path': str(status_path),
                             'status_sha256': file_sha(status_path), 'status_value': status_value,
                             'tts_log_sha256': file_sha(attempt / 'tts.log') if (attempt / 'tts.log').is_file() else None,
                             'generation_result_sha256': file_sha(generation_path) if generation else None,
                             'new_inference_calls_recorded': generation['new_inference_calls'] if generation else None,
                             'complete_voice_metadata_sha256': file_sha(attempt_voice_path) if attempt_voice else None,
                             'counts_from_complete_voice_metadata': {
                                 'new_local_inference_calls': attempt_voice['new_inference_calls'],
                                 'reused_local_inference_calls': attempt_voice['reused_inference_calls'],
                                 'resolved_scene_inferences': attempt_voice['inference_calls'],
                                 'provider_requests_this_attempt': attempt_voice['provider_requests_this_attempt']
                             } if attempt_voice else None,
                             'missing_complete_voice_metadata_is_not_zero_requests': attempt_voice is None,
                             'source_files': entries, 'source_files_manifest_sha256': digest(entries)})
        passing = [a for a in attempts if a['status'] == 'pass']
        assert len(passing) == 1
        active_attempt = out / 'attempts' / passing[0]['name']
        assert file_sha(active_attempt / 'voice.wav') == voice['audio_sha256']
        assert read(active_attempt / 'voice.json') == voice and read(active_attempt / 'tts-plan.json') == plan
        generation = read(active_attempt / 'warm-generation-result.json')
        assert voice['inference_calls'] == len(canonical_plans) == 5
        assert voice['new_inference_calls'] == generation['new_inference_calls']
        assert len(generation['plan_keys']) == len(set(generation['plan_keys'])) == voice['new_inference_calls']
        assert set(generation['plan_keys']) <= {warm_voice.cache_key(cp) for cp in canonical_plans}
        assert voice['new_inference_calls'] + voice['reused_inference_calls'] == voice['inference_calls']
        scene_integrity = []
        for canonical_plan, source in zip(canonical_plans, voice['sources']):
            scene = canonical_plan['scene']; key = warm_voice.cache_key(canonical_plan)
            assert source['plan'] == canonical_plan and source['plan_sha256'] == key
            archived = active_attempt / 'context-sources' / f'scene-{scene:02}'
            assert Path(source['source_wave_path']).resolve() == (archived / 'source.wav').resolve()
            assert source['source_wave_preserved'] is True and source['archived_files']
            recorded_paths = set()
            for saved in source['archived_files']:
                saved_path = (active_attempt / saved['path']).resolve()
                assert active_attempt.resolve() in saved_path.parents and not saved_path.is_symlink()
                assert saved['path'] not in recorded_paths
                recorded_paths.add(saved['path'])
                assert file_sha(saved_path) == saved['sha256'] and saved_path.stat().st_size == saved['bytes']
            assert {str((archived / name).relative_to(active_attempt)).replace('\\', '/')
                    for name in ('plan.json', 'source.wav', 'generated.json')} <= recorded_paths
            generated = warm_voice.generated_record(archived, canonical_plan)
            assert generated == source['generated']
            assert generated['source_wave_sha256'] == source['source_wave_sha256'] == file_sha(archived / 'source.wav')
            pcm = warm_voice.read_wave(archived / 'source.wav')
            if canonical_plan['context_text']:
                timing = warm_voice.timing_record(archived, canonical_plan, generated)
                assert timing is not None and timing == source['timing']
                assert (archived / 'provider/provider-completed.json').is_file()
                raw_receipt = read(archived / 'provider/provider-completed.json')
                assert raw_receipt['payload'] == timing['raw_response']
                assert digest(raw_receipt['payload']) == timing['transcript']['provenance']['raw_response_sha256']
                reconstructed = warm_voice.trim_boundary(canonical_plan, pcm.astype('float64') / 32768, timing)
                assert reconstructed['removed_samples'] == source['boundary']['removed_samples']
                assert abs(reconstructed['cut_seconds'] - source['boundary']['cut_seconds']) <= 1 / warm_voice.RATE
                assert source['boundary']['provider_native_timestamps_are_approximate'] is True
            else:
                assert source['timing'] is None and source['boundary']['removed_samples'] == 0
                assert source['boundary']['method'] == 'first_scene_without_extra_context'
            assert source['boundary']['human_audio_accepted'] is False
            assert source['boundary']['full_target_word_accuracy_confirmed'] is False
            counts = warm_voice.provider_counts(archived)
            assert counts == source['provider_receipts_total_in_cache']
            for counter, value in source['provider_requests_this_attempt'].items():
                assert isinstance(value, int) and 0 <= value <= counts[counter]
            reviewed = accepted_samples.get((item['case'], scene))
            if reviewed:
                assert generated['origin']['classification'] == 'REUSED_ACTUAL_OWNER_REVIEWED_B_SOURCE'
                assert generated['origin']['owner_B_approval_sha256'] == production['owner_B_approval_sha256']
                assert generated['source_wave_sha256'] == reviewed['B_context_source_sha256']
                assert generated['origin']['reviewed_B_onset_wave_sha256'] == reviewed['B_onset_sha256']
                assert generated['origin']['reviewed_B_target_wave_sha256'] == reviewed['B_target_sha256']
                assert abs(source['boundary']['cut_seconds'] - reviewed['cut_seconds']) <= 1 / warm_voice.RATE
                reviewed_samples_verified.add((item['case'], scene))
            else:
                assert generated['origin']['method'] == 'fresh_offline_warm_scene_inference'
                assert key not in new_source_keys
                new_source_keys.add(key)
                for counter in task_provider: task_provider[counter] += counts[counter]
            scene_integrity.append({'scene': scene, 'plan_sha256': key,
                'source_wave_sha256': source['source_wave_sha256'], 'cut_seconds': source['boundary']['cut_seconds'],
                'removed_samples': source['boundary']['removed_samples'], 'cut_method': source['boundary']['method'],
                'reviewed_B_source_reused': bool(reviewed), 'portable_raw_source_and_timing_integrity': 'PASS',
                'full_word_accuracy_or_audio_quality_pass_claimed': False})
        provider_current = {key: sum(s['provider_requests_this_attempt'][key] for s in voice['sources'])
                            for key in ('upload_requests', 'transcript_create_requests', 'observe_requests')}
        assert voice['provider_requests_this_attempt'] == provider_current
        provider_source_total = {key: sum(s['provider_receipts_total_in_cache'][key] for s in voice['sources'])
                                for key in provider_current}
        assert render['approval'] == p['approval'] and timeline['metadata']['content_intelligence'] == approved['research_lineage']
        assert qc == job['result']['qc'] and qc['passed'] and len(qc['checks']) == 11 and all(qc['checks'].values())
        assert qc['final_sha256'] == file_sha(out / 'final.mp4') and not qc['human_final_video_accepted'] and not qc['published']
        assert get('/api/projects/' + p['id'])['document'] == p['document']
        api = get('/api/jobs/' + job['id'] + '/artifacts'); assert api['qc'] == qc and api['final_review'] is None
        limits = [int(n) for n in re.findall(r'\d+', read(ROOT / f"case-{item['case']:02}/storyboard-reviewed-v3.json")['duration_target'])]
        cases.append({**approved, 'job_id': job['id'], 'final_mp4': str(out / 'final.mp4'),
                      'final_sha256': qc['final_sha256'], 'voice_sha256': voice['audio_sha256'],
                      'voice_duration_seconds': voice['duration_seconds'], 'video_duration_seconds': qc['duration_seconds'],
                      'duration_target': limits, 'duration_target_met': limits[0] <= qc['duration_seconds'] <= limits[-1],
                      'qc_checks': qc['checks'], 'tts_plan_sha256': file_sha(out / 'tts-plan.json'),
                      'actual_tts_attempts': attempts, 'active_passing_tts_attempt': passing[0]['name'],
                      'failed_tts_attempts': [a for a in attempts if a['status'] != 'pass'],
                      'all_attempt_new_inference_calls_recorded': sum(a['new_inference_calls_recorded']
                          for a in attempts if a['new_inference_calls_recorded'] is not None),
                      'attempts_without_durable_generation_count': sum(a['new_inference_calls_recorded'] is None
                          for a in attempts),
                      'warm_source_integrity': scene_integrity,
                      'source_totals': {'resolved_scene_inferences': voice['inference_calls'],
                                        'reviewed_B_scene_sources_reused': sum(s['reviewed_B_source_reused'] for s in scene_integrity),
                                        'provider_receipts': provider_source_total,
                                        'semantics': 'All bound source receipts, including previously paid and reused sources; not requests in this successful attempt'},
                      'current_successful_attempt_counts': {'new_local_inference_calls': voice['new_inference_calls'],
                                        'reused_local_inference_calls': voice['reused_inference_calls'],
                                        'provider_requests': provider_current,
                                        'semantics': 'Only actual new work recorded for the final passing TTS attempt; earlier failed attempts retained separately'},
                      'human_full_audio_accepted': False, 'human_final_video_approved': False})
    assert reviewed_samples_verified == set(accepted_samples)
    for name, sha in owner['frozen_prior_evidence'].items(): assert file_sha(REPO / name) == sha
    backups = {b['database']: b for b in owner['backups']}
    for b in backups.values(): assert file_sha(b['path']) == b['sha256']
    with sqlite3.connect(backups['workflow']['path']) as con:
        ids = {r[0] for r in con.execute('SELECT id FROM projects')} - {c['project_id'] for c in cases}
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('projects','sqlite_sequence')")]
    preserved = checks.integrity.rows_preserved(backups['workflow']['path'], store.db, names)
    preserved.update(checks.integrity.rows_preserved(backups['workflow']['path'], store.db, ['projects'], ids))
    intelligence = checks.integrity.rows_preserved(backups['intelligence']['path'], service.store.db)
    protected = checks.protected_release(config, store, service, production)
    with sqlite3.connect(store.db) as con:
        assert con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0] == 0
    return {'recorded_at': datetime.now(timezone.utc).isoformat(), 'classification': 'FIVE_ACTUAL_WARM_B_NATIVE_REVISIONS',
            'cases': cases, 'protected_release': protected, 'historical_rows_preserved': preserved,
            'intelligence_rows_preserved': intelligence, 'frozen_prior_evidence_unchanged': len(owner['frozen_prior_evidence']),
            'table_snapshots': {'workflow': checks.integrity.table_snapshot(store.db), 'intelligence': checks.integrity.table_snapshot(service.store.db)},
            'owner_B_onset_samples_accepted': 8, 'human_final_video_approvals': 0,
            'reviewed_B_sources_and_cuts_verified': len(reviewed_samples_verified),
            'failed_actual_tts_attempt_count': sum(len(c['failed_tts_attempts']) for c in cases),
            'all_attempt_new_inference_calls_recorded': sum(c['all_attempt_new_inference_calls_recorded'] for c in cases),
            'attempts_without_durable_generation_count': sum(c['attempts_without_durable_generation_count'] for c in cases),
            'task_new_source_local_inference_calls':len(new_source_keys),
            'task_new_source_provider_receipts':task_provider,
            'task_count_semantics':'Unique fresh source cache entries created for this repair, including work from explicit failed boundary attempts; reused eight prior B sources excluded',
            'source_totals': {'resolved_scene_inferences': sum(c['source_totals']['resolved_scene_inferences'] for c in cases),
                'reviewed_B_scene_sources_reused': sum(c['source_totals']['reviewed_B_scene_sources_reused'] for c in cases),
                'provider_receipts': {key: sum(c['source_totals']['provider_receipts'][key] for c in cases)
                    for key in ('upload_requests', 'transcript_create_requests', 'observe_requests')},
                'semantics': 'Complete source history including reused original receipts; not newly billed work'},
            'current_successful_attempt_totals': {
                'new_local_inference_calls': sum(c['current_successful_attempt_counts']['new_local_inference_calls'] for c in cases),
                'reused_local_inference_calls': sum(c['current_successful_attempt_counts']['reused_local_inference_calls'] for c in cases),
                'provider_requests': {key: sum(c['current_successful_attempt_counts']['provider_requests'][key] for c in cases)
                    for key in ('upload_requests', 'transcript_create_requests', 'observe_requests')},
                'semantics': 'Final passing attempts only; earlier failures retained in each case record'},
            'main_service_restarted': False, 'new_provider_added': False, 'published': False, 'CONTENT_INTELLIGENCE_READY': 'NO'}


def export():
    from PIL import Image, ImageDraw, ImageFont
    result = verify(); config = Config(); rows = ['# Năm video dùng cách đọc B', '',
        'Owner đã duyệt giọng B ở tám chỗ đầu câu. Năm video dưới đây dùng lại các mẫu đã nghe và áp dụng cách đọc có ngữ cảnh cho các cảnh còn lại. Giữ nguyên lời v2, hình/cách dựng và nguồn đã duyệt.', '',
        'Bản MP4 đầy đủ vẫn cần Owner xem/nghe. Tách câu dựa trên mốc nhận diện AssemblyAI và khoảng nghỉ đo được; đây không phải forced word alignment. Sai khác ASR với lời đã duyệt được ghi trong hồ sơ, chưa đủ để kết luận giọng đọc sai từ.', '']
    for c in result['cases']:
        folder = OUT / f"case-{c['case']:02}"; actual = config.data_root / 'jobs' / c['job_id']
        for name in ('final.mp4','voice.wav','voice.json','tts-plan.json','input.json','qc-report.json','ffprobe.json','render-manifest.json','timeline.json','subtitles.ass'):
            copy(actual / name, folder / name)
        # Export every actual attempt, including failed boundary checks and their
        # original status/receipts. Keep the passing evidence path for convenience.
        for attempt in c['actual_tts_attempts']:
            actual_attempt = actual / 'attempts' / attempt['name']
            for entry in attempt['source_files']:
                source = actual_attempt / entry['path']
                assert file_sha(source) == entry['sha256']
                copy(source, folder / 'tts-attempts' / attempt['name'] / entry['path'])
                if attempt['name'] == c['active_passing_tts_attempt']:
                    copy(source, folder / 'tts-evidence' / entry['path'])
        preserve(folder / 'tts-attempt-manifest.json', {
            'active_passing_tts_attempt': c['active_passing_tts_attempt'],
            'attempts': c['actual_tts_attempts'], 'failed_attempts': c['failed_tts_attempts'],
            'source_totals': c['source_totals'],
            'current_successful_attempt_counts': c['current_successful_attempt_counts'],
            'failure_evidence_preserved': True, 'human_final_video_approved': False})
        preserve(folder / 'acceptance.json', {**c, 'state': 'FULL_NEW_VIDEO_OWNER_REVIEW_PENDING', 'CONTENT_INTELLIGENCE_READY': 'NO'})
        render = read(actual / 'render-manifest.json'); frames = []; images = []
        for scene in render['scenes']:
            cues = [cue for cue in render['captions'] if scene['start'] <= cue['start'] and cue['end'] <= scene['end']]
            cue = cues[len(cues)//2] if cues else None
            seconds = (cue['start'] + cue['end'])/2 if cue else (scene['start'] + scene['end'])/2
            frame_path = folder / f"scene-{scene['scene']:02}.png"
            if not frame_path.exists():
                subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-loglevel','error','-nostdin','-n',
                    '-ss',f'{seconds:.5f}','-i',str(actual/'final.mp4'),'-frames:v','1',str(frame_path)],check=True,capture_output=True,timeout=30)
            with Image.open(frame_path) as frame: images.append(frame.convert('RGB').resize((270,480),Image.Resampling.LANCZOS))
            frames.append({'scene':scene['scene'],'seconds':seconds,'frame_sha256':file_sha(frame_path),'source_MP4_sha256':c['final_sha256']})
        sheet_path = folder/'contact-sheet.png'
        if not sheet_path.exists():
            sheet = Image.new('RGB',(1350,532),'#09211f'); draw = ImageDraw.Draw(sheet)
            font = ImageFont.truetype('C:/Windows/Fonts/seguisb.ttf',25)
            draw.text((20,10),f"Ca {c['case']:02} · Giọng B · {c['video_duration_seconds']:.2f}s · Chờ xem/nghe",font=font,fill='#fcf9f1')
            for index,image in enumerate(images): sheet.paste(image,(index*270,52))
            sheet.save(sheet_path)
        preserve(folder/'frames.json',{'actual_MP4_frames':frames,'contact_sheet_sha256':file_sha(sheet_path)})
        target = '–'.join(map(str,c['duration_target'])) + 's'
        note = 'Trong mục tiêu.' if c['duration_target_met'] else 'Ngắn hơn mục tiêu; cần Owner chấp nhận thời lượng hoặc yêu cầu sửa.'
        rows += [f"## Ca {c['case']:02} · {c['video_duration_seconds']:.2f}s", '', f'Mục tiêu {target}. {note}', '',
                 f"[Xem/nghe video]({(folder/'final.mp4').as_posix()}) · [Nghe WAV]({(folder/'voice.wav').as_posix()}) · [Studio](http://127.0.0.1:8026/?project={c['project_id']})", '',
                 f"![Năm cảnh trích từ video]({sheet_path.as_posix()})", '',
                 f"MP4 SHA256 `{c['final_sha256']}`. Native QC 11/11 PASS. Full human audio/video approval: PENDING.", '']
    rows += ['Giọng B đã được duyệt ở mẫu ngắn. Chỉ xác nhận xem/nghe và duyệt chính năm MP4 đầy đủ này mới hoàn tất nghiệm thu cuối.', '',
             'INTERNAL_PRODUCTION_READY = YES', '', 'CONTENT_INTELLIGENCE_READY = NO', '']
    (OUT/'review-bundle.md').write_text('\n'.join(rows),encoding='utf-8')
    preserve(OUT/'actual-verification.json', result)
    preserve(OUT/'review-manifest.json', {**result,'review_bundle_sha256':file_sha(OUT/'review-bundle.md')})
    print(json.dumps({'new_MP4s_exported':5,'durations':{c['case']:c['video_duration_seconds'] for c in result['cases']},'final_approved':0}),flush=True)


def persistence():
    result=verify(); before=read(OUT/'actual-verification.json')
    assert result['table_snapshots']==before['table_snapshots'] and result['cases']==before['cases']
    preserve(OUT/'fresh-process-persistence.json',{'fresh_process_reopen':'PASS','actual_same_projects_jobs_artifacts_and_approvals':True,
             'table_snapshots':result['table_snapshots'],'main_service_restart_performed':False,'human_final_video_approvals':0})
    print(json.dumps({'fresh_process_reopen':'PASS','main_service_restart_performed':False}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=('cache','prepare','dispatch','status','resume','export','persistence'))
    globals()[parser.parse_args().action]()
