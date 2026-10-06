"""Opt-in shot editing over the existing canonical TimelineSnapshot contract.

The snapshot is the only persisted shot state. Proposal, bindings and edit_plan
are validated projections for the accepted Native pipeline, never a second
editor database. Reading an old project does not migrate or approve it.
"""
from __future__ import annotations

import copy
import math
import re
import uuid

from app.timeline_models import TimelineSnapshot

from .contracts import Proposal, Scene, WorkflowError, digest, normalize
from .editor import SceneOptions, build_plan
from .media import project_assets, validate_bindings

SCHEMA = "native-shot-timeline-v1"
MAX_SHOTS = 20
MAX_DURATION = 180.0
EDIT_FIELDS = {
    "visual", "prompt", "narration", "subtitle", "on_screen_text", "asset_id",
    "duration", "duration_requested", "requested_duration", "narration_enabled", "crop_strategy",
    "motion", "source_start", "transition",
}
SNAPSHOT_FIELDS = {
    "visual", "narration", "subtitle", "on_screen_text", "asset_id", "duration",
    "requested_duration", "narration_enabled", "crop_strategy", "motion", "source_start", "transition",
}


def _error(code, status=400):
    raise WorkflowError(code, status)


def _number(value, low, high, code):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        _error(code)
    return float(value)


def _text(value, limit, code, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        _error(code)
    return value


def _assets(doc):
    return {a["id"]: a for a in project_assets(doc)}


def _check_shot(shot, assets):
    if not isinstance(shot, dict) or not isinstance(shot.get("shot_id"), str) or not re.fullmatch(r"shot_[0-9a-f]{32}", shot["shot_id"]):
        _error("SHOT_ID_INVALID")
    if not SNAPSHOT_FIELDS <= set(shot):
        _error("SHOT_TIMELINE_METADATA_INVALID")
    _text(shot["visual"], 1200, "SHOT_VISUAL_INVALID")
    _text(shot["narration"], 1500, "SHOT_NARRATION_INVALID", empty=True)
    _text(shot["subtitle"], 1500, "SHOT_SUBTITLE_INVALID", empty=True)
    _text(shot["on_screen_text"], 150, "SHOT_ON_SCREEN_TEXT_INVALID")
    if type(shot["narration_enabled"]) is not bool:
        _error("SHOT_NARRATION_ENABLED_BOOLEAN_REQUIRED")
    if shot["narration_enabled"] and not shot["narration"].strip():
        _error("SHOT_ENABLED_NARRATION_REQUIRED")
    _number(shot["duration"], .1, MAX_DURATION, "SHOT_DURATION_INVALID")
    if shot["requested_duration"] is not None:
        _number(shot["requested_duration"], .1, MAX_DURATION, "SHOT_DURATION_INVALID")
        if shot["duration"] != shot["requested_duration"]:
            _error("SHOT_REQUESTED_DURATION_CHANGED")
    _number(shot["source_start"], 0, 600, "SHOT_SOURCE_START_INVALID")
    try:
        SceneOptions.model_validate({"scene": 1, **{k: shot[k] for k in
            ("crop_strategy", "motion", "source_start", "transition")}})
    except ValueError:
        _error("SHOT_VISUAL_OPTIONS_INVALID")
    identifier = shot["asset_id"]
    if identifier is None:
        if shot["source_start"]:
            _error("SHOT_UNASSIGNED_SOURCE_START_INVALID")
        return
    if not isinstance(identifier, str) or identifier not in assets:
        _error("SHOT_MEDIA_NOT_IN_PROJECT")
    asset = assets[identifier]
    if asset["kind"] == "image":
        if shot["source_start"]:
            _error("EDITOR_IMAGE_HAS_NO_SOURCE_TIME")
    elif asset["kind"] == "video":
        if shot["motion"] != "none" or shot["source_start"] >= asset.get("duration_seconds", 0):
            _error("EDITOR_VIDEO_TRIM_OR_MOTION_INVALID")
    else:
        _error("SHOT_MEDIA_KIND_UNSUPPORTED")


def _legacy_shots(doc, project_id, previous=None):
    proposal = doc.get("proposal")
    if not proposal:
        return []
    previous = previous or []
    bindings = {b["scene"]: b["asset_id"] for b in doc.get("scene_media", [])}
    if "scene_media" not in doc and doc.get("asset"):
        bindings = {s["scene"]: doc["asset"]["id"] for s in proposal["visual_brief"]}
    plan = {s["scene"]: s for s in (doc.get("edit_plan") or {}).get("scenes", [])}
    weights = [max(1, len(s["narration_excerpt"])) for s in proposal["visual_brief"]]
    total = max(25., len(proposal["narration"].split()) / 2.5 + 2.)
    result = []
    for index, scene in enumerate(proposal["visual_brief"]):
        old = previous[index] if index < len(previous) else {}
        options = plan.get(scene["scene"], {})
        identifier = bindings.get(scene["scene"])
        asset = _assets(doc).get(identifier)
        narration = scene["narration_excerpt"] if scene["narration_excerpt"].strip() or old.get("narration_enabled", True) else old.get("narration", "")
        subtitle = old.get("subtitle", narration)
        if subtitle == old.get("narration"):
            subtitle = narration
        new_id = (uuid.uuid4() if previous else uuid.uuid5(
            uuid.NAMESPACE_URL, "video-factory/shot/" + project_id + "/" + str(index + 1))).hex
        result.append({"shot_id": old.get("shot_id") or "shot_" + new_id,
            "visual": scene["visual"], "narration": narration,
            "subtitle": subtitle,
            "on_screen_text": scene["on_screen_text"], "asset_id": identifier,
            "duration": old.get("duration", max(.1, options.get("end_target", 0) - options.get("start_target", 0))
                if options else total * weights[index] / sum(weights)),
            "requested_duration": old.get("requested_duration"),
            "narration_enabled": bool(scene["narration_excerpt"].strip()),
            "crop_strategy": options.get("crop_strategy", old.get("crop_strategy", "contain")),
            "motion": "none" if asset and asset["kind"] == "video" else options.get("motion", old.get("motion", "none")),
            "source_start": options.get("source_start", old.get("source_start", 0)) if asset and asset["kind"] == "video" else 0,
            "transition": options.get("transition", old.get("transition", "cut"))})
    return result


def snapshot_from_shots(shots, doc, *, canvas=None):
    """Map one shot to bounded source clips; loops remain part of the same shot."""
    if len(shots) > MAX_SHOTS or len({s["shot_id"] for s in shots}) != len(shots):
        _error("SHOT_COUNT_OR_IDENTITIES_INVALID")
    assets = _assets(doc)
    cursor, clips = 0., []
    for ordinal, shot in enumerate(shots, 1):
        _check_shot(shot, assets)
        duration = float(shot["duration"])
        if cursor + duration > MAX_DURATION + 1e-6:
            _error("SHOT_TIMELINE_EXCEEDS_180_SECONDS")
        asset = assets.get(shot["asset_id"])
        remaining, start, offset, loop = duration, cursor, float(shot["source_start"]), 0
        while remaining > 1e-7:
            if loop >= 1000:
                _error("SHOT_SOURCE_LOOP_LIMIT")
            length = min(remaining, float(asset["duration_seconds"]) - offset) if asset and asset["kind"] == "video" else remaining
            if length <= 0:
                _error("EDITOR_SOURCE_WINDOW_INVALID")
            metadata = {"shot_id": shot["shot_id"], "shot_number": ordinal,
                "native_asset_id": shot["asset_id"], "loop_index": loop,
                "source_sha256": asset["sha256"] if asset else None,
                "fit": shot["crop_strategy"], "motion": shot["motion"], "source_audio": "muted"}
            if loop == 0:
                metadata["shot"] = {k: copy.deepcopy(shot[k]) for k in SNAPSHOT_FIELDS}
            kind = asset["kind"] if asset else "metadata"
            clips.append({"clip_id": "clip_" + shot["shot_id"][5:] + "_" + str(loop),
                "kind": "source" if kind == "video" else kind,
                "label": shot["on_screen_text"],
                "asset_id": "ast_" + digest(shot["asset_id"])[:32] if asset else None,
                "timeline_start": round(start, 6), "duration": round(length, 6),
                "source_start": offset if kind == "video" else 0,
                "source_end": round(offset + length, 6) if kind == "video" else (None if kind == "image" else round(length, 6)),
                "transition_in": {"kind": shot["transition"] if loop == 0 else "cut",
                    "duration_seconds": min(.15, length) if loop == 0 and shot["transition"] == "fade" else 0},
                "metadata": metadata})
            start += length
            remaining -= length
            offset, loop = 0., loop + 1
        cursor += duration
    shape = (doc.get("brand_template") or {}).get("template") or canvas or {}
    value = {"schema_version": "1.1", "width": shape.get("width", 1080), "height": shape.get("height", 1920),
        "fps": shape.get("fps", 30), "aspect_ratio": shape.get("aspect_ratio", "9:16"),
        "duration_seconds": max(.1, round(cursor, 6)),
        "tracks": [{"track_id": "trk_native_video", "type": "video", "kind": "source", "label": "Shots", "order": 0, "clips": clips}],
        "metadata": {"native_shot_schema": SCHEMA, "timing_source": "draft_requested_duration_requires_measured_voice_fit",
            "human_review_required": True, "source_media_mutated": False,
            "brand_template_sha256": digest(doc.get("brand_template")),
            "music_sha256": digest(doc.get("music")) if doc.get("music_enabled", True) else None,
            "music_enabled": doc.get("music_enabled", True), "voice_quality_sha256": digest(doc.get("voice_quality"))}}
    if doc.get("content_intelligence"):
        from .intelligence_lineage import projection
        value["metadata"]["content_intelligence"] = projection(doc)
    return TimelineSnapshot.model_validate(value).model_dump(mode="json")


def shots_from_snapshot(snapshot):
    try:
        value = TimelineSnapshot.model_validate(snapshot).model_dump(mode="json")
        if value["schema_version"] != "1.1" or value["metadata"].get("native_shot_schema") != SCHEMA:
            _error("SHOT_TIMELINE_SCHEMA_INVALID")
        result = []
        seen = set()
        for track in value["tracks"]:
            if track["track_id"] != "trk_native_video":
                continue
            for clip in track["clips"]:
                metadata = clip["metadata"]
                identifier = metadata["shot_id"]
                if identifier not in seen:
                    if metadata["loop_index"] != 0 or not isinstance(metadata.get("shot"), dict) or set(metadata["shot"]) != SNAPSHOT_FIELDS:
                        _error("SHOT_TIMELINE_METADATA_INVALID")
                    seen.add(identifier)
                    result.append({"shot_id": identifier, **copy.deepcopy(metadata["shot"])})
        return result
    except (ValueError, KeyError, TypeError):
        _error("SHOT_TIMELINE_METADATA_INVALID")


def project_projection(doc, shots):
    """Legacy Native fields are generated, not editable alongside the snapshot."""
    result = copy.deepcopy(doc)
    if not shots:
        result["proposal"], result["scene_media"] = None, []
        result.pop("edit_plan", None)
        return result
    narration = normalize(" ".join(s["narration"] for s in shots if s["narration_enabled"]))
    if not narration:
        _error("SHOT_AT_LEAST_ONE_NARRATION_REQUIRED")
    raw = {"narration": narration, "facts_needing_source": (doc.get("proposal") or {}).get("facts_needing_source", []),
        "visual_brief": [{"scene": index + 1, "visual": s["visual"], "on_screen_text": s["on_screen_text"],
            "narration_excerpt": s["narration"] if s["narration_enabled"] else ""} for index, s in enumerate(shots)]}
    try:
        result["proposal"] = Proposal.model_validate(raw).model_dump()
    except ValueError:
        _error("SHOT_PROPOSAL_PROJECTION_INVALID")
    result["scene_media"] = [{"scene": i + 1, "asset_id": s["asset_id"]} for i, s in enumerate(shots) if s["asset_id"]]
    validate_bindings(result)
    if len(result["scene_media"]) == len(shots) and all(a["rights_confirmed"] is True for a in project_assets(result)):
        result["edit_plan"] = build_plan(result, [{"scene": i + 1, **{k: s[k] for k in
            ("crop_strategy", "motion", "source_start", "transition")}} for i, s in enumerate(shots)])
    else:
        result.pop("edit_plan", None)
    return result


def validate_document(doc):
    state = doc.get("canonical_timeline")
    if state is None:
        return None
    if not isinstance(state, dict) or set(state) != {"version", "snapshot", "sha256"} or type(state["version"]) is not int or state["version"] < 1:
        _error("SHOT_TIMELINE_STATE_INVALID")
    if state["sha256"] != digest(state["snapshot"]):
        _error("SHOT_TIMELINE_CHANGED")
    shots = shots_from_snapshot(state["snapshot"])
    if digest(snapshot_from_shots(shots, doc, canvas=state["snapshot"])) != state["sha256"]:
        _error("SHOT_TIMELINE_SOURCE_OR_CLIPS_CHANGED")
    projected = project_projection(doc, shots)
    for key in ("proposal", "scene_media", "edit_plan"):
        if digest(projected.get(key)) != digest(doc.get(key)):
            _error("SHOT_TIMELINE_PROJECTION_STALE")
    return state


def shots(doc):
    """Validated canonical shot metadata consumed by preview/render integration."""
    state = validate_document(doc)
    return shots_from_snapshot(state["snapshot"]) if state else []


def _state(project):
    doc = project["document"]
    state = validate_document(doc)
    if state:
        return copy.deepcopy(state), True
    snapshot = snapshot_from_shots(_legacy_shots(doc, project["id"]), doc)
    return {"version": 0, "snapshot": snapshot, "sha256": digest(snapshot)}, False


def view(store, project):
    if isinstance(project, str):
        project = store.get(project)
    state, persisted = _state(project)
    assets = _assets(project["document"])
    shots = []
    for ordinal, shot in enumerate(shots_from_snapshot(state["snapshot"]), 1):
        asset = assets.get(shot["asset_id"])
        shots.append({**shot, "id": shot["shot_id"], "scene": ordinal, "number": ordinal,
            "prompt": shot["visual"], "duration_requested": shot["requested_duration"],
            "asset_type": asset["kind"] if asset else None, "asset": copy.deepcopy(asset),
            "status": "MEDIA_READY" if asset else "NEEDS_MEDIA", "timing_measured": False})
    return {**project, "shot_timeline": {**state, "shots": shots, "persisted": persisted,
        "preview_valid": False, "scope": {"full_render_requested": False, "provider_calls": 0}}}


def _voice_dependency(shots, index):
    shot = shots[index]
    if not shot["narration_enabled"]:
        return (False, "", "")
    before = next((s["narration"] for s in reversed(shots[:index]) if s["narration_enabled"]), "")
    parts = [s for s in re.split(r"(?<=[.!?])\s+", before.strip()) if s]
    return (shot["narration_enabled"], shot["narration"], parts[-1] if parts else "")


def scope_changes(before, after):
    old = {s["shot_id"]: s for s in before}
    new = {s["shot_id"]: s for s in after}
    changed = [s["shot_id"] for s in after if s != old.get(s["shot_id"])] + [s["shot_id"] for s in before if s["shot_id"] not in new]
    old_voice = {s["shot_id"]: _voice_dependency(before, i) for i, s in enumerate(before)}
    voice = [s["shot_id"] for i, s in enumerate(after) if _voice_dependency(after, i) != old_voice.get(s["shot_id"])]
    visual_keys = ("asset_id", "visual", "on_screen_text", "subtitle", "crop_strategy", "motion", "source_start", "transition", "duration", "requested_duration")
    media = [s["shot_id"] for s in after if any(s[k] != old.get(s["shot_id"], {}).get(k) for k in visual_keys)]
    old_starts, cursor = {}, 0.
    for s in before:
        old_starts[s["shot_id"]], cursor = cursor, cursor + s["duration"]
    retimed, cursor = [], 0.
    for s in after:
        if old_starts.get(s["shot_id"]) != cursor:
            retimed.append(s["shot_id"])
        cursor += s["duration"]
    reordered = [s["shot_id"] for s in before] != [s["shot_id"] for s in after]
    return {"affected_shot_ids": list(dict.fromkeys(changed + voice + retimed)), "voice_dependency_shot_ids": voice,
        "visual_dependency_shot_ids": media, "retimed_shot_ids": retimed, "order_changed": reordered,
        "full_render_requested": False, "provider_calls": 0, "preview_invalidated": True,
        "voice_context_dependency": "preceding_enabled_shot_last_sentence"}


def _apply(shots, doc, operation, store, project, con):
    if not isinstance(operation, dict) or not isinstance(operation.get("type"), str) or operation["type"] not in {"update", "reorder", "duplicate", "delete", "regenerate", "revert"}:
        _error("SHOT_OPERATION_INVALID")
    kind = operation["type"]
    allowed = {"update": {"type", "shot_id", "values"}, "reorder": {"type", "shot_ids"},
        "duplicate": {"type", "shot_id"}, "delete": {"type", "shot_id"},
        "regenerate": {"type", "shot_id"}, "revert": {"type", "shot_id", "restore_revision"}}
    if set(operation) - allowed[kind]:
        _error("SHOT_OPERATION_FIELDS_INVALID")
    if kind == "reorder":
        ids = operation.get("shot_ids")
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids) or len(ids) != len(shots) or len(set(ids)) != len(ids) or set(ids) != {s["shot_id"] for s in shots}:
            _error("SHOT_REORDER_REQUIRES_EXACT_IDS")
        by_id = {s["shot_id"]: s for s in shots}
        return [by_id[i] for i in ids]
    if kind == "revert":
        revision = operation.get("restore_revision")
        if type(revision) is not int or revision < 1 or revision >= project["revision"]:
            _error("SHOT_RESTORE_REVISION_INVALID")
        row = con.execute("SELECT document FROM project_versions WHERE project_id=? AND revision=?", (project["id"], revision)).fetchone()
        if row is None:
            _error("SHOT_RESTORE_REVISION_NOT_FOUND", 404)
        import json
        historical = json.loads(row["document"])
        restored = shots_from_snapshot(historical["canonical_timeline"]["snapshot"]) if historical.get("canonical_timeline") else _legacy_shots(historical, project["id"])
        if operation.get("shot_id"):
            original = next((s for s in restored if s["shot_id"] == operation["shot_id"]), None)
            if not original:
                _error("SHOT_NOT_IN_RESTORE_REVISION")
            return [copy.deepcopy(original) if s["shot_id"] == original["shot_id"] else s for s in shots]
        return restored
    index = next((i for i, s in enumerate(shots) if s["shot_id"] == operation.get("shot_id")), None)
    if index is None:
        _error("SHOT_NOT_FOUND", 404)
    shot = shots[index]
    if kind == "update":
        values = operation.get("values")
        if not isinstance(values, dict) or not values or set(values) - EDIT_FIELDS:
            _error("SHOT_FIELDS_INVALID")
        for aliases in (("visual", "prompt"), ("duration", "duration_requested", "requested_duration")):
            supplied = [values[key] for key in aliases if key in values]
            if supplied and any(value != supplied[0] for value in supplied):
                _error("SHOT_FIELD_ALIASES_CONFLICT")
        follow_narration = "narration" in values and "subtitle" not in values and shot["subtitle"] == shot["narration"]
        for key, value in values.items():
            if key in {"duration_requested", "requested_duration"} and value is None:
                shot["requested_duration"] = None
                continue
            mapped = {"prompt": "visual", "duration_requested": "duration", "requested_duration": "duration"}.get(key, key)
            shot[mapped] = value
            if mapped == "duration":
                shot["requested_duration"] = value
        if follow_narration:
            shot["subtitle"] = shot["narration"]
        if "asset_id" in values and values["asset_id"] != doc_asset_for(shots, index, doc):
            shot["source_start"] = values.get("source_start", 0)
            if _assets(doc).get(shot["asset_id"], {}).get("kind") == "video":
                shot["motion"] = values.get("motion", "none")
    elif kind == "duplicate":
        if len(shots) >= MAX_SHOTS:
            _error("SHOT_COUNT_LIMIT")
        new = copy.deepcopy(shot)
        new["shot_id"] = "shot_" + uuid.uuid4().hex
        shots.insert(index + 1, new)
    elif kind == "delete":
        if len(shots) <= 1:
            _error("SHOT_CANNOT_DELETE_LAST")
        shots.pop(index)
    else:
        from .editor import candidates
        scene = Scene.model_validate({"scene": index + 1, "visual": shot["visual"], "on_screen_text": shot["on_screen_text"], "narration_excerpt": shot["narration"]})
        ranked = [c for c in candidates(doc, scene, index) if c["asset_id"] != shot["asset_id"]]
        if not ranked:
            _error("SHOT_REGENERATE_ALTERNATE_MEDIA_REQUIRED")
        shot["asset_id"], shot["source_start"] = ranked[0]["asset_id"], ranked[0]["source_start"]
        if _assets(doc)[shot["asset_id"]]["kind"] == "video":
            shot["motion"] = "none"
    return shots


def doc_asset_for(shots, index, doc):
    bindings = {b["scene"]: b["asset_id"] for b in doc.get("scene_media", [])}
    return bindings.get(index + 1, (doc.get("asset") or {}).get("id"))


def mutate(store, identifier, revision, operation):
    """One optimistic transaction persists snapshot and all derived projections."""
    import json
    from .store import now
    if type(revision) is not int or revision < 1:
        _error("REVISION_REQUIRED")
    with store.transaction() as con:
        project = store.editable(con, identifier, revision)
        state, _ = _state(project)
        before = shots_from_snapshot(state["snapshot"])
        after = _apply(copy.deepcopy(before), project["document"], operation, store, project, con)
        for item in after:
            _check_shot(item, _assets(project["document"]))
        scope = scope_changes(before, after)
        if before == after and project["document"].get("canonical_timeline"):
            result = view(store, project)
            result["shot_timeline"]["scope"] = {**scope, "preview_invalidated": False}
            return result
        doc = project_projection(project["document"], after)
        snapshot = snapshot_from_shots(after, doc, canvas=state["snapshot"])
        doc["canonical_timeline"] = {"version": state["version"] + 1, "snapshot": snapshot, "sha256": digest(snapshot)}
        validate_document(doc)
        con.execute("UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?",
            (revision + 1, json.dumps(doc, ensure_ascii=False), now(), identifier))
        store.version(con, identifier)
        store.event(con, identifier, "shot_timeline_saved_approval_invalidated", {"revision": revision + 1,
            "timeline_version": doc["canonical_timeline"]["version"], "timeline_sha256": doc["canonical_timeline"]["sha256"],
            "operation": operation["type"], "scope": scope,
            "regeneration_kind": "deterministic_existing_media_candidate" if operation["type"] == "regenerate" else None,
            "automatic_production": False, "human_review_required": True})
    result = view(store, store.get(identifier))
    result["shot_timeline"]["scope"] = scope
    return result


def sync_legacy(doc, previous_doc, project_id):
    """Legacy save remains supported; changed fields regenerate the same snapshot."""
    old = previous_doc.get("canonical_timeline")
    if old is None:
        return doc
    validate_document(previous_doc)
    previous = shots_from_snapshot(old["snapshot"])
    shots = _legacy_shots(doc, project_id, previous)
    projected = project_projection(doc, shots)
    snapshot = snapshot_from_shots(shots, projected, canvas=old["snapshot"])
    projected["canonical_timeline"] = {"version": old["version"] + 1, "snapshot": snapshot, "sha256": digest(snapshot)}
    validate_document(projected)
    return projected
