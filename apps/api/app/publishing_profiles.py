"""Versioned public publishing configuration; OAuth/keys live outside the catalog."""
import hashlib
import json
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .publishing_models import PublishingTargetBinding
from .publishing_operations import OPERATIONS, amount

PROVIDER_KEYS = {'youtube': 'youtube-data-api-publishing', 'tiktok': 'tiktok-content-posting-api',
    'instagram_reels': 'instagram-graph-api-publishing', 'facebook': 'facebook-graph-api-publishing'}


class PublishingProfileError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class PublishingProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    schema_version: Literal['publishing-profile-v1'] = 'publishing-profile-v1'
    target: PublishingTargetBinding
    category_id: str | None = Field(default=None, pattern=r'^[0-9]{1,4}$')
    made_for_kids: bool | None = None
    contains_synthetic_media: bool | None = None
    max_ai_cost: Decimal | None = None
    estimated_costs: dict[str, Decimal] = Field(default_factory=dict, max_length=6)

    @model_validator(mode='after')
    def validate_configuration(self):
        if self.target.provider_key != PROVIDER_KEYS[self.target.platform]:
            raise ValueError('official provider key must match the target platform')
        if not set(self.estimated_costs) <= OPERATIONS:
            raise ValueError('unknown publishing cost operation')
        try:
            amount(self.max_ai_cost)
            for value in self.estimated_costs.values(): amount(value)
        except Exception:
            raise ValueError('cost values must be finite nonnegative exact four-place amounts') from None
        return self

    def youtube_ready(self):
        return self.target.platform == 'youtube' and self.category_id is not None and type(self.made_for_kids) is bool and type(self.contains_synthetic_media) is bool

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.model_dump(mode='json'), ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class PublishingProfileCatalog(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    schema_version: Literal['publishing-profile-catalog-v1'] = 'publishing-profile-catalog-v1'
    profiles: list[PublishingProfile] = Field(max_length=1024)

    @model_validator(mode='after')
    def unique_versions(self):
        seen = set()
        for profile in self.profiles:
            key = (profile.target.workspace_id, profile.target.profile_id, profile.target.profile_version)
            if key in seen: raise ValueError('duplicate profile version')
            seen.add(key)
        return self


class PublishingProfileRegistry:
    def __init__(self, catalog):
        try:
            value = PublishingProfileCatalog.model_validate(catalog.model_dump(warnings=False))
        except Exception:
            raise PublishingProfileError('PUBLISH_PROFILE_CATALOG_INVALID') from None
        self._versions = {(p.target.workspace_id, p.target.profile_id, p.target.profile_version):
            json.dumps(p.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',', ':')) for p in value.profiles}

    @classmethod
    def from_json(cls, data):
        if not isinstance(data, (str, bytes)) or len(data.encode('utf-8') if isinstance(data, str) else data) > 262144:
            raise PublishingProfileError('PUBLISH_PROFILE_CATALOG_INVALID')
        try: return cls(PublishingProfileCatalog.model_validate_json(data))
        except Exception: raise PublishingProfileError('PUBLISH_PROFILE_CATALOG_INVALID') from None

    def resolve(self, workspace, profile_id):
        keys = [key for key in self._versions if key[:2] == (workspace, profile_id)]
        if not keys: raise PublishingProfileError('PUBLISH_PROFILE_SCOPE_NOT_FOUND')
        return PublishingProfile.model_validate_json(self._versions[max(keys, key=lambda key: key[2])])

    def select(self, workspace, platform, profile_id=None):
        identifiers = {key[1] for key in self._versions if key[0] == workspace}
        selected = [self.resolve(workspace, identifier) for identifier in identifiers]
        selected = [p for p in selected if p.target.platform == platform and (profile_id is None or p.target.profile_id == profile_id)]
        if len(selected) != 1:
            raise PublishingProfileError('PUBLISH_PROFILE_SELECTION_REQUIRED')
        return selected[0]

    def target(self, workspace, profile_id):
        return self.resolve(workspace, profile_id).target

    def has_platform(self, platform, *, require_youtube_ready=False):
        return any(self.resolve(workspace, identifier).target.platform == platform
            and (not require_youtube_ready or self.resolve(workspace, identifier).youtube_ready())
            for workspace, identifier in {(key[0], key[1]) for key in self._versions})

    def replace_catalog(self, catalog):
        replacement = type(self)(catalog)
        for key, value in self._versions.items():
            if replacement._versions.get(key) != value:
                raise PublishingProfileError('PUBLISH_PROFILE_HISTORY_IMMUTABLE')
        self._versions = replacement._versions  # additive revisions only
