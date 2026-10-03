"""Provider-neutral TTS profile and honest timing/evidence contracts."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator
from .content_service import canonical_bytes
from .models import StrictModel


class ProductionTTSProfile(StrictModel):
    model_config = {"frozen": True}
    version: Literal[1] = 1
    provider_key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,119}$")
    model: str = Field(min_length=1, max_length=160)
    voice_id: str = Field(min_length=1, max_length=80)
    locale: Literal["vi-VN"] = "vi-VN"
    speed: float = Field(default=1, ge=0.25, le=4, allow_inf_nan=False)
    style_instructions: str = Field(default="", max_length=500)
    alignment_capability: Literal["none", "provider_word", "forced_alignment"] = "none"

    @property
    def sha256(self):
        return hashlib.sha256(canonical_bytes(self.model_dump(mode="json"))).hexdigest()


class SpeechTimingInterval(StrictModel):
    text: str = Field(min_length=1, max_length=180)
    start_seconds: float = Field(ge=0, allow_inf_nan=False)
    end_seconds: float = Field(gt=0, allow_inf_nan=False)
    @model_validator(mode="after")
    def positive(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("TTS timing interval must be positive; no repair")
        return self


def _tokens(text):
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFC", text).casefold())


class SpeechTimingEvidence(StrictModel):
    source: Literal["NONE", "PROVIDER_MEASURED", "MEASURED_PROVIDER", "FORCED_ALIGNMENT", "ESTIMATED_SEGMENT"] = "NONE"
    reference_text: str = Field(default="", max_length=20000)
    audio_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    words: list[SpeechTimingInterval] = Field(default_factory=list, max_length=4000)
    segments: list[SpeechTimingInterval] = Field(default_factory=list, max_length=300)
    aligner_identity: str | None = Field(default=None, min_length=1, max_length=160)
    @model_validator(mode="after")
    def trustworthy(self):
        if self.source in {"NONE", "ESTIMATED_SEGMENT"} and self.words:
            raise ValueError("estimated/absent timing cannot claim word alignment")
        if self.source == "NONE" and self.segments:
            raise ValueError("absent timing cannot carry intervals")
        # MEASURED_PROVIDER is a loadable source-candidate legacy spelling,
        # not a second timing source; new evidence should use PROVIDER_MEASURED.
        if self.source in {"PROVIDER_MEASURED", "MEASURED_PROVIDER", "FORCED_ALIGNMENT"}:
            if not self.audio_sha256 or not self.words or not self.reference_text:
                raise ValueError("word alignment requires audio/input identity and complete words")
            if _tokens(self.reference_text) != _tokens(" ".join(w.text for w in self.words)):
                raise ValueError("word timing coverage must match complete narration")
        if self.source == "FORCED_ALIGNMENT" and not self.aligner_identity:
            raise ValueError("forced alignment requires exact aligner identity")
        for intervals in (self.words, self.segments):
            previous = 0.0
            for interval in intervals:
                if interval.start_seconds < previous or interval.end_seconds > self.duration_seconds:
                    raise ValueError("non-monotonic or out-of-audio TTS timing")
                previous = interval.end_seconds
        return self


class TTSArtifactEvidence(StrictModel):
    version: Literal[1] = 1
    profile: ProductionTTSProfile
    profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    text_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    audio_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decoded_duration_seconds: float = Field(gt=0, allow_inf_nan=False)
    latency_seconds: float = Field(ge=0, allow_inf_nan=False)
    timing: SpeechTimingEvidence
    usage: dict = Field(default_factory=dict)
    modelled_cost_vnd: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    provider_credit_debit: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    out_of_pocket_spend_vnd: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    billing_status: Literal["UNKNOWN", "PROVIDER_REPORTED"] = "UNKNOWN"
    human_quality_accepted: Literal[False] = False
    @model_validator(mode="after")
    def identities(self):
        if self.profile_sha256 != self.profile.sha256:
            raise ValueError("TTS profile digest mismatch")
        if self.timing.duration_seconds != self.decoded_duration_seconds:
            raise ValueError("TTS decoded duration mismatch")
        if self.timing.audio_sha256 and self.timing.audio_sha256 != self.audio_sha256:
            raise ValueError("alignment belongs to a different audio payload")
        if self.timing.reference_text and hashlib.sha256(self.timing.reference_text.encode()).hexdigest() != self.text_sha256:
            raise ValueError("alignment belongs to different narration")
        return self


def tts_zero_call_readiness(profile: ProductionTTSProfile | None, *, owner_voice_selected=False,
                           capability_scope_verified=False, credential_binding_verified=False):
    # Values are metadata attestations supplied by a future verified caller.
    # This helper doesn't validate live authority, read a secret, or reserve.
    blockers = []
    if profile is None:
        blockers.append("MODEL_VOICE_CONFIG_REQUIRED")
    if not owner_voice_selected:
        blockers.append("OWNER_VOICE_SELECTION_REQUIRED")
    if not capability_scope_verified:
        blockers.append("TTS_CAPABILITY_AUTHORITY_REQUIRED")
    if not credential_binding_verified:
        blockers.append("TTS_CREDENTIAL_BINDING_REQUIRED")
    return {"status": "CONFIG_METADATA_PASS" if not blockers else "NOT_READY",
        "blockers": blockers, "provider_calls": 0, "credential_reads": 0,
        "full_preflight": "NOT_RUN", "human_quality_accepted": False}
