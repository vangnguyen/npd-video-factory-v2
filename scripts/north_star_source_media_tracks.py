"""Retained actual upload/controller/renderer/QC proof using owned synthetic media.

Speech evidence, signed human and DOM are fixtures. This never accepts Owner UAT
or invokes an external provider. Owned temporary data is cleaned after exporting
the immutable source copies and verified backup required to recover this run.
"""
import argparse
import copy
from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import unittest
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup, restore_backup
from services.windows_native.contracts import WorkflowError, file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.pipeline import Pipeline
from services.windows_native.server import LocalServer, Runner
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.source_media_tracks import catalog
from services.windows_native.source_preview import resolve_assets
from services.windows_native.source_settings import configure
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_source_media_tracks import prepare


def files(root):
    return {str(path.relative_to(root)).replace('\\', '/'): file_sha(path)
            for name in ('assets', 'originals') for path in (root / name).rglob('*') if path.is_file()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--source-caption-retiming', action='store_true')
    parser.add_argument('--visual-properties', action='store_true')
    parser.add_argument('--source-drag-drop', action='store_true')
    args = parser.parse_args()
    if args.source_drag_drop and (not args.visual_properties or args.source_caption_retiming):
        parser.error('--source-drag-drop requires --visual-properties and uses its own source caption fixture')
    out = args.evidence_dir.resolve()
    if out.exists() or out == REPO or REPO in out.parents:
        raise ValueError('A fresh external evidence directory is required')
    out.mkdir(parents=True)
    case = unittest.TestCase()
    server = manager = None
    try:
        prepare(case)
        original = files(case.root)
        raw, data = human_fixture('editor', workspace=case.workspace)
        access = NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),
            max_token_ttl_seconds=86400), case.workspace)
        server = LocalServer(0, case.config, start_worker=False, access=access)
        cookie, session = access.login(raw)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        current = case.store.get(case.project['id'])
        context = case.owned / 'signed-controller-context.json'
        context_body = {'fixture_human': True,
            'origin': 'http://127.0.0.1:' + str(server.server_port), 'workspace_id': case.workspace,
            'project': {'id': current['id'], 'revision': current['revision']},
            'cookie': cookie, 'csrf': session.csrf}
        controller_script = 'native_source_media_tracks_http_ui.mjs'
        if args.source_caption_retiming or args.source_drag_drop:
            context_body.update(source_video_asset_id=case.video['id'],source_video_asset_sha256=case.video['sha256'])
        if args.source_caption_retiming:
            controller_script = 'native_source_caption_retiming_http_ui.mjs'
        durable_json(context, context_body)
        result = subprocess.run([r'C:\Program Files\nodejs\node.exe',
            str(REPO / 'scripts' / controller_script), str(context)],
            capture_output=True, timeout=60, check=True)
        controller = json.loads(result.stdout)
        if not args.source_caption_retiming and (len(controller['requests']) != 6 or len(controller['imports']) != 3):
            raise AssertionError('Expected four explicit Studio mutations and two reads')
        if args.source_caption_retiming and (controller['reopened']['imports_total']!=2 or controller['reopened']['duration_seconds']!=3.75):
            raise AssertionError('Source follow/manual/reimport path differs')
        durable_json(out / 'signed-controller.json', controller)
        visual_controller = None
        if args.visual_properties:
            context_body['project'] = case.store.get(current['id'])
            durable_json(context, context_body)
            visual_run = subprocess.run([r'C:\Program Files\nodejs\node.exe',
                str(REPO/'scripts/native_source_visual_properties_http_ui.mjs'),str(context)],
                capture_output=True,timeout=90)
            if visual_run.returncode:
                raise AssertionError(visual_run.stderr.decode('utf-8',errors='replace')[:6000])
            visual_controller = json.loads(visual_run.stdout)
            durable_json(out/'visual-controller.json',visual_controller)
        drag_controller = None
        if args.source_drag_drop:
            context_body['project'] = case.store.get(current['id'])
            durable_json(context,context_body)
            drag_run = subprocess.run([r'C:\Program Files\nodejs\node.exe',
                str(REPO/'scripts/native_source_drag_drop_http_ui.mjs'),str(context)],capture_output=True,timeout=90)
            if drag_run.returncode:
                raise AssertionError(drag_run.stderr.decode('utf-8',errors='replace')[:6000])
            drag_controller=json.loads(drag_run.stdout)
            durable_json(out/'drag-controller.json',drag_controller)
        server.shutdown()
        server.server_close()
        thread.join()
        server = None
        current = case.store.get(current['id'])
        current = configure(case.store, current['id'], current['revision'], {
            'expected_version': current['document']['canonical_timeline']['version'],
            'preview_mode': 'final_effects', 'audio_processing': {
                'normalize_original_audio': True, 'normalize_music': True, 'duck_music': True}})
        before = copy.deepcopy(current['document'])
        manager = PreviewManager(case.config, case.store)
        manager.generate(current['id'], current['revision'])
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            preview = manager.status(current['id'])
            if preview['status'] not in {'QUEUED', 'RUNNING'}:
                break
            time.sleep(.1)
        if preview['status'] != 'READY':
            raise AssertionError(preview.get('error') or preview['status'])
        current = case.store.approve(current['id'], current['revision'],
            'AUTOMATED SYNTHETIC MOCK REVIEW — NOT OWNER UAT', True)
        job = case.store.enqueue(current['id'], current['revision'], 'render', uuid.uuid4().hex)
        if not Runner(case.store, Pipeline(case.config)).run_one():
            raise AssertionError('Render worker did not claim its job')
        render = case.store.get_job(job['id'])
        if render['status'] != 'succeeded' or not render['result']['qc']['passed']:
            raise AssertionError(render['error'])
        if render['result']['qc']['human_final_video_accepted'] or case.store.get(current['id'])['document'] != before:
            raise AssertionError('Owner acceptance or immutable source contract changed')
        final_review_required = False
        try:
            case.store.final_video(job['id'])
        except WorkflowError as error:
            if error.code != 'HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED':
                raise
            final_review_required = True
        if not final_review_required:
            raise AssertionError('Final review gate was bypassed')
        jobdir = case.root / 'jobs' / job['id']
        for name in ('final.mp4', 'timeline.json', 'timeline-render.json', 'subtitles.json',
                'audio-analysis.json', 'audio-balance.json', 'audio-stem-manifest.json',
                'render-manifest.json', 'ffprobe.json', 'cost.json', 'renderer-receipt.json',
                'checkpoint-render.json', 'render-frame-qc.json', 'source-media-imports.json'):
            shutil.copyfile(jobdir / name, out / name)
        shutil.copyfile(jobdir / 'qc-report.json', out / 'qc.json')
        shutil.copytree(jobdir / 'render-frame-qc', out / 'render-frame-qc')
        preview_path = manager.video_path(current['id'], preview['timeline_version'])
        shutil.copyfile(preview_path, out / 'preview.mp4')
        durable_json(out / 'preview.json', preview)
        preview_attempts = list((preview_path.parent / 'attempts').glob('effects-preview-*'))
        if len(preview_attempts) != 1:
            raise AssertionError('Fresh effects preview must have one attempt')
        preview_manifest = json.loads((preview_attempts[0] / 'timeline-render.json').read_bytes())
        final_manifest = json.loads((out / 'timeline-render.json').read_bytes())
        def effects(manifest):
            return {'metadata': manifest['metadata'], 'subtitles': [
                {key: value for key, value in cue.items() if key != 'cue_id'} for cue in manifest['subtitles']],
                'subtitle_style': manifest['subtitle_style'], 'brand': manifest['brand'],
                'visual_clips': [{key: value for key, value in clip.items() if key != 'uri'}
                    for clip in manifest['visual_clips']]}
        matching_effects = effects(preview_manifest) == effects(final_manifest)
        mix_sha = file_sha(Path(preview_manifest['audio']['mix_uri']))
        if not matching_effects or mix_sha != file_sha(Path(final_manifest['audio']['mix_uri'])):
            raise AssertionError('Preview/final effects or measured PCM mix differ')
        durable_json(out / 'preview-timeline-render.json', preview_manifest)
        analysis = current['document']['auto_edit_analyses'][0]['analysis']
        for name, value in [('transcript', analysis['transcript']), ('scene-analysis', analysis['scenes']),
                ('highlight-analysis', analysis['highlights']), ('silence-decisions', analysis['silence_decisions'])]:
            durable_json(out / (name + '.json'), value)
        from services.windows_native.source_assets import canonical_assets
        durable_json(out / 'asset-provenance.json', {'assets': canonical_assets(current['document']),
            'explicit_synthetic_fixture': True, 'speech_evidence': 'saved ASR fixture; no inference'})
        durable_json(out / 'project.json', case.store.get(current['id']))
        durable_json(out / 'job.json', render)
        with case.store.transaction() as con:
            events = [{**dict(row), 'payload': json.loads(row['payload'])} for row in con.execute(
                'SELECT * FROM events WHERE project_id=? ORDER BY id', (current['id'],))]
        durable_json(out / 'job-events.json', events)
        imports = json.loads((out / 'source-media-imports.json').read_bytes())
        expected_imports = 4 if args.source_drag_drop else 2 if args.source_caption_retiming else 3
        if len(imports['imports']) != expected_imports or len(imports['verified_active_source_sha256']) != expected_imports:
            raise AssertionError('Every active uploaded voice/music/SRT origin must be verified')
        checkpoint = json.loads((out / 'checkpoint-render.json').read_bytes())
        if 'source-media-imports.json' not in {item['path'] for item in checkpoint['artifacts']}:
            raise AssertionError('Checkpoint must bind imported source evidence')
        for name in ('preview', 'final'):
            sample_seconds=.35
            if args.source_caption_retiming:
                first=controller['reopened']['captions'][0]
                sample_seconds=first['timeline_start']+first['duration']/2
            subprocess.run([str(case.config.ffmpeg_bin / 'ffmpeg.exe'), '-v', 'error', '-nostdin', '-n',
                '-ss', str(sample_seconds), '-i', str(out / (name + '.mp4')), '-frames:v', '1',
                str(out / (name + '-caption-frame.png'))], check=True, capture_output=True, timeout=30)
        manager.close()
        manager = None
        source_page = catalog(case.store, current['id'], case.workspace)
        if args.source_caption_retiming or args.visual_properties:
            from services.windows_native.auto_edit_timeline import view
            durable_json(out/'timeline-editor.json',view(case.store,current['id']))
            with case.store.transaction() as con:
                saved_history=[{'revision':row['revision'],'canonical_timeline':json.loads(row['document']).get('canonical_timeline')}
                    for row in con.execute('SELECT revision,document FROM project_versions WHERE project_id=? ORDER BY revision',(current['id'],))
                    if json.loads(row['document']).get('canonical_timeline')]
            durable_json(out/'timeline-history.json',saved_history)
            durable_json(out/'media-tracks.json',source_page)
        backup = create_backup(case.config, out / 'backup.zip')
        destination = case.owned / 'restore'
        restore = restore_backup(backup['backup_path'], destination, expected_sha256=backup['sha256'])
        restored_store = Store(destination)
        if catalog(restored_store, current['id'], case.workspace) != source_page:
            raise AssertionError('Restored import/caption/waveform catalog differs')
        resolve_assets(replace(case.config, data_root=destination), restored_store.get(current['id']))
        if files(case.root) != original:
            raise AssertionError('Uploaded source bytes changed')
        for name in ('assets', 'originals'):
            shutil.copytree(case.root / name, out / name)
        durable_json(out / 'backup-restore.json', {'backup': backup, 'restore': restore,
            'catalog_equal': True, 'physical_origins_resolved_after_restore': True,
            'temporary_original_and_restore_removed_after_export': True})
        balance = render['result']['qc']['measured_audio_balance']
        receipt = {'schema_version': 'native-source-caption-retiming-render-proof-v1' if args.source_caption_retiming else 'native-source-media-tracks-render-proof-v1',
            'explicit_synthetic_media': True, 'synthetic_tones_not_speech': True,
            'saved_ASR_fixture': True, 'signed_human_fixture': True, 'fake_DOM': True,
            'project_id': current['id'], 'job_id': job['id'], 'actual_uploads': 4,
            'signed_controller_requests': len(controller['requests']), 'imports': expected_imports,
            'timeline_version': before['canonical_timeline']['version'],
            'actual_waveform_measurement': True, 'actual_preview_render_and_full_QC': True,
            'audio_balance_status': balance['status'], 'matching_preview_final_effects': matching_effects,
            'matching_preview_final_PCM_sha256': mix_sha, 'immutable_sources': original,
            'source_project_document_unchanged': True, 'backup_restore_passed': True,
            'imported_source_evidence_in_render_checkpoint': True,
            'final_download_blocked_without_final_review': True, 'human_final_video_accepted': False,
            'real_provider_calls': 0, 'new_ASR_or_TTS_calls': 0, 'paid_calls': 0,
            'browser_rendered': False, 'owner_UAT': False, 'real_speech_quality_accepted': False,
            'publishing_enabled': False, 'production_deployed': False,
            'complete_artifact_A_acceptance': False, 'owned_temporary_data_cleaned_after_export': True,
            'actual_shared_visual_properties_widget': args.visual_properties,
            'visual_widget_requests': len(visual_controller['requests']) if visual_controller else 0,
            'actual_source_drag_drop_controller': args.source_drag_drop,
            'drag_controller_requests': len(drag_controller['requests']) if drag_controller else 0,
            'whole_source_editor_DOM_exercised': False,
            'exports': {str(path.relative_to(out)).replace('\\', '/'): file_sha(path)
                for path in out.rglob('*') if path.is_file()}}
        if args.source_caption_retiming:
            receipt.update(source_caption_retiming=True,source_video_mutations_use_API_not_shot_UI=True,
                explicit_manual_caption_layout_preserved=True,explicit_reimport_returns_to_follow_video=True,
                duration_seconds=3.75,caption_count=len(source_page['captions']))
        durable_json(out / 'evidence.json', receipt)
        print(json.dumps({key: value for key, value in receipt.items() if key != 'exports'}, ensure_ascii=False))
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if manager is not None:
            manager.close()
        if hasattr(case, 'temp'):
            case.temp.cleanup()


if __name__ == '__main__':
    main()
