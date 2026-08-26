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


@pytest.mark.asyncio
async def test_capabilities_report_no_agent_hub_or_publishing_runtime() -> None:
    result = await capabilities()
    assert result["agent_hub_runtime_dependency"] is False
    assert result["publishing_implemented"] is False
    assert result["publish_enabled"] is False
    assert result["human_approval_required"] is True
