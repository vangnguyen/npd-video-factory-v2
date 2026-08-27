import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import capabilities


def test_v2_01_rejects_publish_enablement() -> None:
    with pytest.raises(ValidationError, match="publishing is not implemented"):
        Settings(_env_file=None, publish_enabled=True)


def test_v2_01_rejects_disabling_human_approval() -> None:
    with pytest.raises(ValidationError, match="human approval"):
        Settings(_env_file=None, human_approval_required=False)


def test_v2_03_rejects_fixture_provider_in_production() -> None:
    with pytest.raises(ValidationError, match="trend fixtures must be disabled"):
        Settings(
            _env_file=None,
            app_env="production",
            trend_fixture_enabled=True,
            object_storage_provider="s3",
            object_storage_access_key="test-access-key",
            object_storage_secret_key="test-secret-key",
        )


def test_v2_04_allows_all_fixture_providers_to_be_disabled_in_production() -> None:
    production = Settings(
        _env_file=None,
        app_env="production",
        trend_fixture_enabled=False,
        auto_edit_fixture_enabled=False,
        vision_fixture_enabled=False,
        transcription_provider="contract",
        auto_edit_signal_provider="ffmpeg",
        vision_provider="contract",
        object_storage_provider="s3",
        object_storage_access_key="test-access-key",
        object_storage_secret_key="test-secret-key",
    )

    assert production.trend_fixture_enabled is False
    assert production.auto_edit_fixture_enabled is False
    assert production.vision_fixture_enabled is False


def test_v2_04_rejects_auto_edit_fixture_in_production() -> None:
    with pytest.raises(ValidationError, match="auto-edit fixtures must be disabled"):
        Settings(
            _env_file=None,
            app_env="production",
            trend_fixture_enabled=False,
            auto_edit_fixture_enabled=True,
            object_storage_provider="s3",
            object_storage_access_key="test-access-key",
            object_storage_secret_key="test-secret-key",
        )


def test_v2_04_rejects_upload_limit_that_exceeds_durable_schema() -> None:
    with pytest.raises(ValidationError, match="durable schema limit"):
        Settings(_env_file=None, upload_max_size_bytes=2_147_483_648)


def test_v2_05_rejects_vision_fixture_in_production() -> None:
    with pytest.raises(ValidationError, match="Vision fixtures must be disabled"):
        Settings(
            _env_file=None,
            app_env="production",
            trend_fixture_enabled=False,
            auto_edit_fixture_enabled=False,
            transcription_provider="contract",
            auto_edit_signal_provider="ffmpeg",
            vision_fixture_enabled=True,
            vision_provider="fixture",
            object_storage_provider="s3",
            object_storage_access_key="test-access-key",
            object_storage_secret_key="test-secret-key",
        )


def test_v2_06_rejects_media_fixture_in_production() -> None:
    with pytest.raises(ValidationError, match="media fixtures must be disabled"):
        Settings(
            _env_file=None,
            app_env="production",
            trend_fixture_enabled=False,
            auto_edit_fixture_enabled=False,
            vision_fixture_enabled=False,
            transcription_provider="contract",
            auto_edit_signal_provider="ffmpeg",
            vision_provider="contract",
            media_fixture_enabled=True,
            stock_media_provider="fixture",
            image_generation_provider="fixture",
            video_generation_provider="fixture",
            object_storage_provider="s3",
            object_storage_access_key="test-access-key",
            object_storage_secret_key="test-secret-key",
        )


def test_v2_06_paid_and_comfyui_execution_require_explicit_parent_gates() -> None:
    with pytest.raises(ValidationError, match="paid media execution requires external"):
        Settings(_env_file=None, media_paid_execution_enabled=True)
    with pytest.raises(ValidationError, match="ComfyUI execution requires"):
        Settings(_env_file=None, comfyui_execution_enabled=True)
    with pytest.raises(ValidationError, match="generation providers require"):
        Settings(_env_file=None, image_generation_provider="comfyui")


@pytest.mark.asyncio
async def test_capabilities_report_no_agent_hub_or_publishing_runtime() -> None:
    result = await capabilities()
    assert result["agent_hub_runtime_dependency"] is False
    assert result["publishing_implemented"] is False
    assert result["publish_enabled"] is False
    assert result["human_approval_required"] is True
    assert result["auto_edit_analysis"] is True
    assert result["auto_edit_timeline"] is True
    assert result["timeline_versioning"] is True
    assert result["timeline_optimistic_concurrency"] is True
    assert result["proxy_preview"] == "asynchronous_540p"
    assert result["preview_audio"] == "version_bound_av_review"
    assert result["subtitle_editor"] is True
    assert result["audio_mixer"] is True
    assert result["final_render_profiles"] == [
        "vertical-1080x1920",
        "landscape-1920x1080",
        "square-1080x1080",
    ]
    assert result["preview_publish"] is False
    assert result["source_media_mutation"] is False
    assert result["vision_analysis"] is True
    assert result["ocr"] is True
    assert result["subject_tracking"] is True
    assert result["smart_reframe"] is True
    assert result["smart_reframe_aspect_ratios"] == ["9:16", "16:9", "1:1", "4:5"]
    assert result["smart_reframe_preview_only"] is True
    assert result["media_intelligence"] is True
    assert result["media_planner"] is True
    assert result["broll_planner"] is True
    assert result["media_rights_gate"] == "fail_closed"
    assert result["media_resolution"] == "asynchronous"
    assert result["media_fixture_production_eligible"] is False
    assert result["comfyui_execution_enabled"] is False
    assert result["media_external_execution_enabled"] is False
    assert result["media_paid_execution_enabled"] is False
