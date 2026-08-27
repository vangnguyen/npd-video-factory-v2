from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .analytics_models import (
    AnalyticsPlatform,
    AnalyticsProviderStateRead,
    NormalizedMetrics,
)
from .db import utc_now


class AnalyticsProviderNotConfigured(RuntimeError):
    pass


class AnalyticsRateLimited(RuntimeError):
    def __init__(self, retry_after_seconds: int, message: str = "analytics provider rate limited"):
        self.retry_after_seconds = max(1, retry_after_seconds)
        super().__init__(message)


@dataclass(frozen=True)
class AnalyticsCollectionContext:
    platform: AnalyticsPlatform
    project_id: str
    publication_id: str
    remote_post_id: str | None
    fixture_profile: str | None


@dataclass(frozen=True)
class AnalyticsCollection:
    provider_key: str
    source: str
    source_kind: str
    collected_at: datetime
    metrics: NormalizedMetrics
    mock: bool
    external_call: bool


class AnalyticsProvider(Protocol):
    provider_key: str

    def state(self, platform: AnalyticsPlatform) -> AnalyticsProviderStateRead: ...

    async def collect(self, context: AnalyticsCollectionContext) -> AnalyticsCollection: ...


class DeterministicAnalyticsProvider:
    provider_key = "fixture-analytics-v1"

    def state(self, platform: AnalyticsPlatform) -> AnalyticsProviderStateRead:
        return AnalyticsProviderStateRead(
            platform=platform,
            provider_key=self.provider_key,
            mode="fixture",
            adapter_state="mock",
            credential_status="not_required",
            supports_sync=True,
            external_calls_enabled=False,
            real_provider_tested=False,
            production_deployed=False,
        )

    async def collect(self, context: AnalyticsCollectionContext) -> AnalyticsCollection:
        profile = context.fixture_profile or "winner_candidate"
        if profile == "rate_limited":
            raise AnalyticsRateLimited(30, "deterministic fixture requested a rate-limit response")
        profiles = {
            "winner_candidate": NormalizedMetrics(
                views=120_000,
                impressions=180_000,
                reach=132_000,
                watch_time=4_800_000,
                average_view_duration=40,
                completion_rate=0.82,
                likes=9_500,
                comments=1_200,
                shares=5_100,
                saves=4_300,
                followers_gained=2_100,
                clicks=8_200,
                ctr=0.045,
                revenue=12_000_000,
                rpm=100_000,
                observation_window_hours=24,
            ),
            "normal": NormalizedMetrics(
                views=18_000,
                impressions=42_000,
                reach=31_000,
                watch_time=450_000,
                average_view_duration=25,
                completion_rate=0.51,
                likes=760,
                comments=95,
                shares=130,
                saves=180,
                followers_gained=120,
                clicks=750,
                ctr=0.018,
                revenue=None,
                rpm=None,
                observation_window_hours=24,
            ),
            "underperforming": NormalizedMetrics(
                views=1_200,
                impressions=19_000,
                reach=14_000,
                watch_time=12_000,
                average_view_duration=10,
                completion_rate=0.17,
                likes=22,
                comments=2,
                shares=1,
                saves=3,
                followers_gained=1,
                clicks=70,
                ctr=0.0037,
                revenue=None,
                rpm=None,
                observation_window_hours=24,
            ),
            "insufficient_data": NormalizedMetrics(
                views=80,
                impressions=None,
                reach=None,
                watch_time=None,
                average_view_duration=None,
                completion_rate=None,
                likes=4,
                comments=None,
                shares=None,
                saves=None,
                followers_gained=None,
                clicks=None,
                ctr=None,
                revenue=None,
                rpm=None,
                observation_window_hours=1,
            ),
        }
        if profile not in profiles:
            raise ValueError(f"unknown deterministic analytics fixture profile: {profile}")
        return AnalyticsCollection(
            provider_key=self.provider_key,
            source=f"fixture://analytics/{context.platform}/{profile}",
            source_kind="fixture",
            collected_at=utc_now(),
            metrics=profiles[profile],
            mock=True,
            external_call=False,
        )


class OfficialAnalyticsProvider:
    def __init__(self, *, platform: AnalyticsPlatform, provider_key: str, credential_ref: str):
        self.platform = platform
        self.provider_key = provider_key
        self._credential_configured = bool(credential_ref)

    def state(self, platform: AnalyticsPlatform) -> AnalyticsProviderStateRead:
        if platform != self.platform:
            raise ValueError(f"provider {self.provider_key} does not support {platform}")
        return AnalyticsProviderStateRead(
            platform=platform,
            provider_key=self.provider_key,
            mode="official",
            adapter_state="contract_only" if self._credential_configured else "not_configured",
            credential_status="configured" if self._credential_configured else "not_configured",
            supports_sync=False,
            external_calls_enabled=False,
            real_provider_tested=False,
            production_deployed=False,
        )

    async def collect(self, context: AnalyticsCollectionContext) -> AnalyticsCollection:
        del context
        raise AnalyticsProviderNotConfigured(
            f"{self.provider_key} is contract-only; official analytics collection is not activated in V2-10"
        )


class AnalyticsProviderRegistry:
    OFFICIAL_KEYS: dict[str, str] = {
        "youtube": "youtube-analytics-api",
        "tiktok": "tiktok-video-insights-api",
        "instagram_reels": "instagram-graph-insights-api",
        "facebook": "facebook-graph-video-insights-api",
    }

    def __init__(self, settings):
        self.fixture = DeterministicAnalyticsProvider()
        credential_refs = {
            "youtube": settings.youtube_analytics_credential_ref,
            "tiktok": settings.tiktok_analytics_credential_ref,
            "instagram_reels": settings.instagram_analytics_credential_ref,
            "facebook": settings.facebook_analytics_credential_ref,
        }
        self.official = {
            platform: OfficialAnalyticsProvider(
                platform=platform,  # type: ignore[arg-type]
                provider_key=provider_key,
                credential_ref=credential_refs[platform],
            )
            for platform, provider_key in self.OFFICIAL_KEYS.items()
        }

    def get(self, *, platform: AnalyticsPlatform, mode: str) -> AnalyticsProvider:
        if mode == "fixture":
            return self.fixture
        if mode == "official":
            return self.official[platform]
        raise KeyError(mode)

    def states(self) -> list[AnalyticsProviderStateRead]:
        output: list[AnalyticsProviderStateRead] = []
        for platform in self.OFFICIAL_KEYS:
            output.append(self.fixture.state(platform))  # type: ignore[arg-type]
            output.append(self.official[platform].state(platform))  # type: ignore[arg-type]
        return output
