from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    auto_edit_signal_provider: str = "fixture"
    ffprobe_path: str = "ffprobe"
    ffmpeg_path: str = "ffmpeg"
    upload_staging_root: Path = Path("/workspace/storage/uploads")
    analysis_staging_root: Path = Path("/workspace/storage/analysis")
    vision_fixture_enabled: bool = True
    vision_provider: str = "fixture"
    vision_staging_root: Path = Path("/workspace/storage/vision")
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
    human_approval_required: bool = True

    @model_validator(mode="after")
    def enforce_v2_safety_boundary(self) -> "Settings":
        if self.publish_enabled:
            raise ValueError("publishing is not implemented in V2-08 and must remain disabled")
        if not self.human_approval_required:
            raise ValueError("human approval must remain required in V2-08")
        if self.app_env == "production" and self.trend_fixture_enabled:
            raise ValueError("deterministic trend fixtures must be disabled in production")
        if self.app_env == "production" and self.auto_edit_fixture_enabled:
            raise ValueError("deterministic auto-edit fixtures must be disabled in production")
        if self.app_env == "production" and self.vision_fixture_enabled:
            raise ValueError("deterministic Vision fixtures must be disabled in production")
        if self.app_env == "production" and self.media_fixture_enabled:
            raise ValueError("deterministic media fixtures must be disabled in production")
        if self.transcription_provider not in {"fixture", "contract"}:
            raise ValueError("TRANSCRIPTION_PROVIDER must be fixture or contract")
        if self.auto_edit_signal_provider not in {"fixture", "ffmpeg"}:
            raise ValueError("AUTO_EDIT_SIGNAL_PROVIDER must be fixture or ffmpeg")
        if self.vision_provider not in {"fixture", "contract"}:
            raise ValueError("VISION_PROVIDER must be fixture or contract")
        if self.stock_media_provider not in {"fixture", "contract"}:
            raise ValueError("STOCK_MEDIA_PROVIDER must be fixture or contract")
        if self.image_generation_provider not in {"fixture", "contract", "comfyui"}:
            raise ValueError("IMAGE_GENERATION_PROVIDER must be fixture, contract or comfyui")
        if self.video_generation_provider not in {"fixture", "contract", "comfyui"}:
            raise ValueError("VIDEO_GENERATION_PROVIDER must be fixture, contract or comfyui")
        if self.transcription_provider == "fixture" and not self.auto_edit_fixture_enabled:
            raise ValueError("fixture transcription requires AUTO_EDIT_FIXTURE_ENABLED=true")
        if self.auto_edit_signal_provider == "fixture" and not self.auto_edit_fixture_enabled:
            raise ValueError("fixture media signals require AUTO_EDIT_FIXTURE_ENABLED=true")
        if self.vision_provider == "fixture" and not self.vision_fixture_enabled:
            raise ValueError("fixture Vision provider requires VISION_FIXTURE_ENABLED=true")
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
            raise ValueError("OpenAI audio TTS requires AUDIO_EXTERNAL_EXECUTION_ENABLED=true")
        if self.audio_external_execution_enabled and self.audio_tts_provider != "openai":
            raise ValueError("external audio execution is only valid for the owner-gated OpenAI adapter")
        if self.audio_tts_rate < 80 or self.audio_tts_rate > 260:
            raise ValueError("AUDIO_TTS_RATE must be between 80 and 260")
        return self


settings = Settings()
