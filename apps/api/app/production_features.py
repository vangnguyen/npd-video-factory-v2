"""Bounded immutable learning metadata captured with a canonical render request."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import select, update

from .db import ProjectVersionORM, VideoProjectORM, utc_now
from .models import StrictModel
from .timeline_db import TimelineVersionORM
from .trend_db import IdeaCandidateORM


class RenderFeatureContext(StrictModel):
    schema_version: Literal['render-feature-context-v1'] = 'render-feature-context-v1'
    workspace_id: str = Field(max_length=64)
    project_id: str = Field(max_length=64)
    timeline_version_id: str = Field(max_length=64)
    project_version_id: str | None = Field(default=None, max_length=64)
    source_content_version_id: str | None = Field(default=None, max_length=64)
    idea_id: str | None = Field(default=None, max_length=64)
    trend_cluster_id: str | None = Field(default=None, max_length=64)
    idea_version: int | None = Field(default=None, ge=1)
    hook_type: str | None = Field(default=None, max_length=600)
    visual_strategy: str | None = Field(default=None, max_length=1000)
    niche: str | None = Field(default=None, max_length=80)
    topic: str | None = Field(default=None, max_length=500)
    cta: str | None = Field(default=None, max_length=500)
    idea_source: Literal['linked_idea_at_render_request', 'project_version_annotation', 'unavailable']
    captured_at: datetime
    capture_boundary: Literal['render_request'] = 'render_request'

    @model_validator(mode='after')
    def clock(self):
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError('FEATURE_CAPTURE_OFFSET_REQUIRED')
        self.captured_at = self.captured_at.astimezone(timezone.utc)
        return self


def digest(context):
    return hashlib.sha256(json.dumps(context.model_dump(mode='json'), ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def annotation(value, limit):
    return value if isinstance(value, str) and value.strip() and len(value) <= limit else None


async def capture(session, package):
    # Linearize current metadata with project-version writes without changing it.
    locked = await session.execute(update(VideoProjectORM).where(VideoProjectORM.project_id == package.project_id,
        VideoProjectORM.workspace_id == package.workspace_id).values(updated_at=VideoProjectORM.updated_at))
    if locked.rowcount != 1: raise ValueError('RENDER_FEATURE_SCOPE_MISMATCH')
    project = await session.scalar(select(VideoProjectORM).where(VideoProjectORM.project_id == package.project_id,
        VideoProjectORM.workspace_id == package.workspace_id).with_for_update())
    timeline = await session.get(TimelineVersionORM, package.timeline_version_id)
    if project is None or timeline is None or timeline.project_id != project.project_id:
        raise ValueError('RENDER_FEATURE_SCOPE_MISMATCH')
    metadata = (timeline.snapshot_json or {}).get('metadata') or {}
    content_id = metadata.get('content_version_id')
    version_id = content_id or project.current_version_id
    version = await session.get(ProjectVersionORM, version_id) if version_id else None
    if version_id and (version is None or version.project_id != project.project_id or version.workspace_id != project.workspace_id):
        raise ValueError('RENDER_FEATURE_VERSION_SCOPE_MISMATCH')
    snapshot = version.snapshot if version else {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    source = snapshot.get('source_idea'); source = source if isinstance(source, dict) else {}
    content = snapshot.get('content'); content = content if isinstance(content, dict) else {}
    linked = await session.scalar(select(IdeaCandidateORM).where(IdeaCandidateORM.project_id == project.project_id,
        IdeaCandidateORM.workspace_id == project.workspace_id).order_by(IdeaCandidateORM.updated_at.desc(), IdeaCandidateORM.idea_id).limit(1))
    context = RenderFeatureContext(workspace_id=project.workspace_id, project_id=project.project_id,
        timeline_version_id=timeline.timeline_version_id, project_version_id=version_id, source_content_version_id=content_id,
        idea_id=linked.idea_id if linked else annotation(source.get('idea_id'), 64),
        trend_cluster_id=linked.cluster_id if linked else annotation(source.get('cluster_id'), 64),
        idea_version=linked.version if linked else None,
        hook_type=linked.hook_concept if linked else annotation(source.get('hook_concept'), 600),
        visual_strategy=linked.visual_concept if linked else annotation(source.get('visual_concept'), 1000),
        niche=project.niche, topic=linked.title if linked else annotation(source.get('title'), 500) or annotation(snapshot.get('topic'), 500),
        cta=linked.cta_concept if linked else annotation(source.get('cta_concept'), 500) or annotation(content.get('cta'), 500),
        idea_source='linked_idea_at_render_request' if linked else 'project_version_annotation' if source else 'unavailable',
        captured_at=utc_now())
    return {'feature_context': context.model_dump(mode='json'), 'feature_context_sha256': digest(context)}


def read(manifest, *, workspace, project, timeline_version):
    context = manifest.get('feature_context')
    if context is None and manifest.get('feature_context_sha256') is None: return None
    try: value = RenderFeatureContext.model_validate(context)
    except ValueError: raise ValueError('RENDER_FEATURE_CONTEXT_INVALID') from None
    if (digest(value) != manifest.get('feature_context_sha256') or value.workspace_id != workspace
        or value.project_id != project or value.timeline_version_id != timeline_version):
        raise ValueError('RENDER_FEATURE_CONTEXT_SCOPE_OR_HASH_MISMATCH')
    return value


def retain(manifest, original):
    """Completion cannot replace, invent or drop the queue-time context."""
    result = dict(manifest)
    for key in ('feature_context', 'feature_context_sha256'):
        if key in result and result[key] != original.get(key):
            raise ValueError('RENDER_FEATURE_CONTEXT_REPLACEMENT_REFUSED')
        if key in original: result[key] = original[key]
    return result
