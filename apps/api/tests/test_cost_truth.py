"""Real isolated persistence; all provider responses and approvals are explicit fixtures."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from decimal import Decimal

import pytest

from app.auto_edit_models import AutoEditAnalysisRequest, MediaMetadata
from app.auto_edit_providers import DeterministicTranscriptionProvider
from app.db import create_engine, create_session_factory
from app.models import JobRecord
from app.platform_models import ProjectCreate, WorkspaceCreate
from app.repositories import PlatformRepository, PostgresJobStore
from test_analytics_learning import analytics_stack, request
from test_assemblyai_direct_asr import FakeTransport, _fixture, _provider
from test_auto_edit_analysis import setup_services, synthetic_mp4, upload_fixture
from test_durable_platform import FakeRedis, built_in_providers, request_payload, schema


async def cost_stack(tmp_path):
    engine, sessions = await schema(tmp_path)
    platform = PlatformRepository(sessions)
    workspaces = []
    projects = []
    for number in range(2):
        workspace = await platform.create_workspace(
            WorkspaceCreate(slug=f"cost-truth-{number}", name="Cost fixture", owner_ref="fixture-owner")
        )
        project = await platform.create_project(
            workspace.workspace_id, ProjectCreate(slug="shared-slug", name="Cost fixture")
        )
        workspaces.append(workspace)
        projects.append(project)
    await platform.seed_providers(built_in_providers())
    return engine, sessions, platform, workspaces, projects


async def record(platform, workspace, project, operation, *, estimate=None, actual=None, **kwargs):
    return await platform.record_provider_operation(
        workspace_id=workspace.workspace_id, project_id=project.project_id, job_id=None,
        provider_key="deterministic-content", capability="content", operation=operation,
        estimated_cost=estimate, actual_cost=actual, **kwargs,
    )


@pytest.mark.asyncio
async def test_partial_cost_totals_preserve_null_and_known_subtotals_after_restart(tmp_path):
    engine, _, platform, workspaces, projects = await cost_stack(tmp_path)
    empty = await platform.project_cost_summary(projects[0].project_id)
    assert empty.records == 0
    assert empty.actual_cost_total == empty.estimated_cost_total == 0
    assert empty.actual_cost_complete and empty.estimated_cost_complete
    assert empty.totals_basis == "recorded_operations_only_v1"
    # Known zero, estimated-only, billed-only and entirely unpriced are distinct.
    await record(platform, workspaces[0], projects[0], "zero", estimate=Decimal(0), actual=Decimal(0))
    await record(platform, workspaces[0], projects[0], "estimated", estimate=Decimal(50))
    await record(platform, workspaces[0], projects[0], "billed", actual=Decimal(70))
    await record(platform, workspaces[0], projects[0], "unpriced")
    await record(platform, workspaces[1], projects[1], "billed", estimate=Decimal(900), actual=Decimal(800))
    summary = await platform.project_cost_summary(projects[0].project_id)
    assert summary.records == 4 and summary.unpriced_operations == 1
    assert summary.estimated_cost == 50 and summary.actual_cost == 70
    assert summary.unknown_actual_cost_operations == summary.unknown_estimated_cost_operations == 2
    assert summary.actual_cost_total is None and summary.estimated_cost_total is None
    assert not summary.actual_cost_complete and not summary.estimated_cost_complete
    serialized = summary.model_dump(mode="json")
    assert serialized["actual_cost_total"] is None
    assert serialized["estimated_cost_total"] is None
    await engine.dispose()
    restarted_engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'durable.db').as_posix()}")
    restarted = PlatformRepository(create_session_factory(restarted_engine))
    assert await restarted.project_cost_summary(projects[0].project_id) == summary
    before = await restarted.list_cost_records(projects[0].project_id)
    # A replay must not invent a missing billed receipt or rewrite original evidence.
    _, replay = await record(restarted, workspaces[0], projects[0], "estimated", actual=Decimal(999))
    assert replay.actual_cost is None and replay.estimated_cost == 50
    assert await restarted.list_cost_records(projects[0].project_id) == before
    assert (await restarted.project_cost_summary(projects[1].project_id)).actual_cost_total == 800
    await restarted_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["estimate", "actual"])
async def test_estimated_and_actual_coverage_are_independent(tmp_path, missing):
    engine, _, platform, workspaces, projects = await cost_stack(tmp_path)
    await record(platform, workspaces[0], projects[0], "one-sided",
                 estimate=None if missing == "estimate" else Decimal(5),
                 actual=None if missing == "actual" else Decimal(7))
    summary = await platform.project_cost_summary(projects[0].project_id)
    assert summary.estimated_cost_complete is (missing != "estimate")
    assert summary.actual_cost_complete is (missing != "actual")
    assert summary.estimated_cost_total == (None if missing == "estimate" else Decimal(5))
    assert summary.actual_cost_total == (None if missing == "actual" else Decimal(7))
    assert summary.unpriced_operations == 0
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
@pytest.mark.parametrize("field", ["estimated_cost", "actual_cost", "max_cost_vnd"])
async def test_invalid_cost_cannot_enter_durable_ledger(tmp_path, amount, field):
    engine, _, platform, workspaces, projects = await cost_stack(tmp_path)
    with pytest.raises(ValueError, match="finite and non-negative"):
        await platform.record_provider_operation(
            workspace_id=workspaces[0].workspace_id, project_id=projects[0].project_id, job_id=None,
            provider_key="deterministic-content", capability="content", operation="invalid", **{field: amount})
    assert (await platform.project_cost_summary(projects[0].project_id)).records == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_foreign_project_or_job_cannot_pollute_cost_ledger(tmp_path):
    engine, sessions, platform, workspaces, projects = await cost_stack(tmp_path)
    job_store = PostgresJobStore(sessions, FakeRedis())
    job = await job_store.create(JobRecord.new(
        job_id="vid_cost_scope_fixture", request=request_payload(),
        workspace_id=workspaces[1].workspace_id, project_id=projects[1].project_id,
    ), idempotency_key="cost-fixture")
    with pytest.raises(ValueError, match="project scope mismatch"):
        await record(platform, workspaces[0], projects[1], "foreign-project", actual=Decimal(10))
    for workspace, project, job_id in [
        (workspaces[0], projects[0], job.job_id),
        (workspaces[1], projects[1], "vid_cost_missing_fixture"),
        (workspaces[1], None, job.job_id),
    ]:
        with pytest.raises(ValueError, match="job scope mismatch"):
            await platform.record_provider_operation(
                workspace_id=workspace.workspace_id, project_id=project.project_id if project else None,
                job_id=job_id, provider_key="deterministic-content", capability="content", operation="foreign-job")
    for project in projects:
        assert (await platform.project_cost_summary(project.project_id)).records == 0
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(("estimate", "actual", "needs_approval"), [
    (None, None, True), (Decimal(11), None, True), (Decimal(10), None, False),
    (None, Decimal(0), False),
])
async def test_unknown_cost_with_explicit_limit_requires_approval(tmp_path, estimate, actual, needs_approval):
    engine, _, platform, workspaces, projects = await cost_stack(tmp_path)
    _, cost = await record(platform, workspaces[0], projects[0], "budget",
                           estimate=estimate, actual=actual, max_cost_vnd=Decimal(10))
    assert cost.needs_approval is needs_approval
    assert (await platform.project_cost_summary(projects[0].project_id)).needs_approval is needs_approval
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("credit_debit", [None, 0, 12.5])
async def test_asr_duration_rate_and_untyped_credit_are_not_billed_vnd(tmp_path, credit_debit):
    source = tmp_path / "fixture.wav"
    source.write_bytes(b"synthetic-wave")
    result = _fixture("asset01.synthetic.json")
    result["credit_debit"] = credit_debit
    transcript = await _provider(FakeTransport(result)).transcribe(
        source, metadata=MediaMetadata(media_kind="audio", detected_content_type="audio/wav", duration_seconds=2),
        checksum_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    assert transcript.actual_cost_vnd is None
    assert Decimal(transcript.provenance["estimated_cost_vnd"]) == Decimal("4.650000")
    assert transcript.provenance["provider_credit_debit"] == credit_debit
    assert transcript.provenance["cost_basis"] == "configured_rate_times_observed_duration; billed_cost_unavailable"


class UnknownBillingFixture(DeterministicTranscriptionProvider):
    def __init__(self, estimate):
        self.estimated_cost_vnd = estimate

    async def transcribe(self, *args, **kwargs):
        transcript = await super().transcribe(*args, **kwargs)
        return replace(transcript, actual_cost_vnd=None)


class ExplicitReservationFixture:
    """Exercise the real service with an explicit, non-billed reservation receipt."""
    def __init__(self, controller):
        self.controller = controller

    async def execute(self, *args, **kwargs):
        result = await self.controller.execute(*args, **kwargs)
        return replace(result, receipt=result.receipt.model_copy(update={"charged_cost_vnd": Decimal(1000)}))


@pytest.mark.asyncio
@pytest.mark.parametrize("estimate", [None, Decimal(300)])
async def test_analysis_persists_unknown_billing_separately_from_reservation(tmp_path, estimate):
    engine, _, platform, _, uploads, service, project, version = await setup_services(tmp_path)
    service.transcription_provider = UnknownBillingFixture(estimate)
    service.provider_safety = ExplicitReservationFixture(service.provider_safety)
    uploaded = await upload_fixture(uploads, project, version, synthetic_mp4())
    analysis = await service.analyze(project.project_id, AutoEditAnalysisRequest(asset_id=uploaded.asset_id))
    assert analysis.status == "succeeded" and analysis.transcript is not None
    costs = await platform.list_cost_records(project.project_id)
    transcript_cost = next(item for item in costs if item.actual_cost is None)
    assert transcript_cost.estimated_cost == estimate
    assert len(costs) == 2
    summary = await platform.project_cost_summary(project.project_id)
    assert summary.actual_cost_total is None and not summary.actual_cost_complete
    assert summary.unknown_actual_cost_operations == 1
    from app.db import ProviderUsageORM
    async with platform.session_factory() as session:
        usage = await session.get(ProviderUsageORM, transcript_cost.provider_usage_id)
        assert usage.metadata_json["budget_reserved_vnd"] == "1000"
        assert usage.metadata_json["budget_reservation_is_billed_cost"] is False
        assert usage.metadata_json["actual_cost_known"] is False
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("billing", ["estimated_only", "partial_actual", "complete_actual"])
async def test_winner_never_treats_estimates_or_partial_actual_as_observed_spend(tmp_path, billing):
    stack = await analytics_stack(tmp_path)
    platform = stack.production.platform
    project = stack.production.project
    await platform.seed_providers(built_in_providers())
    await platform.record_provider_operation(
        workspace_id=project.workspace_id, project_id=project.project_id, job_id=None,
        provider_key="deterministic-content", capability="content", operation="cost-input-1",
        estimated_cost=Decimal(200), actual_cost=None if billing == "estimated_only" else Decimal(70),
    )
    if billing == "partial_actual":
        await platform.record_provider_operation(
            workspace_id=project.workspace_id, project_id=project.project_id, job_id=None,
            provider_key="deterministic-content", capability="content", operation="cost-input-2",
            estimated_cost=Decimal(500), actual_cost=None,
        )
    sync, _ = await stack.service.create_sync(project_id=project.project_id,
        payload=request(stack.publication.publication_id), idempotency_key=f"cost-{billing}-fixture")
    assert (await stack.processor.process(sync.sync_id)).status == "succeeded"
    report = await stack.repository.report(project.project_id)
    factor = next(item for item in report.latest_assessment.factors if item.factor == "production_cost_efficiency")
    assert factor.evidence["production_cost_vnd"] == (70 if billing == "complete_actual" else None)
    assert (factor.score is not None) is (billing == "complete_actual")
    assert any("recorded operations only" in item for item in report.latest_assessment.evidence)
    assert report.latest_assessment.automatic_action is False
    await stack.production.engine.dispose()
