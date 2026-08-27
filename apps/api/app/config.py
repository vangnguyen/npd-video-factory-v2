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
    upload_default_part_size_bytes: int = 8 * 1024 * 1024
    upload_max_part_size_bytes: int = 32 * 1024 * 1024
    # Asset and upload byte counts use PostgreSQL INTEGER in the current
    # durable schema, so the configurable ceiling must stay within int32.
    upload_max_size_bytes: int = 2_000_000_000
    tts_provider: str = "espeak"
    openai_api_key: str = ""
    public_base_url: str = "http://localhost:8000"
    video_factory_brand_name: str = "NPD Video Factory"
    video_factory_logo_path: Path = Path("/workspace/storage/assets/brand/default-logo.png")
    publish_enabled: bool = False
    human_approval_required: bool = True

    @model_validator(mode="after")
    def enforce_v2_safety_boundary(self) -> "Settings":
        if self.publish_enabled:
            raise ValueError("publishing is not implemented in V2-04 and must remain disabled")
        if not self.human_approval_required:
            raise ValueError("human approval must remain required in V2-04")
        if self.app_env == "production" and self.trend_fixture_enabled:
            raise ValueError("deterministic trend fixtures must be disabled in production")
        if self.app_env == "production" and self.auto_edit_fixture_enabled:
            raise ValueError("deterministic auto-edit fixtures must be disabled in production")
        if self.transcription_provider not in {"fixture", "contract"}:
            raise ValueError("TRANSCRIPTION_PROVIDER must be fixture or contract")
        if self.auto_edit_signal_provider not in {"fixture", "ffmpeg"}:
            raise ValueError("AUTO_EDIT_SIGNAL_PROVIDER must be fixture or ffmpeg")
        if self.transcription_provider == "fixture" and not self.auto_edit_fixture_enabled:
            raise ValueError("fixture transcription requires AUTO_EDIT_FIXTURE_ENABLED=true")
        if self.auto_edit_signal_provider == "fixture" and not self.auto_edit_fixture_enabled:
            raise ValueError("fixture media signals require AUTO_EDIT_FIXTURE_ENABLED=true")
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
        return self


settings = Settings()
