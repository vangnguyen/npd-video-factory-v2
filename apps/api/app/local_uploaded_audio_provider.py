"""Explicit offline CPU ASR for SQL uploaded audio, reusing approved model custody."""
import asyncio
import copy
from dataclasses import asdict, replace
from decimal import Decimal
import math
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
import wave
from app.auto_edit_models import MediaMetadata
from app.auto_edit_providers import ProviderNotConfigured, ProviderWord, ProviderSegment
from app.local_asr_runtime import runtime, plain, file_sha
from app.local_asr_profile import profile, model_manifest, digest
from app.local_transcription_provider import LocalCpuTranscriptionProvider, SCRIPT
from app.decoded_audio_clock import parse_audio_clock, audio_clock_lines
import app.local_asr_profile as profile_module
import app.local_asr_runtime as runtime_module
import app.local_transcription_provider as cpu_module
import app.decoded_audio_clock as clock_module
import app.source_audio_clock as source_clock_module


class LocalAudioRejected(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class LocalAudioEvidenceRejected(LocalAudioRejected):
    """One invocation's rejected result, independent of shared diagnostics."""
    def __init__(self, code, evidence):
        super().__init__(code)
        self.evidence = {**copy.deepcopy(evidence), 'rejection_code': code}
        self.evidence_sha256 = digest(self.evidence)


def proof(path):
    path = plain(path)
    if not path.is_file():
        raise ValueError('LOCAL_AUDIO_FILE_REQUIRED')
    return {'path_sha256': digest(str(path)), 'bytes': path.stat().st_size, 'sha256': file_sha(path)}


def custody(manifest, expected_manifest_sha256, decoder, expected_decoder_sha256, model_key):
    manifest = plain(manifest);decoder = plain(decoder)
    if file_sha(manifest) != expected_manifest_sha256 or file_sha(decoder) != expected_decoder_sha256:
        raise ValueError('LOCAL_AUDIO_RUNTIME_CHANGED')
    selected = runtime(manifest, model_key=model_key)
    model = model_manifest(model_key)
    files = {name: proof(Path(selected['model_root'])/name) for name in model['files']}
    public = {'schema_version': 'sql-local-audio-runtime.v1', 'runtime_manifest': proof(manifest),
        'python': proof(selected['python']), 'model_root_sha256': digest(str(plain(selected['model_root']))),
        'model_manifest_sha256': selected['model_manifest_sha256'], 'model_files': files,
        'decoder': proof(decoder), 'inference_script': proof(SCRIPT),
        'uploaded_audio_adapter': proof(__file__),
        'code_files': {label: proof(module.__file__) for label, module in {
            'profile': profile_module, 'runtime': runtime_module, 'cpu_provider': cpu_module,
            'audio_clock': clock_module, 'canonical_source_clock': source_clock_module}.items()},
        'model': model['model'], 'model_revision': model['revision'], 'license': model['license'],
        'library': 'faster-whisper', 'library_version': '1.2.1', 'device': 'cpu', 'compute_type': 'int8',
        'cpu_threads': selected['cpu_threads'], 'inference_timeout_seconds': selected['timeout_seconds']}
    return selected, public


async def bounded_process(arguments, *, timeout, maximum_stderr=16*1024*1024):
    env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', PYTHONUTF8='1')
    child = await asyncio.create_subprocess_exec(*arguments, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    async def collect():
        output = bytearray()
        while True:
            chunk = await child.stderr.read(65536)
            if not chunk:
                break
            output.extend(chunk)
            if len(output) > maximum_stderr:
                raise LocalAudioRejected('LOCAL_AUDIO_DECODER_OUTPUT_LIMIT')
        await child.wait()
        return bytes(output)
    try:
        output = await asyncio.wait_for(collect(), timeout)
        if child.returncode:
            raise LocalAudioRejected('LOCAL_AUDIO_DECODE_FAILED')
        return output
    finally:
        if child.returncode is None:
            child.kill()
            await child.communicate()


def decoded(path, stderr, duration):
    clock = parse_audio_clock(audio_clock_lines(stderr.decode('utf-8', 'strict')), sample_rate=16000)
    with wave.open(str(path), 'rb') as sound:
        if sound.getnchannels() != 1 or sound.getsampwidth() != 2 or sound.getframerate() != 16000 \
                or sound.getnframes() != clock['pcm_samples']:
            raise LocalAudioRejected('LOCAL_AUDIO_PCM_CLOCK_MISMATCH')
        frames = sound.getnframes()
        if len(sound.readframes(frames)) != frames*2:
            raise LocalAudioRejected('LOCAL_AUDIO_PCM_TRUNCATED')
    if not 0 < frames <= 16000*1800 or clock['source_end_seconds'] > duration+1/16000:
        raise LocalAudioRejected('LOCAL_AUDIO_SOURCE_CLOCK_OUTSIDE_MEDIA')
    return clock, frames/16000


def projection(transcript, clock, source_sha256, pcm_sha256, binding):
    """Raw provider evidence remains intact; an observed offset is a derived view."""
    offset = clock['source_start_seconds']
    pcm_duration = clock['pcm_samples']/16000
    source_end = clock['source_end_seconds']
    if len(transcript.segments) > 1000:
        raise LocalAudioRejected('LOCAL_AUDIO_SEGMENT_LIMIT')
    for segment in transcript.segments:
        numbers = [segment.start_seconds, segment.end_seconds,
            *(number for word in segment.words for number in (word.start_seconds, word.end_seconds))]
        if any(type(number) not in (int, float) or not math.isfinite(number) for number in numbers) \
                or not 0 <= segment.start_seconds < segment.end_seconds <= pcm_duration \
                or segment.end_seconds+offset > source_end:
            raise LocalAudioRejected('LOCAL_AUDIO_PROVIDER_OUTSIDE_DECODED_CLOCK')
        for word in segment.words:
            if not segment.start_seconds <= word.start_seconds <= word.end_seconds <= segment.end_seconds \
                    or word.end_seconds+offset > source_end:
                raise LocalAudioRejected('LOCAL_AUDIO_PROVIDER_OUTSIDE_DECODED_CLOCK')
    original = asdict(transcript);original['actual_cost_vnd'] = str(transcript.actual_cost_vnd) if transcript.actual_cost_vnd is not None else None
    segments = tuple(ProviderSegment(start_seconds=s.start_seconds+offset, end_seconds=s.end_seconds+offset,
        text=s.text, speaker=s.speaker, confidence=s.confidence,
        words=tuple(ProviderWord(start_seconds=w.start_seconds+offset, end_seconds=w.end_seconds+offset,
            text=w.text, confidence=w.confidence, timing_semantics=w.timing_semantics) for w in s.words)) for s in transcript.segments)
    return replace(transcript, segments=segments, actual_cost_vnd=Decimal('0'), provenance={**copy.deepcopy(transcript.provenance),
        'source_checksum': source_sha256, 'source_pcm_sha256': pcm_sha256, 'local_runtime_binding': binding,
        'decoded_audio_clock': clock, 'decoded_audio_clock_sha256': digest(clock),
        'provider_pcm_transcript': original, 'provider_pcm_transcript_sha256': digest(original),
        'source_clock_projection': {'schema_version': 'sql-local-audio-source-projection.v1', 'offset_seconds': offset,
            'mapping': 'source_seconds = provider_pcm_seconds + observed_source_start_seconds',
            'derived_projection': True, 'provider_pcm_evidence_mutated': False, 'time_scale_changed': False,
            'observed_clock_tolerance_samples': 1, 'observed_clock_tolerance_seconds': 1/16000,
            'bounds_clipped': False, 'provider_interval_end_imputed': False},
        'word_timing_rewritten': False, 'source_media_mutated': False, 'recognition_review_required': True,
        'canonical_source_clock_policy': source_clock_module.POLICY,
        'canonical_source_alignment_filter': source_clock_module.SOURCE_ALIGNMENT_FILTER,
        'word_confidence_calibrated': False,
        'provider_billed_cost_vnd': 0, 'operating_electricity_hardware_cost_vnd': None,
        'owner_uat_accepted': False, 'publishing_enabled': False})


async def cancellable(factory, is_cancelled):
    if is_cancelled is not None and await is_cancelled():
        raise LocalAudioRejected('LOCAL_AUDIO_CANCELLED')
    task = asyncio.create_task(factory())
    try:
        while not task.done():
            await asyncio.wait([task], timeout=.1)
            if is_cancelled is not None and await is_cancelled():
                raise LocalAudioRejected('LOCAL_AUDIO_CANCELLED')
        return await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


class LocalUploadedAudioProvider:
    key = 'local-faster-whisper'
    external_call = False
    paid = False
    credential_alias = None
    estimated_cost_vnd = Decimal('0')
    profile = None  # Paid provider prompt profiles are deliberately absent.
    response_format = 'json'
    timestamp_granularities = ('segment', 'word')
    supports_durable_cancellation = True

    def __init__(self, *, manifest, manifest_sha256, decoder, decoder_sha256,
        language='auto', model_key='base', decoder_timeout_seconds=60,
        max_file_bytes=25_000_000, max_duration_seconds=1800):
        if model_key not in {'base', 'small'} or language not in {'vi', 'en', 'auto'}:
            raise ProviderNotConfigured('LOCAL_AUDIO_MODEL_OR_LANGUAGE_NOT_CONFIGURED')
        if type(decoder_timeout_seconds) is not int or not 1 <= decoder_timeout_seconds <= 120 \
                or type(max_file_bytes) is not int or not 1 <= max_file_bytes <= 25_000_000 \
                or type(max_duration_seconds) not in (int, float) or not math.isfinite(max_duration_seconds) \
                or not 0 < max_duration_seconds <= 1800:
            raise ValueError('LOCAL_AUDIO_BOUNDS_INVALID')
        self._manifest, self._decoder = plain(manifest), plain(decoder)
        self._manifest_sha256, self._decoder_sha256 = manifest_sha256, decoder_sha256
        self.language, self.model_key = language, model_key
        self.decoder_timeout_seconds = decoder_timeout_seconds
        self.max_file_bytes, self.max_duration_seconds = max_file_bytes, max_duration_seconds
        self._profile = profile(language, model_key)
        self.model = self._profile['model']
        _, public = custody(self._manifest, manifest_sha256, self._decoder, decoder_sha256, model_key)
        self._binding = {**public, 'profile': self._profile, 'decoder_timeout_seconds': decoder_timeout_seconds,
            'max_file_bytes': max_file_bytes, 'max_duration_seconds': max_duration_seconds,
            'clock_policy': 'observed_contiguous_pcm_affine_source_projection.v1',
            'canonical_clock_policy': source_clock_module.POLICY,
            'canonical_source_alignment_filter': source_clock_module.SOURCE_ALIGNMENT_FILTER}
        self._frozen_sha256 = digest(self._binding)
        self.raw_result = None

    @property
    def immutable_binding(self):
        return {**copy.deepcopy(self._binding), 'sha256': self._frozen_sha256}

    def verify(self):
        _, current = custody(self._manifest, self._manifest_sha256, self._decoder, self._decoder_sha256, self.model_key)
        current.update(profile=profile(self.language, self.model_key), decoder_timeout_seconds=self.decoder_timeout_seconds,
            max_file_bytes=self.max_file_bytes, max_duration_seconds=self.max_duration_seconds,
            clock_policy='observed_contiguous_pcm_affine_source_projection.v1',
            canonical_clock_policy=source_clock_module.POLICY,
            canonical_source_alignment_filter=source_clock_module.SOURCE_ALIGNMENT_FILTER)
        if digest(current) != self._frozen_sha256 or digest(self._binding) != self._frozen_sha256 \
                or self._profile != current['profile'] or self.model != current['model'] or self.profile is not None \
                or self.external_call is not False or self.paid is not False or self.credential_alias is not None \
                or self.key != 'local-faster-whisper' or self.estimated_cost_vnd != Decimal('0') \
                or self.response_format != 'json' or self.timestamp_granularities != ('segment', 'word'):
            raise ProviderNotConfigured('LOCAL_AUDIO_RUNTIME_OR_CONFIGURATION_CHANGED')

    def evidence(self, raw, clock, source_sha256, pcm_sha256, size, *, normalized):
        return {'schema_version': 'sql-local-audio-evidence.v1', 'model_result': copy.deepcopy(raw),
            'model_result_sha256': digest(raw), 'decoded_audio_clock': copy.deepcopy(clock),
            'decoded_audio_clock_sha256': digest(clock), 'pcm_sha256': pcm_sha256,
            'source_sha256': source_sha256, 'source_size_bytes': size,
            'immutable_binding': self.immutable_binding, 'provider_result_normalized': normalized,
            'source_projection_validated': False,
            'source_checksum_verified_before_inference': True,
            'source_checksum_verified_after_result': None,
            'provider_billed_cost_vnd': 0, 'operating_electricity_hardware_cost_vnd': None,
            'human_accepted': False, 'publishing_enabled': False}

    async def transcribe(self, path, *, metadata, checksum_sha256, execution_trace=None, is_cancelled=None):
        self.raw_result = None
        await asyncio.to_thread(self.verify)
        source = plain(path)
        if metadata.media_kind != 'audio' or metadata.detected_content_type not in {'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/flac'} \
                or not source.is_file() or not 0 < source.stat().st_size <= self.max_file_bytes \
                or metadata.duration_seconds is None or not 0 < metadata.duration_seconds <= self.max_duration_seconds:
            raise LocalAudioRejected('LOCAL_AUDIO_SOURCE_UNSUPPORTED_OR_LIMIT')
        if await asyncio.to_thread(file_sha, source) != checksum_sha256:
            raise LocalAudioRejected('LOCAL_AUDIO_SOURCE_CHANGED')
        with TemporaryDirectory(prefix='vf-sql-asr-') as owned:
            pcm = Path(owned)/'speech.wav'
            output = await cancellable(lambda: bounded_process([str(self._decoder), '-hide_banner', '-xerror', '-nostdin', '-y',
                '-copyts', '-start_at_zero', '-protocol_whitelist', 'file,pipe', '-i', str(source),
                '-map', '0:a:0', '-vn', '-ac', '1', '-af', 'aresample=16000,asettb=1/16000,ashowinfo',
                '-c:a', 'pcm_s16le', str(pcm)], timeout=self.decoder_timeout_seconds), is_cancelled)
            clock, duration = await asyncio.to_thread(decoded, pcm, output, metadata.duration_seconds)
            await asyncio.to_thread(self.verify)
            if await asyncio.to_thread(file_sha, source) != checksum_sha256:
                raise LocalAudioRejected('LOCAL_AUDIO_SOURCE_CHANGED')
            pcm_sha = await asyncio.to_thread(file_sha, pcm)
            provider = LocalCpuTranscriptionProvider(self._manifest, self.language, model_key=self.model_key)
            if provider.profile != self._profile:
                raise ProviderNotConfigured('LOCAL_AUDIO_PROFILE_CHANGED')
            try:
                transcript = await cancellable(lambda: provider.transcribe(pcm, metadata=MediaMetadata(media_kind='audio',
                    detected_content_type='audio/wav', duration_seconds=duration, audio_channels=1, audio_sample_rate=16000),
                    checksum_sha256=pcm_sha, execution_trace=execution_trace), is_cancelled)
            except Exception:
                if isinstance(provider.raw_result, dict):
                    captured = self.evidence(provider.raw_result, clock, checksum_sha256, pcm_sha,
                        source.stat().st_size, normalized=False)
                    self.raw_result = copy.deepcopy(captured)
                    raise LocalAudioEvidenceRejected('LOCAL_AUDIO_NORMALIZATION_REJECTED', captured) from None
                raise
            await asyncio.to_thread(self.verify)
            if await asyncio.to_thread(file_sha, source) != checksum_sha256 or await asyncio.to_thread(file_sha, pcm) != pcm_sha:
                raise LocalAudioRejected('LOCAL_AUDIO_SOURCE_OR_PCM_CHANGED')
            raw = copy.deepcopy(provider.raw_result)
            if not isinstance(raw, dict):
                raise LocalAudioRejected('LOCAL_AUDIO_RAW_MODEL_RESULT_REQUIRED')
            captured = self.evidence(raw, clock, checksum_sha256, pcm_sha, source.stat().st_size, normalized=True)
            captured['original_source_unchanged'] = True
            captured['source_checksum_verified_after_result'] = True
            self.raw_result = copy.deepcopy(captured)
            try:
                projected = projection(transcript, clock, checksum_sha256, pcm_sha, self.immutable_binding)
            except LocalAudioRejected as exc:
                raise LocalAudioEvidenceRejected(exc.code, captured) from None
            captured['source_projection_validated'] = True
            self.raw_result = copy.deepcopy(captured)
            return replace(projected, provenance={**projected.provenance, 'raw_model_result': raw,
                'raw_model_result_sha256': digest(raw)})
