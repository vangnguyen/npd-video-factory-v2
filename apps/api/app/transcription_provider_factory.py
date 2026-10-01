"""Closed transcription-provider registry for verified execution scopes."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from .assemblyai_asr_profile import AssemblyAIAsrProfile
from .assemblyai_transcription_provider import AssemblyAITranscriptionProvider
from .openai_transcription_provider import OpenAITranscriptionProvider
from .provider_safety import ProviderExecutionGateScope


TranscriptionAdapter = OpenAITranscriptionProvider | AssemblyAITranscriptionProvider
ALLOWLISTED_TRANSCRIPTION_IMPLEMENTATIONS = frozenset({
    "openai-transcription",
    "assemblyai-transcription",
})


def create_verified_transcription_provider(
    scope: ProviderExecutionGateScope,
    credential_resolver: Callable[[str], str],
    *,
    openai_provider_type: type[OpenAITranscriptionProvider] = OpenAITranscriptionProvider,
    assemblyai_provider_type: type[AssemblyAITranscriptionProvider] = AssemblyAITranscriptionProvider,
) -> TranscriptionAdapter:
    common = {
        "credential_alias": scope.credential_alias,
        "credential_resolver": credential_resolver,
        "language": scope.requested_language,
        "provider_http_timeout_seconds": scope.provider_http_timeout_seconds,
        "controller_hard_timeout_seconds": scope.controller_hard_timeout_seconds,
        "max_file_bytes": scope.max_file_bytes or 0,
        "max_duration_seconds": scope.max_duration_seconds or 0,
        "estimated_cost_vnd": scope.per_operation_limit_vnd,
        "vnd_per_minute": scope.vnd_per_minute or Decimal("0"),
    }
    if scope.provider_key == "openai-transcription":
        return openai_provider_type(
            model="whisper-1",
            asr_prompt_profile=scope.asr_prompt_profile,
            **common,
        )
    if scope.provider_key == "assemblyai-transcription":
        if type(scope.asr_prompt_profile) is not AssemblyAIAsrProfile:
            raise ValueError("ASSEMBLYAI_PROFILE_BINDING_INVALID")
        return assemblyai_provider_type(
            model="universal-3-5-pro",
            profile=scope.asr_prompt_profile,
            **common,
        )
    raise ValueError("PROVIDER_IMPLEMENTATION_NOT_ALLOWLISTED")
