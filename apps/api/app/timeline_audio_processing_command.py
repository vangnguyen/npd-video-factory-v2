"""Canonical metadata mutation using existing timeline versions and invalidation.

No provider, media read, queue, or schema addition occurs in this command. Request
receipts are immutable mutation history, never an authority supplied by a client.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from .timeline_db import TimelineORM, TimelineVersionORM
from .timeline_models import TimelineSnapshot
from .timeline_repository import TimelineConflictError
from .timeline_audio_processing_api import ProcessingConfiguration, ProcessingReceipt


class ProcessingConflict(RuntimeError):
    def __init__(self, code, current_version=None):
        self.code = code
        self.current_version = current_version
        super().__init__(code)


def _configuration(snapshot):
    try:
        value = snapshot.metadata.get("source_audio_processing", {})
        return ProcessingConfiguration.model_validate({} if value is None else value).model_dump(mode="json")
    except ValidationError as exc:
        raise ProcessingConflict("STORED_AUDIO_PROCESSING_INVALID") from exc


def _receipt(mutation):
    if mutation.get("type") != "source-audio-processing":
        return None
    try:
        return ProcessingReceipt.model_validate(mutation["receipt"]).model_dump(mode="json")
    except (KeyError, ValidationError) as exc:
        raise ProcessingConflict("AUDIO_PROCESSING_RECEIPT_INVALID") from exc


def _result(timeline, mutation, *, replayed=False):
    return {"timeline": timeline, "configuration": _configuration(timeline.snapshot),
            "locked_audio_track_ids": sorted(track.track_id for track in timeline.snapshot.tracks
                                             if track.type == "audio" and track.locked),
            "receipt": _receipt(mutation), "replayed": replayed}


async def _current(session, project_id):
    row = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id).with_for_update())
    if row is None:
        raise KeyError(project_id)
    version = await session.get(TimelineVersionORM, row.current_version_id)
    if (version is None or version.timeline_id != row.timeline_id or version.project_id != project_id
            or version.version != row.current_version):
        raise ProcessingConflict("TIMELINE_CURRENT_VERSION_INVALID", row.current_version)
    return row, version


async def read_processing(service, project_id):
    async with service.repository.session_factory() as session:
        row, version = await _current(session, project_id)
        return _result(await service.repository._timeline_read(session, row), version.mutation_json)


async def apply_processing(service, project_id, payload, *, actor_ref):
    # Pydantic objects remain local to this request, while all identities and
    # normalized values used below are copied before the first database await.
    timeline_id = payload.expected_timeline_id
    expected = payload.expected_version
    key = payload.request_key
    configuration = payload.configuration.model_dump(mode="json")
    intent = {"project_id": project_id, "timeline_id": timeline_id, "parent_version": expected,
              "request_key": key, "actor_ref": actor_ref, "configuration": configuration}
    digest = hashlib.sha256(json.dumps(intent, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    try:
        async with service.repository.session_factory() as session:
            async with session.begin():
                row, version = await _current(session, project_id)
                if row.timeline_id != timeline_id:
                    raise ProcessingConflict("TIMELINE_IDENTITY_CONFLICT", row.current_version)
                prior = (await session.scalars(select(TimelineVersionORM).where(
                    TimelineVersionORM.timeline_id == timeline_id,
                    TimelineVersionORM.project_id == project_id,
                    TimelineVersionORM.mutation_json["type"].as_string() == "source-audio-processing",
                    TimelineVersionORM.mutation_json["receipt"]["request_key"].as_string() == key))).all()
                if prior:
                    if len(prior) != 1:
                        raise ProcessingConflict("AUDIO_PROCESSING_RECEIPT_INVALID", row.current_version)
                    receipt = _receipt(prior[0].mutation_json)
                    if receipt["request_sha256"] != digest or receipt["actor_ref"] != actor_ref:
                        raise ProcessingConflict("AUDIO_PROCESSING_KEY_CONFLICT", row.current_version)
                    if (receipt["workspace_id"] != row.workspace_id or receipt["project_id"] != project_id
                            or receipt["timeline_id"] != timeline_id or receipt["parent_version"] != expected
                            or receipt["result_version"] != prior[0].version
                            or receipt["configuration"] != configuration):
                        raise ProcessingConflict("AUDIO_PROCESSING_RECEIPT_INVALID", row.current_version)
                    if (row.current_version_id != prior[0].timeline_version_id
                            or _configuration(TimelineSnapshot.model_validate(version.snapshot_json)) != configuration):
                        raise ProcessingConflict("AUDIO_PROCESSING_RECEIPT_SUPERSEDED", row.current_version)
                    return _result(await service.repository._timeline_read(session, row),
                                   prior[0].mutation_json, replayed=True)
                if row.current_version != expected:
                    raise ProcessingConflict("TIMELINE_VERSION_CONFLICT", row.current_version)
                snapshot = TimelineSnapshot.model_validate(version.snapshot_json)
                if any(track.type == "audio" and track.locked for track in snapshot.tracks):
                    raise ProcessingConflict("AUDIO_TRACK_LOCKED", row.current_version)
                # Reserve the same row using a conditional SQL write. SQLite
                # ignores FOR UPDATE, so this also fences concurrent writers
                # before any version/approval mutation. This is not a version
                # increment; the existing repository owns the version commit.
                reserved = await session.execute(update(TimelineORM).where(
                    TimelineORM.project_id == project_id, TimelineORM.timeline_id == timeline_id,
                    TimelineORM.current_version == expected,
                    TimelineORM.current_version_id == version.timeline_version_id
                ).values(current_version=expected).execution_options(synchronize_session=False))
                if reserved.rowcount != 1:
                    raise ProcessingConflict("TIMELINE_VERSION_CONFLICT")
                snapshot = snapshot.model_copy(deep=True)
                snapshot.metadata["source_audio_processing"] = configuration
                service.validator.validate(snapshot)
                receipt = {"schema_version": "source-audio-processing-v1", "request_key": key,
                           "request_sha256": digest, "workspace_id": row.workspace_id,
                           "project_id": project_id, "timeline_id": timeline_id,
                           "parent_version": expected, "result_version": expected + 1,
                           "actor_ref": actor_ref, "configuration": configuration}
                mutation = {"type": "source-audio-processing", "receipt": receipt,
                            "source_media_mutated": False, "publish_requested": False}
                row = await service.repository.commit_mutation_in_session(session=session,
                    project_id=project_id, expected_version=expected, snapshot=snapshot,
                    mutation=mutation, actor_ref=actor_ref)
                await session.flush()
                result = _result(await service.repository._timeline_read(session, row), mutation)
            return result
    except TimelineConflictError as exc:
        raise ProcessingConflict("TIMELINE_VERSION_CONFLICT", exc.actual) from exc
    except IntegrityError as exc:
        raise ProcessingConflict("TIMELINE_VERSION_CONFLICT") from exc
    except OperationalError as exc:
        if not any(word in str(exc.orig).lower() for word in ("locked", "busy")):
            raise
        raise ProcessingConflict("TIMELINE_VERSION_CONFLICT") from exc
