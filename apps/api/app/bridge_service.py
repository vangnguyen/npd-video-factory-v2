from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from typing import Protocol

import httpx

from .bridge_auth import SigningKeyring, canonical_json_bytes
from .bridge_models import (
    BRIDGE_CONTRACT_VERSION,
    BridgeContractRead,
    BridgeProjectCreatedResponse,
    BridgeProjectRequestCreate,
    BridgeProjectSummary,
    WebhookDeliveryRead,
)
from .bridge_repository import BridgeRepository
from .db import utc_now
from .platform_models import ProjectCreate, ProjectVersionCreate


WEBHOOK_QUEUE_KEY = "npd:video-factory:v2:bridge:webhooks:queued"
WEBHOOK_PROCESSING_KEY = "npd:video-factory:v2:bridge:webhooks:processing"


class QueueClient(Protocol):
    async def rpush(self, key: str, value: str) -> object: ...


class BridgeBoundaryError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def ensure_secret_free(value: object, *, path: str = "payload") -> None:
    forbidden = ("secret", "token", "password", "credential", "cookie", "api_key", "apikey")
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(term in normalized for term in forbidden):
                raise BridgeBoundaryError("BRIDGE_SECRET_REJECTED", f"Secret-like field is not allowed at {path}.")
            ensure_secret_free(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            ensure_secret_free(child, path=f"{path}[{index}]")
    elif isinstance(value, str) and (value.startswith("Bearer ") or value.startswith("sk-")):
        raise BridgeBoundaryError("BRIDGE_SECRET_REJECTED", f"Secret-like value is not allowed at {path}.")


class AgentHubBridgeService:
    def __init__(
        self,
        *,
        repository: BridgeRepository,
        platform_repository,
        publishing_repository,
        analytics_repository,
        queue: QueueClient,
        default_workspace_id: str,
        webhook_destination_ref: str,
        webhook_provider_mode: str,
        webhook_max_attempts: int,
        production_deployed: bool = False,
    ):
        self.repository = repository
        self.platform_repository = platform_repository
        self.publishing_repository = publishing_repository
        self.analytics_repository = analytics_repository
        self.queue = queue
        self.default_workspace_id = default_workspace_id
        self.webhook_destination_ref = webhook_destination_ref
        self.webhook_provider_mode = webhook_provider_mode
        self.webhook_max_attempts = webhook_max_attempts
        self.production_deployed = production_deployed

    def contract(self) -> BridgeContractRead:
        return BridgeContractRead(
            inbound_actions=["project.create_draft"],
            outbound_events=[
                "trend.opportunity.detected",
                "idea.shortlist.ready",
                "video.project.created",
                "video.analysis.completed",
                "video.preview.ready",
                "video.approval.required",
                "video.approved",
                "video.render.completed",
                "video.render.failed",
                "video.publish.completed",
                "video.publish.failed",
                "video.analytics.updated",
                "video.winner.detected",
            ],
            roles=["owner", "editor", "reviewer", "viewer", "service"],
            production_deployed=self.production_deployed,
        )

    async def create_draft_project(
        self,
        *,
        service_id: str,
        payload: BridgeProjectRequestCreate,
        idempotency_key: str,
    ) -> BridgeProjectCreatedResponse:
        ensure_secret_free(payload.model_dump(mode="json"))
        workspace_id = payload.workspace_id or self.default_workspace_id
        if await self.platform_repository.get_workspace(workspace_id) is None:
            raise KeyError(workspace_id)
        reserved, replay = await self.repository.reserve_request(
            service_id=service_id,
            workspace_id=workspace_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        if replay and reserved.status == "succeeded":
            if not reserved.project_id or not reserved.project_version_id:
                raise BridgeBoundaryError("BRIDGE_REQUEST_INCOMPLETE", "The prior idempotent request is not complete.")
            project = await self.platform_repository.get_project(reserved.project_id)
            version = await self.platform_repository.get_version(reserved.project_version_id)
            if project is None or version is None:
                raise RuntimeError("bridge replay references missing canonical project state")
            return BridgeProjectCreatedResponse(
                bridge_request=reserved,
                project=project,
                project_version=version,
                idempotent_replay=True,
            )
        try:
            project_payload = ProjectCreate(
                slug=payload.slug,
                name=payload.name,
                niche=payload.niche,
                provenance={
                    "source": "agent-hub-bridge.v1",
                    "bridge_request_id": reserved.request_id,
                    "service_id": service_id,
                    "source_campaign_id": payload.source_campaign_id,
                    "draft_only": True,
                },
            )
            try:
                project = await self.platform_repository.create_project(workspace_id, project_payload)
            except ValueError:
                project = await self.platform_repository.ensure_project(workspace_id, project_payload)
                if project.provenance.get("bridge_request_id") != reserved.request_id:
                    raise ValueError("project slug already belongs to another request")
            versions = await self.platform_repository.list_versions(project.project_id)
            version = next(
                (
                    item
                    for item in versions
                    if item.provenance.get("bridge_request_id") == reserved.request_id
                ),
                None,
            )
            if version is None:
                version = await self.platform_repository.create_version(
                    project.project_id,
                    ProjectVersionCreate(
                        label="agent-hub-draft",
                        snapshot={
                            "brief": payload.brief,
                            "source_campaign_id": payload.source_campaign_id,
                            "execution_mode": "draft_only",
                            "pipeline_started": False,
                            "publish_requested": False,
                        },
                        provenance={
                            "source": "agent-hub-bridge.v1",
                            "bridge_request_id": reserved.request_id,
                            "service_id": service_id,
                        },
                    ),
                )
            project = await self.platform_repository.get_project(project.project_id)
            if project is None:
                raise RuntimeError("canonical project disappeared during bridge request")
            completed, _event, delivery = await self.repository.complete_request(
                reserved.request_id,
                project_id=project.project_id,
                project_version_id=version.project_version_id,
                event_payload={
                    "project_id": project.project_id,
                    "project_version_id": version.project_version_id,
                    "workspace_id": workspace_id,
                    "source_campaign_id": payload.source_campaign_id,
                    "status": "draft",
                    "execution_started": False,
                    "external_action": False,
                },
                destination_ref=self.webhook_destination_ref,
                provider_mode=self.webhook_provider_mode,
                max_attempts=self.webhook_max_attempts,
            )
            if delivery.status == "queued":
                await self.queue.rpush(WEBHOOK_QUEUE_KEY, delivery.delivery_id)
            return BridgeProjectCreatedResponse(
                bridge_request=completed,
                project=project,
                project_version=version,
                idempotent_replay=replay,
            )
        except Exception as exc:
            await self.repository.fail_request(
                reserved.request_id,
                code="BRIDGE_PROJECT_CREATE_FAILED",
                reason=f"{type(exc).__name__}: {exc}",
            )
            raise

    async def project_summary(self, project_id: str) -> BridgeProjectSummary:
        project = await self.platform_repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        versions = await self.platform_repository.list_versions(project_id)
        assets = await self.platform_repository.list_assets(project_id)
        costs = await self.platform_repository.project_cost_summary(project_id)
        publications = await self.publishing_repository.list(project_id)
        snapshots = await self.analytics_repository.list_snapshots(project_id)
        return BridgeProjectSummary(
            project=project,
            versions=len(versions),
            assets=len(assets),
            estimated_cost_vnd=str(costs.estimated_cost),
            actual_cost_vnd=str(costs.actual_cost),
            publications=len(publications),
            analytics_snapshots=len(snapshots),
        )


class WebhookProvider(Protocol):
    mode: str
    external_call: bool

    async def deliver(self, *, body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, object]]: ...


class FixtureWebhookProvider:
    mode = "fixture"
    external_call = False

    def __init__(self, keyring: SigningKeyring):
        self.keyring = keyring

    async def deliver(self, *, body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, object]]:
        valid = self.keyring.verify(
            body,
            key_id=headers["X-NPD-Key-Id"],
            timestamp=int(headers["X-NPD-Timestamp"]),
            event_id=headers["X-NPD-Event-Id"],
            signature=headers["X-NPD-Signature"],
        )
        if not valid:
            raise RuntimeError("fixture webhook signature validation failed")
        return 202, {"accepted": True, "mock": True, "external_action": False}


class HttpWebhookProvider:
    mode = "http"
    external_call = True

    def __init__(self, url: str, *, timeout_seconds: float = 10.0):
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def deliver(self, *, body: bytes, headers: dict[str, str]) -> tuple[int, dict[str, object]]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.url, content=body, headers={**headers, "Content-Type": "application/json"})
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"Agent Hub webhook returned HTTP {response.status_code}")
        return response.status_code, {"accepted": True, "mock": False, "external_action": True}


class WebhookDeliveryProcessor:
    def __init__(
        self,
        *,
        repository: BridgeRepository,
        signer: SigningKeyring,
        provider: WebhookProvider,
        retry_base_seconds: int,
        retry_max_seconds: int,
    ):
        self.repository = repository
        self.signer = signer
        self.provider = provider
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds

    async def process(self, delivery_id: str) -> WebhookDeliveryRead:
        delivery = await self.repository.claim_delivery(delivery_id)
        if delivery is None:
            raise KeyError(delivery_id)
        if delivery.status != "running":
            return delivery
        event = await self.repository.get_event(delivery.event_id)
        if event is None:
            return await self.repository.fail_or_retry_delivery(
                delivery_id,
                code="WEBHOOK_EVENT_MISSING",
                reason="Canonical webhook event is missing.",
                next_retry_at=utc_now(),
            )
        body = canonical_json_bytes(
            {
                "contract_version": BRIDGE_CONTRACT_VERSION,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "occurred_at": event.created_at.isoformat(),
                "payload": event.payload,
            }
        )
        timestamp = int(time.time())
        headers = self.signer.sign(body, timestamp=timestamp, event_id=event.event_id)
        try:
            response_status, receipt = await self.provider.deliver(body=body, headers=headers)
            ensure_secret_free(receipt)
            return await self.repository.finish_delivery(
                delivery_id,
                key_id=headers["X-NPD-Key-Id"],
                signed_at_unix=timestamp,
                body_sha256=headers["X-NPD-Content-SHA256"],
                signature=headers["X-NPD-Signature"],
                response_status=response_status,
                receipt={
                    **receipt,
                    "event_id": event.event_id,
                    "contract_version": BRIDGE_CONTRACT_VERSION,
                    "key_id": headers["X-NPD-Key-Id"],
                    "signed_at_unix": timestamp,
                    "body_sha256": headers["X-NPD-Content-SHA256"],
                },
                external_call=self.provider.external_call,
            )
        except Exception as exc:
            delay = min(
                self.retry_max_seconds,
                self.retry_base_seconds * (2 ** max(0, delivery.attempt_count - 1)),
            )
            return await self.repository.fail_or_retry_delivery(
                delivery_id,
                code="WEBHOOK_DELIVERY_FAILED",
                reason=f"{type(exc).__name__}: {exc}",
                next_retry_at=utc_now() + timedelta(seconds=delay),
            )


def create_webhook_provider(settings, signer: SigningKeyring) -> WebhookProvider:
    if settings.agent_hub_webhook_mode == "fixture":
        return FixtureWebhookProvider(signer)
    if settings.agent_hub_webhook_mode == "http":
        if not settings.agent_hub_webhook_external_delivery_enabled:
            raise ValueError("HTTP webhook provider requires its explicit external delivery gate")
        return HttpWebhookProvider(
            settings.agent_hub_webhook_url,
            timeout_seconds=settings.agent_hub_webhook_timeout_seconds,
        )
    raise ValueError("disabled webhook mode has no delivery processor")


async def webhook_scheduler(repository: BridgeRepository, queue: QueueClient) -> None:
    while True:
        for delivery_id in await repository.activate_due_delivery_ids():
            await queue.rpush(WEBHOOK_QUEUE_KEY, delivery_id)
        await asyncio.sleep(5)
