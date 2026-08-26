from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .trend_models import ProviderTrendSignal, TrendCollectionRequest


class TrendProviderError(RuntimeError):
    pass


class TrendProviderNotConfigured(TrendProviderError):
    pass


class TrendSourceProvider(ABC):
    provider_key: str
    display_name: str
    source_type: str
    status: str
    authorized_access: bool
    config_ref: str | None

    @abstractmethod
    async def collect_signals(self, request: TrendCollectionRequest) -> list[ProviderTrendSignal]:
        raise NotImplementedError

    @abstractmethod
    async def search_topic(self, topic: str, request: TrendCollectionRequest) -> list[ProviderTrendSignal]:
        raise NotImplementedError

    @abstractmethod
    async def get_topic_metrics(self, topic: str) -> dict[str, float | int | None]:
        raise NotImplementedError

    @abstractmethod
    async def get_content_reference(self, source_reference: str) -> dict[str, Any]:
        raise NotImplementedError

    def registry_definition(self) -> dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "display_name": self.display_name,
            "source_type": self.source_type,
            "status": self.status,
            "authorized_access": self.authorized_access,
            "config_ref": self.config_ref,
            "capabilities": {
                "collect_signals": True,
                "search_topic": True,
                "get_topic_metrics": True,
                "get_content_reference": True,
                "downloads_creator_media": False,
                "fixture": self.source_type == "fixture",
            },
        }


class FixtureTrendSourceProvider(TrendSourceProvider):
    provider_key = "fixture-trends"
    display_name = "Deterministic Trend Fixtures"
    source_type = "fixture"
    status = "healthy"
    authorized_access = True
    config_ref = "bundled:app/fixtures/trend-signals.json"

    def __init__(self, fixture_path: Path, *, enabled: bool = True):
        self.fixture_path = fixture_path
        self.status = "healthy" if enabled else "not_configured"
        self.authorized_access = enabled
        self._adapter = TypeAdapter(list[ProviderTrendSignal])

    def _load(self) -> list[ProviderTrendSignal]:
        if self.status == "not_configured":
            raise TrendProviderNotConfigured("deterministic trend fixtures are disabled")
        if not self.fixture_path.is_file():
            raise TrendProviderNotConfigured("trend fixture file is unavailable")
        return self._adapter.validate_json(self.fixture_path.read_text(encoding="utf-8"))

    @staticmethod
    def _matches(signal: ProviderTrendSignal, request: TrendCollectionRequest) -> bool:
        if request.country and signal.country != request.country:
            return False
        if request.locale and signal.locale != request.locale:
            return False
        if request.language and signal.language != request.language:
            return False
        if request.query:
            haystack = " ".join(
                [signal.topic or "", signal.keyword or "", *signal.hashtags]
            ).casefold()
            if request.query.casefold() not in haystack:
                return False
        return True

    async def collect_signals(self, request: TrendCollectionRequest) -> list[ProviderTrendSignal]:
        matching = [signal for signal in self._load() if self._matches(signal, request)]
        return matching[: request.limit]

    async def search_topic(self, topic: str, request: TrendCollectionRequest) -> list[ProviderTrendSignal]:
        scoped = request.model_copy(update={"query": topic})
        return await self.collect_signals(scoped)

    async def get_topic_metrics(self, topic: str) -> dict[str, float | int | None]:
        signals = await self.search_topic(topic, TrendCollectionRequest())
        if not signals:
            return {"signal_count": 0, "views": None, "velocity": None, "acceleration": None}

        def optional_sum(field: str) -> int | None:
            values = [getattr(item, field) for item in signals if getattr(item, field) is not None]
            return sum(values) if values else None

        def optional_average(field: str) -> float | None:
            values = [float(getattr(item, field)) for item in signals if getattr(item, field) is not None]
            return round(sum(values) / len(values), 4) if values else None

        return {
            "signal_count": len(signals),
            "views": optional_sum("views"),
            "velocity": optional_average("velocity"),
            "acceleration": optional_average("acceleration"),
        }

    async def get_content_reference(self, source_reference: str) -> dict[str, Any]:
        signal = next(
            (item for item in self._load() if str(item.source_reference) == source_reference),
            None,
        )
        if signal is None:
            raise KeyError(source_reference)
        return {
            "source": signal.source,
            "source_reference": str(signal.source_reference),
            "topic": signal.topic,
            "reference_only": True,
            "download_allowed": False,
        }


class ContractOnlyTrendSourceProvider(TrendSourceProvider):
    status = "not_configured"
    authorized_access = False

    def __init__(
        self,
        *,
        provider_key: str,
        display_name: str,
        source_type: str,
        config_ref: str,
    ) -> None:
        self.provider_key = provider_key
        self.display_name = display_name
        self.source_type = source_type
        self.config_ref = config_ref

    async def collect_signals(self, request: TrendCollectionRequest) -> list[ProviderTrendSignal]:
        raise TrendProviderNotConfigured(self.provider_key)

    async def search_topic(self, topic: str, request: TrendCollectionRequest) -> list[ProviderTrendSignal]:
        raise TrendProviderNotConfigured(self.provider_key)

    async def get_topic_metrics(self, topic: str) -> dict[str, float | int | None]:
        raise TrendProviderNotConfigured(self.provider_key)

    async def get_content_reference(self, source_reference: str) -> dict[str, Any]:
        raise TrendProviderNotConfigured(self.provider_key)


class TrendProviderRegistry:
    def __init__(self, providers: list[TrendSourceProvider]):
        self._providers = {provider.provider_key: provider for provider in providers}

    def get(self, provider_key: str) -> TrendSourceProvider:
        provider = self._providers.get(provider_key)
        if provider is None:
            raise KeyError(provider_key)
        if provider.status == "not_configured":
            raise TrendProviderNotConfigured(provider_key)
        return provider

    def definitions(self) -> list[dict[str, Any]]:
        return [provider.registry_definition() for provider in self._providers.values()]


def create_trend_provider_registry(
    fixture_path: Path,
    *,
    fixture_enabled: bool = True,
) -> TrendProviderRegistry:
    return TrendProviderRegistry(
        [
            FixtureTrendSourceProvider(fixture_path, enabled=fixture_enabled),
            ContractOnlyTrendSourceProvider(
                provider_key="youtube-data-api",
                display_name="YouTube Data API",
                source_type="youtube",
                config_ref="env:YOUTUBE_DATA_API_*",
            ),
            ContractOnlyTrendSourceProvider(
                provider_key="tiktok-authorized-api",
                display_name="TikTok Authorized Research API",
                source_type="tiktok",
                config_ref="env:TIKTOK_RESEARCH_API_*",
            ),
            ContractOnlyTrendSourceProvider(
                provider_key="google-trends-authorized",
                display_name="Google Trends Authorized Provider",
                source_type="google_trends",
                config_ref="env:GOOGLE_TRENDS_PROVIDER_*",
            ),
            ContractOnlyTrendSourceProvider(
                provider_key="meta-content-library",
                display_name="Meta Content Library API",
                source_type="meta",
                config_ref="env:META_CONTENT_LIBRARY_*",
            ),
            ContractOnlyTrendSourceProvider(
                provider_key="public-rss",
                display_name="Public RSS/News Feeds",
                source_type="rss",
                config_ref="file:TREND_RSS_ALLOWLIST_FILE",
            ),
        ]
    )
