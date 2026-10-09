"""Bounded actual Native PNG input for the existing structured Vision adapter.

This primitive makes no provider call, grants no paid authority and does not
change the original CPU observations, canonical timeline or fixture journals.
"""
import copy
import hashlib
import io
import math
from pathlib import Path

from .contracts import WorkflowError, digest
from .media_frame_analysis import checked_path, frame_path, validate, FRAME_COUNT
from app.auto_edit_models import MediaMetadata, SceneRead
from app.openai_vision_provider import ExtractedVisionFrame


class NativeEvidenceFrameExtractor:
    def __init__(self, root, config, project_id, source):
        self.root = Path(root).absolute()
        self.config = config
        self.project_id = project_id
        self.source = copy.deepcopy(source)
        self._root = self.root
        self._data_root = config.data_root.absolute()
        self._project_id = project_id
        self._fingerprint = digest(self.source)
        self.max_image_bytes = 4 * 1024 * 1024
        self.max_dimension_pixels = 2048
        self._check()
        self.max_frames = len(self.source['source_observation']['observation']['frames'])
        self._max_frames = self.max_frames

    def _check(self):
        try:
            s = self.source
            if (self.root != self._root or self.config.data_root.absolute() != self._data_root
                or self.root != self._data_root or self.project_id != self._project_id
                or digest(s) != self._fingerprint
                or self.max_image_bytes != 4 * 1024 * 1024 or self.max_dimension_pixels != 2048
                or set(s) != {'asset', 'source_observation', 'source_media', 'scenes', 'transcript_ref'}):
                raise ValueError()
            asset = s['asset']
            metadata = MediaMetadata.model_validate(s['source_media'])
            if metadata.model_dump(mode='json') != s['source_media']:
                raise ValueError()
            if asset['kind'] not in ('image', 'video') or metadata.media_kind != asset['kind']:
                raise ValueError()
            for name in ('width', 'height', 'duration_seconds', 'fps', 'video_codec', 'audio_codec'):
                if getattr(metadata, name) != asset.get(name):
                    raise ValueError()
            if not metadata.width or not metadata.height:
                raise ValueError()
            observation = validate(s['source_observation'], self.project_id, asset)
            frames = observation['frames']
            if (not 1 <= len(frames) <= FRAME_COUNT or getattr(self, 'max_frames', len(frames)) != len(frames)
                or getattr(self, '_max_frames', len(frames)) != len(frames)
                or any(not math.isfinite(f['timestamp_seconds']) or f['width'] > self.max_dimension_pixels
                    or f['height'] > self.max_dimension_pixels for f in frames)):
                raise ValueError()
            if asset['kind'] == 'image' and (len(frames) != 1 or frames[0]['timestamp_seconds'] != 0):
                raise ValueError()
            if len({(f['width'], f['height']) for f in frames}) != 1:
                raise ValueError()
            for frame in frames:
                mounted = frame_path(self.root, frame)
                if not 1 <= mounted.stat().st_size <= self.max_image_bytes or mounted.stat().st_nlink != 1:
                    raise ValueError()
            scenes = [SceneRead.model_validate(scene) for scene in s['scenes']]
            if any(scene.model_dump(mode='json') != raw for scene, raw in zip(scenes, s['scenes'])):
                raise ValueError()
            transcript = s['transcript_ref']
            if transcript is not None:
                if (set(transcript) != {'transcript_id', 'version', 'sha256'}
                    or not isinstance(transcript['transcript_id'], str) or not transcript['transcript_id']
                    or type(transcript['version']) is not int or transcript['version'] < 1
                    or not isinstance(transcript['sha256'], str) or len(transcript['sha256']) != 64
                    or any(c not in 'abcdef0123456789' for c in transcript['sha256'])):
                    raise ValueError()
            path = checked_path(self.config, asset)
            if path.stat().st_nlink != 1:
                raise ValueError()
            with path.open('rb') as handle:
                header = handle.read(16)
            content_type = ('image/png' if header.startswith(b'\x89PNG\r\n\x1a\n')
                else 'image/jpeg' if header.startswith(b'\xff\xd8\xff')
                else ('video/quicktime' if header[8:12] == b'qt  ' else 'video/mp4')
                    if header[4:8] == b'ftyp' else None)
            if content_type != metadata.detected_content_type:
                raise ValueError()
            return path, metadata, observation
        except Exception:
            raise WorkflowError('NATIVE_VISION_INPUT_BINDING_INVALID') from None

    def input_metadata(self):
        """Actual sampled PNG dimensions, explicitly distinct from raw source metadata."""
        _, _, observation = self._check()
        frame = observation['frames'][0]
        return MediaMetadata(media_kind='image', detected_content_type='image/png', format_name='png',
            width=frame['width'], height=frame['height'])

    def binding(self):
        _, metadata, observation = self._check()
        return {'schema_version': 'native-vision-frame-input-v1', 'project_id': self.project_id,
            'asset_id': self.source['asset']['id'], 'source_sha256': self.source['asset']['sha256'],
            'source_binding_sha256': self._fingerprint,
            'source_observation_id': observation['observation_id'],
            'source_observation_sha256': self.source['source_observation']['sha256'],
            'original_source_metadata': metadata.model_dump(mode='json'),
            'vision_input_metadata': self.input_metadata().model_dump(mode='json'),
            'source_frame_evidence': copy.deepcopy(observation['frames']),
            'scenes_sha256': digest(self.source['scenes']),
            'transcript_ref': copy.deepcopy(self.source['transcript_ref']),
            'timestamp_basis': 'requested_ffmpeg_source_seek; decoded_pts_unavailable',
            'decoded_pts_seconds': None, 'continuous_tracking_performed': False,
            'frozen_video_detection_performed': False, 'semantic_inference_performed': False,
            'external_provider_calls': 0, 'paid_operations': 0,
            'source_media_mutated': False, 'canonical_timeline_mutated': False}

    async def extract(self, path, *, metadata, scenes, asset_id, sample_interval_seconds):
        checked, original, observation = self._check()
        if (Path(path).absolute() != checked.absolute() or asset_id != self.source['asset']['id']
            or metadata.model_dump(mode='json') not in (original.model_dump(mode='json'), self.input_metadata().model_dump(mode='json'))
            or [scene.model_dump(mode='json') for scene in scenes] != self.source['scenes']
            or type(sample_interval_seconds) not in (int, float) or not math.isfinite(sample_interval_seconds)
            or sample_interval_seconds <= 0):
            raise WorkflowError('NATIVE_VISION_INPUT_REQUEST_INVALID')
        from PIL import Image
        output = []
        for frame in observation['frames']:
            try:
                frame_file = frame_path(self.root, frame)
                if not 1 <= frame_file.stat().st_size <= self.max_image_bytes or frame_file.stat().st_nlink != 1:
                    raise ValueError()
                with frame_file.open('rb') as handle:
                    payload = handle.read(self.max_image_bytes + 1)
                if (len(payload) > self.max_image_bytes or not payload.startswith(b'\x89PNG\r\n\x1a\n')
                    or hashlib.sha256(payload).hexdigest() != frame['sha256']):
                    raise ValueError()
                with Image.open(io.BytesIO(payload)) as image:
                    if image.format != 'PNG' or image.size != (frame['width'], frame['height']) or getattr(image, 'n_frames', 1) != 1:
                        raise ValueError()
                    image.load()
                    rgb = image.convert('RGB')
                    pixels = f'{image.width}x{image.height}:'.encode() + rgb.tobytes()
                    if hashlib.sha256(pixels).hexdigest() != frame['decoded_pixels_sha256']:
                        raise ValueError()
                if frame_path(self.root, frame) != frame_file:
                    raise ValueError()
                output.append(ExtractedVisionFrame(timestamp_seconds=frame['timestamp_seconds'],
                    evidence_frame_reference=frame['reference'], content_type='image/png',
                    payload=payload, sha256=frame['sha256']))
            except Exception:
                raise WorkflowError('NATIVE_VISION_FRAME_INPUT_INVALID') from None
        self._check()
        return tuple(output)
