from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from pydantic import ValidationError
from sqlalchemy import text

import app.auto_edit_providers as auto_edit_providers
from app.auto_edit_models import (
    AutoEditAnalysisRequest,
    MediaMetadata,
    UploadCompleteRequest,
    UploadInitRequest,
)
from app.auto_edit_logic import build_highlights, build_silence_decisions
from app.auto_edit_providers import (
    ContractOnlyTranscriptionProvider,
    DeterministicMediaSignalProvider,
    DeterministicTranscriptionProvider,
    FFprobeMediaProbe,
    ProviderNotConfigured,
    MediaSignals,
    ProviderSegment,
    ProviderTranscript,
    ProviderWord,
)
from app.auto_edit_repository import AutoEditRepository
from app.auto_edit_service import (
    AutoEditAnalysisService,
    UploadConflictError,
    UploadService,
    UploadSizeError,
)
from app.db import Base, create_engine, create_session_factory
from app.media_validation import MediaValidationError, safe_upload_filename, sniff_media
from app.main import app
from app.object_storage import LocalObjectStorageProvider
from app.platform_models import ProjectCreate, WorkspaceCreate
from app.repositories import PlatformRepository


class FakeMediaProbe:
    async def probe(self, path: Path, *, detected_content_type: str, media_kind: str) -> MediaMetadata:
        assert path.is_file()
        return MediaMetadata(
            media_kind=media_kind,
            detected_content_type=detected_content_type,
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            duration_seconds=16.0,
            width=1080,
            height=1920,
            fps=30,
            video_codec="h264",
            audio_codec="aac",
            audio_channels=2,
            audio_sample_rate=48000,
        )


async def bytes_stream(payload: bytes) -> AsyncIterator[bytes]:
    midpoint = max(1, len(payload) // 2)
    yield payload[:midpoint]
    yield payload[midpoint:]


def synthetic_mp4(size: int = 100_000) -> bytes:
    header = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
    return header + b"V" * (size - len(header))


async def setup_services(tmp_path: Path):
    database = tmp_path / "auto-edit.db"
    engine = create_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(slug="auto-edit-test", name="Auto Edit Test", owner_ref="test-owner")
    )
    project = await platform.create_project(
        workspace.workspace_id,
        ProjectCreate(slug="uploaded-footage", name="Uploaded Footage", niche="real_estate"),
    )
    version = await platform.ensure_initial_version(project.project_id, snapshot={"mode": "auto-edit"})
    await platform.seed_providers(
        [
            {
                "provider_key": "fixture-transcription",
                "display_name": "Fixture Transcript",
                "capability": "transcription",
                "adapter": "fixture",
                "routing_mode": "primary",
                "status": "healthy",
                "enabled": True,
                "supports_dry_run": True,
            },
            {
                "provider_key": "fixture-media-signals",
                "display_name": "Fixture Signals",
                "capability": "media_analysis",
                "adapter": "fixture",
                "routing_mode": "primary",
                "status": "healthy",
                "enabled": True,
                "supports_dry_run": True,
            },
        ]
    )
    object_storage = LocalObjectStorageProvider(tmp_path / "objects")
    await object_storage.ensure_ready()
    repository = AutoEditRepository(session_factory)
    upload_service = UploadService(
        repository=repository,
        platform=platform,
        object_storage=object_storage,
        media_probe=FakeMediaProbe(),
        staging_root=tmp_path / "uploads",
        default_part_size_bytes=64 * 1024,
        max_part_size_bytes=128 * 1024,
        max_upload_size_bytes=1024 * 1024,
    )
    analysis_service = AutoEditAnalysisService(
        repository=repository,
        platform=platform,
        object_storage=object_storage,
        transcription_provider=DeterministicTranscriptionProvider(),
        signal_provider=DeterministicMediaSignalProvider(),
        staging_root=tmp_path / "analysis",
    )
    return engine, session_factory, platform, repository, upload_service, analysis_service, project, version


async def upload_fixture(upload_service: UploadService, project, version, payload: bytes):
    checksum = hashlib.sha256(payload).hexdigest()
    upload = await upload_service.initialize(
        UploadInitRequest(
            project_id=project.project_id,
            project_version_id=version.project_version_id,
            filename="../Video thử nghiệm.MP4",
            media_kind="video",
            content_type="video/mp4",
            size_bytes=len(payload),
            checksum_sha256=checksum,
            part_size_bytes=64 * 1024,
        )
    )
    for part_number in range(1, upload.total_parts + 1):
        start = (part_number - 1) * upload.part_size_bytes
        part = payload[start : start + upload.part_size_bytes]
        await upload_service.store_part(
            upload.upload_id,
            part_number,
            bytes_stream(part),
            expected_part_sha256=hashlib.sha256(part).hexdigest(),
        )
    return await upload_service.complete(
        upload.upload_id,
        UploadCompleteRequest(checksum_sha256=checksum),
    )


def test_safe_filename_and_magic_byte_validation(tmp_path: Path) -> None:
    assert safe_upload_filename("../../Vị trí căn?.MP4") == "Vi-tri-can-.MP4"
    video = tmp_path / "video.bin"
    video.write_bytes(synthetic_mp4())
    assert sniff_media(video, "video/mp4") == ("video", "video/mp4")
    with pytest.raises(MediaValidationError, match="does not match"):
        sniff_media(video, "image/png")


def test_upload_contract_rejects_url_import_fake_extension_and_archive_payload(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="source_url"):
        UploadInitRequest.model_validate(
            {
                "project_id": "prj_fixture1234",
                "filename": "remote.mp4",
                "media_kind": "video",
                "content_type": "video/mp4",
                "size_bytes": 100,
                "source_url": "http://127.0.0.1/internal",
            }
        )

    fake_extension = tmp_path / "looks-like-video.mp4"
    fake_extension.write_bytes(b"\x89PNG\r\n\x1a\n" + b"P" * 64)
    with pytest.raises(MediaValidationError, match="does not match"):
        sniff_media(fake_extension, "video/mp4")

    archive = tmp_path / "archive-bomb.mp4"
    archive.write_bytes(b"PK\x03\x04" + b"Z" * 64)
    with pytest.raises(MediaValidationError, match="unsupported or unrecognized"):
        sniff_media(archive, "video/mp4")


@pytest.mark.asyncio
async def test_upload_size_and_ffprobe_arguments_fail_closed_without_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _, _, _, upload_service, _, project, version = await setup_services(tmp_path)
    with pytest.raises(UploadSizeError, match="configured maximum"):
        await upload_service.initialize(
            UploadInitRequest(
                project_id=project.project_id,
                project_version_id=version.project_version_id,
                filename="oversized.mp4",
                media_kind="video",
                content_type="video/mp4",
                size_bytes=1024 * 1024 + 1,
            )
        )

    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            payload = {
                "format": {"format_name": "mov,mp4", "duration": "1.0"},
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1080,
                        "height": 1920,
                        "r_frame_rate": "30/1",
                    }
                ],
            }
            return json.dumps(payload).encode("utf-8"), b""

    async def fake_exec(*arguments: str, **options: object) -> Process:
        captured["arguments"] = arguments
        captured["options"] = options
        return Process()

    monkeypatch.setattr(auto_edit_providers.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(auto_edit_providers.asyncio, "create_subprocess_exec", fake_exec)
    hostile_name = tmp_path / "clip;touch-owned.mp4"
    hostile_name.write_bytes(synthetic_mp4())
    await FFprobeMediaProbe().probe(
        hostile_name,
        detected_content_type="video/mp4",
        media_kind="video",
    )
    assert captured["arguments"][-1] == str(hostile_name)
    assert "shell" not in captured["options"]
    await engine.dispose()


def test_spoken_word_conflict_disables_cut_and_top_five_is_supported() -> None:
    transcript = ProviderTranscript(
        language="vi",
        confidence=1,
        segments=(
            ProviderSegment(
                start_seconds=1,
                end_seconds=2,
                text="không cắt lời",
                speaker=None,
                confidence=1,
                words=(ProviderWord(start_seconds=1, end_seconds=2, text="lời", confidence=1),),
            ),
        ),
        provenance={},
    )
    decisions = build_silence_decisions(
        signals=MediaSignals(
            shot_boundaries=(),
            silence_intervals=((0.5, 2.5, -50),),
            provenance={},
        ),
        transcript=transcript,
        config=AutoEditAnalysisRequest(
            asset_id="ast_fixture1234",
            top_highlights=5,
            padding_before=0,
            padding_after=0,
        ),
    )
    assert decisions[0]["conflicts_with_speech"] is True
    assert decisions[0]["enabled"] is False
    scenes = [
        {
            "ordinal": index,
            "start_seconds": float(index * 4),
            "end_seconds": float(index * 4 + 4),
            "description": f"Thông tin quan trọng số {index}",
            "speech_score": 0.8,
            "motion_score": 0.7,
        }
        for index in range(6)
    ]
    assert len(build_highlights(scenes=scenes, top_k=5)) == 5


@pytest.mark.asyncio
async def test_resumable_upload_hash_metadata_and_duplicate_detection(tmp_path: Path) -> None:
    engine, _, _, repository, upload_service, _, project, version = await setup_services(tmp_path)
    payload = synthetic_mp4()
    first = await upload_fixture(upload_service, project, version, payload)
    assert first.duplicate is False
    assert first.upload.safe_filename == "Video-thu-nghiem.MP4"
    assert first.upload.received_bytes == len(payload)
    assert first.media_metadata.duration_seconds == 16
    asset = await repository.get_asset(first.asset_id)
    assert asset is not None
    assert asset.provenance["source_type"] == "user_upload"
    assert asset.provenance["rights_status"] == "owned"
    assert asset.provenance["media_metadata"]["width"] == 1080

    second = await upload_fixture(upload_service, project, version, payload)
    assert second.duplicate is True
    assert second.asset_id == first.asset_id
    assert second.upload.duplicate_of_asset_id == first.asset_id
    await engine.dispose()


@pytest.mark.asyncio
async def test_upload_rejects_missing_parts_and_checksum_mismatch(tmp_path: Path) -> None:
    engine, _, _, _, upload_service, _, project, version = await setup_services(tmp_path)
    payload = synthetic_mp4()
    upload = await upload_service.initialize(
        UploadInitRequest(
            project_id=project.project_id,
            project_version_id=version.project_version_id,
            filename="safe.mp4",
            media_kind="video",
            content_type="video/mp4",
            size_bytes=len(payload),
            checksum_sha256="0" * 64,
            part_size_bytes=64 * 1024,
        )
    )
    with pytest.raises(UploadConflictError, match="not all"):
        await upload_service.complete(upload.upload_id, UploadCompleteRequest())
    first = payload[: upload.part_size_bytes]
    with pytest.raises(UploadConflictError, match="part checksum"):
        await upload_service.store_part(
            upload.upload_id,
            1,
            bytes_stream(first),
            expected_part_sha256="f" * 64,
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_analysis_persists_original_transcript_scenes_safe_silence_and_highlights(tmp_path: Path) -> None:
    engine, session_factory, platform, _, upload_service, analysis_service, project, version = (
        await setup_services(tmp_path)
    )
    completed = await upload_fixture(upload_service, project, version, synthetic_mp4())
    request = AutoEditAnalysisRequest(asset_id=completed.asset_id, top_highlights=3)
    analysis = await analysis_service.analyze(project.project_id, request)
    assert analysis.status == "succeeded"
    assert analysis.transcript is not None
    assert analysis.transcript.version == 1
    assert analysis.transcript.is_original_evidence is True
    assert analysis.transcript.provenance["original_evidence"] is True
    assert len(analysis.scenes) == 4
    assert len(analysis.highlights) == 3
    assert [item.rank for item in analysis.highlights] == [1, 2, 3]
    assert all(item.evidence["vision_used"] is False for item in analysis.scenes)
    assert all(item.evidence["source_media_mutated"] is False for item in analysis.silence_decisions)
    words = [word for segment in analysis.transcript.segments for word in segment.words]
    for decision in (item for item in analysis.silence_decisions if item.enabled):
        assert all(
            min(decision.end_seconds, word.end_seconds)
            <= max(decision.start_seconds, word.start_seconds)
            for word in words
        )
    assert analysis.source_media_mutated is False
    assert analysis.publish_requested is False

    replay = await analysis_service.analyze(project.project_id, request)
    assert replay.analysis_id == analysis.analysis_id
    assert len(await analysis_service.list(project.project_id)) == 1
    cost = await platform.project_cost_summary(project.project_id)
    assert cost.currency == "VND"
    assert cost.actual_cost == 0
    assert cost.records == 2

    restarted = AutoEditRepository(session_factory)
    recovered = await restarted.get_analysis(analysis.analysis_id)
    assert recovered == analysis
    await engine.dispose()


@pytest.mark.asyncio
async def test_missing_live_transcription_provider_fails_closed(tmp_path: Path) -> None:
    engine, _, platform, repository, upload_service, _, project, version = await setup_services(tmp_path)
    completed = await upload_fixture(upload_service, project, version, synthetic_mp4())
    service = AutoEditAnalysisService(
        repository=repository,
        platform=platform,
        object_storage=upload_service.object_storage,
        transcription_provider=ContractOnlyTranscriptionProvider(),
        signal_provider=DeterministicMediaSignalProvider(),
        staging_root=tmp_path / "analysis-contract",
    )
    with pytest.raises(ProviderNotConfigured):
        await service.analyze(
            project.project_id,
            AutoEditAnalysisRequest(asset_id=completed.asset_id, top_highlights=5),
        )
    failed = (await service.list(project.project_id))[0]
    assert failed.status == "failed"
    assert failed.error_code == "PROVIDER_NOT_CONFIGURED"
    assert failed.publish_requested is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_upload_and_analysis_api_contract(tmp_path: Path) -> None:
    engine, _, platform, _, upload_service, analysis_service, project, version = await setup_services(tmp_path)
    app.state.upload_service = upload_service
    app.state.auto_edit_analysis_service = analysis_service
    install_test_human_auth(app, platform_repository=platform)
    payload = synthetic_mp4()
    checksum = hashlib.sha256(payload).hexdigest()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=TEST_HUMAN_HEADERS
    ) as client:
        initialized = await client.post(
            "/api/v1/uploads/init",
            json={
                "project_id": project.project_id,
                "project_version_id": version.project_version_id,
                "filename": "api-upload.mp4",
                "media_kind": "video",
                "content_type": "video/mp4",
                "size_bytes": len(payload),
                "checksum_sha256": checksum,
                "part_size_bytes": 65536,
                "rights_status": "owned",
                "license": "user-provided",
            },
        )
        assert initialized.status_code == 201, initialized.text
        upload = initialized.json()
        for part_number in range(1, upload["total_parts"] + 1):
            start = (part_number - 1) * upload["part_size_bytes"]
            part = payload[start : start + upload["part_size_bytes"]]
            response = await client.put(
                f"/api/v1/uploads/{upload['upload_id']}/parts/{part_number}",
                content=part,
                headers={"X-Part-SHA256": hashlib.sha256(part).hexdigest()},
            )
            assert response.status_code == 200, response.text
        completed = await client.post(
            f"/api/v1/uploads/{upload['upload_id']}/complete",
            json={"checksum_sha256": checksum},
        )
        assert completed.status_code == 200, completed.text
        analyzed = await client.post(
            f"/api/v1/projects/{project.project_id}/analyze",
            json={"asset_id": completed.json()["asset_id"], "top_highlights": 3},
        )
        assert analyzed.status_code == 201, analyzed.text
        result = analyzed.json()
        assert result["status"] == "succeeded"
        assert result["source_media_mutated"] is False
        assert result["publish_requested"] is False
        recovered = await client.get(
            f"/api/v1/projects/{project.project_id}/analyses/{result['analysis_id']}"
        )
        assert recovered.status_code == 200
        assert recovered.json() == result
    await engine.dispose()
