"""One SQL crop transaction, preserving independent tracks and measured clocks."""
from __future__ import annotations

import math
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from .auto_edit_db import AutoEditAnalysisORM
from .auto_edit_models import MediaMetadata
from .db import AssetORM
from .frozen_storage_read import asset_custody, FrozenReadRejected
from .manual_reframe_api import ManualReframeReceipt, ManualReframeSettings, ManualReframeSource
from .source_linked_edit_command import _begin_snapshot, _source, current, digest, SourceLinkedConflict
from .timeline_db import TimelineORM, TimelineVersionORM
from .timeline_logic import TimelineEditError
from .timeline_models import TimelineSnapshot
from .timeline_reframe import ASPECT_DIMENSIONS, bind_reframe, crop_keyframes
from .timeline_repository import TimelineConflictError


class ManualReframeConflict(RuntimeError):
    def __init__(self, code, current_version=None):
        self.code, self.current_version = code, current_version
        super().__init__(code)


def _receipt(mutation):
    if mutation.get("type") != "manual-reframe":
        return None
    try:
        return ManualReframeReceipt.model_validate(mutation["receipt"]).model_dump(mode="json")
    except (KeyError, ValidationError) as exc:
        raise ManualReframeConflict("MANUAL_REFRAME_RECEIPT_INVALID") from exc


async def _identity(session, row, analysis, snapshot):
    value, _ = await _source(session, row, analysis, snapshot)
    media = MediaMetadata.model_validate(analysis.source_media_json)
    if (type(media.width) is not int or type(media.height) is not int
            or not 1 <= media.width <= 1_000_000 or not 1 <= media.height <= 1_000_000
            or media.fps is None or not math.isfinite(media.fps) or media.fps <= 0
            or not math.isfinite(media.duration_seconds)):
        raise ManualReframeConflict("MANUAL_REFRAME_MEASURED_GEOMETRY_REQUIRED")
    asset = await session.get(AssetORM, analysis.asset_id)
    measured = asset.provenance.get("media_metadata") if asset is not None else None
    if (not isinstance(measured, dict) or type(asset.size_bytes) is not int or asset.size_bytes <= 0
            or any(measured.get(k) != getattr(media, k) for k in ("width", "height", "fps", "duration_seconds", "audio_codec"))):
        raise ManualReframeConflict("MANUAL_REFRAME_MEASURED_SOURCE_CHANGED")
    value.update(width=media.width, height=media.height, fps=media.fps)
    value = ManualReframeSource.model_validate(value).model_dump(mode="json")
    try:
        custody = asset_custody(asset)
    except FrozenReadRejected as exc:
        raise ManualReframeConflict("MANUAL_REFRAME_CUSTODY_INVALID") from exc
    binding = digest(dict(workspace_id=row.workspace_id, project_id=row.project_id, source=value, asset=custody))
    return value, media, binding


def _request_sha(project_id, timeline_id, parent_version, request_key, actor_ref, settings, binding):
    return digest(dict(project_id=project_id, timeline_id=timeline_id, parent_version=parent_version,
        request_key=request_key, actor_ref=actor_ref, settings=settings, source_binding_sha256=binding))


def _main(snapshot, source):
    tracks = [t for t in snapshot.tracks if t.kind == "source"]
    if len(tracks) != 1 or tracks[0].type != "video" or not tracks[0].clips:
        raise ManualReframeConflict("MANUAL_REFRAME_SOURCE_TRACK_REQUIRED")
    main = tracks[0]
    for clip in main.clips:
        numbers = (clip.source_start, clip.source_end, clip.timeline_start, clip.duration, clip.speed)
        if (clip.kind != "source" or clip.asset_id != source["asset_id"] or not all(math.isfinite(x) for x in numbers)
                or not 0 <= clip.source_start < clip.source_end <= source["duration_seconds"]
                or clip.timeline_start < 0 or clip.duration <= 0 or clip.speed <= 0
                or abs(clip.duration - (clip.source_end - clip.source_start) / clip.speed) > .00001):
            raise ManualReframeConflict("MANUAL_REFRAME_SOURCE_CLOCK_INVALID")
    return main


def _plan(settings, source):
    if any(p.time > source["duration_seconds"] for p in settings.points):
        raise ManualReframeConflict("MANUAL_REFRAME_SOURCE_TIME_INVALID")
    width, height = ASPECT_DIMENSIONS[settings.aspect_ratio]
    relative = (source["width"] / source["height"]) / (width / height)
    minimum = max(relative, 1 / relative)
    # This internal plan is entirely server-derived. It deliberately does not
    # reuse Vision's scale<=20 evidence model: zoom is relative to aspect-fit,
    # including measured ultrawide sources. crop_keyframes owns the geometry.
    points = [SimpleNamespace(time=p.time, x=p.x, y=p.y, scale=minimum * p.zoom) for p in settings.points]
    if not all(math.isfinite(p.scale) for p in points):
        raise ManualReframeConflict("MANUAL_REFRAME_SCALE_INVALID")
    return SimpleNamespace(reframe_id="rfr_manual_" + digest(dict(source=source, settings=settings.model_dump(mode="json")))[:24],
        aspect_ratio=settings.aspect_ratio, keyframes=points, strategy="manual_override", confidence=None,
        fallback="none", needs_attention=True)


def _changed(snapshot, source, media, settings):
    main = _main(snapshot, source)
    if main.locked or main.disabled or not any(not c.disabled for c in main.clips):
        raise ManualReframeConflict("MANUAL_REFRAME_SOURCE_LOCKED_OR_DISABLED")
    plan = _plan(settings, source)
    # Bind only the source track. Other video tracks may legally reuse this
    # asset, but their independent crop and all audio/captions remain exact.
    part = snapshot.model_copy(deep=True)
    part.tracks = [main.model_copy(deep=True)]
    disabled = {c.clip_id: c.disabled for c in part.tracks[0].clips}
    for clip in part.tracks[0].clips:
        clip.disabled = False
    bound = bind_reframe(part, asset_id=source["asset_id"], metadata=media, plan=plan, vision_analysis_id=None)
    for clip in bound.tracks[0].clips:
        clip.disabled = disabled[clip.clip_id]
    result = snapshot.model_copy(deep=True)
    result.tracks = [bound.tracks[0] if t.track_id == main.track_id else t for t in result.tracks]
    result.width, result.height, result.aspect_ratio = bound.width, bound.height, bound.aspect_ratio
    points = crop_keyframes(plan, media)
    result.metadata = {**result.metadata, "reframe": bound.metadata["reframe"], "manual_reframe": {
        "schema_version": "manual-reframe-settings-v1", "source": source,
        "settings": settings.model_dump(mode="json"), "plan_id": plan.reframe_id,
        "applied_keyframes_sha256": digest(points), "provider_dispatches": 0,
        "confidence_basis": "explicit_human_crop_coordinates", "human_review_required": True}}
    return result, points


def _settings(snapshot, source, media):
    """Return editable settings only while the canonical crop still matches."""
    saved = snapshot.metadata.get("manual_reframe")
    if saved is None:
        return None
    try:
        settings = ManualReframeSettings.model_validate(saved["settings"])
        plan = _plan(settings, source)
        points = crop_keyframes(plan, media)
        main = _main(snapshot, source)
        if (saved.get("schema_version") != "manual-reframe-settings-v1" or saved.get("source") != source
                or saved.get("plan_id") != plan.reframe_id or saved.get("applied_keyframes_sha256") != digest(points)
                or saved.get("provider_dispatches") != 0 or saved.get("human_review_required") is not True
                or saved.get("confidence_basis") != "explicit_human_crop_coordinates"
                or snapshot.aspect_ratio != settings.aspect_ratio
                or (snapshot.width, snapshot.height) != ASPECT_DIMENSIONS[settings.aspect_ratio]):
            return None
        for clip in main.clips:
            binding = clip.metadata.get("reframe", {})
            if (binding.get("plan_id") != plan.reframe_id or binding.get("keyframes") != points
                    or binding.get("time_space") != "source_seconds"
                    or binding.get("strategy") != "manual_override" or binding.get("confidence") is not None
                    or clip.crop.model_dump(mode="json") != {k: v for k, v in points[0].items() if k != "time"}):
                return None
        return settings.model_dump(mode="json")
    except (KeyError, TypeError, ValidationError, TimelineEditError, ManualReframeConflict):
        return None


async def read_manual_reframe(service, project_id):
    try:
        async with service.repository.session_factory() as session:
            async with session.begin():
                await _begin_snapshot(session)
                row, version = await current(session, project_id)
                analysis = await session.get(AutoEditAnalysisORM, row.source_analysis_id) if row.source_analysis_id else None
                if analysis is None:
                    raise ManualReframeConflict("MANUAL_REFRAME_SOURCE_ANALYSIS_REQUIRED")
                snapshot = TimelineSnapshot.model_validate(version.snapshot_json)
                source, media, binding = await _identity(session, row, analysis, snapshot)
                settings = _settings(snapshot, source, media)
                saved = _receipt(version.mutation_json)
                if saved is not None:
                    parent = await session.get(TimelineVersionORM, saved["parent_version_id"])
                    if (saved["workspace_id"] != row.workspace_id or saved["project_id"] != project_id
                            or saved["timeline_id"] != row.timeline_id or saved["result_version"] != row.current_version
                            or saved["source"] != source or saved["settings"] != settings or version.actor_ref != saved["actor_ref"]
                            or version.mutation_json.get("source_media_mutated") is not False
                            or version.mutation_json.get("publish_requested") is not False
                            or parent is None or parent.timeline_id != row.timeline_id or parent.project_id != project_id
                            or parent.version != saved["parent_version"]
                            or saved["request_sha256"] != _request_sha(project_id, row.timeline_id, saved["parent_version"],
                                saved["request_key"], saved["actor_ref"], saved["settings"], binding)
                            or digest(snapshot.model_dump(mode="json")) != saved["result_snapshot_sha256"]
                            or saved["applied_keyframes"] != crop_keyframes(_plan(ManualReframeSettings.model_validate(settings), source), media)):
                        raise ManualReframeConflict("MANUAL_REFRAME_RECEIPT_INVALID", row.current_version)
                return dict(timeline=await service.repository._timeline_read(session, row), source=source,
                    source_binding_sha256=binding,
                    settings=settings, receipt=saved, replayed=False)
    except SourceLinkedConflict as exc:
        raise ManualReframeConflict(exc.code, exc.current_version) from exc
    except ValidationError as exc:
        raise ManualReframeConflict("MANUAL_REFRAME_SOURCE_BINDING_INVALID") from exc


async def apply_manual_reframe(service, project_id, payload, *, actor_ref):
    if not isinstance(actor_ref, str) or not actor_ref or len(actor_ref) > 160 or any(ord(c) < 32 for c in actor_ref):
        raise ManualReframeConflict("MANUAL_REFRAME_ACTOR_INVALID")
    settings = ManualReframeSettings(aspect_ratio=payload.aspect_ratio, points=payload.points)
    values = settings.model_dump(mode="json")
    expected, timeline_id, key = payload.expected_version, payload.expected_timeline_id, payload.request_key
    request_sha = _request_sha(project_id, timeline_id, expected, key, actor_ref, values, payload.expected_source_binding_sha256)
    try:
        async with service.repository.session_factory() as session:
            async with session.begin():
                await _begin_snapshot(session)
                first = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id))
                if first is None:
                    raise KeyError(project_id)
                analysis_id = first.source_analysis_id
                analysis = await session.scalar(select(AutoEditAnalysisORM).where(
                    AutoEditAnalysisORM.analysis_id == analysis_id).with_for_update()) if analysis_id else None
                if analysis is None:
                    raise ManualReframeConflict("MANUAL_REFRAME_SOURCE_ANALYSIS_REQUIRED")
                row = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id)
                    .with_for_update().execution_options(populate_existing=True))
                if row is None:
                    raise KeyError(project_id)
                if row.timeline_id != timeline_id or row.source_analysis_id != analysis_id:
                    raise ManualReframeConflict("TIMELINE_IDENTITY_CONFLICT", row.current_version)
                row, version = await current(session, project_id)
                await session.scalar(select(AssetORM).where(AssetORM.asset_id == analysis.asset_id).with_for_update())
                snapshot = TimelineSnapshot.model_validate(version.snapshot_json)
                source, media, binding = await _identity(session, row, analysis, snapshot)
                if binding != payload.expected_source_binding_sha256:
                    raise ManualReframeConflict("MANUAL_REFRAME_SOURCE_CHANGED", row.current_version)
                prior = (await session.scalars(select(TimelineVersionORM).where(
                    TimelineVersionORM.timeline_id == timeline_id, TimelineVersionORM.project_id == project_id,
                    TimelineVersionORM.mutation_json["type"].as_string() == "manual-reframe",
                    TimelineVersionORM.mutation_json["receipt"]["request_key"].as_string() == key))).all()
                if prior:
                    if len(prior) != 1:
                        raise ManualReframeConflict("MANUAL_REFRAME_RECEIPT_INVALID")
                    saved = _receipt(prior[0].mutation_json)
                    parent = await session.get(TimelineVersionORM, saved["parent_version_id"])
                    if saved["request_sha256"] != request_sha or saved["actor_ref"] != actor_ref:
                        raise ManualReframeConflict("MANUAL_REFRAME_KEY_CONFLICT", row.current_version)
                    if (saved["workspace_id"] != row.workspace_id or saved["project_id"] != project_id
                            or saved["timeline_id"] != timeline_id or saved["parent_version"] != expected
                            or saved["result_version"] != prior[0].version or saved["settings"] != values
                            or saved["source"] != source or prior[0].actor_ref != actor_ref
                            or prior[0].mutation_json.get("source_media_mutated") is not False
                            or prior[0].mutation_json.get("publish_requested") is not False
                            or parent is None or parent.timeline_id != timeline_id or parent.project_id != project_id
                            or parent.version != expected):
                        raise ManualReframeConflict("MANUAL_REFRAME_RECEIPT_INVALID", row.current_version)
                    if (row.current_version_id != prior[0].timeline_version_id
                            or digest(snapshot.model_dump(mode="json")) != saved["result_snapshot_sha256"]
                            or _settings(snapshot, source, media) != values
                            or saved["applied_keyframes"] != crop_keyframes(_plan(settings, source), media)):
                        raise ManualReframeConflict("MANUAL_REFRAME_RECEIPT_SUPERSEDED", row.current_version)
                    return dict(timeline=await service.repository._timeline_read(session, row), source=source,
                        source_binding_sha256=binding,
                        settings=values, receipt=saved, replayed=True)
                if row.current_version != expected:
                    raise ManualReframeConflict("TIMELINE_VERSION_CONFLICT", row.current_version)
                changed, points = _changed(snapshot, source, media, settings)
                service.validator.validate(changed)
                reserved = await session.execute(update(TimelineORM).where(TimelineORM.project_id == project_id,
                    TimelineORM.timeline_id == timeline_id, TimelineORM.current_version == expected,
                    TimelineORM.current_version_id == version.timeline_version_id).values(current_version=expected)
                    .execution_options(synchronize_session=False))
                if reserved.rowcount != 1:
                    raise ManualReframeConflict("TIMELINE_VERSION_CONFLICT")
                saved = ManualReframeReceipt(schema_version="manual-reframe-v1", request_key=key,
                    request_sha256=request_sha, workspace_id=row.workspace_id, project_id=project_id,
                    timeline_id=timeline_id, parent_version_id=version.timeline_version_id,
                    parent_version=expected, result_version=expected + 1, actor_ref=actor_ref, source=source,
                    settings=settings, applied_keyframes=points,
                    result_snapshot_sha256=digest(changed.model_dump(mode="json"))).model_dump(mode="json")
                mutation = dict(type="manual-reframe", receipt=saved, source_media_mutated=False, publish_requested=False)
                row = await service.repository.commit_mutation_in_session(session=session, project_id=project_id,
                    expected_version=expected, snapshot=changed, mutation=mutation, actor_ref=actor_ref)
                await session.flush()
                result = dict(timeline=await service.repository._timeline_read(session, row), source=source,
                    source_binding_sha256=binding,
                    settings=values, receipt=saved, replayed=False)
            return result
    except SourceLinkedConflict as exc:
        raise ManualReframeConflict(exc.code, exc.current_version) from exc
    except (TimelineEditError, ValidationError) as exc:
        raise ManualReframeConflict("MANUAL_REFRAME_PLAN_OR_SOURCE_INVALID") from exc
    except TimelineConflictError as exc:
        raise ManualReframeConflict("TIMELINE_VERSION_CONFLICT", exc.actual) from exc
    except IntegrityError as exc:
        raise ManualReframeConflict("TIMELINE_VERSION_CONFLICT") from exc
    except OperationalError as exc:
        if not any(word in str(exc.orig).lower() for word in ("locked", "busy")):
            raise
        raise ManualReframeConflict("TIMELINE_VERSION_CONFLICT") from exc
