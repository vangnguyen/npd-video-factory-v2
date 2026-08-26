from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.db import Base, create_engine, create_session_factory
from app.models import Artifact, JobRecord, JobStage, JobStatus, VideoJobCreate
from app.object_storage import LocalObjectStorageProvider, artifact_object_key, sha256_file
from app.platform_models import CostRecordRead, ProjectCreate, WorkspaceCreate
from app.repositories import PlatformRepository, PostgresJobStore


class FakeRedis:
    def __init__(self) -> None:
        self.queue: list[str] = []

    async def rpush(self, _key: str, value: str) -> None:
        self.queue.append(value)


def request_payload() -> VideoJobCreate:
    root = Path(__file__).resolve().parents[3]
    return VideoJobCreate.model_validate_json(
        (root / "examples" / "vinhomes-green-paradise.request.json").read_text(encoding="utf-8")
    )


async def schema(tmp_path: Path):
    database_path = tmp_path / "durable.db"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, create_session_factory(engine)


def built_in_providers() -> list[dict[str, object]]:
    return [
        {
            "provider_key": "deterministic-content",
            "display_name": "Deterministic Content Fixture",
            "capability": "content",
            "adapter": "fixture",
            "routing_mode": "primary",
            "status": "healthy",
            "enabled": True,
            "supports_dry_run": True,
        }
    ]


@pytest.mark.asyncio
async def test_workspace_project_version_and_job_survive_repository_restart(tmp_path: Path) -> None:
    engine, session_factory = await schema(tmp_path)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(
            slug="npd-test",
            name="NPD Test",
            owner_ref="test-owner",
            provenance={"fixture": True},
        )
    )
    project = await platform.create_project(
        workspace.workspace_id,
        ProjectCreate(slug="vinhomes-green-paradise", name="Vinhomes Green Paradise", niche="real_estate"),
    )
    version = await platform.ensure_initial_version(project.project_id, snapshot={"title": "initial"})
    redis = FakeRedis()
    store = PostgresJobStore(session_factory, redis)  # type: ignore[arg-type]
    request = request_payload()
    record = JobRecord.new(
        job_id="vid_durable_1234",
        request=request,
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
        project_version_id=version.project_version_id,
    )
    created = await store.create(record, idempotency_key="same-request")
    duplicate = await store.create(
        JobRecord.new(
            job_id="vid_different_5678",
            request=request,
            workspace_id=workspace.workspace_id,
            project_id=project.project_id,
            project_version_id=version.project_version_id,
        ),
        idempotency_key="same-request",
    )
    assert duplicate.job_id == created.job_id
    await store.enqueue(created.job_id)
    assert redis.queue == [created.job_id]
    await store.update_stage(
        created.job_id,
        status=JobStatus.RUNNING,
        stage=JobStage.SCRIPTING,
        progress=10,
    )
    await engine.dispose()

    restarted_engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'durable.db').as_posix()}")
    restarted_store = PostgresJobStore(create_session_factory(restarted_engine), redis)  # type: ignore[arg-type]
    recovered = await restarted_store.get(created.job_id)
    assert recovered is not None
    assert recovered.workspace_id == workspace.workspace_id
    assert recovered.project_id == project.project_id
    assert recovered.project_version_id == version.project_version_id
    assert recovered.stage == JobStage.SCRIPTING
    events = await restarted_store.list_events(created.job_id)
    assert [event.event_type for event in events] == ["job.created", "job.transitioned"]
    await restarted_engine.dispose()


@pytest.mark.asyncio
async def test_idempotency_key_is_scoped_to_workspace(tmp_path: Path) -> None:
    engine, session_factory = await schema(tmp_path)
    platform = PlatformRepository(session_factory)
    first_workspace = await platform.create_workspace(
        WorkspaceCreate(slug="first-workspace", name="First", owner_ref="owner-a")
    )
    second_workspace = await platform.create_workspace(
        WorkspaceCreate(slug="second-workspace", name="Second", owner_ref="owner-b")
    )
    store = PostgresJobStore(session_factory, FakeRedis())  # type: ignore[arg-type]
    first = await store.create(
        JobRecord.new(
            job_id="vid_workspace_first",
            request=request_payload(),
            workspace_id=first_workspace.workspace_id,
        ),
        idempotency_key="shared-client-key",
    )
    second = await store.create(
        JobRecord.new(
            job_id="vid_workspace_second",
            request=request_payload(),
            workspace_id=second_workspace.workspace_id,
        ),
        idempotency_key="shared-client-key",
    )
    assert first.job_id != second.job_id
    await engine.dispose()


@pytest.mark.asyncio
async def test_object_storage_artifact_and_asset_metadata_are_persisted(tmp_path: Path) -> None:
    engine, session_factory = await schema(tmp_path)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(slug="npd-assets", name="NPD Assets", owner_ref="test-owner")
    )
    project = await platform.create_project(
        workspace.workspace_id,
        ProjectCreate(slug="asset-project", name="Asset Project"),
    )
    version = await platform.ensure_initial_version(project.project_id, snapshot={})
    object_storage = LocalObjectStorageProvider(tmp_path / "objects")
    await object_storage.ensure_ready()
    redis = FakeRedis()
    store = PostgresJobStore(
        session_factory,
        redis,  # type: ignore[arg-type]
        platform=platform,
        object_storage=object_storage,
    )
    record = JobRecord.new(
        job_id="vid_asset_1234",
        request=request_payload(),
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
        project_version_id=version.project_version_id,
    )
    await store.create(record)
    artifact_file = tmp_path / "final.mp4"
    artifact_file.write_bytes(b"deterministic-video")
    object_key = artifact_object_key(
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
        job_id=record.job_id,
        filename=artifact_file.name,
    )
    stored = await object_storage.put_file(object_key=object_key, path=artifact_file)
    updated = await store.add_artifact(
        record.job_id,
        artifact=Artifact(
            kind="video",
            name="final.mp4",
            url=f"/api/v1/video-jobs/{record.job_id}/artifacts/final.mp4",
            object_key=stored.object_key,
            checksum_sha256=stored.checksum_sha256,
            size_bytes=stored.size_bytes,
            storage_provider=stored.storage_provider,
            content_type=stored.content_type,
        ),
    )
    assert updated.artifacts[0].asset_id is not None
    assets = await platform.list_assets(project.project_id)
    assert len(assets) == 1
    assert assets[0].checksum_sha256 == sha256_file(artifact_file)
    assert assets[0].asset_class == "render"
    recovery = tmp_path / "recovered.mp4"
    await object_storage.download_file(object_key=object_key, destination=recovery)
    assert recovery.read_bytes() == artifact_file.read_bytes()
    await engine.dispose()


@pytest.mark.asyncio
async def test_provider_usage_and_vnd_cost_summary_are_idempotent(tmp_path: Path) -> None:
    engine, session_factory = await schema(tmp_path)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(slug="npd-costs", name="NPD Costs", owner_ref="test-owner")
    )
    project = await platform.create_project(
        workspace.workspace_id,
        ProjectCreate(slug="cost-project", name="Cost Project"),
    )
    await platform.seed_providers(built_in_providers())
    seeded = await platform.list_providers(capability="content")
    assert seeded[0].version == 1
    await platform.seed_providers(built_in_providers())
    assert (await platform.list_providers(capability="content"))[0].version == 1
    first_usage, first_cost = await platform.record_provider_operation(
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
        job_id=None,
        provider_key="deterministic-content",
        capability="content",
        operation="content.fixture",
        estimated_cost=Decimal("0"),
        actual_cost=Decimal("0"),
    )
    second_usage, second_cost = await platform.record_provider_operation(
        workspace_id=workspace.workspace_id,
        project_id=project.project_id,
        job_id=None,
        provider_key="deterministic-content",
        capability="content",
        operation="content.fixture",
        estimated_cost=Decimal("999"),
        actual_cost=Decimal("999"),
    )
    assert second_usage.usage_id == first_usage.usage_id
    assert second_cost.cost_id == first_cost.cost_id
    summary = await platform.project_cost_summary(project.project_id)
    assert summary.currency == "VND"
    assert summary.actual_cost == 0
    assert summary.records == 1
    with pytest.raises(ValidationError):
        CostRecordRead.model_validate({**first_cost.model_dump(), "currency": "USD"})
    await engine.dispose()


@pytest.mark.asyncio
async def test_local_object_storage_rejects_path_traversal(tmp_path: Path) -> None:
    provider = LocalObjectStorageProvider(tmp_path / "objects")
    source = tmp_path / "source.txt"
    source.write_text("safe", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid object key"):
        await provider.put_file(object_key="../secret.txt", path=source)
