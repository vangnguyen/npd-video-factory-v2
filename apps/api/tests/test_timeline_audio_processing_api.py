"""Actual isolated SQLite/ASGI; graph planning only, no media/provider execution."""
import asyncio
import copy
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.db import AssetORM, CostRecordORM, ProviderUsageORM
from app.production_db import ProductionApprovalORM, ProductionPackageORM, ProductionRenderJobORM, ProductionEventORM
from app.production_models import MixConfig
from app.timeline_audio_processing_api import router
from app.timeline_audio_processing_command import apply_processing, ProcessingConflict
from app.timeline_audio_processing_api import ProcessingUpdate
from app.timeline_audio_processing import build_processed_audio_graph
from app.production_audio import canonical_audio_graph, canonical_audio_input
from app.timeline_db import TimelineORM, TimelineVersionORM, PreviewJobORM
from app.timeline_models import TimelineCreateRequest, TimelineRestoreRequest, TimelineTrack, TimelineClip
from app.production_models import ProductionPackageCreateRequest
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_mvp1_multi_input import env, image, author
from test_service_final_render_admission import approved


@pytest.fixture
async def processing_api(env):
    photo = await image(env)
    content = await author(env)
    timeline = await env.service.create(env.project.project_id, TimelineCreateRequest(
        source_kind="storyboard_media", content_version_id=content.project_version_id))
    package = await env.package.create_or_refresh(env.project.project_id, ProductionPackageCreateRequest())
    app = FastAPI()
    app.include_router(router)  # Own router admission, no main/lifespan/bootstrap.
    app.state.timeline_service = env.service
    install_test_human_auth(app, platform_repository=env.platform, platform_role=None,
                            workspace_roles={env.workspace.workspace_id: "editor"})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://fixture-processing") as client:
        yield SimpleNamespace(env=env, app=app, client=client, timeline=timeline, package=package, photo=photo,
            path=f"/api/v1/projects/{env.project.project_id}/timeline/audio-processing")


def body(a, **updates):
    return {"expected_timeline_id": a.timeline.timeline_id, "expected_version": 1,
        "request_key": "processing-fixture-intent-01", "acknowledged": True,
        "configuration": {"normalize_original_audio": True, "normalize_music": True, "duck_music": True,
            "original_target_lufs": -18, "music_target_lufs": -26, "duck_threshold": .025,
            "duck_ratio": 6, "duck_attack_ms": 25, "duck_release_ms": 300}, **updates}


async def put(a, value=None):
    return await a.client.put(a.path, json=value or body(a), headers=TEST_HUMAN_HEADERS)


async def state(a):
    timeline = await a.env.timeline.get_timeline(a.env.project.project_id)
    versions = await a.env.timeline.list_versions(a.env.project.project_id)
    async with a.env.factory() as session:
        rows = {}
        for model in (PreviewJobORM, ProductionApprovalORM, ProductionPackageORM, ProductionRenderJobORM,
                      ProductionEventORM, AssetORM, CostRecordORM, ProviderUsageORM):
            data = (await session.scalars(select(model))).all()
            rows[model.__name__] = [dict((c.name, copy.deepcopy(getattr(r, c.name)))
                for c in model.__table__.columns) for r in data]
    return timeline.model_dump(mode="json"), [v.model_dump(mode="json") for v in versions], rows


async def test_editor_current_receipt_exact_replay_and_history_source_unchanged(processing_api):
    a = processing_api
    initial = await state(a)
    read = await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)
    assert read.status_code == 200 and read.headers["Cache-Control"] == "no-store"
    assert read.json()["configuration"]["duck_threshold"] == .02 and read.json()["receipt"] is None
    first = await put(a)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["timeline"]["current_version"] == 2 and result["replayed"] is False
    receipt = result["receipt"]
    assert receipt["actor_ref"] == "usr:test-owner" and receipt["parent_version"] == 1
    assert receipt["result_version"] == 2 and receipt["configuration"] == result["configuration"]
    after = await state(a)
    assert after[0]["snapshot"]["tracks"] == initial[0]["snapshot"]["tracks"]
    assert after[0]["snapshot"]["source_media_mutated"] is False
    old_version = next(v for v in after[1] if v["version"] == 1)
    assert old_version == initial[1][0]
    replay = await put(a)
    assert replay.status_code == 200 and replay.json()["replayed"] is True
    assert replay.json()["receipt"] == receipt and await state(a) == after
    current = await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)
    assert current.json()["receipt"] == receipt and current.json()["replayed"] is False
    assert a.env.queue.values == []


@pytest.mark.parametrize("mode,status", [("viewer", 403), ("foreign", 404), ("write_off", 503),
                                        ("api_off", 503), ("unauthenticated", 401)])
async def test_admission_before_body_validation_and_no_write(processing_api, mode, status):
    a = processing_api
    before = await state(a)
    if mode in {"viewer", "foreign"}:
        install_test_human_auth(a.app, platform_repository=a.env.platform, platform_role=None,
            workspace_roles={a.env.workspace.workspace_id: "viewer"} if mode == "viewer" else {"wsp_foreign": "editor"})
    elif mode == "write_off":
        a.app.state.human_write_enabled = False
    elif mode == "api_off":
        a.app.state.human_api_enabled = False
    headers = {} if mode == "unauthenticated" else TEST_HUMAN_HEADERS
    value = await a.client.put(a.path, json={"malformed": "fixture"}, headers=headers)
    assert value.status_code == status, value.text
    assert await state(a) == before and a.env.queue.values == []
    if mode in {"viewer", "write_off"}:
        read = await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)
        assert read.status_code == 200


@pytest.mark.parametrize("change", [
    {"acknowledged": False}, {"acknowledged": 1}, {"expected_version": True}, {"expected_version": "1"},
    {"request_key": "short"}, {"actor_ref": "forged-client"},
    {"configuration": {"normalize_music": "true"}}, {"configuration": {"duck_ratio": True}},
    {"configuration": {"duck_ratio": "6"}}, {"configuration": {"duck_ratio": 21}},
    {"configuration": {"original_target_lufs": -25}}, {"configuration": {"unknown": 1}},
    {"configuration": {"duck_ratio": 10 ** 400}},
])
async def test_strict_contract_rejects_before_mutation(processing_api, change):
    a = processing_api
    before = await state(a)
    response = await put(a, body(a, **change))
    assert response.status_code == 422, response.text
    assert await state(a) == before and a.env.queue.values == []


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_processing_never_enters_command(value):
    from pydantic import ValidationError
    from app.timeline_audio_processing_api import ProcessingConfiguration
    with pytest.raises(ValidationError):
        ProcessingConfiguration(duck_ratio=value)


async def test_key_payload_actor_identity_and_superseded_receipt_conflicts(processing_api):
    a = processing_api
    assert (await put(a)).status_code == 200
    after = await state(a)
    changed = body(a); changed["configuration"]["duck_ratio"] = 9
    response = await put(a, changed)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "AUDIO_PROCESSING_KEY_CONFLICT"
    with pytest.raises(ProcessingConflict, match="KEY_CONFLICT"):
        await apply_processing(a.env.service, a.env.project.project_id, ProcessingUpdate(**body(a)),
                               actor_ref="usr:other-fixture-editor")
    wrong = await put(a, body(a, expected_timeline_id="tml_other_fixture"))
    assert wrong.status_code == 409 and wrong.json()["detail"]["code"] == "TIMELINE_IDENTITY_CONFLICT"
    stale = await put(a, body(a, request_key="processing-different-intent-02"))
    assert stale.status_code == 409 and await state(a) == after
    await a.env.service.restore(a.env.project.project_id, TimelineRestoreRequest(expected_version=2, restore_version=1))
    restored = await state(a)
    assert restored[0]["current_version"] == 3 and restored[0]["snapshot"] == a.timeline.snapshot.model_dump(mode="json")
    response = await put(a)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "AUDIO_PROCESSING_RECEIPT_SUPERSEDED"
    assert await state(a) == restored and a.env.queue.values == []


async def test_dormant_locked_audio_track_blocks_processing_without_unlocking(processing_api):
    a = processing_api
    snapshot = a.timeline.snapshot.model_copy(deep=True)
    snapshot.tracks.append(TimelineTrack(track_id="trk_dormant_audio", type="audio", kind="voice", label="Locked fixture",
        order=len(snapshot.tracks), locked=True, disabled=True, muted=True, clips=[]))
    await a.env.timeline.commit_mutation(project_id=a.env.project.project_id, expected_version=1, snapshot=snapshot,
        mutation={"type": "explicit-fixture-lock"}, actor_ref="explicit-fixture-editor")
    before = await state(a)
    response = await put(a, body(a, expected_version=2))
    assert response.status_code == 409 and response.json()["detail"]["code"] == "AUDIO_TRACK_LOCKED"
    assert await state(a) == before
    read = await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)
    assert read.json()["locked_audio_track_ids"] == ["trk_dormant_audio"]


async def test_legacy_null_configuration_reads_shared_defaults_without_mutation(processing_api):
    a = processing_api
    snapshot = a.timeline.snapshot.model_copy(deep=True)
    snapshot.metadata["source_audio_processing"] = None
    await a.env.timeline.commit_mutation(project_id=a.env.project.project_id, expected_version=1, snapshot=snapshot,
        mutation={"type": "explicit-legacy-null-fixture"}, actor_ref="explicit-fixture-editor")
    before = await state(a)
    read = await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)
    assert read.status_code == 200 and read.json()["configuration"]["normalize_original_audio"] is False
    assert read.json()["configuration"]["duck_threshold"] == .02 and await state(a) == before


async def prepare_invalidations(a):
    # Existing unrendered CI review/QC/decision fixture; never Owner acceptance.
    approval = await approved(a)
    preview, _ = await a.env.timeline.create_preview(project_id=a.env.project.project_id, timeline_version=1,
        width=540, height=960, actor_ref="explicit-fixture-preview")
    await a.env.timeline.start_preview(preview.preview_id)
    return approval


async def test_settings_commit_uses_existing_preview_render_and_approval_invalidation(processing_api):
    a = processing_api
    approval = await prepare_invalidations(a)
    assert (await put(a)).status_code == 200
    _, _, rows = await state(a)
    assert all(r["status"] == "stale" and r["cancellation_requested"] for r in rows["PreviewJobORM"])
    assert all(r["status"] == "stale" and r["cancellation_requested"] for r in rows["ProductionRenderJobORM"])
    assert next(r for r in rows["ProductionApprovalORM"] if r["approval_id"] == approval)["status"] == "changes_requested"
    package = rows["ProductionPackageORM"][0]
    assert package["current_approval_id"] is None and package["latest_review_render_id"] is None
    assert (await a.env.timeline.get_timeline(a.env.project.project_id)).approval_status == "draft"


@pytest.mark.parametrize("cancel", [False, True])
async def test_late_exception_or_cancel_rolls_back_all_invalidations(processing_api, monkeypatch, cancel):
    a = processing_api
    await prepare_invalidations(a)
    before = await state(a)
    original = a.env.timeline.commit_mutation_in_session
    reached = asyncio.Event()
    hold = asyncio.Event()
    async def fail_after_flush(**kwargs):
        row = await original(**kwargs)
        await kwargs["session"].flush()
        reached.set()
        if cancel:
            await hold.wait()
        raise RuntimeError("explicit-late-transaction-fixture")
    monkeypatch.setattr(a.env.timeline, "commit_mutation_in_session", fail_after_flush)
    task = asyncio.create_task(put(a))
    await asyncio.wait_for(reached.wait(), 5)
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(RuntimeError, match="explicit-late"):
            await task
    assert await state(a) == before and a.env.queue.values == []


async def test_simultaneous_intents_cannot_overwrite_same_parent(processing_api):
    a = processing_api
    first, second = await asyncio.gather(put(a), put(a, body(a, request_key="processing-other-concurrent-02",
        configuration={"duck_music": False})))
    assert sorted([first.status_code, second.status_code]) == [200, 409], (first.text, second.text)
    versions = await a.env.timeline.list_versions(a.env.project.project_id)
    assert [v.version for v in versions] == [2, 1]
    winner = first if first.status_code == 200 else second
    assert (await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)).json()["receipt"] == winner.json()["receipt"]
    assert a.env.queue.values == []


async def test_saved_processing_drives_shared_proxy_and_production_graph_planning(processing_api):
    a = processing_api
    saved = await put(a)
    snapshot = (await a.env.timeline.get_timeline(a.env.project.project_id)).snapshot.model_copy(deep=True)
    # Explicit non-playable graph-only source contracts. No SQL source is forged,
    # no decoder/DSP is invoked, and no source quality is claimed.
    assets = {}
    for kind in ("original_audio", "music"):
        asset = a.photo.model_copy(update={"asset_id": "ast_contract_" + kind, "kind": "audio",
                                          "content_type": "audio/wav", "filename": "contract-only.wav"})
        assets[asset.asset_id] = (asset, a.env.tmp / (kind + "-nonplayable-fixture.wav"))
        snapshot.tracks.append(TimelineTrack(track_id="trk_contract_" + kind, type="audio", kind=kind,
            label="Graph-only fixture", order=len(snapshot.tracks), clips=[TimelineClip(
                clip_id="clip_contract_" + kind, kind=kind, label="Explicit source-clock fixture", asset_id=asset.asset_id,
                source_start=1, source_end=3, speed=2, timeline_start=.5, duration=1)]))
    proxy = build_processed_audio_graph(snapshot, assets, first_input_index=1,
                                       processing=snapshot.metadata["source_audio_processing"])
    final = canonical_audio_graph(snapshot, assets, MixConfig(limiter_peak_db=-3), first_input_index=1)
    binding = canonical_audio_input(snapshot, assets, MixConfig(limiter_peak_db=-3))
    assert proxy.processing["configuration"] == final.processing["configuration"] == saved.json()["configuration"]
    assert binding.processing.model_dump(mode="json") == saved.json()["configuration"]
    assert proxy.processing["music_ducking"] is True and final.processing["music_ducking"] is True
    assert any("loudnorm=I=-18" in f for f in final.filters)
    assert any("threshold=0.025000000:ratio=6.000000" in f for f in proxy.filters)
    assert final.processing["limiter_peak_db"] == -3 and proxy.processing["limiter_peak_db"] == -1
    assert final.clips == proxy.clips
    assert all(clip["source_start"] == 1 and clip["source_end"] == 3 for clip in proxy.clips)
    assert a.env.queue.values == []
