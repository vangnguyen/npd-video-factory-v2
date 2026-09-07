from __future__ import annotations

# Offline contract-only tests. No provider transport or credential resolver is
# instantiated. Any reservations below exist only in disposable test databases.

import hashlib
import json
import wave
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text

from app.config import Settings
from app.db import Base, create_engine, create_session_factory
from app.provider_gate_loader import (
    OpenAIAsrGateBundle,
    ProviderGateBundleError,
    ProviderApprovalRecord,
    canonical_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_safety import (
    ProviderCallContext,
    ProviderRightsEvidence,
    ProviderSafetyController,
    provider_safety_policy_from_settings,
)
from app.provider_safety_db import ProviderSafetyOperationORM
from app.provider_safety_durable import DurableProviderSafetyController
from app.provider_safety_repository import ProviderSafetyRepository
import app.provider_safety_db  # noqa: F401


REPO_ROOT = Path(__file__).resolve().parents[3]
ACCEPTANCE_ROOT = REPO_ROOT / "docs" / "acceptance" / "v3-01"
BUNDLE_PATH = ACCEPTANCE_ROOT / "V3-01-GATE-RC15-OPENAI-ASR-A.json"
EXPECTED_RC = "7d1290aacac61df98a51544731243e5e322a8644"
EXPECTED_BUNDLE_SHA = "d1075d9c22c9a6fb3f608ffcd5bf2de09d81895a2b17680fc981a3680249a966"
EXPECTED_SCOPE_SHA = "fee7086afeac45fa38c225365ceeae293f1a80aea1eba73bb261ce34aca350aa"
ACTIVE_AT = datetime(2026, 9, 8, 14, 30, tzinfo=timezone.utc)

ASSETS = (
    {
        "name": "g03-asr-vi-owned-01.wav",
        "sha256": "fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef",
        "bytes": 5_800_940,
        "duration": 120.852,
        "transcript": "g03-asr-vi-owned-01.txt",
        "transcript_sha256": "585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e",
        "rights": "V3-01-RIGHTS-ASR-001.json",
        "rights_sha256": "5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091",
    },
    {
        "name": "g03-asr-vi-owned-02.wav",
        "sha256": "dce36c5246c17e0385842006dcb0088a8c97a79d3009796815c2564c075cf20b",
        "bytes": 6_460_396,
        "duration": 134.59066666666666,
        "transcript": "g03-asr-vi-owned-02.txt",
        "transcript_sha256": "0bff8c2b403cee452fac00f71b84759988ea515027fda6bd49be76ae382c1fef",
        "rights": "V3-01-RIGHTS-ASR-002.json",
        "rights_sha256": "972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323",
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _active_policy():
    settings = Settings(
        _env_file=None,
        transcription_provider="openai",
        openai_transcription_model="whisper-1",
        openai_transcription_credential_alias="secret://openai/codex-video",
        openai_transcription_language="vi",
        openai_transcription_max_file_bytes=25_000_000,
        openai_transcription_max_duration_seconds=180,
        openai_transcription_estimated_cost_vnd=Decimal("500"),
        openai_transcription_vnd_per_minute=Decimal("162"),
        provider_verified_gate_bundle_enabled=True,
        provider_verified_gate_bundle_file=BUNDLE_PATH,
        provider_verified_gate_bundle_sha256=EXPECTED_BUNDLE_SHA,
        provider_gate_expected_rc_commit=EXPECTED_RC,
        provider_gate_expected_rc_tag="vf-v3-01-rc15",
        provider_external_execution_enabled=True,
        provider_paid_execution_enabled=True,
        provider_global_kill_switch_engaged=False,
        provider_per_operation_limit_vnd=Decimal("500"),
        provider_daily_limit_vnd=Decimal("1250"),
        provider_retry_max_attempts=1,
        provider_http_timeout_seconds=90,
        controller_hard_timeout_seconds=120,
        provider_retry_max_elapsed_seconds=120,
        provider_max_concurrent_calls=1,
    )
    return provider_safety_policy_from_settings(settings)


def _asr_context(slot: int, **updates: object) -> ProviderCallContext:
    scope = _active_policy().execution_gate
    assert scope is not None
    operation = scope.allowed_operations[slot - 1]
    asset = ASSETS[slot - 1]
    values: dict[str, object] = {
        "operation_key": operation.operation_key,
        "workspace_id": "wsp_rc15_asr_acceptance",
        "project_id": "prj_rc15_asr_acceptance",
        "provider_key": "openai-transcription",
        "model": "whisper-1",
        "capability": "asr",
        "operation": "flow_a_asr",
        "external_call": True,
        "paid": True,
        "estimated_cost_vnd": Decimal("500"),
        "credential_alias": "secret://openai/codex-video",
        "asset_id": operation.asset_id,
        "asset_hash": operation.asset_hash,
        "input_media_kind": "audio",
        "input_file_bytes": asset["bytes"],
        "input_duration_seconds": asset["duration"],
        "requested_language": "vi",
        "response_format": "verbose_json",
        "timestamp_granularities": ("segment", "word"),
        "rights_required": True,
        "rights": [],
    }
    values.update(updates)
    return ProviderCallContext.model_validate(values)


async def _durable_preflight(tmp_path: Path, context: ProviderCallContext, name: str):
    database = tmp_path / f"{name}.db"
    engine = create_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    repository = ProviderSafetyRepository(session_factory)
    await repository.ensure_state()
    controller = DurableProviderSafetyController(
        _active_policy(),
        repository=repository,
        clock=lambda: ACTIVE_AT,
        operation_lease_seconds=900,
        operation_retention_days=400,
    )
    decision = await controller.preflight(context)
    async with session_factory() as session:
        operation_count = int(
            await session.scalar(
                select(func.count()).select_from(ProviderSafetyOperationORM)
            )
            or 0
        )
    await engine.dispose()
    return decision, operation_count


def test_rc15_asr_bundle_loads_with_fresh_exact_bindings() -> None:
    assert _sha256(BUNDLE_PATH) == EXPECTED_BUNDLE_SHA
    scope = load_verified_provider_gate_bundle(
        BUNDLE_PATH,
        expected_bundle_sha256=EXPECTED_BUNDLE_SHA,
        expected_rc_commit=EXPECTED_RC,
        expected_rc_tag="vf-v3-01-rc15",
    )

    assert scope.execution_scope_sha256 == EXPECTED_SCOPE_SHA
    assert scope.provider_key == "openai-transcription"
    assert scope.model == "whisper-1"
    assert scope.credential_alias == "secret://openai/codex-video"
    assert scope.per_operation_limit_vnd == Decimal("500")
    assert scope.acceptance_window_limit_vnd == Decimal("1250")
    assert scope.provider_http_timeout_seconds == 90
    assert scope.controller_hard_timeout_seconds == 120
    assert [item.operation_key for item in scope.allowed_operations] == [
        "v3-01-rc15-openai-transcription-asr-call-01",
        "v3-01-rc15-openai-transcription-asr-call-02",
    ]
    assert all(
        "rc14" not in item.operation_key
        and "rc13" not in item.operation_key
        and "rc12" not in item.operation_key
        for item in scope.allowed_operations
    )


def test_rc15_asr_bundle_embeds_exact_rebind_records() -> None:
    payload = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    bundle = OpenAIAsrGateBundle.model_validate(payload)

    for key, filename in (
        ("credential_approval", "V3-01-APP-061.json"),
        ("budget_approval", "V3-01-APP-062.json"),
        ("rights_approval", "V3-01-APP-063.json"),
    ):
        external = ProviderApprovalRecord.model_validate(
            json.loads(
                (ACCEPTANCE_ROOT / "approvals" / filename).read_text(encoding="utf-8")
            )
        )
        embedded = getattr(bundle, key)
        assert embedded.record == external
        assert embedded.record_sha256 == canonical_sha256(external)

    for index, asset in enumerate(ASSETS):
        external = ProviderRightsEvidence.model_validate(
            json.loads(
                (ACCEPTANCE_ROOT / "rights" / str(asset["rights"])).read_text(
                    encoding="utf-8"
                )
            )
        )
        assert bundle.rights_records[index].record == external
        assert bundle.rights_records[index].record_sha256 == asset["rights_sha256"]


def test_rc15_rebind_preserves_exact_assets_transcripts_and_rights() -> None:
    manifest_path = ACCEPTANCE_ROOT / "assets" / "V3-01-RC11-ASR-ASSET-MANIFEST.json"
    assert _sha256(manifest_path) == (
        "0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0"
    )
    modeled_total = Decimal("0")
    for asset in ASSETS:
        wav_path = ACCEPTANCE_ROOT / "assets" / str(asset["name"])
        transcript_path = ACCEPTANCE_ROOT / "transcripts" / str(asset["transcript"])
        rights_path = ACCEPTANCE_ROOT / "rights" / str(asset["rights"])
        assert _sha256(wav_path) == asset["sha256"]
        assert wav_path.stat().st_size == asset["bytes"]
        assert _sha256(transcript_path) == asset["transcript_sha256"]
        rights = ProviderRightsEvidence.model_validate(
            json.loads(rights_path.read_text(encoding="utf-8"))
        )
        assert canonical_sha256(rights) == asset["rights_sha256"]
        with wave.open(str(wav_path), "rb") as recording:
            duration = recording.getnframes() / recording.getframerate()
            assert recording.getnchannels() == 1
            assert recording.getframerate() == 24_000
        assert duration == pytest.approx(asset["duration"], abs=0.000001)
        assert 90 <= duration <= 180
        modeled_cost = Decimal(str(duration)) * Decimal("162") / Decimal("60")
        assert modeled_cost < Decimal("500")
        modeled_total += modeled_cost
    assert modeled_total < Decimal("1250")


def test_rc15_rebind_keeps_checked_in_runtime_fail_closed() -> None:
    settings = Settings(_env_file=None)
    assert settings.transcription_provider == "fixture"
    assert settings.openai_transcription_model == ""
    assert settings.provider_verified_gate_bundle_enabled is False
    assert settings.provider_external_execution_enabled is False
    assert settings.provider_paid_execution_enabled is False
    assert settings.provider_global_kill_switch_engaged is True
    assert settings.provider_per_operation_limit_vnd == Decimal("0")
    assert settings.provider_daily_limit_vnd == Decimal("0")


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", [1, 2])
async def test_rc15_durable_and_non_durable_select_same_exact_rights(
    tmp_path: Path, slot: int
) -> None:
    context = _asr_context(slot)
    memory = await ProviderSafetyController(
        _active_policy(), clock=lambda: ACTIVE_AT
    ).preflight(context)
    durable, operation_count = await _durable_preflight(
        tmp_path, context, f"rc15-slot-{slot}"
    )

    assert durable.code == memory.code == "PROVIDER_CALL_RESERVED"
    assert durable.rights == memory.rights
    assert durable.rights.checked_records == 1
    assert operation_count == 1


@pytest.mark.asyncio
async def test_rc15_wrong_asset_fails_before_durable_operation_row(tmp_path: Path) -> None:
    context = _asr_context(
        1,
        asset_id="asset-not-approved",
        asset_hash="f" * 64,
    )
    durable, operation_count = await _durable_preflight(
        tmp_path, context, "rc15-wrong-asset"
    )

    assert durable.allowed is False
    assert durable.code == "RIGHTS_ASSET_BINDING_MISMATCH"
    assert operation_count == 0

def test_rc15_proposed_scope_does_not_grant_operation_authority() -> None:
    bundle = OpenAIAsrGateBundle.model_validate_json(BUNDLE_PATH.read_text(encoding="utf-8"))
    assert bundle.valid_from_utc == datetime(2026, 9, 8, 14, tzinfo=timezone.utc)
    assert bundle.expires_at_utc == datetime(2026, 9, 8, 18, tzinfo=timezone.utc)
    assert bundle.budget.max_attempts == 1
    assert bundle.budget.max_concurrent_calls == 1
    assert bundle.budget.automatic_retry is False
    assert bundle.budget.model_fallback is False
    assert bundle.budget.currency == "VND"
    for approval in (
        bundle.credential_approval,
        bundle.budget_approval,
        bundle.rights_approval,
    ):
        assert "not execution authority" in approval.record.notes
        assert "RC-14 authority and both RC-14 operation IDs are retired" in approval.record.notes
    # The allowlist defines permitted identities, not a signed runtime decision.
    assert "operation_authority" not in bundle.model_dump()
    assert "runtime_authority" not in bundle.model_dump()
    assert Settings(_env_file=None).provider_verified_gate_bundle_enabled is False


def test_rc14_bundle_cannot_load_as_rc15() -> None:
    stale_path = ACCEPTANCE_ROOT / "V3-01-GATE-RC14-OPENAI-ASR-A.json"
    with pytest.raises(ProviderGateBundleError, match="does not match the exact RC"):
        load_verified_provider_gate_bundle(
            stale_path,
            expected_bundle_sha256=_sha256(stale_path),
            expected_rc_commit=EXPECTED_RC,
            expected_rc_tag="vf-v3-01-rc15",
        )


@pytest.mark.parametrize("slot", [1, 2])
def test_rc15_bundle_rejects_rc14_operation_identity(tmp_path: Path, slot: int) -> None:
    payload = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    payload["allowed_operations"][slot - 1]["operation_key"] = (
        f"v3-01-rc14-openai-transcription-asr-call-{slot:02d}"
    )
    tampered_path = tmp_path / "rc15-stale-operation.json"
    tampered_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProviderGateBundleError, match="bundle is invalid"):
        load_verified_provider_gate_bundle(
            tampered_path,
            expected_bundle_sha256=_sha256(tampered_path),
            expected_rc_commit=EXPECTED_RC,
            expected_rc_tag="vf-v3-01-rc15",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", [1, 2])
async def test_rc14_identity_denied_before_durable_row(tmp_path: Path, slot: int) -> None:
    context = _asr_context(
        slot, operation_key=f"v3-01-rc14-openai-transcription-asr-call-{slot:02d}"
    )
    memory = await ProviderSafetyController(
        _active_policy(), clock=lambda: ACTIVE_AT
    ).preflight(context)
    durable, operation_count = await _durable_preflight(
        tmp_path, context, f"rc15-stale-identity-{slot}"
    )
    assert durable.allowed is memory.allowed is False
    assert durable.code == memory.code == "OPERATION_NOT_ALLOWLISTED"
    assert operation_count == 0


@pytest.mark.asyncio
async def test_rc15_checked_in_defaults_cannot_activate_allowlist() -> None:
    controller = ProviderSafetyController(
        provider_safety_policy_from_settings(Settings(_env_file=None)),
        clock=lambda: ACTIVE_AT,
    )
    decision = await controller.preflight(_asr_context(2))
    assert decision.allowed is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("updates", "expected_code"),
    [
        ({"estimated_cost_vnd": Decimal("500.01")}, "COST_RESERVATION_MISMATCH"),
        ({"input_duration_seconds": 180.001}, "INPUT_DURATION_LIMIT_EXCEEDED"),
        (
            {"operation_key": "v3-01-rc15-openai-transcription-asr-call-03"},
            "OPERATION_NOT_ALLOWLISTED",
        ),
    ],
)
async def test_rc15_scope_ceiling_denied_without_durable_row(
    tmp_path: Path, updates: dict[str, object], expected_code: str
) -> None:
    context = _asr_context(1, **updates)
    memory = await ProviderSafetyController(
        _active_policy(), clock=lambda: ACTIVE_AT
    ).preflight(context)
    durable, operation_count = await _durable_preflight(tmp_path, context, "rc15-denied")
    assert durable.allowed is memory.allowed is False
    assert durable.code == memory.code == expected_code
    assert operation_count == 0


def test_rc15_file_cap_fails_during_context_validation() -> None:
    with pytest.raises(ValidationError, match="input_file_bytes"):
        _asr_context(1, input_file_bytes=25_000_001)
