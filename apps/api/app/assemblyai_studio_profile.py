"""Allowlisted general-purpose ASR profiles; the certified VI profile is separate."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .assemblyai_asr_profile import ASSEMBLYAI_MODEL


class AssemblyAIStudioProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, revalidate_instances="always")
    schema_version: Literal["assemblyai-studio-asr-profile-v1"]
    profile_id: str
    provider_key: Literal["assemblyai-transcription"]
    model: Literal["universal-3-5-pro"]
    language: Literal["vi", "en", "auto"]
    punctuate: Literal[True]
    format_text: Literal[True]
    automatic_retry: Literal[False]
    model_fallback: Literal[False]

    @model_validator(mode="after")
    def allowlisted(self):
        if self.profile_id != "asr-assemblyai-studio-" + self.language + "-v1":
            raise ValueError("ASSEMBLYAI_STUDIO_PROFILE_NOT_ALLOWLISTED")
        return self


def studio_profile(language: str) -> AssemblyAIStudioProfile:
    return AssemblyAIStudioProfile.model_validate({
        "schema_version": "assemblyai-studio-asr-profile-v1",
        "profile_id": "asr-assemblyai-studio-" + language + "-v1",
        "provider_key": "assemblyai-transcription", "model": ASSEMBLYAI_MODEL,
        "language": language, "punctuate": True, "format_text": True,
        "automatic_retry": False, "model_fallback": False,
    })


def studio_profile_sha256(value: object) -> str:
    if type(value) is AssemblyAIStudioProfile:
        value = value.model_dump(mode="python")
    profile = AssemblyAIStudioProfile.model_validate(value)
    return hashlib.sha256(json.dumps(profile.model_dump(mode="json"), ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def studio_request(profile: AssemblyAIStudioProfile, audio_url: str) -> dict:
    profile = AssemblyAIStudioProfile.model_validate(profile)
    request = {"audio_url": audio_url, "speech_models": [profile.model],
        "punctuate": True, "format_text": True}
    if profile.language == "auto":
        request.update(language_detection=True,
            language_detection_options={"expected_languages": ["vi", "en"]})
    else:
        request["language_code"] = profile.language
    return request


def studio_result_language(profile: AssemblyAIStudioProfile, result: dict) -> str:
    profile = AssemblyAIStudioProfile.model_validate(profile)
    language = result.get("language_code")
    # Provider expected_languages is a hint, not a strict filter. Never relabel.
    if language not in {"vi", "en"} or profile.language != "auto" and language != profile.language:
        raise ValueError("ASSEMBLYAI_STUDIO_LANGUAGE_MISMATCH")
    if result.get("speech_model_used") != profile.model:
        raise ValueError("ASSEMBLYAI_MODEL_MISMATCH_NO_FALLBACK")
    return language
