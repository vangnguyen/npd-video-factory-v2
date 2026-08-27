from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .auto_edit_db import AutoEditAnalysisORM
from .auto_edit_models import AutoEditAnalysisRead
from .db import utc_now
from .media_intelligence_db import (
    MediaAssetProvenanceORM,
    MediaPlanItemORM,
    MediaPlanORM,
    MediaResolutionJobORM,
)
from .media_intelligence_models import (
    BrollDecisionRead,
    MediaAssetProvenanceRead,
    MediaPlanItemRead,
    MediaPlanRead,
    MediaPlanRequest,
    MediaResolutionJobRead,
    StockMediaCandidateRead,
)
from .platform_models import AssetRead
from .vision_db import VisionAnalysisORM
from .vision_models import VisionAnalysisRead


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


class MediaIntelligenceRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def create_plan(
        self,
        *,
        analysis: AutoEditAnalysisRead,
        vision: VisionAnalysisRead | None,
        fingerprint: str,
        configuration: MediaPlanRequest,
        provider_status: dict[str, Any],
        provenance: dict[str, Any],
    ) -> tuple[str, bool]:
        async with self.session_factory() as session:
            base = await session.get(AutoEditAnalysisORM, analysis.analysis_id)
            if base is None or base.project_id != analysis.project_id or base.status != "succeeded":
                raise KeyError(analysis.analysis_id)
            if vision is not None:
                vision_row = await session.get(VisionAnalysisORM, vision.vision_analysis_id)
                if (
                    vision_row is None
                    or vision_row.project_id != analysis.project_id
                    or vision_row.analysis_id != analysis.analysis_id
                    or vision_row.status != "succeeded"
                ):
                    raise KeyError(vision.vision_analysis_id)
            existing = await session.scalar(
                select(MediaPlanORM).where(
                    MediaPlanORM.project_id == analysis.project_id,
                    MediaPlanORM.fingerprint == fingerprint,
                )
            )
            if existing:
                return existing.media_plan_id, False
            row = MediaPlanORM(
                media_plan_id=_new_id("mpl"),
                workspace_id=analysis.workspace_id,
                project_id=analysis.project_id,
                project_version_id=analysis.project_version_id,
                analysis_id=analysis.analysis_id,
                vision_analysis_id=vision.vision_analysis_id if vision else None,
                status="draft",
                fingerprint=fingerprint,
                version=1,
                configuration_json=configuration.model_dump(mode="json"),
                provider_status_json=provider_status,
                projected_ai_cost_vnd=Decimal("0"),
                max_ai_cost_vnd=configuration.max_ai_cost_vnd,
                needs_approval=False,
                provenance_json=provenance,
            )
            session.add(row)
            try:
                await session.commit()
                return row.media_plan_id, True
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(MediaPlanORM).where(
                        MediaPlanORM.project_id == analysis.project_id,
                        MediaPlanORM.fingerprint == fingerprint,
                    )
                )
                if existing is None:
                    raise
                return existing.media_plan_id, False

    async def save_plan_items(
        self,
        *,
        media_plan_id: str,
        items: list[MediaPlanItemRead],
        projected_ai_cost_vnd: Decimal,
        needs_approval: bool,
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                plan = await session.scalar(
                    select(MediaPlanORM)
                    .where(MediaPlanORM.media_plan_id == media_plan_id)
                    .with_for_update()
                )
                if plan is None:
                    raise KeyError(media_plan_id)
                existing = await session.scalar(
                    select(MediaPlanItemORM.media_plan_item_id).where(
                        MediaPlanItemORM.media_plan_id == media_plan_id
                    )
                )
                if existing:
                    return
                for item in items:
                    session.add(
                        MediaPlanItemORM(
                            media_plan_item_id=item.media_plan_item_id,
                            media_plan_id=media_plan_id,
                            scene_id=item.scene_id,
                            ordinal=item.ordinal,
                            strategy=item.strategy,
                            fallback_json=list(item.fallback),
                            broll_json=item.broll.model_dump(mode="json"),
                            candidates_json=[candidate.model_dump(mode="json") for candidate in item.candidates],
                            source_asset_id=item.source_asset_id,
                            selected_media_asset_id=None,
                            estimated_cost_vnd=item.estimated_cost_vnd,
                            needs_approval=item.needs_approval,
                            needs_attention=item.needs_attention,
                            status=item.status,
                            provenance_json=item.provenance,
                        )
                    )
                plan.projected_ai_cost_vnd = projected_ai_cost_vnd
                plan.needs_approval = needs_approval
                plan.updated_at = utc_now()

    async def mark_plan_failed(self, media_plan_id: str, error_code: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(MediaPlanORM, media_plan_id)
            if row is None:
                return
            row.status = "failed"
            row.error_code = error_code
            row.updated_at = utc_now()
            await session.commit()

    async def get_plan(self, media_plan_id: str) -> MediaPlanRead | None:
        async with self.session_factory() as session:
            plan = await session.get(MediaPlanORM, media_plan_id)
            if plan is None:
                return None
            item_rows = (
                await session.scalars(
                    select(MediaPlanItemORM)
                    .where(MediaPlanItemORM.media_plan_id == media_plan_id)
                    .order_by(MediaPlanItemORM.ordinal)
                )
            ).all()
            asset_rows = (
                await session.scalars(
                    select(MediaAssetProvenanceORM)
                    .where(MediaAssetProvenanceORM.media_plan_id == media_plan_id)
                    .order_by(MediaAssetProvenanceORM.created_at)
                )
            ).all()
            job_rows = (
                await session.scalars(
                    select(MediaResolutionJobORM)
                    .where(MediaResolutionJobORM.media_plan_id == media_plan_id)
                    .order_by(MediaResolutionJobORM.created_at)
                )
            ).all()
        items = [_item_read(row) for row in item_rows]
        assets = [_media_asset_read(row) for row in asset_rows]
        jobs = [_resolution_job_read(row) for row in job_rows]
        unresolved = sum(item.status != "resolved" for item in items)
        publishing_blocked = bool(
            unresolved
            or not assets
            or any(not item.publishing_allowed for item in assets)
        )
        return MediaPlanRead(
            media_plan_id=plan.media_plan_id,
            workspace_id=plan.workspace_id,
            project_id=plan.project_id,
            project_version_id=plan.project_version_id,
            analysis_id=plan.analysis_id,
            vision_analysis_id=plan.vision_analysis_id,
            status=plan.status,
            fingerprint=plan.fingerprint,
            version=plan.version,
            configuration=MediaPlanRequest.model_validate(plan.configuration_json),
            provider_status=plan.provider_status_json,
            items=items,
            media_assets=assets,
            resolution_jobs=jobs,
            projected_ai_cost_vnd=plan.projected_ai_cost_vnd,
            max_ai_cost_vnd=plan.max_ai_cost_vnd,
            needs_approval=plan.needs_approval,
            publishing_blocked=publishing_blocked,
            unresolved_items=unresolved,
            error_code=plan.error_code,
            provenance=plan.provenance_json,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
        )

    async def list_plans(self, project_id: str) -> list[MediaPlanRead]:
        async with self.session_factory() as session:
            identifiers = (
                await session.scalars(
                    select(MediaPlanORM.media_plan_id)
                    .where(MediaPlanORM.project_id == project_id)
                    .order_by(MediaPlanORM.created_at.desc())
                )
            ).all()
        return [item for identifier in identifiers if (item := await self.get_plan(identifier))]

    async def create_resolution_job(
        self,
        *,
        media_plan_id: str,
        media_plan_item_id: str,
        fingerprint: str,
        provider_key: str,
        capability: str,
        operation: str,
        selected_candidate_id: str | None,
        request_payload: dict[str, Any],
        estimated_cost_vnd: Decimal | None,
        external_call: bool,
        paid: bool,
        real_provider_tested: bool,
        provenance: dict[str, Any],
    ) -> tuple[MediaResolutionJobRead, bool]:
        async with self.session_factory() as session:
            plan = await session.get(MediaPlanORM, media_plan_id)
            item = await session.get(MediaPlanItemORM, media_plan_item_id)
            if plan is None or item is None or item.media_plan_id != media_plan_id:
                raise KeyError(media_plan_item_id)
            existing = await session.scalar(
                select(MediaResolutionJobORM).where(MediaResolutionJobORM.fingerprint == fingerprint)
            )
            if existing:
                return _resolution_job_read(existing), False
            row = MediaResolutionJobORM(
                resolution_job_id=_new_id("mrj"),
                fingerprint=fingerprint,
                workspace_id=plan.workspace_id,
                project_id=plan.project_id,
                project_version_id=plan.project_version_id,
                media_plan_id=media_plan_id,
                media_plan_item_id=media_plan_item_id,
                status="needs_approval" if item.needs_approval else "queued",
                progress=0,
                provider_key=provider_key,
                capability=capability,
                operation=operation,
                selected_candidate_id=selected_candidate_id,
                request_json=request_payload,
                estimated_cost_vnd=estimated_cost_vnd,
                external_call=external_call,
                paid=paid,
                real_provider_tested=real_provider_tested,
                provenance_json=provenance,
            )
            session.add(row)
            if item.needs_approval:
                item.status = "needs_approval"
                item.needs_attention = True
            else:
                item.status = "resolving"
            item.updated_at = utc_now()
            try:
                await session.commit()
                await session.refresh(row)
                return _resolution_job_read(row), True
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(MediaResolutionJobORM).where(
                        MediaResolutionJobORM.fingerprint == fingerprint
                    )
                )
                if existing is None:
                    raise
                return _resolution_job_read(existing), False

    async def mark_resolution_running(self, resolution_job_id: str) -> None:
        async with self.session_factory() as session:
            row = await session.get(MediaResolutionJobORM, resolution_job_id)
            if row is None:
                raise KeyError(resolution_job_id)
            if row.status == "succeeded":
                return
            row.status = "running"
            row.progress = max(row.progress, 10)
            row.updated_at = utc_now()
            await session.commit()

    async def mark_resolution_needs_approval(
        self, resolution_job_id: str, *, reason: str
    ) -> None:
        async with self.session_factory() as session:
            row = await session.get(MediaResolutionJobORM, resolution_job_id)
            if row is None:
                raise KeyError(resolution_job_id)
            item = await session.get(MediaPlanItemORM, row.media_plan_item_id)
            row.status = "needs_approval"
            row.error_code = "COST_APPROVAL_REQUIRED"
            row.failure_reason = reason[:1000]
            row.updated_at = utc_now()
            if item:
                item.status = "needs_approval"
                item.needs_approval = True
                item.needs_attention = True
                item.updated_at = utc_now()
            await session.commit()

    async def mark_resolution_failed(
        self, resolution_job_id: str, *, error_code: str, reason: str
    ) -> None:
        async with self.session_factory() as session:
            row = await session.get(MediaResolutionJobORM, resolution_job_id)
            if row is None:
                return
            item = await session.get(MediaPlanItemORM, row.media_plan_item_id)
            row.status = "failed"
            row.progress = min(row.progress, 99)
            row.error_code = error_code
            row.failure_reason = reason[:1000]
            row.updated_at = utc_now()
            if item:
                item.status = "failed"
                item.needs_attention = True
                item.updated_at = utc_now()
            await session.commit()

    async def complete_resolution(
        self,
        *,
        resolution_job_id: str,
        asset: AssetRead,
        media_asset_id: str,
        source_type: str,
        rights_status: str,
        license_name: str,
        license_url: str | None,
        provider: str,
        provider_asset_id: str | None,
        creator: str | None,
        source_reference: str,
        attribution_requirement: str | None,
        generation_provenance: dict[str, Any],
        width: int | None,
        height: int | None,
        duration_seconds: float | None,
        orientation: str,
        production_eligible: bool,
        provider_job_id: str | None,
        actual_cost_vnd: Decimal,
        downloaded_at,
        provenance: dict[str, Any],
    ) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                job = await session.scalar(
                    select(MediaResolutionJobORM)
                    .where(MediaResolutionJobORM.resolution_job_id == resolution_job_id)
                    .with_for_update()
                )
                if job is None:
                    raise KeyError(resolution_job_id)
                if job.status == "succeeded":
                    return
                item = await session.get(MediaPlanItemORM, job.media_plan_item_id)
                if item is None:
                    raise KeyError(job.media_plan_item_id)
                existing = await session.scalar(
                    select(MediaAssetProvenanceORM).where(
                        MediaAssetProvenanceORM.asset_id == asset.asset_id
                    )
                )
                publishing_allowed = bool(
                    production_eligible
                    and rights_status in {"owned", "licensed", "verified"}
                )
                if existing is None:
                    session.add(
                        MediaAssetProvenanceORM(
                            media_asset_id=media_asset_id,
                            workspace_id=asset.workspace_id,
                            project_id=asset.project_id,
                            project_version_id=asset.project_version_id,
                            media_plan_id=job.media_plan_id,
                            media_plan_item_id=job.media_plan_item_id,
                            asset_id=asset.asset_id,
                            source_type=source_type,
                            rights_status=rights_status,
                            license=license_name,
                            license_url=license_url,
                            provider=provider,
                            provider_asset_id=provider_asset_id,
                            creator=creator,
                            source_reference=source_reference,
                            attribution_requirement=attribution_requirement,
                            generation_provenance_json=generation_provenance,
                            width=width,
                            height=height,
                            duration_seconds=duration_seconds,
                            orientation=orientation,
                            production_eligible=production_eligible,
                            publishing_allowed=publishing_allowed,
                            owner_override_recorded=False,
                            downloaded_at=downloaded_at,
                            provenance_json=provenance,
                        )
                    )
                    selected_media_asset_id = media_asset_id
                else:
                    selected_media_asset_id = existing.media_asset_id
                job.status = "succeeded"
                job.progress = 100
                job.provider_job_id = provider_job_id
                job.actual_cost_vnd = actual_cost_vnd
                job.output_media_asset_id = selected_media_asset_id
                job.error_code = None
                job.failure_reason = None
                job.updated_at = utc_now()
                item.selected_media_asset_id = selected_media_asset_id
                item.status = "resolved"
                item.needs_attention = not publishing_allowed
                item.updated_at = utc_now()

    async def get_resolution_job(self, resolution_job_id: str) -> MediaResolutionJobRead | None:
        async with self.session_factory() as session:
            row = await session.get(MediaResolutionJobORM, resolution_job_id)
            return _resolution_job_read(row) if row else None

    async def get_resolution_context(
        self, resolution_job_id: str
    ) -> tuple[MediaResolutionJobRead, MediaPlanRead, MediaPlanItemRead]:
        job = await self.get_resolution_job(resolution_job_id)
        if job is None:
            raise KeyError(resolution_job_id)
        plan = await self.get_plan(job.media_plan_id)
        if plan is None:
            raise KeyError(job.media_plan_id)
        item = next(
            (candidate for candidate in plan.items if candidate.media_plan_item_id == job.media_plan_item_id),
            None,
        )
        if item is None:
            raise KeyError(job.media_plan_item_id)
        return job, plan, item

    async def list_incomplete_resolution_job_ids(self) -> list[str]:
        async with self.session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(MediaResolutionJobORM.resolution_job_id)
                        .where(MediaResolutionJobORM.status.in_(["queued", "running"]))
                        .order_by(MediaResolutionJobORM.created_at)
                    )
                ).all()
            )

    async def list_media_assets(self, project_id: str) -> list[MediaAssetProvenanceRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(MediaAssetProvenanceORM)
                    .where(MediaAssetProvenanceORM.project_id == project_id)
                    .order_by(MediaAssetProvenanceORM.created_at)
                )
            ).all()
            return [_media_asset_read(row) for row in rows]


def _item_read(row: MediaPlanItemORM) -> MediaPlanItemRead:
    return MediaPlanItemRead(
        media_plan_item_id=row.media_plan_item_id,
        media_plan_id=row.media_plan_id,
        scene_id=row.scene_id,
        ordinal=row.ordinal,
        strategy=row.strategy,
        fallback=row.fallback_json,
        broll=BrollDecisionRead.model_validate(row.broll_json),
        candidates=[StockMediaCandidateRead.model_validate(item) for item in row.candidates_json],
        source_asset_id=row.source_asset_id,
        selected_media_asset_id=row.selected_media_asset_id,
        estimated_cost_vnd=row.estimated_cost_vnd,
        needs_approval=row.needs_approval,
        needs_attention=row.needs_attention,
        status=row.status,
        provenance=row.provenance_json,
    )


def _media_asset_read(row: MediaAssetProvenanceORM) -> MediaAssetProvenanceRead:
    return MediaAssetProvenanceRead(
        media_asset_id=row.media_asset_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        project_version_id=row.project_version_id,
        media_plan_id=row.media_plan_id,
        media_plan_item_id=row.media_plan_item_id,
        asset_id=row.asset_id,
        source_type=row.source_type,
        rights_status=row.rights_status,
        license=row.license,
        license_url=row.license_url,
        provider=row.provider,
        provider_asset_id=row.provider_asset_id,
        creator=row.creator,
        source_reference=row.source_reference,
        attribution_requirement=row.attribution_requirement,
        generation_provenance=row.generation_provenance_json,
        width=row.width,
        height=row.height,
        duration_seconds=row.duration_seconds,
        orientation=row.orientation,
        production_eligible=row.production_eligible,
        publishing_allowed=row.publishing_allowed,
        owner_override_recorded=False,
        downloaded_at=row.downloaded_at,
        provenance=row.provenance_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _resolution_job_read(row: MediaResolutionJobORM) -> MediaResolutionJobRead:
    return MediaResolutionJobRead(
        resolution_job_id=row.resolution_job_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        project_version_id=row.project_version_id,
        media_plan_id=row.media_plan_id,
        media_plan_item_id=row.media_plan_item_id,
        status=row.status,
        progress=row.progress,
        provider_key=row.provider_key,
        capability=row.capability,
        operation=row.operation,
        provider_job_id=row.provider_job_id,
        selected_candidate_id=row.selected_candidate_id,
        estimated_cost_vnd=row.estimated_cost_vnd,
        actual_cost_vnd=row.actual_cost_vnd,
        output_media_asset_id=row.output_media_asset_id,
        error_code=row.error_code,
        failure_reason=row.failure_reason,
        external_call=row.external_call,
        paid=row.paid,
        real_provider_tested=row.real_provider_tested,
        provenance=row.provenance_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
