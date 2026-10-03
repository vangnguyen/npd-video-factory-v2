"""Durable proposal jobs on the existing jobs/project-version/provider/cost stores.

Only the explicitly selected offline fixture adapter is executable here. Contract
mode fails closed, never selects a vendor, loads a credential or falls back.
"""
from __future__ import annotations

import difflib
import hashlib
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select, update

from .content_models import ContentDocument, ContentGenerationResult, ContentGenerateRequest, ContentSaveRequest
from .content_service import ContentConflictError, ContentService, canonical_bytes, script_scenes
from .db import JobORM, ProjectVersionORM, VideoProjectORM, utc_now
from .models import ContentGenerationJobInput, JobRecord, JobStage
from .repositories import PostgresJobStore, _version_read

CONTENT_QUEUE = "npd:video-factory:v2:content-generation:queued"
FIXTURE_KEY = "fixture-storyboard-content"


class ContentProviderUnavailable(ValueError):
    pass


class StoryboardContentProvider(Protocol):
    key: str
    async def generate(self, document: ContentDocument) -> ContentGenerationResult: ...


class FixtureStoryboardContentProvider:
    key = FIXTURE_KEY

    async def generate(self, document: ContentDocument) -> ContentGenerationResult:
        # Deliberately not creative AI. No instructions/URLs/unverified property
        # facts from arbitrary input are copied into narration or executed.
        script = "Đây là bản đề xuất thử nghiệm nội bộ.\nThông tin cụ thể cần được bổ sung và kiểm chứng trước khi sử dụng."
        return ContentGenerationResult(script=script, scenes=script_scenes(script),
            facts_needing_source=["Fixture không hiểu ý tưởng/prompt và không xác minh dữ kiện.",
                                 "Cần kịch bản thực, nguồn thông tin và người duyệt trước nghiệm thu."])


def content_provider_definition(mode: str) -> dict:
    enabled = mode == "fixture"
    return {"provider_key": FIXTURE_KEY, "display_name": "Offline storyboard fixture (not AI)",
        "capability": "content_generation", "adapter": "app.content_generation.FixtureStoryboardContentProvider",
        "routing_mode": "primary" if enabled else "disabled", "enabled": enabled,
        "status": "healthy" if enabled else "not_configured", "supports_dry_run": True,
        "metadata": {"paid": False, "ci_safe": True, "fixture": True, "real_provider_accepted": False}}


class ContentGenerationService:
    def __init__(self, *, platform, store, queue, mode="contract", provider=None):
        self.platform, self.store, self.queue, self.mode = platform, store, queue, mode
        self.content = ContentService(platform)
        self.provider = provider or FixtureStoryboardContentProvider()

    async def availability(self):
        providers = await self.platform.list_providers(capability="content_generation")
        allowed = self.mode == "fixture" and any(p.provider_key == FIXTURE_KEY and p.enabled
            and p.status == "healthy" and p.routing_mode == "primary" for p in providers)
        return {"provider_key": FIXTURE_KEY if allowed else None,
            "status": "FIXTURE_ONLY" if allowed else "CONTENT_PROVIDER_NOT_CONFIGURED",
            "external_call": False, "real_provider_accepted": False}

    async def create(self, project_id: str, payload: ContentGenerateRequest, *, actor_ref: str):
        available = await self.availability()
        if available["status"] != "FIXTURE_ONLY" or self.provider.key != FIXTURE_KEY:
            raise ContentProviderUnavailable("CONTENT_PROVIDER_NOT_CONFIGURED: write a script manually; no provider was called")
        project = await self.platform.get_project(project_id)
        current = await self.content.latest(project_id)
        if project is None:
            raise KeyError(project_id)
        if current is None or current.project_version_id != payload.expected_content_version_id:
            raise ContentConflictError("save/reload the current input version before generation")
        fingerprint = hashlib.sha256(canonical_bytes([project_id, current.project_version_id,
            FIXTURE_KEY, payload.idempotency_key])).hexdigest()
        identifier = f"job_content_{fingerprint[:24]}"
        record = JobRecord.new(job_id=identifier, workspace_id=project.workspace_id, project_id=project_id,
            project_version_id=current.project_version_id,
            request=ContentGenerationJobInput(content_version_id=current.project_version_id, actor_ref=actor_ref))
        created = await self.store.create(record, idempotency_key=f"content-generation-{fingerprint}")
        if created.status.value == "queued":
            await self.queue.rpush(CONTENT_QUEUE, created.job_id)
        return await self.get(project_id, identifier)

    async def get(self, project_id: str, generation_id: str):
        record = await self.store.get(generation_id)
        if record is None or record.project_id != project_id or not isinstance(record.request, ContentGenerationJobInput):
            raise KeyError(generation_id)
        proposal = await self.platform.get_version(record.artifacts[0].url) if record.artifacts else None
        if proposal and (proposal.project_id != project_id or proposal.workspace_id != record.workspace_id
                         or proposal.source_job_id != generation_id or proposal.label != "mvp1-content-proposal"):
            raise KeyError(generation_id)
        return {"job": record.model_dump(mode="json"),
            "proposal": proposal.model_dump(mode="json") if proposal else None,
            "provider_status": "FIXTURE_ONLY", "external_call": False}

    async def latest(self, project_id: str):
        async with self.platform.session_factory() as session:
            rows = (await session.scalars(select(JobORM).where(JobORM.project_id == project_id)
                .order_by(JobORM.created_at.desc()))).all()
            identifier = next((r.job_id for r in rows if r.request_json.get("kind") == "content_generation"), None)
        return await self.get(project_id, identifier) if identifier else None

    async def process(self, generation_id: str):
        async with self.platform.session_factory() as session:
            async with session.begin():
                row = await session.scalar(update(JobORM).where(JobORM.job_id == generation_id,
                    JobORM.status == "queued", JobORM.request_json["kind"].as_string() == "content_generation")
                    .values(status="running", stage="scripting", progress=10, updated_at=utc_now())
                    .returning(JobORM))
                if row is None:
                    return  # Duplicate queue delivery or restart never re-executes a claimed job.
                session.add(PostgresJobStore._event(row=row, event_type="content.generation_claimed",
                    actor_ref=row.request_json["actor_ref"]))
                project_id, source_id, actor = row.project_id, row.project_version_id, row.request_json["actor_ref"]
        try:
            source = await self.platform.get_version(source_id)
            if source is None or source.project_id != project_id or (await self.availability())["status"] != "FIXTURE_ONLY":
                raise ContentProviderUnavailable("CONTENT_PROVIDER_NOT_CONFIGURED")
            document = ContentDocument.model_validate(source.snapshot["content"])
            result = ContentGenerationResult.model_validate(await self.provider.generate(document))
            proposal = ContentDocument.model_validate({**document.model_dump(), **result.model_dump(),
                "generator": "fixture-storyboard-v1", "approved": False})
            await self.platform.record_provider_operation(workspace_id=source.workspace_id, project_id=project_id,
                job_id=generation_id, provider_key=FIXTURE_KEY, capability="content_generation",
                operation="storyboard-proposal", model="offline-fixture-v1", estimated_cost=Decimal(0),
                actual_cost=Decimal(0), metadata={"fixture": True, "external_call": False, "human_accepted": False})
            async with self.platform.session_factory() as session:
                async with session.begin():
                    await session.scalar(select(VideoProjectORM).where(VideoProjectORM.project_id == project_id).with_for_update())
                    row = await session.get(JobORM, generation_id, with_for_update=True)
                    if row.status != "running":
                        return  # Cancellation wins; no proposal can resurrect it.
                    current = await session.scalar(select(ProjectVersionORM).where(
                        ProjectVersionORM.project_id == project_id, ProjectVersionORM.label == "mvp1-content")
                        .order_by(ProjectVersionORM.ordinal.desc()).limit(1))
                    stale = current is None or current.project_version_id != source_id
                    ordinal = await session.scalar(select(func.max(ProjectVersionORM.ordinal)).where(ProjectVersionORM.project_id == project_id))
                    version = ProjectVersionORM(project_version_id=f"pver_{generation_id.removeprefix('job_content_')}",
                        workspace_id=source.workspace_id, project_id=project_id, ordinal=int(ordinal or 0)+1,
                        label="mvp1-content-proposal", source_job_id=generation_id, snapshot={"content": proposal.model_dump(mode="json")},
                        provenance={"base_content_version_id": source_id, "actor_ref": actor,
                            "content_sha256": hashlib.sha256(canonical_bytes(proposal.model_dump(mode="json"))).hexdigest(),
                            "script_diff": list(difflib.unified_diff(document.script.splitlines(), proposal.script.splitlines(), lineterm="")),
                            "provider": FIXTURE_KEY, "external_call": False, "fixture": True, "stale": stale})
                    session.add(version)
                    await session.flush()
                    row.artifacts_json = [{"kind": "script", "name": "content-proposal.json", "url": version.project_version_id}]
                    row.status, row.stage, row.progress = ("failed", "failed", 100) if stale else ("awaiting_review", "storyboarding", 100)
                    row.error_json = {"code": "CONTENT_RESPONSE_STALE", "message": "input changed; proposal cannot overwrite it",
                        "failed_stage": "storyboarding", "retryable": False} if stale else None
                    row.updated_at = utc_now()
                    session.add(PostgresJobStore._event(row=row, event_type="content.proposal_stale" if stale else "content.proposal_ready", actor_ref=actor))
        except Exception:
            async with self.platform.session_factory() as session:
                async with session.begin():
                    row = await session.get(JobORM, generation_id, with_for_update=True)
                    if row and row.status == "running":
                        row.status, row.stage = "failed", "failed"
                        row.error_json = {"code": "CONTENT_GENERATION_FAILED", "message": "generation failed; input preserved",
                            "failed_stage": "scripting", "retryable": False}
                        row.updated_at = utc_now()
                        session.add(PostgresJobStore._event(row=row, event_type="content.generation_failed", actor_ref=actor))

    async def cancel(self, project_id: str, generation_id: str, *, actor_ref: str):
        await self.get(project_id, generation_id)
        async with self.platform.session_factory() as session:
            async with session.begin():
                row = await session.get(JobORM, generation_id, with_for_update=True)
                if row.status in {"queued", "running", "awaiting_review"}:
                    row.status, row.stage = "cancelled", "failed"
                    row.updated_at = utc_now()
                    session.add(PostgresJobStore._event(row=row, event_type="content.generation_cancelled", actor_ref=actor_ref))
        return await self.get(project_id, generation_id)

    async def apply(self, project_id: str, generation_id: str, *, expected_version: str, actor_ref: str):
        response = await self.get(project_id, generation_id)
        proposal = response["proposal"]
        current = await self.content.latest(project_id)
        if current and current.source_job_id == generation_id:
            return current  # Idempotent apply; not a new approval or generation.
        if response["job"]["status"] != "awaiting_review" or proposal is None:
            raise ContentConflictError("no current reviewable proposal")
        base = proposal["provenance"]["base_content_version_id"]
        if base != expected_version:
            raise ContentConflictError("proposal source changed; reload before applying")
        return await self.content.save(project_id, ContentSaveRequest(expected_content_version_id=base,
            document=ContentDocument.model_validate(proposal["snapshot"]["content"])), actor_ref=actor_ref,
            source_job_id=generation_id, source_proposal_id=proposal["project_version_id"])

    async def recover(self):
        """Queued jobs are resumable. Ambiguous running jobs require review, not retry."""
        async with self.platform.session_factory() as session:
            async with session.begin():
                rows = (await session.scalars(select(JobORM).where(JobORM.status.in_(["queued", "running"])).with_for_update())).all()
                pending = []
                for row in rows:
                    if row.request_json.get("kind") != "content_generation":
                        continue
                    if row.status == "queued":
                        pending.append(row.job_id)
                    else:
                        row.status, row.stage = "failed", "failed"
                        row.error_json = {"code": "GENERATION_OBSERVATION_UNCERTAIN", "message": "worker interrupted after claim; no automatic retry",
                            "failed_stage": "scripting", "retryable": False}
                        row.updated_at = utc_now()
                        session.add(PostgresJobStore._event(row=row, event_type="content.generation_interrupted", actor_ref="worker-recovery"))
        for identifier in pending:
            await self.queue.rpush(CONTENT_QUEUE, identifier)
        return len(pending)
