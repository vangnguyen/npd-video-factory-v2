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


def test_v2_03_allows_fixture_provider_to_be_disabled_in_production() -> None:
    production = Settings(
        _env_file=None,
        app_env="production",
        trend_fixture_enabled=False,
        object_storage_provider="s3",
        object_storage_access_key="test-access-key",
        object_storage_secret_key="test-secret-key",
    )

    assert production.trend_fixture_enabled is False


@pytest.mark.asyncio
async def test_capabilities_report_no_agent_hub_or_publishing_runtime() -> None:
    result = await capabilities()
    assert result["agent_hub_runtime_dependency"] is False
    assert result["publishing_implemented"] is False
    assert result["publish_enabled"] is False
    assert result["human_approval_required"] is True
