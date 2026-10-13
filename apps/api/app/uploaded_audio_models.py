"""Independent uploaded-speech contracts; recognition is never human acceptance."""
from typing import Literal
from pydantic import Field, model_validator
from .models import StrictModel
from .auto_edit_models import TranscriptRead, TranscriptEditRequest
from .transcript_word_review import WordReview
from .provider_safety import ProviderRightsEvidence


class AudioTranscriptionCreate(StrictModel):
    asset_id: str = Field(pattern=r'^ast_[A-Za-z0-9_-]{4,60}$')
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    idempotency_key: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$')
    expected_provider_key: str | None = Field(default=None, max_length=120)
    provider_operation_key: str | None = Field(default=None, max_length=199)
    rights: list[ProviderRightsEvidence] = Field(default_factory=list, max_length=100)


class AudioTextEdit(StrictModel):
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_transcript_id: str = Field(pattern=r'^trn_[a-f0-9]{24}$')
    edit: TranscriptEditRequest


class AudioWordEdit(StrictModel):
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    edit: WordReview


class AudioRestore(StrictModel):
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_version: int = Field(ge=1, strict=True)
    expected_transcript_id: str = Field(pattern=r'^trn_[a-f0-9]{24}$')
    expected_timeline_version: int | None = Field(default=None, ge=1, strict=True)
    target_transcript_id: str = Field(pattern=r'^trn_[a-f0-9]{24}$')
    acknowledged: bool = Field(strict=True)
    note: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def acknowledged_restore(self):
        if not self.acknowledged:
            raise ValueError('explicit restore acknowledgement required')
        return self


class AudioTranscriptionRead(StrictModel):
    schema_version: Literal['uploaded-audio-transcription.v1'] = 'uploaded-audio-transcription.v1'
    audio_id: str
    workspace_id: str
    project_id: str
    asset_id: str
    source_sha256: str
    job: dict
    original: TranscriptRead | None
    current: TranscriptRead | None
    versions: list[TranscriptRead] = Field(max_length=51)
    timeline_version: int | None
    human_review_required: Literal[True] = True
    source_media_mutated: Literal[False] = False
    publishing_enabled: Literal[False] = False


class AudioCaptionApply(StrictModel):
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_transcript_id: str = Field(pattern=r'^trn_[a-f0-9]{24}$')
    expected_version: int = Field(ge=1, strict=True)
    expected_timeline_version: int = Field(ge=1, strict=True)
    source_start: float = Field(default=0., ge=0, allow_inf_nan=False)
    source_end: float = Field(gt=0, allow_inf_nan=False)
    timeline_start: float = Field(default=0., ge=0, allow_inf_nan=False)
    speed: float = Field(default=1., gt=0, le=8, allow_inf_nan=False)
    mute_original: bool = Field(default=False, strict=True)
    acknowledged: bool = Field(strict=True)
    idempotency_key: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{7,159}$')

    @model_validator(mode='after')
    def explicit_apply(self):
        if not self.acknowledged:
            raise ValueError('explicit caption apply acknowledgement required')
        return self
