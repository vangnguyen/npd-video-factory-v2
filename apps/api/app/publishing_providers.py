from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .publishing_logic import validation_check
from .publishing_models import (
    ProviderValidationRead,
    PublicationMetadata,
    PublicationReceipt,
    PublishingPlatform,
)


class PublishingProviderError(RuntimeError):
    pass


class ExternalPublishingNotActivated(PublishingProviderError):
    pass


@dataclass(frozen=True)
class PublishingContext:
    platform: PublishingPlatform
    project_id: str
    final_render_id: str
    output_asset_id: str
    request_fingerprint: str
    metadata: PublicationMetadata


class PublishingProvider(Protocol):
    provider_key: str
    platform: PublishingPlatform | None

    def validate(self) -> ProviderValidationRead: ...

    async def publish(self, context: PublishingContext) -> PublicationReceipt: ...

    async def get_status(self, receipt: PublicationReceipt) -> str: ...

    async def delete_or_cancel_if_supported(self, receipt: PublicationReceipt) -> bool: ...


class MockPublishingProvider:
    provider_key = "mock-publishing"
    platform = None

    def validate(self) -> ProviderValidationRead:
        return ProviderValidationRead(
            provider_key=self.provider_key,
            adapter_state="mock",
            credential_status="not_required",
            supports_dry_run=True,
            supports_live_publish=False,
            checks=[
                validation_check(
                    "external-action",
                    True,
                    "DRY_RUN_NO_EXTERNAL_ACTION",
                    "Deterministic dry-run provider performs no external action.",
                    external_action=False,
                )
            ],
        )

    async def publish(self, context: PublishingContext) -> PublicationReceipt:
        digest = hashlib.sha256(
            f"{context.platform}:{context.project_id}:{context.final_render_id}:{context.request_fingerprint}".encode(
                "utf-8"
            )
        ).hexdigest()
        return PublicationReceipt(
            receipt_id=f"rcpt_{digest[:24]}",
            provider_key=self.provider_key,
            platform=context.platform,
            mode="dry_run",
            request_fingerprint=context.request_fingerprint,
            mock=True,
            external_action=False,
            created_at=datetime.now(timezone.utc),
        )

    async def get_status(self, receipt: PublicationReceipt) -> str:
        return "dry_run_succeeded" if receipt.mock and not receipt.external_action else "invalid"

    async def delete_or_cancel_if_supported(self, receipt: PublicationReceipt) -> bool:
        del receipt
        return False


class OfficialPublishingProvider:
    """Official-API adapter boundary.

    V2-09 deliberately contains no vendor SDK or outbound HTTP call. Credential
    references point to an external secret store, and the adapter stays
    contract-only until a later owner-gated integration supplies an authorized
    implementation and current platform acceptance evidence.
    """

    def __init__(
        self,
        *,
        platform: PublishingPlatform,
        provider_key: str,
        credential_ref: str,
        publish_enabled: bool,
        external_execution_enabled: bool,
        owner_gate_enabled: bool,
    ):
        self.platform = platform
        self.provider_key = provider_key
        self._credential_configured = bool(credential_ref.strip())
        self._publish_enabled = publish_enabled
        self._external_execution_enabled = external_execution_enabled
        self._owner_gate_enabled = owner_gate_enabled

    def validate(self) -> ProviderValidationRead:
        checks = [
            validation_check(
                "credential-reference",
                self._credential_configured,
                "CREDENTIAL_REFERENCE_CONFIGURED"
                if self._credential_configured
                else "CREDENTIAL_REFERENCE_NOT_CONFIGURED",
                "An external secret-store credential reference is configured."
                if self._credential_configured
                else "No external credential reference is configured.",
            ),
            validation_check(
                "publish-enabled",
                self._publish_enabled,
                "PUBLISH_OWNER_ENABLED" if self._publish_enabled else "PUBLISH_DISABLED",
                "Publishing is enabled by configuration."
                if self._publish_enabled
                else "PUBLISH_ENABLED is false.",
            ),
            validation_check(
                "external-execution",
                self._external_execution_enabled,
                "EXTERNAL_EXECUTION_ENABLED"
                if self._external_execution_enabled
                else "EXTERNAL_EXECUTION_DISABLED",
                "External execution is enabled."
                if self._external_execution_enabled
                else "External publishing execution is disabled.",
            ),
            validation_check(
                "owner-gate",
                self._owner_gate_enabled,
                "OWNER_GATE_ENABLED" if self._owner_gate_enabled else "OWNER_GATE_DISABLED",
                "Owner live-publishing gate is enabled."
                if self._owner_gate_enabled
                else "Owner live-publishing gate is disabled.",
            ),
            validation_check(
                "adapter-activation",
                False,
                "OFFICIAL_ADAPTER_CONTRACT_ONLY",
                "Official adapter architecture exists, but outbound execution is not activated in V2-09.",
            ),
        ]
        return ProviderValidationRead(
            provider_key=self.provider_key,
            adapter_state="contract_only" if self._credential_configured else "not_configured",
            credential_status="configured" if self._credential_configured else "not_configured",
            supports_dry_run=False,
            supports_live_publish=False,
            checks=checks,
        )

    async def publish(self, context: PublishingContext) -> PublicationReceipt:
        del context
        raise ExternalPublishingNotActivated(
            f"{self.provider_key} is contract-only; live external publishing is not activated in V2-09"
        )

    async def get_status(self, receipt: PublicationReceipt) -> str:
        del receipt
        raise ExternalPublishingNotActivated("official publication status lookup is not activated")

    async def delete_or_cancel_if_supported(self, receipt: PublicationReceipt) -> bool:
        del receipt
        raise ExternalPublishingNotActivated("official cancellation is not activated")


class PublishingProviderRegistry:
    PROVIDER_KEYS = {
        "youtube": "youtube-data-api-publishing",
        "tiktok": "tiktok-content-posting-api",
        "instagram_reels": "instagram-graph-api-publishing",
        "facebook": "facebook-graph-api-publishing",
    }

    def __init__(self, settings):
        self.mock = MockPublishingProvider()
        credential_refs = {
            "youtube": settings.youtube_publishing_credential_ref,
            "tiktok": settings.tiktok_publishing_credential_ref,
            "instagram_reels": settings.instagram_publishing_credential_ref,
            "facebook": settings.facebook_publishing_credential_ref,
        }
        self.official = {
            platform: OfficialPublishingProvider(
                platform=platform,
                provider_key=self.PROVIDER_KEYS[platform],
                credential_ref=credential_refs[platform],
                publish_enabled=settings.publish_enabled,
                external_execution_enabled=settings.publish_external_execution_enabled,
                owner_gate_enabled=settings.publish_owner_gate_enabled,
            )
            for platform in self.PROVIDER_KEYS
        }

    def for_dry_run(self) -> MockPublishingProvider:
        return self.mock

    def for_live(self, platform: PublishingPlatform) -> OfficialPublishingProvider:
        return self.official[platform]

    def official_status(self, platform: PublishingPlatform) -> ProviderValidationRead:
        return self.official[platform].validate()
