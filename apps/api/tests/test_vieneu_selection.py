"""Synthetic contract tests; Owner voice selection is not output acceptance."""
import hashlib
import json
from pathlib import Path
import runpy
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from app.config import Settings
from app.content_service import canonical_bytes
from app.production_audio import audio_provider_status, create_audio_tts_provider
from app.production_models import VoiceConfig
from app.providers import TTSNotConfiguredError
from app.vieneu_contracts import (VieNeuVoiceSelection, VieNeuTTSProfile, VieNeuLicenseProvenance,
    SELECTED_PROFILE_SHA, selected_vieneu_profile)
from app.vieneu_tts_provider import VieNeuTTSProvider


def test_owner_selected_exact_profile_and_deterministic_sidecar():
    profile = selected_vieneu_profile()
    assert profile.voice_id == "Thùy Dung" and profile.sha256 == SELECTED_PROFILE_SHA
    raw = canonical_bytes(profile.model_dump(mode="json"))
    assert hashlib.sha256(raw).hexdigest() == SELECTED_PROFILE_SHA
    assert VieNeuTTSProfile.model_validate_json(raw).sha256 == SELECTED_PROFILE_SHA
    sidecar = VieNeuVoiceSelection()
    assert not sidecar.human_quality_accepted and not sidecar.deployment_authorized
    assert sidecar.real_input_output_review == "PENDING" and sidecar.word_alignment == "WORD_ALIGNMENT_OPEN"
    assert sidecar.sha256 == VieNeuVoiceSelection.model_validate_json(canonical_bytes(sidecar.model_dump(mode="json"))).sha256


@pytest.mark.parametrize("voice", ["Mai Anh", "Ngọc Huyền"])
def test_worker_cannot_switch_selected_voice_but_audition_history_still_loads(voice):
    historical = VieNeuTTSProfile(voice_id=voice, rights=VieNeuLicenseProvenance())
    assert VieNeuTTSProvider(historical).voice == voice  # explicit audition-only path preserved
    settings = Settings(_env_file=None, audio_tts_provider="vieneu",
        vieneu_local_execution_enabled=True, vieneu_voice_id=voice)
    assert audio_provider_status(settings) == "selected_voice_mismatch"
    with pytest.raises(TTSNotConfiguredError, match="OWNER_REVIEW"):
        create_audio_tts_provider(settings)


def test_factory_defaults_to_selected_voice_and_cannot_change_render_voice():
    settings = Settings(_env_file=None, audio_tts_provider="vieneu", vieneu_local_execution_enabled=True)
    poison = Mock(side_effect=AssertionError("no resolver/authority/provider call allowed"))
    provider = create_audio_tts_provider(settings, credential_resolver=poison, controller=poison)
    assert provider.voice == "Thùy Dung" and provider.selected_voice_only
    for voice in ("vi", "Thùy Dung"):
        assert provider.for_render_voice(VoiceConfig(voice=voice)).profile.sha256 == SELECTED_PROFILE_SHA
    for voice in ("Mai Anh", "Ngọc Huyền"):
        with pytest.raises(TTSNotConfiguredError, match="OWNER_REVIEW"):
            provider.for_render_voice(VoiceConfig(voice=voice))
    poison.assert_not_called()


def test_selected_profile_synthesis_parameter_drift_fails_closed():
    document = selected_vieneu_profile().model_dump(mode="json")
    document["parameters"]["temperature"] = .7
    with pytest.raises(TTSNotConfiguredError, match="PROFILE_MISMATCH"):
        VieNeuTTSProvider(VieNeuTTSProfile.model_validate(document), selected_voice_only=True)


@pytest.mark.parametrize("change", [{"voice":"Mai Anh"}, {"human_quality_accepted":True},
    {"deployment_authorized":True}, {"profile_sha256":"0"*64}])
def test_selection_cannot_expand_to_acceptance_or_deployment(change):
    document = VieNeuVoiceSelection().model_dump(mode="json")
    document.update(change)
    with pytest.raises(ValidationError):
        VieNeuVoiceSelection.model_validate(document)


def review_driver():
    return runpy.run_path(str(Path(__file__).resolve().parents[3]/"scripts/vieneu-selected-review.py"),
        run_name="input_contract_test_not_inference")


def test_review_input_hash_custody_and_explicit_permission(tmp_path):
    read = review_driver()["read_bound_file"]
    path = tmp_path/"script.txt"
    path.write_text("Ngọc Phương Đông", encoding="utf-8")
    record = {"path":"script.txt", "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "permission_reference":"synthetic permission; not Owner media evidence"}
    assert read(record, tmp_path, max_bytes=100) == path
    for changed in [dict(record, sha256="0"*64), dict(record, permission_reference="")]:
        with pytest.raises(ValueError):
            read(changed, tmp_path, max_bytes=100)
    with pytest.raises(ValueError, match="SIZE_INVALID"):
        read(record, tmp_path, max_bytes=1)
    link = tmp_path/"link.txt"
    try:
        link.symlink_to(path)
    except OSError:
        pytest.skip("symlink creation unavailable on this test OS")
    with pytest.raises(ValueError, match="CUSTODY"):
        read(dict(record, path="link.txt"), tmp_path, max_bytes=100)


def test_representative_review_inputs_cannot_relabel_missing_mixed_video(tmp_path):
    loader = review_driver()["load_inputs"]
    path = tmp_path/"script.txt"
    path.write_text("Synthetic narration", encoding="utf-8")
    item = {"path":"script.txt", "sha256":hashlib.sha256(path.read_bytes()).hexdigest(), "permission_reference":"synthetic test"}
    manifest = tmp_path/"inputs.json"
    doc = {"cases":[{"case":case, "script":item, "image":item if case!="script_only" else None,
        "script_approval_reference":"synthetic editorial fixture, not Owner approval",
        "video":item if case=="mixed_no_audio" else None} for case in ["image_script", "script_only", "mixed_no_audio"]]}
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    assert loader(manifest) == doc  # media sniff/decode happens separately before inference
    doc["cases"][-1]["video"] = None
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="VIDEO_CASE_MISMATCH"):
        loader(manifest)
    doc["cases"][-1]["video"] = item
    doc["cases"][0]["script_approval_reference"] = ""
    manifest.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="SCRIPT_REVIEW_REQUIRED"):
        loader(manifest)


async def test_final_does_not_accept_voice_selection_in_place_of_movie_review(tmp_path):
    driver = review_driver()
    movie = tmp_path/"review.mp4"
    movie.write_bytes(b"synthetic-not-media-negative-review-binding-test")
    digest = hashlib.sha256(movie.read_bytes()).hexdigest()
    (tmp_path/"metadata.json").write_text(json.dumps({"source_commit":"synthetic", "review_sha256":digest}), encoding="utf-8")
    for review in [{}, {"review_sha256":digest, "decision":"PASS_AS_SELECTED_PRODUCTION_TTS_CANDIDATE", "reviewer":"Owner"},
        {"review_sha256":"0"*64, "decision":"APPROVED_FOR_FINAL_RENDER", "reviewer":"Owner"}]:
        with pytest.raises(ValueError, match="EXACT_OWNER_REVIEW_REQUIRED"):
            await driver["finalize_case"](None, tmp_path, review, "synthetic")
