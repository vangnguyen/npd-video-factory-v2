"""Bounded decoded final-render pixels, distinct from semantic Vision predictions."""
import io
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Literal

from PIL import Image
from pydantic import Field, StrictInt, model_validator
from app.models import StrictModel
from app.media_frame_facts import PixelFacts, pixel_facts
from .contracts import WorkflowError, digest, file_sha
from .hardening import durable_json
from .media_frame_analysis import linked

SCHEMA = 'native-render-frame-qc-v1'
MAX_FRAMES = 8
MAX_PNG_BYTES = 4 * 1024 * 1024
FOLDER = 'render-frame-qc'
REPORT = 'render-frame-qc.json'


class RenderFrame(StrictModel):
    frame_id: str = Field(pattern=r'^rqf_[a-f0-9]{24}$')
    evidence_frame_reference: str = Field(pattern=r'^render-frame-qc/[0-7]\.png$')
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    decoded_pixels_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    decoded_render_pts: StrictInt
    decoded_render_pts_seconds: float = Field(allow_inf_nan=False)
    timestamp_seconds: float = Field(ge=0, allow_inf_nan=False)
    width: StrictInt = Field(ge=3, le=960)
    height: StrictInt = Field(ge=3, le=960)
    size_bytes: StrictInt = Field(ge=1, le=MAX_PNG_BYTES)
    pixel_facts: PixelFacts


class RenderObservation(StrictModel):
    schema_version: Literal['native-render-frame-qc-v1'] = SCHEMA
    rendered_video_reference: Literal['final.mp4'] = 'final.mp4'
    rendered_video_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    document_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    render_manifest_reference: Literal['render-manifest.json', 'timeline-render.json']
    render_manifest_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    render_stream_time_base: str = Field(pattern=r'^[1-9][0-9]*/[1-9][0-9]*$')
    render_stream_start_seconds: float = Field(allow_inf_nan=False)
    render_duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    sampling_interval_seconds: float = Field(gt=0, allow_inf_nan=False)
    provider: Literal['local_ffmpeg_pillow_pixels'] = 'local_ffmpeg_pillow_pixels'
    model: Literal['pixel-quality-facts-v1'] = 'pixel-quality-facts-v1'
    timestamp_basis: Literal['decoded_render_pts_before_scaling_with_copyts'] = 'decoded_render_pts_before_scaling_with_copyts'
    frames: list[RenderFrame] = Field(min_length=1, max_length=MAX_FRAMES)
    confidence: None = None
    semantic_provider_status: Literal['NOT_REQUESTED'] = 'NOT_REQUESTED'
    semantic_inference_performed: Literal[False] = False
    full_video_tracking_performed: Literal[False] = False
    external_provider_calls: Literal[0] = 0
    paid_operations: Literal[0] = 0
    publishing_authorized: Literal[False] = False
    owner_uat_accepted: Literal[False] = False

    @model_validator(mode='after')
    def ordered_samples(self):
        num, den = map(int, self.render_stream_time_base.split('/'))
        if abs(self.sampling_interval_seconds-max(1/30,self.render_duration_seconds/MAX_FRAMES))>.000001:
            raise ValueError('Fixed bounded sampling policy required')
        last = -1.
        for index, frame in enumerate(self.frames):
            pts_seconds = frame.decoded_render_pts * num / den
            relative = pts_seconds - self.render_stream_start_seconds
            if (frame.evidence_frame_reference != f'{FOLDER}/{index}.png'
                    or frame.frame_id != 'rqf_' + digest([self.rendered_video_sha256, index, frame.decoded_render_pts, frame.sha256])[:24]
                    or abs(frame.decoded_render_pts_seconds - pts_seconds) > .00001
                    or abs(frame.timestamp_seconds - relative) > .00001
                    or frame.timestamp_seconds <= last
                    or frame.timestamp_seconds >= self.render_duration_seconds + .001):
                raise ValueError('Exact ordered decoded final-render samples required')
            last = frame.timestamp_seconds
        return self


def checked(directory, name):
    directory = Path(directory).absolute()
    path = directory / name
    if (Path(name).is_absolute() or directory.resolve() not in path.resolve().parents
            or linked(directory) or linked(path) or path.resolve().parent != (directory / Path(name).parent).resolve()
            or not path.is_file() or path.stat().st_nlink != 1):
        raise WorkflowError('RENDER_FRAME_QC_ARTIFACT_INVALID')
    return path


def image_evidence(path):
    if not 0 < path.stat().st_size <= MAX_PNG_BYTES:
        raise WorkflowError('RENDER_FRAME_QC_IMAGE_INVALID')
    raw = path.read_bytes()
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != 'PNG' or not 3 <= image.width <= 960 or not 3 <= image.height <= 960:
                raise ValueError()
            image.load()
            rgb = image.convert('RGB')
            # Keep the existing transparent pixel heuristic and null semantics.
            pixels = rgb.convert('L').resize((64, 64), Image.Resampling.BILINEAR).tobytes()
            import hashlib
            return {'sha256': hashlib.sha256(raw).hexdigest(), 'decoded_pixels_sha256': hashlib.sha256(rgb.tobytes()).hexdigest(),
                    'width': rgb.width, 'height': rgb.height, 'size_bytes': len(raw),
                    'pixel_facts': pixel_facts(pixels, 64, 64).model_dump(mode='json')}
    except (ValueError, OSError):
        raise WorkflowError('RENDER_FRAME_QC_IMAGE_INVALID') from None


def decoded_stamps(directory, time_base, count):
    log_file=checked(directory,'render-frame-qc.log')
    if log_file.stat().st_size>1024*1024:raise WorkflowError('RENDER_FRAME_QC_TIMESTAMPS_INVALID')
    log=log_file.read_text(encoding='utf-8',errors='replace')
    bases=re.findall(r'config in time_base: (\d+/\d+)',log)
    stamps=re.findall(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:\s*([-+0-9.eE]+)',log)
    num,den=map(int,time_base.split('/'))
    if not bases or any(v!=time_base for v in bases) or len(stamps)<count:
        raise WorkflowError('RENDER_FRAME_QC_TIMESTAMPS_INVALID')
    result=[]
    for index,(ordinal,raw_pts,shown_seconds) in enumerate(stamps[:count]):
        pts=int(raw_pts);seconds=pts*num/den
        if int(ordinal)!=index or not math.isclose(float(shown_seconds),seconds,rel_tol=1e-5,abs_tol=.001):
            raise WorkflowError('RENDER_FRAME_QC_TIMESTAMPS_INVALID')
        result.append(pts)
    return result


def validate(directory, record, *, document_sha256=None, physical=True, materialized_video_name='final.mp4'):
    """No provider/model/key needed to verify original render evidence on recovery."""
    try:
        if type(physical) is not bool or materialized_video_name not in {'final.mp4', 'preview.mp4'}:
            raise ValueError()
        if set(record) != {'observation', 'sha256'} or record['sha256'] != digest(record['observation']):
            raise ValueError()
        model = RenderObservation.model_validate(record['observation'])
        value = model.model_dump(mode='json')
        # Reject bool/int substitutions and forged semantic/authority constants.
        if digest(value) != digest(record['observation']) or document_sha256 is not None and model.document_sha256 != document_sha256:
            raise ValueError()
        if physical:
            # Narrated preview publishes the original final.mp4 bytes under
            # preview.mp4. Keep the original evidence immutable; verify exact
            # content at the explicit local materialization, never another path.
            if (file_sha(checked(directory, materialized_video_name)) != model.rendered_video_sha256
                    or file_sha(checked(directory, model.render_manifest_reference)) != model.render_manifest_sha256):
                raise WorkflowError('RENDER_FRAME_QC_INPUT_CHANGED')
            if decoded_stamps(directory,model.render_stream_time_base,len(model.frames))!=[f.decoded_render_pts for f in model.frames]:
                raise WorkflowError('RENDER_FRAME_QC_TIMESTAMPS_CHANGED')
            for frame in value['frames']:
                measured = image_evidence(checked(directory, frame['evidence_frame_reference']))
                if any(digest(measured[key]) != digest(frame[key]) for key in measured):
                    raise WorkflowError('RENDER_FRAME_QC_IMAGE_CHANGED')
        return value
    except WorkflowError:
        raise
    except (TypeError, ValueError, KeyError, OSError):
        raise WorkflowError('RENDER_FRAME_QC_RECORD_INVALID') from None


def build(config, directory, *, document_sha256, manifest_name):
    directory = Path(directory).absolute()
    if manifest_name not in {'render-manifest.json', 'timeline-render.json'}:
        raise WorkflowError('RENDER_FRAME_QC_INPUT_INVALID')
    video = checked(directory, 'final.mp4')
    manifest = checked(directory, manifest_name)
    source_sha, manifest_sha = file_sha(video), file_sha(manifest)
    try:
        probe = subprocess.run([str(config.ffmpeg_bin / 'ffprobe.exe'), '-v', 'error', '-show_streams', '-show_format',
            '-of', 'json', str(video)], capture_output=True, check=True, timeout=30)
        data = json.loads(probe.stdout)
        stream = next(v for v in data['streams'] if v['codec_type'] == 'video')
        duration = float(stream.get('duration') or data['format']['duration'])
        start = float(stream.get('start_time') or 0)
        time_base = stream['time_base']
        num, den = map(int, time_base.split('/'))
        if not math.isfinite(duration) or not 0 < duration <= 3600 or not math.isfinite(start) or num <= 0 or den <= 0:
            raise ValueError()
        interval = max(1 / 30, duration / MAX_FRAMES)
        folder = directory / FOLDER
        if linked(folder) or folder.exists() or (directory / REPORT).exists():
            raise WorkflowError('RENDER_FRAME_QC_ALREADY_EXISTS')
        folder.mkdir()
        # showinfo BEFORE scale retains decoded input PTS/timebase. No fps or
        # setpts filter, input seek, timestamp reset or duplicate output frames.
        filters = f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{interval:.12f})',showinfo,scale=w=960:h=960:force_original_aspect_ratio=decrease"
        with (directory / 'render-frame-qc.log').open('xb') as log:
            result = subprocess.run([str(config.ffmpeg_bin / 'ffmpeg.exe'), '-hide_banner', '-nostdin', '-n', '-v', 'info',
                '-copyts', '-i', str(video), '-map', '0:v:0', '-an', '-vf', filters, '-frames:v', str(MAX_FRAMES),
                '-fps_mode', 'passthrough', '-start_number', '0', str(folder / '%01d.png')],
                stdout=subprocess.DEVNULL, stderr=log, timeout=180)
        if result.returncode:
            raise WorkflowError('RENDER_FRAME_QC_DECODE_FAILED')
        images = sorted(folder.glob('*.png'))
        # FFmpeg may read an additional frame while flushing the encoder. Only
        # records corresponding one-for-one to actual written PNGs are saved.
        if not 1 <= len(images) <= MAX_FRAMES:
            raise WorkflowError('RENDER_FRAME_QC_TIMESTAMPS_INVALID')
        stamps=decoded_stamps(directory,time_base,len(images))
        frames = []
        for index, path in enumerate(images):
            pts = stamps[index]; seconds = pts * num / den
            if path.name != f'{index}.png':
                raise WorkflowError('RENDER_FRAME_QC_TIMESTAMPS_INVALID')
            measured = image_evidence(checked(directory, f'{FOLDER}/{index}.png'))
            frames.append({**measured, 'frame_id': 'rqf_' + digest([source_sha, index, pts, measured['sha256']])[:24],
                'evidence_frame_reference': f'{FOLDER}/{index}.png', 'decoded_render_pts': pts,
                'decoded_render_pts_seconds': seconds, 'timestamp_seconds': max(0., seconds - start)})
        observation = RenderObservation(rendered_video_sha256=source_sha, document_sha256=document_sha256,
            render_manifest_reference=manifest_name, render_manifest_sha256=manifest_sha, render_stream_time_base=time_base,
            render_stream_start_seconds=start, render_duration_seconds=duration, sampling_interval_seconds=interval,
            frames=frames).model_dump(mode='json')
        record = {'observation': observation, 'sha256': digest(observation)}
        validate(directory, record, document_sha256=document_sha256)
        durable_json(directory / REPORT, record)
        return record
    except WorkflowError:
        raise
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, StopIteration):
        raise WorkflowError('RENDER_FRAME_QC_DECODE_FAILED') from None


def artifact_names(directory):
    record = json.loads(checked(directory, REPORT).read_bytes())
    observation = validate(directory, record)
    return (REPORT, 'render-frame-qc.log', *(frame['evidence_frame_reference'] for frame in observation['frames']))
