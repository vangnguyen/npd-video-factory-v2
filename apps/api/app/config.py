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
            raise ValueError("publishing is not implemented in V2-02 and must remain disabled")
        if not self.human_approval_required:
            raise ValueError("human approval must remain required in V2-02")
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
