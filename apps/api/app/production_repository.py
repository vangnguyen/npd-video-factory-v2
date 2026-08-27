from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import VideoProjectORM, utc_now
from .production_db import (
    AudioMixVersionORM,
    ProductionApprovalORM,
    ProductionEventORM,
    ProductionPackageORM,
    ProductionRenderJobORM,
    SubtitleVersionORM,
)
from .production_models import (
    ApprovalRead,
    AudioMixVersionRead,
    MixConfig,
    ProductionEventRead,
    ProductionPackageRead,
    RenderJobRead,
    SubtitleCue,
    SubtitleStyle,
    SubtitleVersionRead,
)
from .timeline_db import TimelineORM
from .timeline_models import TimelineRead


class ProductionConflictError(RuntimeError):
    def __init__(self, *, entity: str, expected: int, actual: int):
        self.entity = entity
        self.expected = expected
        self.actual = actual
        super().__init__(f"{entity} version conflict: expected {expected}, current version is {actual}")


class ApprovalBoundaryError(RuntimeError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class ProductionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def create_or_refresh_package(
        self,
        *,
        timeline: TimelineRead,
        cues: list[SubtitleCue],
        style: SubtitleStyle,
        mix_config: MixConfig,
        provider_status: str,
        actor_ref: str,
    ) -> tuple[ProductionPackageRead, bool]:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    select(ProductionPackageORM)
                    .where(ProductionPackageORM.project_id == timeline.project_id)
                    .with_for_update()
                )
                if row is not None and row.timeline_version_id == timeline.current_version_id:
                    return await self._package_read(session, row), False

                now = utc_now()
                if row is None:
                    row = ProductionPackageORM(
                        package_id=_new_id("pkg"),
                        workspace_id=timeline.workspace_id,
                        project_id=timeline.project_id,
                        timeline_id=timeline.timeline_id,
                        timeline_version_id=timeline.current_version_id,
                        timeline_version=timeline.current_version,
                        current_subtitle_version_id="pending",
                        current_subtitle_version=1,
                        current_audio_version_id="pending",
                        current_audio_version=1,
                        current_approval_id=None,
                        latest_review_render_id=None,
                        latest_final_render_id=None,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                    # PostgreSQL cannot insert subtitle/audio/event children until the
                    # package parent exists.  The ORM models intentionally avoid
                    # relationship wiring, so make the dependency ordering explicit.
                    await session.flush()
                    subtitle_version = 1
                    audio_version = 1
                    event_type = "production_package.created"
                else:
                    subtitle_version = row.current_subtitle_version + 1
                    audio_version = row.current_audio_version + 1
                    await self._invalidate_locked(
                        session,
                        row,
                        reason="timeline-version-changed",
                        actor_ref=actor_ref,
                    )
                    row.timeline_id = timeline.timeline_id
                    row.timeline_version_id = timeline.current_version_id
                    row.timeline_version = timeline.current_version
                    event_type = "production_package.refreshed"

                subtitle_id = _new_id("stv")
                audio_id = _new_id("amv")
                session.add_all(
                    [
                        SubtitleVersionORM(
                            subtitle_version_id=subtitle_id,
                            package_id=row.package_id,
                            project_id=row.project_id,
                            timeline_version_id=row.timeline_version_id,
                            timeline_version=row.timeline_version,
                            version=subtitle_version,
                            cues_json=[item.model_dump(mode="json") for item in cues],
                            style_json=style.model_dump(mode="json"),
                            actor_ref=actor_ref,
                            created_at=now,
                        ),
                        AudioMixVersionORM(
                            audio_version_id=audio_id,
                            package_id=row.package_id,
                            project_id=row.project_id,
                            timeline_version_id=row.timeline_version_id,
                            timeline_version=row.timeline_version,
                            version=audio_version,
                            config_json=mix_config.model_dump(mode="json"),
                            provider_status=provider_status,
                            actor_ref=actor_ref,
                            created_at=now,
                        ),
                    ]
                )
                row.current_subtitle_version_id = subtitle_id
                row.current_subtitle_version = subtitle_version
                row.current_audio_version_id = audio_id
                row.current_audio_version = audio_version
                row.current_approval_id = None
                row.latest_review_render_id = None
                row.latest_final_render_id = None
                row.updated_at = now
                await self._event(
                    session,
                    package=row,
                    event_type=event_type,
                    entity_type="package",
                    entity_id=row.package_id,
                    actor_ref=actor_ref,
                    payload={
                        "timeline_version": row.timeline_version,
                        "subtitle_version": subtitle_version,
                        "audio_version": audio_version,
                        "provider_status": provider_status,
                        "publishing_allowed": False,
                    },
                )
            return await self._package_read(session, row), True

    async def get_package(self, project_id: str) -> ProductionPackageRead | None:
        async with self.session_factory() as session:
            row = await session.scalar(
                select(ProductionPackageORM).where(ProductionPackageORM.project_id == project_id)
            )
            return await self._package_read(session, row) if row else None

    async def replace_subtitles(
        self,
        *,
        project_id: str,
        expected_timeline_version: int,
        expected_subtitle_version: int,
        cues: list[SubtitleCue],
        style: SubtitleStyle,
        actor_ref: str,
        reason: str,
    ) -> ProductionPackageRead:
        async with self.session_factory() as session:
            async with session.begin():
                package = await self._locked_package(session, project_id)
                await self._assert_current_timeline(session, package, expected_timeline_version)
                if package.current_subtitle_version != expected_subtitle_version:
                    raise ProductionConflictError(
                        entity="subtitle",
                        expected=expected_subtitle_version,
                        actual=package.current_subtitle_version,
                    )
                version = package.current_subtitle_version + 1
                version_id = _new_id("stv")
                now = utc_now()
                session.add(
                    SubtitleVersionORM(
                        subtitle_version_id=version_id,
                        package_id=package.package_id,
                        project_id=package.project_id,
                        timeline_version_id=package.timeline_version_id,
                        timeline_version=package.timeline_version,
                        version=version,
                        cues_json=[item.model_dump(mode="json") for item in cues],
                        style_json=style.model_dump(mode="json"),
                        actor_ref=actor_ref,
                        created_at=now,
                    )
                )
                await self._invalidate_locked(session, package, reason=reason, actor_ref=actor_ref)
                package.current_subtitle_version_id = version_id
                package.current_subtitle_version = version
                package.updated_at = now
                await self._event(
                    session,
                    package=package,
                    event_type="subtitles.version_created",
                    entity_type="subtitle_version",
                    entity_id=version_id,
                    actor_ref=actor_ref,
                    payload={"version": version, "cue_count": len(cues), "reason": reason},
                )
            return await self._package_read(session, package)

    async def replace_audio_mix(
        self,
        *,
        project_id: str,
        expected_timeline_version: int,
        expected_audio_version: int,
        config: MixConfig,
        provider_status: str,
        actor_ref: str,
        reason: str,
    ) -> ProductionPackageRead:
        async with self.session_factory() as session:
            async with session.begin():
                package = await self._locked_package(session, project_id)
                await self._assert_current_timeline(session, package, expected_timeline_version)
                if package.current_audio_version != expected_audio_version:
                    raise ProductionConflictError(
                        entity="audio",
                        expected=expected_audio_version,
                        actual=package.current_audio_version,
                    )
                version = package.current_audio_version + 1
                version_id = _new_id("amv")
                now = utc_now()
                session.add(
                    AudioMixVersionORM(
                        audio_version_id=version_id,
                        package_id=package.package_id,
                        project_id=package.project_id,
                        timeline_version_id=package.timeline_version_id,
                        timeline_version=package.timeline_version,
                        version=version,
                        config_json=config.model_dump(mode="json"),
                        provider_status=provider_status,
                        actor_ref=actor_ref,
                        created_at=now,
                    )
                )
                await self._invalidate_locked(session, package, reason=reason, actor_ref=actor_ref)
                package.current_audio_version_id = version_id
                package.current_audio_version = version
                package.updated_at = now
                await self._event(
                    session,
                    package=package,
                    event_type="audio_mix.version_created",
                    entity_type="audio_version",
                    entity_id=version_id,
                    actor_ref=actor_ref,
                    payload={
                        "version": version,
                        "provider_status": provider_status,
                        "music_asset_configured": config.music.asset_id is not None,
                        "reason": reason,
                    },
                )
            return await self._package_read(session, package)

    async def create_render(
        self,
        *,
        project_id: str,
        expected_timeline_version: int,
        expected_subtitle_version: int,
        expected_audio_version: int,
        render_kind: str,
        profile: str,
        actor_ref: str,
        approval_id: str | None = None,
    ) -> RenderJobRead:
        async with self.session_factory() as session:
            async with session.begin():
                package = await self._locked_package(session, project_id)
                await self._assert_current_timeline(session, package, expected_timeline_version)
                self._assert_package_versions(package, expected_subtitle_version, expected_audio_version)
                if render_kind == "final":
                    approval = await session.get(ProductionApprovalORM, approval_id)
                    if approval is None or approval.package_id != package.package_id:
                        raise ApprovalBoundaryError("approved review package was not found")
                    self._assert_approval_current(package, approval)
                next_version = int(
                    (
                        await session.scalar(
                            select(func.max(ProductionRenderJobORM.version)).where(
                                ProductionRenderJobORM.package_id == package.package_id,
                                ProductionRenderJobORM.render_kind == render_kind,
                            )
                        )
                    )
                    or 0
                ) + 1
                render = ProductionRenderJobORM(
                    render_id=_new_id("rnd"),
                    version=next_version,
                    package_id=package.package_id,
                    workspace_id=package.workspace_id,
                    project_id=package.project_id,
                    timeline_id=package.timeline_id,
                    timeline_version_id=package.timeline_version_id,
                    timeline_version=package.timeline_version,
                    subtitle_version_id=package.current_subtitle_version_id,
                    subtitle_version=package.current_subtitle_version,
                    audio_version_id=package.current_audio_version_id,
                    audio_version=package.current_audio_version,
                    approval_id=approval_id,
                    render_kind=render_kind,
                    profile=profile,
                    status="queued",
                    progress=0,
                    output_asset_id=None,
                    qc_status="pending",
                    qc_report_json={},
                    manifest_json={
                        "renderer": "remotion-timeline-v1",
                        "audio_mix": "ffmpeg-v2-08",
                        "publishing_allowed": False,
                        "requested_by": actor_ref,
                    },
                    cancellation_requested=False,
                    invalidated_at=None,
                    error_code=None,
                    failure_reason=None,
                )
                session.add(render)
                if render_kind == "review":
                    package.latest_review_render_id = render.render_id
                else:
                    package.latest_final_render_id = render.render_id
                package.updated_at = utc_now()
                await self._event(
                    session,
                    package=package,
                    event_type=f"render.{render_kind}_queued",
                    entity_type="render",
                    entity_id=render.render_id,
                    actor_ref=actor_ref,
                    payload={"version": next_version, "profile": profile, "approval_id": approval_id},
                )
            return _render_read(render)

    async def get_render(self, render_id: str) -> RenderJobRead | None:
        async with self.session_factory() as session:
            row = await session.get(ProductionRenderJobORM, render_id)
            return _render_read(row) if row else None

    async def get_render_context(
        self, render_id: str
    ) -> tuple[RenderJobRead, SubtitleVersionRead, AudioMixVersionRead, dict[str, Any]] | None:
        from .timeline_db import TimelineVersionORM

        async with self.session_factory() as session:
            render = await session.get(ProductionRenderJobORM, render_id)
            if render is None:
                return None
            subtitle = await session.get(SubtitleVersionORM, render.subtitle_version_id)
            audio = await session.get(AudioMixVersionORM, render.audio_version_id)
            timeline = await session.get(TimelineVersionORM, render.timeline_version_id)
            if subtitle is None or audio is None or timeline is None:
                return None
            return (
                _render_read(render),
                _subtitle_read(subtitle),
                _audio_read(audio),
                dict(timeline.snapshot_json),
            )

    async def start_render(self, render_id: str) -> RenderJobRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(ProductionRenderJobORM, render_id, with_for_update=True)
                if row is None:
                    return None
                if row.status not in {"queued", "running"}:
                    return _render_read(row)
                if row.cancellation_requested:
                    row.status = "cancelled"
                else:
                    row.status = "running"
                    row.progress = max(row.progress, 5)
                row.updated_at = utc_now()
            return _render_read(row)

    async def set_render_progress(self, render_id: str, progress: int) -> None:
        async with self.session_factory() as session:
            await session.execute(
                update(ProductionRenderJobORM)
                .where(ProductionRenderJobORM.render_id == render_id, ProductionRenderJobORM.status == "running")
                .values(progress=max(0, min(99, progress)), updated_at=utc_now())
            )
            await session.commit()

    async def render_cancel_requested(self, render_id: str) -> bool:
        async with self.session_factory() as session:
            value = await session.scalar(
                select(ProductionRenderJobORM.cancellation_requested).where(
                    ProductionRenderJobORM.render_id == render_id
                )
            )
            return bool(value)

    async def complete_render(
        self,
        render_id: str,
        *,
        output_asset_id: str,
        qc_report: dict[str, Any],
        manifest: dict[str, Any],
    ) -> RenderJobRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(ProductionRenderJobORM, render_id, with_for_update=True)
                if row is None:
                    return None
                if row.cancellation_requested or row.status == "stale":
                    row.status = "stale" if row.status == "stale" else "cancelled"
                    row.updated_at = utc_now()
                    return _render_read(row)
                row.status = "awaiting_review" if row.render_kind == "review" else "ready"
                row.progress = 100
                row.output_asset_id = output_asset_id
                row.qc_status = "passed"
                row.qc_report_json = qc_report
                row.manifest_json = manifest
                row.error_code = None
                row.failure_reason = None
                row.updated_at = utc_now()
                package = await session.get(ProductionPackageORM, row.package_id)
                if package:
                    await self._event(
                        session,
                        package=package,
                        event_type=f"render.{row.render_kind}_completed",
                        entity_type="render",
                        entity_id=row.render_id,
                        actor_ref="render-worker",
                        payload={
                            "qc_status": "passed",
                            "checksum_sha256": manifest.get("output_checksum_sha256"),
                            "publishing_allowed": False,
                        },
                    )
            return _render_read(row)

    async def fail_render(
        self,
        render_id: str,
        *,
        code: str,
        reason: str,
        qc_report: dict[str, Any] | None = None,
    ) -> RenderJobRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(ProductionRenderJobORM, render_id, with_for_update=True)
                if row is None:
                    return None
                if row.status == "stale":
                    return _render_read(row)
                cancelled = row.cancellation_requested or code == "RENDER_CANCELLED"
                row.status = "cancelled" if cancelled else "failed_qc" if code == "QC_FAILED" else "failed"
                row.qc_status = "failed" if code == "QC_FAILED" else row.qc_status
                row.qc_report_json = qc_report or row.qc_report_json
                row.error_code = code
                row.failure_reason = reason[:1000]
                row.updated_at = utc_now()
                package = await session.get(ProductionPackageORM, row.package_id)
                if package:
                    await self._event(
                        session,
                        package=package,
                        event_type=f"render.{row.status}",
                        entity_type="render",
                        entity_id=row.render_id,
                        actor_ref="render-worker",
                        payload={"error_code": code, "secret_free": True},
                    )
            return _render_read(row)

    async def cancel_render(self, project_id: str, render_id: str, actor_ref: str) -> RenderJobRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(ProductionRenderJobORM, render_id, with_for_update=True)
                if row is None or row.project_id != project_id:
                    return None
                if row.status in {"queued", "running"}:
                    row.cancellation_requested = True
                    row.status = "cancelled" if row.status == "queued" else row.status
                    row.updated_at = utc_now()
                package = await session.get(ProductionPackageORM, row.package_id)
                if package:
                    await self._event(
                        session,
                        package=package,
                        event_type="render.cancel_requested",
                        entity_type="render",
                        entity_id=row.render_id,
                        actor_ref=actor_ref,
                        payload={},
                    )
            return _render_read(row)

    async def list_incomplete_render_ids(self) -> list[str]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(ProductionRenderJobORM.render_id)
                    .where(ProductionRenderJobORM.status.in_(["queued", "running"]))
                    .order_by(ProductionRenderJobORM.created_at)
                )
            ).all()
            return list(rows)

    async def request_approval(
        self,
        *,
        project_id: str,
        review_render_id: str,
        requester_ref: str,
        note: str,
    ) -> ApprovalRead:
        async with self.session_factory() as session:
            async with session.begin():
                package = await self._locked_package(session, project_id)
                await self._assert_current_timeline(session, package, package.timeline_version)
                render = await session.get(ProductionRenderJobORM, review_render_id)
                if (
                    render is None
                    or render.package_id != package.package_id
                    or render.render_kind != "review"
                    or render.status != "awaiting_review"
                    or render.qc_status != "passed"
                ):
                    raise ApprovalBoundaryError("approval requires a current review render with passing QC")
                if (
                    render.timeline_version_id != package.timeline_version_id
                    or render.subtitle_version_id != package.current_subtitle_version_id
                    or render.audio_version_id != package.current_audio_version_id
                ):
                    raise ApprovalBoundaryError("review render is stale for the current production package")
                if package.current_approval_id:
                    previous = await session.get(ProductionApprovalORM, package.current_approval_id)
                    if previous and previous.status in {"awaiting_review", "approved"}:
                        previous.status = "changes_requested"
                        previous.invalidated_reason = "superseded-by-new-approval-request"
                        previous.updated_at = utc_now()
                now = utc_now()
                approval = ProductionApprovalORM(
                    approval_id=_new_id("apr"),
                    package_id=package.package_id,
                    project_id=package.project_id,
                    timeline_version_id=package.timeline_version_id,
                    timeline_version=package.timeline_version,
                    preview_render_id=render.render_id,
                    preview_version=render.version,
                    subtitle_version_id=package.current_subtitle_version_id,
                    subtitle_version=package.current_subtitle_version,
                    audio_version_id=package.current_audio_version_id,
                    audio_version=package.current_audio_version,
                    status="awaiting_review",
                    requester_ref=requester_ref,
                    reviewer_ref=None,
                    note=note,
                    decision_comment="",
                    invalidated_reason=None,
                    requested_at=now,
                    decided_at=None,
                    updated_at=now,
                )
                session.add(approval)
                package.current_approval_id = approval.approval_id
                package.updated_at = now
                timeline = await session.get(TimelineORM, package.timeline_id)
                if timeline:
                    timeline.approval_status = "awaiting_review"
                    timeline.approved_timeline_version = None
                    timeline.updated_at = now
                await self._event(
                    session,
                    package=package,
                    event_type="approval.requested",
                    entity_type="approval",
                    entity_id=approval.approval_id,
                    actor_ref=requester_ref,
                    payload={
                        "timeline_version": approval.timeline_version,
                        "preview_version": approval.preview_version,
                        "subtitle_version": approval.subtitle_version,
                        "audio_version": approval.audio_version,
                    },
                )
            return _approval_read(approval)

    async def decide_approval(
        self,
        *,
        project_id: str,
        approval_id: str,
        decision: str,
        reviewer_ref: str,
        comment: str,
    ) -> ApprovalRead:
        async with self.session_factory() as session:
            async with session.begin():
                package = await self._locked_package(session, project_id)
                approval = await session.get(ProductionApprovalORM, approval_id, with_for_update=True)
                if approval is None or approval.package_id != package.package_id:
                    raise KeyError(approval_id)
                if package.current_approval_id != approval_id or approval.status != "awaiting_review":
                    raise ApprovalBoundaryError("only the current awaiting-review package can be decided")
                self._assert_approval_binding(package, approval)
                now = utc_now()
                approval.status = decision
                approval.reviewer_ref = reviewer_ref
                approval.decision_comment = comment
                approval.decided_at = now
                approval.updated_at = now
                timeline = await session.get(TimelineORM, package.timeline_id)
                if timeline:
                    timeline.approval_status = "approved" if decision == "approved" else "changes_requested"
                    timeline.approved_timeline_version = package.timeline_version if decision == "approved" else None
                    timeline.updated_at = now
                await self._event(
                    session,
                    package=package,
                    event_type=f"approval.{decision}",
                    entity_type="approval",
                    entity_id=approval.approval_id,
                    actor_ref=reviewer_ref,
                    payload={"comment_recorded": bool(comment), "publishing_allowed": False},
                )
            return _approval_read(approval)

    async def list_events(self, project_id: str) -> list[ProductionEventRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(ProductionEventORM)
                    .where(ProductionEventORM.project_id == project_id)
                    .order_by(ProductionEventORM.created_at.desc())
                )
            ).all()
            return [_event_read(row) for row in rows]

    async def _locked_package(self, session: AsyncSession, project_id: str) -> ProductionPackageORM:
        package = await session.scalar(
            select(ProductionPackageORM)
            .where(ProductionPackageORM.project_id == project_id)
            .with_for_update()
        )
        if package is None:
            raise KeyError(project_id)
        return package

    async def _assert_current_timeline(
        self, session: AsyncSession, package: ProductionPackageORM, expected_version: int
    ) -> None:
        timeline = await session.get(TimelineORM, package.timeline_id)
        if timeline is None:
            raise KeyError(package.timeline_id)
        if timeline.current_version != expected_version:
            raise ProductionConflictError(
                entity="timeline", expected=expected_version, actual=timeline.current_version
            )
        if package.timeline_version_id != timeline.current_version_id:
            raise ApprovalBoundaryError("production package is stale; refresh it from the current timeline")

    @staticmethod
    def _assert_package_versions(
        package: ProductionPackageORM, expected_subtitle_version: int, expected_audio_version: int
    ) -> None:
        if package.current_subtitle_version != expected_subtitle_version:
            raise ProductionConflictError(
                entity="subtitle",
                expected=expected_subtitle_version,
                actual=package.current_subtitle_version,
            )
        if package.current_audio_version != expected_audio_version:
            raise ProductionConflictError(
                entity="audio",
                expected=expected_audio_version,
                actual=package.current_audio_version,
            )

    @staticmethod
    def _assert_approval_binding(package: ProductionPackageORM, approval: ProductionApprovalORM) -> None:
        if (
            approval.timeline_version_id != package.timeline_version_id
            or approval.timeline_version != package.timeline_version
            or approval.subtitle_version_id != package.current_subtitle_version_id
            or approval.subtitle_version != package.current_subtitle_version
            or approval.audio_version_id != package.current_audio_version_id
            or approval.audio_version != package.current_audio_version
        ):
            raise ApprovalBoundaryError("approval does not match the current version-bound production package")

    @classmethod
    def _assert_approval_current(cls, package: ProductionPackageORM, approval: ProductionApprovalORM) -> None:
        cls._assert_approval_binding(package, approval)
        if package.current_approval_id != approval.approval_id or approval.status != "approved":
            raise ApprovalBoundaryError("final render requires the current approved review package")

    async def _invalidate_locked(
        self,
        session: AsyncSession,
        package: ProductionPackageORM,
        *,
        reason: str,
        actor_ref: str,
    ) -> None:
        now = utc_now()
        if package.current_approval_id:
            approval = await session.get(ProductionApprovalORM, package.current_approval_id)
            if approval and approval.status in {"awaiting_review", "approved"}:
                approval.status = "changes_requested"
                approval.invalidated_reason = reason
                approval.updated_at = now
        await session.execute(
            update(ProductionRenderJobORM)
            .where(
                ProductionRenderJobORM.package_id == package.package_id,
                ProductionRenderJobORM.status.in_(["queued", "running", "awaiting_review", "ready"]),
            )
            .values(
                status="stale",
                cancellation_requested=True,
                invalidated_at=now,
                updated_at=now,
            )
        )
        timeline = await session.get(TimelineORM, package.timeline_id)
        if timeline:
            timeline.approval_status = "draft"
            timeline.approved_timeline_version = None
            timeline.updated_at = now
        package.current_approval_id = None
        package.latest_review_render_id = None
        package.latest_final_render_id = None
        await self._event(
            session,
            package=package,
            event_type="production_package.invalidated",
            entity_type="package",
            entity_id=package.package_id,
            actor_ref=actor_ref,
            payload={"reason": reason},
        )

    async def _package_read(
        self, session: AsyncSession, row: ProductionPackageORM
    ) -> ProductionPackageRead:
        subtitle = await session.get(SubtitleVersionORM, row.current_subtitle_version_id)
        audio = await session.get(AudioMixVersionORM, row.current_audio_version_id)
        if subtitle is None or audio is None:
            raise RuntimeError("production package version references are incomplete")
        approval = await session.get(ProductionApprovalORM, row.current_approval_id) if row.current_approval_id else None
        review = (
            await session.get(ProductionRenderJobORM, row.latest_review_render_id)
            if row.latest_review_render_id
            else None
        )
        final = (
            await session.get(ProductionRenderJobORM, row.latest_final_render_id)
            if row.latest_final_render_id
            else None
        )
        timeline = await session.get(TimelineORM, row.timeline_id)
        return ProductionPackageRead(
            package_id=row.package_id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            timeline_id=row.timeline_id,
            timeline_version_id=row.timeline_version_id,
            timeline_version=row.timeline_version,
            subtitle=_subtitle_read(subtitle),
            audio_mix=_audio_read(audio),
            approval=_approval_read(approval) if approval else None,
            latest_review_render=_render_read(review) if review else None,
            latest_final_render=_render_read(final) if final else None,
            current_for_timeline=bool(
                timeline
                and timeline.current_version_id == row.timeline_version_id
                and timeline.current_version == row.timeline_version
            ),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    async def _event(
        self,
        session: AsyncSession,
        *,
        package: ProductionPackageORM,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor_ref: str,
        payload: dict[str, Any],
    ) -> None:
        session.add(
            ProductionEventORM(
                event_id=_new_id("pev"),
                package_id=package.package_id,
                project_id=package.project_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_ref=actor_ref,
                payload_json=payload,
                created_at=utc_now(),
            )
        )


def _subtitle_read(row: SubtitleVersionORM) -> SubtitleVersionRead:
    return SubtitleVersionRead(
        subtitle_version_id=row.subtitle_version_id,
        package_id=row.package_id,
        project_id=row.project_id,
        timeline_version_id=row.timeline_version_id,
        timeline_version=row.timeline_version,
        version=row.version,
        cues=[SubtitleCue.model_validate(item) for item in row.cues_json],
        style=SubtitleStyle.model_validate(row.style_json),
        actor_ref=row.actor_ref,
        created_at=row.created_at,
    )


def _audio_read(row: AudioMixVersionORM) -> AudioMixVersionRead:
    return AudioMixVersionRead(
        audio_version_id=row.audio_version_id,
        package_id=row.package_id,
        project_id=row.project_id,
        timeline_version_id=row.timeline_version_id,
        timeline_version=row.timeline_version,
        version=row.version,
        config=MixConfig.model_validate(row.config_json),
        provider_status=row.provider_status,
        actor_ref=row.actor_ref,
        created_at=row.created_at,
    )


def _approval_read(row: ProductionApprovalORM) -> ApprovalRead:
    return ApprovalRead(
        approval_id=row.approval_id,
        package_id=row.package_id,
        project_id=row.project_id,
        timeline_version_id=row.timeline_version_id,
        timeline_version=row.timeline_version,
        preview_render_id=row.preview_render_id,
        preview_version=row.preview_version,
        subtitle_version_id=row.subtitle_version_id,
        subtitle_version=row.subtitle_version,
        audio_version_id=row.audio_version_id,
        audio_version=row.audio_version,
        status=row.status,
        requester_ref=row.requester_ref,
        reviewer_ref=row.reviewer_ref,
        note=row.note,
        decision_comment=row.decision_comment,
        invalidated_reason=row.invalidated_reason,
        requested_at=row.requested_at,
        decided_at=row.decided_at,
        updated_at=row.updated_at,
    )


def _render_read(row: ProductionRenderJobORM) -> RenderJobRead:
    return RenderJobRead(
        render_id=row.render_id,
        version=row.version,
        package_id=row.package_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        timeline_id=row.timeline_id,
        timeline_version_id=row.timeline_version_id,
        timeline_version=row.timeline_version,
        subtitle_version_id=row.subtitle_version_id,
        subtitle_version=row.subtitle_version,
        audio_version_id=row.audio_version_id,
        audio_version=row.audio_version,
        approval_id=row.approval_id,
        render_kind=row.render_kind,
        profile=row.profile,
        status=row.status,
        progress=row.progress,
        output_asset_id=row.output_asset_id,
        playback_url=(
            f"/api/v1/projects/{row.project_id}/renders/{row.render_id}/content"
            if row.output_asset_id
            else None
        ),
        qc_status=row.qc_status,
        qc_report=dict(row.qc_report_json or {}),
        manifest=dict(row.manifest_json or {}),
        cancellation_requested=row.cancellation_requested,
        error_code=row.error_code,
        failure_reason=row.failure_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_read(row: ProductionEventORM) -> ProductionEventRead:
    return ProductionEventRead(
        event_id=row.event_id,
        package_id=row.package_id,
        project_id=row.project_id,
        event_type=row.event_type,
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        actor_ref=row.actor_ref,
        payload=dict(row.payload_json or {}),
        created_at=row.created_at,
    )
