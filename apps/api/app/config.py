from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .provider_safety import ProviderTimeoutEnvelope


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql+asyncpg://video_factory:development-only@postgres:5432/video_factory"
    redis_url: str = "redis://redis:6379/0"
    job_storage_root: Path = Path("/workspace/storage/jobs")
    asset_storage_root: Path = Path("/workspace/storage/assets")
    contracts_root: Path = Path("/workspace/packages/contracts")
    renderer_url: str = "http://renderer:3001"
    object_storage_provider: str = "local"
    object_storage_local_root: Path = Path("/workspace/storage/object-store")
    object_storage_endpoint_url: str = "http://minio:9000"
    object_storage_bucket: str = "npd-video-factory-v2"
    object_storage_region: str = "us-east-1"
    object_storage_access_key: str = ""
    object_storage_secret_key: str = ""
    object_storage_auto_create_bucket: bool = False
    default_workspace_slug: str = "npd-local"
    default_workspace_name: str = "NPD Local Workspace"
    default_workspace_owner_ref: str = "local-owner"
    trend_fixture_enabled: bool = True
    trend_fixture_path: Path = Path(__file__).resolve().parent / "fixtures" / "trend-signals.json"
    auto_edit_fixture_enabled: bool = True
    transcription_provider: str = "fixture"
    openai_transcription_model: str = ""
    openai_transcription_credential_alias: str = "secret://openai/codex-video"
    openai_transcription_language: str = "vi"
    openai_transcription_max_file_bytes: int = 25_000_000
    openai_transcription_max_duration_seconds: float = 600.0
    openai_transcription_estimated_cost_vnd: Decimal = Decimal("0")
    openai_transcription_vnd_per_minute: Decimal = Decimal("0")
    auto_edit_signal_provider: str = "fixture"
    ffprobe_path: str = "ffprobe"
    ffmpeg_path: str = "ffmpeg"
    upload_staging_root: Path = Path("/workspace/storage/uploads")
    analysis_staging_root: Path = Path("/workspace/storage/analysis")
    vision_fixture_enabled: bool = True
    vision_provider: str = "fixture"
    vision_staging_root: Path = Path("/workspace/storage/vision")
    openai_vision_model: str = "gpt-5-mini"
    openai_vision_credential_alias: str = "secret://openai/codex-video"
    openai_vision_image_detail: str = "high"
    openai_vision_max_frames: int = 8
    openai_vision_max_dimension_pixels: int = 2048
    openai_vision_input_token_ceiling: int = 16_384
    openai_vision_max_output_tokens: int = 8000
    openai_vision_estimated_cost_vnd: Decimal = Decimal("0")
    openai_vision_input_vnd_per_million_tokens: Decimal = Decimal("0")
    openai_vision_cached_input_vnd_per_million_tokens: Decimal = Decimal("0")
    openai_vision_output_vnd_per_million_tokens: Decimal = Decimal("0")
    media_fixture_enabled: bool = False
    stock_media_provider: str = "contract"
    image_generation_provider: str = "contract"
    video_generation_provider: str = "contract"
    media_staging_root: Path = Path("/workspace/storage/media-resolution")
    preview_staging_root: Path = Path("/workspace/storage/previews")
    preview_download_root: Path = Path("/workspace/storage/preview-downloads")
    production_render_staging_root: Path = Path("/workspace/storage/production-renders")
    production_render_download_root: Path = Path("/workspace/storage/production-downloads")
    media_external_execution_enabled: bool = False
    media_paid_execution_enabled: bool = False
    comfyui_bridge_url: str = "http://comfyui-bridge:8011"
    comfyui_execution_enabled: bool = False
    comfyui_bridge_timeout_seconds: float = 300.0
    comfyui_image_workflow_id: str = "npd-text-to-image-v1"
    comfyui_video_workflow_id: str = "npd-video-generation-v1"
    upload_default_part_size_bytes: int = 8 * 1024 * 1024
    upload_max_part_size_bytes: int = 32 * 1024 * 1024
    # Asset and upload byte counts use PostgreSQL INTEGER in the current
    # durable schema, so the configurable ceiling must stay within int32.
    upload_max_size_bytes: int = 2_000_000_000
    media_malware_scanner_mode: str = "fixture"
    media_malware_scanner_host: str = "clamd"
    media_malware_scanner_port: int = 3310
    media_malware_scan_timeout_seconds: float = 30.0
    media_quarantine_retention_days: int = 30
    tts_provider: str = "espeak"
    openai_api_key: str = ""
    audio_tts_provider: str = "espeak"
    audio_external_execution_enabled: bool = False
    audio_tts_voice: str = "vi"
    audio_tts_rate: int = 145
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "marin"
    openai_tts_instructions: str = ""
    openai_base_url: str = "https://api.openai.com"
    renderer_timeout_seconds: float = 600.0
    public_base_url: str = "http://localhost:8000"
    video_factory_brand_name: str = "NPD Video Factory"
    video_factory_logo_path: Path = Path("/workspace/storage/assets/brand/default-logo.png")
    publish_enabled: bool = False
    publish_external_execution_enabled: bool = False
    publish_owner_gate_enabled: bool = False
    publishing_credential_store: str = "external"
    youtube_publishing_credential_ref: str = ""
    tiktok_publishing_credential_ref: str = ""
    instagram_publishing_credential_ref: str = ""
    facebook_publishing_credential_ref: str = ""
    analytics_fixture_enabled: bool = True
    analytics_external_execution_enabled: bool = False
    analytics_scheduled_refresh_enabled: bool = False
    analytics_max_attempts: int = 3
    analytics_retry_base_seconds: int = 30
    analytics_retry_max_seconds: int = 900
    youtube_analytics_credential_ref: str = ""
    tiktok_analytics_credential_ref: str = ""
    instagram_analytics_credential_ref: str = ""
    facebook_analytics_credential_ref: str = ""
    agent_hub_bridge_enabled: bool = False
    agent_hub_service_keys_file: Path = Path("/run/secrets/video-factory-agent-hub.json")
    agent_hub_webhook_signing_keys_file: Path = Path("/run/secrets/video-factory-agent-hub.json")
    agent_hub_webhook_mode: str = "disabled"
    agent_hub_webhook_destination_ref: str = "agent-hub"
    agent_hub_webhook_url: str = ""
    agent_hub_webhook_allowed_hosts: str = "mkt.ngocphuongdong.com"
    agent_hub_webhook_external_delivery_enabled: bool = False
    agent_hub_webhook_timeout_seconds: float = 10.0
    agent_hub_webhook_max_attempts: int = 3
    agent_hub_webhook_retry_base_seconds: int = 30
    agent_hub_webhook_retry_max_seconds: int = 900
    service_auth_max_clock_skew_seconds: int = 300
    service_auth_replay_ttl_seconds: int = 600
    human_api_enabled: bool = True
    human_write_enabled: bool = False
    human_auth_keys_file: Path = Path("/run/secrets/video-factory-human-auth.json")
    human_auth_max_token_ttl_seconds: int = 86_400
    human_rate_limit_per_minute: int = 300
    human_approval_required: bool = True
    provider_external_execution_enabled: bool = False
    provider_paid_execution_enabled: bool = False
    provider_global_kill_switch_engaged: bool = True
    provider_verified_gate_bundle_enabled: bool = False
    provider_verified_gate_bundle_file: Path = Path(
        "/run/secrets/video-factory-provider-gates.json"
    )
    provider_verified_gate_bundle_sha256: str = ""
    provider_gate_expected_rc_commit: str = ""
    provider_gate_expected_rc_tag: str = ""
    provider_budget_currency: str = "VND"
    provider_per_operation_limit_vnd: Decimal = Decimal("0")
    provider_daily_limit_vnd: Decimal = Decimal("0")
    provider_retry_max_attempts: int = 3
    provider_http_timeout_seconds: float = 90.0
    controller_hard_timeout_seconds: float = 120.0
    provider_retry_base_seconds: float = 1.0
    provider_retry_max_seconds: float = 30.0
    provider_retry_max_elapsed_seconds: float = 120.0
    provider_poll_max_attempts: int = 20
    provider_poll_interval_seconds: float = 2.0
    provider_max_concurrent_calls: int = 2
    provider_circuit_failure_threshold: int = 3
    provider_circuit_cooldown_seconds: int = 60
    provider_operation_lease_seconds: int = 900
    provider_operation_retention_days: int = 400
    provider_retention_cleanup_enabled: bool = False
    operations_queue_backlog_warning: int = 50
    operations_failed_jobs_warning: int = 1
    operations_disk_warning_percent: float = 85.0
    operations_disk_critical_percent: float = 95.0
    operations_evidence_retention_days: int = 400
    operations_log_retention_days: int = 30
    operations_external_notifications_enabled: bool = False

    @model_validator(mode="after")
    def enforce_v2_safety_boundary(self) -> "Settings":
        if not self.human_approval_required:
            raise ValueError("human approval must remain required")
        if not 900 <= self.human_auth_max_token_ttl_seconds <= 86_400:
            raise ValueError("human auth token TTL must be between 15 minutes and 24 hours")
        if not 10 <= self.human_rate_limit_per_minute <= 1_000:
            raise ValueError("human API rate limit must be between 10 and 1000 requests per minute")
        if self.app_env.lower() == "production" and not self.human_api_enabled:
            raise ValueError("production readiness requires the human auth boundary to be enabled")
        if self.publish_external_execution_enabled and not self.publish_enabled:
            raise ValueError("external publishing execution requires PUBLISH_ENABLED=true")
        if self.publish_enabled and not self.publish_external_execution_enabled:
            raise ValueError("PUBLISH_ENABLED requires the separate external execution gate")
        if self.publish_owner_gate_enabled and not (
            self.publish_enabled and self.publish_external_execution_enabled
        ):
            raise ValueError("publishing owner gate requires both publish execution gates")
        if self.publish_enabled and not self.publish_owner_gate_enabled:
            raise ValueError("live publishing requires the explicit owner gate")
        if self.publishing_credential_store != "external":
            raise ValueError("publishing credentials must use an external encrypted secret store")
        credential_refs = (
            self.youtube_publishing_credential_ref,
            self.tiktok_publishing_credential_ref,
            self.instagram_publishing_credential_ref,
            self.facebook_publishing_credential_ref,
        )
        for credential_ref in credential_refs:
            if credential_ref and not credential_ref.startswith(("secret://", "vault://", "external://")):
                raise ValueError("publishing credential values must be external secret references, never tokens")
        if self.publish_enabled and not any(credential_refs):
            raise ValueError("live publishing requires at least one external credential reference")
        if self.app_env.lower() in {"ci", "test"} and (
            self.publish_enabled or self.publish_external_execution_enabled or self.publish_owner_gate_enabled
        ):
            raise ValueError("CI and test environments prohibit external publishing")
        analytics_credential_refs = (
            self.youtube_analytics_credential_ref,
            self.tiktok_analytics_credential_ref,
            self.instagram_analytics_credential_ref,
            self.facebook_analytics_credential_ref,
        )
        for credential_ref in analytics_credential_refs:
            if credential_ref and not credential_ref.startswith(("secret://", "vault://", "external://")):
                raise ValueError("analytics credential values must be external secret references, never tokens")
        if self.analytics_external_execution_enabled:
            raise ValueError("official analytics API execution is not activated in V2-10")
        if not 1 <= self.analytics_max_attempts <= 10:
            raise ValueError("ANALYTICS_MAX_ATTEMPTS must be between 1 and 10")
        if self.analytics_retry_base_seconds < 1:
            raise ValueError("ANALYTICS_RETRY_BASE_SECONDS must be positive")
        if self.analytics_retry_max_seconds < self.analytics_retry_base_seconds:
            raise ValueError("analytics retry maximum cannot be lower than the base delay")
        if self.agent_hub_webhook_mode not in {"disabled", "fixture", "http"}:
            raise ValueError("AGENT_HUB_WEBHOOK_MODE must be disabled, fixture or http")
        if self.agent_hub_webhook_mode != "disabled" and not self.agent_hub_bridge_enabled:
            raise ValueError("webhook delivery requires AGENT_HUB_BRIDGE_ENABLED=true")
        if self.agent_hub_webhook_external_delivery_enabled and self.agent_hub_webhook_mode != "http":
            raise ValueError("external webhook delivery requires AGENT_HUB_WEBHOOK_MODE=http")
        if self.agent_hub_webhook_mode == "http":
            if not self.agent_hub_webhook_external_delivery_enabled:
                raise ValueError("HTTP webhook mode requires its explicit external delivery gate")
            parsed = urlparse(self.agent_hub_webhook_url)
            allowed_hosts = {host.strip().lower() for host in self.agent_hub_webhook_allowed_hosts.split(",") if host.strip()}
            if parsed.scheme != "https" or not parsed.hostname or parsed.hostname.lower() not in allowed_hosts:
                raise ValueError("Agent Hub webhook URL must use HTTPS and an allowlisted host")
            if parsed.username or parsed.password:
                raise ValueError("Agent Hub webhook URL must not contain credentials")
            if (
                parsed.path != "/agent-hub/events/v1"
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "Agent Hub webhook URL must use the exact versioned event path without query data"
                )
        if self.app_env.lower() in {"ci", "test"} and self.agent_hub_webhook_external_delivery_enabled:
            raise ValueError("CI and test environments prohibit external Agent Hub webhooks")
        if self.app_env.lower() == "production" and self.agent_hub_webhook_mode == "fixture":
            raise ValueError("fixture Agent Hub webhooks are prohibited in production")
        if not 1 <= self.agent_hub_webhook_max_attempts <= 10:
            raise ValueError("AGENT_HUB_WEBHOOK_MAX_ATTEMPTS must be between 1 and 10")
        if self.agent_hub_webhook_retry_base_seconds < 1:
            raise ValueError("Agent Hub webhook retry base must be positive")
        if self.agent_hub_webhook_retry_max_seconds < self.agent_hub_webhook_retry_base_seconds:
            raise ValueError("Agent Hub webhook retry maximum cannot be lower than the base delay")
        if not 30 <= self.service_auth_max_clock_skew_seconds <= 900:
            raise ValueError("service auth clock skew must be between 30 and 900 seconds")
        if self.service_auth_replay_ttl_seconds < self.service_auth_max_clock_skew_seconds:
            raise ValueError("service auth replay TTL cannot be shorter than the clock-skew window")
        if self.app_env == "production" and self.trend_fixture_enabled:
            raise ValueError("deterministic trend fixtures must be disabled in production")
        if self.app_env == "production" and self.auto_edit_fixture_enabled:
            raise ValueError("deterministic auto-edit fixtures must be disabled in production")
        if self.app_env == "production" and self.vision_fixture_enabled:
            raise ValueError("deterministic Vision fixtures must be disabled in production")
        if self.app_env == "production" and self.media_fixture_enabled:
            raise ValueError("deterministic media fixtures must be disabled in production")
        if self.app_env == "production" and self.analytics_fixture_enabled:
            raise ValueError("deterministic analytics fixtures must be disabled in production")
        if self.transcription_provider not in {"fixture", "contract", "openai"}:
            raise ValueError("TRANSCRIPTION_PROVIDER must be fixture, contract or openai")
        if self.auto_edit_signal_provider not in {"fixture", "ffmpeg"}:
            raise ValueError("AUTO_EDIT_SIGNAL_PROVIDER must be fixture or ffmpeg")
        if self.vision_provider not in {"fixture", "contract", "openai"}:
            raise ValueError("VISION_PROVIDER must be fixture, contract or openai")
        if self.stock_media_provider not in {"fixture", "contract"}:
            raise ValueError("STOCK_MEDIA_PROVIDER must be fixture or contract")
        if self.image_generation_provider not in {"fixture", "contract", "comfyui"}:
            raise ValueError("IMAGE_GENERATION_PROVIDER must be fixture, contract or comfyui")
        if self.video_generation_provider not in {"fixture", "contract", "comfyui"}:
            raise ValueError("VIDEO_GENERATION_PROVIDER must be fixture, contract or comfyui")
        if self.transcription_provider == "fixture" and not self.auto_edit_fixture_enabled:
            raise ValueError("fixture transcription requires AUTO_EDIT_FIXTURE_ENABLED=true")
        if self.transcription_provider == "openai":
            if self.openai_transcription_model != "whisper-1":
                raise ValueError(
                    "OpenAI transcription requires an explicitly configured model compatible "
                    "with the strict native timestamp contract"
                )
            if not self.openai_transcription_credential_alias.startswith(
                ("secret://", "vault://", "external://")
            ):
                raise ValueError(
                    "OpenAI transcription credentials must be referenced by external alias"
                )
            if self.openai_transcription_language != "vi":
                raise ValueError("OpenAI transcription is locked to Vietnamese for Flow A")
            if not 1 <= self.openai_transcription_max_file_bytes <= 25_000_000:
                raise ValueError("OpenAI transcription file bound exceeds the API contract")
            if not 1 <= self.openai_transcription_max_duration_seconds <= 3_600:
                raise ValueError("OpenAI transcription duration bound is invalid")
            if (
                self.openai_transcription_estimated_cost_vnd < 0
                or self.openai_transcription_vnd_per_minute < 0
            ):
                raise ValueError("OpenAI transcription VND values cannot be negative")
        if self.auto_edit_signal_provider == "fixture" and not self.auto_edit_fixture_enabled:
            raise ValueError("fixture media signals require AUTO_EDIT_FIXTURE_ENABLED=true")
        if self.vision_provider == "fixture" and not self.vision_fixture_enabled:
            raise ValueError("fixture Vision provider requires VISION_FIXTURE_ENABLED=true")
        if self.openai_vision_model != "gpt-5-mini":
            raise ValueError("OPENAI_VISION_MODEL is locked to gpt-5-mini in V3-01-09")
        if not self.openai_vision_credential_alias.startswith(
            ("secret://", "vault://", "external://")
        ):
            raise ValueError("OpenAI Vision credentials must be referenced by external alias")
        if self.openai_vision_image_detail not in {"low", "high", "auto"}:
            raise ValueError("OPENAI_VISION_IMAGE_DETAIL must be low, high or auto")
        if not 1 <= self.openai_vision_max_frames <= 32:
            raise ValueError("OPENAI_VISION_MAX_FRAMES must be between 1 and 32")
        if not 32 <= self.openai_vision_max_dimension_pixels <= 65_535:
            raise ValueError("OPENAI_VISION_MAX_DIMENSION_PIXELS is outside the supported range")
        if self.openai_vision_input_token_ceiling < 1:
            raise ValueError("OPENAI_VISION_INPUT_TOKEN_CEILING must be positive")
        if not 256 <= self.openai_vision_max_output_tokens <= 32768:
            raise ValueError("OPENAI_VISION_MAX_OUTPUT_TOKENS is outside the supported range")
        vision_cost_values = (
            self.openai_vision_estimated_cost_vnd,
            self.openai_vision_input_vnd_per_million_tokens,
            self.openai_vision_cached_input_vnd_per_million_tokens,
            self.openai_vision_output_vnd_per_million_tokens,
        )
        if any(value < 0 for value in vision_cost_values):
            raise ValueError("OpenAI Vision VND cost configuration cannot be negative")
        if (
            self.vision_provider == "openai" or self.transcription_provider == "openai"
        ) and self.openai_base_url.rstrip("/") != "https://api.openai.com":
            raise ValueError("OpenAI providers require the official HTTPS API origin")
        if (
            "fixture"
            in {self.stock_media_provider, self.image_generation_provider, self.video_generation_provider}
            and not self.media_fixture_enabled
        ):
            raise ValueError("fixture media providers require MEDIA_FIXTURE_ENABLED=true")
        if self.media_paid_execution_enabled and not self.media_external_execution_enabled:
            raise ValueError("paid media execution requires external media execution to be enabled")
        if self.comfyui_execution_enabled and not self.media_external_execution_enabled:
            raise ValueError("ComfyUI execution requires MEDIA_EXTERNAL_EXECUTION_ENABLED=true")
        if self.comfyui_execution_enabled and not self.comfyui_bridge_url.strip():
            raise ValueError("COMFYUI_BRIDGE_URL is required when ComfyUI execution is enabled")
        if (
            "comfyui" in {self.image_generation_provider, self.video_generation_provider}
            and not self.comfyui_execution_enabled
        ):
            raise ValueError("ComfyUI generation providers require COMFYUI_EXECUTION_ENABLED=true")
        if self.upload_default_part_size_bytes > self.upload_max_part_size_bytes:
            raise ValueError("default upload part size cannot exceed maximum part size")
        if self.upload_max_part_size_bytes > self.upload_max_size_bytes:
            raise ValueError("maximum upload part size cannot exceed maximum upload size")
        if self.upload_max_size_bytes > 2_147_483_647:
            raise ValueError("maximum upload size exceeds the current durable schema limit")
        if self.media_malware_scanner_mode not in {"disabled", "fixture", "clamd"}:
            raise ValueError("MEDIA_MALWARE_SCANNER_MODE must be disabled, fixture or clamd")
        if self.app_env.lower() == "production" and self.media_malware_scanner_mode == "fixture":
            raise ValueError("deterministic malware scanning is prohibited in production")
        if self.media_malware_scanner_mode == "clamd" and not self.media_malware_scanner_host.strip():
            raise ValueError("clamd mode requires MEDIA_MALWARE_SCANNER_HOST")
        if not 1 <= self.media_malware_scanner_port <= 65535:
            raise ValueError("MEDIA_MALWARE_SCANNER_PORT must be a valid TCP port")
        if not 1 <= self.media_malware_scan_timeout_seconds <= 300:
            raise ValueError("MEDIA_MALWARE_SCAN_TIMEOUT_SECONDS must be between 1 and 300")
        if not 1 <= self.media_quarantine_retention_days <= 365:
            raise ValueError("MEDIA_QUARANTINE_RETENTION_DAYS must be between 1 and 365")
        if self.object_storage_provider not in {"local", "s3"}:
            raise ValueError("OBJECT_STORAGE_PROVIDER must be local or s3")
        if self.object_storage_provider == "s3" and (
            not self.object_storage_access_key or not self.object_storage_secret_key
        ):
            raise ValueError("S3 object storage credentials must be configured outside source control")
        if self.app_env == "production" and self.object_storage_provider == "local":
            raise ValueError("production must use S3-compatible object storage")
        if self.audio_tts_provider not in {"espeak", "contract", "openai"}:
            raise ValueError("AUDIO_TTS_PROVIDER must be espeak, contract or openai")
        if self.audio_tts_provider == "openai" and not self.audio_external_execution_enabled:
            raise ValueError("OpenAI audio TTS requires the external audio execution owner gate")
        if self.audio_external_execution_enabled and self.audio_tts_provider != "openai":
            raise ValueError("external audio execution is only valid for the owner-gated OpenAI adapter")
        if self.audio_tts_rate < 80 or self.audio_tts_rate > 260:
            raise ValueError("AUDIO_TTS_RATE must be between 80 and 260")
        if self.provider_budget_currency != "VND":
            raise ValueError("PROVIDER_BUDGET_CURRENCY must be VND")
        if self.provider_per_operation_limit_vnd < 0 or self.provider_daily_limit_vnd < 0:
            raise ValueError("provider VND budget limits cannot be negative")
        if self.provider_daily_limit_vnd < self.provider_per_operation_limit_vnd:
            raise ValueError("provider daily VND limit cannot be lower than the per-operation limit")
        if (
            self.provider_per_operation_limit_vnd or self.provider_daily_limit_vnd
        ) and not self.provider_verified_gate_bundle_enabled:
            raise ValueError("provider budgets cannot be activated before the separate G-02 owner gate")
        if not 1 <= self.provider_retry_max_attempts <= 10:
            raise ValueError("PROVIDER_RETRY_MAX_ATTEMPTS must be between 1 and 10")
        ProviderTimeoutEnvelope(
            provider_http_timeout_seconds=self.provider_http_timeout_seconds,
            controller_hard_timeout_seconds=self.controller_hard_timeout_seconds,
        )
        if self.provider_retry_base_seconds < 0:
            raise ValueError("PROVIDER_RETRY_BASE_SECONDS cannot be negative")
        if self.provider_retry_max_seconds < self.provider_retry_base_seconds:
            raise ValueError("provider retry maximum cannot be lower than the base delay")
        if self.provider_retry_max_elapsed_seconds <= 0:
            raise ValueError("PROVIDER_RETRY_MAX_ELAPSED_SECONDS must be positive")
        if not 1 <= self.provider_poll_max_attempts <= 200:
            raise ValueError("PROVIDER_POLL_MAX_ATTEMPTS must be between 1 and 200")
        if self.provider_poll_interval_seconds < 0:
            raise ValueError("PROVIDER_POLL_INTERVAL_SECONDS cannot be negative")
        if not 1 <= self.provider_max_concurrent_calls <= 100:
            raise ValueError("PROVIDER_MAX_CONCURRENT_CALLS must be between 1 and 100")
        if not 1 <= self.provider_circuit_failure_threshold <= 20:
            raise ValueError("PROVIDER_CIRCUIT_FAILURE_THRESHOLD must be between 1 and 20")
        if not 1 <= self.provider_circuit_cooldown_seconds <= 86_400:
            raise ValueError("PROVIDER_CIRCUIT_COOLDOWN_SECONDS must be between 1 and 86400")
        minimum_lease = int(
            self.provider_retry_max_elapsed_seconds
            + self.controller_hard_timeout_seconds
            + 60
        )
        if not minimum_lease <= self.provider_operation_lease_seconds <= 86_400:
            raise ValueError(
                "PROVIDER_OPERATION_LEASE_SECONDS must cover retry/timeout bounds and be at most one day"
            )
        if not 30 <= self.provider_operation_retention_days <= 3650:
            raise ValueError("PROVIDER_OPERATION_RETENTION_DAYS must be between 30 and 3650")
        if self.provider_retention_cleanup_enabled:
            raise ValueError("provider ledger deletion is not activated in V3-01-03")
        if not 1 <= self.operations_queue_backlog_warning <= 1_000_000:
            raise ValueError("operations queue warning threshold must be positive and bounded")
        if not 1 <= self.operations_failed_jobs_warning <= 1_000_000:
            raise ValueError("operations failed-job threshold must be positive and bounded")
        if not 1 <= self.operations_disk_warning_percent < self.operations_disk_critical_percent <= 100:
            raise ValueError("operations disk thresholds must be ordered percentages")
        if not 30 <= self.operations_evidence_retention_days <= 3650:
            raise ValueError("operations evidence retention must be between 30 and 3650 days")
        if not 7 <= self.operations_log_retention_days <= 365:
            raise ValueError("operations log retention must be between 7 and 365 days")
        if self.operations_external_notifications_enabled:
            raise ValueError("external operations notifications are not activated in V3-01-07")
        if self.provider_paid_execution_enabled and not self.provider_external_execution_enabled:
            raise ValueError("paid provider execution requires external provider execution")
        provider_specific_external_gates = (
            self.media_external_execution_enabled,
            self.audio_external_execution_enabled,
            self.publish_external_execution_enabled,
            self.analytics_external_execution_enabled,
            self.agent_hub_webhook_external_delivery_enabled,
            self.comfyui_execution_enabled,
        )
        if any(provider_specific_external_gates) and not self.provider_external_execution_enabled:
            raise ValueError("provider-specific external execution requires the global provider safety gate")
        if self.provider_verified_gate_bundle_enabled:
            if not self.provider_verified_gate_bundle_sha256:
                raise ValueError("verified provider gate bundle SHA-256 is required")
            if not self.provider_gate_expected_rc_commit or not self.provider_gate_expected_rc_tag:
                raise ValueError("verified provider gates require an exact RC commit and tag")
            selected_capabilities = tuple(
                capability
                for capability, selected
                in (
                    ("vision", self.vision_provider == "openai"),
                    ("asr", self.transcription_provider == "openai"),
                )
                if selected
            )
            if len(selected_capabilities) != 1:
                raise ValueError(
                    "a verified provider gate must select exactly one OpenAI capability"
                )
            if selected_capabilities[0] == "vision":
                acceptance_limits = {
                    "model": self.openai_vision_model,
                    "credential_alias": self.openai_vision_credential_alias,
                    "detail": self.openai_vision_image_detail,
                    "max_frames": self.openai_vision_max_frames,
                    "max_dimension_pixels": self.openai_vision_max_dimension_pixels,
                    "input_token_ceiling": self.openai_vision_input_token_ceiling,
                    "max_output_tokens": self.openai_vision_max_output_tokens,
                    "estimated_cost_vnd": self.openai_vision_estimated_cost_vnd,
                    "input_vnd_per_million_tokens": (
                        self.openai_vision_input_vnd_per_million_tokens
                    ),
                    "cached_input_vnd_per_million_tokens": (
                        self.openai_vision_cached_input_vnd_per_million_tokens
                    ),
                    "output_vnd_per_million_tokens": (
                        self.openai_vision_output_vnd_per_million_tokens
                    ),
                    "per_operation_limit_vnd": self.provider_per_operation_limit_vnd,
                    "daily_limit_vnd": self.provider_daily_limit_vnd,
                    "retry_max_attempts": self.provider_retry_max_attempts,
                    "provider_http_timeout_seconds": self.provider_http_timeout_seconds,
                    "controller_hard_timeout_seconds": self.controller_hard_timeout_seconds,
                    "retry_max_elapsed_seconds": self.provider_retry_max_elapsed_seconds,
                    "max_concurrent_calls": self.provider_max_concurrent_calls,
                }
                expected_limits = {
                    "model": "gpt-5-mini",
                    "credential_alias": "secret://openai/codex-video",
                    "detail": "high",
                    "max_frames": 1,
                    "max_dimension_pixels": 2048,
                    "input_token_ceiling": 16_384,
                    "max_output_tokens": 4_096,
                    "estimated_cost_vnd": Decimal("500"),
                    "input_vnd_per_million_tokens": Decimal("6565"),
                    "cached_input_vnd_per_million_tokens": Decimal("656.5"),
                    "output_vnd_per_million_tokens": Decimal("52520"),
                    "per_operation_limit_vnd": Decimal("500"),
                    "daily_limit_vnd": Decimal("1250"),
                    "retry_max_attempts": 1,
                    "provider_http_timeout_seconds": 90.0,
                    "controller_hard_timeout_seconds": 120.0,
                    "retry_max_elapsed_seconds": 120.0,
                    "max_concurrent_calls": 1,
                }
                if acceptance_limits != expected_limits:
                    raise ValueError(
                        "provider settings do not match the approved G-02-A envelope"
                    )
            else:
                # ASR has no checked-in price/budget choice. A future G-02-ASR
                # bundle is hash-pinned first, then its exact values must match
                # the process settings before any adapter can be activated.
                from .provider_gate_loader import load_verified_provider_gate_bundle

                scope = load_verified_provider_gate_bundle(
                    self.provider_verified_gate_bundle_file,
                    expected_bundle_sha256=self.provider_verified_gate_bundle_sha256,
                    expected_rc_commit=self.provider_gate_expected_rc_commit,
                    expected_rc_tag=self.provider_gate_expected_rc_tag,
                )
                acceptance_limits = {
                    "provider_key": "openai-transcription",
                    "capability": "asr",
                    "model": self.openai_transcription_model,
                    "credential_alias": self.openai_transcription_credential_alias,
                    "language": self.openai_transcription_language,
                    "max_file_bytes": self.openai_transcription_max_file_bytes,
                    "max_duration_seconds": self.openai_transcription_max_duration_seconds,
                    "estimated_cost_vnd": self.openai_transcription_estimated_cost_vnd,
                    "vnd_per_minute": self.openai_transcription_vnd_per_minute,
                    "per_operation_limit_vnd": self.provider_per_operation_limit_vnd,
                    "acceptance_window_limit_vnd": self.provider_daily_limit_vnd,
                    "retry_max_attempts": self.provider_retry_max_attempts,
                    "provider_http_timeout_seconds": self.provider_http_timeout_seconds,
                    "controller_hard_timeout_seconds": self.controller_hard_timeout_seconds,
                    "retry_max_elapsed_seconds": self.provider_retry_max_elapsed_seconds,
                    "max_concurrent_calls": self.provider_max_concurrent_calls,
                }
                expected_limits = {
                    "provider_key": scope.provider_key,
                    "capability": scope.capability,
                    "model": scope.model,
                    "credential_alias": scope.credential_alias,
                    "language": scope.requested_language,
                    "max_file_bytes": scope.max_file_bytes,
                    "max_duration_seconds": scope.max_duration_seconds,
                    "estimated_cost_vnd": scope.per_operation_limit_vnd,
                    "vnd_per_minute": scope.vnd_per_minute,
                    "per_operation_limit_vnd": scope.per_operation_limit_vnd,
                    "acceptance_window_limit_vnd": scope.acceptance_window_limit_vnd,
                    "retry_max_attempts": scope.max_attempts,
                    "provider_http_timeout_seconds": scope.provider_http_timeout_seconds,
                    "controller_hard_timeout_seconds": scope.controller_hard_timeout_seconds,
                    "retry_max_elapsed_seconds": scope.controller_hard_timeout_seconds,
                    "max_concurrent_calls": scope.max_concurrent_calls,
                }
                if acceptance_limits != expected_limits:
                    raise ValueError(
                        "provider settings do not match the verified G-02-ASR envelope"
                    )
        elif self.provider_external_execution_enabled:
            raise ValueError("real provider execution requires a verified owner-gate bundle")
        if self.provider_external_execution_enabled:
            if not self.provider_verified_gate_bundle_enabled:
                raise ValueError("real provider execution requires a verified owner-gate bundle")
            selected_openai_adapters = sum(
                (
                    self.vision_provider == "openai",
                    self.transcription_provider == "openai",
                )
            )
            if selected_openai_adapters != 1 or not self.provider_paid_execution_enabled:
                raise ValueError(
                    "gated execution is limited to one paid OpenAI provider capability"
                )
        if not self.provider_global_kill_switch_engaged and not self.provider_external_execution_enabled:
            raise ValueError(
                "the global provider kill switch must remain engaged outside gated execution"
            )
        return self


settings = Settings()
