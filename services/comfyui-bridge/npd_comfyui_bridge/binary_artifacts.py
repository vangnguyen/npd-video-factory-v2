"""Immutable scoped media registration with actual bounded FFmpeg decoding.

The bridge owns this directory; no Video Factory/Hub database is shared. Rights
remain unknown and production eligibility false even for successfully decoded
media. Caller-provided MIME/extensions alone never establish media validity.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid
from pydantic import Field, StrictInt
from typing import Annotated, Literal

from .job_store import linked
from .http_transport import IMAGE_LIMIT, MEDIA_LIMIT
from .model_base import StrictModel


class ArtifactError(RuntimeError):
    pass


class ArtifactProvenance(StrictModel):
    provider: Literal['comfyui'] = 'comfyui'
    model: str = Field(min_length=1, max_length=200)
    workflow_id: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{2,80}$')
    workflow_version: str = Field(min_length=1, max_length=40)
    graph_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    server_source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    inputs_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    prompt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    seed: StrictInt = Field(ge=0)
    remote_prompt_id: str = Field(pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
    source_reference_sha256: list[Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]] = Field(default_factory=list, max_length=11)
    adapter_elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    estimated_cost_vnd: None = None
    actual_cost_vnd: None = None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def scope(workspace_id, job_id):
    if (not isinstance(workspace_id, str) or not 1 <= len(workspace_id) <= 200
            or any(c.isspace() or ord(c) < 33 for c in workspace_id)
            or not isinstance(job_id, str) or not re.fullmatch(r'cui_[a-zA-Z0-9_-]{1,80}', job_id)):
        raise ArtifactError('ARTIFACT_SCOPE_INVALID')
    return digest(workspace_id), job_id


def checked(path, root):
    if linked(path) or root.resolve() not in path.resolve().parents:
        raise ArtifactError('ARTIFACT_PATH_INVALID')
    return path


class FFmpegMediaValidator:
    def __init__(self, *, ffmpeg=None, ffprobe=None, timeout_seconds=30):
        if not 1 <= timeout_seconds <= 120:
            raise ValueError('MEDIA_DECODE_TIMEOUT_INVALID')
        self.ffmpeg, self.ffprobe = Path(ffmpeg) if ffmpeg else None, Path(ffprobe) if ffprobe else None
        self.timeout_seconds = timeout_seconds

    @property
    def configured(self):
        return bool(self.ffmpeg and self.ffprobe and all(p.is_absolute() and p.is_file() and not linked(p)
            for p in (self.ffmpeg, self.ffprobe)))

    async def _run(self, executable, args):
        process = None
        readers = []
        async def bounded_read(stream):
            chunks, size = [], 0
            while chunk := await stream.read(4096):
                size += len(chunk)
                if size > 65536:
                    raise ArtifactError('MEDIA_DECODE_OUTPUT_LIMIT')
                chunks.append(chunk)
            return b''.join(chunks)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                process = await asyncio.create_subprocess_exec(str(executable), *args,
                    stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                readers = [asyncio.create_task(bounded_read(process.stdout)), asyncio.create_task(bounded_read(process.stderr))]
                output, _ = await asyncio.gather(*readers)
                if await process.wait() != 0:
                    raise ArtifactError('MEDIA_DECODE_FAILED')
                return output
        except TimeoutError:
            raise ArtifactError('MEDIA_DECODE_TIMEOUT') from None
        except OSError:
            raise ArtifactError('MEDIA_DECODE_TOOL_FAILED') from None
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()
            for reader in readers:
                if not reader.done():
                    reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)

    async def validate(self, path, mime_type):
        if not self.configured:
            raise ArtifactError('MEDIA_DECODE_NOT_CONFIGURED')
        try:
            raw = await self._run(self.ffprobe, ['-v', 'error', '-protocol_whitelist', 'file,pipe',
                '-show_entries', 'stream=codec_type,codec_name,width,height,avg_frame_rate,duration:format=format_name,duration', '-of', 'json', str(path)])
            probe = json.loads(raw)
            streams = probe['streams']
            videos = [s for s in streams if s.get('codec_type') == 'video']
            if len(videos) != 1 or len(streams) > 4 or any(s.get('codec_type') not in {'video', 'audio'} for s in streams):
                raise ValueError()
            video = videos[0]
            width, height = int(video['width']), int(video['height'])
            if not 1 <= width <= 8192 or not 1 <= height <= 8192 or width * height > 16 * 1024 * 1024:
                raise ValueError()
            duration, fps = None, None
            if mime_type == 'video/mp4':
                if 'mp4' not in probe['format']['format_name'].split(','):
                    raise ValueError()
                duration = float(probe['format']['duration'])
                fps = float(Fraction(video['avg_frame_rate']))
                if not math.isfinite(duration) or not 0 < duration <= 600 or not 1 <= fps <= 120:
                    raise ValueError()
            elif mime_type == 'image/png':
                if video['codec_name'] != 'png' or len(streams) != 1:
                    raise ValueError()
            elif mime_type == 'image/jpeg':
                if video['codec_name'] != 'mjpeg' or len(streams) != 1:
                    raise ValueError()
            else:
                raise ValueError()
        except (ValueError, KeyError, TypeError, OverflowError, ZeroDivisionError):
            raise ArtifactError('MEDIA_PROBE_INVALID') from None
        decoded = await self._run(self.ffmpeg, ['-hide_banner', '-nostdin', '-v', 'error', '-xerror',
            '-err_detect', 'explode', '-protocol_whitelist', 'file,pipe', '-threads', '2', '-i', str(path),
            '-map', '0:v:0', '-map', '0:a?', '-sn', '-dn', '-fps_mode', 'passthrough', '-threads', '2',
            '-progress', 'pipe:1', '-f', 'null', '-'])
        frames = re.findall(rb'(?:^|\n)frame=(\d+)\r?(?:\n|$)', decoded)
        if not frames or int(frames[-1]) < 1 or mime_type.startswith('image/') and int(frames[-1]) != 1:
            raise ArtifactError('MEDIA_DECODE_FRAMES_INVALID')
        return {'width': width, 'height': height, 'duration_seconds': duration, 'fps': fps,
            'video_codec': video['codec_name'], 'audio_streams': len(streams) - 1,
            'decoded_video_frames': int(frames[-1]), 'full_decode_passed': True,
            'decoder': 'ffmpeg', 'qc_passed': False}


@dataclass(frozen=True)
class RegisteredArtifact:
    document: dict
    path: Path


class BinaryArtifactStore:
    def __init__(self, root: Path, *, validator: FFmpegMediaValidator):
        self.root = Path(root)
        if linked(self.root):
            raise ArtifactError('ARTIFACT_PATH_INVALID')
        self.root = self.root.resolve()
        if not isinstance(validator, FFmpegMediaValidator):
            raise ArtifactError('ARTIFACT_VALIDATOR_INVALID')
        self.validator = validator
        self._lock = asyncio.Lock()

    def _job_root(self, workspace_id, job_id):
        workspace_hash, job = scope(workspace_id, job_id)
        return checked(self.root / workspace_hash / job, self.root)

    def read(self, *, workspace_id, job_id, artifact_id):
        if not isinstance(artifact_id, str) or not re.fullmatch(r'[a-f0-9]{64}', artifact_id):
            raise ArtifactError('ARTIFACT_ID_INVALID')
        directory = checked(self._job_root(workspace_id, job_id) / artifact_id, self.root)
        manifest = checked(directory / 'artifact.json', self.root)
        if not manifest.is_file():
            raise ArtifactError('ARTIFACT_NOT_FOUND')
        try:
            if manifest.stat().st_size > 65536:
                raise ValueError()
            wrapper = json.loads(manifest.read_bytes())
            document = wrapper['document']
            if (set(wrapper) != {'schema', 'document', 'sha256'} or wrapper['schema'] != 'vf-binary-artifact-v1'
                    or digest(document) != wrapper['sha256'] or document['workspace_id'] != workspace_id
                    or document['job_id'] != job_id or document['artifact_id'] != artifact_id
                    or document['rights_status'] != 'unknown' or document['production_eligible'] is not False
                    or document['media']['full_decode_passed'] is not True):
                raise ValueError()
            ArtifactProvenance.model_validate(document['provenance'])
            expected_extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'video/mp4': 'mp4'}[document['mime_type']]
            if document['filename'] != 'media.' + expected_extension:
                raise ValueError()
            path = checked(directory / document['filename'], self.root)
            limit = MEDIA_LIMIT if document['mime_type'] == 'video/mp4' else IMAGE_LIMIT
            if not path.is_file() or path.stat().st_size != document['size_bytes'] or not 1 <= path.stat().st_size <= limit:
                raise ValueError()
            content_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if content_sha != document['checksum_sha256'] or digest([workspace_id, job_id, content_sha]) != artifact_id:
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ArtifactError('ARTIFACT_INTEGRITY_INVALID') from None
        return RegisteredArtifact(document=document, path=path)

    async def register(self, *, workspace_id, job_id, content, mime_type, provenance, fixture):
        if not isinstance(provenance, ArtifactProvenance):
            raise ArtifactError('ARTIFACT_PROVENANCE_INVALID')
        provenance = provenance.model_dump(mode='json')
        extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'video/mp4': 'mp4'}.get(mime_type)
        limit = MEDIA_LIMIT if mime_type == 'video/mp4' else IMAGE_LIMIT
        if extension is None or not isinstance(content, bytes) or not 1 <= len(content) <= limit or type(fixture) is not bool:
            raise ArtifactError('ARTIFACT_CONTENT_INVALID')
        magic = (content.startswith(b'\x89PNG\r\n\x1a\n') if extension == 'png' else
            content.startswith(b'\xff\xd8\xff') if extension == 'jpg' else len(content) >= 12 and content[4:8] == b'ftyp')
        if not magic or not isinstance(provenance, dict) or len(json.dumps(provenance, allow_nan=False).encode()) > 32768:
            raise ArtifactError('ARTIFACT_CONTENT_INVALID')
        content_sha = hashlib.sha256(content).hexdigest()
        artifact_id = digest([workspace_id, job_id, content_sha])
        job_root = self._job_root(workspace_id, job_id)
        directory = checked(job_root / artifact_id, self.root)
        async with self._lock:
            if directory.exists():
                existing = self.read(workspace_id=workspace_id, job_id=job_id, artifact_id=artifact_id)
                if existing.document['provenance'] != provenance or existing.document['fixture'] != fixture:
                    raise ArtifactError('ARTIFACT_REPLAY_CONFLICT')
                return existing
            job_root.mkdir(parents=True, exist_ok=True)
            temporary = checked(job_root / ('.partial-' + uuid.uuid4().hex), self.root)
            temporary.mkdir(exist_ok=False)
            media_path, manifest_path = temporary / ('media.' + extension), temporary / 'artifact.json'
            try:
                with media_path.open('xb') as handle:
                    handle.write(content); handle.flush(); os.fsync(handle.fileno())
                media = await self.validator.validate(media_path, mime_type)
                document = {'artifact_id': artifact_id, 'workspace_id': workspace_id, 'job_id': job_id,
                    'filename': media_path.name, 'mime_type': mime_type, 'checksum_sha256': content_sha,
                    'size_bytes': len(content), 'media': media, 'provenance': provenance, 'fixture': fixture,
                    'rights_status': 'unknown', 'production_eligible': False,
                    'created_at': datetime.now(timezone.utc).isoformat()}
                raw = json.dumps({'schema': 'vf-binary-artifact-v1', 'document': document, 'sha256': digest(document)},
                    sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
                if len(raw) > 65536:
                    raise ArtifactError('ARTIFACT_METADATA_TOO_LARGE')
                with manifest_path.open('xb') as handle:
                    handle.write(raw); handle.flush(); os.fsync(handle.fileno())
                if linked(directory) or directory.exists():
                    raise ArtifactError('ARTIFACT_COMMIT_CONFLICT')
                temporary.rename(directory)
                return self.read(workspace_id=workspace_id, job_id=job_id, artifact_id=artifact_id)
            finally:
                # Only these two freshly owned files can be removed; no recursion.
                if temporary.exists():
                    for path in (media_path, manifest_path):
                        if path.is_file() and not linked(path):
                            path.unlink()
                    temporary.rmdir()
