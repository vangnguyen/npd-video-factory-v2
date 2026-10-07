"""Actual offline Native restore rehearsal using fixture research/money and real media."""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess

from services.windows_native.backup import create_backup, restore_backup
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.costs import CostLedger
from services.windows_native.intelligence_service import IntelligenceService
from services.windows_native.media import ingest_media, media_path
from services.windows_native.pipeline import Config
from services.windows_native.store import Store
from services.windows_native.tests.test_multi_niche import build_tech_project, ExplicitAIIdeasFixture


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


def run(base, output, ffmpeg):
    base.mkdir(parents=True, exist_ok=False)
    output.mkdir(parents=True, exist_ok=False)
    source = base / 'source'
    config, store, service, project, research, unrelated = build_tech_project(source)
    config = replace(config, ffmpeg_bin=ffmpeg.parent)
    fixture_video = base / 'explicit-source-fixture.mp4'
    subprocess.run([str(ffmpeg), '-nostdin', '-hide_banner', '-loglevel', 'error',
        '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30', '-f', 'lavfi', '-i',
        'sine=frequency=600:sample_rate=48000', '-t', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-y', str(fixture_video)], check=True, timeout=60, capture_output=True)
    asset = ingest_media(config, fixture_video, 'video/mp4', 'explicit-source-fixture.mp4',
        rights_confirmed=True, illustration=True)
    project = store.append_media(project['id'], project['revision'], asset)
    before = store.shot_view(project['id'])
    project = store.mutate_shots(project['id'], project['revision'],
        {'type': 'reorder', 'shot_ids': [shot['shot_id'] for shot in before['shot_timeline']['shots']]})
    ledger = CostLedger(store)
    cost_id = ledger.begin(project_id=project['id'], provider='explicit-cost-fixture', model='no-provider',
        operation='retained-unknown-cost', request_sha256='a' * 64, estimated_cost=None, external_call=False)
    ledger.settle(cost_id, status='outcome_unknown', error_code='ExplicitFixtureTimeout')
    expected_project = store.get(project['id'])
    expected_versions = store.versions(project['id'])
    expected_research = service.bundle(research['run']['id'])
    expected_costs = ledger.summary(project['id'])
    expected_asset_sha = file_sha(media_path(config, asset['id']))
    package = base / 'native-offline-backup.zip'
    backup = create_backup(config, package)
    destination = base / 'restored'
    restored = restore_backup(package, destination, expected_sha256=backup['sha256'])
    # This fresh, explicitly owned fixture is retained elsewhere, so restored reads
    # cannot accidentally fall back to original paths. No accepted/live root moves.
    retained_source = base / 'retained-original'
    assert source.resolve().parent == base.resolve() and retained_source.resolve().parent == base.resolve()
    source.rename(retained_source)
    assert not source.exists()
    recovered_config = Config.load(restored['runtime_config_path'])
    recovered_store = Store(destination)
    recovered_service = IntelligenceService(recovered_config, recovered_store, idea_provider=ExplicitAIIdeasFixture())
    assert recovered_store.get(project['id']) == expected_project
    assert recovered_store.versions(project['id']) == expected_versions
    assert recovered_service.bundle(research['run']['id']) == expected_research
    recovered_service.verify_sources(expected_research['sources'], expected_research['findings'])
    assert CostLedger(recovered_store).summary(project['id']) == expected_costs
    assert recovered_store.get(unrelated['id']) == unrelated
    recovered_video = media_path(recovered_config, asset['id'])
    assert file_sha(recovered_video) == expected_asset_sha
    decoded = subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-i', str(recovered_video),
        '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'], capture_output=True, timeout=60)
    assert decoded.returncode == 0, 'Actual restored synthetic video/audio must decode'
    current = recovered_store.shot_view(project['id'])
    restored_shot = current['shot_timeline']['shots'][0]
    changed_text = restored_shot['on_screen_text'] + ' · Khôi phục fixture'
    edited = recovered_store.mutate_shots(project['id'], current['revision'],
        {'type': 'update', 'shot_id': restored_shot['shot_id'], 'values': {'on_screen_text': changed_text}})
    assert edited['revision'] == current['revision'] + 1 and edited['approval'] is None
    assert edited['shot_timeline']['shots'][0]['on_screen_text'] == changed_text
    try:
        recovered_store.enqueue(project['id'], edited['revision'], 'render', 'restored-render-must-block')
        raise AssertionError('Restoration must not create human approval')
    except WorkflowError as error:
        assert 'HUMAN_APPROVAL' in error.code
    write(output / 'backup-receipt.json', backup)
    write(output / 'restore-receipt.json', restored)
    write(output / 'project-before.json', expected_project)
    write(output / 'project-after-restore.json', current)
    write(output / 'project-after-editor.json', edited)
    write(output / 'versions.json', expected_versions)
    write(output / 'research.json', expected_research)
    write(output / 'cost.json', expected_costs)
    write(output / 'asset-recovery.json', {'asset': asset, 'sha256': expected_asset_sha,
        'recovered_path': str(recovered_video), 'full_video_audio_decode': True,
        'content': 'explicit 2-second FFmpeg test pattern/sine fixture; no speech or AI',
        'unrelated_project_sha256': digest(unrelated), 'original_root_unavailable': True})
    receipt = {'schema': 'north-star-native-restore-contract-v1', 'status': 'PASS',
        'fixture_research_and_ideas': True, 'fixture_money': True, 'local_real_sqlite': True,
        'database_history_exact': True, 'research_exact': True, 'costs_exact': True, 'asset_sha_exact': True,
        'actual_restored_media_decode': True, 'editor_continues': True, 'approval_not_invented': True,
        'original_fixture_retained': str(retained_source), 'backup_sha256': backup['sha256'],
        'external_provider_calls': 0, 'paid_operations': 0, 'services_started': False,
        'owner_uat_accepted': False, 'production_deployed': False,
        'exports_sha256': {path.name: file_sha(path) for path in output.glob('*.json')}}
    write(output / 'receipt.json', receipt)
    print(json.dumps({'status': 'PASS', 'exports': 10, 'backup_entries': backup['entries'],
        'backup_sha256': backup['sha256'], 'output_root': str(output)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    args = parser.parse_args()
    run(args.fixture_root.resolve(), args.output_root.resolve(), args.ffmpeg.resolve())
