"""One existing SQL transaction for exact saved speech, CAS, history and review."""
from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError
from sqlalchemy import select, update, text
from sqlalchemy.exc import IntegrityError, OperationalError

from .auto_edit_db import AutoEditAnalysisORM, TranscriptORM
from .auto_edit_models import MediaMetadata
from .db import AssetORM, VideoProjectORM
from .source_linked_edit import SourceLinkedEditError, apply_linked_operations
from .source_linked_edit_api import SourceLinkedReceipt
from .timeline_db import TimelineORM, TimelineVersionORM
from .timeline_models import TimelineSnapshot
from .timeline_logic import TimelineEditError
from .timeline_repository import TimelineConflictError
from .transcript_word_editing import _read_transcript, _manual_caption_tracks


class SourceLinkedConflict(RuntimeError):
    def __init__(self, code, current_version=None):
        self.code, self.current_version = code, current_version
        super().__init__(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def receipt(mutation):
    if mutation.get("type") != "source-linked-edit":
        return None
    try:
        return SourceLinkedReceipt.model_validate(mutation["receipt"]).model_dump(mode="json")
    except (KeyError, ValidationError) as exc:
        raise SourceLinkedConflict("SOURCE_LINKED_RECEIPT_INVALID") from exc


async def current(session, project_id, *, lock=False):
    statement = select(TimelineORM).where(TimelineORM.project_id == project_id)
    row = await session.scalar(statement.with_for_update() if lock else statement)
    if row is None:
        raise KeyError(project_id)
    version = await session.get(TimelineVersionORM, row.current_version_id)
    if (version is None or version.timeline_id != row.timeline_id or version.project_id != project_id
            or version.version != row.current_version):
        raise SourceLinkedConflict("TIMELINE_CURRENT_VERSION_INVALID", row.current_version)
    return row, version


async def read_source_linked_edit(service, project_id):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await _begin_snapshot(session)
            row, version = await current(session, project_id)
            return dict(timeline=await service.repository._timeline_read(session, row),
                        receipt=receipt(version.mutation_json), replayed=False)


async def _begin_snapshot(session):
    # SQLite's legacy driver does not issue BEGIN for SELECT. Establish the
    # owned read snapshot before source/transcript checks, not only at CAS.
    if session.get_bind().dialect.name == "sqlite":
        await session.execute(text("BEGIN"))


async def _source(session, row, analysis, snapshot):
    project = await session.get(VideoProjectORM, row.project_id)
    asset = await session.get(AssetORM, analysis.asset_id)
    if (project is None or asset is None or analysis.project_id != row.project_id
            or analysis.workspace_id != row.workspace_id or project.workspace_id != row.workspace_id
            or asset.workspace_id != row.workspace_id or asset.project_id != row.project_id):
        raise KeyError(row.project_id)
    if (analysis.status != "succeeded" or asset.asset_class != "source" or not asset.content_type.startswith("video/")
            or snapshot.metadata.get("source_analysis_id") != analysis.analysis_id
            or snapshot.metadata.get("source_asset_id") != asset.asset_id):
        raise SourceLinkedConflict("SOURCE_BINDING_INVALID")
    media = MediaMetadata.model_validate(analysis.source_media_json)
    if (media.media_kind != "video" or media.duration_seconds is None or media.duration_seconds <= 0
            or snapshot.metadata.get("source_duration_seconds") != media.duration_seconds
            or "audio_codec" not in analysis.source_media_json
            or media.audio_codec in {"", "unknown"}):
        raise SourceLinkedConflict("SOURCE_MEDIA_NOT_MEASURED")
    if analysis.provenance_json.get("source_asset_checksum") != asset.checksum_sha256:
        raise SourceLinkedConflict("SOURCE_CHECKSUM_CHANGED")
    for track in snapshot.tracks:
        if track.kind not in {"source", "original_audio"}:
            continue
        for clip in track.clips:
            if (clip.asset_id != asset.asset_id or clip.metadata.get("source_checksum_sha256") != asset.checksum_sha256
                    or clip.metadata.get("object_key") != asset.object_key
                    or clip.metadata.get("content_type") != asset.content_type):
                raise SourceLinkedConflict("SOURCE_CLIP_BINDING_CHANGED")
    binding = snapshot.metadata.get("transcript_revision")
    transcript = None
    if binding is not None:
        if not isinstance(binding, dict) or type(binding.get("version")) is not int or not isinstance(binding.get("transcript_id"), str):
            raise SourceLinkedConflict("SOURCE_TRANSCRIPT_BINDING_INVALID")
        saved = await session.get(TranscriptORM, binding["transcript_id"])
        if (saved is None or saved.analysis_id != analysis.analysis_id or saved.asset_id != asset.asset_id
                or saved.version != binding["version"]):
            raise SourceLinkedConflict("SOURCE_TRANSCRIPT_BINDING_INVALID")
        transcript = await _read_transcript(session, saved)
        if any(transcript.provenance.get(key) is not None and transcript.provenance[key] != asset.checksum_sha256
               for key in ("source_checksum", "source_asset_sha256")):
            raise SourceLinkedConflict("SOURCE_TRANSCRIPT_CHECKSUM_CHANGED")
        if any(not 0 <= s.start_seconds < s.end_seconds <= media.duration_seconds for s in transcript.segments):
            raise SourceLinkedConflict("SOURCE_TRANSCRIPT_BOUNDS_INVALID")
    elif media.audio_codec is not None:
        raise SourceLinkedConflict("SOURCE_TRANSCRIPT_REQUIRED")
    source = {"analysis_id": analysis.analysis_id, "analysis_fingerprint": analysis.fingerprint,
        "asset_id": asset.asset_id, "source_sha256": asset.checksum_sha256,
        "object_key": asset.object_key, "duration_seconds": media.duration_seconds,
        "has_audio": media.audio_codec is not None,
        "transcript_id": transcript.transcript_id if transcript else None,
        "transcript_version": transcript.version if transcript else None,
        "transcript_sha256": digest(transcript.model_dump(mode="json")) if transcript else None}
    return source, transcript


async def apply_source_linked_edit(service, project_id, payload, *, actor_ref):
    if not isinstance(actor_ref, str) or not actor_ref or len(actor_ref) > 160 or any(ord(c) < 32 for c in actor_ref):
        raise SourceLinkedConflict("SOURCE_ACTOR_INVALID")
    expected, timeline_id, key = payload.expected_version, payload.expected_timeline_id, payload.request_key
    operations = [op.model_dump(mode="json", exclude_none=True) for op in payload.operations]
    intent = dict(project_id=project_id, timeline_id=timeline_id, parent_version=expected,
                  request_key=key, actor_ref=actor_ref, operations=operations)
    request_sha = digest(intent)
    try:
        async with service.repository.session_factory() as session:
            async with session.begin():
                await _begin_snapshot(session)
                # The existing transcript editor locks analysis -> timeline.
                # Read identity first, then take the same lock order and recheck.
                first = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id))
                if first is None:
                    raise KeyError(project_id)
                analysis_id = first.source_analysis_id
                if not analysis_id:
                    raise SourceLinkedConflict("SOURCE_ANALYSIS_REQUIRED", first.current_version)
                analysis = await session.scalar(select(AutoEditAnalysisORM).where(
                    AutoEditAnalysisORM.analysis_id == analysis_id).with_for_update())
                if analysis is None:
                    raise SourceLinkedConflict("SOURCE_ANALYSIS_REQUIRED")
                # Populate existing ORM identity from the locked current row.
                statement = select(TimelineORM).where(TimelineORM.project_id == project_id).with_for_update()
                row = await session.scalar(statement.execution_options(populate_existing=True))
                if row is None:
                    raise KeyError(project_id)
                if row.timeline_id != timeline_id or row.source_analysis_id != analysis_id:
                    raise SourceLinkedConflict("TIMELINE_IDENTITY_CONFLICT", row.current_version)
                row, version = await current(session, project_id)
                snapshot = TimelineSnapshot.model_validate(version.snapshot_json)
                source, transcript = await _source(session, row, analysis, snapshot)
                prior = (await session.scalars(select(TimelineVersionORM).where(
                    TimelineVersionORM.timeline_id == timeline_id, TimelineVersionORM.project_id == project_id,
                    TimelineVersionORM.mutation_json["type"].as_string() == "source-linked-edit",
                    TimelineVersionORM.mutation_json["receipt"]["request_key"].as_string() == key))).all()
                if prior:
                    if len(prior) != 1:
                        raise SourceLinkedConflict("SOURCE_LINKED_RECEIPT_INVALID")
                    saved = receipt(prior[0].mutation_json)
                    parent = await session.get(TimelineVersionORM, saved["parent_version_id"])
                    if saved["request_sha256"] != request_sha or saved["actor_ref"] != actor_ref:
                        raise SourceLinkedConflict("SOURCE_LINKED_KEY_CONFLICT", row.current_version)
                    if (saved["workspace_id"] != row.workspace_id or saved["project_id"] != project_id
                            or saved["timeline_id"] != timeline_id or saved["parent_version"] != expected
                            or saved["result_version"] != prior[0].version or saved["requested_operations"] != operations
                            or saved["source"] != source or prior[0].actor_ref != saved["actor_ref"]
                            or prior[0].mutation_json.get("source_media_mutated") is not False
                            or prior[0].mutation_json.get("publish_requested") is not False
                            or parent is None or parent.timeline_id != timeline_id or parent.project_id != project_id
                            or parent.version != expected):
                        raise SourceLinkedConflict("SOURCE_LINKED_RECEIPT_INVALID", row.current_version)
                    if (row.current_version_id != prior[0].timeline_version_id
                            or digest(snapshot.model_dump(mode="json")) != saved["result_snapshot_sha256"]):
                        raise SourceLinkedConflict("SOURCE_LINKED_RECEIPT_SUPERSEDED", row.current_version)
                    return dict(timeline=await service.repository._timeline_read(session, row), receipt=saved, replayed=True)
                if row.current_version != expected:
                    raise SourceLinkedConflict("TIMELINE_VERSION_CONFLICT", row.current_version)
                manual = await _manual_caption_tracks(session, row)
                changed, applied = apply_linked_operations(snapshot, payload.operations,
                    transcript=transcript, source_asset_id=source["asset_id"], source_duration=source["duration_seconds"],
                    has_audio=source["has_audio"], manual_caption_track_ids=manual)
                service.validator.validate(changed)
                reserved = await session.execute(update(TimelineORM).where(TimelineORM.project_id == project_id,
                    TimelineORM.timeline_id == timeline_id, TimelineORM.current_version == expected,
                    TimelineORM.current_version_id == version.timeline_version_id).values(current_version=expected)
                    .execution_options(synchronize_session=False))
                if reserved.rowcount != 1:
                    raise SourceLinkedConflict("TIMELINE_VERSION_CONFLICT")
                saved = SourceLinkedReceipt(schema_version="source-linked-edit-v1", request_key=key,
                    request_sha256=request_sha, workspace_id=row.workspace_id, project_id=project_id,
                    timeline_id=timeline_id, parent_version_id=version.timeline_version_id,
                    parent_version=expected, result_version=expected + 1, actor_ref=actor_ref, source=source,
                    requested_operations=operations, applied_operations=applied,
                    result_snapshot_sha256=digest(changed.model_dump(mode="json"))).model_dump(mode="json")
                mutation = dict(type="source-linked-edit", receipt=saved, source_media_mutated=False, publish_requested=False)
                row = await service.repository.commit_mutation_in_session(session=session, project_id=project_id,
                    expected_version=expected, snapshot=changed, mutation=mutation, actor_ref=actor_ref)
                await session.flush()
                result = dict(timeline=await service.repository._timeline_read(session, row), receipt=saved, replayed=False)
            return result
    except (TimelineEditError, ValidationError) as exc:
        raise SourceLinkedConflict(str(exc)) from exc
    except TimelineConflictError as exc:
        raise SourceLinkedConflict("TIMELINE_VERSION_CONFLICT", exc.actual) from exc
    except IntegrityError as exc:
        raise SourceLinkedConflict("TIMELINE_VERSION_CONFLICT") from exc
    except OperationalError as exc:
        if not any(word in str(exc.orig).lower() for word in ("locked", "busy")):
            raise
        raise SourceLinkedConflict("TIMELINE_VERSION_CONFLICT") from exc
