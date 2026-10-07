"""Consume only authenticated job-bound registered bridge media, never URLs."""
import asyncio
import hashlib
import json
import math
import re


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


async def bounded_response(client, path, *, limit, timeout_seconds):
    async with asyncio.timeout(timeout_seconds):
        async with client.stream('GET', path) as response:
            if response.status_code != 200:
                raise ValueError('COMFYUI_ARTIFACT_HTTP_FAILED')
            declared = response.headers.get('Content-Length')
            if declared and (not declared.isdigit() or int(declared) > limit):
                raise ValueError('COMFYUI_ARTIFACT_TOO_LARGE')
            size, chunks = 0, []
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ValueError('COMFYUI_ARTIFACT_TOO_LARGE')
                chunks.append(chunk)
            return b''.join(chunks), response.headers.get('Content-Type', '').split(';')[0].lower(), response.headers.get('X-VF-Content-SHA256')


async def registered_binary(client, *, job, workspace_id, workflow_id, modality, inputs, timeout_seconds):
    result = job.get('result') or {}
    reference = result.get('artifact_reference', '')
    if not isinstance(reference, str) or not re.fullmatch(r'vf-artifact://[a-f0-9]{64}', reference):
        raise ValueError('COMFYUI_ARTIFACT_REFERENCE_INVALID')
    try:
        if (checksum(result) != job.get('result_metadata_sha256') or result.get('workflow_id') != workflow_id
                or result.get('workflow_version') != job.get('workflow_version') or type(result.get('fixture')) is not bool
                or not isinstance(job.get('workflow_version'), str) or not 1 <= len(job['workflow_version']) <= 40
                or not isinstance(job.get('job_id'), str) or not re.fullmatch(r'cui_[A-Za-z0-9_-]{1,80}', job['job_id'])):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('COMFYUI_ARTIFACT_RESULT_INVALID') from None
    artifact_id = reference.removeprefix('vf-artifact://')
    path = f'/v1/jobs/{job["job_id"]}/artifacts/{artifact_id}'
    raw, mime, _ = await bounded_response(client, path + '/metadata', limit=65536, timeout_seconds=timeout_seconds)
    try:
        metadata = json.loads(raw)
        media, provenance = metadata['media'], metadata['provenance']
        expected_mime = metadata['mime_type']
        expected_size = metadata['size_bytes']
        if (mime != 'application/json' or metadata['workspace_id'] != workspace_id
                or metadata['job_id'] != job['job_id'] or metadata['artifact_id'] != artifact_id
                or metadata['checksum_sha256'] != result['checksum_sha256']
                or provenance['workflow_id'] != workflow_id or provenance['workflow_version'] != job['workflow_version']
                or provenance['inputs_sha256'] != checksum(inputs)
                or provenance['prompt_sha256'] != hashlib.sha256(inputs['prompt'].encode()).hexdigest()
                or type(provenance['seed']) is not int or provenance['seed'] != inputs['seed']
                or provenance['estimated_cost_vnd'] is not None or provenance['actual_cost_vnd'] is not None
                or metadata['fixture'] != result['fixture'] or metadata['rights_status'] != 'unknown'
                or type(metadata['fixture']) is not bool
                or metadata['production_eligible'] is not False or media['full_decode_passed'] is not True
                or type(media['width']) is not int or type(media['height']) is not int
                or not 1 <= media['width'] <= 8192 or not 1 <= media['height'] <= 8192
                or media['width'] * media['height'] > 16 * 1024 * 1024
                or type(media['decoded_video_frames']) is not int or not 1 <= media['decoded_video_frames'] <= 72000
                or type(media['audio_streams']) is not int or not 0 <= media['audio_streams'] <= 3
                or type(expected_size) is not int or expected_size <= 0
                or expected_mime not in ({'image/png', 'image/jpeg'} if modality == 'image' else {'video/mp4'})):
            raise ValueError()
        if modality == 'video':
            duration, fps = media['duration_seconds'], media['fps']
            if (type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 600
                    or type(fps) not in (int, float) or not math.isfinite(fps) or not 1 <= fps <= 120):
                raise ValueError()
        elif (media['duration_seconds'] is not None or media['fps'] is not None or media['decoded_video_frames'] != 1
                or media['audio_streams'] != 0 or media['video_codec'] != ('png' if expected_mime == 'image/png' else 'mjpeg')):
            raise ValueError()
    except (ValueError, TypeError, KeyError):
        raise ValueError('COMFYUI_ARTIFACT_METADATA_INVALID') from None
    limit = 250 * 1024 * 1024 if modality == 'video' else 32 * 1024 * 1024
    if expected_size > limit:
        raise ValueError('COMFYUI_ARTIFACT_TOO_LARGE')
    content, returned_mime, header_sha = await bounded_response(client, path, limit=limit, timeout_seconds=timeout_seconds)
    content_sha = hashlib.sha256(content).hexdigest()
    magic = (content.startswith(b'\x89PNG\r\n\x1a\n') if expected_mime == 'image/png' else
             content.startswith(b'\xff\xd8\xff') if expected_mime == 'image/jpeg' else len(content) >= 12 and content[4:8] == b'ftyp')
    if (not magic or len(content) != expected_size or returned_mime != expected_mime
            or content_sha != metadata['checksum_sha256'] or header_sha != content_sha
            or checksum([workspace_id, job['job_id'], content_sha]) != artifact_id):
        raise ValueError('COMFYUI_ARTIFACT_BYTES_INVALID')
    return content, metadata
