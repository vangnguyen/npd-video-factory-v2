from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any, Iterable

from redis.asyncio import Redis
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import (
    AssetORM,
    CostRecordORM,
    IdempotencyKeyORM,
    JobEventORM,
    JobORM,
    ProjectVersionORM,
    ProviderRegistryORM,
    ProviderUsageORM,
    VideoProjectORM,
    WorkspaceORM,
    utc_now,
)
from .models import Artifact, JobError, JobRecord, JobStage, JobStatus
from .object_storage import ObjectStorageProvider
from .platform_models import (
    AssetRead,
    AssetRegister,
    CostRecordRead,
    JobContext,
    JobEventRead,
    ProjectCostSummary,
    ProjectCreate,
    ProjectRead,
    ProjectVersionCreate,
    ProjectVersionRead,
    ProviderRead,
    ProviderUsageRead,
    WorkspaceCreate,
    WorkspaceRead,
)
from .state import QUEUE_KEY, validate_transition


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def _workspace_read(row: WorkspaceORM) -> WorkspaceRead:
    return WorkspaceRead(
        workspace_id=row.workspace_id,
        slug=row.slug,
        name=row.name,
        owner_ref=row.owner_ref,
        version=row.version,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _project_read(row: VideoProjectORM) -> ProjectRead:
    return ProjectRead(
        project_id=row.project_id,
        workspace_id=row.workspace_id,
        slug=row.slug,
        name=row.name,
        niche=row.niche,
        status=row.status,
        current_version_id=row.current_version_id,
        version=row.version,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _version_read(row: ProjectVersionORM) -> ProjectVersionRead:
    return ProjectVersionRead(
        project_version_id=row.project_version_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        ordinal=row.ordinal,
        label=row.label,
        snapshot=row.snapshot,
        source_job_id=row.source_job_id,
        version=row.version,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _asset_read(row: AssetORM) -> AssetRead:
    return AssetRead(
        asset_id=row.asset_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        project_version_id=row.project_version_id,
        job_id=row.job_id,
        asset_class=row.asset_class,
        kind=row.kind,
        filename=row.filename,
        object_key=row.object_key,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        checksum_sha256=row.checksum_sha256,
        storage_provider=row.storage_provider,
        version=row.version,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _provider_read(row: ProviderRegistryORM) -> ProviderRead:
    return ProviderRead(
        provider_id=row.provider_id,
        workspace_id=row.workspace_id,
        provider_key=row.provider_key,
        display_name=row.display_name,
        capability=row.capability,
        adapter=row.adapter,
        routing_mode=row.routing_mode,
        status=row.status,
        enabled=row.enabled,
        supports_dry_run=row.supports_dry_run,
        config_ref=row.config_ref,
        version=row.version,
        metadata=row.metadata_json,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _usage_read(row: ProviderUsageORM) -> ProviderUsageRead:
    return ProviderUsageRead(
        usage_id=row.usage_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        job_id=row.job_id,
        provider_id=row.provider_id,
        provider_key=row.provider_key,
        capability=row.capability,
        model=row.model,
        operation=row.operation,
        units=row.units,
        unit_name=row.unit_name,
        status=row.status,
        metadata=row.metadata_json,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _cost_read(row: CostRecordORM) -> CostRecordRead:
    return CostRecordRead(
        cost_id=row.cost_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        job_id=row.job_id,
        provider_usage_id=row.provider_usage_id,
        estimated_cost=row.estimated_cost,
        actual_cost=row.actual_cost,
        currency="VND",
        needs_approval=row.needs_approval,
        approved=row.approved,
        provenance=row.provenance,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PlatformRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def create_workspace(self, payload: WorkspaceCreate) -> WorkspaceRead:
        row = WorkspaceORM(
            workspace_id=new_id("wsp"),
            slug=payload.slug,
            name=payload.name,
            owner_ref=payload.owner_ref,
            provenance=payload.provenance,
        )
        async with self.session_factory() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("workspace slug already exists") from exc
            await session.refresh(row)
        return _workspace_read(row)

    async def ensure_workspace(self, payload: WorkspaceCreate) -> WorkspaceRead:
        async with self.session_factory() as session:
            row = await session.scalar(select(WorkspaceORM).where(WorkspaceORM.slug == payload.slug))
        if row:
            return _workspace_read(row)
        try:
            return await self.create_workspace(payload)
        except ValueError:
            async with self.session_factory() as session:
                row = await session.scalar(select(WorkspaceORM).where(WorkspaceORM.slug == payload.slug))
                if row is None:
                    raise
                return _workspace_read(row)

    async def get_workspace(self, workspace_id: str) -> WorkspaceRead | None:
        async with self.session_factory() as session:
            row = await session.get(WorkspaceORM, workspace_id)
            return _workspace_read(row) if row else None

    async def list_workspaces(self) -> list[WorkspaceRead]:
        async with self.session_factory() as session:
            rows = (await session.scalars(select(WorkspaceORM).order_by(WorkspaceORM.created_at))).all()
            return [_workspace_read(row) for row in rows]

    async def create_project(self, workspace_id: str, payload: ProjectCreate) -> ProjectRead:
        async with self.session_factory() as session:
            if await session.get(WorkspaceORM, workspace_id) is None:
                raise KeyError(workspace_id)
            row = VideoProjectORM(
                project_id=new_id("prj"),
                workspace_id=workspace_id,
                slug=payload.slug,
                name=payload.name,
                niche=payload.niche,
                provenance=payload.provenance,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("project slug already exists in workspace") from exc
            await session.refresh(row)
            return _project_read(row)

    async def ensure_project(self, workspace_id: str, payload: ProjectCreate) -> ProjectRead:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(VideoProjectORM).where(
                    VideoProjectORM.workspace_id == workspace_id,
                    VideoProjectORM.slug == payload.slug,
                )
            )
        if row:
            return _project_read(row)
        try:
            return await self.create_project(workspace_id, payload)
        except ValueError:
            async with self.session_factory() as session:
                row = await session.scalar(
                    select(VideoProjectORM).where(
                        VideoProjectORM.workspace_id == workspace_id,
                        VideoProjectORM.slug == payload.slug,
                    )
                )
                if row is None:
                    raise
                return _project_read(row)

    async def get_project(self, project_id: str) -> ProjectRead | None:
        async with self.session_factory() as session:
            row = await session.get(VideoProjectORM, project_id)
            return _project_read(row) if row else None

    async def list_projects(self, workspace_id: str) -> list[ProjectRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(VideoProjectORM)
                    .where(VideoProjectORM.workspace_id == workspace_id)
                    .order_by(VideoProjectORM.created_at)
                )
            ).all()
            return [_project_read(row) for row in rows]

    async def create_version(
        self,
        project_id: str,
        payload: ProjectVersionCreate,
        *,
        source_job_id: str | None = None,
    ) -> ProjectVersionRead:
        async with self.session_factory() as session:
            async with session.begin():
                project = await session.scalar(
                    select(VideoProjectORM).where(VideoProjectORM.project_id == project_id).with_for_update()
                )
                if project is None:
                    raise KeyError(project_id)
                latest = await session.scalar(
                    select(func.max(ProjectVersionORM.ordinal)).where(ProjectVersionORM.project_id == project_id)
                )
                row = ProjectVersionORM(
                    project_version_id=new_id("pver"),
                    workspace_id=project.workspace_id,
                    project_id=project_id,
                    ordinal=int(latest or 0) + 1,
                    label=payload.label,
                    snapshot=payload.snapshot,
                    source_job_id=source_job_id,
                    provenance=payload.provenance,
                )
                session.add(row)
                await session.flush()
                project.current_version_id = row.project_version_id
                project.version += 1
                project.updated_at = utc_now()
            await session.refresh(row)
            return _version_read(row)

    async def ensure_initial_version(
        self,
        project_id: str,
        *,
        snapshot: dict[str, Any],
    ) -> ProjectVersionRead:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(ProjectVersionORM)
                .where(ProjectVersionORM.project_id == project_id)
                .order_by(ProjectVersionORM.ordinal)
                .limit(1)
            )
        if row:
            return _version_read(row)
        try:
            return await self.create_version(
                project_id,
                ProjectVersionCreate(
                    label="initial",
                    snapshot=snapshot,
                    provenance={"source": "video-job-compatibility-adapter"},
                ),
            )
        except IntegrityError:
            async with self.session_factory() as session:
                row = await session.scalar(
                    select(ProjectVersionORM)
                    .where(ProjectVersionORM.project_id == project_id)
                    .order_by(ProjectVersionORM.ordinal)
                    .limit(1)
                )
                if row is None:
                    raise
                return _version_read(row)

    async def get_version(self, project_version_id: str) -> ProjectVersionRead | None:
        async with self.session_factory() as session:
            row = await session.get(ProjectVersionORM, project_version_id)
            return _version_read(row) if row else None

    async def list_versions(self, project_id: str) -> list[ProjectVersionRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(ProjectVersionORM)
                    .where(ProjectVersionORM.project_id == project_id)
                    .order_by(ProjectVersionORM.ordinal)
                )
            ).all()
            return [_version_read(row) for row in rows]

    async def resolve_job_context(
        self,
        request_payload: dict[str, Any],
        *,
        default_workspace: WorkspaceCreate,
    ) -> JobContext:
        requested_workspace_id = request_payload.get("workspace_id")
        requested_project_id = request_payload.get("project_id")
        requested_version_id = request_payload.get("project_version_id")

        if requested_workspace_id:
            workspace = await self.get_workspace(requested_workspace_id)
            if workspace is None:
                raise KeyError(requested_workspace_id)
        else:
            workspace = await self.ensure_workspace(default_workspace)

        if requested_project_id:
            project = await self.get_project(requested_project_id)
            if project is None or project.workspace_id != workspace.workspace_id:
                raise KeyError(requested_project_id)
        else:
            slug = str(request_payload["project"])
            project = await self.ensure_project(
                workspace.workspace_id,
                ProjectCreate(
                    slug=slug,
                    name=" ".join(part.capitalize() for part in slug.split("-")),
                    niche=str(request_payload.get("niche", "custom")),
                    provenance={"source": "video-job-compatibility-adapter"},
                ),
            )

        if requested_version_id:
            version = await self.get_version(requested_version_id)
            if version is None or version.project_id != project.project_id:
                raise KeyError(requested_version_id)
        else:
            version = await self.ensure_initial_version(project.project_id, snapshot=request_payload)

        return JobContext(
            workspace_id=workspace.workspace_id,
            project_id=project.project_id,
            project_version_id=version.project_version_id,
        )

    async def register_asset(
        self,
        project_id: str,
        payload: AssetRegister,
        *,
        job_id: str | None = None,
    ) -> AssetRead:
        async with self.session_factory() as session:
            project = await session.get(VideoProjectORM, project_id)
            if project is None:
                raise KeyError(project_id)
            if payload.project_version_id:
                version = await session.get(ProjectVersionORM, payload.project_version_id)
                if version is None or version.project_id != project_id:
                    raise KeyError(payload.project_version_id)
            existing = await session.scalar(select(AssetORM).where(AssetORM.object_key == payload.object_key))
            if existing:
                if existing.project_id != project_id or existing.checksum_sha256 != payload.checksum_sha256:
                    raise ValueError("object key is already registered to different content")
                return _asset_read(existing)
            row = AssetORM(
                asset_id=new_id("ast"),
                workspace_id=project.workspace_id,
                project_id=project_id,
                project_version_id=payload.project_version_id,
                job_id=job_id,
                asset_class=payload.asset_class,
                kind=payload.kind,
                filename=payload.filename,
                object_key=payload.object_key,
                content_type=payload.content_type,
                size_bytes=payload.size_bytes,
                checksum_sha256=payload.checksum_sha256,
                storage_provider=payload.storage_provider,
                provenance=payload.provenance,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return _asset_read(row)

    async def list_assets(self, project_id: str) -> list[AssetRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(AssetORM).where(AssetORM.project_id == project_id).order_by(AssetORM.created_at)
                )
            ).all()
            return [_asset_read(row) for row in rows]

    async def seed_providers(self, definitions: Iterable[dict[str, Any]]) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                for definition in definitions:
                    existing = await session.scalar(
                        select(ProviderRegistryORM).where(
                            ProviderRegistryORM.workspace_id.is_(None),
                            ProviderRegistryORM.provider_key == definition["provider_key"],
                            ProviderRegistryORM.capability == definition["capability"],
                        )
                    )
                    if existing:
                        updates = {
                            "display_name": definition["display_name"],
                            "adapter": definition["adapter"],
                            "routing_mode": definition["routing_mode"],
                            "status": definition["status"],
                            "enabled": definition["enabled"],
                            "supports_dry_run": definition.get("supports_dry_run", False),
                            "config_ref": definition.get("config_ref"),
                            "metadata_json": definition.get("metadata", {}),
                        }
                        changed = any(getattr(existing, key) != value for key, value in updates.items())
                        if changed:
                            for key, value in updates.items():
                                setattr(existing, key, value)
                            existing.version += 1
                            existing.updated_at = utc_now()
                    else:
                        session.add(
                            ProviderRegistryORM(
                                provider_id=new_id("prv"),
                                workspace_id=None,
                                provider_key=definition["provider_key"],
                                display_name=definition["display_name"],
                                capability=definition["capability"],
                                adapter=definition["adapter"],
                                routing_mode=definition["routing_mode"],
                                status=definition["status"],
                                enabled=definition["enabled"],
                                supports_dry_run=definition.get("supports_dry_run", False),
                                config_ref=definition.get("config_ref"),
                                metadata_json=definition.get("metadata", {}),
                                provenance={"source": "built-in-provider-registry"},
                            )
                        )

    async def list_providers(self, *, capability: str | None = None) -> list[ProviderRead]:
        query = select(ProviderRegistryORM)
        if capability:
            query = query.where(ProviderRegistryORM.capability == capability)
        query = query.order_by(ProviderRegistryORM.capability, ProviderRegistryORM.provider_key)
        async with self.session_factory() as session:
            rows = (await session.scalars(query)).all()
            return [_provider_read(row) for row in rows]

    async def record_provider_operation(
        self,
        *,
        workspace_id: str,
        project_id: str | None,
        job_id: str | None,
        provider_key: str,
        capability: str,
        operation: str,
        model: str | None = None,
        units: Decimal | None = None,
        unit_name: str | None = None,
        estimated_cost: Decimal | None = None,
        actual_cost: Decimal | None = None,
        max_cost_vnd: Decimal | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ProviderUsageRead, CostRecordRead]:
        operation_key = hashlib.sha256(
            (
                f"{workspace_id}|{project_id or '-'}|{job_id or '-'}|"
                f"{provider_key}|{capability}|{operation}"
            ).encode("utf-8")
        ).hexdigest()
        async with self.session_factory() as session:
            async with session.begin():
                existing_usage = await session.scalar(
                    select(ProviderUsageORM).where(ProviderUsageORM.operation_key == operation_key)
                )
                if existing_usage:
                    existing_cost = await session.scalar(
                        select(CostRecordORM).where(
                            CostRecordORM.provider_usage_id == existing_usage.usage_id
                        )
                    )
                    if existing_cost is None:
                        raise RuntimeError("provider usage is missing its cost record")
                    return _usage_read(existing_usage), _cost_read(existing_cost)

                provider = await session.scalar(
                    select(ProviderRegistryORM).where(
                        ProviderRegistryORM.workspace_id.is_(None),
                        ProviderRegistryORM.provider_key == provider_key,
                        ProviderRegistryORM.capability == capability,
                    )
                )
                if provider is None:
                    raise KeyError(f"provider not registered: {provider_key}/{capability}")

                usage = ProviderUsageORM(
                    usage_id=new_id("pus"),
                    operation_key=operation_key,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    job_id=job_id,
                    provider_id=provider.provider_id,
                    provider_key=provider_key,
                    capability=capability,
                    model=model,
                    operation=operation,
                    units=units,
                    unit_name=unit_name,
                    status="succeeded",
                    metadata_json=metadata or {},
                    completed_at=utc_now(),
                )
                session.add(usage)
                await session.flush()
                projected = estimated_cost if estimated_cost is not None else actual_cost
                needs_approval = bool(
                    max_cost_vnd is not None and projected is not None and projected > max_cost_vnd
                )
                cost = CostRecordORM(
                    cost_id=new_id("cost"),
                    workspace_id=workspace_id,
                    project_id=project_id,
                    job_id=job_id,
                    provider_usage_id=usage.usage_id,
                    estimated_cost=estimated_cost,
                    actual_cost=actual_cost,
                    currency="VND",
                    needs_approval=needs_approval,
                    approved=False,
                    provenance={"source": "provider-usage-meter"},
                )
                session.add(cost)
                await session.flush()
                return _usage_read(usage), _cost_read(cost)

    async def list_cost_records(self, project_id: str) -> list[CostRecordRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(CostRecordORM)
                    .where(CostRecordORM.project_id == project_id)
                    .order_by(CostRecordORM.created_at)
                )
            ).all()
            return [_cost_read(row) for row in rows]

    async def project_cost_summary(self, project_id: str) -> ProjectCostSummary:
        async with self.session_factory() as session:
            if await session.get(VideoProjectORM, project_id) is None:
                raise KeyError(project_id)
            result = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(CostRecordORM.estimated_cost), 0),
                        func.coalesce(func.sum(CostRecordORM.actual_cost), 0),
                        func.coalesce(
                            func.sum(
                                case(
                                    (
                                        CostRecordORM.estimated_cost.is_(None)
                                        & CostRecordORM.actual_cost.is_(None),
                                        1,
                                    ),
                                    else_=0,
                                )
                            ),
                            0,
                        ),
                        func.coalesce(func.max(case((CostRecordORM.needs_approval.is_(True), 1), else_=0)), 0),
                        func.count(CostRecordORM.cost_id),
                    ).where(CostRecordORM.project_id == project_id)
                )
            ).one()
            return ProjectCostSummary(
                project_id=project_id,
                estimated_cost=Decimal(str(result[0])),
                actual_cost=Decimal(str(result[1])),
                unpriced_operations=int(result[2]),
                needs_approval=bool(result[3]),
                records=int(result[4]),
            )


class PostgresJobStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        *,
        platform: PlatformRepository | None = None,
        object_storage: ObjectStorageProvider | None = None,
    ):
        self.session_factory = session_factory
        self.redis = redis
        self.platform = platform or PlatformRepository(session_factory)
        self.object_storage = object_storage

    @staticmethod
    def idempotency_hash(key: str, *, workspace_id: str | None) -> str:
        scope = workspace_id or "unscoped"
        return hashlib.sha256(f"{scope}|{key}".encode("utf-8")).hexdigest()

    @staticmethod
    def _record(row: JobORM) -> JobRecord:
        return JobRecord.model_validate(
            {
                "job_id": row.job_id,
                "workspace_id": row.workspace_id,
                "project_id": row.project_id,
                "project_version_id": row.project_version_id,
                "status": row.status,
                "stage": row.stage,
                "progress": row.progress,
                "request": row.request_json,
                "artifacts": row.artifacts_json,
                "error": row.error_json,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )

    @staticmethod
    def _event(
        *,
        row: JobORM,
        event_type: str,
        current: JobRecord | None = None,
        updated: JobRecord | None = None,
        payload: dict[str, Any] | None = None,
        actor_ref: str = "system",
    ) -> JobEventORM:
        return JobEventORM(
            event_id=new_id("jev"),
            job_id=row.job_id,
            workspace_id=row.workspace_id,
            event_type=event_type,
            from_status=current.status.value if current else None,
            to_status=updated.status.value if updated else row.status,
            from_stage=current.stage.value if current else None,
            to_stage=updated.stage.value if updated else row.stage,
            from_progress=current.progress if current else None,
            to_progress=updated.progress if updated else row.progress,
            actor_ref=actor_ref,
            payload_json=payload or {},
        )

    async def create(self, record: JobRecord, *, idempotency_key: str | None = None) -> JobRecord:
        key_hash = (
            self.idempotency_hash(idempotency_key, workspace_id=record.workspace_id)
            if idempotency_key
            else None
        )
        if key_hash:
            async with self.session_factory() as session:
                existing_id = await session.scalar(
                    select(IdempotencyKeyORM.job_id).where(
                        IdempotencyKeyORM.key_hash == key_hash,
                        IdempotencyKeyORM.expires_at > utc_now(),
                    )
                )
            if existing_id:
                existing = await self.get(existing_id)
                if existing:
                    return existing

        row = JobORM(
            job_id=record.job_id,
            workspace_id=record.workspace_id,
            project_id=record.project_id,
            project_version_id=record.project_version_id,
            status=record.status.value,
            stage=record.stage.value,
            progress=record.progress,
            request_json=record.request.model_dump(mode="json"),
            artifacts_json=[artifact.model_dump(mode="json") for artifact in record.artifacts],
            error_json=record.error.model_dump(mode="json") if record.error else None,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        async with self.session_factory() as session:
            session.add(row)
            # Flush the canonical job first so PostgreSQL foreign keys for the
            # audit event and optional idempotency receipt are always valid.
            await session.flush()
            session.add(self._event(row=row, event_type="job.created", updated=record))
            if key_hash:
                session.add(
                    IdempotencyKeyORM(
                        key_hash=key_hash,
                        job_id=record.job_id,
                        expires_at=utc_now() + timedelta(hours=24),
                    )
                )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                if key_hash:
                    existing_id = await session.scalar(
                        select(IdempotencyKeyORM.job_id).where(IdempotencyKeyORM.key_hash == key_hash)
                    )
                    if existing_id:
                        existing = await self.get(existing_id)
                        if existing:
                            return existing
                existing = await self.get(record.job_id)
                if existing:
                    return existing
                raise RuntimeError("job key collision")
        return record

    async def enqueue(self, job_id: str) -> None:
        await self.redis.rpush(QUEUE_KEY, job_id)

    async def get(self, job_id: str) -> JobRecord | None:
        async with self.session_factory() as session:
            row = await session.get(JobORM, job_id)
            return self._record(row) if row else None

    async def update_stage(
        self,
        job_id: str,
        *,
        status: JobStatus,
        stage: JobStage,
        progress: int,
    ) -> JobRecord:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.scalar(select(JobORM).where(JobORM.job_id == job_id).with_for_update())
                if row is None:
                    raise KeyError(job_id)
                current = self._record(row)
                validate_transition(current, stage=stage, progress=progress)
                updated = current.model_copy(
                    update={
                        "status": status,
                        "stage": stage,
                        "progress": progress,
                        "updated_at": utc_now(),
                    }
                )
                row.status = status.value
                row.stage = stage.value
                row.progress = progress
                row.updated_at = updated.updated_at
                row.record_version += 1
                session.add(self._event(row=row, event_type="job.transitioned", current=current, updated=updated))
            return updated

    async def add_artifact(self, job_id: str, *, artifact: Artifact) -> JobRecord:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.scalar(select(JobORM).where(JobORM.job_id == job_id).with_for_update())
                if row is None:
                    raise KeyError(job_id)
                current = self._record(row)
                recorded = artifact
                if artifact.object_key and row.workspace_id and row.project_id:
                    existing_asset = await session.scalar(
                        select(AssetORM).where(AssetORM.object_key == artifact.object_key)
                    )
                    if existing_asset:
                        if existing_asset.checksum_sha256 != artifact.checksum_sha256:
                            raise ValueError("artifact object key checksum changed")
                        asset_id = existing_asset.asset_id
                    else:
                        asset_id = new_id("ast")
                        session.add(
                            AssetORM(
                                asset_id=asset_id,
                                workspace_id=row.workspace_id,
                                project_id=row.project_id,
                                project_version_id=row.project_version_id,
                                job_id=row.job_id,
                                asset_class=(
                                    "source"
                                    if artifact.kind == "source_asset"
                                    else "render"
                                    if artifact.kind == "video"
                                    else "metadata"
                                    if artifact.kind in {"request", "script", "storyboard", "subtitle", "manifest", "qc", "metadata"}
                                    else "generated"
                                ),
                                kind=artifact.kind,
                                filename=artifact.name,
                                object_key=artifact.object_key,
                                content_type=artifact.content_type or "application/octet-stream",
                                size_bytes=artifact.size_bytes or 0,
                                checksum_sha256=artifact.checksum_sha256 or "0" * 64,
                                storage_provider=artifact.storage_provider or "unknown",
                                provenance={"source": "video-job-pipeline"},
                            )
                        )
                    recorded = artifact.model_copy(update={"asset_id": asset_id})
                artifacts = [item for item in current.artifacts if item.name != recorded.name]
                artifacts.append(recorded)
                updated = current.model_copy(update={"artifacts": artifacts, "updated_at": utc_now()})
                row.artifacts_json = [item.model_dump(mode="json") for item in artifacts]
                row.updated_at = updated.updated_at
                row.record_version += 1
                session.add(
                    self._event(
                        row=row,
                        event_type="job.artifact_recorded",
                        current=current,
                        updated=updated,
                        payload={"kind": recorded.kind, "name": recorded.name, "asset_id": recorded.asset_id},
                    )
                )
            return updated

    async def fail(self, job_id: str, *, error: JobError) -> JobRecord:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.scalar(select(JobORM).where(JobORM.job_id == job_id).with_for_update())
                if row is None:
                    raise KeyError(job_id)
                current = self._record(row)
                updated = current.model_copy(
                    update={
                        "status": JobStatus.FAILED,
                        "stage": JobStage.FAILED,
                        "error": error,
                        "updated_at": utc_now(),
                    }
                )
                row.status = JobStatus.FAILED.value
                row.stage = JobStage.FAILED.value
                row.error_json = error.model_dump(mode="json")
                row.updated_at = updated.updated_at
                row.record_version += 1
                session.add(
                    self._event(
                        row=row,
                        event_type="job.failed",
                        current=current,
                        updated=updated,
                        payload={"error_code": error.code, "retryable": error.retryable},
                    )
                )
            return updated

    async def list_events(self, job_id: str) -> list[JobEventRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(JobEventORM)
                    .where(JobEventORM.job_id == job_id)
                    .order_by(JobEventORM.created_at, JobEventORM.event_id)
                )
            ).all()
            return [
                JobEventRead(
                    event_id=row.event_id,
                    job_id=row.job_id,
                    workspace_id=row.workspace_id,
                    event_type=row.event_type,
                    from_status=row.from_status,
                    to_status=row.to_status,
                    from_stage=row.from_stage,
                    to_stage=row.to_stage,
                    from_progress=row.from_progress,
                    to_progress=row.to_progress,
                    actor_ref=row.actor_ref,
                    payload=row.payload_json,
                    created_at=row.created_at,
                )
                for row in rows
            ]
