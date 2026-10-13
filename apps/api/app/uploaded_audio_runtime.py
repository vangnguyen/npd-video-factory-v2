"""Explicit ASR selection shared by API/worker; the default has no fake speech."""
from .auto_edit_providers import ContractOnlyTranscriptionProvider
from .openai_transcription_provider import OpenAITranscriptionProvider
from .assemblyai_transcription_provider import AssemblyAITranscriptionProvider
from .assemblyai_asr_profile import assemblyai_asr_profile
from .asr_prompt_profile import profile_for_id


def provider_from_settings(settings):
    if settings.transcription_provider == 'openai':
        return OpenAITranscriptionProvider(model=settings.openai_transcription_model,
            credential_alias=settings.openai_transcription_credential_alias,
            credential_resolver=lambda alias:settings.openai_api_key if alias==settings.openai_transcription_credential_alias else '',
            base_url=settings.openai_base_url,language=settings.openai_transcription_language,
            provider_http_timeout_seconds=settings.provider_http_timeout_seconds,
            controller_hard_timeout_seconds=settings.controller_hard_timeout_seconds,
            max_file_bytes=settings.openai_transcription_max_file_bytes,
            max_duration_seconds=settings.openai_transcription_max_duration_seconds,
            estimated_cost_vnd=settings.openai_transcription_estimated_cost_vnd,
            vnd_per_minute=settings.openai_transcription_vnd_per_minute,
            asr_prompt_profile=profile_for_id(settings.openai_transcription_prompt_profile_id))
    if settings.transcription_provider == 'assemblyai':
        # Existing SQL custody has no AssemblyAI credential resolver. Do not
        # substitute a Native credential or the historical OpenAI alias.
        return AssemblyAITranscriptionProvider(model=settings.assemblyai_transcription_model,
            credential_alias=settings.assemblyai_transcription_credential_alias,credential_resolver=lambda _: '',
            profile=assemblyai_asr_profile(),language=settings.assemblyai_transcription_language,
            provider_http_timeout_seconds=settings.provider_http_timeout_seconds,
            controller_hard_timeout_seconds=settings.controller_hard_timeout_seconds,
            max_file_bytes=settings.assemblyai_transcription_max_file_bytes,
            max_duration_seconds=settings.assemblyai_transcription_max_duration_seconds,
            estimated_cost_vnd=settings.assemblyai_transcription_estimated_cost_vnd,
            vnd_per_minute=settings.assemblyai_transcription_vnd_per_minute)
    return ContractOnlyTranscriptionProvider()
