"""Synthetic transport/boundary contracts only. No live authority or credential.

The synthetic controller is NOT a verified production gate; durable controller
regression is run separately. No fixture result is human/provider acceptance.
"""
import asyncio
import hashlib
import io
import json
import wave
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.content_generation import ContentProviderUnavailable
from app.content_models import ContentDocument, ContentGenerateRequest, ContentSaveRequest
from app.content_service import ContentConflictError, canonical_bytes
from app.provider_credential_mounts import validate_provider_systemd_mount
from app.provider_safety import ProviderCallContext
from app.providers import OpenAIVietnameseTTSProvider, TTSNotConfiguredError
from app.production_audio import audio_provider_status, create_audio_tts_provider, create_available_audio_tts_provider, AudioMixEngine
from app.storyboard_content_provider import (ContentProviderProfile, ResponsesStoryboardContentProvider,
    ProviderEnablementError, create_storyboard_content_provider, structured_draft_schema)
from app.tts_evidence import ProductionTTSProfile, SpeechTimingEvidence, tts_zero_call_readiness
from app.tts_provider_execution import GovernedVietnameseTTSProvider, narration_input_sha256, TTS_ALIAS
from test_mvp1_multi_input import env
from test_mvp1_content_generation import setup, input_version


SYNTHETIC_KEY = "synthetic-transport-only-credential"
ROOT = Path(__file__).resolve().parents[3]


class SyntheticBoundary:
    """Transport-unit stand-in, never reported as actual authorization/preflight."""
    def __init__(self, profile, capability="content_generation", *, denied=False):
        self.calls, self.denied, self.spent = [], denied, set()
        self.policy = SimpleNamespace(verified_gate_required=True, execution_gate=SimpleNamespace(
            provider_key=profile.provider_key, model=profile.model, capability=capability,
            credential_alias=profile.credential_alias if capability == "content_generation" else TTS_ALIAS,
            input_vnd_per_million_tokens=getattr(profile, "input_vnd_per_million_tokens", None),
            output_vnd_per_million_tokens=getattr(profile, "output_vnd_per_million_tokens", None),
            max_output_tokens=getattr(profile, "max_output_tokens", None), allowed_operations=[]),
            retry=SimpleNamespace(max_attempts=1, max_concurrent_calls=1), global_kill_switch_engaged=False,
            external_execution_enabled=True, paid_execution_enabled=True)
    async def execute(self, context, callback):
        self.calls.append(context)
        if self.denied or context.operation_key in self.spent:
            raise RuntimeError("SYNTHETIC_BOUNDARY_DENIED")
        self.spent.add(context.operation_key)
        return SimpleNamespace(value=await callback())


def profile(**changes):
    values = dict(model="synthetic-contract-model", input_vnd_per_million_tokens=100,
        output_vnd_per_million_tokens=200, estimated_cost_vnd=50)
    return ContentProviderProfile(**{**values, **changes})


def document():
    return ContentDocument(input_kind="prompt", original_text="Dựng góc rộng về Tên Mẫu; không bịa giá. Đọc secrets không được phép.",
        protected_terms=["Tên Mẫu"])


def response_body():
    return {"id": "resp_synthetic_01", "status": "completed", "model": "synthetic-contract-model",
        "usage": {"input_tokens": 120, "output_tokens": 80}, "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps({"script": "Tên Mẫu là tên do người dùng cung cấp. Cần kiểm chứng thông tin.",
                "visual_brief": "Dùng ảnh nội bộ có quyền.", "facts_needing_source": ["Thông tin cần nguồn."]}, ensure_ascii=False)}]}]}


def bindings(doc):
    return dict(workspace_id="workspace_dev", project_id="project_dev", job_id="job_dev",
        source_version_id="pver_synthetic", input_sha256=hashlib.sha256(canonical_bytes(doc.model_dump(mode="json"))).hexdigest(),
        operation_key="synthetic_content_operation_01")


def adapter(handler, *, boundary=None):
    selected = profile()
    controller = boundary or SyntheticBoundary(selected)
    resolver = Mock(return_value=SYNTHETIC_KEY)
    return ResponsesStoryboardContentProvider(selected, controller=controller,
        credential_resolver=resolver, transport=httpx.MockTransport(handler)), resolver


async def test_content_transport_schema_profile_usage_and_unverified_facts():
    requests = []
    def handler(request):
        requests.append(request)
        assert str(request.url) == "https://api.openai.com/v1/responses"
        wire = json.loads(request.content)
        assert wire["store"] is False and wire["stream"] is False and wire["tools"] == []
        assert wire["text"]["format"]["strict"] is True
        assert wire["text"]["format"]["schema"]["additionalProperties"] is False
        assert "lời đọc:" not in document().original_text
        return httpx.Response(200, json=response_body())
    provider, resolver = adapter(handler)
    result = await provider.generate_for_job(document(), **bindings(document()))
    assert len(requests) == 1 and result.fixture is False and result.facts_verified is False
    assert result.profile_sha256 == provider.profile.sha256
    assert result.modelled_cost_vnd == Decimal("0.028")
    assert result.usage == {"input_tokens": 120, "output_tokens": 80}
    assert result.request_sha256 == hashlib.sha256(canonical_bytes(json.loads(requests[0].content))).hexdigest()
    assert "Tên Mẫu" in result.result.script
    assert "unverified" in result.result.facts_needing_source[-1]
    resolver.assert_called_once_with(provider.profile.credential_alias)


def test_schema_all_required_and_defaults_live_disabled_without_secret_access():
    schema = structured_draft_schema()
    assert set(schema["required"]) == set(schema["properties"])
    settings = Settings(_env_file=None, content_generation_provider="responses")
    assert not settings.content_external_execution_enabled
    assert create_storyboard_content_provider(settings).readiness() == "CONTENT_PROVIDER_NOT_CONFIGURED"
    assert not Settings(_env_file=None).audio_external_execution_enabled
    # No construction/readiness metadata check is a durable reservation or load.
    candidate = ResponsesStoryboardContentProvider(profile())
    assert candidate.readiness() == "AUTHORITY_REQUIRED"
    assert tts_zero_call_readiness(None)["full_preflight"] == "NOT_RUN"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, content_external_execution_enabled=True, content_generation_provider="responses")


@pytest.mark.parametrize("status,category", [(400,"CONFIG"),(401,"AUTH"),(403,"AUTH"),(429,"QUOTA"),(500,"TRANSPORT")])
async def test_content_http_failure_is_safe_classified_and_not_retried(status, category):
    calls = []
    provider, resolver = adapter(lambda request: (calls.append(request) or httpx.Response(status,
        json={"error": "private user payload and unrelated secret must not enter logs"})))
    with pytest.raises(ProviderEnablementError) as error:
        await provider.generate_for_job(document(), **bindings(document()))
    assert error.value.category == category and "payload" not in str(error.value)
    assert len(calls) == 1 and resolver.call_count == 1


@pytest.mark.parametrize("mutation", ["incomplete", "refusal", "model", "usage", "extra", "names", "missing", "ambiguous"])
async def test_content_mapping_incomplete_refusal_names_and_model_fail_closed(mutation):
    body = response_body()
    if mutation == "incomplete": body["status"] = "incomplete"
    if mutation == "refusal": body["output"][0]["content"][0] = {"type":"refusal", "refusal":"No"}
    if mutation == "model": body["model"] = "different-model"
    if mutation == "usage": body["usage"]["input_tokens"] = True
    if mutation == "extra":
        data = json.loads(body["output"][0]["content"][0]["text"]); data["approved"] = True
        body["output"][0]["content"][0]["text"] = json.dumps(data)
    if mutation == "names": body["output"][0]["content"][0]["text"] = json.dumps({"script":"Tên bị đổi.","visual_brief":"", "facts_needing_source":[]})
    if mutation == "missing": del body["usage"]
    if mutation == "ambiguous": body["output"][0]["content"] *= 2
    provider, _ = adapter(lambda _: httpx.Response(200, json=body))
    with pytest.raises(ProviderEnablementError, match="MAPPING / CONTENT_STRUCTURED_RESPONSE_INVALID"):
        await provider.generate_for_job(document(), **bindings(document()))


async def test_content_transport_error_secret_echo_and_binding_rejection():
    def fail(request): raise httpx.ReadTimeout(SYNTHETIC_KEY, request=request)
    provider, _ = adapter(fail)
    with pytest.raises(ProviderEnablementError) as error:
        await provider.generate_for_job(document(), **bindings(document()))
    assert SYNTHETIC_KEY not in str(error.value) and error.value.category == "TRANSPORT"
    provider, _ = adapter(lambda _: httpx.Response(200, content=SYNTHETIC_KEY.encode()))
    with pytest.raises(ProviderEnablementError, match="SECRET_ECHO_REJECTED"):
        await provider.generate_for_job(document(), **bindings(document()))
    provider, resolver = adapter(lambda _: pytest.fail("must not send"))
    bad = {**bindings(document()), "input_sha256": "0"*64}
    with pytest.raises(ProviderEnablementError, match="INPUT_BINDING_MISMATCH"):
        await provider.generate_for_job(document(), **bad)
    resolver.assert_not_called()


async def test_content_boundary_denies_before_credential_and_does_not_use_preflight():
    boundary = SyntheticBoundary(profile(), denied=True)
    provider, resolver = adapter(lambda _: pytest.fail("network forbidden"), boundary=boundary)
    assert provider.readiness() == "CONFIG_AND_SCOPE_PRESENT"
    with pytest.raises(RuntimeError, match="BOUNDARY_DENIED"):
        await provider.generate_for_job(document(), **bindings(document()))
    resolver.assert_not_called()
    for field, value in [("capability", "asr"), ("credential_alias", "secret://openai/codex-video"), ("model", "wrong")]:
        boundary = SyntheticBoundary(profile()); setattr(boundary.policy.execution_gate, field, value)
        provider, resolver = adapter(lambda _: pytest.fail("network forbidden"), boundary=boundary)
        assert provider.readiness() == "AUTHORITY_REQUIRED"
        resolver.assert_not_called()


async def test_content_small_cost_envelope_and_secret_loader_error_are_safe():
    selected = profile(estimated_cost_vnd=Decimal("0.001"))
    resolver = Mock(return_value=SYNTHETIC_KEY)
    provider = ResponsesStoryboardContentProvider(selected, controller=SyntheticBoundary(selected),
        credential_resolver=resolver, transport=httpx.MockTransport(lambda _: pytest.fail("no network")))
    with pytest.raises(ProviderEnablementError, match="COST_ENVELOPE_TOO_SMALL"):
        await provider.generate_for_job(document(), **bindings(document()))
    resolver.assert_not_called()
    assert provider.controller.calls == []  # Not even a durable reservation boundary.
    provider, resolver = adapter(lambda _: pytest.fail("no network"))
    resolver.side_effect = RuntimeError(SYNTHETIC_KEY)
    with pytest.raises(ProviderEnablementError) as error:
        await provider.generate_for_job(document(), **bindings(document()))
    assert error.value.category == "AUTH" and SYNTHETIC_KEY not in str(error.value)


async def test_actual_durable_controller_unapproved_metadata_never_reserves_or_resolves():
    from unittest.mock import AsyncMock
    from app.provider_safety import ProviderSafetyPolicy
    from app.provider_safety_durable import DurableProviderSafetyController
    repository = AsyncMock()
    controller = DurableProviderSafetyController(ProviderSafetyPolicy(), repository=repository)
    provider, resolver = adapter(lambda _:pytest.fail("no network"), boundary=controller)
    with pytest.raises(ProviderEnablementError, match="CONTENT_AUTHORITY_REQUIRED"):
        await provider.generate_for_job(document(), **bindings(document()))
    resolver.assert_not_called()
    assert repository.mock_calls == []


async def real_service(env, handler):
    provider, resolver = adapter(handler)
    service = await setup(env, "responses", provider)
    version = await input_version(env, "prompt", "Một prompt tự do, không cần nhãn lời đọc.")
    doc = ContentDocument.model_validate(version.snapshot["content"])
    provider.controller.policy.execution_gate.allowed_operations = [SimpleNamespace(
        asset_id=version.project_version_id, asset_hash=bindings(doc)["input_sha256"], operation_key="synthetic_service_operation_01")]
    created = await service.create(env.project.project_id, ContentGenerateRequest(
        expected_content_version_id=version.project_version_id, idempotency_key="synthetic_real_service"), actor_ref="editor")
    return service, version, created["job"]["job_id"], resolver


async def test_real_service_proposal_diff_apply_cost_unknown_and_duplicate_delivery(env):
    service, version, identifier, resolver = await real_service(env, lambda _: httpx.Response(200, json=response_body()))
    await service.process(identifier); await service.process(identifier)
    result = await service.get(env.project.project_id, identifier)
    assert result["job"]["status"] == "awaiting_review"
    proposal = result["proposal"]
    assert not proposal["snapshot"]["content"]["approved"]
    assert proposal["provenance"]["fixture"] is False and proposal["provenance"]["script_diff"]
    assert proposal["provenance"]["facts_verified"] is False
    assert (await env.content.latest(env.project.project_id)).project_version_id == version.project_version_id
    applied = await service.apply(env.project.project_id, identifier, expected_version=version.project_version_id, actor_ref="editor")
    assert applied.snapshot["content"]["generator"] == "provider-storyboard-v1"
    assert not applied.snapshot["content"]["approved"]
    assert applied.snapshot["content"]["original_text"] == version.snapshot["content"]["original_text"]
    costs = await env.platform.list_cost_records(env.project.project_id)
    assert len(costs) == 1 and costs[0].actual_cost is None
    assert costs[0].estimated_cost == Decimal("0.028")
    assert resolver.call_count == 1


async def test_real_service_edit_during_transport_does_not_overwrite_user(env):
    entered, resume = asyncio.Event(), asyncio.Event()
    async def handler(_):
        entered.set(); await resume.wait()
        return httpx.Response(200, json=response_body())
    service, version, identifier, _ = await real_service(env, handler)
    task = asyncio.create_task(service.process(identifier)); await entered.wait()
    edited = await env.content.save(env.project.project_id, ContentSaveRequest(
        expected_content_version_id=version.project_version_id,
        document=ContentDocument(input_kind="script", original_text="Đây là bản sửa của người dùng.")))
    resume.set(); await task
    result = await service.get(env.project.project_id, identifier)
    assert result["job"]["error"]["code"] == "CONTENT_RESPONSE_STALE"
    assert (await env.content.latest(env.project.project_id)).project_version_id == edited.project_version_id
    with pytest.raises(ContentConflictError):
        await service.apply(env.project.project_id, identifier, expected_version=version.project_version_id, actor_ref="editor")


async def test_real_service_profile_change_before_execution_no_secret(env):
    service, _, identifier, resolver = await real_service(env, lambda _: pytest.fail("no network"))
    service.provider.profile = profile(max_output_tokens=512)
    # Scope changed too, so readiness alone cannot detect the pinned job drift.
    service.provider.controller.policy.execution_gate.max_output_tokens = 512
    await service.process(identifier)
    result = await service.get(env.project.project_id, identifier)
    assert result["job"]["error"]["code"] == "CONTENT_PROFILE_CHANGED"
    resolver.assert_not_called()


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b"\x01\x10" * 4000)
    return buffer.getvalue()


async def test_tts_actual_wav_duration_evidence_unknown_billing_not_measured_words(tmp_path):
    data = wav_bytes()
    provider = OpenAIVietnameseTTSProvider(api_key=SYNTHETIC_KEY, model="synthetic-tts-model", voice="synthetic-voice",
        instructions="Đọc tự nhiên.", speed=1.1, transport=httpx.MockTransport(lambda _: httpx.Response(200, content=data)))
    result = await provider.synthesize(text="Tên Mẫu, xin chào.", language="vi", output_path=tmp_path/"voice.wav")
    assert result.duration_seconds == .25
    assert result.evidence.audio_sha256 == hashlib.sha256(data).hexdigest()
    assert result.evidence.profile.locale == "vi-VN" and result.evidence.profile.speed == 1.1
    assert result.evidence.timing.source == "NONE" and result.evidence.timing.words == []
    assert result.evidence.billing_status == "UNKNOWN" and result.evidence.provider_credit_debit is None
    assert result.evidence.out_of_pocket_spend_vnd is None and not result.evidence.human_quality_accepted


@pytest.mark.parametrize("status,category", [(401,"AUTH"),(429,"QUOTA"),(400,"CONFIG"),(503,"TRANSPORT")])
async def test_tts_error_does_not_expose_response_body_or_credential(tmp_path, status, category):
    provider = OpenAIVietnameseTTSProvider(api_key=SYNTHETIC_KEY,
        transport=httpx.MockTransport(lambda _: httpx.Response(status, content=SYNTHETIC_KEY.encode())))
    with pytest.raises(ProviderEnablementError) as error:
        await provider.synthesize(text="Xin chào.", language="vi", output_path=tmp_path/"none.wav")
    assert error.value.category == category and SYNTHETIC_KEY not in str(error.value)
    assert not (tmp_path/"none.wav").exists()


def timing(**changes):
    return dict(source="MEASURED_PROVIDER", reference_text="Xin chào", audio_sha256="a"*64,
        duration_seconds=1, words=[{"text":"Xin", "start_seconds":0, "end_seconds":.4},
        {"text":"chào", "start_seconds":.4, "end_seconds":1}], **changes)


def test_alignment_positive_full_coverage_native_or_forced_separate_from_estimate():
    assert SpeechTimingEvidence(**timing()).source == "MEASURED_PROVIDER"
    forced = timing(); forced.update(source="FORCED_ALIGNMENT", aligner_identity="synthetic-aligner-v1")
    assert SpeechTimingEvidence(**forced).aligner_identity == "synthetic-aligner-v1"
    estimate = SpeechTimingEvidence(source="ESTIMATED_SEGMENT", duration_seconds=1,
        segments=[{"text":"Xin chào", "start_seconds":0, "end_seconds":1}])
    assert estimate.words == []


@pytest.mark.parametrize("mutation", ["zero", "negative", "overlap", "bounds", "coverage", "fake_words", "aligner_missing", "nan"])
def test_bad_alignment_cannot_be_repaired_or_relabelled(mutation):
    data = timing()
    if mutation == "zero": data["words"][1]["end_seconds"] = .4
    if mutation == "negative": data["words"][1]["end_seconds"] = .3
    if mutation == "overlap": data["words"][1]["start_seconds"] = .2
    if mutation == "bounds": data["words"][1]["end_seconds"] = 2
    if mutation == "coverage": data["words"] = data["words"][:1]
    if mutation == "fake_words": data["source"] = "ESTIMATED_SEGMENT"
    if mutation == "aligner_missing": data["source"] = "FORCED_ALIGNMENT"
    if mutation == "nan": data["words"][1]["end_seconds"] = float("nan")
    with pytest.raises(ValidationError): SpeechTimingEvidence(**data)


async def test_governed_tts_input_voice_binding_and_duplicate_no_second_resolution(tmp_path):
    selected = ProductionTTSProfile(provider_key="openai-tts", model="synthetic-tts-model", voice_id="synthetic-voice")
    digest = narration_input_sha256(selected, "Xin chào.")
    context = ProviderCallContext(operation_key="synthetic_tts_unit_01", workspace_id="workspace_dev",
        project_id="project_dev", job_id="job_dev", provider_key="openai-tts", model=selected.model,
        capability="tts", operation="narration-unit", external_call=True, paid=True,
        credential_alias=TTS_ALIAS, asset_id="pver_synthetic_unit", asset_hash=digest,
        input_media_kind="document", rights_required=True, estimated_cost_vnd=50)
    controller = SyntheticBoundary(selected, "tts"); resolver = Mock(return_value=SYNTHETIC_KEY)
    provider = GovernedVietnameseTTSProvider(selected, controller=controller, credential_resolver=resolver,
        approved_units={digest:context}, transport=httpx.MockTransport(lambda _:httpx.Response(200, content=wav_bytes())))
    result = await provider.synthesize(text="Xin chào.", language="vi", output_path=tmp_path/"speech.wav")
    assert result.evidence.profile_sha256 == selected.sha256 and resolver.call_count == 1
    with pytest.raises(RuntimeError, match="BOUNDARY_DENIED"):
        await provider.synthesize(text="Xin chào.", language="vi", output_path=tmp_path/"duplicate.wav")
    assert resolver.call_count == 1
    with pytest.raises(TTSNotConfiguredError, match="INPUT_INVALID"):
        await provider.synthesize(text="x"*4097, language="vi", output_path=tmp_path/"long.wav")
    assert resolver.call_count == 1
    with pytest.raises(TTSNotConfiguredError, match="INPUT_NOT_AUTHORIZED"):
        await provider.synthesize(text="Bản sửa mới.", language="vi", output_path=tmp_path/"edit.wav")
    assert resolver.call_count == 1


def test_tts_factory_requires_explicit_voice_and_exact_capability_never_inspects_key():
    settings = SimpleNamespace(audio_tts_provider="openai", production_tts_model="", production_tts_voice_id="")
    assert audio_provider_status(settings) == "model_voice_selection_required"
    settings.production_tts_model, settings.production_tts_voice_id = "synthetic-model", "synthetic-voice"
    assert audio_provider_status(settings) == "tts_authority_required"
    settings.provider_external_execution_enabled = settings.provider_paid_execution_enabled = settings.audio_external_execution_enabled = True
    settings.provider_global_kill_switch_engaged = False
    settings.production_tts_style, settings.production_tts_speed = "", 1
    with pytest.raises(TTSNotConfiguredError, match="CAPABILITY_INPUT_AUTHORITY_REQUIRED"):
        create_audio_tts_provider(settings)


async def test_blocked_tts_does_not_fail_shared_worker_construction(tmp_path):
    candidate = create_available_audio_tts_provider(Settings(_env_file=None, audio_tts_provider="openai"))
    with pytest.raises(TTSNotConfiguredError):
        await candidate.synthesize(text="Xin chào.", language="vi", output_path=tmp_path/"none.wav")
    assert not (tmp_path/"none.wav").exists()


async def test_provider_audio_provenance_survives_pcm_reflow_without_fake_words(env):
    from test_mvp1_multi_input import author, timeline
    from app.production_logic import derive_subtitle_cues
    from app.production_models import MixConfig
    version = await author(env, original="Đây là nội dung dùng thử.")
    built = await timeline(env, version)
    provider = OpenAIVietnameseTTSProvider(api_key=SYNTHETIC_KEY, model="synthetic-tts-model", voice="synthetic-voice",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=wav_bytes())))
    engine = AudioMixEngine(ffmpeg_path="not-invoked")
    async def normalize(source, target, *, speed):
        # Actual PCM fixture normalization (48 kHz), not fabricated timestamps.
        import struct
        with wave.open(str(source), "rb") as src:
            count = src.getnframes()*3
        with wave.open(str(target), "wb") as dst:
            dst.setnchannels(1); dst.setsampwidth(2); dst.setframerate(48000)
            dst.writeframes(struct.pack("<h",4097)*count)
    engine._normalize_chunk = normalize
    result = await engine.synthesize_planned_narration(provider, cues=derive_subtitle_cues(built.snapshot),
        config=MixConfig(), duration_seconds=built.snapshot.duration_seconds, output_path=env.tmp/"mix.wav",
        workdir=env.tmp, plan=built.snapshot.metadata["narration_plan"])
    unit = result["timing"][0]
    assert unit["provider_evidence"]["decoded_duration_seconds"] == .25
    assert unit["alignment_source_audio_only"] == "NONE"
    assert unit["provider_evidence"]["audio_sha256"] == hashlib.sha256((env.tmp/unit["provider_audio_file"]).read_bytes()).hexdigest()
    assert unit["word_alignment"] == "NOT_AVAILABLE" and unit["measured_word_timestamps"] is False
    assert result["caption_timing_source"].startswith("estimated_editorial")
    assert all(c["words"] == [] for c in result["caption_schedule"])


def mounts(unit, dropins=()):
    return validate_provider_systemd_mount(provider_key="assemblyai-transcription",
        credential_alias="secret://assemblyai/stt-video-factory-benchmark", unit_text=unit, dropins=dropins)


def test_actual_source_mount_blocker_and_candidate_no_secret_load():
    base = (ROOT/"deploy/executor/npd-vf-secret-resolver.service").read_text()
    candidate = (ROOT/"deploy/executor/assemblyai-secret-resolver.service.d/20-provider-credential.conf").read_text()
    with pytest.raises(ValueError, match="MOUNT_MISMATCH"): mounts(base)
    result = mounts(base, (candidate,))
    assert result["verdict"] == "SOURCE_MAPPING_PASS" and not result["credential_bytes_read"]
    assert result["live_load_validation"] == "NOT_RUN" and not result["execution_authority"]
    # Historical OpenAI unit remains valid without the candidate override.
    assert validate_provider_systemd_mount(provider_key="openai-transcription", credential_alias="secret://openai/codex-video",
        unit_text=base)["systemd_credential_id"] == "openai-codex-video"


@pytest.mark.parametrize("unit", [
    "[Service]\nLoadCredentialEncrypted=openai-codex-video:/etc/credstore.encrypted/openai-codex-video",
    "[Service]\nLoadCredentialEncrypted=assemblyai-stt-video-factory-benchmark:/etc/credstore.encrypted/openai-codex-video",
    "[Service]\nLoadCredentialEncrypted=assemblyai-stt-video-factory-benchmark:/arbitrary/source",
    "[Service]\nLoadCredential=assemblyai-stt-video-factory-benchmark:/secret/plaintext",
    "[Service]\nLoadCredentialEncrypted=assemblyai-stt-video-factory-benchmark:/etc/credstore.encrypted/assemblyai-stt-video-factory-benchmark\nLoadCredentialEncrypted = openai-codex-video:/etc/credstore.encrypted/openai-codex-video",
    "[Service]\nLoadCredentialEncrypted=assemblyai-stt-video-factory-benchmark:https://arbitrary.example",
])
def test_cross_provider_or_arbitrary_mount_fails_without_loading_credential(unit):
    with pytest.raises(ValueError): mounts(unit)
