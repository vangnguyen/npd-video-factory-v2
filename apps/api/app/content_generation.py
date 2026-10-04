"""Durable proposal jobs on the existing jobs/project-version/provider/cost stores.

The fixture path remains offline. Real adapters must bind the exact job/input
and pass the existing durable per-capability safety boundary; no fallback.
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
from .storyboard_content_provider import CONTENT_REAL_KEY, ProviderEnablementError

CONTENT_QUEUE = "npd:video-factory:v2:content-generation:queued"
FIXTURE_KEY = "fixture-storyboard-content"


class ContentProviderUnavailable(ValueError):
    def __init__(self, message, *, code="CONTENT_PROVIDER_NOT_CONFIGURED"):
        self.code = code
        super().__init__(message)


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
    if mode == "responses":
        return {"provider_key": CONTENT_REAL_KEY, "display_name": "Structured storyboard provider candidate",
            "capability": "content_generation", "adapter": "app.storyboard_content_provider.ResponsesStoryboardContentProvider",
            "routing_mode": "primary", "enabled": True, "status": "degraded", "supports_dry_run": True,
            "metadata": {"paid": True, "external_call": True, "fixture": False,
                "authority_required": True, "real_provider_accepted": False}}
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
        if self.mode == "responses":
            selected = any(p.provider_key == CONTENT_REAL_KEY and p.enabled and p.routing_mode == "primary"
                for p in providers)
            readiness = self.provider.readiness() if selected and self.provider.key == CONTENT_REAL_KEY else "CONTENT_PROVIDER_NOT_CONFIGURED"
            return {"provider_key": CONTENT_REAL_KEY, "status": readiness,
                "external_call": True, "real_provider_accepted": False,
                "zero_call_check": "CONFIG_METADATA_ONLY_NOT_DURABLE_PREFLIGHT"}
        allowed = self.mode == "fixture" and any(p.provider_key == FIXTURE_KEY and p.enabled
            and p.status == "healthy" and p.routing_mode == "primary" for p in providers)
        return {"provider_key": FIXTURE_KEY if allowed else None,
            "status": "FIXTURE_ONLY" if allowed else "CONTENT_PROVIDER_NOT_CONFIGURED",
            "external_call": False, "real_provider_accepted": False}

    async def create(self, project_id: str, payload: ContentGenerateRequest, *, actor_ref: str):
        available = await self.availability()
        if available["status"] not in {"FIXTURE_ONLY", "CONFIG_AND_SCOPE_PRESENT"}:
            raise ContentProviderUnavailable(available["status"] + ": no provider was called",
                code=available["status"])
        project = await self.platform.get_project(project_id)
        current = await self.content.latest(project_id)
        if project is None:
            raise KeyError(project_id)
        if current is None or current.project_version_id != payload.expected_content_version_id:
            raise ContentConflictError("save/reload the current input version before generation")
        document = ContentDocument.model_validate(current.snapshot["content"])
        input_sha = hashlib.sha256(canonical_bytes(document.model_dump(mode="json"))).hexdigest()
        profile_sha = None
        operation_key = None
        identity = [project_id, current.project_version_id, self.provider.key, payload.idempotency_key]
        if self.mode == "responses":
            input_sha = self.provider.input_sha256(document, current.project_version_id)
            profile_sha = self.provider.profile.sha256
            identity.append(profile_sha)
            scope = self.provider.controller.policy.execution_gate
            matches = [item for item in scope.allowed_operations
                if item.asset_id == current.project_version_id and item.asset_hash == input_sha]
            if len(matches) != 1:
                raise ContentProviderUnavailable("CONTENT_INPUT_AUTHORITY_REQUIRED",
                    code="CONTENT_INPUT_AUTHORITY_REQUIRED")
            operation_key = matches[0].operation_key
        fingerprint = hashlib.sha256(canonical_bytes(identity)).hexdigest()
        identifier = f"job_content_{fingerprint[:24]}"
        record = JobRecord.new(job_id=identifier, workspace_id=project.workspace_id, project_id=project_id,
            project_version_id=current.project_version_id,
            request=ContentGenerationJobInput(content_version_id=current.project_version_id, actor_ref=actor_ref,
                provider_key=self.provider.key, provider_profile_sha256=profile_sha,
                input_sha256=input_sha, provider_operation_key=operation_key))
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
            "provider_status": "FIXTURE_ONLY" if record.request.provider_key == FIXTURE_KEY else "REAL_ADAPTER_PROPOSAL_NOT_ACCEPTED",
            "external_call": record.request.provider_key != FIXTURE_KEY}

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
                job_input = ContentGenerationJobInput.model_validate(row.request_json)
        try:
            source = await self.platform.get_version(source_id)
            if (source is None or source.project_id != project_id or job_input.provider_key != self.provider.key
                    or (await self.availability())["status"] not in {"FIXTURE_ONLY", "CONFIG_AND_SCOPE_PRESENT"}):
                raise ContentProviderUnavailable("CONTENT_PROVIDER_NOT_CONFIGURED")
            document = ContentDocument.model_validate(source.snapshot["content"])
            input_sha = hashlib.sha256(canonical_bytes(document.model_dump(mode="json"))).hexdigest()
            if job_input.provider_key != FIXTURE_KEY:
                input_sha = self.provider.input_sha256(document, source_id)
            if job_input.input_sha256 and input_sha != job_input.input_sha256:
                raise ProviderEnablementError("MAPPING", "CONTENT_INPUT_CHANGED")
            # Do not start a call for a cancelled/edited input. Edits during a
            # genuine call still win the existing completion/apply CAS.
            async with self.platform.session_factory() as session:
                claimed = await session.get(JobORM, generation_id)
                if claimed.status != "running":
                    return
            if (await self.content.latest(project_id)).project_version_id != source_id:
                raise ProviderEnablementError("MAPPING", "CONTENT_RESPONSE_STALE")
            external = job_input.provider_key != FIXTURE_KEY
            metadata = {"fixture": not external, "external_call": external, "human_accepted": False}
            if external:
                if job_input.provider_profile_sha256 != self.provider.profile.sha256:
                    raise ProviderEnablementError("MAPPING", "CONTENT_PROFILE_CHANGED")
                envelope = await self.provider.generate_for_job(document,
                    workspace_id=source.workspace_id, project_id=project_id, job_id=generation_id,
                    source_version_id=source_id, input_sha256=input_sha,
                    operation_key=job_input.provider_operation_key)
                result = envelope.result
                metadata.update(envelope.model_dump(mode="json", exclude={"result"}))
                model, estimated, actual = envelope.model, envelope.modelled_cost_vnd, None
            else:
                result = ContentGenerationResult.model_validate(await self.provider.generate(document))
                model, estimated, actual = "offline-fixture-v1", Decimal(0), Decimal(0)
            proposal = ContentDocument.model_validate({**document.model_dump(), **result.model_dump(),
                "generator": "provider-storyboard-v1" if external else "fixture-storyboard-v1", "approved": False})
            await self.platform.record_provider_operation(workspace_id=source.workspace_id, project_id=project_id,
                job_id=generation_id, provider_key=job_input.provider_key, capability="content_generation",
                operation="storyboard-proposal", model=model, estimated_cost=estimated,
                actual_cost=actual, metadata=metadata)
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
                            "provider": job_input.provider_key, **metadata, "stale": stale})
                    session.add(version)
                    await session.flush()
                    row.artifacts_json = [{"kind": "script", "name": "content-proposal.json", "url": version.project_version_id}]
                    row.status, row.stage, row.progress = ("failed", "failed", 100) if stale else ("awaiting_review", "storyboarding", 100)
                    row.error_json = {"code": "CONTENT_RESPONSE_STALE", "message": "input changed; proposal cannot overwrite it",
                        "failed_stage": "storyboarding", "retryable": False} if stale else None
                    row.updated_at = utc_now()
                    session.add(PostgresJobStore._event(row=row, event_type="content.proposal_stale" if stale else "content.proposal_ready", actor_ref=actor))
        except Exception as exc:
            async with self.platform.session_factory() as session:
                async with session.begin():
                    row = await session.get(JobORM, generation_id, with_for_update=True)
                    if row and row.status == "running":
                        row.status, row.stage = "failed", "failed"
                        row.error_json = {"code": exc.code if isinstance(exc, ProviderEnablementError) else "CONTENT_GENERATION_FAILED",
                            "message": (exc.category + ": " if isinstance(exc, ProviderEnablementError) else "") + "generation failed; input preserved",
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
