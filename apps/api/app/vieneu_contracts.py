"""Pinned, preset-only local audition contract. Not production voice approval."""
from __future__ import annotations
import hashlib
from typing import Literal
from pydantic import Field
from .models import StrictModel
from .content_service import canonical_bytes

MODEL_REVISION = "61b85e3d937fbbacb387714180e8182823512523"
SDK_COMMIT = "85344322b7258b4e25479b692e8e3396baf9db34"
CODEC_REVISION = "ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae"
PRESETS_SHA = "e1f13cd2c2e0d29fdab5e15bfd7a30f3d7b768e6132bb43dd2b853f8efefdce9"
MODEL_CARD_SHA = "5d5bb2de661fabc0e073b3b844dc131696fac3dddd5ea882d10fd9a849108eb7"
CODEC_CARD_SHA = "3c7b9e9ef1c8c5e5c829a077a1d32c1f7aea1668f2bf17ead318ff04bf1e6fe4"
SDK_LICENSE_SHA = "1eb85fc97224598dad1852b5d6483bbcf0aa8608790dcc657a5a2a761ae9c8c6"
LOCAL_ENDPOINT = "http://127.0.0.1:18083"
VOICE_IDS = ("Mai Anh", "Thùy Dung", "Ngọc Huyền")
SELECTED_VOICE = "Thùy Dung"
SELECTED_PROFILE_SHA = "f2d848766784e7bd892680f933a799ec812c1c8acff62b019ac777aa1292c4d3"
AUDITION_SOURCE_COMMIT = "f642e487e89bc8ecf86045c67682a8ec087cd6d2"


class VieNeuLicenseProvenance(StrictModel):
    """Upstream revision-bound license attestation, NOT an Owner RightsRecord."""
    model_config = {"frozen": True}
    schema_version: Literal[1] = 1
    license_identifier: Literal["Apache-2.0"] = "Apache-2.0"
    model_repository: Literal["pnnbao-ump/VieNeu-TTS-v3-Turbo"] = "pnnbao-ump/VieNeu-TTS-v3-Turbo"
    model_revision: Literal[MODEL_REVISION] = MODEL_REVISION
    model_card_sha256: Literal[MODEL_CARD_SHA] = MODEL_CARD_SHA
    sdk_commit: Literal[SDK_COMMIT] = SDK_COMMIT
    sdk_license_sha256: Literal[SDK_LICENSE_SHA] = SDK_LICENSE_SHA
    preset_asset_sha256: Literal[PRESETS_SHA] = PRESETS_SHA
    codec_repository: Literal["OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"] = "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano-ONNX"
    codec_revision: Literal[CODEC_REVISION] = CODEC_REVISION
    codec_card_sha256: Literal[CODEC_CARD_SHA] = CODEC_CARD_SHA
    purpose: Literal["local preset voice audition; human selection pending"] = "local preset voice audition; human selection pending"
    voice_cloning_enabled: Literal[False] = False
    human_quality_accepted: Literal[False] = False

    @property
    def sha256(self):
        return hashlib.sha256(canonical_bytes(self.model_dump(mode="json"))).hexdigest()


class VieNeuSynthesisParameters(StrictModel):
    model_config = {"frozen": True}
    temperature: float = Field(default=.8, gt=0, le=1.5, allow_inf_nan=False)
    top_k: int = Field(default=25, ge=1, le=100)
    top_p: float = Field(default=.95, gt=0, le=1, allow_inf_nan=False)
    repetition_penalty: float = Field(default=1.2, ge=1, le=2, allow_inf_nan=False)
    max_new_frames: Literal[300] = 300
    max_chars: Literal[256] = 256
    babble_retries: Literal[0] = 0
    normalization_layer: Literal["vieneu-3.8.3/sea-g2p-0.9.1-punc_norm-v1"] = "vieneu-3.8.3/sea-g2p-0.9.1-punc_norm-v1"
    watermark: Literal["NOT_INSTALLED_LOCAL_AUDITION"] = "NOT_INSTALLED_LOCAL_AUDITION"


class VieNeuTTSProfile(StrictModel):
    model_config = {"frozen": True}
    version: Literal[3] = 3
    provider_key: Literal["vieneu-tts"] = "vieneu-tts"
    model: Literal["vieneu-v3-turbo"] = "vieneu-v3-turbo"
    model_revision: Literal[MODEL_REVISION] = MODEL_REVISION
    sdk_version: Literal["3.8.3"] = "3.8.3"
    sdk_commit: Literal[SDK_COMMIT] = SDK_COMMIT
    server_version: Literal["vf-vieneu-preset-local-v1"] = "vf-vieneu-preset-local-v1"
    server_image: Literal["NOT_CONTAINERIZED"] = "NOT_CONTAINERIZED"
    runtime_version: Literal["onnxruntime-1.30.0/cpu/numpy-2.5.3/sea-g2p-0.9.1"] = "onnxruntime-1.30.0/cpu/numpy-2.5.3/sea-g2p-0.9.1"
    voice_id: Literal["Mai Anh", "Thùy Dung", "Ngọc Huyền"]
    locale: Literal["vi-VN"] = "vi-VN"
    endpoint: Literal[LOCAL_ENDPOINT] = LOCAL_ENDPOINT
    credential_mode: Literal["none/local_service"] = "none/local_service"
    sample_rate: Literal[48000] = 48000
    parameters: VieNeuSynthesisParameters = Field(default_factory=VieNeuSynthesisParameters)
    rights: VieNeuLicenseProvenance  # mandatory, never inferred from provider name
    alignment_capability: Literal["none"] = "none"
    max_audio_seconds: int = Field(default=180, ge=1, le=180)
    timeout_seconds: int = Field(default=600, ge=1, le=600)

    @property
    def sha256(self):
        return hashlib.sha256(canonical_bytes(self.model_dump(mode="json"))).hexdigest()


def selected_vieneu_profile() -> VieNeuTTSProfile:
    """Exact audition bytes/config; selection does not rewrite license evidence."""
    profile = VieNeuTTSProfile(voice_id=SELECTED_VOICE, rights=VieNeuLicenseProvenance())
    if profile.sha256 != SELECTED_PROFILE_SHA:
        raise ValueError("VIENEU_SELECTED_PROFILE_DRIFT")
    return profile


class VieNeuVoiceSelection(StrictModel):
    """Owner selection sidecar, separate from synthesis and output acceptance."""
    model_config = {"frozen": True}
    schema_id: Literal["vf-mvp1-vieneu-voice-selection-v1"] = "vf-mvp1-vieneu-voice-selection-v1"
    task: Literal["VF-MVP1-VIENEU-THUY-DUNG-SELECTION-02"] = "VF-MVP1-VIENEU-THUY-DUNG-SELECTION-02"
    audition_source_commit: Literal[AUDITION_SOURCE_COMMIT] = AUDITION_SOURCE_COMMIT
    profile_sha256: Literal[SELECTED_PROFILE_SHA] = SELECTED_PROFILE_SHA
    provider: Literal["vieneu-tts"] = "vieneu-tts"
    model: Literal["vieneu-v3-turbo"] = "vieneu-v3-turbo"
    voice: Literal[SELECTED_VOICE] = SELECTED_VOICE
    owner_audition_decision: Literal["PASS_AS_SELECTED_PRODUCTION_TTS_CANDIDATE"] = "PASS_AS_SELECTED_PRODUCTION_TTS_CANDIDATE"
    historical_audition_voices: tuple[Literal["Mai Anh"], Literal["Ngọc Huyền"]] = ("Mai Anh", "Ngọc Huyền")
    timing_source: Literal["ESTIMATED_SEGMENT"] = "ESTIMATED_SEGMENT"
    word_alignment: Literal["WORD_ALIGNMENT_OPEN"] = "WORD_ALIGNMENT_OPEN"
    real_input_output_review: Literal["PENDING"] = "PENDING"
    human_quality_accepted: Literal[False] = False
    deployment_authorized: Literal[False] = False

    @property
    def sha256(self):
        return hashlib.sha256(canonical_bytes(self.model_dump(mode="json"))).hexdigest()
