from __future__ import annotations

import hashlib
import json
import wave
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text

from app.config import Settings
from app.db import Base, create_engine, create_session_factory
from app.provider_gate_loader import (
    OpenAIAsrGateBundle,
    ProviderApprovalRecord,
    canonical_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_safety import (
    ProviderCallContext,
    ProviderRightsEvidence,
    ProviderSafetyController,
    ProviderSafetyPolicy,
    provider_safety_policy_from_settings,
)
from app.provider_safety_db import ProviderSafetyOperationORM
from app.provider_safety_durable import DurableProviderSafetyController
from app.provider_safety_repository import ProviderSafetyRepository
import app.provider_safety_db  # noqa: F401


REPO_ROOT = Path(__file__).resolve().parents[3]
ACCEPTANCE_ROOT = REPO_ROOT / "docs" / "acceptance" / "v3-01"
BUNDLE_PATH = ACCEPTANCE_ROOT / "V3-01-GATE-RC11-OPENAI-ASR-A.json"
EXPECTED_RC = "207ff9fee5557eb0976f575c9263b61d995b20a0"
EXPECTED_BUNDLE_SHA = "4f8edd02ec62182404976de16e8d75b39ddbbbbe96c0d78efd46e3a97d6ace46"
EXPECTED_SCOPE_SHA = "7368b506b8971b190a1828ecab588dfe6b46a7e354d00c4d7cf2f35c1cc2c39a"
ACTIVE_AT = datetime(2026, 9, 4, 14, 30, tzinfo=timezone.utc)

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


def _active_policy() -> ProviderSafetyPolicy:
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
        provider_gate_expected_rc_tag="vf-v3-01-rc11",
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
        "workspace_id": "wsp_rc11_asr_acceptance",
        "project_id": "prj_rc11_asr_acceptance",
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


async def _durable_controller(tmp_path: Path, policy: ProviderSafetyPolicy, name: str):
    database = tmp_path / f"{name}.db"
    engine = create_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    repository = ProviderSafetyRepository(session_factory)
    await repository.ensure_state()
    controller = DurableProviderSafetyController(
        policy,
        repository=repository,
        clock=lambda: ACTIVE_AT,
        operation_lease_seconds=900,
        operation_retention_days=400,
    )
    return engine, session_factory, controller


async def _durable_preflight(
    tmp_path: Path,
    policy: ProviderSafetyPolicy,
    context: ProviderCallContext,
    name: str,
):
    engine, session_factory, controller = await _durable_controller(
        tmp_path, policy, name
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


def test_rc11_asr_bundle_loads_with_exact_hash_pins() -> None:
    assert _sha256(BUNDLE_PATH) == EXPECTED_BUNDLE_SHA
    scope = load_verified_provider_gate_bundle(
        BUNDLE_PATH,
        expected_bundle_sha256=EXPECTED_BUNDLE_SHA,
        expected_rc_commit=EXPECTED_RC,
        expected_rc_tag="vf-v3-01-rc11",
    )

    assert scope.execution_scope_sha256 == EXPECTED_SCOPE_SHA
    assert scope.provider_key == "openai-transcription"
    assert scope.model == "whisper-1"
    assert scope.capability == "asr"
    assert scope.credential_alias == "secret://openai/codex-video"
    assert scope.per_operation_limit_vnd == Decimal("500")
    assert scope.acceptance_window_limit_vnd == Decimal("1250")
    assert scope.vnd_per_minute == Decimal("162")
    assert scope.provider_http_timeout_seconds == 90
    assert scope.controller_hard_timeout_seconds == 120
    assert scope.allowed_operations[0].operation_key == (
        "v3-01-rc11-openai-transcription-asr-call-01"
    )
    assert scope.allowed_operations[1].operation_key == (
        "v3-01-rc11-openai-transcription-asr-call-02"
    )


def test_rc11_asr_bundle_embeds_exact_external_records() -> None:
    payload = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    bundle = OpenAIAsrGateBundle.model_validate(payload)

    for key, filename in (
        ("credential_approval", "V3-01-APP-044.json"),
        ("budget_approval", "V3-01-APP-045.json"),
        ("rights_approval", "V3-01-APP-046.json"),
    ):
        external = ProviderApprovalRecord.model_validate(
            json.loads((ACCEPTANCE_ROOT / "approvals" / filename).read_text(encoding="utf-8"))
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
        embedded = bundle.rights_records[index]
        assert embedded.record == external
        assert embedded.record_sha256 == asset["rights_sha256"]
        assert embedded.record_sha256 == canonical_sha256(external)


def test_rc11_asr_assets_transcripts_and_owner_manifest_are_exact() -> None:
    manifest_path = ACCEPTANCE_ROOT / "assets" / "V3-01-RC11-ASR-ASSET-MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert _sha256(manifest_path) == (
        "0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0"
    )
    assert manifest["owner_confirmation"] == {
        "decision": "APPROVED",
        "recorded_at_utc": "2026-09-03T07:05:17Z",
        "content_matches_reference_transcript": True,
        "voice_processing_consent": True,
        "publishing_allowed": False,
        "training_allowed": False,
        "resale_allowed": False,
    }

    modeled_total = Decimal("0")
    for index, asset in enumerate(ASSETS):
        wav_path = ACCEPTANCE_ROOT / "assets" / str(asset["name"])
        transcript_path = ACCEPTANCE_ROOT / "transcripts" / str(asset["transcript"])
        assert _sha256(wav_path) == asset["sha256"]
        assert wav_path.stat().st_size == asset["bytes"]
        assert _sha256(transcript_path) == asset["transcript_sha256"]

        with wave.open(str(wav_path), "rb") as recording:
            assert recording.getnchannels() == 1
            assert recording.getframerate() == 24_000
            assert recording.getsampwidth() == 2
            duration = recording.getnframes() / recording.getframerate()
        assert duration == pytest.approx(asset["duration"], abs=0.000001)
        assert 90 <= duration <= 180
        assert manifest["assets"][index]["sha256"] == asset["sha256"]
        assert manifest["assets"][index]["reference_transcript_sha256"] == (
            asset["transcript_sha256"]
        )
        assert manifest["assets"][index]["critical_terms"]
        modeled_total += Decimal(str(duration)) * Decimal("162") / Decimal("60")

    assert modeled_total < Decimal("1250")
    assert all(
        Decimal(str(asset["duration"])) * Decimal("162") / Decimal("60")
        < Decimal("500")
        for asset in ASSETS
    )


def test_rc11_asr_checked_in_defaults_remain_fail_closed() -> None:
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
async def test_durable_rc11_selects_exact_rights_record_with_controller_parity(
    tmp_path: Path,
    slot: int,
) -> None:
    policy = _active_policy()
    context = _asr_context(slot)
    memory = await ProviderSafetyController(
        policy, clock=lambda: ACTIVE_AT
    ).preflight(context)
    durable, operation_count = await _durable_preflight(
        tmp_path, policy, context, f"slot-{slot}"
    )

    assert durable.code == memory.code == "PROVIDER_CALL_RESERVED"
    assert durable.rights == memory.rights
    assert durable.rights.checked_records == 1
    assert durable.rights.blocked_record_ids == []
    assert operation_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("slot", [1, 2])
async def test_durable_rights_selection_is_independent_of_record_order(
    tmp_path: Path,
    slot: int,
) -> None:
    policy = _active_policy()
    scope = policy.execution_gate
    assert scope is not None
    reordered = scope.model_copy(
        update={"rights_records": tuple(reversed(scope.rights_records))}
    )
    reordered_policy = policy.model_copy(update={"execution_gate": reordered})
    context = _asr_context(slot)

    durable, operation_count = await _durable_preflight(
        tmp_path, reordered_policy, context, f"reordered-{slot}"
    )

    assert durable.code == "PROVIDER_CALL_RESERVED"
    assert durable.rights.checked_records == 1
    assert operation_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("wrong_asset", "RIGHTS_ASSET_BINDING_MISMATCH"),
        ("missing_record", "RIGHTS_EVIDENCE_REQUIRED"),
        ("tampered_record", "RIGHTS_EVIDENCE_REQUIRED"),
        ("expired_record", "RIGHTS_BLOCKED"),
        ("unauthorized_rights", "RIGHTS_BLOCKED"),
        ("unauthorized_operation", "OPERATION_SCOPE_MISMATCH"),
    ],
)
async def test_durable_multi_asset_rights_fail_closed_with_controller_parity(
    tmp_path: Path,
    case: str,
    expected_code: str,
) -> None:
    policy = _active_policy()
    scope = policy.execution_gate
    assert scope is not None
    context = _asr_context(1)

    if case == "wrong_asset":
        context = context.model_copy(
            update={"asset_id": "asset-not-approved", "asset_hash": "f" * 64}
        )
    elif case == "missing_record":
        scope = scope.model_copy(
            update={"rights_record": None, "rights_records": ()}
        )
        policy = policy.model_copy(update={"execution_gate": scope})
    elif case == "tampered_record":
        tampered = scope.rights_records[0].model_copy(
            update={"asset_hash": "f" * 64}
        )
        scope = scope.model_copy(
            update={"rights_records": (tampered, scope.rights_records[1])}
        )
        policy = policy.model_copy(update={"execution_gate": scope})
    elif case == "expired_record":
        expired = scope.rights_records[0].model_copy(
            update={"expiry": ACTIVE_AT - timedelta(seconds=1)}
        )
        scope = scope.model_copy(
            update={"rights_records": (expired, scope.rights_records[1])}
        )
        policy = policy.model_copy(update={"execution_gate": scope})
    elif case == "unauthorized_rights":
        unauthorized = scope.rights_records[0].model_copy(
            update={"commercial_use": False}
        )
        scope = scope.model_copy(
            update={"rights_records": (unauthorized, scope.rights_records[1])}
        )
        policy = policy.model_copy(update={"execution_gate": scope})
    elif case == "unauthorized_operation":
        context = context.model_copy(update={"operation": "publish"})

    memory = await ProviderSafetyController(
        policy, clock=lambda: ACTIVE_AT
    ).preflight(context)
    durable, operation_count = await _durable_preflight(
        tmp_path, policy, context, case
    )

    assert durable.code == memory.code == expected_code
    assert durable.allowed is memory.allowed is False
    assert durable.rights == memory.rights
    assert operation_count == 0


@pytest.mark.asyncio
async def test_durable_verified_rights_keeps_legacy_single_record_compatibility(
    tmp_path: Path,
) -> None:
    policy = _active_policy()
    scope = policy.execution_gate
    assert scope is not None
    legacy_record = scope.rights_records[0]
    legacy_scope = scope.model_copy(
        update={
            "rights_record": legacy_record,
            "rights_records": (),
            "rights_record_sha256": scope.rights_record_sha256s[0],
            "rights_record_sha256s": (),
        }
    )
    legacy_policy = policy.model_copy(update={"execution_gate": legacy_scope})

    durable, operation_count = await _durable_preflight(
        tmp_path, legacy_policy, _asr_context(1), "legacy-single-record"
    )

    assert durable.code == "PROVIDER_CALL_RESERVED"
    assert durable.rights.checked_records == 1
    assert operation_count == 1


def test_rc11_bundle_rejects_duplicate_rights_sha_and_record_tampering() -> None:
    payload = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    payload["rights_records"][1] = json.loads(
        json.dumps(payload["rights_records"][0])
    )
    with pytest.raises(
        ValidationError, match="both distinct RightsRecord hashes"
    ):
        OpenAIAsrGateBundle.model_validate(payload)

    payload = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    payload["rights_records"][0]["record"]["reviewer"] = "tampered reviewer"
    with pytest.raises(ValidationError, match="RightsRecord SHA-256 mismatch"):
        OpenAIAsrGateBundle.model_validate(payload)
