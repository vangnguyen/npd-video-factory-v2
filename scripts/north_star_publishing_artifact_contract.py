"""Real portrait MP4/admission/QC; explicit fixture approval, no provider publish."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/tests'))
from test_publishing_dispatch import fixture_stack
from app.db import AssetORM
from app.object_storage import LocalObjectStorageProvider
from app.publishing_artifact import ArtifactAdmissionError, BLOCK, PublishingArtifactGuard


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


async def run(root, output, ffmpeg, ffprobe):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    source = root / 'explicit-synthetic-portrait.mp4'
    subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=1080x1920:rate=30:duration=3',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=3', '-c:v', 'libx264', '-preset', 'ultrafast',
        '-crf', '28', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-shortest', '-movflags', '+faststart', str(source)],
        check=True, timeout=90, capture_output=True)
    original_sha = sha(source); raw = source.read_bytes()
    generator = fixture_stack.__wrapped__(root / 'project-fixture'); fixture = await anext(generator)
    try:
        parent = fixture['publication']; storage = LocalObjectStorageProvider(root / 'objects'); await storage.ensure_ready()
        key = f'workspaces/{fixture["workspace"]}/projects/{parent.project_id}/publish-source/explicit-synthetic.mp4'
        stored = await storage.put_file(object_key=key, path=source, content_type='video/mp4')
        async with fixture['stack'].repository.session_factory() as session:
            async with session.begin():
                asset = await session.get(AssetORM, parent.output_asset_id)
                asset.object_key = key; asset.storage_provider = stored.storage_provider
                asset.size_bytes = stored.size_bytes; asset.checksum_sha256 = stored.checksum_sha256
        grant = await fixture['approve'](expected_artifact_sha256=original_sha)
        state = await fixture['journal'].prepare(fixture['workspace'], parent.publication_id, grant['publish_approval_id'])
        work = root / 'private-work'; work.mkdir()
        guard = PublishingArtifactGuard(fixture['journal'], storage, work, ffmpeg_path=str(ffmpeg), ffprobe_path=str(ffprobe))
        transmitted = bytearray(); ranges = []
        async with guard.open(fixture['workspace'], parent.publication_id) as artifact:
            assert artifact.qc_report['status'] == 'passed' and artifact.qc_report['width'] == 1080 and artifact.qc_report['height'] == 1920
            assert artifact.qc_report['video_codec'] == 'h264' and artifact.qc_report['audio_codec'] == 'aac'
            write(output / 'media-qc.json', artifact.qc_report)
            # No network call: exact intended ranges are assembled in a local buffer.
            for offset in range(0, artifact.size_bytes, BLOCK):
                content = artifact.read(offset, min(BLOCK, artifact.size_bytes - offset)); transmitted.extend(content)
                ranges.append({'offset': offset, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
            assert bytes(transmitted) == raw
            assert artifact.read(13, BLOCK + 7) == raw[13:BLOCK + 20]
        assert list(work.iterdir()) == [] and sha(source) == original_sha
        write(output / 'range-admission.json', {'status': 'PASS', 'exact_source_bytes_equal_verified_ranges': True,
            'unaligned_range_verified': True, 'ranges': ranges, 'local_buffer_only': True, 'actual_upload_requests': 0})
        # A scoped stored object is corrupted only in this disposable fixture.
        stored_path = storage.root / Path(key)
        with stored_path.open('r+b') as handle: handle.seek(32); handle.write(b'\xff')
        try:
            async with guard.open(fixture['workspace'], parent.publication_id): pass
        except ArtifactAdmissionError as error: assert error.code == 'PUBLISH_ARTIFACT_CHECKSUM_MISMATCH'
        else: raise AssertionError('Changed stored bytes were admitted')
        assert list(work.iterdir()) == [] and sha(source) == original_sha
        write(output / 'changed-storage.json', {'status': 'PASS', 'same_size_corruption': 'refused_before_qc_and_wire',
            'original_synthetic_source_unchanged': True, 'private_work_cleaned': True, 'accepted_or_live_artifact_modified': False})
        write(output / 'source.json', {'path': str(source), 'sha256': original_sha, 'bytes': len(raw), 'synthetic_test_pattern_and_sine_only': True,
            'fixture_production_approval': True, 'fixture_publish_consent': True, 'real_voice_or_video_factory_final_render': False,
            'binding_sha256': state['binding_sha256']})
    finally: await generator.aclose()
    write(output / 'receipt.json', {'schema': 'north-star-publishing-artifact-contract-v1', 'status': 'PASS',
        'actual_portrait_mp4_and_full_qc': True, 'actual_range_checksum_verification': True, 'fixture_identity_approval_project_only': True,
        'actual_external_requests': 0, 'secrets_read': 0, 'paid_operations': 0, 'live_adapter_activated': False,
        'publishing_ready': False, 'owner_uat_accepted': False, 'production_deployed': False,
        'exports_sha256': {path.name: sha(path) for path in sorted(output.glob('*.json'))}})
    print(json.dumps({'status': 'PASS', 'exports': 5, 'source_bytes': len(raw), 'ranges': len(ranges), 'actual_provider_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True); parser.add_argument('--ffmpeg', type=Path, required=True)
    parser.add_argument('--ffprobe', type=Path, required=True); args = parser.parse_args()
    asyncio.run(run(args.fixture_root.resolve(), args.output_root.resolve(), args.ffmpeg.resolve(), args.ffprobe.resolve()))
