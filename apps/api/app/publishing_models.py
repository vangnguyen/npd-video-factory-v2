from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from .models import StrictModel


PublishingPlatform = Literal["youtube", "tiktok", "instagram_reels", "facebook"]
PublicationMode = Literal["dry_run", "live"]
PublicationStatus = Literal[
    "validating",
    "blocked",
    "dry_run_succeeded",
    "publishing",
    "published",
    "failed",
    "cancelled",
]


class PublicationMetadata(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10_000)
    caption: str = Field(default="", max_length=10_000)
    hashtags: list[str] = Field(default_factory=list, max_length=40)
    thumbnail_asset_id: str | None = Field(default=None, pattern=r"^ast_[A-Za-z0-9_-]{4,60}$")
    privacy: Literal["private", "unlisted", "public"] = "private"
    scheduled_at: datetime | None = None

    @field_validator("hashtags")
    @classmethod
    def validate_hashtags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            tag = item.strip().lstrip("#")
            if not tag or len(tag) > 80 or any(character.isspace() for character in tag):
                raise ValueError("hashtags must be non-empty single tokens of at most 80 characters")
            if tag not in normalized:
                normalized.append(tag)
        return normalized

    @model_validator(mode="after")
    def validate_schedule(self) -> "PublicationMetadata":
        if self.scheduled_at is not None and self.scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at must include a timezone")
        return self


class PublicationCreateRequest(StrictModel):
    platform: PublishingPlatform
    final_render_id: str = Field(pattern=r"^rnd_[A-Za-z0-9_-]{4,60}$")
    mode: PublicationMode = "dry_run"
    metadata: PublicationMetadata
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)


class PublishingValidationCheck(StrictModel):
    key: str = Field(min_length=1, max_length=100)
    passed: bool
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    evidence: dict[str, Any] = Field(default_factory=dict)


class RightsValidationRead(StrictModel):
    status: Literal["passed", "failed"]
    policy_version: str
    asset_ids: list[str]
    checks: list[PublishingValidationCheck]


class PlatformCapabilityRead(StrictModel):
    platform: PublishingPlatform
    version: str
    verification_state: Literal["internal_safe_profile", "owner_verified_for_live"]
    supported_profiles: list[str]
    min_duration_seconds: float = Field(ge=0)
    max_duration_seconds: float = Field(gt=0)
    max_file_size_bytes: int = Field(gt=0)
    video_codecs: list[str]
    audio_codecs: list[str]
    max_title_characters: int = Field(gt=0)
    max_caption_characters: int = Field(gt=0)
    max_hashtags: int = Field(ge=0)
    thumbnail: Literal["optional", "required", "unsupported"]


class PlatformValidationRead(StrictModel):
    status: Literal["passed", "failed"]
    capability: PlatformCapabilityRead
    checks: list[PublishingValidationCheck]


class ProviderValidationRead(StrictModel):
    provider_key: str
    adapter_state: Literal["mock", "not_configured", "contract_only", "ready"]
    credential_status: Literal["not_required", "not_configured", "configured"]
    official_api_only: Literal[True] = True
    supports_dry_run: bool
    supports_live_publish: bool
    checks: list[PublishingValidationCheck]


class PublishingPlatformStateRead(StrictModel):
    platform: PublishingPlatform
    capability: PlatformCapabilityRead
    dry_run_provider: ProviderValidationRead
    official_provider: ProviderValidationRead
    live_execution_enabled: bool


class PublicationReceipt(StrictModel):
    receipt_id: str
    provider_key: str
    platform: PublishingPlatform
    mode: PublicationMode
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    remote_post_id: str | None = None
    remote_url: str | None = None
    mock: bool
    external_action: bool
    duplicate_post_created: Literal[False] = False
    created_at: datetime


class PublicationRead(StrictModel):
    publication_id: str
    workspace_id: str
    project_id: str
    package_id: str
    approval_id: str
    final_render_id: str
    output_asset_id: str
    platform: PublishingPlatform
    provider_key: str
    capability_version: str
    mode: PublicationMode
    status: PublicationStatus
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    metadata: PublicationMetadata
    rights_validation: RightsValidationRead | None
    platform_validation: PlatformValidationRead | None
    provider_validation: ProviderValidationRead | None
    receipt: PublicationReceipt | None
    dry_run: bool
    mock: bool
    external_action: bool
    attempt_count: int = Field(ge=1)
    failure_code: str | None
    failure_reason: str | None
    actor_ref: str
    created_at: datetime
    updated_at: datetime


class PublicationEventRead(StrictModel):
    event_id: str
    publication_id: str
    project_id: str
    event_type: str
    actor_ref: str
    payload: dict[str, Any]
    created_at: datetime
