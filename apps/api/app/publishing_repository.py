from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .db import utc_now
from .publishing_db import PublicationEventORM, PublicationORM
from .publishing_models import (
    PlatformValidationRead,
    ProviderValidationRead,
    PublicationEventRead,
    PublicationMetadata,
    PublicationRead,
    PublicationReceipt,
    RightsValidationRead,
)


class PublicationIdempotencyConflict(RuntimeError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class PublishingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def reserve(
        self,
        *,
        workspace_id: str,
        project_id: str,
        package_id: str,
        approval_id: str,
        final_render_id: str,
        output_asset_id: str,
        platform: str,
        provider_key: str,
        capability_version: str,
        mode: str,
        idempotency_key_hash: str,
        request_fingerprint: str,
        metadata: PublicationMetadata,
        actor_ref: str,
    ) -> tuple[PublicationRead, bool]:
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(PublicationORM).where(
                    PublicationORM.project_id == project_id,
                    PublicationORM.idempotency_key_hash == idempotency_key_hash,
                )
            )
            if existing is not None:
                return self._assert_replay(existing, request_fingerprint), True
            now = utc_now()
            row = PublicationORM(
                publication_id=_new_id("pub"),
                workspace_id=workspace_id,
                project_id=project_id,
                package_id=package_id,
                approval_id=approval_id,
                final_render_id=final_render_id,
                output_asset_id=output_asset_id,
                platform=platform,
                provider_key=provider_key,
                capability_version=capability_version,
                mode=mode,
                status="validating",
                idempotency_key_hash=idempotency_key_hash,
                request_fingerprint=request_fingerprint,
                metadata_json=metadata.model_dump(mode="json"),
                rights_validation_json=None,
                platform_validation_json=None,
                provider_validation_json=None,
                receipt_json=None,
                dry_run=mode == "dry_run",
                mock=mode == "dry_run",
                external_action=False,
                attempt_count=1,
                failure_code=None,
                failure_reason=None,
                actor_ref=actor_ref,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            # ORM relationships are intentionally not used; flush the parent so
            # SQLite and PostgreSQL both satisfy the publication-event FK.
            await session.flush()
            session.add(
                PublicationEventORM(
                    event_id=_new_id("pue"),
                    publication_id=row.publication_id,
                    project_id=project_id,
                    event_type="publication.validation_reserved",
                    actor_ref=actor_ref,
                    payload_json={
                        "platform": platform,
                        "mode": mode,
                        "provider_key": provider_key,
                        "external_action": False,
                        "secret_free": True,
                    },
                    created_at=now,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(PublicationORM).where(
                        PublicationORM.project_id == project_id,
                        PublicationORM.idempotency_key_hash == idempotency_key_hash,
                    )
                )
                if existing is None:
                    raise
                return self._assert_replay(existing, request_fingerprint), True
            return _publication_read(row), False

    async def finalize(
        self,
        publication_id: str,
        *,
        status: str,
        rights_validation: RightsValidationRead,
        platform_validation: PlatformValidationRead,
        provider_validation: ProviderValidationRead,
        receipt: PublicationReceipt | None,
        failure_code: str | None,
        failure_reason: str | None,
        actor_ref: str,
    ) -> PublicationRead:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(PublicationORM, publication_id, with_for_update=True)
                if row is None:
                    raise KeyError(publication_id)
                if row.status != "validating":
                    return _publication_read(row)
                row.status = status
                row.rights_validation_json = rights_validation.model_dump(mode="json")
                row.platform_validation_json = platform_validation.model_dump(mode="json")
                row.provider_validation_json = provider_validation.model_dump(mode="json")
                row.receipt_json = receipt.model_dump(mode="json") if receipt else None
                row.external_action = bool(receipt.external_action) if receipt else False
                row.mock = bool(receipt.mock) if receipt else row.mock
                row.failure_code = failure_code
                row.failure_reason = failure_reason[:2000] if failure_reason else None
                row.updated_at = utc_now()
                session.add(
                    PublicationEventORM(
                        event_id=_new_id("pue"),
                        publication_id=row.publication_id,
                        project_id=row.project_id,
                        event_type=(
                            "publication.dry_run_succeeded"
                            if status == "dry_run_succeeded"
                            else "publication.blocked"
                            if status == "blocked"
                            else f"publication.{status}"
                        ),
                        actor_ref=actor_ref,
                        payload_json={
                            "status": status,
                            "failure_code": failure_code,
                            "mock": row.mock,
                            "external_action": row.external_action,
                            "secret_free": True,
                        },
                        created_at=row.updated_at,
                    )
                )
            return _publication_read(row)

    async def get(self, project_id: str, publication_id: str) -> PublicationRead | None:
        async with self.session_factory() as session:
            row = await session.get(PublicationORM, publication_id)
            return _publication_read(row) if row is not None and row.project_id == project_id else None

    async def list(self, project_id: str) -> list[PublicationRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(PublicationORM)
                    .where(PublicationORM.project_id == project_id)
                    .order_by(PublicationORM.created_at.desc())
                )
            ).all()
            return [_publication_read(row) for row in rows]

    async def list_events(self, project_id: str) -> list[PublicationEventRead]:
        async with self.session_factory() as session:
            rows = (
                await session.scalars(
                    select(PublicationEventORM)
                    .where(PublicationEventORM.project_id == project_id)
                    .order_by(PublicationEventORM.created_at.desc())
                )
            ).all()
            return [_event_read(row) for row in rows]

    @staticmethod
    def _assert_replay(row: PublicationORM, fingerprint: str) -> PublicationRead:
        if row.request_fingerprint != fingerprint:
            raise PublicationIdempotencyConflict(
                "Idempotency-Key was already used for a different publication request"
            )
        return _publication_read(row)


def _publication_read(row: PublicationORM) -> PublicationRead:
    return PublicationRead(
        publication_id=row.publication_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        package_id=row.package_id,
        approval_id=row.approval_id,
        final_render_id=row.final_render_id,
        output_asset_id=row.output_asset_id,
        platform=row.platform,
        provider_key=row.provider_key,
        capability_version=row.capability_version,
        mode=row.mode,
        status=row.status,
        request_fingerprint=row.request_fingerprint,
        metadata=PublicationMetadata.model_validate(row.metadata_json),
        rights_validation=(
            RightsValidationRead.model_validate(row.rights_validation_json)
            if row.rights_validation_json
            else None
        ),
        platform_validation=(
            PlatformValidationRead.model_validate(row.platform_validation_json)
            if row.platform_validation_json
            else None
        ),
        provider_validation=(
            ProviderValidationRead.model_validate(row.provider_validation_json)
            if row.provider_validation_json
            else None
        ),
        receipt=PublicationReceipt.model_validate(row.receipt_json) if row.receipt_json else None,
        dry_run=row.dry_run,
        mock=row.mock,
        external_action=row.external_action,
        attempt_count=row.attempt_count,
        failure_code=row.failure_code,
        failure_reason=row.failure_reason,
        actor_ref=row.actor_ref,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_read(row: PublicationEventORM) -> PublicationEventRead:
    return PublicationEventRead(
        event_id=row.event_id,
        publication_id=row.publication_id,
        project_id=row.project_id,
        event_type=row.event_type,
        actor_ref=row.actor_ref,
        payload=dict(row.payload_json or {}),
        created_at=row.created_at,
    )
