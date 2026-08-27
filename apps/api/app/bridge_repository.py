from __future__ import annotations

import hashlib
import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .bridge_auth import canonical_json_bytes
from .bridge_db import BridgeEventORM, BridgeRequestORM, WebhookDeliveryORM
from .bridge_models import (
    BRIDGE_CONTRACT_VERSION,
    BridgeEventRead,
    BridgeProjectRequestCreate,
    BridgeProjectRequestRead,
    WebhookDeliveryRead,
)
from .db import utc_now


class BridgeIdempotencyConflict(RuntimeError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def request_fingerprint(payload: BridgeProjectRequestCreate) -> str:
    return hashlib.sha256(canonical_json_bytes(payload.model_dump(mode="json"))).hexdigest()


def idempotency_hash(service_id: str, key: str) -> str:
    return hashlib.sha256(f"{service_id}|{key}".encode("utf-8")).hexdigest()


class BridgeRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def reserve_request(
        self,
        *,
        service_id: str,
        workspace_id: str,
        payload: BridgeProjectRequestCreate,
        idempotency_key: str,
    ) -> tuple[BridgeProjectRequestRead, bool]:
        key_hash = idempotency_hash(service_id, idempotency_key)
        fingerprint = request_fingerprint(payload)
        async with self.session_factory() as session:
            existing = await session.scalar(
                select(BridgeRequestORM).where(
                    BridgeRequestORM.service_id == service_id,
                    BridgeRequestORM.idempotency_key_hash == key_hash,
                )
            )
            if existing is not None:
                return self._assert_replay(existing, fingerprint), True
            now = utc_now()
            row = BridgeRequestORM(
                request_id=_new_id("breq"),
                contract_version=BRIDGE_CONTRACT_VERSION,
                service_id=service_id,
                workspace_id=workspace_id,
                project_id=None,
                project_version_id=None,
                status="reserved",
                idempotency_key_hash=key_hash,
                request_fingerprint=fingerprint,
                request_json=payload.model_dump(mode="json"),
                result_json=None,
                failure_code=None,
                failure_reason=None,
                execution_started=False,
                external_action=False,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(BridgeRequestORM).where(
                        BridgeRequestORM.service_id == service_id,
                        BridgeRequestORM.idempotency_key_hash == key_hash,
                    )
                )
                if existing is None:
                    raise
                return self._assert_replay(existing, fingerprint), True
            return _request_read(row), False

    async def complete_request(
        self,
        request_id: str,
        *,
        project_id: str,
        project_version_id: str,
        event_payload: dict[str, object],
        destination_ref: str,
        provider_mode: str,
        max_attempts: int,
    ) -> tuple[BridgeProjectRequestRead, BridgeEventRead, WebhookDeliveryRead]:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(BridgeRequestORM, request_id, with_for_update=True)
                if row is None:
                    raise KeyError(request_id)
                if row.status == "succeeded":
                    event = await session.scalar(
                        select(BridgeEventORM).where(BridgeEventORM.request_id == request_id)
                    )
                    if event is None:
                        raise RuntimeError("completed bridge request is missing its event")
                    delivery = await session.scalar(
                        select(WebhookDeliveryORM).where(WebhookDeliveryORM.event_id == event.event_id)
                    )
                    if delivery is None:
                        raise RuntimeError("completed bridge event is missing its delivery")
                    return _request_read(row), _event_read(event), _delivery_read(delivery)
                now = utc_now()
                row.project_id = project_id
                row.project_version_id = project_version_id
                row.status = "succeeded"
                row.result_json = {
                    "project_id": project_id,
                    "project_version_id": project_version_id,
                    "execution_started": False,
                    "external_action": False,
                }
                row.updated_at = now
                event = BridgeEventORM(
                    event_id=_new_id("bevt"),
                    request_id=request_id,
                    project_id=project_id,
                    contract_version=BRIDGE_CONTRACT_VERSION,
                    event_type="video.project.created",
                    payload_json=event_payload,
                    contains_secret=False,
                    created_at=now,
                )
                session.add(event)
                await session.flush()
                delivery = WebhookDeliveryORM(
                    delivery_id=_new_id("wdl"),
                    event_id=event.event_id,
                    destination_ref=destination_ref,
                    provider_mode=provider_mode,
                    status="queued" if provider_mode != "disabled" else "not_configured",
                    attempt_count=0,
                    max_attempts=max_attempts,
                    external_call=False,
                    failure_code=("WEBHOOK_NOT_CONFIGURED" if provider_mode == "disabled" else None),
                    failure_reason=("Webhook delivery is disabled by configuration." if provider_mode == "disabled" else None),
                    created_at=now,
                    updated_at=now,
                )
                session.add(delivery)
                await session.flush()
                return _request_read(row), _event_read(event), _delivery_read(delivery)

    async def fail_request(self, request_id: str, *, code: str, reason: str) -> BridgeProjectRequestRead:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(BridgeRequestORM, request_id, with_for_update=True)
                if row is None:
                    raise KeyError(request_id)
                row.status = "failed"
                row.failure_code = code
                row.failure_reason = reason[:2000]
                row.updated_at = utc_now()
            return _request_read(row)

    async def get_request(self, request_id: str) -> BridgeProjectRequestRead | None:
        async with self.session_factory() as session:
            row = await session.get(BridgeRequestORM, request_id)
            return _request_read(row) if row else None

    async def list_events(self, *, project_id: str | None = None) -> list[BridgeEventRead]:
        query = select(BridgeEventORM)
        if project_id is not None:
            query = query.where(BridgeEventORM.project_id == project_id)
        query = query.order_by(BridgeEventORM.created_at.desc())
        async with self.session_factory() as session:
            rows = (await session.scalars(query)).all()
            return [_event_read(row) for row in rows]

    async def list_deliveries(self, *, project_id: str | None = None) -> list[WebhookDeliveryRead]:
        query = select(WebhookDeliveryORM).join(BridgeEventORM)
        if project_id is not None:
            query = query.where(BridgeEventORM.project_id == project_id)
        query = query.order_by(WebhookDeliveryORM.created_at.desc())
        async with self.session_factory() as session:
            rows = (await session.scalars(query)).all()
            return [_delivery_read(row) for row in rows]

    async def get_event(self, event_id: str) -> BridgeEventRead | None:
        async with self.session_factory() as session:
            row = await session.get(BridgeEventORM, event_id)
            return _event_read(row) if row else None

    async def get_delivery(self, delivery_id: str) -> WebhookDeliveryRead | None:
        async with self.session_factory() as session:
            row = await session.get(WebhookDeliveryORM, delivery_id)
            return _delivery_read(row) if row else None

    async def claim_delivery(self, delivery_id: str) -> WebhookDeliveryRead | None:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(WebhookDeliveryORM, delivery_id, with_for_update=True)
                if row is None:
                    return None
                if row.status != "queued":
                    return _delivery_read(row)
                row.status = "running"
                row.attempt_count += 1
                row.next_retry_at = None
                row.updated_at = utc_now()
            return _delivery_read(row)

    async def finish_delivery(
        self,
        delivery_id: str,
        *,
        key_id: str,
        signed_at_unix: int,
        body_sha256: str,
        signature: str,
        response_status: int,
        receipt: dict[str, object],
        external_call: bool,
    ) -> WebhookDeliveryRead:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(WebhookDeliveryORM, delivery_id, with_for_update=True)
                if row is None:
                    raise KeyError(delivery_id)
                row.status = "succeeded"
                row.key_id = key_id
                row.signed_at_unix = signed_at_unix
                row.body_sha256 = body_sha256
                row.signature = signature
                row.response_status = response_status
                row.receipt_json = receipt
                row.failure_code = None
                row.failure_reason = None
                row.external_call = external_call
                row.updated_at = utc_now()
            return _delivery_read(row)

    async def fail_or_retry_delivery(
        self,
        delivery_id: str,
        *,
        code: str,
        reason: str,
        next_retry_at: datetime,
    ) -> WebhookDeliveryRead:
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(WebhookDeliveryORM, delivery_id, with_for_update=True)
                if row is None:
                    raise KeyError(delivery_id)
                exhausted = row.attempt_count >= row.max_attempts
                row.status = "failed" if exhausted else "retry_scheduled"
                row.failure_code = code
                row.failure_reason = reason[:2000]
                row.next_retry_at = None if exhausted else next_retry_at
                row.updated_at = utc_now()
            return _delivery_read(row)

    async def recover_incomplete_delivery_ids(self) -> list[str]:
        async with self.session_factory() as session:
            async with session.begin():
                rows = (
                    await session.scalars(
                        select(WebhookDeliveryORM).where(WebhookDeliveryORM.status.in_(("queued", "running")))
                    )
                ).all()
                for row in rows:
                    if row.status == "running":
                        row.status = "queued"
                        row.updated_at = utc_now()
                return [row.delivery_id for row in rows]

    async def activate_due_delivery_ids(self, *, at: datetime | None = None) -> list[str]:
        effective = at or utc_now()
        async with self.session_factory() as session:
            async with session.begin():
                rows = (
                    await session.scalars(
                        select(WebhookDeliveryORM)
                        .where(
                            WebhookDeliveryORM.status == "retry_scheduled",
                            or_(WebhookDeliveryORM.next_retry_at.is_(None), WebhookDeliveryORM.next_retry_at <= effective),
                        )
                        .with_for_update()
                    )
                ).all()
                for row in rows:
                    row.status = "queued"
                    row.next_retry_at = None
                    row.updated_at = effective
                return [row.delivery_id for row in rows]

    @staticmethod
    def _assert_replay(row: BridgeRequestORM, fingerprint: str) -> BridgeProjectRequestRead:
        if row.request_fingerprint != fingerprint:
            raise BridgeIdempotencyConflict("Idempotency-Key was already used for a different bridge request")
        return _request_read(row)


def _request_read(row: BridgeRequestORM) -> BridgeProjectRequestRead:
    return BridgeProjectRequestRead(
        request_id=row.request_id,
        contract_version=row.contract_version,
        service_id=row.service_id,
        workspace_id=row.workspace_id,
        project_id=row.project_id,
        project_version_id=row.project_version_id,
        status=row.status,
        request=row.request_json,
        result=row.result_json,
        failure_code=row.failure_code,
        failure_reason=row.failure_reason,
        execution_started=False,
        external_action=False,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event_read(row: BridgeEventORM) -> BridgeEventRead:
    return BridgeEventRead(
        event_id=row.event_id,
        request_id=row.request_id,
        project_id=row.project_id,
        contract_version=row.contract_version,
        event_type=row.event_type,
        payload=row.payload_json,
        contains_secret=False,
        created_at=row.created_at,
    )


def _delivery_read(row: WebhookDeliveryORM) -> WebhookDeliveryRead:
    return WebhookDeliveryRead(
        delivery_id=row.delivery_id,
        event_id=row.event_id,
        destination_ref=row.destination_ref,
        provider_mode=row.provider_mode,
        status=row.status,
        attempt_count=row.attempt_count,
        max_attempts=row.max_attempts,
        key_id=row.key_id,
        signed_at_unix=row.signed_at_unix,
        body_sha256=row.body_sha256,
        signature=row.signature,
        response_status=row.response_status,
        receipt=row.receipt_json,
        failure_code=row.failure_code,
        failure_reason=row.failure_reason,
        next_retry_at=row.next_retry_at,
        external_call=row.external_call,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
