"""Canonical image timing, immutable recovery and authenticated edit evidence."""
from copy import deepcopy

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.content_models import StoryboardScene
from app.main import app
from app.timeline_logic import TimelineEditError, apply_operations
from app.timeline_models import (
    TimelineClip, TimelineCreateRequest, TimelineMutationRequest, TimelineOperation,
    TimelineRestoreRequest, TimelineSnapshot, TimelineTrack,
)
from app.timeline_repository import TimelineConflictError
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_mvp1_multi_input import env, image, author, timeline


def still_snapshot():
    return TimelineSnapshot(schema_version="1.1", duration_seconds=4, tracks=[
        TimelineTrack(track_id="trk_photo", type="video", kind="broll", label="Photo", order=0,
                      clips=[TimelineClip(clip_id="clip_photo", kind="image", label="Photo",
                                          timeline_start=0, duration=4)]),
        TimelineTrack(track_id="trk_video", type="video", kind="source", label="Footage", order=1,
                      clips=[TimelineClip(clip_id="clip_video", kind="source", label="Footage",
                                          source_start=2, source_end=6, timeline_start=0, duration=4)]),
    ])


@pytest.mark.parametrize("operation_type", ["trim", "set_clip_properties"])
def test_still_duration_preserves_source_and_other_tracks(operation_type):
    original = still_snapshot()
    before = original.model_dump(mode="json")
    result = apply_operations(original, [TimelineOperation(type=operation_type, clip_id="clip_photo", duration=7.25)])
    clip = result.tracks[0].clips[0]
    assert (clip.duration, clip.source_start, clip.source_end, clip.speed) == (7.25, 0, None, 1)
    assert result.duration_seconds == 7.25
    assert result.tracks[1] == original.tracks[1]
    assert original.model_dump(mode="json") == before
    split = apply_operations(result, [TimelineOperation(type="split", clip_id="clip_photo", at_seconds=3)])
    assert [(c.duration, c.timeline_start, c.source_end) for c in split.tracks[0].clips] == [(3, 0, None), (4.25, 3, None)]
    assert all(c.source_start == 0 and c.speed == 1 for c in split.tracks[0].clips)


@pytest.mark.parametrize("operation_type", ["trim", "set_clip_properties"])
def test_temporal_duration_cannot_replace_source_timing(operation_type):
    original = still_snapshot()
    with pytest.raises(TimelineEditError):
        apply_operations(original, [TimelineOperation(type=operation_type, clip_id="clip_video", duration=5)])
    assert original.tracks[1].clips[0].source_end == 6


@pytest.mark.parametrize("extra", [{"source_start": 1}, {"source_end": 7}, {"source_start": 0, "source_end": 7}])
def test_still_trim_rejects_fabricated_source_window(extra):
    with pytest.raises(TimelineEditError, match="source time window"):
        apply_operations(still_snapshot(), [TimelineOperation(type="trim", clip_id="clip_photo", duration=5, **extra)])


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf"), 86401])
def test_display_duration_is_finite_positive_and_bounded(duration):
    with pytest.raises(ValidationError):
        TimelineOperation(type="trim", clip_id="clip_photo", duration=duration)


def test_duration_cannot_be_silently_ignored_by_move_or_locked_track():
    with pytest.raises(ValidationError, match="only valid"):
        TimelineOperation(type="move", clip_id="clip_photo", duration=5, timeline_start=2)
    original = still_snapshot()
    original.tracks[0].locked = True
    with pytest.raises(TimelineEditError, match="locked"):
        apply_operations(original, [TimelineOperation(type="trim", clip_id="clip_photo", duration=5)])


async def test_image_timing_cas_preview_invalidation_and_restore(env):
    asset = await image(env)
    content = await author(env, [StoryboardScene(scene_id="scene_photo", narration="Ảnh có quyền sử dụng.",
                                                 media_strategy="user_asset", asset_id=asset.asset_id)])
    built = await timeline(env, content)
    original = deepcopy(built.snapshot)
    clip = built.snapshot.tracks[0].clips[0]
    preview, _ = await env.timeline.create_preview(project_id=env.project.project_id, timeline_version=1,
                                                  width=540, height=960, actor_ref="synthetic-editor")
    request = TimelineMutationRequest(expected_version=1, actor_ref="synthetic-editor",
        operations=[TimelineOperation(type="trim", clip_id=clip.clip_id, duration=clip.duration + 2)])
    changed = await env.service.mutate(env.project.project_id, request)
    assert changed.current_version == 2 and changed.approval_status == "draft"
    assert (await env.timeline.get_preview(preview.preview_id)).status == "stale"
    assert (await env.timeline.get_version(built.timeline_id, 1)).snapshot == original
    with pytest.raises(TimelineConflictError):
        await env.service.mutate(env.project.project_id, request)
    restored = await env.service.restore(env.project.project_id,
        TimelineRestoreRequest(expected_version=2, restore_version=1, actor_ref="synthetic-editor"))
    assert restored.current_version == 3 and restored.snapshot == original
    assert (await env.timeline.get_version(built.timeline_id, 2)).snapshot == changed.snapshot
    assert (await env.assets.get_asset(asset.asset_id)).checksum_sha256 == asset.checksum_sha256


async def test_http_edits_and_undo_record_authenticated_actor(env):
    asset = await image(env)
    content = await author(env, [StoryboardScene(scene_id="scene_photo", narration="Ảnh có quyền sử dụng.",
                                                 media_strategy="user_asset", asset_id=asset.asset_id)])
    app.state.timeline_service = env.service
    install_test_human_auth(app, platform_repository=env.platform)
    url = f"/api/v1/projects/{env.project.project_id}/timeline"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = TimelineCreateRequest(source_kind="storyboard_media", content_version_id=content.project_version_id,
                                     actor_ref="forged-owner").model_dump(mode="json")
        assert (await client.post(url, json=body)).status_code == 401
        created = await client.post(url, json=body, headers=TEST_HUMAN_HEADERS)
        assert created.status_code == 201, created.text
        clip = created.json()["snapshot"]["tracks"][0]["clips"][0]
        edit = {"expected_version": 1, "actor_ref": "forged-owner",
                "operations": [{"type": "trim", "clip_id": clip["clip_id"], "duration": clip["duration"] + 1}]}
        install_test_human_auth(app, platform_repository=env.platform, platform_role=None, workspace_roles={"*": "viewer"})
        assert (await client.put(url, json=edit, headers=TEST_HUMAN_HEADERS)).status_code == 403
        install_test_human_auth(app, platform_repository=env.platform)
        changed = await client.put(url, json=edit, headers=TEST_HUMAN_HEADERS)
        assert changed.status_code == 200, changed.text
        assert (await client.put(url, json=edit, headers=TEST_HUMAN_HEADERS)).status_code == 409
        restored = await client.post(url + "/restore", headers=TEST_HUMAN_HEADERS,
                                    json={"expected_version": 2, "restore_version": 1, "actor_ref": "forged-owner"})
        assert restored.status_code == 200 and restored.json()["current_version"] == 3
        versions = (await client.get(url + "/versions", headers=TEST_HUMAN_HEADERS)).json()
        assert len(versions) == 3 and all(v["actor_ref"] == "usr:test-owner" for v in versions)
