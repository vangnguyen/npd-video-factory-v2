"""Provider-specific ASR profile dispatch without weakening historical profiles."""

from __future__ import annotations

from typing import TypeAlias

from .assemblyai_asr_profile import (
    ASSEMBLYAI_PROFILE_ID,
    AssemblyAIAsrProfile,
    assemblyai_asr_profile,
    assemblyai_profile_sha256,
    validate_assemblyai_profile,
)
from .asr_prompt_profile import AsrPromptProfile, prompt_profile_sha256, validate_prompt_profile


AsrRequestProfile: TypeAlias = AsrPromptProfile | AssemblyAIAsrProfile


def asr_profile_for_id(profile_id: str | None) -> AsrRequestProfile | None:
    if profile_id == ASSEMBLYAI_PROFILE_ID:
        return assemblyai_asr_profile()
    from .asr_prompt_profile import profile_for_id

    return profile_for_id(profile_id)


def validate_asr_request_profile(value: object | None) -> AsrRequestProfile | None:
    if value is None:
        return None
    if type(value) is AssemblyAIAsrProfile:
        return validate_assemblyai_profile(value)
    if type(value) is AsrPromptProfile:
        return validate_prompt_profile(value)
    if type(value) is dict and value.get("provider_key") == "assemblyai-transcription":
        return validate_assemblyai_profile(value)
    return validate_prompt_profile(value)


def asr_request_profile_sha256(value: object | None) -> str | None:
    profile = validate_asr_request_profile(value)
    if profile is None:
        return None
    if type(profile) is AssemblyAIAsrProfile:
        return assemblyai_profile_sha256(profile)
    return prompt_profile_sha256(profile)
