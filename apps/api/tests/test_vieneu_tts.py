"""Synthetic transport/audio tests, not real synthesis or human acceptance."""
import asyncio
import hashlib
import io
from pathlib import Path
import shutil
import wave
import httpx
import pytest
from pydantic import ValidationError
from app.content_service import canonical_bytes
from app.config import Settings
from app.providers import TTSNotConfiguredError
from app.production_audio import create_audio_tts_provider, AudioMixEngine
from app.tts_evidence import TTSArtifactEvidence
from app.vieneu_contracts import VieNeuTTSProfile, VieNeuLicenseProvenance, LOCAL_ENDPOINT
from app.vieneu_tts_provider import VieNeuTTSProvider
from test_mvp1_multi_input import env, author, timeline


def profile(voice="Mai Anh", **changes):
    return VieNeuTTSProfile(voice_id=voice, rights=VieNeuLicenseProvenance(), **changes)


def wav(seconds=.5, rate=48000, channels=1):
    buf=io.BytesIO()
    with wave.open(buf,"wb") as audio:
        audio.setnchannels(channels); audio.setsampwidth(2); audio.setframerate(rate)
        audio.writeframes(b"\x00\x10" * int(seconds*rate)*channels)
    return buf.getvalue()


def response(provider, body=None, **headers):
    return httpx.Response(200,content=wav() if body is None else body,headers={
        "x-vieneu-profile-sha256":provider.profile.sha256,
        "x-vieneu-server-sha256":provider.server_sha,
        "x-vieneu-normalization-sha256":"2"*64, **headers})


@pytest.mark.parametrize("voice",["Mai Anh","Thùy Dung","Ngọc Huyền"])
def test_identity_license_revision_and_canonical_profile(voice):
    value=profile(voice)
    assert value.provider_key=="vieneu-tts" and value.credential_mode=="none/local_service"
    assert value.rights.license_identifier=="Apache-2.0" and not value.rights.voice_cloning_enabled
    assert value.sha256==hashlib.sha256(canonical_bytes(value.model_dump(mode="json"))).hexdigest()


@pytest.mark.parametrize("field,value",[("provider_key","openai-tts"),("model","VieNeu"),
    ("model_revision","0"*40),("voice_id","marin"),("endpoint","http://localhost:18083"),
    ("endpoint","http://127.0.0.1:18084"),("endpoint","http://api.openai.com"),
    ("credential_mode","secret://openai/codex-video"),("rights",None),
    ("runtime_version","latest"),("sdk_commit","0"*40)])
def test_unpinned_configuration_and_arbitrary_endpoint_rejected(field,value):
    doc=profile().model_dump(mode="json");doc[field]=value
    with pytest.raises(ValidationError):VieNeuTTSProfile.model_validate(doc)


def test_default_disabled_and_factory_is_not_openai():
    settings=Settings(_env_file=None,audio_tts_provider="vieneu")
    with pytest.raises(TTSNotConfiguredError):create_audio_tts_provider(settings)
    enabled=Settings(_env_file=None,audio_tts_provider="vieneu",vieneu_local_execution_enabled=True)
    assert isinstance(create_audio_tts_provider(enabled),VieNeuTTSProvider)


async def test_decode_persistence_restart_no_secret_and_no_external_request(tmp_path,monkeypatch):
    calls=[]
    async def handler(request):
        calls.append(request)
        assert str(request.url)==LOCAL_ENDPOINT+"/v1/audio/speech"
        assert "authorization" not in request.headers
        return response(provider)
    provider=VieNeuTTSProvider(profile(),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    first=await provider.synthesize(text="Ngọc Phương Đông.",language="vi",output_path=tmp_path/"audio.wav")
    restarted=VieNeuTTSProvider(profile(),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    second=await restarted.synthesize(text="Ngọc Phương Đông.",language="vi",output_path=first.path)
    assert first.evidence==second.evidence and len(calls)==1
    assert first.duration_seconds==.5 and first.evidence.audio_sha256==hashlib.sha256(first.path.read_bytes()).hexdigest()
    assert first.evidence.timing.source=="ESTIMATED_SEGMENT" and not first.evidence.timing.words
    assert first.evidence.profile.rights.preset_asset_sha256 and not first.evidence.human_quality_accepted
    assert TTSArtifactEvidence.model_validate_json(first.path.with_suffix(".wav.vieneu.json").read_bytes())==first.evidence
    with pytest.raises(ValueError,match="OUTPUT_CONFLICT"):
        await restarted.synthesize(text="changed",language="vi",output_path=first.path)
    assert len(calls)==1


@pytest.mark.parametrize("body",[b"",b"private-provider-error",wav(0),wav(rate=24000),wav(channels=2),wav()[:-20]])
async def test_bad_empty_or_truncated_audio_fail_closed(tmp_path,body):
    async def handler(_):return response(provider,body)
    provider=VieNeuTTSProvider(profile(),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    with pytest.raises((ValueError,TTSNotConfiguredError)) as error:
        await provider.synthesize(text="Test.",language="vi",output_path=tmp_path/"a.wav")
    assert "private-provider-error" not in str(error.value) and not (tmp_path/"a.wav").exists()


async def test_oversize_no_retry(tmp_path):
    calls=[]
    async def handler(_):calls.append(1);return response(provider,wav(2))
    provider=VieNeuTTSProvider(profile(max_audio_seconds=1),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError,match="TOO_LARGE"):
        await provider.synthesize(text="Test.",language="vi",output_path=tmp_path/"a.wav")
    assert calls==[1]


@pytest.mark.parametrize("field,value",[("x-vieneu-profile-sha256","0"*64),
    ("x-vieneu-server-sha256","0"*64),("x-vieneu-normalization-sha256","")])
async def test_server_identity_and_provenance_required(tmp_path,field,value):
    async def handler(_):return response(provider,**{field:value})
    provider=VieNeuTTSProvider(profile(),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    with pytest.raises(ValueError):
        await provider.synthesize(text="Test.",language="vi",output_path=tmp_path/"a.wav")
    assert not (tmp_path/"a.wav").exists()


def test_explicit_voice_change_and_unsupported_settings():
    from app.production_models import VoiceConfig
    provider=VieNeuTTSProvider(profile(),local_execution_enabled=True)
    assert provider.for_render_voice(VoiceConfig(voice="Ngọc Huyền")).voice=="Ngọc Huyền"
    for config in [VoiceConfig(speed=1.1),VoiceConfig(instructions="warm style")]:
        with pytest.raises(TTSNotConfiguredError):provider.for_render_voice(config)
    with pytest.raises(ValidationError):provider.for_render_voice(VoiceConfig(voice="cloned voice"))


def test_missing_or_changed_local_artifact_fail_closed(tmp_path):
    import runpy
    server=Path(__file__).resolve().parents[3]/"scripts/vieneu-local-server.py"
    module=runpy.run_path(str(server),run_name="audited_import_not_server_start")
    with pytest.raises(ValueError,match="PINNED_FILE_MISMATCH"):
        module["verify_files"](tmp_path,{"missing.onnx":"0"*64})
    (tmp_path/"missing.onnx").write_bytes(b"changed bytes")
    with pytest.raises(ValueError,match="PINNED_FILE_MISMATCH"):
        module["verify_files"](tmp_path,{"missing.onnx":"0"*64})


async def test_actual_local_route_reads_body_not_query_and_replays_synthetic_cache(tmp_path):
    """Transport regression only; synthetic cached WAV is not local audition evidence."""
    import runpy
    from app.content_service import canonical_bytes
    server=Path(__file__).resolve().parents[3]/"scripts/vieneu-local-server.py"
    module=runpy.run_path(str(server),run_name="transport_test_not_server_start")
    class NeverInfer:
        def infer(self, **_kwargs):raise AssertionError("no inference allowed in transport test")
    body={"profile":profile().model_dump(mode="json"),"text":"Synthetic transport test.","scope":None,"format":"wav"}
    key=hashlib.sha256(canonical_bytes(body)).hexdigest()
    audio=wav()
    (tmp_path/(key+".wav")).write_bytes(audio)
    (tmp_path/(key+".json")).write_bytes(canonical_bytes({"audio_sha256":hashlib.sha256(audio).hexdigest(),
        "normalization":{"fixture":True}}))
    app=module["build_app"](NeverInfer(),{},tmp_path,"a"*64,{})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://local.invalid") as client:
        invalid=await client.post("/v1/audio/speech",json={})
        assert invalid.status_code==422 and invalid.content==b""  # no query/request/prompt echo
        result=await client.post("/v1/audio/speech",json=body)
        assert result.status_code==200 and result.content==audio
        assert result.headers["x-vieneu-profile-sha256"]==profile().sha256
        oversized=await client.post("/v1/audio/speech",content=b"x"*40001)
        assert oversized.status_code==413
    assert not list(tmp_path.glob("*.intent"))


@pytest.mark.parametrize("late",[False,True])
async def test_stale_and_late_completion_cannot_write_audio(tmp_path,late):
    checks=[];calls=[]
    async def guard():
        checks.append(1)
        if not late or len(checks)>1:raise RuntimeError("STALE_VERSION")
    async def handler(_):calls.append(1);return response(provider)
    provider=VieNeuTTSProvider(profile(),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    bound=provider.bind_render_scope(workspace_id="w",project_id="p",content_version_id="v",render_id="r",before_unit=guard)
    with pytest.raises(RuntimeError,match="STALE_VERSION"):
        await bound.synthesize(text="Test.",language="vi",output_path=tmp_path/"a.wav")
    assert not (tmp_path/"a.wav").exists() and len(calls)==int(late)
    assert provider._scope is None  # concurrent renders never share mutable scope


async def test_cancellation_is_not_retry(tmp_path):
    entered=asyncio.Event();calls=[]
    async def handler(_):calls.append(1);entered.set();await asyncio.Event().wait()
    provider=VieNeuTTSProvider(profile(),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    task=asyncio.create_task(provider.synthesize(text="Test.",language="vi",output_path=tmp_path/"a.wav"))
    await entered.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert calls==[1] and not (tmp_path/"a.wav").exists()


async def test_private_error_not_logged_or_returned(tmp_path,caplog):
    async def handler(_):raise RuntimeError("PRIVATE_SYNTHETIC_SECRET_NOT_REAL")
    provider=VieNeuTTSProvider(profile(),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    with pytest.raises(TTSNotConfiguredError) as error:
        await provider.synthesize(text="Test.",language="vi",output_path=tmp_path/"a.wav")
    assert "PRIVATE_SYNTHETIC" not in str(error.value)+caplog.text


async def test_pipeline_estimates_reflow_and_voice_edit_invalidates_approval(env):
    from app.production_logic import derive_subtitle_cues
    from app.production_models import MixConfig
    from app.narration_pacing import reflow_snapshot
    built=await timeline(env,await author(env,original="Ngọc Phương Đông. Đây là bài thử giọng."))
    async def handler(_):return response(provider)
    provider=VieNeuTTSProvider(profile(),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    audio=AudioMixEngine(ffmpeg_path="not-invoked-synthetic-test")
    async def normalize(source,target,*,speed):shutil.copyfile(source,target)
    audio._normalize_chunk=normalize
    result=await audio.synthesize_planned_narration(provider,cues=derive_subtitle_cues(built.snapshot),
        config=MixConfig(),duration_seconds=built.snapshot.duration_seconds,output_path=env.tmp/"voice.wav",
        workdir=env.tmp,plan=built.snapshot.metadata["narration_plan"])
    assert result["provider"]=="vieneu-tts" and all(c["words"]==[] for c in result["caption_schedule"])
    assert result["timing"][0]["provider_evidence"]["profile"]["voice_id"]=="Mai Anh"
    updated=await env.timeline.commit_mutation(project_id=env.project.project_id,expected_version=1,
        snapshot=reflow_snapshot(built.snapshot,result),mutation={"type":"measured-narration-reflow"},actor_ref="synthetic")
    assert updated.approval_status=="draft" and updated.current_version==2
    changed=VieNeuTTSProvider(profile("Thùy Dung"),local_execution_enabled=True,transport=httpx.MockTransport(handler))
    # Identity change cannot reuse prior voice bytes under the same artifact path.
    with pytest.raises(ValueError,match="OUTPUT_CONFLICT"):
        await changed.synthesize(text=built.snapshot.metadata["narration_plan"]["units"][0]["text"],language="vi",output_path=env.tmp/"unit-000-raw.wav")
