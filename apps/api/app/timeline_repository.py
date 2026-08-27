from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import VideoProjectORM, utc_now
from .timeline_db import PreviewJobORM, TimelineORM, TimelineVersionORM
from .timeline_models import PreviewRead, TimelineRead, TimelineSnapshot, TimelineVersionRead


class TimelineConflictError(RuntimeError):
    def __init__(self, *, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(f"timeline version conflict: expected {expected}, current version is {actual}")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class TimelineRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def create_timeline(
        self,
        *,
        project_id: str,
        source_analysis_id: str,
        source_media_plan_id: str | None,
        snapshot: TimelineSnapshot,
        actor_ref: str,
    ) -> tuple[TimelineRead, bool]:
        async with self.session_factory() as session:
            project = await session.get(VideoProjectORM, project_id)
            if project is None:
                raise KeyError(project_id)
            existing = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id))
            if existing is not None:
                current = await self._timeline_read(session, existing)
                return current, False
            timeline_id = _new_id("tml")
            version_id = _new_id("tlv")
            now = utc_now()
            row = TimelineORM(
                timeline_id=timeline_id,
                workspace_id=project.workspace_id,
                project_id=project_id,
                project_version_id=project.current_version_id,
                source_analysis_id=source_analysis_id,
                source_media_plan_id=source_media_plan_id,
                current_version_id=version_id,
                current_version=1,
                approval_status="draft",
                approved_timeline_version=None,
                latest_preview_id=None,
                created_at=now,
                updated_at=now,
            )
            version = TimelineVersionORM(
                timeline_version_id=version_id,
                timeline_id=timeline_id,
                project_id=project_id,
                version=1,
                snapshot_json=snapshot.model_dump(mode="json"),
                mutation_json={
                    "type": "initialize",
                    "source_analysis_id": source_analysis_id,
                    "source_media_plan_id": source_media_plan_id,
                },
                actor_ref=actor_ref,
                created_at=now,
            )
            session.add_all([row, version])
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id))
                if existing is None:
                    raise
                return await self._timeline_read(session, existing), False
            return await self._timeline_read(session, row), True

    async def get_timeline(self, project_id: str) -> TimelineRead | None:
        async with self.session_factory() as session:
            row = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id))
            return await self._timeline_read(session, row) if row else None

    async def get_version(self, timeline_id: str, version: int) -> TimelineVersionRead | None:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(TimelineVersionORM).where(
                    TimelineVersionORM.timeline_id == timeline_id,
                    TimelineVersionORM.version == version,
                )
            )
            return _version_read(row) if row else None

    async def get_version_by_id(self, timeline_version_id: str) -> TimelineVersionRead | None:
        async with self.session_factory() as session:
            row = await session.get(TimelineVersionORM, timeline_version_id)
            return _version_read(row) if row else None

    async def list_versions(self, project_id: str) -> list[TimelineVersionRead]:
        async with self.session_factory() as session:
            timeline = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id))
            if timeline is None:
                return []
            rows = (
                await session.scalars(
                    select(TimelineVersionORM)
                    .where(TimelineVersionORM.timeline_id == timeline.timeline_id)
                    .order_by(TimelineVersionORM.version.desc())
                )
            ).all()
            return [_version_read(row) for row in rows]

    async def commit_mutation(
        self,
        *,
        project_id: str,
        expected_version: int,
        snapshot: TimelineSnapshot,
        mutation: dict[str, Any],
        actor_ref: str,
    ) -> TimelineRead:
        async with self.session_factory() as session:
            async with session.begin():
                timeline = await session.scalar(
                    select(TimelineORM)
                    .where(TimelineORM.project_id == project_id)
                    .with_for_update()
                )
                if timeline is None:
                    raise KeyError(project_id)
                if timeline.current_version != expected_version:
                    raise TimelineConflictError(expected=expected_version, actual=timeline.current_version)
                new_version = expected_version + 1
                version_id = _new_id("tlv")
                now = utc_now()
                session.add(
                    TimelineVersionORM(
                        timeline_version_id=version_id,
                        timeline_id=timeline.timeline_id,
                        project_id=project_id,
                        version=new_version,
                        snapshot_json=snapshot.model_dump(mode="json"),
                        mutation_json=mutation,
                        actor_ref=actor_ref,
                        created_at=now,
                    )
                )
                await session.execute(
                    update(PreviewJobORM)
                    .where(
                        PreviewJobORM.timeline_id == timeline.timeline_id,
                        PreviewJobORM.status.in_(["queued", "running", "ready"]),
                    )
                    .values(
                        status="stale",
                        cancellation_requested=True,
                        invalidated_at=now,
                        updated_at=now,
                    )
                )
                timeline.current_version_id = version_id
                timeline.current_version = new_version
                timeline.approval_status = "draft"
                timeline.approved_timeline_version = None
                timeline.latest_preview_id = None
                timeline.updated_at = now
            return await self._timeline_read(session, timeline)

    async def create_preview(
        self,
        *,
        project_id: str,
        timeline_version: int | None,
        width: int,
        height: int,
        actor_ref: str,
    ) -> tuple[PreviewRead, bool]:
        async with self.session_factory() as session:
            async with session.begin():
                timeline = await session.scalar(
                    select(TimelineORM)
                    .where(TimelineORM.project_id == project_id)
                    .with_for_update()
                )
                if timeline is None:
                    raise KeyError(project_id)
                requested_version = timeline_version or timeline.current_version
                version_row = await session.scalar(
                    select(TimelineVersionORM).where(
                        TimelineVersionORM.timeline_id == timeline.timeline_id,
                        TimelineVersionORM.version == requested_version,
                    )
                )
                if version_row is None:
                    raise KeyError(f"timeline-version:{requested_version}")
                existing = await session.scalar(
                    select(PreviewJobORM).where(
                        PreviewJobORM.timeline_version_id == version_row.timeline_version_id,
                        PreviewJobORM.width == width,
                        PreviewJobORM.height == height,
                    )
                )
                if existing is not None:
                    if (
                        requested_version == timeline.current_version
                        and existing.status in {"failed", "cancelled"}
                    ):
                        existing.status = "queued"
                        existing.progress = 0
                        existing.output_asset_id = None
                        existing.cancellation_requested = False
                        existing.invalidated_at = None
                        existing.error_code = None
                        existing.failure_reason = None
                        existing.manifest_json = {
                            "mode": "proxy",
                            "audio": "deferred_to_v2_08",
                            "requested_by": actor_ref,
                        }
                        existing.updated_at = utc_now()
                        timeline.latest_preview_id = existing.preview_id
                        timeline.updated_at = utc_now()
                        created = True
                    else:
                        created = False
                    preview = await self._preview_read(session, existing, timeline)
                    return preview, created
                now = utc_now()
                row = PreviewJobORM(
                    preview_id=_new_id("prv"),
                    workspace_id=timeline.workspace_id,
                    project_id=project_id,
                    timeline_id=timeline.timeline_id,
                    timeline_version_id=version_row.timeline_version_id,
                    timeline_version=requested_version,
                    status="queued",
                    progress=0,
                    width=width,
                    height=height,
                    output_asset_id=None,
                    cancellation_requested=False,
                    invalidated_at=None,
                    error_code=None,
                    failure_reason=None,
                    manifest_json={
                        "mode": "proxy",
                        "audio": "deferred_to_v2_08",
                        "requested_by": actor_ref,
                    },
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
                if requested_version == timeline.current_version:
                    timeline.latest_preview_id = row.preview_id
                    timeline.updated_at = now
            return await self._preview_read(session, row, timeline), True

    async def get_preview(self, preview_id: str) -> PreviewRead | None:
        async with self.session_factory() as session:
            row = await session.get(PreviewJobORM, preview_id)
            if row is None:
                return None
            timeline = await session.get(TimelineORM, row.timeline_id)
            if timeline is None:
                return None
            return await self._preview_read(session, row, timeline)

    async def get_preview_context(
        self, preview_id: str
    ) -> tuple[PreviewRead, TimelineVersionRead] | None:
        async with self.session_factory() as session:
            row = await session.get(PreviewJobORM, preview_id)
            if row is None:
                return None
            timeline = await session.get(TimelineORM, row.timeline_id)
            version = await session.get(TimelineVersionORM, row.timeline_version_id)
            if timeline is None or version is None:
                return None
            return await self._preview_read(session, row, timeline), _version_read(version)

    async def list_incomplete_preview_ids(self) -> list[str]:
        async with self.session_factory() as session:
            return list(
                (
                    await session.scalars(
                        select(PreviewJobORM.preview_id)
                        .where(PreviewJobORM.status.in_(["queued", "running"]))
                        .order_by(PreviewJobORM.created_at)
                    )
                ).all()
            )

    async def start_preview(self, preview_id: str) -> PreviewRead | None:
        return await self._set_preview_state(preview_id, status="running", progress=10)

    async def set_preview_progress(self, preview_id: str, progress: int) -> PreviewRead | None:
        return await self._set_preview_state(preview_id, progress=progress)

    async def complete_preview(
        self,
        preview_id: str,
        *,
        output_asset_id: str,
        manifest: dict[str, Any],
    ) -> PreviewRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(PreviewJobORM, preview_id, with_for_update=True)
                if row is None:
                    return None
                timeline = await session.get(TimelineORM, row.timeline_id)
                if timeline is None:
                    return None
                row.output_asset_id = output_asset_id
                row.manifest_json = manifest
                if row.cancellation_requested or row.invalidated_at is not None:
                    row.status = "stale" if row.invalidated_at is not None else "cancelled"
                    row.progress = min(row.progress, 99)
                else:
                    row.status = "ready"
                    row.progress = 100
                row.updated_at = utc_now()
            return await self._preview_read(session, row, timeline)

    async def fail_preview(self, preview_id: str, *, code: str, reason: str) -> PreviewRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(PreviewJobORM, preview_id, with_for_update=True)
                if row is None:
                    return None
                timeline = await session.get(TimelineORM, row.timeline_id)
                if timeline is None:
                    return None
                if row.cancellation_requested:
                    row.status = "stale" if row.invalidated_at is not None else "cancelled"
                else:
                    row.status = "failed"
                    row.error_code = code[:80]
                    row.failure_reason = reason[:1000]
                row.updated_at = utc_now()
            return await self._preview_read(session, row, timeline)

    async def cancel_preview(self, preview_id: str) -> PreviewRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(PreviewJobORM, preview_id, with_for_update=True)
                if row is None:
                    return None
                timeline = await session.get(TimelineORM, row.timeline_id)
                if timeline is None:
                    return None
                row.cancellation_requested = True
                if row.status == "queued":
                    row.status = "cancelled"
                row.updated_at = utc_now()
            return await self._preview_read(session, row, timeline)

    async def preview_cancel_requested(self, preview_id: str) -> bool:
        async with self.session_factory() as session:
            row = await session.get(PreviewJobORM, preview_id)
            return bool(row is None or row.cancellation_requested or row.invalidated_at is not None)

    async def get_preview_output_asset_id(self, preview_id: str) -> str | None:
        async with self.session_factory() as session:
            row = await session.get(PreviewJobORM, preview_id)
            return row.output_asset_id if row else None

    async def _set_preview_state(
        self,
        preview_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
    ) -> PreviewRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(PreviewJobORM, preview_id, with_for_update=True)
                if row is None:
                    return None
                timeline = await session.get(TimelineORM, row.timeline_id)
                if timeline is None:
                    return None
                if row.cancellation_requested or row.invalidated_at is not None:
                    row.status = "stale" if row.invalidated_at is not None else "cancelled"
                else:
                    if status is not None:
                        row.status = status
                    if progress is not None:
                        row.progress = max(row.progress, min(progress, 99))
                row.updated_at = utc_now()
            return await self._preview_read(session, row, timeline)

    async def _timeline_read(self, session: AsyncSession, row: TimelineORM) -> TimelineRead:
        version = await session.get(TimelineVersionORM, row.current_version_id)
        if version is None:
            raise RuntimeError("timeline current version is missing")
        preview_valid = False
        if row.latest_preview_id:
            preview = await session.get(PreviewJobORM, row.latest_preview_id)
            preview_valid = bool(
                preview
                and preview.status == "ready"
                and preview.invalidated_at is None
                and preview.timeline_version == row.current_version
            )
        return TimelineRead(
            timeline_id=row.timeline_id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            project_version_id=row.project_version_id,
            source_analysis_id=row.source_analysis_id,
            source_media_plan_id=row.source_media_plan_id,
            current_version_id=row.current_version_id,
            current_version=row.current_version,
            approval_status=row.approval_status,
            approved_timeline_version=row.approved_timeline_version,
            snapshot=TimelineSnapshot.model_validate(version.snapshot_json),
            latest_preview_id=row.latest_preview_id,
            latest_preview_valid=preview_valid,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _preview_read(
        self,
        session: AsyncSession,
        row: PreviewJobORM,
        timeline: TimelineORM,
    ) -> PreviewRead:
        valid = bool(
            row.status == "ready"
            and row.invalidated_at is None
            and row.timeline_version == timeline.current_version
        )
        playback_url = (
            f"/api/v1/projects/{row.project_id}/previews/{row.preview_id}/content"
            if row.output_asset_id and row.status in {"ready", "stale"}
            else None
        )
        return PreviewRead(
            preview_id=row.preview_id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            timeline_id=row.timeline_id,
            timeline_version_id=row.timeline_version_id,
            timeline_version=row.timeline_version,
            status=row.status,
            progress=row.progress,
            width=row.width,
            height=row.height,
            output_asset_id=row.output_asset_id,
            playback_url=playback_url,
            valid_for_current_timeline=valid,
            cancellation_requested=row.cancellation_requested,
            error_code=row.error_code,
            failure_reason=row.failure_reason,
            manifest=row.manifest_json,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


def _version_read(row: TimelineVersionORM) -> TimelineVersionRead:
    return TimelineVersionRead(
        timeline_version_id=row.timeline_version_id,
        timeline_id=row.timeline_id,
        project_id=row.project_id,
        version=row.version,
        snapshot=TimelineSnapshot.model_validate(row.snapshot_json),
        mutation=row.mutation_json,
        actor_ref=row.actor_ref,
        created_at=row.created_at,
    )
