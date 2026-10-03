from __future__ import annotations

import difflib
import hashlib
import json
import re
import uuid
from sqlalchemy import func, select, update
from .content_models import ContentDocument, ContentSaveRequest, StoryboardScene
from .db import ProjectVersionORM, VideoProjectORM, utc_now
from .platform_models import ProjectVersionRead
from .production_db import ProductionApprovalORM, ProductionPackageORM, ProductionRenderJobORM
from .repositories import _version_read
from .timeline_db import TimelineORM


class ContentConflictError(ValueError):
    pass


def canonical_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def prepare_document(document: ContentDocument) -> ContentDocument:
    """No LLM, facts, tools or shell instructions are inferred from user text."""
    payload = document.model_dump()
    if document.input_kind == "prompt":
        parts = re.split(r"(?im)^\s*(?:lời đọc|narration|kịch bản):\s*", document.original_text, maxsplit=1)
        payload["creative_instructions"] = parts[0].strip()
        payload["script"] = document.script or (parts[1].strip() if len(parts) == 2 else "")
    else:
        payload["script"] = document.script or document.original_text
    if document.scenes:
        return ContentDocument.model_validate(payload)
    text = payload["script"]
    lines = [part.strip() for part in re.split(r"\n+|(?<=[.!?])\s+", text) if part.strip()]
    if any(len(line) > 180 for line in lines):
        raise ValueError("split long narration into scenes of at most 180 characters")
    payload["scenes"] = [StoryboardScene(scene_id=f"scene_{index:02d}", narration=line,
                         visual_brief=line).model_dump() for index, line in enumerate(lines)]
    if document.input_kind != "script":
        payload["facts_needing_source"] = ["User idea/prompt is not factual evidence; review narration and supply sources."]
    return ContentDocument.model_validate(payload)


class ContentService:
    """Uses the existing project-version store and locks the existing project."""
    def __init__(self, platform):
        self.platform = platform

    async def latest(self, project_id: str):
        versions = await self.platform.list_versions(project_id)
        return next((v for v in reversed(versions) if v.label == "mvp1-content"), None)

    async def save(self, project_id: str, payload: ContentSaveRequest) -> ProjectVersionRead:
        document = prepare_document(payload.document)
        data = document.model_dump(mode="json")
        digest = hashlib.sha256(canonical_bytes(data)).hexdigest()
        async with self.platform.session_factory() as session:
            async with session.begin():
                project = await session.scalar(select(VideoProjectORM).where(
                    VideoProjectORM.project_id == project_id).with_for_update())
                if project is None:
                    raise KeyError(project_id)
                old = await session.scalar(select(ProjectVersionORM).where(
                    ProjectVersionORM.project_id == project_id, ProjectVersionORM.label == "mvp1-content"
                ).order_by(ProjectVersionORM.ordinal.desc()).limit(1))
                if old and old.provenance.get("content_sha256") == digest:
                    return _version_read(old)  # repeat submission/restart is idempotent
                if (old.project_version_id if old else None) != payload.expected_content_version_id:
                    raise ContentConflictError("content version changed; reload before saving")
                ordinal = await session.scalar(select(func.max(ProjectVersionORM.ordinal)).where(
                    ProjectVersionORM.project_id == project_id))
                previous = old.snapshot.get("content", {}) if old else {}
                diff = list(difflib.unified_diff(previous.get("script", "").splitlines(),
                                               document.script.splitlines(), lineterm=""))
                row = ProjectVersionORM(project_version_id=f"pver_{uuid.uuid4().hex[:24]}",
                    workspace_id=project.workspace_id, project_id=project_id,
                    ordinal=int(ordinal or 0)+1, label="mvp1-content", snapshot={"content": data},
                    provenance={"content_sha256": digest,
                        "original_text_sha256": hashlib.sha256(document.original_text.encode()).hexdigest(),
                        "previous_version_id": old.project_version_id if old else None,
                        "script_diff": diff, "actor_ref": payload.actor_ref, "external_call": False})
                session.add(row)
                await session.flush()
                project.current_version_id = row.project_version_id
                project.version += 1
                project.updated_at = utc_now()
                # Invalidate approval/final immediately, before a new timeline is built.
                now = utc_now()
                await session.execute(update(ProductionApprovalORM).where(
                    ProductionApprovalORM.project_id == project_id,
                    ProductionApprovalORM.status.in_(["awaiting_review", "approved"])).values(
                    status="changes_requested", invalidated_reason="content-version-changed", updated_at=now))
                await session.execute(update(ProductionRenderJobORM).where(
                    ProductionRenderJobORM.project_id == project_id,
                    ProductionRenderJobORM.status.in_(["queued", "running", "awaiting_review", "ready"])).values(
                    status="stale", cancellation_requested=True, invalidated_at=now, updated_at=now))
                await session.execute(update(ProductionPackageORM).where(
                    ProductionPackageORM.project_id == project_id).values(current_approval_id=None,
                    latest_review_render_id=None, latest_final_render_id=None, updated_at=now))
                await session.execute(update(TimelineORM).where(TimelineORM.project_id == project_id).values(
                    approval_status="draft", approved_timeline_version=None))
            return _version_read(row)
