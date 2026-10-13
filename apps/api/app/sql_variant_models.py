"""Versioned master-family contracts. Reservations grant no execution authority."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

PROFILE_REFS = ('youtube-landscape@1', 'youtube-shorts@1', 'tiktok-short@1',
                'instagram-reel@1', 'social-square@1', 'social-feed@1')
TARGET_GEOMETRY = {
    'youtube_landscape': ('16:9', 1920, 1080, 'youtube', 'review-960x540', 'landscape-1920x1080'),
    'youtube_shorts': ('9:16', 1080, 1920, 'youtube', 'review-540x960', 'vertical-1080x1920'),
    'tiktok': ('9:16', 1080, 1920, 'tiktok', 'review-540x960', 'vertical-1080x1920'),
    'instagram_reels': ('9:16', 1080, 1920, 'instagram_reels', 'review-540x960', 'vertical-1080x1920'),
    'social_square': ('1:1', 1080, 1080, None, 'review-540x540', 'square-1080x1080'),
    'social_feed': ('4:5', 1080, 1350, None, 'review-432x540', 'portrait-1080x1350'),
}
MAX_BINDING_BYTES = 8 * 1024 * 1024


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class VariantProfile(Contract):
    schema_version: Literal['sql-variant-profile.v1'] = 'sql-variant-profile.v1'
    profile_ref: str = Field(pattern=r'^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$')
    target: Literal['youtube_landscape', 'youtube_shorts', 'tiktok', 'instagram_reels', 'social_square', 'social_feed']
    label: str = Field(min_length=1, max_length=100)
    aspect_ratio: Literal['16:9', '9:16', '1:1', '4:5']
    width: int = Field(ge=16, le=7680)
    height: int = Field(ge=16, le=7680)
    platform: Literal['youtube', 'tiktok', 'instagram_reels'] | None
    review_profile: str = Field(min_length=1, max_length=64)
    final_profile: str = Field(min_length=1, max_length=64)

    @model_validator(mode='after')
    def geometry(self):
        if (self.aspect_ratio, self.width, self.height, self.platform, self.review_profile, self.final_profile) != TARGET_GEOMETRY[self.target]:
            raise ValueError('SQL_VARIANT_PROFILE_GEOMETRY_OR_TARGET_INVALID')
        return self


class VariantCatalog(Contract):
    schema_version: Literal['sql-variant-catalog.v1'] = 'sql-variant-catalog.v1'
    catalog_ref: str = Field(pattern=r'^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$')
    profiles: list[VariantProfile] = Field(min_length=6, max_length=6)

    @model_validator(mode='after')
    def six_distinct_targets(self):
        if len({p.profile_ref for p in self.profiles}) != 6 or {p.target for p in self.profiles} != set(TARGET_GEOMETRY):
            raise ValueError('SQL_VARIANT_CATALOG_SIX_TARGETS_REQUIRED')
        return self


def default_catalog():
    labels = ('YouTube · 16:9', 'YouTube Shorts · 9:16', 'TikTok · 9:16',
              'Instagram Reels · 9:16', 'Social · 1:1', 'Feed · 4:5')
    profiles = []
    for ref, target, label in zip(PROFILE_REFS, TARGET_GEOMETRY, labels):
        ratio, width, height, platform, review, final = TARGET_GEOMETRY[target]
        profiles.append(VariantProfile(profile_ref=ref, target=target, label=label, aspect_ratio=ratio,
            width=width, height=height, platform=platform, review_profile=review, final_profile=final))
    return VariantCatalog(catalog_ref='master-platform-formats@1', profiles=profiles)


class NoAuthority(Contract):
    provider_calls: Literal[0] = 0
    new_inference_calls: Literal[0] = 0
    child_projects_created: Literal[0] = 0
    source_bytes_verified: Literal[False] = False
    approval_inherited: Literal[False] = False
    rights_override_inherited: Literal[False] = False
    automatic_render: Literal[False] = False
    publishing_enabled: Literal[False] = False

    @model_validator(mode='before')
    @classmethod
    def exact_flags(cls, value):
        if isinstance(value, dict):
            for key in ('provider_calls', 'new_inference_calls', 'child_projects_created'):
                if key in value and (type(value[key]) is not int or value[key] != 0):
                    raise ValueError('SQL_VARIANT_AUTHORITY_FLAG_INVALID')
            for key in ('source_bytes_verified', 'approval_inherited', 'rights_override_inherited', 'automatic_render', 'publishing_enabled'):
                if key in value and (type(value[key]) is not bool or value[key] is not False):
                    raise ValueError('SQL_VARIANT_AUTHORITY_FLAG_INVALID')
        return value


class RecordProof(Contract):
    table: str = Field(min_length=1, max_length=80)
    owner_ref: str = Field(min_length=1, max_length=64)
    count: int = Field(ge=0)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class AssetProof(Contract):
    asset_id: str = Field(pattern=r'^ast_[A-Za-z0-9_-]{4,60}$')
    workspace_id: str = Field(min_length=1, max_length=64)
    project_id: str = Field(pattern=r'^prj_[A-Za-z0-9_-]{4,60}$')
    project_version_id: str | None = None
    asset_class: str = Field(min_length=1, max_length=40)
    kind: str = Field(min_length=1, max_length=64)
    content_type: str = Field(min_length=1, max_length=160)
    size_bytes: int = Field(ge=0)
    checksum_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    storage_provider: str = Field(min_length=1, max_length=80)
    object_key_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class MasterBinding(Contract):
    schema_version: Literal['sql-variant-master-binding.v1'] = 'sql-variant-master-binding.v1'
    workspace_id: str = Field(min_length=1, max_length=64)
    master_project_id: str = Field(pattern=r'^prj_[A-Za-z0-9_-]{4,60}$')
    project_version: int = Field(ge=1)
    project_current_version_id: str | None
    timeline_id: str
    timeline_version_id: str
    timeline_version: int = Field(ge=1)
    timeline_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source_mode: Literal['video_analysis', 'storyboard_media', 'mixed']
    source_analysis_id: str | None
    source_content_version_id: str | None
    selected_transcript_id: str | None
    records: list[RecordProof] = Field(max_length=64)
    assets: list[AssetProof] = Field(max_length=5000)
    safety: NoAuthority = Field(default_factory=NoAuthority)

    @model_validator(mode='after')
    def source_scope(self):
        if (self.source_analysis_id is None) == (self.source_content_version_id is None):
            raise ValueError('SQL_VARIANT_MASTER_SOURCE_IDENTITY_REQUIRED')
        if (self.source_mode == 'video_analysis') != (self.source_analysis_id is not None):
            raise ValueError('SQL_VARIANT_MASTER_SOURCE_MODE_INVALID')
        if len({a.asset_id for a in self.assets}) != len(self.assets) or any(
                (a.workspace_id, a.project_id) != (self.workspace_id, self.master_project_id) for a in self.assets):
            raise ValueError('SQL_VARIANT_MASTER_ASSET_SCOPE_INVALID')
        if len({(p.table, p.owner_ref) for p in self.records}) != len(self.records):
            raise ValueError('SQL_VARIANT_MASTER_PROOF_DUPLICATE')
        if len(canonical(self.model_dump(mode='json'))) > MAX_BINDING_BYTES:
            raise ValueError('SQL_VARIANT_MASTER_BINDING_LIMIT')
        return self


class VariantAvailability(Contract):
    schema_version: Literal['sql-variant-availability.v1'] = 'sql-variant-availability.v1'
    catalog: VariantCatalog
    catalog_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    binding: MasterBinding
    binding_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    safety: NoAuthority = Field(default_factory=NoAuthority)

    @model_validator(mode='after')
    def hashes(self):
        if digest(self.catalog.model_dump(mode='json')) != self.catalog_sha256 or digest(self.binding.model_dump(mode='json')) != self.binding_sha256:
            raise ValueError('SQL_VARIANT_AVAILABILITY_HASH_INVALID')
        return self


class FamilyReserveRequest(Contract):
    schema_version: Literal['sql-variant-family-reserve.v1'] = 'sql-variant-family-reserve.v1'
    expected_project_version: int = Field(ge=1)
    expected_timeline_version: int = Field(ge=1)
    expected_timeline_version_id: str = Field(min_length=1, max_length=64)
    expected_binding_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    catalog_ref: str = Field(min_length=1, max_length=80)
    catalog_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    profile_refs: list[str] = Field(min_length=1, max_length=6)
    request_key: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{15,99}$')
    acknowledge_draft_derivation: Literal[True]

    @model_validator(mode='before')
    @classmethod
    def real_ack(cls, value):
        if isinstance(value, dict) and type(value.get('acknowledge_draft_derivation')) is not bool:
            raise ValueError('SQL_VARIANT_EXPLICIT_DRAFT_ACK_REQUIRED')
        return value

    @model_validator(mode='after')
    def targets(self):
        if len(set(self.profile_refs)) != len(self.profile_refs):
            raise ValueError('SQL_VARIANT_PROFILE_DUPLICATE')
        return self


class FamilyVersionRequest(Contract):
    expected_version: int = Field(ge=1)
    expected_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_key: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{15,99}$')


class AssetReceiptReserveRequest(FamilyVersionRequest):
    schema_version: Literal['sql-variant-asset-reserve.v1'] = 'sql-variant-asset-reserve.v1'
    member_id: str = Field(pattern=r'^vfm_[a-f0-9]{32}$')
    source_asset_id: str = Field(pattern=r'^ast_[A-Za-z0-9_-]{4,60}$')
    expected_source_record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class FamilySnapshot(Contract):
    schema_version: Literal['sql-variant-family-snapshot.v1'] = 'sql-variant-family-snapshot.v1'
    binding: MasterBinding
    binding_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    catalog: VariantCatalog
    catalog_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    request: dict
    request_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    safety: NoAuthority = Field(default_factory=NoAuthority)


class VariantProgressSafety(Contract):
    provider_calls: Literal[0] = 0
    new_inference_calls: Literal[0] = 0
    child_projects_created: int = Field(default=0, ge=0, le=6)
    source_bytes_verified: bool = False
    approval_inherited: Literal[False] = False
    rights_override_inherited: Literal[False] = False
    automatic_render: Literal[False] = False
    publishing_enabled: Literal[False] = False

    @model_validator(mode='before')
    @classmethod
    def exact_types(cls, value):
        if isinstance(value, dict):
            for key in ('provider_calls', 'new_inference_calls', 'child_projects_created'):
                if key in value and type(value[key]) is not int:
                    raise ValueError('SQL_VARIANT_SAFETY_TYPE_INVALID')
            for key in ('source_bytes_verified', 'approval_inherited', 'rights_override_inherited',
                        'automatic_render', 'publishing_enabled'):
                if key in value and type(value[key]) is not bool:
                    raise ValueError('SQL_VARIANT_SAFETY_TYPE_INVALID')
        return value


class FamilyMemberRead(Contract):
    schema_version: Literal['sql-variant-member.v1'] = 'sql-variant-member.v1'
    member_id: str
    family_id: str
    workspace_id: str
    profile: VariantProfile
    planned_project_id: str
    child_project_id: str | None = None
    state: Literal['reserved', 'deriving', 'needs_attention', 'review_required', 'cancelled', 'failed']
    safety: VariantProgressSafety = Field(default_factory=VariantProgressSafety)


class FamilyRead(Contract):
    schema_version: Literal['sql-variant-family.v1'] = 'sql-variant-family.v1'
    family_id: str
    workspace_id: str
    master_project_id: str
    version: int = Field(ge=1)
    state: Literal['reserved', 'deriving', 'review_required', 'needs_attention', 'recovery_required', 'cancelled', 'failed']
    snapshot: FamilySnapshot
    snapshot_sha256: str
    result: dict
    result_sha256: str
    source_current: bool
    source_current_reason: str | None
    members: list[FamilyMemberRead]
    actor_ref: str
    created_at: datetime
    safety: VariantProgressSafety = Field(default_factory=VariantProgressSafety)


class AssetReceiptRead(Contract):
    schema_version: Literal['sql-variant-asset-reservation.v1'] = 'sql-variant-asset-reservation.v1'
    receipt_id: str
    family_id: str
    member_id: str
    workspace_id: str
    state: Literal['reserved', 'cancelled']
    input: dict
    input_sha256: str
    request_sha256: str
    result: None = None
    claim_id: None = None
    target_asset_id: None = None
    actor_ref: str
    safety: NoAuthority = Field(default_factory=NoAuthority)


class FamilyPage(Contract):
    schema_version: Literal['sql-variant-family-page.v1'] = 'sql-variant-family-page.v1'
    items: list[FamilyRead]
    next_cursor: str | None


def as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
