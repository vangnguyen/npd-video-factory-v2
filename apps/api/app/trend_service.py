from __future__ import annotations

import math
import re
import unicodedata

from .platform_models import ProjectCreate, ProjectVersionCreate
from .repositories import PlatformRepository
from .trend_models import (
    ContentQueueItemRead,
    ContentQueueRefreshRequest,
    IdeaCandidateRead,
    IdeaGenerateRequest,
    IdeaProjectRead,
    TrendClusterRead,
    TrendClusterRefreshRequest,
    TrendCollectionRequest,
    TrendCollectionResult,
    TrendSignalRead,
    TrendSourceRead,
)
from .trend_providers import TrendProviderRegistry
from .trend_repository import TrendRepository
from .trend_scoring import IdeaEngine


def _project_slug(title: str, idea_id: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    stem = re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")[:56] or "trend-idea"
    suffix = idea_id.removeprefix("idea_")[:12].lower()
    return f"{stem}-{suffix}"[:80].rstrip("-")


class TrendIntelligenceService:
    def __init__(
        self,
        repository: TrendRepository,
        providers: TrendProviderRegistry,
        platform: PlatformRepository,
        *,
        idea_engine: IdeaEngine | None = None,
    ) -> None:
        self.repository = repository
        self.providers = providers
        self.platform = platform
        self.idea_engine = idea_engine or IdeaEngine()

    async def list_sources(self) -> list[TrendSourceRead]:
        return await self.repository.list_sources()

    async def collect(
        self,
        workspace_id: str,
        request: TrendCollectionRequest,
    ) -> TrendCollectionResult:
        provider = self.providers.get(request.provider_key)
        signals = await provider.collect_signals(request)
        return await self.repository.record_collection(
            workspace_id=workspace_id,
            request=request,
            signals=signals,
        )

    async def list_signals(self, workspace_id: str) -> list[TrendSignalRead]:
        return await self.repository.list_signals(workspace_id)

    async def refresh_clusters(
        self,
        workspace_id: str,
        request: TrendClusterRefreshRequest,
    ) -> list[TrendClusterRead]:
        return await self.repository.refresh_clusters(workspace_id, request)

    async def list_clusters(self, workspace_id: str) -> list[TrendClusterRead]:
        return await self.repository.list_clusters(workspace_id)

    async def get_cluster(self, cluster_id: str) -> TrendClusterRead | None:
        return await self.repository.get_cluster(cluster_id)

    async def generate_ideas(
        self,
        cluster_id: str,
        request: IdeaGenerateRequest,
    ) -> list[IdeaCandidateRead]:
        return await self.repository.generate_ideas(
            cluster_id,
            request,
            engine=self.idea_engine,
        )

    async def list_ideas(self, workspace_id: str) -> list[IdeaCandidateRead]:
        return await self.repository.list_ideas(workspace_id)

    async def refresh_queue(
        self,
        workspace_id: str,
        request: ContentQueueRefreshRequest,
    ) -> list[ContentQueueItemRead]:
        cluster_request = TrendClusterRefreshRequest(
            channel=request.channel,
            niche=request.niche,
            business_objective=request.business_objective,
            weights=request.weights,
        )
        clusters = await self.repository.refresh_clusters(workspace_id, cluster_request)
        cluster_limit = max(1, math.ceil(request.top_n / request.ideas_per_cluster))
        idea_request = IdeaGenerateRequest(
            channel=request.channel,
            niche=request.niche,
            business_objective=request.business_objective,
            weights=request.weights,
            audience=request.audience,
            cta=request.cta,
            budget_vnd=request.budget_vnd,
            count=request.ideas_per_cluster,
        )
        for cluster in clusters[:cluster_limit]:
            await self.repository.generate_ideas(
                cluster.cluster_id,
                idea_request,
                engine=self.idea_engine,
            )
        return await self.repository.refresh_queue(workspace_id, request)

    async def list_queue(self, workspace_id: str) -> list[ContentQueueItemRead]:
        return await self.repository.list_queue(workspace_id)

    async def create_draft_project(self, idea_id: str) -> IdeaProjectRead:
        idea = await self.repository.get_idea(idea_id)
        if idea is None:
            raise KeyError(idea_id)
        project = await self.platform.ensure_project(
            idea.workspace_id,
            ProjectCreate(
                slug=_project_slug(idea.title, idea.idea_id),
                name=idea.title,
                niche=idea.niche,
                provenance={
                    "source": "trend-idea-selection",
                    "idea_id": idea.idea_id,
                    "cluster_id": idea.cluster_id,
                    "execution": False,
                },
            ),
        )
        version = await self.platform.ensure_initial_version(
            project.project_id,
            snapshot={
                "status": "draft",
                "source_idea": idea.model_dump(mode="json"),
                "approval": {
                    "human_required": True,
                    "approved": False,
                    "publish_enabled": False,
                },
                "source_reference_policy": {
                    "reference_only": True,
                    "creator_media_copied": False,
                },
            },
        )
        linked = await self.repository.link_idea_project(idea_id, project.project_id)
        return IdeaProjectRead(
            idea_id=linked.idea_id,
            project_id=project.project_id,
            project_version_id=version.project_version_id,
            status="selected",
        )
