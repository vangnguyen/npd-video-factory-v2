import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import capabilities


def test_v2_09_rejects_partial_publish_enablement() -> None:
    with pytest.raises(ValidationError, match="separate external execution gate"):
        Settings(_env_file=None, publish_enabled=True)
    with pytest.raises(ValidationError, match="requires PUBLISH_ENABLED"):
        Settings(_env_file=None, publish_external_execution_enabled=True)
    with pytest.raises(ValidationError, match="explicit owner gate"):
        Settings(
            _env_file=None,
            publish_enabled=True,
            publish_external_execution_enabled=True,
            youtube_publishing_credential_ref="secret://video-factory/youtube",
        )


def test_v2_09_rejects_raw_credentials_and_ci_external_publish() -> None:
    with pytest.raises(ValidationError, match="external secret references"):
        Settings(_env_file=None, youtube_publishing_credential_ref="plain-text-token")
    with pytest.raises(ValidationError, match="prohibit external publishing"):
        Settings(
            _env_file=None,
            app_env="ci",
            publish_enabled=True,
            publish_external_execution_enabled=True,
            publish_owner_gate_enabled=True,
            youtube_publishing_credential_ref="secret://video-factory/youtube",
        )


def test_v2_01_rejects_disabling_human_approval() -> None:
    with pytest.raises(ValidationError, match="human approval"):
        Settings(_env_file=None, human_approval_required=False)


def test_v3_01_human_auth_config_bounds_and_production_boundary() -> None:
    with pytest.raises(ValidationError, match="token TTL"):
        Settings(_env_file=None, human_auth_max_token_ttl_seconds=86_401)
    with pytest.raises(ValidationError, match="rate limit"):
        Settings(_env_file=None, human_rate_limit_per_minute=9)
    with pytest.raises(ValidationError, match="human auth boundary"):
        Settings(
            _env_file=None,
            app_env="production",
            human_api_enabled=False,
            trend_fixture_enabled=False,
            auto_edit_fixture_enabled=False,
            vision_fixture_enabled=False,
            media_fixture_enabled=False,
            analytics_fixture_enabled=False,
            transcription_provider="contract",
            auto_edit_signal_provider="ffmpeg",
            vision_provider="contract",
            object_storage_provider="s3",
            object_storage_access_key="test-access-key",
            object_storage_secret_key="test-secret-key",
        )


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
        media_fixture_enabled=False,
        analytics_fixture_enabled=False,
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
    assert production.analytics_fixture_enabled is False


def test_v2_10_rejects_live_analytics_and_raw_credential_values() -> None:
    with pytest.raises(ValidationError, match="not activated in V2-10"):
        Settings(_env_file=None, analytics_external_execution_enabled=True)
    with pytest.raises(ValidationError, match="external secret references"):
        Settings(_env_file=None, youtube_analytics_credential_ref="plain-text-token")


def test_v2_11_webhook_delivery_gates_and_allowlist_fail_closed() -> None:
    with pytest.raises(ValidationError, match="requires AGENT_HUB_BRIDGE_ENABLED"):
        Settings(_env_file=None, agent_hub_webhook_mode="fixture")
    with pytest.raises(ValidationError, match="explicit external delivery gate"):
        Settings(_env_file=None, agent_hub_bridge_enabled=True, agent_hub_webhook_mode="http")
    with pytest.raises(ValidationError, match="HTTPS and an allowlisted host"):
        Settings(
            _env_file=None,
            agent_hub_bridge_enabled=True,
            agent_hub_webhook_mode="http",
            agent_hub_webhook_external_delivery_enabled=True,
            agent_hub_webhook_url="https://untrusted.example/events",
        )
    with pytest.raises(ValidationError, match="exact versioned event path"):
        Settings(
            _env_file=None,
            agent_hub_bridge_enabled=True,
            agent_hub_webhook_mode="http",
            agent_hub_webhook_external_delivery_enabled=True,
            agent_hub_webhook_url=(
                "https://mkt.ngocphuongdong.com/agent-hub/events/v1?token=forbidden"
            ),
        )
    with pytest.raises(ValidationError, match="prohibit external Agent Hub webhooks"):
        Settings(
            _env_file=None,
            app_env="ci",
            agent_hub_bridge_enabled=True,
            agent_hub_webhook_mode="http",
            agent_hub_webhook_external_delivery_enabled=True,
            agent_hub_webhook_url="https://mkt.ngocphuongdong.com/agent-hub/events/v1",
        )
    with pytest.raises(ValidationError, match="fixture Agent Hub webhooks are prohibited"):
        Settings(
            _env_file=None,
            app_env="production",
            trend_fixture_enabled=False,
            auto_edit_fixture_enabled=False,
            vision_fixture_enabled=False,
            media_fixture_enabled=False,
            analytics_fixture_enabled=False,
            transcription_provider="contract",
            auto_edit_signal_provider="ffmpeg",
            vision_provider="contract",
            object_storage_provider="s3",
            object_storage_access_key="test-access-key",
            object_storage_secret_key="test-secret-key",
            agent_hub_bridge_enabled=True,
            agent_hub_webhook_mode="fixture",
        )


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


def test_v3_01_02_global_provider_gate_is_vnd_only_and_cannot_be_activated() -> None:
    with pytest.raises(ValidationError, match="must be VND"):
        Settings(_env_file=None, provider_budget_currency="USD")
    with pytest.raises(ValidationError, match="G-02 owner gate"):
        Settings(_env_file=None, provider_per_operation_limit_vnd=1, provider_daily_limit_vnd=1)
    with pytest.raises(ValidationError, match="not activated in V3-01-02"):
        Settings(_env_file=None, provider_external_execution_enabled=True)
    with pytest.raises(ValidationError, match="kill switch must remain engaged"):
        Settings(_env_file=None, provider_global_kill_switch_engaged=False)
    with pytest.raises(ValidationError, match="REQUEST_TIMEOUT_SECONDS"):
        Settings(_env_file=None, provider_request_timeout_seconds=0)
    with pytest.raises(ValidationError, match="MAX_CONCURRENT_CALLS"):
        Settings(_env_file=None, provider_max_concurrent_calls=0)


@pytest.mark.asyncio
async def test_capabilities_report_no_agent_hub_or_publishing_runtime() -> None:
    result = await capabilities()
    assert result["agent_hub_runtime_dependency"] is False
    assert result["agent_hub_bridge_implemented"] is True
    assert result["agent_hub_bridge_enabled"] is False
    assert result["agent_hub_bridge_contract"] == "agent-hub-bridge.v1"
    assert result["agent_hub_webhook_external_delivery_enabled"] is False
    assert result["shared_agent_hub_database"] is False
    assert result["shared_agent_hub_redis"] is False
    assert result["publishing_implemented"] is True
    assert result["publishing_mode"] == "dry_run_only"
    assert result["publish_enabled"] is False
    assert result["publish_external_execution_enabled"] is False
    assert result["publish_owner_gate_enabled"] is False
    assert result["human_approval_required"] is True
    assert result["human_authentication"] == "short_lived_external_bearer"
    assert result["human_rbac_roles"] == ["viewer", "editor", "reviewer", "owner"]
    assert result["workspace_isolation"] == "deny_by_default"
    assert result["analytics_implemented"] is True
    assert result["analytics_external_execution_enabled"] is False
    assert result["analytics_historical_snapshots"] is True
    assert result["winner_detection"] == "explainable_recommendation_only"
    assert result["learning_feedback_auto_applied"] is False
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
    assert result["final_render_publish"] == "dry_run_validation_only"
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
    assert result["provider_safety_plane"] == "enforced"
    assert result["provider_external_execution_enabled"] is False
    assert result["provider_paid_execution_enabled"] is False
    assert result["provider_global_kill_switch_engaged"] is True
    assert result["provider_budget_currency"] == "VND"
