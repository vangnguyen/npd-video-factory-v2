from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth

from app.auto_edit_models import (
    AutoEditAnalysisRead,
    AutoEditAnalysisRequest,
    HighlightRead,
    MediaMetadata,
    SceneRead,
    SilenceDecisionRead,
    TranscriptRead,
    TranscriptSegmentRead,
)
from app.db import Base, create_engine, create_session_factory
from app.main import app
from app.object_storage import LocalObjectStorageProvider
from app.platform_models import AssetRegister, ProjectCreate, WorkspaceCreate
from app.repositories import PlatformRepository
from app.timeline_logic import TimelineEditError, apply_operations, build_initial_timeline
from app.timeline_models import (
    PreviewCreateRequest,
    TimelineClip,
    TimelineCreateRequest,
    TimelineMutationRequest,
    TimelineOperation,
    TimelineSnapshot,
    TimelineTrack,
)
from app.timeline_repository import TimelineConflictError, TimelineRepository
from app.timeline_service import (
    PREVIEW_QUEUE_KEY,
    DeterministicProxyRenderer,
    PreviewService,
    TimelineContractValidator,
    TimelineService,
)


NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)
SCHEMA = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "timeline.schema.json"


class FakeQueue:
    def __init__(self) -> None:
        self.values: list[tuple[str, str]] = []

    async def rpush(self, key: str, value: str) -> int:
        self.values.append((key, value))
        return len(self.values)


def analysis_fixture(project_id: str, asset_id: str) -> AutoEditAnalysisRead:
    return AutoEditAnalysisRead(
        analysis_id="ana_timeline_fixture",
        workspace_id="wsp_timeline_fixture",
        project_id=project_id,
        project_version_id=None,
        asset_id=asset_id,
        status="succeeded",
        fingerprint="a" * 64,
        configuration=AutoEditAnalysisRequest(asset_id=asset_id),
        source_media=MediaMetadata(
            media_kind="video",
            detected_content_type="video/mp4",
            format_name="mp4",
            duration_seconds=10,
            width=1080,
            height=1920,
            fps=30,
            video_codec="h264",
            audio_codec="aac",
            audio_channels=2,
            audio_sample_rate=48000,
        ),
        transcript=TranscriptRead(
            transcript_id="trn_timeline_fixture",
            analysis_id="ana_timeline_fixture",
            asset_id=asset_id,
            version=1,
            is_original_evidence=True,
            provider_key="fixture-transcription",
            language="vi",
            confidence=0.96,
            segments=[
                TranscriptSegmentRead(
                    segment_id="seg_timeline_001",
                    ordinal=0,
                    start_seconds=0,
                    end_seconds=3,
                    text="Mở đầu dự án Vịnh Tiên",
                    confidence=0.95,
                    words=[],
                ),
                TranscriptSegmentRead(
                    segment_id="seg_timeline_002",
                    ordinal=1,
                    start_seconds=5,
                    end_seconds=8,
                    text="Không gian sống ven biển",
                    confidence=0.94,
                    words=[],
                ),
            ],
            provenance={"fixture": True},
            created_at=NOW,
        ),
        scenes=[
            SceneRead(
                scene_id="scn_timeline_001",
                ordinal=0,
                start_seconds=0,
                end_seconds=5,
                semantic_label="opening",
                description="Mở đầu",
                subjects=["project"],
                quality_score=0.9,
                motion_score=0.5,
                speech_score=0.8,
                confidence=0.95,
                evidence={"fixture": True},
            ),
            SceneRead(
                scene_id="scn_timeline_002",
                ordinal=1,
                start_seconds=5,
                end_seconds=10,
                semantic_label="benefit",
                description="Lợi ích",
                subjects=["landscape"],
                quality_score=0.92,
                motion_score=0.6,
                speech_score=0.7,
                confidence=0.94,
                evidence={"fixture": True},
            ),
        ],
        silence_decisions=[
            SilenceDecisionRead(
                decision_id="sil_timeline_001",
                start_seconds=4,
                end_seconds=5,
                padding_before_seconds=0,
                padding_after_seconds=0,
                enabled=True,
                reason="fixture silence",
                conflicts_with_speech=False,
                evidence={"fixture": True},
            )
        ],
        highlights=[
            HighlightRead(
                highlight_id="hlt_timeline_001",
                rank=1,
                highlight_score=0.9,
                reason="strong opening",
                recommended_start=0,
                recommended_end=3,
                recommended_platform="facebook_reels",
                scene_id="scn_timeline_001",
                evidence={"fixture": True},
            )
        ],
        error_code=None,
        provenance={"fixture": True},
        created_at=NOW,
        updated_at=NOW,
    )


def minimal_snapshot(asset_id: str) -> TimelineSnapshot:
    return TimelineSnapshot(
        duration_seconds=6,
        tracks=[
            TimelineTrack(
                track_id="trk_video_main",
                type="video",
                kind="source",
                label="Video gốc",
                order=0,
                clips=[
                    TimelineClip(
                        clip_id="clip_video_main",
                        kind="source",
                        label="Cảnh chính",
                        asset_id=asset_id,
                        source_start=0,
                        source_end=6,
                        timeline_start=0,
                        duration=6,
                        metadata={"content_type": "video/mp4"},
                    )
                ],
            ),
            TimelineTrack(
                track_id="trk_audio_main",
                type="audio",
                kind="original_audio",
                label="Âm thanh gốc",
                order=1,
                clips=[],
            ),
        ],
    )


async def setup_timeline_stack(tmp_path: Path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'timeline.db'}")
    session_factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(
            slug="timeline-tests",
            name="Timeline tests",
            owner_ref="test-owner",
            provenance={"fixture": True},
        )
    )
    project = await platform.create_project(
        workspace.workspace_id,
        ProjectCreate(
            slug="auto-edit-studio",
            name="Auto Edit Studio",
            niche="real_estate",
            provenance={"fixture": True},
        ),
    )
    storage = LocalObjectStorageProvider(tmp_path / "objects")
    await storage.ensure_ready()
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"deterministic-source-for-preview-contract")
    stored = await storage.put_file(
        object_key=f"workspaces/{workspace.workspace_id}/projects/{project.project_id}/source/source.mp4",
        path=source_path,
        content_type="video/mp4",
    )
    asset = await platform.register_asset(
        project.project_id,
        AssetRegister(
            asset_class="source",
            kind="video",
            filename="source.mp4",
            object_key=stored.object_key,
            content_type="video/mp4",
            size_bytes=stored.size_bytes,
            checksum_sha256=stored.checksum_sha256,
            storage_provider=stored.storage_provider,
            provenance={"fixture": True},
        ),
    )
    repository = TimelineRepository(session_factory)
    timeline, _ = await repository.create_timeline(
        project_id=project.project_id,
        source_analysis_id="ana_timeline_fixture",
        source_media_plan_id=None,
        snapshot=minimal_snapshot(asset.asset_id),
        actor_ref="test-owner",
    )
    return {
        "engine": engine,
        "platform": platform,
        "storage": storage,
        "project": project,
        "asset": asset,
        "repository": repository,
        "timeline": timeline,
    }


def test_timeline_contract_initial_build_and_editor_operations() -> None:
    request = TimelineCreateRequest(
        analysis_id="ana_timeline_fixture",
        media_plan_id="mpl_timeline_fixture",
    )
    assert request.media_plan_id == "mpl_timeline_fixture"
    asset = type(
        "AssetFixture",
        (),
        {
            "asset_id": "ast_timeline_fixture",
            "checksum_sha256": "b" * 64,
            "content_type": "video/mp4",
            "object_key": "source/fixture.mp4",
        },
    )()
    timeline = build_initial_timeline(
        analysis=analysis_fixture("prj_timeline_fixture", asset.asset_id),
        source_asset=asset,
        media_plan=None,
        media_assets={},
    )
    TimelineContractValidator(SCHEMA).validate(timeline)
    source_track = next(track for track in timeline.tracks if track.kind == "source")
    assert timeline.duration_seconds == 9
    assert len(source_track.clips) == 2
    assert timeline.source_media_mutated is False and timeline.publish_requested is False

    first = source_track.clips[0]
    split_at = first.timeline_start + first.duration / 2
    edited = apply_operations(
        timeline,
        [
            TimelineOperation(type="split", clip_id=first.clip_id, at_seconds=split_at),
            TimelineOperation(type="disable", clip_id=source_track.clips[1].clip_id, disabled=True),
        ],
    )
    TimelineContractValidator(SCHEMA).validate(edited)
    edited_source = next(track for track in edited.tracks if track.kind == "source")
    assert len(edited_source.clips) == 3
    assert sum(item.disabled for item in edited_source.clips) == 1
    assert edited.source_media_mutated is False and edited.publish_requested is False

    reordered_clip_id = edited_source.clips[-1].clip_id
    reordered = apply_operations(
        edited,
        [TimelineOperation(type="reorder", clip_id=reordered_clip_id, target_index=0)],
    )
    reordered_source = next(track for track in reordered.tracks if track.kind == "source")
    assert reordered_source.clips[0].clip_id == reordered_clip_id

    locked = edited.model_copy(deep=True)
    locked.tracks[0].locked = True
    with pytest.raises(TimelineEditError, match="locked"):
        apply_operations(
            locked,
            [TimelineOperation(type="delete", clip_id=locked.tracks[0].clips[0].clip_id)],
        )


@pytest.mark.asyncio
async def test_versions_conflicts_preview_invalidation_cancel_and_recovery(tmp_path: Path) -> None:
    stack = await setup_timeline_stack(tmp_path)
    repository: TimelineRepository = stack["repository"]
    timeline = stack["timeline"]
    queue = FakeQueue()
    preview_service = PreviewService(
        repository=repository,
        platform=stack["platform"],
        auto_edit_repository=type(
            "AssetRepository",
            (),
            {"get_asset": lambda _self, asset_id: _async_value(stack["asset"] if asset_id == stack["asset"].asset_id else None)},
        )(),
        object_storage=stack["storage"],
        queue=queue,
        renderer=DeterministicProxyRenderer(),
        staging_root=tmp_path / "previews",
    )
    preview = await preview_service.enqueue(stack["project"].project_id, PreviewCreateRequest())
    assert preview.status == "queued"
    assert queue.values == [(PREVIEW_QUEUE_KEY, preview.preview_id)]
    ready = await preview_service.process(preview.preview_id)
    assert ready.status == "ready" and ready.progress == 100
    assert ready.valid_for_current_timeline is True
    assert ready.manifest["proxy_only"] is True
    assert ready.manifest["playable"] is False
    assert ready.source_media_mutated is False and ready.publish_requested is False

    moved = apply_operations(
        timeline.snapshot,
        [TimelineOperation(type="move", clip_id="clip_video_main", timeline_start=1)],
    )
    version_two = await repository.commit_mutation(
        project_id=stack["project"].project_id,
        expected_version=1,
        snapshot=moved,
        mutation={"type": "test-move"},
        actor_ref="test-owner",
    )
    assert version_two.current_version == 2
    stale = await preview_service.get(stack["project"].project_id, preview.preview_id)
    assert stale and stale.status == "stale" and not stale.valid_for_current_timeline
    with pytest.raises(TimelineConflictError) as conflict:
        await repository.commit_mutation(
            project_id=stack["project"].project_id,
            expected_version=1,
            snapshot=moved,
            mutation={"type": "stale-write"},
            actor_ref="test-owner",
        )
    assert conflict.value.actual == 2

    queued = await preview_service.enqueue(stack["project"].project_id, PreviewCreateRequest())
    cancelled = await preview_service.cancel(stack["project"].project_id, queued.preview_id)
    assert cancelled and cancelled.status == "cancelled" and cancelled.cancellation_requested
    recovered = TimelineRepository(stack["repository"].session_factory)
    persisted = await recovered.get_timeline(stack["project"].project_id)
    assert persisted and persisted.current_version == 2
    assert len(await recovered.list_versions(stack["project"].project_id)) == 2
    await stack["engine"].dispose()


@pytest.mark.asyncio
async def test_auto_edit_studio_api_contract(tmp_path: Path) -> None:
    stack = await setup_timeline_stack(tmp_path)
    repository: TimelineRepository = stack["repository"]
    timeline_service = TimelineService(
        repository=repository,
        platform=stack["platform"],
        auto_edit_repository=None,  # type: ignore[arg-type]
        media_repository=None,  # type: ignore[arg-type]
        validator=TimelineContractValidator(SCHEMA),
    )
    queue = FakeQueue()
    preview_service = PreviewService(
        repository=repository,
        platform=stack["platform"],
        auto_edit_repository=type(
            "AssetRepository",
            (),
            {"get_asset": lambda _self, asset_id: _async_value(stack["asset"] if asset_id == stack["asset"].asset_id else None)},
        )(),
        object_storage=stack["storage"],
        queue=queue,
        renderer=DeterministicProxyRenderer(),
        staging_root=tmp_path / "previews-api",
    )
    app.state.timeline_service = timeline_service
    app.state.preview_service = preview_service
    install_test_human_auth(app, platform_repository=stack["platform"])
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=TEST_HUMAN_HEADERS
    ) as client:
        fetched = await client.get(f"/api/v1/projects/{stack['project'].project_id}/timeline")
        assert fetched.status_code == 200 and fetched.json()["current_version"] == 1
        changed = await client.put(
            f"/api/v1/projects/{stack['project'].project_id}/timeline",
            json={
                "expected_version": 1,
                "reason": "drag-drop",
                "operations": [
                    {"type": "move", "clip_id": "clip_video_main", "timeline_start": 0.5}
                ],
            },
        )
        assert changed.status_code == 200 and changed.json()["current_version"] == 2
        conflict = await client.put(
            f"/api/v1/projects/{stack['project'].project_id}/timeline",
            json={
                "expected_version": 1,
                "operations": [{"type": "disable", "clip_id": "clip_video_main", "disabled": True}],
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["current_version"] == 2
        versions = await client.get(
            f"/api/v1/projects/{stack['project'].project_id}/timeline/versions"
        )
        assert versions.status_code == 200 and len(versions.json()) == 2
        preview = await client.post(
            f"/api/v1/projects/{stack['project'].project_id}/preview", json={}
        )
        assert preview.status_code == 202 and preview.json()["status"] == "queued"
        cancelled = await client.post(
            f"/api/v1/projects/{stack['project'].project_id}/previews/{preview.json()['preview_id']}/cancel"
        )
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    await stack["engine"].dispose()


async def _async_value(value):
    return value
