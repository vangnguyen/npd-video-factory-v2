"""Master Spec flow A: actual local media chain, explicit fixture ASR/reviewer.

Reuses a hash-pinned, already generated speech WAV. No inference, provider key,
network dispatch, publication or Owner acceptance is authorized by this runner.
The output is a CI candidate for Artifact A, not its real-provider acceptance.
"""
from contextlib import ExitStack
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import uuid
import wave

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'apps/api'))
from services.windows_native import asr, auto_edit_timeline as timeline
from services.windows_native import source_broll, source_reframe, source_settings
from services.windows_native import source_linked_edit, source_media_tracks
from services.windows_native.auto_edit_analysis import asset_reference
from services.windows_native.backup import create_backup, restore_backup
from services.windows_native.contracts import WorkflowError, file_sha, digest
from services.windows_native.hardening import durable_json
from services.windows_native.multipart_ingestion import NativeMultipartIngestion, CHUNK_BYTES
from services.windows_native.pipeline import Config, Pipeline
from services.windows_native.server import Runner
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.source_assets import canonical_assets
from services.windows_native.source_preview import resolve_assets
from services.windows_native.store import Store
from app.subtitle_templates import load_templates

REQUIRED = ('final.mp4', 'preview.mp4', 'timeline.json', 'transcript.json',
    'scene-analysis.json', 'highlight-analysis.json', 'asset-provenance.json',
    'subtitles.json', 'audio-analysis.json', 'render-manifest.json', 'qc.json',
    'job-events.json', 'cost.json')


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def speech_fixture(wav_path, metadata_path, expected):
    """Bind reused speech and synthetic word intervals; never infer alignment."""
    check(file_sha(wav_path) == expected, 'Reused speech SHA256 changed')
    metadata = json.loads(metadata_path.read_bytes())
    check(metadata['audio_sha256'] == expected, 'Speech metadata binding changed')
    with wave.open(str(wav_path), 'rb') as stream:
        duration = stream.getnframes() / stream.getframerate()
    check(abs(duration - metadata['duration_seconds']) < .001, 'Speech duration differs')
    words = []
    previous = 0
    for unit in metadata['units']:
        start, end = unit['activity_start_seconds'], unit['activity_end_seconds']
        tokens = unit['text'].split()
        check(tokens and previous <= start < end <= duration, 'Speech unit bounds invalid')
        # These uniformly spaced intervals are deliberately CI input, not ASR.
        width = (end - start) / len(tokens)
        for index, text in enumerate(tokens):
            words.append({'text': text, 'start': round((start + index * width) * 1000),
                'end': round((start + (index + .9) * width) * 1000), 'confidence': .9})
        previous = end
    check(words, 'No reused speech units')
    return duration, metadata, words


def physical_sources(root):
    return {str(p.relative_to(root)).replace('\\', '/'): file_sha(p)
        for name in ('assets', 'originals') for p in (root / name).rglob('*') if p.is_file()}


def upload(store, uploads, project_id, path, kind, mime):
    project = store.get(project_id)
    row = uploads.create(project_id, {'revision': project['revision'], 'kind': kind,
        'content_type': mime, 'filename': path.name, 'total_bytes': path.stat().st_size,
        'expected_sha256': file_sha(path), 'rights_confirmed': True,
        'illustration': kind == 'video', 'request_key': uuid.uuid4().hex}, actor='CI_FIXTURE_EDITOR')[0]
    with path.open('rb') as stream:
        offset = 0
        while chunk := stream.read(CHUNK_BYTES):
            row = uploads.chunk(project_id, row['upload_id'], offset,
                hashlib.sha256(chunk).hexdigest(), chunk)[0]
            offset += len(chunk)
    result = uploads.complete(project_id, row['upload_id'], {'revision': project['revision'],
        'expected_parts_sha256': row['parts_sha256']})[0]
    check(result['result']['source_sha256'] == file_sha(path), 'Ingest changed original source')
    return result


def run_job(store, config, project_id, kind):
    project = store.get(project_id)
    job = store.enqueue(project_id, project['revision'], kind, uuid.uuid4().hex)
    check(Runner(store, Pipeline(config)).run_one(), 'Worker did not claim ' + kind)
    result = store.get_job(job['id'])
    check(result['status'] == 'succeeded', kind + ' failed: ' + str(result.get('error')))
    return result


def current_binding(store, project_id):
    project = timeline.view(store, project_id)
    return project, {'expected_version': project['shot_timeline']['version']}


def cold_verify(backup, sha, project_id, job_id, destination):
    """Separate interpreter restore, with provider dispatch forbidden."""
    restore_backup(backup, destination, expected_sha256=sha)
    store = Store(destination)
    project = store.get(project_id)
    with patch('services.windows_native.asr.analyze', side_effect=AssertionError('No cold ASR replay')), \
            patch('services.windows_native.pipeline.generate', side_effect=AssertionError('No cold AI replay')):
        resolve_assets(Config(data_root=destination), project)
        # Verified checkpoint only; do not enqueue another render or accept UAT.
        with store.transaction() as con:
            verified, _ = store.verified_render(job_id, con)
    check(verified['id'] == job_id, 'Cold restore returned another render')
    return {'project_sha256': digest(project), 'job_sha256': digest(store.get_job(job_id)),
        'physical_sources': physical_sources(destination), 'provider_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--speech-wav', type=Path)
    parser.add_argument('--speech-metadata', type=Path)
    parser.add_argument('--expected-speech-sha256')
    parser.add_argument('--cold-context', type=Path)
    args = parser.parse_args()
    if args.cold_context:
        context = json.loads(args.cold_context.read_bytes())
        with tempfile.TemporaryDirectory(prefix='vf-mode-b-ci-cold-') as owned:
            result = cold_verify(context['backup'], context['backup_sha256'], context['project_id'],
                context['job_id'], Path(owned) / 'state')
        print(json.dumps(result, ensure_ascii=False))
        return
    check(all((args.output, args.speech_wav, args.speech_metadata, args.expected_speech_sha256)),
        'Output and hash-pinned reused speech are required')
    out = args.output.resolve()
    check(not out.exists() and out != REPO and REPO not in out.parents, 'Fresh external output required')
    duration, speech, words = speech_fixture(args.speech_wav, args.speech_metadata, args.expected_speech_sha256)
    out.mkdir(parents=True)
    durable_json(out / 'scope.json', {'schema': 'north-star-mode-b-ci-v1',
        'master_spec_flow': 'A / deterministic CI', 'artifact_A': 'CI_CANDIDATE',
        'source_video': 'generated moving test pixels plus reused local-real TTS speech',
        'speech_sha256': args.expected_speech_sha256, 'speech_duration_seconds': duration,
        'ASR': 'explicit mocked provider response; synthetic word intervals',
        'reviewer': 'simulated CI reviewer; not Owner', 'real_provider_calls': 0,
        'new_TTS_calls': 0, 'paid_calls': 0, 'real_asr_acceptance': False,
        'subject_tracking_accepted': False, 'whole_UI_flow_tested': False,
        'owner_UAT': False, 'full_Mode_B_ready': False, 'publishing_enabled': False,
        'production_deployed': False})
    durable_json(out / 'fixture-word-intervals.json', {'synthetic_fixture': True,
        'alignment_is_not_measured': True, 'words': words, 'speech_units': speech['units']})
    with tempfile.TemporaryDirectory(prefix='vf-mode-b-ci-') as owned_name, ExitStack() as stack:
        owned = Path(owned_name)
        config = Config(data_root=owned / 'state')
        store = Store(config.data_root)
        project = store.create('Master Spec Mode B CI candidate — not Owner UAT', '', 'media')
        project_id = project['id']
        uploads = NativeMultipartIngestion(store, config, workspace_id='wsp_mode_b_ci_fixture')
        manager = None
        try:
            source = owned / 'generated-pixels-reused-speech.mp4'
            subprocess.run([str(config.ffmpeg_bin / 'ffmpeg.exe'), '-v', 'error', '-nostdin', '-n',
                '-f', 'lavfi', '-i', f'testsrc2=s=640x360:r=30:d={duration}',
                '-i', str(args.speech_wav), '-c:v', 'libx264', '-preset', 'ultrafast',
                '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-t', str(duration), str(source)],
                check=True, capture_output=True, timeout=45)
            source_receipt = upload(store, uploads, project_id, source, 'video', 'video/mp4')
            durable_json(out / 'upload-video.json', source_receipt)
            calls = []

            class FixtureTransport(asr.DurableTransport):
                async def request(self, method, path, credential, timeout, **kwargs):
                    calls.append({'method': method, 'path': path, 'fixture': True})
                    if path == '/v2/upload':
                        return {'upload_url': 'https://cdn.assemblyai.com/mode-b-ci-fixture.wav'}
                    if path == '/v2/transcript':
                        return {'id': 'mode-b-ci-explicit-fixture'}
                    check(method == 'GET' and path == '/v2/transcript/mode-b-ci-explicit-fixture',
                        'Unexpected fixture request')
                    return {'id': 'mode-b-ci-explicit-fixture', 'status': 'completed',
                        'language_code': 'vi', 'speech_model_used': 'universal-3-5-pro',
                        'text': ' '.join(unit['text'] for unit in speech['units']),
                        'words': words, 'explicit_test_fixture': True,
                        'alignment_is_not_measured': True}

            original_analyze = asr.analyze
            stack.enter_context(patch.object(asr.connection, 'status', return_value={'connected': True}))
            stack.enter_context(patch.object(asr.connection, 'load_credential', return_value='EXPLICIT_CI_FIXTURE_NOT_A_SECRET'))
            stack.enter_context(patch.object(asr.DurableTransport, 'request', side_effect=AssertionError('External ASR forbidden')))
            stack.enter_context(patch.object(asr, 'analyze', side_effect=lambda c, j, o, s:
                original_analyze(c, j, o, s, transport_factory=FixtureTransport)))
            stack.enter_context(patch('services.windows_native.pipeline.generate', side_effect=AssertionError('New AI calls forbidden')))
            asr_job = run_job(store, config, project_id, 'asr')
            durable_json(out / 'asr-job.json', asr_job)
            durable_json(out / 'fixture-provider-calls.json', calls)
            check(len(calls) == 3, 'Unexpected ASR fixture dispatch count')
            analysis_job = run_job(store, config, project_id, 'auto_edit_analysis')
            project = store.get(project_id)
            analysis = project['document']['auto_edit_analyses'][0]['analysis']
            check(analysis['transcript'] and analysis['scenes'] and analysis['highlights'], 'Incomplete analysis')
            decisions = [item for item in analysis['silence_decisions'] if item['enabled']]
            check(decisions, 'No actual measured reviewable silence cuts')
            for decision in decisions:
                check(not any(decision['start_seconds'] < word['end']/1000 and
                    decision['end_seconds'] > word['start']/1000 for word in words), 'Cut crosses a fixture word')
            for filename, value in (('transcript', analysis['transcript']), ('scene-analysis', analysis['scenes']),
                    ('highlight-analysis', analysis['highlights']), ('silence-decisions', analysis['silence_decisions'])):
                durable_json(out / (filename + '.json'), value)
            durable_json(out / 'analysis-job.json', analysis_job)
            # Explicitly review a highlight candidate without narrowing away the other speech unit.
            durable_json(out / 'highlight-review.json', {'simulated_reviewer': True,
                'candidates': [item['highlight_id'] for item in analysis['highlights']],
                'decision': 'keep both speech units for this CI master', 'auto_shorts_selected': False})
            project = timeline.create(store, project_id, project['revision'], {
                'analysis_id': analysis['analysis_id'], 'transcript_id': analysis['transcript']['transcript_id'],
                'silence_decision_ids': [item['decision_id'] for item in decisions], 'aspect_ratio': '9:16'})
            # Exercise a source shot edit, then reversible undo through the same canonical history.
            before_edit = copy.deepcopy(project)
            clip = next(clip for track in project['shot_timeline']['snapshot']['tracks']
                if track['kind'] == 'source' for clip in track['clips'])
            project = source_linked_edit.edit(store, project_id, project['revision'], {
                'expected_version': project['shot_timeline']['version'],
                'operation': {'type': 'set_clip_properties', 'clip_id': clip['clip_id'], 'opacity': .9}})
            project = timeline.restore(store, project_id, project['revision'], {
                'expected_version': project['shot_timeline']['version'], 'restore_revision': before_edit['revision']})
            check(project['shot_timeline']['snapshot'] == before_edit['shot_timeline']['snapshot'], 'Undo changed canonical content')
            project = source_reframe.apply(store, project_id, project['revision'], {
                'expected_version': project['shot_timeline']['version'], 'aspect_ratio': '9:16', 'mode': 'center_crop'})
            check(project['shot_timeline']['snapshot']['metadata']['reframe_review']['needs_attention'],
                'Unmeasured subject crop must require review')
            template = next(item['template_ref'] for item in load_templates()
                if item['style']['animation'] == 'word_by_word')
            project = source_settings.configure(store, project_id, project['revision'], {
                'expected_version': project['shot_timeline']['version'], 'subtitle_template_ref': template,
                'preview_mode': 'final_effects', 'audio_processing': {
                    'normalize_original_audio': True, 'normalize_music': True, 'duck_music': True}})
            broll_path = owned / 'generated-supporting-motion.mp4'
            subprocess.run([str(config.ffmpeg_bin / 'ffmpeg.exe'), '-v', 'error', '-nostdin', '-n',
                '-f', 'lavfi', '-i', 'testsrc2=s=360x640:r=30:d=2', '-an', '-c:v', 'libx264',
                '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(broll_path)],
                check=True, capture_output=True, timeout=30)
            support = upload(store, uploads, project_id, broll_path, 'video', 'video/mp4')['result']['asset']
            project, binding = current_binding(store, project_id)
            project = source_broll.create(store, config, project_id, project['revision'], binding)
            plan = project['document']['source_broll_plans'][-1]['plan']
            item = plan['items'][0]
            project = source_broll.select(store, config, project_id, project['revision'], {
                'expected_version': project['shot_timeline']['version'], 'media_plan_id': plan['media_plan_id'],
                'expected_plan_version': plan['version'], 'item_id': item['media_plan_item_id'],
                'asset_id': asset_reference(support)})
            plan = project['document']['source_broll_plans'][-1]['plan']
            project = source_broll.apply(store, config, project_id, project['revision'], {
                'expected_version': project['shot_timeline']['version'], 'media_plan_id': plan['media_plan_id'],
                'expected_plan_version': plan['version'], 'item_ids': [item['media_plan_item_id']]})
            durable_json(out / 'media-plan.json', plan)
            music_path = owned / 'generated-tone-bed-not-licensed-song.wav'
            subprocess.run([str(config.ffmpeg_bin / 'ffmpeg.exe'), '-v', 'error', '-nostdin', '-n',
                '-f', 'lavfi', '-i', 'sine=frequency=220:duration=2', '-ar', '48000', '-ac', '1',
                '-c:a', 'pcm_s16le', str(music_path)], check=True, capture_output=True, timeout=20)
            music = upload(store, uploads, project_id, music_path, 'music', 'audio/wav')['result']['asset']
            project, binding = current_binding(store, project_id)
            state = project['document']['canonical_timeline']
            music_result = source_media_tracks.add_audio(store, project_id, {
                **binding, 'revision': project['revision'], 'timeline_sha256': state['sha256'],
                'asset_id': music['id'], 'asset_sha256': music['sha256'], 'request_key': uuid.uuid4().hex,
                'role': 'music', 'source_start': 0, 'source_end': 2, 'timeline_start': 0,
                'volume': .1, 'repeat_until': state['snapshot']['duration_seconds'],
                'crossfade_seconds': .2, 'fade_in_seconds': .1, 'fade_out_seconds': .1}, actor_ref='CI_FIXTURE_EDITOR')
            durable_json(out / 'music-import.json', music_result)
            immutable = physical_sources(config.data_root)
            project = store.get(project_id)
            frozen = copy.deepcopy(project['document'])
            snapshot = frozen['canonical_timeline']['snapshot']
            sources = [clip for track in snapshot['tracks'] if track['kind'] == 'source'
                for clip in track['clips'] if not clip['disabled']]
            for word in words:
                check(any(clip['source_start'] <= word['start']/1000 < word['end']/1000 <= clip['source_end']
                    for clip in sources), 'Canonical cut removed a fixture speech word')
            for kind in ('source', 'original_audio'):
                coordinates = [(clip['source_start'], clip['source_end'], clip['timeline_start'])
                    for track in snapshot['tracks'] if track['kind'] == kind for clip in track['clips']]
                if kind == 'source':
                    visual_coordinates = coordinates
                else:
                    check(coordinates == visual_coordinates, 'Source video/audio edit windows differ')
            try:
                store.enqueue(project_id, project['revision'], 'render', uuid.uuid4().hex)
            except WorkflowError as error:
                check(error.code == 'AUTO_EDIT_HUMAN_APPROVAL_REQUIRED_BEFORE_RENDER', 'Unexpected preapproval failure')
            else:
                raise AssertionError('Render started without simulated approval')
            manager = PreviewManager(config, store)
            manager.generate(project_id, project['revision'])
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                preview = manager.status(project_id)
                if preview['status'] not in {'QUEUED', 'RUNNING'}:
                    break
                time.sleep(.1)
            check(preview['status'] == 'READY', 'Preview failed: ' + str(preview.get('error')))
            preview_path = manager.video_path(project_id, preview['timeline_version'])
            shutil.copyfile(preview_path, out / 'preview.mp4')
            durable_json(out / 'preview.json', preview)
            store.approve(project_id, project['revision'], 'SIMULATED CI REVIEW — NOT OWNER UAT', True)
            render = run_job(store, config, project_id, 'render')
            check(render['result']['qc']['passed'], 'Full QC failed')
            check(not render['result']['qc']['human_final_video_accepted'], 'Owner gate falsely accepted')
            check(store.get(project_id)['document'] == frozen, 'Render mutated canonical content')
            try:
                store.final_video(render['id'])
            except WorkflowError as error:
                check(error.code == 'HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED', 'Unexpected final download block')
            else:
                raise AssertionError('Owner final review gate bypassed')
            jobdir = config.data_root / 'jobs' / render['id']
            final_manifest = json.loads((jobdir / 'timeline-render.json').read_bytes())
            actual_words = [word for cue in final_manifest['subtitles'] for word in cue['words']]
            check([word['text'] for word in actual_words] == [word['text'] for word in words],
                'Renderer subtitle text lost or duplicated speech words')
            attempts = list((preview_path.parent / 'attempts').glob('effects-preview-*'))
            check(len(attempts) == 1, 'Fresh preview must have exactly one effects attempt')
            preview_manifest = json.loads((attempts[0] / 'timeline-render.json').read_bytes())
            def effects(manifest):
                return {'metadata': manifest['metadata'], 'subtitles': [
                    {key: value for key, value in cue.items() if key != 'cue_id'} for cue in manifest['subtitles']],
                    'subtitle_style': manifest['subtitle_style'], 'brand': manifest['brand'],
                    'visual_clips': [{key: value for key, value in clip.items() if key != 'uri'}
                        for clip in manifest['visual_clips']]}
            check(effects(preview_manifest) == effects(final_manifest), 'Preview/final effects differ')
            check(file_sha(Path(preview_manifest['audio']['mix_uri'])) == file_sha(Path(final_manifest['audio']['mix_uri'])),
                'Preview/final canonical PCM mix differs')
            durable_json(out / 'preview-timeline-render.json', preview_manifest)
            for name in ('final.mp4', 'timeline.json', 'timeline-render.json', 'subtitles.json',
                    'audio-analysis.json', 'audio-balance.json', 'source-audio-clocks.json',
                    'canonical-audio-mux.json', 'render-manifest.json', 'ffprobe.json', 'cost.json',
                    'checkpoint-render.json', 'render-frame-qc.json', 'source-media-imports.json'):
                shutil.copyfile(jobdir / name, out / name)
            shutil.copyfile(jobdir / 'qc-report.json', out / 'qc.json')
            shutil.copytree(jobdir / 'render-frame-qc', out / 'render-frame-qc')
            durable_json(out / 'asset-provenance.json', {'assets': canonical_assets(frozen),
                'source_pixels': 'generated fixture', 'speech': 'reused local-real TTS; Owner review deferred',
                'word_alignment': 'synthetic fixture', 'publishing_enabled': False})
            durable_json(out / 'project.json', store.get(project_id))
            durable_json(out / 'render-job.json', render)
            with store.transaction() as con:
                events = [{**dict(row), 'payload': json.loads(row['payload'])} for row in con.execute(
                    'SELECT * FROM events WHERE project_id=? ORDER BY id', (project_id,))]
            durable_json(out / 'job-events.json', events)
            check(physical_sources(config.data_root) == immutable, 'Source bytes mutated')
            check(file_sha(args.speech_wav) == args.expected_speech_sha256, 'Historical speech changed')
            for name in ('assets', 'originals'):
                shutil.copytree(config.data_root / name, out / name)
            manager.close()
            manager = None
            backup = create_backup(config, out / 'owned-state.zip')
            context = {'backup': backup['backup_path'], 'backup_sha256': backup['sha256'],
                'project_id': project_id, 'job_id': render['id']}
            context_path = out / 'cold-context.json'
            durable_json(context_path, context)
            cold = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--cold-context', str(context_path)],
                capture_output=True, text=True, encoding='utf-8', timeout=120)
            if cold.returncode:
                (out / 'cold-failure.log').write_text(cold.stderr, encoding='utf-8')
                raise AssertionError('Separate-process recovery failed: ' + cold.stderr[-4000:])
            restored = json.loads(cold.stdout)
            check(restored['project_sha256'] == digest(store.get(project_id)), 'Cold project changed')
            check(restored['job_sha256'] == digest(render), 'Cold job changed')
            check(restored['physical_sources'] == immutable, 'Cold source SHA differs')
            durable_json(out / 'cold-restore.json', {'separate_interpreter': True, 'exact_project': True,
                'exact_job': True, 'exact_source_hashes': True, 'provider_calls': 0, **context})
            check(all((out / name).is_file() for name in REQUIRED), 'Required Artifact A CI outputs missing')
            receipt = {'schema': 'north-star-mode-b-ci-v1', 'ci_chain_passed': True,
                'artifact_A_real_acceptance': False, 'owner_UAT': False, 'full_Mode_B_ready': False,
                'real_provider_calls': 0, 'paid_calls': 0, 'new_TTS_calls': 0,
                'ASR_fixture_requests': len(calls), 'silence_decisions_applied': len(decisions),
                'scene_count': len(analysis['scenes']), 'highlight_count': len(analysis['highlights']),
                'source_duration_seconds': duration, 'render_duration_seconds': frozen['canonical_timeline']['snapshot']['duration_seconds'],
                'source_words_preserved': len(words), 'final_review_gate_retained': True,
                'canonical_undo_passed': True, 'cold_restore_passed': True,
                'preapproval_render_blocked': True, 'preview_final_effects_equal': True,
                'preview_final_PCM_mix_equal': True, 'all_rendered_subtitle_words_preserved': True,
                'cleanup': 'owned TemporaryDirectory lifecycle after immutable export',
                'exports': {str(p.relative_to(out)).replace('\\', '/'): file_sha(p)
                    for p in out.rglob('*') if p.is_file()}}
            durable_json(out / 'evidence.json', receipt)
            print(json.dumps({key: value for key, value in receipt.items() if key != 'exports'}, ensure_ascii=False))
        except BaseException as error:
            durable_json(out / 'failure.json', {'type': type(error).__name__, 'message': str(error),
                'project_id': project_id, 'fixture_only': True, 'owner_UAT': False})
            durable_json(out / 'failed-project.json', store.get(project_id))
            for path in config.data_root.rglob('*.log'):
                target = out / 'failure-logs' / path.relative_to(config.data_root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            raise
        finally:
            if manager is not None:
                manager.close()


if __name__ == '__main__':
    main()
