"""Immutable AssemblyAI request profile selected by the two-asset benchmark.

The profile is source configuration, not provider authority.  Its text is
intentionally independent of either reference transcript.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


ASSEMBLYAI_PROFILE_ID = "asr-assemblyai-vi-direct-v1"
ASSEMBLYAI_PROVIDER_KEY = "assemblyai-transcription"
ASSEMBLYAI_MODEL = "universal-3-5-pro"
ASSEMBLYAI_LANGUAGE = "vi"
ASSEMBLYAI_CREDENTIAL_ALIAS = "secret://assemblyai/stt-video-factory-benchmark"
ASSEMBLYAI_KEYTERMS = (
    "Ngọc Phương Đông",
    "Vinhomes Green Paradise",
    "Cần Giờ",
    "tham quan sa bàn",
    "chính sách bán hàng",
)
ASSEMBLYAI_CONTEXT_PROMPT = (
    "Cuộc tư vấn bằng tiếng Việt về bất động sản, một dự án ven biển và "
    "chuyến tham quan khu trưng bày."
)
ASSEMBLYAI_KEYTERMS_SHA256 = "5b555dd98d59e6ac31f9f88470bd97d2910f479e68165f7940465c94fb7ceccf"
ASSEMBLYAI_CONTEXT_PROMPT_SHA256 = "aa9844e215fb5589eeca1480bc0b3d279ee7001c8e2eae46234a9ba58c120adc"


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _payload() -> dict[str, Any]:
    return {
        "profile_id": ASSEMBLYAI_PROFILE_ID,
        "provider_key": ASSEMBLYAI_PROVIDER_KEY,
        "model": ASSEMBLYAI_MODEL,
        "language": ASSEMBLYAI_LANGUAGE,
        "mode": "async_pre_recorded",
        "keyterms": ASSEMBLYAI_KEYTERMS,
        "keyterms_sha256": ASSEMBLYAI_KEYTERMS_SHA256,
        "context_prompt": ASSEMBLYAI_CONTEXT_PROMPT,
        "context_prompt_sha256": ASSEMBLYAI_CONTEXT_PROMPT_SHA256,
        "native_word_timestamps": True,
        "automatic_retry": False,
        "model_fallback": False,
    }


class AssemblyAIAsrProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, revalidate_instances="always")

    profile_id: Literal["asr-assemblyai-vi-direct-v1"]
    provider_key: Literal["assemblyai-transcription"]
    model: Literal["universal-3-5-pro"]
    language: Literal["vi"]
    mode: Literal["async_pre_recorded"]
    keyterms: tuple[str, str, str, str, str]
    keyterms_sha256: Literal[ASSEMBLYAI_KEYTERMS_SHA256]
    context_prompt: str
    context_prompt_sha256: Literal[ASSEMBLYAI_CONTEXT_PROMPT_SHA256]
    native_word_timestamps: Literal[True]
    automatic_retry: Literal[False]
    model_fallback: Literal[False]

    @property
    def prompt_sha256(self) -> str:
        """Expose the sealed context hash through the strict manifest field name.

        For AssemblyAI, ``prompt_sha256`` binds the scenario-only context
        prompt.  It never denotes a reference transcript or a hidden answer.
        """

        return self.context_prompt_sha256

    @model_validator(mode="before")
    @classmethod
    def exact_profile(cls, value: Any) -> dict[str, Any]:
        if type(value) is AssemblyAIAsrProfile:
            value = value.model_dump(mode="python")
        if type(value) is not dict or set(value) != set(_payload()):
            raise ValueError("ASSEMBLYAI_PROFILE_FIELDS_INVALID")
        supplied = value.copy()
        if type(supplied["keyterms"]) not in (list, tuple):
            raise ValueError("ASSEMBLYAI_PROFILE_FIELD_TYPE_INVALID")
        supplied["keyterms"] = tuple(supplied["keyterms"])
        if supplied != _payload():
            raise ValueError("ASSEMBLYAI_PROFILE_NOT_ALLOWLISTED")
        # Benchmark hashes are semantic decision bindings, not inferred from
        # transcript output.  Verify the exact source bytes independently.
        if hashlib.sha256(ASSEMBLYAI_CONTEXT_PROMPT.encode()).hexdigest() != ASSEMBLYAI_CONTEXT_PROMPT_SHA256:
            raise ValueError("ASSEMBLYAI_CONTEXT_PROMPT_HASH_INVALID")
        keyterms_bytes = json.dumps(
            list(ASSEMBLYAI_KEYTERMS), ensure_ascii=False, separators=(",", ":")
        ).encode()
        if hashlib.sha256(keyterms_bytes).hexdigest() != ASSEMBLYAI_KEYTERMS_SHA256:
            raise ValueError("ASSEMBLYAI_KEYTERMS_HASH_INVALID")
        return supplied


def assemblyai_asr_profile() -> AssemblyAIAsrProfile:
    return AssemblyAIAsrProfile.model_validate(_payload())


def validate_assemblyai_profile(value: object) -> AssemblyAIAsrProfile:
    if type(value) is AssemblyAIAsrProfile:
        value = value.model_dump(mode="python")
    return AssemblyAIAsrProfile.model_validate(value)


def assemblyai_profile_sha256(value: object | None = None) -> str:
    profile = assemblyai_asr_profile() if value is None else validate_assemblyai_profile(value)
    return hashlib.sha256(_canonical(profile.model_dump(mode="json"))).hexdigest()
