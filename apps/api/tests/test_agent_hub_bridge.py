from __future__ import annotations

import base64
import json
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.analytics_repository import AnalyticsRepository
from app.bridge_auth import (
    ServiceAuthError,
    ServiceAuthVerifier,
    ServiceIdentity,
    SigningKeyring,
    canonical_json_bytes,
    sign_service_request,
)
from app.bridge_models import BridgeProjectRequestCreate
from app.bridge_repository import BridgeIdempotencyConflict, BridgeRepository
from app.bridge_service import (
    AgentHubBridgeService,
    BridgeBoundaryError,
    FixtureWebhookProvider,
    WebhookDeliveryProcessor,
)
from app.db import Base, create_engine, create_session_factory, utc_now
from app.main import app
from app.platform_models import ProjectCreate, ProjectVersionCreate, WorkspaceCreate
from app.publishing_repository import PublishingRepository
from app.repositories import PlatformRepository


KEY_V1 = b"v2-11-fixture-key-v1-at-least-32-bytes"
KEY_V2 = b"v2-11-fixture-key-v2-at-least-32-bytes"


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.queue: list[str] = []

    async def set(self, key: str, value: str, *, ex: int, nx: bool):
        assert ex >= 300 and nx is True
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def rpush(self, _key: str, value: str):
        self.queue.append(value)
        return len(self.queue)


async def bridge_stack(tmp_path: Path):
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'bridge.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(slug="bridge-test", name="Bridge Test", owner_ref="owner-fixture")
    )
    redis = FakeRedis()
    repository = BridgeRepository(session_factory)
    service = AgentHubBridgeService(
        repository=repository,
        platform_repository=platform,
        publishing_repository=PublishingRepository(session_factory),
        analytics_repository=AnalyticsRepository(session_factory),
        queue=redis,
        default_workspace_id=workspace.workspace_id,
        webhook_destination_ref="agent-hub-fixture",
        webhook_provider_mode="fixture",
        webhook_max_attempts=3,
    )
    verifier = ServiceAuthVerifier(
        {
            "agent-hub": ServiceIdentity(
                service_id="agent-hub",
                roles=("service",),
                keys={"v1": KEY_V1},
            )
        },
        redis,
    )
    return SimpleNamespace(
        engine=engine,
        platform=platform,
        workspace=workspace,
        redis=redis,
        repository=repository,
        service=service,
        verifier=verifier,
    )


def payload(**overrides) -> BridgeProjectRequestCreate:
    values = {
        "slug": "vinh-tien-agent-hub-draft",
        "name": "Vịnh Tiên Agent Hub Draft",
        "niche": "real_estate",
        "source_campaign_id": "CMP-VGP-VINHTIEN-202609-01",
        "brief": {"objective": "lead_generation", "language": "vi"},
    }
    values.update(overrides)
    return BridgeProjectRequestCreate(**values)


@pytest.mark.asyncio
async def test_service_auth_validates_body_timestamp_unknown_key_and_replay() -> None:
    redis = FakeRedis()
    now = int(time.time())
    verifier = ServiceAuthVerifier(
        {"agent-hub": ServiceIdentity("agent-hub", ("service",), {"v1": KEY_V1})},
        redis,
        now=lambda: now,
    )
    body = b'{"safe":true}'
    headers = sign_service_request(
        key=KEY_V1,
        service_id="agent-hub",
        key_id="v1",
        method="POST",
        path="/api/v1/bridge/project-requests",
        body=body,
        timestamp=now,
        nonce="nonce-0000000001",
    )
    identity = await verifier.verify(
        method="POST",
        path="/api/v1/bridge/project-requests",
        query="",
        body=body,
        headers=headers,
    )
    assert identity.service_id == "agent-hub" and identity.roles == ("service",)
    malformed_nonce = sign_service_request(
        key=KEY_V1,
        service_id="agent-hub",
        key_id="v1",
        method="POST",
        path="/api/v1/bridge/project-requests",
        body=body,
        timestamp=now,
        nonce="too-short",
    )
    with pytest.raises(ServiceAuthError, match="invalid"):
        await verifier.verify(
            method="POST",
            path="/api/v1/bridge/project-requests",
            query="",
            body=body,
            headers=malformed_nonce,
        )
    with pytest.raises(ServiceAuthError, match="already been used"):
        await verifier.verify(
            method="POST",
            path="/api/v1/bridge/project-requests",
            query="",
            body=body,
            headers=headers,
        )
    unknown = {**headers, "X-NPD-Key-Id": "unknown", "X-NPD-Nonce": "nonce-0000000002"}
    with pytest.raises(ServiceAuthError, match="invalid"):
        await verifier.verify(method="POST", path="/api/v1/bridge/project-requests", query="", body=body, headers=unknown)
    expired = sign_service_request(
        key=KEY_V1,
        service_id="agent-hub",
        key_id="v1",
        method="POST",
        path="/api/v1/bridge/project-requests",
        body=body,
        timestamp=now - 301,
        nonce="nonce-0000000003",
    )
    with pytest.raises(ServiceAuthError, match="timestamp"):
        await verifier.verify(method="POST", path="/api/v1/bridge/project-requests", query="", body=body, headers=expired)
    changed = sign_service_request(
        key=KEY_V1,
        service_id="agent-hub",
        key_id="v1",
        method="POST",
        path="/api/v1/bridge/project-requests",
        body=body,
        timestamp=now,
        nonce="nonce-0000000004",
    )
    with pytest.raises(ServiceAuthError, match="invalid"):
        await verifier.verify(method="POST", path="/api/v1/bridge/project-requests", query="", body=b'{"safe":false}', headers=changed)


@pytest.mark.asyncio
async def test_bridge_creates_draft_only_project_and_signed_fixture_webhook(tmp_path: Path) -> None:
    stack = await bridge_stack(tmp_path)
    created = await stack.service.create_draft_project(
        service_id="agent-hub",
        payload=payload(),
        idempotency_key="v2-11-project-request-0001",
    )
    assert created.project.status == "draft"
    assert created.project.current_version_id == created.project_version.project_version_id
    assert created.bridge_request.execution_started is False
    assert created.bridge_request.external_action is False
    assert stack.redis.queue
    replay = await stack.service.create_draft_project(
        service_id="agent-hub",
        payload=payload(),
        idempotency_key="v2-11-project-request-0001",
    )
    assert replay.idempotent_replay is True and replay.project.project_id == created.project.project_id
    with pytest.raises(BridgeIdempotencyConflict):
        await stack.service.create_draft_project(
            service_id="agent-hub",
            payload=payload(name="Different payload"),
            idempotency_key="v2-11-project-request-0001",
        )

    keyring = SigningKeyring(active_key_id="v2", keys={"v1": KEY_V1, "v2": KEY_V2})
    processor = WebhookDeliveryProcessor(
        repository=stack.repository,
        signer=keyring,
        provider=FixtureWebhookProvider(keyring),
        retry_base_seconds=30,
        retry_max_seconds=300,
    )
    delivery = await processor.process(stack.redis.queue[0])
    assert delivery.status == "succeeded"
    assert delivery.key_id == "v2" and delivery.external_call is False
    assert delivery.signed_at_unix is not None
    assert delivery.receipt and delivery.receipt["mock"] is True
    assert delivery.receipt["signed_at_unix"] == delivery.signed_at_unix
    event = (await stack.repository.list_events(project_id=created.project.project_id))[0]
    webhook_body = canonical_json_bytes(
        {
            "contract_version": "agent-hub-bridge.v1",
            "event_id": event.event_id,
            "event_type": event.event_type,
            "occurred_at": event.created_at.isoformat(),
            "payload": event.payload,
        }
    )
    assert keyring.verify(
        webhook_body,
        key_id=delivery.key_id,
        timestamp=delivery.signed_at_unix,
        event_id=delivery.event_id,
        signature=delivery.signature or "",
    )
    serialized = json.dumps(delivery.model_dump(mode="json"), default=str).lower()
    assert "v2-11-fixture-key" not in serialized and "token" not in serialized
    await stack.engine.dispose()


@pytest.mark.asyncio
async def test_bridge_rejects_secret_fields_and_recovers_retry_state(tmp_path: Path) -> None:
    stack = await bridge_stack(tmp_path)
    with pytest.raises(BridgeBoundaryError, match="Secret-like field"):
        await stack.service.create_draft_project(
            service_id="agent-hub",
            payload=payload(brief={"access_token": "not-allowed"}),
            idempotency_key="v2-11-secret-rejection-0001",
        )
    created = await stack.service.create_draft_project(
        service_id="agent-hub",
        payload=payload(slug="retry-project", name="Retry Project"),
        idempotency_key="v2-11-retry-request-0001",
    )
    deliveries = await stack.repository.list_deliveries(project_id=created.project.project_id)

    class FailingProvider:
        mode = "fixture"
        external_call = False

        async def deliver(self, **_kwargs):
            raise RuntimeError("deterministic failure")

    processor = WebhookDeliveryProcessor(
        repository=stack.repository,
        signer=SigningKeyring(active_key_id="v2", keys={"v1": KEY_V1, "v2": KEY_V2}),
        provider=FailingProvider(),
        retry_base_seconds=30,
        retry_max_seconds=300,
    )
    first = await processor.process(deliveries[0].delivery_id)
    assert first.status == "retry_scheduled" and first.next_retry_at is not None
    due = await stack.repository.activate_due_delivery_ids(at=utc_now() + timedelta(hours=1))
    assert due == [first.delivery_id]
    recovered = BridgeRepository(stack.service.repository.session_factory)
    assert await recovered.recover_incomplete_delivery_ids() == [first.delivery_id]
    await stack.engine.dispose()


@pytest.mark.asyncio
async def test_bridge_resumes_a_partially_materialized_idempotent_request(tmp_path: Path) -> None:
    stack = await bridge_stack(tmp_path)
    request_payload = payload(slug="resume-project", name="Resume Project")
    reserved, replay = await stack.repository.reserve_request(
        service_id="agent-hub",
        workspace_id=stack.workspace.workspace_id,
        payload=request_payload,
        idempotency_key="v2-11-partial-recovery-0001",
    )
    assert replay is False and reserved.status == "reserved"
    project = await stack.platform.create_project(
        stack.workspace.workspace_id,
        ProjectCreate(
            slug=request_payload.slug,
            name=request_payload.name,
            niche=request_payload.niche,
            provenance={
                "source": "agent-hub-bridge.v1",
                "bridge_request_id": reserved.request_id,
                "service_id": "agent-hub",
                "source_campaign_id": request_payload.source_campaign_id,
                "draft_only": True,
            },
        ),
    )
    version = await stack.platform.create_version(
        project.project_id,
        ProjectVersionCreate(
            label="agent-hub-draft",
            snapshot={"execution_mode": "draft_only"},
            provenance={
                "source": "agent-hub-bridge.v1",
                "bridge_request_id": reserved.request_id,
                "service_id": "agent-hub",
            },
        ),
    )
    recovered = await stack.service.create_draft_project(
        service_id="agent-hub",
        payload=request_payload,
        idempotency_key="v2-11-partial-recovery-0001",
    )
    assert recovered.idempotent_replay is True
    assert recovered.project.project_id == project.project_id
    assert recovered.project_version.project_version_id == version.project_version_id
    assert len(await stack.platform.list_versions(project.project_id)) == 1
    assert stack.redis.queue
    await stack.engine.dispose()


def test_signing_keyring_supports_rotation_historical_verification_and_reload(tmp_path: Path) -> None:
    config_path = tmp_path / "service-keys.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "service_identities": {
                    "agent-hub": {"roles": ["service"], "keys": {"v1": base64.b64encode(KEY_V1).decode()}}
                },
                "webhook_signing": {
                    "active_key_id": "v2",
                    "keys": {
                        "v1": base64.b64encode(KEY_V1).decode(),
                        "v2": base64.b64encode(KEY_V2).decode(),
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    keyring = SigningKeyring.from_file(config_path)
    body = canonical_json_bytes({"event": "safe"})
    headers = keyring.sign(body, timestamp=1_800_000_000, event_id="bevt_rotation")
    assert headers["X-NPD-Key-Id"] == "v2"
    assert keyring.verify(
        body,
        key_id="v2",
        timestamp=1_800_000_000,
        event_id="bevt_rotation",
        signature=headers["X-NPD-Signature"],
    )
    old = SigningKeyring(active_key_id="v1", keys={"v1": KEY_V1}).sign(
        body, timestamp=1_700_000_000, event_id="bevt_historical"
    )
    assert keyring.verify(
        body,
        key_id="v1",
        timestamp=1_700_000_000,
        event_id="bevt_historical",
        signature=old["X-NPD-Signature"],
    )
    assert not keyring.verify(body, key_id="unknown", timestamp=1, event_id="x", signature="0" * 64)
    assert not keyring.verify(body + b"x", key_id="v2", timestamp=1_800_000_000, event_id="bevt_rotation", signature=headers["X-NPD-Signature"])
    reloaded = SigningKeyring.from_file(config_path)
    assert reloaded.active_key_id == "v2" and set(reloaded.keys) == {"v1", "v2"}


@pytest.mark.asyncio
async def test_bridge_api_requires_signed_service_role_and_preserves_contract(tmp_path: Path) -> None:
    stack = await bridge_stack(tmp_path)
    app.state.agent_hub_bridge_service = stack.service
    app.state.bridge_auth_verifier = stack.verifier
    body = canonical_json_bytes(payload().model_dump(mode="json"))
    path = "/api/v1/bridge/project-requests"
    headers = sign_service_request(
        key=KEY_V1,
        service_id="agent-hub",
        key_id="v1",
        method="POST",
        path=path,
        body=body,
        nonce="api-nonce-00000001",
    )
    headers["Idempotency-Key"] = "v2-11-api-request-0001"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        contract_path = "/api/v1/bridge/contract"
        contract_headers = sign_service_request(
            key=KEY_V1,
            service_id="agent-hub",
            key_id="v1",
            method="GET",
            path=contract_path,
            nonce="api-contract-000001",
        )
        contract = await client.get(contract_path, headers=contract_headers)
        assert contract.status_code == 200
        assert contract.json()["production_deployed"] is False
        assert "trend.opportunity.detected" in contract.json()["outbound_events"]
        unsigned = await client.post(path, content=body, headers={"Content-Type": "application/json"})
        assert unsigned.status_code in {400, 401}
        response = await client.post(path, content=body, headers={**headers, "Content-Type": "application/json"})
        assert response.status_code == 201
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["Cache-Control"] == "no-store"
        assert len(response.headers["X-Request-ID"]) == 32
        result = response.json()
        assert result["project"]["status"] == "draft"
        assert result["bridge_request"]["execution_started"] is False
        summary_path = f"/api/v1/bridge/projects/{result['project']['project_id']}/summary"
        summary_headers = sign_service_request(
            key=KEY_V1,
            service_id="agent-hub",
            key_id="v1",
            method="GET",
            path=summary_path,
            nonce="api-nonce-00000002",
        )
        summary = await client.get(summary_path, headers=summary_headers)
        assert summary.status_code == 200
        assert summary.json()["execution_controlled_by_video_factory"] is True
        assert float(summary.json()["actual_cost_vnd"]) == 0
    await stack.engine.dispose()
