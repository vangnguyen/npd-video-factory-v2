"""Synthetic/offline W1 gate checks; no credentials, transport or live ledger."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.asr_prompt_profile import W1_PROFILE_ID, prompt_profile_sha256, w1_prompt_profile
from app.config import Settings
from app.db import Base, create_engine, create_session_factory
from app.provider_gate_loader import (
    OpenAIAsrGateBundle,
    asr_execution_scope_sha256,
    canonical_sha256,
    execution_scope_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_safety import ProviderSafetyBlocked, ProviderSafetyController, provider_safety_policy_from_settings
from app.provider_safety_db import (
    ProviderSafetyAttemptORM,
    ProviderSafetyBudgetDayORM,
    ProviderSafetyCircuitORM,
    ProviderSafetyOperationORM,
)
from app.provider_safety_durable import DurableProviderSafetyController
from app.provider_safety_repository import ProviderSafetyRepository
from test_openai_asr_gate_loader import (
    ACTIVATES_AT, RC_COMMIT, RC_TAG, _bundle, _context, _settings, _write_bundle,
)


def _scope_hash(bundle, profile=None, **changes):
    fields = dict(
        rc_tag=bundle.rc_tag, rc_commit=bundle.rc_commit,
        provider_key=bundle.provider_key, model=bundle.model, capability=bundle.capability,
        credential_alias=bundle.credential_alias, valid_from_utc=bundle.valid_from_utc,
        expires_at_utc=bundle.expires_at_utc, budget=bundle.budget,
        allowed_operations=bundle.allowed_operations,
        rights_record_sha256s=tuple(item.record_sha256 for item in bundle.rights_records),
        asr_prompt_profile=profile,
    )
    fields.update(changes)
    return execution_scope_sha256(**fields)


def _w1_bundle_payload():
    original = _bundle()
    old_scope = _scope_hash(original)
    new_scope = _scope_hash(original, w1_prompt_profile())
    payload = original.model_dump(mode="json")
    payload["asr_prompt_profile"] = w1_prompt_profile().model_dump(mode="json")
    for key in ("credential_approval", "budget_approval", "rights_approval"):
        record = payload[key]["record"]
        record["artifact_or_commit_hashes"] = [
            new_scope if value == old_scope else value
            for value in record["artifact_or_commit_hashes"]
        ]
        payload[key]["record_sha256"] = canonical_sha256(record)
    return payload


def _policy(tmp_path, *, prompted=True):
    payload = _w1_bundle_payload() if prompted else _bundle().model_dump(mode="json")
    path, digest = _write_bundle(tmp_path, payload)
    settings = _settings(
        path, digest,
        openai_transcription_prompt_profile_id=W1_PROFILE_ID if prompted else "",
        provider_external_execution_enabled=True,
        provider_paid_execution_enabled=True,
        provider_global_kill_switch_engaged=False,
    )
    return provider_safety_policy_from_settings(settings)


def test_w1_changes_scope_not_budget_and_requires_all_three_approval_rebinds():
    original = _bundle()
    payload = _w1_bundle_payload()
    current = OpenAIAsrGateBundle.model_validate(payload)
    assert current.budget == original.budget
    assert current.rights_records == original.rights_records
    assert _scope_hash(current, current.asr_prompt_profile) != _scope_hash(original)
    for key in ("credential_approval", "budget_approval", "rights_approval"):
        stale = copy.deepcopy(payload)
        stale[key] = original.model_dump(mode="json")[key]
        with pytest.raises(ValidationError, match="execution scope hash"):
            OpenAIAsrGateBundle.model_validate(stale)


@pytest.mark.parametrize("mutation", ["w2", "hash", "type", "temperature", "missing"])
def test_bundle_rejects_noncanonical_profiles(mutation):
    payload = _w1_bundle_payload()
    profile = payload["asr_prompt_profile"]
    if mutation == "w2":
        profile["profile_id"] = "asr-whisper-vi-w2-v1"
    elif mutation == "hash":
        profile["prompt_sha256"] = "f" * 64
    elif mutation == "type":
        profile["prompt_utf8_bytes"] = str(profile["prompt_utf8_bytes"])
    elif mutation == "temperature":
        profile["temperature"] = 0
    else:
        del profile["prompt"]
    with pytest.raises(ValidationError):
        OpenAIAsrGateBundle.model_validate(payload)


def test_w1_scope_hash_cannot_be_used_for_other_capability_or_model():
    for changes in ({"capability": "vision"}, {"model": "gpt-transcribe"}, {"provider_key": "other"}):
        with pytest.raises(ValueError, match="exact whisper-1 ASR scope"):
            _scope_hash(_bundle(), w1_prompt_profile(), **changes)


def test_w1_settings_match_only_the_exact_verified_profile(tmp_path):
    for prompted in (False, True):
        payload = _w1_bundle_payload() if prompted else _bundle().model_dump(mode="json")
        path, digest = _write_bundle(tmp_path, payload)
        valid_id = W1_PROFILE_ID if prompted else ""
        settings = _settings(path, digest, openai_transcription_prompt_profile_id=valid_id)
        assert settings.provider_external_execution_enabled is False
        assert settings.provider_paid_execution_enabled is False
        assert settings.provider_global_kill_switch_engaged is True
        with pytest.raises(ValidationError, match="verified G-02-ASR envelope"):
            _settings(path, digest, openai_transcription_prompt_profile_id="" if prompted else W1_PROFILE_ID)
    defaults = Settings(_env_file=None)
    assert defaults.openai_transcription_prompt_profile_id == ""
    assert defaults.transcription_provider == "fixture"
    assert defaults.openai_transcription_model == ""
    assert defaults.provider_daily_limit_vnd == 0


@pytest.mark.parametrize("profile_id", ["W1", "W2", " asr-whisper-vi-w1-v1", 1, False, None])
def test_settings_reject_noncanonical_profile_id_even_when_execution_off(profile_id):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, openai_transcription_prompt_profile_id=profile_id)


@pytest.mark.parametrize("slot", [1, 2])
@pytest.mark.parametrize("durable", [False, True])
async def test_same_exact_w1_profile_works_for_both_asset_slots(tmp_path, slot, durable):
    policy = _policy(tmp_path)
    context = _context(slot, asr_prompt_profile=w1_prompt_profile())
    engine = None
    if durable:
        engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'success.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        repository = ProviderSafetyRepository(create_session_factory(engine))
        await repository.ensure_state()
        controller = DurableProviderSafetyController(policy, repository=repository, clock=lambda: ACTIVATES_AT + timedelta(minutes=5))
    else:
        controller = ProviderSafetyController(policy, clock=lambda: ACTIVATES_AT + timedelta(minutes=5))
    try:
        assert prompt_profile_sha256(context.asr_prompt_profile) == prompt_profile_sha256(policy.execution_gate.asr_prompt_profile)
        decision = await controller.preflight(context)
        assert decision.allowed and decision.reserved_vnd == 400
        # Synthetic reservation only: no execute(), resolver or provider exists.
    finally:
        if engine is not None:
            await engine.dispose()


@pytest.mark.parametrize("durable", [False, True])
@pytest.mark.parametrize("case", ["w1_on_w0", "w0_on_w1", "invalid_copy", "invalid_scope", "scope_removed_profile", "scope_removed_hash", "scope_fake_hash", "scope_inserted_profile", "paired_insertion", "paired_removal", "wrong_capability", "unverified", "missing_scope"])
async def test_prompt_denials_are_before_any_reservation_or_operation(tmp_path, durable, case):
    policy = _policy(tmp_path, prompted=case not in {"w1_on_w0", "scope_inserted_profile", "paired_insertion"})
    context = _context(1, asr_prompt_profile=w1_prompt_profile())
    expected = "ASR_PROMPT_PROFILE_SCOPE_MISMATCH"
    if case == "w0_on_w1":
        context = _context(1)
    elif case == "invalid_copy":
        context = context.model_copy(update={"asr_prompt_profile": w1_prompt_profile().model_copy(update={"temperature": 0})})
        expected = "ASR_PROMPT_PROFILE_INVALID"
    elif case == "invalid_scope":
        policy = policy.model_copy(update={"execution_gate": policy.execution_gate.model_copy(update={"asr_prompt_profile": {"profile_id": "W2"}})})
        expected = "ASR_PROMPT_PROFILE_INVALID"
    elif case in {"paired_insertion", "paired_removal"}:
        profile = w1_prompt_profile() if case == "paired_insertion" else None
        update = {"asr_prompt_profile": profile, "asr_prompt_profile_sha256": prompt_profile_sha256(profile)}
        original_scope = policy.execution_gate
        policy = policy.model_copy(update={"execution_gate": original_scope.model_copy(update=update)})
        assert policy.execution_gate.execution_scope_sha256 == original_scope.execution_scope_sha256
        assert policy.execution_gate.approval_record_sha256 == original_scope.approval_record_sha256
        context = _context(1, asr_prompt_profile=profile)
        expected = "ASR_PROMPT_EXECUTION_SCOPE_MISMATCH"
    elif case.startswith("scope_"):
        update = {
            "scope_removed_profile": {"asr_prompt_profile": None},
            "scope_removed_hash": {"asr_prompt_profile_sha256": None},
            "scope_fake_hash": {"asr_prompt_profile_sha256": "f" * 64},
            "scope_inserted_profile": {"asr_prompt_profile": w1_prompt_profile()},
        }[case]
        policy = policy.model_copy(update={"execution_gate": policy.execution_gate.model_copy(update=update)})
        expected = "ASR_PROMPT_PROFILE_INVALID"
    elif case == "wrong_capability":
        context = context.model_copy(update={"capability": "vision"})
        expected = "ASR_PROMPT_PROFILE_INVALID"
    elif case == "unverified":
        policy = policy.model_copy(update={"verified_gate_required": False})
        expected = "ASR_PROMPT_VERIFIED_GATE_REQUIRED"
    elif case == "missing_scope":
        policy = policy.model_copy(update={"execution_gate": None})
        expected = "ASR_PROMPT_VERIFIED_GATE_REQUIRED"

    engine = None
    calls = 0
    async def forbidden_operation():
        nonlocal calls
        calls += 1
        raise AssertionError("operation must not run")

    if durable:
        engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'deny.db').as_posix()}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = create_session_factory(engine)
        repository = ProviderSafetyRepository(sessions)
        await repository.ensure_state()
        controller = DurableProviderSafetyController(policy, repository=repository, clock=lambda: ACTIVATES_AT + timedelta(minutes=5))
    else:
        controller = ProviderSafetyController(policy, clock=lambda: ACTIVATES_AT + timedelta(minutes=5))
    try:
        with pytest.raises(ProviderSafetyBlocked) as blocked:
            await controller.execute(context, forbidden_operation)
        assert blocked.value.code == expected
        assert calls == 0
        if durable:
            async with sessions() as session:
                for model in (ProviderSafetyOperationORM, ProviderSafetyAttemptORM, ProviderSafetyBudgetDayORM, ProviderSafetyCircuitORM):
                    assert await session.scalar(select(func.count()).select_from(model)) == 0
        else:
            assert controller._reserved_vnd == {}
            assert controller._active_operations == set()
            assert controller._attempts == []
            assert controller._circuits == {}
    finally:
        if engine is not None:
            await engine.dispose()


def test_historical_rc15_w0_bundle_and_scope_hashes_remain_exact():
    path = Path(__file__).resolve().parents[3] / "docs/acceptance/v3-01/V3-01-GATE-RC15-OPENAI-ASR-A.json"
    raw = path.read_bytes()
    digest = "d1075d9c22c9a6fb3f608ffcd5bf2de09d81895a2b17680fc981a3680249a966"
    assert hashlib.sha256(raw).hexdigest() == digest
    scope = load_verified_provider_gate_bundle(
        path, expected_bundle_sha256=digest,
        expected_rc_commit="7d1290aacac61df98a51544731243e5e322a8644", expected_rc_tag="vf-v3-01-rc15",
    )
    assert scope.asr_prompt_profile is None
    assert scope.execution_scope_sha256 == "fee7086afeac45fa38c225365ceeae293f1a80aea1eba73bb261ce34aca350aa"
    bundle = OpenAIAsrGateBundle.model_validate_json(raw)
    assert _scope_hash(bundle) == scope.execution_scope_sha256
    assert asr_execution_scope_sha256(scope) == scope.execution_scope_sha256
    payload = json.loads(raw)
    payload["asr_prompt_profile"] = w1_prompt_profile().model_dump(mode="json")
    with pytest.raises(ValidationError, match="execution scope hash"):
        OpenAIAsrGateBundle.model_validate(payload)
