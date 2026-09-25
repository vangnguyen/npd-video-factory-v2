"""VF-EXECUTOR-02 probes remain offline tests, not live-host attestation."""
from dataclasses import replace
import json
from pathlib import Path

import pytest
from app import executor_qualification as q
from test_executor_plane import host, mock_probes  # shared synthetic dependencies only


def test_positive_fixture_is_inactive_and_cannot_be_owner_authority(tmp_path):
    from app.provider_gate_loader import load_verified_provider_gate_bundle
    from app.provider_safety import ProviderSafetyPolicy
    fixture = Path(q.__file__).parent / "data/executor/expired-loader-fixture.json"
    payload = json.loads(fixture.read_bytes())
    assert all(payload[name]["record"]["approved_by"] == "SYNTHETIC_FIXTURE_GENERATOR_NOT_OWNER"
               for name in ("credential_approval", "budget_approval", "rights_approval"))
    scope = load_verified_provider_gate_bundle(fixture, expected_bundle_sha256=q.sha(fixture.read_bytes()),
        expected_rc_tag="vf-v3-01-rc999999", expected_rc_commit="f" * 40)
    assert scope.rc_tag != "vf-v3-01-rc22"
    assert not ProviderSafetyPolicy().external_execution_enabled
    result = q.fixture_mount(tmp_path)
    assert result["cleanup"] == "VERIFIED" and result["active_bundle_mounted"] is False
    assert not list(tmp_path.iterdir())


def test_fixture_tampering_cleans_staging(tmp_path, monkeypatch):
    original = Path.read_bytes
    def tampered(path):
        return b"{}" if path.name == "expired-loader-fixture.json" else original(path)
    monkeypatch.setattr(Path, "read_bytes", tampered)
    with pytest.raises(q.Blocked, match="FIXTURE_HASH_MISMATCH"):
        q.fixture_mount(tmp_path)
    assert not list(tmp_path.iterdir())


async def test_ledger_change_during_qualification_blocks(host, tmp_path, mock_probes, monkeypatch):
    calls = []
    async def changing_custody(host):
        calls.append(1)
        return {"identity": {}, "migration_head": "0015", "operation_state": "VIRGIN",
                "reserved_vnd": "0", "reservation_privileges": True, "control_revision": len(calls)}
    monkeypatch.setattr(q, "custody", changing_custody)
    result = await q.qualify(host, tmp_path)
    assert len(calls) == 2
    assert result["gates"]["E10"]["code"] == "LEDGER_RECHECK_FAILED"
    assert result["execution_plane_qualified"] is False


async def test_mock_probe_success_is_never_plane_qualification(host, tmp_path, mock_probes):
    result = await q.qualify(host, tmp_path)
    assert result["verdict"] == "CAPABILITY_PROBES_PASS"
    assert result["execution_plane_qualified"] is False
    assert result["gates"]["E10"]["ledger_unchanged"] is True
    assert all(result[key] == value for key, value in q.ZERO.items())
    assert result["source_commit"] == host.source_commit
