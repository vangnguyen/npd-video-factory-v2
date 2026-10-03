"""Synthetic public admission tests; not Owner approvals or runtime readiness.

No successful provider response is used to claim admission. Real durable
controller + fixture ledger reach public request preparation with no key/call/
reservation. Fixtures use current UTC, not a substituted execution clock.
"""
import hashlib
import os
import stat
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from app.config import Settings
from app.content_models import ContentDocument
from app.mvp1_provider_admission import (AdmissionInput, Mvp1AdmissionScope, ProtectedResolverReference,
    canonical, digest, load_mvp1_admission, create_mvp1_lane_bindings)
from app.provider_safety import ProviderCallContext, ProviderSafetyBlocked, ProviderRightsEvidence
from app.provider_safety_repository import ProviderSafetyRepository
from app.provider_credential_mounts import validate_additive_assemblyai_mount
from app.storyboard_content_provider import ContentProviderProfile, ResponsesStoryboardContentProvider, ProviderEnablementError
from app.tts_evidence import ProductionTTSProfile, SpeechTimingEvidence
from app.tts_provider_execution import GovernedVietnameseTTSProvider, narration_input_sha256
from app.providers import TTSNotConfiguredError
from test_mvp1_multi_input import env

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def synthetic_public_file_custody(monkeypatch):
    """CI unit-only root-owner stat simulation, not a host custody attestation.

    Local root run exercises real custody. Unprivileged CI cannot chown files:
    simulate ONLY owner UID for this named public synthetic fixture, preserving
    real bytes/hash, symlink, mode, inode and size checks. The independent
    non-root rejection test never requests this fixture.
    """
    if os.getuid() == 0:
        return
    real_stat, real_fstat = Path.stat, os.fstat
    def owner_only(info):
        values = list(info)
        values[stat.ST_UID] = 0
        return os.stat_result(values)
    def fixture_stat(path, *args, **kwargs):
        info = real_stat(path, *args, **kwargs)
        return owner_only(info) if path.name == "synthetic-public-admission.json" else info
    def fixture_fstat(fd):
        info = real_fstat(fd)
        target = Path(os.readlink(f"/proc/self/fd/{fd}"))
        return owner_only(info) if target.name == "synthetic-public-admission.json" else info
    monkeypatch.setattr(Path, "stat", fixture_stat)
    monkeypatch.setattr(os, "fstat", fixture_fstat)


def synthetic_scope(capability="content_generation", *, workspace="workspace_dev", project="project_dev"):
    # These identifiers are deliberately test-local; no registry is allocated.
    now = datetime.now(timezone.utc)
    selected = (ContentProviderProfile(model="synthetic-model", input_vnd_per_million_tokens=100,
        output_vnd_per_million_tokens=200, estimated_cost_vnd=50) if capability == "content_generation" else
        ProductionTTSProfile(provider_key="openai-tts", model="synthetic-tts", voice_id="synthetic-voice"))
    document = ContentDocument(input_kind="idea", original_text="Ý tưởng nội bộ dùng cho contract test.")
    text = "Xin chào Tên Mẫu."
    input_hash = digest(document.model_dump(mode="json")) if capability == "content_generation" else narration_input_sha256(selected, text)
    identity = dict(source_commit="a"*40, profile_sha256=selected.sha256, workspace_id=workspace,
        project_id=project, asset_id="pver_synthetic", asset_hash=input_hash)
    provider = selected.provider_key
    purpose = "bounded content generation proposal only" if capability == "content_generation" else "bounded Vietnamese narration synthesis only"
    rights = dict(rights_record_id="synthetic_rights_01", asset_id="pver_synthetic", asset_hash=input_hash,
        source_type="internal", provider=provider, provider_asset_or_job_id="synthetic-only",
        source_url_or_reference="synthetic:test-local", acquired_at_utc=now.isoformat(), license_name=purpose,
        license_version_or_terms_date="synthetic-only", commercial_use=True, derivative_use=True,
        social_platform_use=[], territory=[], expiry=None, attribution_required=False, attribution_text="",
        model_or_voice_rights="synthetic-only", person_likeness_consent="synthetic-only",
        trademark_review="synthetic-only", evidence_reference="synthetic:not-real-rights",
        reviewer="synthetic-test-not-real-consent", decision="APPROVED", secret_recorded=False)
    rights = ProviderRightsEvidence.model_validate(rights).model_dump(mode="json")
    item = dict(operation_key="mvp1-"+capability+"-"+digest(identity),
        operation="storyboard-proposal" if capability == "content_generation" else "narration-unit",
        asset_id=identity["asset_id"], asset_hash=input_hash, narration=None if capability == "content_generation" else text,
        rights_record=rights, rights_record_sha256=digest(rights))
    # Scope ends within the current UTC day; tests are not live window authority.
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = max(start, now-timedelta(minutes=1))
    expiry = min(now+timedelta(minutes=10), now.replace(hour=23, minute=59, second=59, microsecond=999999))
    raw = dict(capability=capability, provider_key=provider,
        credential_alias=selected.credential_alias if capability == "content_generation" else "secret://openai/video-factory-vietnamese-tts",
        source_commit=identity["source_commit"], workspace_id=workspace, project_id=project, model=selected.model,
        profile=selected.model_dump(mode="json"), profile_sha256=selected.sha256,
        owner_approval_id="V3-01-APP-999999", decision="APPROVED", approved_by="Owner (GitHub: vangnguyen)",
        purpose=purpose, execution_authorized=False, valid_from_utc=start, expires_at_utc=expiry,
        budget_day_utc=now.date(), per_operation_limit_vnd=50, acceptance_window_limit_vnd=50,
        tts_vnd_per_character=None if capability == "content_generation" else Decimal("0.1"), allowed_operations=(item,))
    return Mvp1AdmissionScope(**raw), selected, document


def write_fixture(tmp_path, scope):
    path = tmp_path/"synthetic-public-admission.json"
    path.write_bytes(canonical(scope.model_dump(mode="json")))
    path.chmod(0o600)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def configured(tmp_path, scope, selected):
    path, sha = write_fixture(tmp_path, scope)
    prefix = "content" if scope.capability == "content_generation" else "tts"
    settings = Settings(_env_file=None, **{prefix+"_admission_enabled":True,
        prefix+"_admission_file":path, prefix+"_admission_sha256":sha,
        "mvp1_provider_source_commit":scope.source_commit})
    return settings, path, sha


@pytest.mark.parametrize("capability", ["content_generation", "tts"])
async def test_exact_public_admission_zero_network_zero_secret_zero_reservation(env, capability, synthetic_public_file_custody):
    scope, selected, document = synthetic_scope(capability)
    settings, path, sha = configured(env.tmp, scope, selected)
    repository = ProviderSafetyRepository(env.factory)
    forbidden = Mock(side_effect=AssertionError("protected backend MUST NOT be reached"))
    bindings = create_mvp1_lane_bindings(settings, capability=capability, repository=repository, resolver_transport=forbidden)
    if capability == "content_generation":
        candidate = ResponsesStoryboardContentProvider(selected, controller=bindings["controller"], credential_resolver=bindings["credential_resolver"])
        item = scope.allowed_operations[0]
        result = candidate.prepare_zero_call(document, workspace_id=scope.workspace_id, project_id=scope.project_id,
            job_id="job_synthetic", source_version_id=item.asset_id, input_sha256=item.asset_hash, operation_key=item.operation_key)
        assert result["request_sha256"]
    else:
        candidate = GovernedVietnameseTTSProvider(selected, **bindings)
        result = candidate.prepare_zero_call(text=scope.allowed_operations[0].narration)
        assert result["word_alignment"] == "WORD_ALIGNMENT_OPEN"
    assert result["provider_call_performed"] is False and result["credential_read_performed"] is False
    assert result["budget_reserved_vnd"] == 0 and result["full_preflight"] == "NOT_RUN"
    forbidden.assert_not_called()
    snapshot = await repository.snapshot(now=datetime.now(timezone.utc), stale_after_seconds=900)
    assert snapshot.operations_total == snapshot.attempts_recorded == snapshot.reserved_today_vnd == 0
    assert load_mvp1_admission(path, expected_sha256=sha, expected_source_commit=scope.source_commit, capability=capability).profile_sha256 == selected.sha256
    assert candidate.readiness() in {"AUTHORITY_REQUIRED", "TTS_AUTHORITY_REQUIRED"}


@pytest.mark.parametrize("mutation", ["provider", "alias", "profile", "model", "purpose", "operation", "input", "rights", "rate", "retry", "fallback", "window", "duplicate", "extra"])
def test_hostile_scope_rejected_before_key_or_budget(mutation):
    scope, _, _ = synthetic_scope()
    raw = scope.model_dump(mode="json")
    if mutation == "provider": raw["provider_key"] = "assemblyai-transcription"
    if mutation == "alias": raw["credential_alias"] = "secret://openai/codex-video"
    if mutation == "profile": raw["profile_sha256"] = "b"*64
    if mutation == "model": raw["model"] = "other-model"
    if mutation == "purpose": raw["purpose"] = "bounded Vietnamese narration synthesis only"
    if mutation == "operation": raw["allowed_operations"][0]["operation_key"] = "mvp1-content_generation-"+"c"*64
    if mutation == "input": raw["allowed_operations"][0]["asset_hash"] = "d"*64
    if mutation == "rights": raw["allowed_operations"][0]["rights_record"]["provider"] = "openai-transcription"
    if mutation == "rate": raw["profile"]["input_vnd_per_million_tokens"] = "0"
    if mutation == "retry": raw["max_attempts"] = 2
    if mutation == "fallback": raw["model_fallback"] = True
    if mutation == "window": raw["expires_at_utc"] = raw["valid_from_utc"]
    if mutation == "duplicate": raw["allowed_operations"].append(raw["allowed_operations"][0])
    if mutation == "extra": raw["api_key"] = "synthetic-plaintext-not-permitted"
    with pytest.raises(ValidationError): Mvp1AdmissionScope.model_validate(raw)


@pytest.mark.parametrize("mutation", ["raw_hash", "source", "lane", "world_write", "symlink"])
def test_loader_custody_and_raw_identity(tmp_path, mutation, synthetic_public_file_custody):
    scope, _, _ = synthetic_scope()
    path, sha = write_fixture(tmp_path, scope)
    commit, lane = scope.source_commit, scope.capability
    if mutation == "raw_hash": path.write_bytes(path.read_bytes()+b"\n")
    if mutation == "source": commit = "b"*40
    if mutation == "lane": lane = "tts"
    if mutation == "world_write": path.chmod(0o666)
    if mutation == "symlink":
        other = tmp_path/"link.json"; other.symlink_to(path); path = other
    with pytest.raises(ValueError): load_mvp1_admission(path, expected_sha256=sha, expected_source_commit=commit, capability=lane)


async def test_admission_only_bundle_cannot_reserve_or_execute(env, synthetic_public_file_custody):
    scope, selected, _ = synthetic_scope("tts")
    settings, _, _ = configured(env.tmp, scope, selected)
    repository = ProviderSafetyRepository(env.factory)
    bindings = create_mvp1_lane_bindings(settings, capability="tts", repository=repository)
    callback = Mock(side_effect=AssertionError("no provider"))
    context = next(iter(bindings["approved_units"].values()))
    with pytest.raises(ProviderSafetyBlocked): await bindings["controller"].execute(context, callback)
    callback.assert_not_called()
    snapshot = await repository.snapshot(now=datetime.now(timezone.utc), stale_after_seconds=900)
    assert snapshot.operations_total == snapshot.reserved_today_vnd == snapshot.attempts_recorded == 0


async def test_tts_version_binding_cancellation_and_no_credential(env, synthetic_public_file_custody):
    scope, selected, _ = synthetic_scope("tts")
    settings, _, _ = configured(env.tmp, scope, selected)
    bindings = create_mvp1_lane_bindings(settings, capability="tts", repository=ProviderSafetyRepository(env.factory))
    candidate = GovernedVietnameseTTSProvider(selected, **bindings)
    with pytest.raises(TTSNotConfiguredError, match="VERSION_SCOPE"):
        candidate.bind_render_scope(workspace_id=scope.workspace_id, project_id="different_project",
            content_version_id="pver_synthetic", render_id="render_synthetic", before_unit=None)
    async def cancelled(): raise RuntimeError("synthetic cancelled before unit")
    bound = candidate.bind_render_scope(workspace_id=scope.workspace_id, project_id=scope.project_id,
        content_version_id="pver_synthetic", render_id="render_synthetic", before_unit=cancelled)
    assert next(iter(bound.approved_units.values())).job_id == "render_synthetic"
    with pytest.raises(RuntimeError, match="cancelled"):
        await bound.synthesize(text=scope.allowed_operations[0].narration, language="vi", output_path=env.tmp/"none.wav")
    assert not (env.tmp/"none.wav").exists()


def test_default_lanes_no_selection_no_file_load_no_key():
    settings = Settings(_env_file=None)
    for lane in ("content_generation", "tts"):
        assert create_mvp1_lane_bindings(settings, capability=lane, repository=None) == {
            "controller":None, "credential_resolver":None, "approved_units":{}}
    assert not settings.content_admission_enabled and not settings.tts_admission_enabled
    assert settings.production_tts_voice_id == settings.content_generation_model == ""


@pytest.mark.parametrize("mutation", ["reset", "unit", "id", "source", "plaintext", "command", "env"])
def test_asr_additive_candidate_cannot_remove_mounts_or_expand_scope(mutation):
    base = (ROOT/"deploy/executor/npd-vf-secret-resolver.service").read_text()
    text = (ROOT/"deploy/executor/npd-vf-secret-resolver.service.d/20-assemblyai-credential.conf").read_text()
    unit = "npd-vf-secret-resolver.service"
    if mutation == "reset": text += "LoadCredentialEncrypted=\n"
    if mutation == "unit": unit = "other.service"
    if mutation == "id": text = text.replace("=assemblyai-stt", "=openai-stt")
    if mutation == "source": text = text.replace("/etc/credstore.encrypted/assemblyai", "/arbitrary/assemblyai")
    if mutation == "plaintext": text += "LoadCredential=other:/tmp/plaintext\n"
    if mutation == "command": text += "ExecStart=/tmp/arbitrary\n"
    if mutation == "env": text += "Environment=API_KEY=synthetic\n"
    with pytest.raises(ValueError): validate_additive_assemblyai_mount(unit_name=unit, unit_text=base, dropin_text=text)


def test_requested_timing_source_spelling_and_no_fake_measured_words():
    with pytest.raises(ValidationError): SpeechTimingEvidence(source="PROVIDER_MEASURED", duration_seconds=1)
    assert SpeechTimingEvidence(source="ESTIMATED_SEGMENT", duration_seconds=1).words == []


@pytest.mark.parametrize("field,value", [("workspace_id", "other_workspace"), ("project_id", "other_project"),
    ("asset_id", "pver_other_version"), ("asset_hash", "f"*64), ("credential_alias", "secret://openai/codex-video")])
async def test_public_context_drift_never_reaches_secret_budget_or_provider(env, field, value, synthetic_public_file_custody):
    scope, selected, _ = synthetic_scope("tts")
    settings, _, _ = configured(env.tmp, scope, selected)
    repository = ProviderSafetyRepository(env.factory)
    forbidden = Mock(side_effect=AssertionError("no credential handoff"))
    bindings = create_mvp1_lane_bindings(settings, capability="tts", repository=repository, resolver_transport=forbidden)
    context = next(iter(bindings["approved_units"].values())).model_copy(update={field:value})
    assert scope.denial_for(context, datetime.now(timezone.utc), require_execution=False)
    with pytest.raises(RuntimeError): bindings["credential_resolver"].resolve_for_context(context)
    forbidden.assert_not_called()
    snapshot = await repository.snapshot(now=datetime.now(timezone.utc), stale_after_seconds=900)
    assert snapshot.operations_total == snapshot.attempts_recorded == snapshot.reserved_today_vnd == 0


def test_one_invalid_public_lane_does_not_abort_other_lane(tmp_path, synthetic_public_file_custody):
    from app.storyboard_content_provider import create_storyboard_content_provider
    scope, selected, _ = synthetic_scope("tts")
    settings, _, _ = configured(tmp_path, scope, selected)
    settings = settings.model_copy(update={"content_generation_provider":"responses", "content_admission_enabled":True,
        "content_admission_file":tmp_path/"missing-public.json", "content_admission_sha256":"b"*64})
    blocked = create_mvp1_lane_bindings(settings, capability="content_generation", repository=None)
    assert blocked["admission_error"] == "MVP1_LANE_ADMISSION_BLOCKED"
    assert create_storyboard_content_provider(settings, controller=blocked["controller"],
        credential_resolver=blocked["credential_resolver"], admission_error=blocked["admission_error"]).readiness() == "MVP1_LANE_ADMISSION_BLOCKED"
    tts = create_mvp1_lane_bindings(settings, capability="tts", repository=None)
    assert tts["controller"] is not None and tts["approved_units"]


def test_global_live_flags_without_selected_lane_cannot_become_authority():
    with pytest.raises(ValidationError, match="SELECTED_EXECUTABLE_LANE"):
        Settings(_env_file=None, content_admission_enabled=True,
            provider_external_execution_enabled=True, provider_paid_execution_enabled=True)


def test_unknown_lane_fails_before_path_or_credential():
    with pytest.raises(ValueError, match="UNKNOWN_CAPABILITY"):
        create_mvp1_lane_bindings(Settings(_env_file=None), capability="arbitrary", repository=None)


def test_nonroot_cannot_admit_self_owned_public_authority(tmp_path):
    import os
    if os.getuid() == 0:
        # Run this exact node separately as non-root; do not claim DAC from root.
        pytest.skip("root custody rejection requires non-root execution")
    scope, _, _ = synthetic_scope()
    path, sha = write_fixture(tmp_path, scope)
    with pytest.raises(ValueError, match="ROOT_CUSTODY_REQUIRED"):
        load_mvp1_admission(path, expected_sha256=sha, expected_source_commit=scope.source_commit, capability=scope.capability)
