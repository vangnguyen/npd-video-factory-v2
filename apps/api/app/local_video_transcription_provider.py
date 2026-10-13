"""Explicit offline video ASR; measured source projection retains raw PCM evidence."""
import asyncio
import copy
from dataclasses import replace
from decimal import Decimal
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from .auto_edit_models import MediaMetadata
from .auto_edit_providers import ProviderNotConfigured
from .local_asr_profile import digest, profile
from .local_asr_runtime import plain, file_sha
from .local_transcription_provider import LocalCpuTranscriptionProvider
from .local_uploaded_audio_provider import custody, proof, bounded_process, decoded, projection


async def completed_io(awaitable):
    """Drain file I/O before a cancelled caller removes its owned files."""
    task = asyncio.create_task(awaitable)
    try:
        return await asyncio.shield(task)
    except BaseException:
        # Repeated cancellation is still a request to stop the caller, never
        # permission to abandon a thread that owns an open temporary file.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if task.done() and not task.cancelled():
            task.exception()  # Retrieve any I/O failure while preserving caller cancellation.
        raise


class LocalVideoRejected(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


async def cancellable(factory, is_cancelled):
    """One cancellation reaches the child; later caller cancellation drains it."""
    if is_cancelled is not None and await is_cancelled():
        raise LocalVideoRejected('LOCAL_VIDEO_CANCELLED')
    task = asyncio.create_task(factory())
    try:
        while not task.done():
            await asyncio.wait([task], timeout=.1)
            if is_cancelled is not None and await is_cancelled():
                raise LocalVideoRejected('LOCAL_VIDEO_CANCELLED')
        return await task
    finally:
        if not task.done():
            task.cancel()
        async def collect():
            return await asyncio.gather(task, return_exceptions=True)
        await completed_io(collect())


class LocalVideoEvidenceRejected(LocalVideoRejected):
    """Immutable result of this invocation, never a shared raw-result lookup."""
    def __init__(self, code, evidence):
        super().__init__(code)
        self.evidence = {**copy.deepcopy(evidence), 'rejection_code': code}
        self.evidence_sha256 = digest(self.evidence)


class LocalVideoTranscriptionProvider:
    key = 'local-faster-whisper'
    external_call = False
    paid = False
    credential_alias = None
    estimated_cost_vnd = Decimal('0')
    profile = None
    response_format = 'json'
    timestamp_granularities = ('segment', 'word')
    supports_durable_cancellation = True

    def __init__(self, *, manifest, manifest_sha256, decoder, decoder_sha256,
                 language='auto', model_key='base', decoder_timeout_seconds=60,
                 max_file_bytes=2*1024**3, max_duration_seconds=1800):
        if model_key not in {'base', 'small'} or language not in {'vi', 'en', 'auto'}:
            raise ProviderNotConfigured('LOCAL_VIDEO_MODEL_OR_LANGUAGE_NOT_CONFIGURED')
        if (type(decoder_timeout_seconds) is not int or not 1 <= decoder_timeout_seconds <= 120
            or type(max_file_bytes) is not int or not 1 <= max_file_bytes <= 2*1024**3
            or type(max_duration_seconds) not in (int, float) or not math.isfinite(max_duration_seconds)
            or not 0 < max_duration_seconds <= 1800):
            raise ValueError('LOCAL_VIDEO_BOUNDS_INVALID')
        self._manifest, self._decoder = plain(manifest), plain(decoder)
        self._manifest_sha256, self._decoder_sha256 = manifest_sha256, decoder_sha256
        self.language, self.model_key = language, model_key
        self.decoder_timeout_seconds = decoder_timeout_seconds
        self.max_file_bytes, self.max_duration_seconds = max_file_bytes, max_duration_seconds
        self.max_pcm_bytes = int(math.ceil(max_duration_seconds*16000))*2+4096
        self._profile = profile(language, model_key)
        self.model = self._profile['model']
        self._binding = self._current_binding()
        self._frozen_sha256 = digest(self._binding)

    def _current_binding(self):
        _, public = custody(self._manifest, self._manifest_sha256, self._decoder, self._decoder_sha256, self.model_key)
        return {**public, 'schema_version': 'sql-local-video-runtime.v1', 'video_adapter': proof(__file__),
            'profile': profile(self.language, self.model_key), 'decoder_timeout_seconds': self.decoder_timeout_seconds,
            'max_file_bytes': self.max_file_bytes, 'max_duration_seconds': self.max_duration_seconds,
            'max_pcm_bytes': self.max_pcm_bytes, 'input_media_kind': 'video',
            'clock_policy': 'observed_contiguous_pcm_affine_source_projection.v1'}

    @property
    def immutable_binding(self):
        return {**copy.deepcopy(self._binding), 'sha256': self._frozen_sha256}

    def verify(self):
        try:
            current = self._current_binding()
        except (OSError, ValueError, TypeError, KeyError):
            raise ProviderNotConfigured('LOCAL_VIDEO_RUNTIME_OR_CONFIGURATION_CHANGED') from None
        if (digest(current) != self._frozen_sha256 or digest(self._binding) != self._frozen_sha256
            or self._profile != current['profile'] or self.model != current['model']
            or self.profile is not None or self.key != 'local-faster-whisper'
            or self.external_call is not False or self.paid is not False or self.credential_alias is not None
            or self.estimated_cost_vnd != Decimal('0') or self.response_format != 'json'
            or self.timestamp_granularities != ('segment', 'word')):
            raise ProviderNotConfigured('LOCAL_VIDEO_RUNTIME_OR_CONFIGURATION_CHANGED')

    def _evidence(self, raw, clock, sha, pcm_sha, size, *, normalized):
        return {'schema_version': 'sql-local-video-evidence.v1', 'model_result': copy.deepcopy(raw),
            'model_result_sha256': digest(raw), 'decoded_audio_clock': copy.deepcopy(clock),
            'decoded_audio_clock_sha256': digest(clock), 'pcm_sha256': pcm_sha, 'source_sha256': sha,
            'source_size_bytes': size, 'immutable_binding': self.immutable_binding,
            'provider_result_normalized': normalized, 'source_projection_validated': False,
            'source_checksum_verified_before_inference': True, 'source_checksum_verified_after_result': None,
            'provider_billed_cost_vnd': 0, 'operating_electricity_hardware_cost_vnd': None,
            'human_accepted': False, 'publishing_enabled': False}

    async def transcribe(self, path, *, metadata, checksum_sha256, execution_trace=None, is_cancelled=None):
        await completed_io(asyncio.to_thread(self.verify))
        source = plain(path)
        source_size = source.stat().st_size if source.is_file() else 0
        if (metadata.media_kind != 'video' or not metadata.detected_content_type.startswith('video/')
            or metadata.video_codec is None or metadata.audio_codec is None
            or not source.is_file() or not 0 < source_size <= self.max_file_bytes
            or metadata.duration_seconds is None or not 0 < metadata.duration_seconds <= self.max_duration_seconds):
            raise LocalVideoRejected('LOCAL_VIDEO_SOURCE_UNSUPPORTED_OR_LIMIT')
        if await completed_io(asyncio.to_thread(file_sha, source)) != checksum_sha256:
            raise LocalVideoRejected('LOCAL_VIDEO_SOURCE_CHANGED')
        with TemporaryDirectory(prefix='vf-video-asr-') as owned:
            pcm = Path(owned)/'speech.wav'
            output = await cancellable(lambda: bounded_process([str(self._decoder), '-hide_banner', '-xerror', '-nostdin', '-y',
                '-copyts', '-start_at_zero', '-protocol_whitelist', 'file,pipe', '-i', str(source),
                '-map', '0:a:0', '-vn', '-ac', '1', '-af', 'aresample=16000,asettb=1/16000,ashowinfo',
                '-t', str(self.max_duration_seconds), '-c:a', 'pcm_s16le', str(pcm)],
                timeout=self.decoder_timeout_seconds), is_cancelled)
            # The source duration was admitted in full; -t is a resource ceiling,
            # never permission to process a silently truncated overlong source.
            if not 0 < pcm.stat().st_size <= self.max_pcm_bytes:
                raise LocalVideoRejected('LOCAL_VIDEO_PCM_SIZE_LIMIT')
            clock, duration = await completed_io(asyncio.to_thread(decoded, pcm, output, metadata.duration_seconds))
            await completed_io(asyncio.to_thread(self.verify))
            if await completed_io(asyncio.to_thread(file_sha, source)) != checksum_sha256:
                raise LocalVideoRejected('LOCAL_VIDEO_SOURCE_CHANGED')
            pcm_sha = await completed_io(asyncio.to_thread(file_sha, pcm))
            provider = LocalCpuTranscriptionProvider(self._manifest, self.language, model_key=self.model_key)
            if provider.profile != self._profile:
                raise ProviderNotConfigured('LOCAL_VIDEO_PROFILE_CHANGED')
            try:
                transcript = await cancellable(lambda: provider.transcribe(pcm, metadata=MediaMetadata(media_kind='audio',
                    detected_content_type='audio/wav', duration_seconds=duration, audio_channels=1, audio_sample_rate=16000),
                    checksum_sha256=pcm_sha, execution_trace=execution_trace), is_cancelled)
            except Exception:
                if isinstance(provider.raw_result, dict):
                    captured = self._evidence(provider.raw_result, clock, checksum_sha256, pcm_sha,
                        source_size, normalized=False)
                    raise LocalVideoEvidenceRejected('LOCAL_VIDEO_NORMALIZATION_REJECTED', captured) from None
                raise
            raw = copy.deepcopy(provider.raw_result)
            if not isinstance(raw, dict):
                raise LocalVideoRejected('LOCAL_VIDEO_RAW_MODEL_RESULT_REQUIRED')
            captured = self._evidence(raw, clock, checksum_sha256, pcm_sha, source_size, normalized=True)
            try:
                await completed_io(asyncio.to_thread(self.verify))
                if await completed_io(asyncio.to_thread(file_sha, source)) != checksum_sha256 or await completed_io(asyncio.to_thread(file_sha, pcm)) != pcm_sha:
                    raise LocalVideoRejected('LOCAL_VIDEO_SOURCE_OR_PCM_CHANGED')
                captured['source_checksum_verified_after_result'] = True
                projected = projection(transcript, clock, checksum_sha256, pcm_sha, self.immutable_binding)
            except Exception as exc:
                code = getattr(exc, 'code', 'LOCAL_VIDEO_POST_RESULT_CUSTODY_REJECTED')
                raise LocalVideoEvidenceRejected(code, captured) from None
            captured['source_projection_validated'] = True
            return replace(projected, provenance={**projected.provenance, 'raw_model_result': raw,
                'raw_model_result_sha256': digest(raw), 'local_video_evidence': captured,
                'input_media_kind': 'video'})
