"""Explicit video-analysis provider selection; no fallback speech or discovery."""
from .auto_edit_providers import ContractOnlyTranscriptionProvider, DeterministicTranscriptionProvider, ProviderNotConfigured
from .uploaded_audio_runtime import provider_from_settings as audio_provider_from_settings


def provider_from_settings(settings):
    if settings.transcription_provider == 'fixture':
        return DeterministicTranscriptionProvider()
    if settings.transcription_provider != 'local_cpu':
        return audio_provider_from_settings(settings)
    if getattr(settings, 'local_asr_enabled', False) is not True:
        return ContractOnlyTranscriptionProvider()
    from .local_video_transcription_provider import LocalVideoTranscriptionProvider
    try:
        return LocalVideoTranscriptionProvider(manifest=settings.local_asr_runtime_manifest,
            manifest_sha256=settings.local_asr_runtime_manifest_sha256, decoder=settings.ffmpeg_path,
            decoder_sha256=settings.local_asr_decoder_sha256, language=settings.local_asr_language,
            model_key=settings.local_asr_model_key, decoder_timeout_seconds=settings.local_asr_decoder_timeout_seconds,
            max_file_bytes=min(settings.local_asr_video_max_file_bytes, settings.upload_max_size_bytes),
            max_duration_seconds=settings.local_asr_max_duration_seconds)
    except (OSError, ValueError, TypeError, KeyError, ProviderNotConfigured):
        return ContractOnlyTranscriptionProvider()
