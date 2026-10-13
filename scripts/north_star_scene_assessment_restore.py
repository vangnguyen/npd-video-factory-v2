"""Verify a trusted offline scene/Shorts backup in a fresh owned state root.

This starts no server, worker, ASR, model or provider. It verifies saved evidence
and lineage only; it cannot certify Owner UAT, speech quality or production.
"""
import argparse
import json
from pathlib import Path
import re
import socket
import sys
import tempfile
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO / 'apps/api'), str(REPO)]
from services.windows_native.backup import guard, io_path, read_database, restore_backup, validate_archive
from services.windows_native.contracts import WorkflowError, canonical, digest, file_sha
from services.windows_native.store import Store
from services.windows_native import auto_edit_analysis, auto_edit_timeline, scene_assessments, source_shorts
from services.windows_native.asr import analysis_for_asset
from services.windows_native.media import project_assets, _verify_library_record
from services.windows_native.source_duplicate import transcript_checks


def require(value, code):
    if not value:
        raise WorkflowError(code)


def database_evidence(root):
    """Hash logical source rows without exporting transcript/private content."""
    con = read_database(root / 'workflow.sqlite3')
    try:
        evidence = {}
        for table in ('projects', 'jobs', 'project_versions', 'events'):
            cursor = con.execute('SELECT * FROM ' + table)
            columns = [item[0] for item in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            evidence[table] = {'count': len(rows), 'sha256': digest(sorted(rows, key=canonical))}
        return evidence
    finally:
        con.close()


def historical(store, project_id, revision):
    with store.transaction() as con:
        row = con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',
            (project_id, revision)).fetchone()
    require(row is not None, 'SCENE_RESTORE_SOURCE_VERSION_MISSING')
    return json.loads(row['document'])


def selected(document, project_id, analysis_id):
    asset_map = {item['id']: item for item in project_assets(document)}
    record = next((r for r in document.get('auto_edit_analyses', [])
        if r['analysis']['analysis_id'] == analysis_id), None)
    require(record is not None, 'SCENE_RESTORE_ANALYSIS_MISSING')
    asset = asset_map.get(record['native_asset_id'])
    require(asset is not None, 'SCENE_RESTORE_ASSET_MISSING')
    value = auto_edit_analysis.validate_record(record, project_id, document, asset)
    return auto_edit_analysis.selected_transcript(document, value), record


def transcript_content(value):
    if value is None:
        return None
    output = value.model_dump(mode='json')
    return {key: output[key] for key in ('version', 'is_original_evidence', 'provider_key', 'language', 'confidence')}, [
        {**{key: segment[key] for key in ('ordinal', 'start_seconds', 'end_seconds', 'text', 'confidence')},
            'words': [{key: word[key] for key in ('ordinal', 'start_seconds', 'end_seconds', 'text', 'confidence')}
                for word in segment['words']]} for segment in output['segments']]


def verify_media(store, projects, entry_map):
    assets = {}; analyses = {}; local_raw = {}
    for project in projects:
        for asset in project_assets(project['document']):
            path = _verify_library_record(store, {'metadata': asset, 'metadata_conflict': False})
            asset_key = 'state/assets/' + asset['id']
            require(asset_key in entry_map and entry_map[asset_key]['sha256'] == asset['sha256'],
                'SCENE_RESTORE_ASSET_NOT_ANCHORED')
            assets[asset['id']] = {'sha256': file_sha(path), 'bytes': path.stat().st_size,
                'original_sha256': asset.get('source_sha256') if asset.get('original_id') else None}
            record = analysis_for_asset(project['document'], asset)
            if asset.get('has_audio'):
                require(record is not None, 'SCENE_RESTORE_RAW_ASR_INVALID')
            if record is None:
                continue
            analyses[asset['id']] = {'analysis_sha256': record['analysis_sha256'],
                'saved_transcript_sha256': digest(record.get('transcript')),
                'source_sha256': record['source_sha256']}
            transcript = record.get('transcript') or {}
            provenance = transcript.get('provenance') or {}
            if not provenance.get('local_inference'):
                continue
            expected = provenance.get('raw_response_sha256')
            require(isinstance(expected, str) and re.fullmatch(r'[a-f0-9]{64}', expected),
                'SCENE_RESTORE_LOCAL_RAW_BINDING_INVALID')
            matches = []
            for row in entry_map.values():
                name = row['path']
                if not name.startswith('state/jobs/') or not name.endswith('/analysis/' + asset['id'] + '/local-transcript.json'):
                    continue
                path = io_path(store.root / name[len('state/'):])
                receipt = json.loads(path.read_bytes())
                if digest(receipt.get('raw')) == expected:
                    require(file_sha(path) == row['sha256'], 'SCENE_RESTORE_LOCAL_RAW_CHANGED')
                    matches.append({'path': name[len('state/'):], 'sha256': row['sha256'], 'raw_sha256': expected})
            require(matches, 'SCENE_RESTORE_LOCAL_RAW_MISSING')
            local_raw[asset['id']] = matches
    require(assets and analyses, 'SCENE_RESTORE_SOURCE_EVIDENCE_MISSING')
    return {'assets': assets, 'saved_asr': analyses, 'local_provider_raw_files': local_raw}


def verify_state(root, project_id, workspace, manifest):
    before = database_evidence(root)
    store = Store(root)
    parent = store.get(project_id)
    page = scene_assessments.page(store, project_id, workspace)
    require(page['items'], 'SCENE_RESTORE_ASSESSMENT_MISSING')
    require(any(item['current'] for item in page['items']), 'SCENE_RESTORE_CURRENT_ASSESSMENT_MISSING')
    if parent['document'].get('canonical_timeline'):
        auto_edit_timeline.validate_document(parent['document'])
    indexed = {item['assessment']['assessment_id']: item for item in page['items']}
    batches = source_shorts.view(store, project_id)['batches']
    verified_batches = []; verified_children = []; children = []
    for batch in batches:
        proof = batch.get('scene_evidence', {}).get('reviewed_local_scene_selection')
        if proof is None:
            continue
        record = indexed.get(proof.get('assessment_id'))
        require(record is not None and proof == scene_assessments.lineage(record),
            'SCENE_RESTORE_SHORT_PARENT_LINEAGE_INVALID')
        require(batch['source_project_id'] == project_id and batch['provider_calls'] == 0 and batch['paid_operations'] == 0,
            'SCENE_RESTORE_SHORT_BATCH_INVALID')
        original = historical(store, project_id, batch['source_revision'])
        require(digest(original) == batch['source_document_sha256'], 'SCENE_RESTORE_SHORT_SOURCE_CHANGED')
        parent_transcript, parent_analysis = selected(original, project_id, batch['analysis_id'])
        require(batch['transcript_id'] == (parent_transcript.transcript_id if parent_transcript else None),
            'SCENE_RESTORE_SHORT_TRANSCRIPT_CHANGED')
        require(batch['generated_count'] == len(batch['drafts']) and batch['drafts'], 'SCENE_RESTORE_SHORT_COUNT_INVALID')
        for draft in batch['drafts']:
            child_id = draft['project_id']
            require(re.fullmatch(r'[a-f0-9]{32}', child_id) and child_id != project_id,
                'SCENE_RESTORE_CHILD_ID_INVALID')
            child = store.get(child_id); document = child['document']
            state = auto_edit_timeline.validate_document(document); metadata = state['snapshot']['metadata']
            require(child['approval'] is None and not child['jobs'], 'SCENE_RESTORE_CHILD_AUTHORITY_TRANSFERRED')
            require(metadata['native_project_id'] == child_id and metadata.get('human_review_required') is True,
                'SCENE_RESTORE_CHILD_SCOPE_INVALID')
            require(not document.get('source_scene_assessments') and 'reviewed_local_scene_selection' not in metadata,
                'SCENE_RESTORE_CHILD_SELECTION_AUTHORITY_TRANSFERRED')
            short = metadata.get('source_short', {})
            require(short.get('parent_project_id') == project_id and short.get('parent_revision') == batch['source_revision']
                and short.get('parent_document_sha256') == batch['source_document_sha256'],
                'SCENE_RESTORE_CHILD_PARENT_CHANGED')
            require(metadata.get('highlight_draft', {}).get('reviewed_local_scene_selection') == proof
                and short.get('evidence', {}).get('reviewed_local_scene_selection') == proof,
                'SCENE_RESTORE_CHILD_LINEAGE_REBOUND')
            require(state['sha256'] == draft['timeline_sha256'], 'SCENE_RESTORE_CHILD_TIMELINE_CHANGED')
            archived = document.get('source_scene_inherited_assessment_history', [])
            original_record = {key: record[key] for key in ('assessment', 'sha256')}
            require(any(item.get('source_project_id') == project_id and item.get('original_record') == original_record
                and item.get('original_record_sha256') == digest(original_record)
                and item.get('authority_transferred') is False and item.get('new_review_required') is True for item in archived),
                'SCENE_RESTORE_CHILD_ASSESSMENT_ARCHIVE_INVALID')
            transcript_checks(document)
            child_transcript, child_analysis = selected(document, child_id, metadata['source_analysis_id'])
            require(transcript_content(child_transcript) == transcript_content(parent_transcript),
                'SCENE_RESTORE_CHILD_WORD_CONTENT_CHANGED')
            if parent_transcript:
                binding = child_transcript.provenance.get('identity_rebinding', {})
                require(child_transcript.transcript_id != parent_transcript.transcript_id
                    and binding.get('source_transcript_id') == parent_transcript.transcript_id
                    and binding.get('source_transcript_sha256') == digest(parent_transcript.model_dump(mode='json'))
                    and binding.get('fresh_provider_measurement') is False,
                    'SCENE_RESTORE_CHILD_TRANSCRIPT_CUSTODY_INVALID')
            binding = child_analysis['analysis']['provenance'].get('identity_rebinding', {})
            require(binding.get('source_record_sha256') == parent_analysis['sha256']
                and binding.get('fresh_provider_measurement') is False,
                'SCENE_RESTORE_CHILD_ANALYSIS_CUSTODY_INVALID')
            require(document['media_analysis'] == original['media_analysis'], 'SCENE_RESTORE_RAW_ASR_CHANGED')
            children.append(child)
            verified_children.append({'project_id': child_id, 'document_sha256': digest(document),
                'timeline_sha256': state['sha256'], 'source_project_id': project_id,
                'parent_selection_sha256': digest(proof), 'transcript_sha256': digest(child_transcript.model_dump(mode='json'))
                    if child_transcript else None, 'word_intervals_and_confidence_unchanged': True,
                'approval_transferred': False, 'fresh_provider_measurement': False})
        verified_batches.append({'request_key': batch['request_key'], 'batch_sha256': digest(batch),
            'source_document_sha256': batch['source_document_sha256'], 'generated_count': batch['generated_count']})
    require(verified_batches, 'SCENE_RESTORE_REVIEWED_SHORT_BATCH_MISSING')
    entries = {row['path']: row for row in manifest['entries']}
    media = verify_media(store, [parent, *children], entries)
    require(database_evidence(root) == before, 'SCENE_RESTORE_VERIFICATION_WROTE_SOURCE_ROWS')
    return {'project_id': project_id, 'workspace_id': workspace, 'project_document_sha256': digest(parent['document']),
        'assessment_page_sha256': digest(page), 'assessment_records': [
            {'assessment_id': item['assessment']['assessment_id'], 'sha256': item['sha256'], 'current': item['current']}
            for item in page['items']], 'short_batches': verified_batches, 'children': verified_children,
        'media': media, 'database_source_rows': before, 'source_rows_unchanged': True,
        'parent_approval_present': parent['approval'] is not None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--project-id', required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    require(re.fullmatch(r'[a-f0-9]{32}', args.project_id), 'SCENE_RESTORE_PROJECT_ID_INVALID')
    require(re.fullmatch(r'wsp_[A-Za-z0-9_-]{1,120}', args.workspace), 'SCENE_RESTORE_WORKSPACE_INVALID')
    require(re.fullmatch(r'[a-fA-F0-9]{64}', args.sha), 'SCENE_RESTORE_TRUSTED_SHA_INVALID')
    backup = guard(Path(args.backup), exists=True); expected_sha = args.sha.lower()
    require(file_sha(backup) == expected_sha, 'SCENE_RESTORE_TRUSTED_SHA_MISMATCH')
    output = guard(Path(args.output)); require(not output.exists(), 'SCENE_RESTORE_OUTPUT_ALREADY_EXISTS')
    with zipfile.ZipFile(backup, 'r') as archive:
        manifest = validate_archive(archive)
    with tempfile.TemporaryDirectory(prefix='vf-scene-cold-') as temporary:
        root = Path(temporary) / 'restore'
        receipt = restore_backup(backup, root, expected_sha256=expected_sha)
        for row in manifest['entries']:
            name = row['path']; relative = name[len('state/'):] if name.startswith('state/') else (
                '_recovery/' + receipt['manifest_sha256'] + '/' + name)
            path = io_path(root / relative)
            require(path.is_file() and path.stat().st_size == row['bytes'] and file_sha(path) == row['sha256'],
                'SCENE_RESTORE_ARCHIVE_ENTRY_CHANGED')
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('No network in restore verification')), \
                patch('socket.create_connection', side_effect=AssertionError('No network in restore verification')), \
                patch('subprocess.Popen', side_effect=AssertionError('No worker/model in restore verification')):
            evidence = verify_state(root, args.project_id, args.workspace, manifest)
    require(file_sha(backup) == expected_sha, 'SCENE_RESTORE_INPUT_BACKUP_CHANGED')
    report = {'schema_version': 'north-star-scene-assessment-cold-restore.v1',
        'backup_sha256': expected_sha, 'manifest_sha256': receipt['manifest_sha256'],
        'archive_entries_verified': receipt['verified_entries'], 'fresh_owned_root_restore': True,
        'owned_temporary_root_cleaned': True, 'services_started': False, 'workers_started': False,
        'provider_calls': 0, 'local_model_inferences': 0, 'paid_operations': 0,
        'owner_uat_accepted': False, 'full_mode_a_b_accepted': False, 'production_deployed': False,
        'evidence': evidence}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2); handle.write('\n')
    print(json.dumps({'report': str(output), 'report_sha256': file_sha(output),
        'assessments': len(evidence['assessment_records']), 'children': len(evidence['children']),
        'fresh_restore_verified': True, 'provider_calls': 0}))


if __name__ == '__main__':
    main()
