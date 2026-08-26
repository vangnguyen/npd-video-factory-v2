from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    redis_url: str = "redis://redis:6379/0"
    job_storage_root: Path = Path("/workspace/storage/jobs")
    asset_storage_root: Path = Path("/workspace/storage/assets")
    contracts_root: Path = Path("/workspace/packages/contracts")
    renderer_url: str = "http://renderer:3001"
    public_base_url: str = "http://localhost:8000"
    video_factory_brand_name: str = "NPD Video Factory"
    video_factory_logo_path: Path = Path("/workspace/storage/assets/brand/default-logo.png")
    publish_enabled: bool = False
    human_approval_required: bool = True

    @model_validator(mode="after")
    def enforce_v2_01_safety_boundary(self) -> "Settings":
        if self.publish_enabled:
            raise ValueError("publishing is not implemented in V2-01 and must remain disabled")
        if not self.human_approval_required:
            raise ValueError("human approval must remain required in V2-01")
        return self


settings = Settings()
