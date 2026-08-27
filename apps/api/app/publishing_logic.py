from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .publishing_models import (
    PlatformCapabilityRead,
    PlatformValidationRead,
    PublicationCreateRequest,
    PublicationMetadata,
    PublishingPlatform,
    PublishingValidationCheck,
    RightsValidationRead,
)


RIGHTS_POLICY_VERSION = "v2-09-rights-fail-closed-v1"
ALLOWED_RIGHTS = {"owned", "licensed", "public_domain", "royalty_free", "verified"}


class PublishingContractError(ValueError):
    pass


def hash_idempotency_key(value: str) -> str:
    if len(value) < 16 or len(value) > 200:
        raise PublishingContractError("Idempotency-Key must contain 16 to 200 characters")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def request_fingerprint(payload: PublicationCreateRequest) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PublishingCapabilityRegistry:
    def __init__(self, path: Path):
        self.path = path
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PublishingContractError("publishing capability registry is unavailable or invalid") from exc
        if raw.get("schema_version") != "1.0" or not isinstance(raw.get("platforms"), dict):
            raise PublishingContractError("publishing capability registry has an unsupported schema")
        self.policy = str(raw.get("policy") or "unknown")
        self._platforms = {
            key: PlatformCapabilityRead(platform=key, **value)
            for key, value in raw["platforms"].items()
        }

    def get(self, platform: PublishingPlatform) -> PlatformCapabilityRead:
        try:
            return self._platforms[platform]
        except KeyError as exc:
            raise PublishingContractError(f"publishing platform is not configured: {platform}") from exc

    def list(self) -> list[PlatformCapabilityRead]:
        return [self._platforms[key] for key in sorted(self._platforms)]


def validation_check(
    key: str,
    passed: bool,
    code: str,
    message: str,
    **evidence: Any,
) -> PublishingValidationCheck:
    return PublishingValidationCheck(
        key=key,
        passed=passed,
        code=code,
        message=message,
        evidence=evidence,
    )


def validate_rights(assets: Iterable[Any]) -> RightsValidationRead:
    checks: list[PublishingValidationCheck] = []
    asset_ids: list[str] = []
    for asset in assets:
        asset_id = str(asset.asset_id)
        if asset_id in asset_ids:
            continue
        asset_ids.append(asset_id)
        provenance = dict(getattr(asset, "provenance", {}) or {})
        rights_status = str(provenance.get("rights_status") or "unknown").lower()
        production_eligible = provenance.get("production_eligible") is not False
        license_present = bool(provenance.get("license"))
        rights_allowed = rights_status in ALLOWED_RIGHTS
        licensed_evidence_ok = rights_status != "licensed" or license_present
        passed = rights_allowed and production_eligible and licensed_evidence_ok
        checks.append(
            validation_check(
                f"asset:{asset_id}",
                passed,
                "RIGHTS_VERIFIED" if passed else "RIGHTS_NOT_VERIFIED",
                "Asset rights evidence is sufficient."
                if passed
                else "Asset has unknown, incomplete or non-production rights evidence.",
                asset_id=asset_id,
                rights_status=rights_status,
                license_present=license_present,
                production_eligible=production_eligible,
            )
        )
    if not asset_ids:
        checks.append(
            validation_check(
                "asset-set",
                False,
                "RIGHTS_ASSET_SET_EMPTY",
                "No source assets were available for rights validation.",
            )
        )
    passed = bool(checks) and all(item.passed for item in checks)
    return RightsValidationRead(
        status="passed" if passed else "failed",
        policy_version=RIGHTS_POLICY_VERSION,
        asset_ids=asset_ids,
        checks=checks,
    )


def validate_platform(
    *,
    capability: PlatformCapabilityRead,
    metadata: PublicationMetadata,
    render: Any,
    output_asset: Any,
    mode: str,
) -> PlatformValidationRead:
    qc = dict(render.qc_report or {})
    duration = float(qc.get("duration_seconds") or 0)
    width = int(qc.get("width") or 0)
    height = int(qc.get("height") or 0)
    video_codec = str(qc.get("video_codec") or "").lower()
    audio_codec = str(qc.get("audio_codec") or "").lower()
    caption = metadata.caption or metadata.description
    checks = [
        validation_check(
            "render-profile",
            render.profile in capability.supported_profiles,
            "PROFILE_SUPPORTED" if render.profile in capability.supported_profiles else "PROFILE_UNSUPPORTED",
            "Final render profile is supported by the versioned platform contract."
            if render.profile in capability.supported_profiles
            else "Final render profile is outside the versioned platform contract.",
            profile=render.profile,
        ),
        validation_check(
            "duration",
            capability.min_duration_seconds <= duration <= capability.max_duration_seconds,
            "DURATION_SUPPORTED"
            if capability.min_duration_seconds <= duration <= capability.max_duration_seconds
            else "DURATION_UNSUPPORTED",
            "Duration is within the configured platform range."
            if capability.min_duration_seconds <= duration <= capability.max_duration_seconds
            else "Duration is outside the configured platform range.",
            duration_seconds=duration,
        ),
        validation_check(
            "resolution",
            width > 0 and height > 0,
            "RESOLUTION_PRESENT" if width > 0 and height > 0 else "RESOLUTION_MISSING",
            "QC contains a positive output resolution."
            if width > 0 and height > 0
            else "QC does not contain a valid output resolution.",
            width=width,
            height=height,
        ),
        validation_check(
            "file-size",
            0 < int(output_asset.size_bytes) <= capability.max_file_size_bytes,
            "FILE_SIZE_SUPPORTED"
            if 0 < int(output_asset.size_bytes) <= capability.max_file_size_bytes
            else "FILE_SIZE_UNSUPPORTED",
            "Output size is within the configured platform ceiling."
            if 0 < int(output_asset.size_bytes) <= capability.max_file_size_bytes
            else "Output size is missing or exceeds the configured platform ceiling.",
            size_bytes=int(output_asset.size_bytes),
        ),
        validation_check(
            "video-codec",
            video_codec in capability.video_codecs,
            "VIDEO_CODEC_SUPPORTED" if video_codec in capability.video_codecs else "VIDEO_CODEC_UNSUPPORTED",
            "Video codec is supported." if video_codec in capability.video_codecs else "Video codec is unsupported.",
            codec=video_codec,
        ),
        validation_check(
            "audio-codec",
            audio_codec in capability.audio_codecs,
            "AUDIO_CODEC_SUPPORTED" if audio_codec in capability.audio_codecs else "AUDIO_CODEC_UNSUPPORTED",
            "Audio codec is supported." if audio_codec in capability.audio_codecs else "Audio codec is unsupported.",
            codec=audio_codec,
        ),
        validation_check(
            "title-length",
            len(metadata.title) <= capability.max_title_characters,
            "TITLE_SUPPORTED" if len(metadata.title) <= capability.max_title_characters else "TITLE_TOO_LONG",
            "Title length is supported."
            if len(metadata.title) <= capability.max_title_characters
            else "Title exceeds the configured platform limit.",
            characters=len(metadata.title),
        ),
        validation_check(
            "caption-length",
            len(caption) <= capability.max_caption_characters,
            "CAPTION_SUPPORTED"
            if len(caption) <= capability.max_caption_characters
            else "CAPTION_TOO_LONG",
            "Caption length is supported."
            if len(caption) <= capability.max_caption_characters
            else "Caption exceeds the configured platform limit.",
            characters=len(caption),
        ),
        validation_check(
            "hashtag-count",
            len(metadata.hashtags) <= capability.max_hashtags,
            "HASHTAGS_SUPPORTED"
            if len(metadata.hashtags) <= capability.max_hashtags
            else "TOO_MANY_HASHTAGS",
            "Hashtag count is supported."
            if len(metadata.hashtags) <= capability.max_hashtags
            else "Hashtag count exceeds the configured platform limit.",
            count=len(metadata.hashtags),
        ),
        validation_check(
            "thumbnail",
            capability.thumbnail != "required" or bool(metadata.thumbnail_asset_id),
            "THUMBNAIL_SUPPORTED"
            if capability.thumbnail != "required" or bool(metadata.thumbnail_asset_id)
            else "THUMBNAIL_REQUIRED",
            "Thumbnail requirement is satisfied."
            if capability.thumbnail != "required" or bool(metadata.thumbnail_asset_id)
            else "This platform contract requires a thumbnail.",
            policy=capability.thumbnail,
        ),
        validation_check(
            "capability-live-verification",
            mode != "live" or capability.verification_state == "owner_verified_for_live",
            "CAPABILITY_DRY_RUN_ONLY"
            if mode != "live" or capability.verification_state == "owner_verified_for_live"
            else "CAPABILITY_NOT_VERIFIED_FOR_LIVE",
            "Capability snapshot is permitted for this execution mode."
            if mode != "live" or capability.verification_state == "owner_verified_for_live"
            else "Owner must verify current official platform limits before live activation.",
            verification_state=capability.verification_state,
        ),
    ]
    passed = all(item.passed for item in checks)
    return PlatformValidationRead(
        status="passed" if passed else "failed",
        capability=capability,
        checks=checks,
    )
