"""Synthetic HTTP/event codec tests. NO live credentials, authority or voice audition."""
import asyncio
import base64
import copy
import hashlib
import json
import wave

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.content_service import canonical_bytes
from app.mvp1_provider_admission import Mvp1AdmissionScope, digest, create_mvp1_lane_bindings
from app.provider_safety_repository import ProviderSafetyRepository
from unittest.mock import Mock
from app.realtime_tts_candidate import RealtimeVietnameseTTSMigrationCandidate, WebSocketRealtimeExchange, realtime_commands, _NoRedirectConnect
from app.storyboard_content_provider import (ContentProviderProfile, ResponsesStoryboardContentProvider,
    ProviderEnablementError, single_structured_output_text, create_storyboard_content_provider)
from app.tts_evidence import RealtimeTTSProfile, TTSArtifactEvidence
from test_mvp1_provider_admission import synthetic_scope, configured, synthetic_public_file_custody
from test_mvp1_multi_input import env
from test_real_provider_enablement import (SyntheticBoundary, SYNTHETIC_KEY, document, bindings, response_body, profile)


def luna_profile(**changes):
    # Synthetic rates/envelope only, NOT proposed or approved live prices/budget.
    return profile(version=2, model="gpt-6-luna", reasoning_effort="none", **changes)


@pytest.mark.parametrize("before", [True, False])
async def test_responses_reasoning_item_is_not_the_structured_message(before):
    selected = luna_profile()
    body = response_body(); body["model"] = selected.model
    reasoning = {"type": "reasoning", "id": "rs_synthetic", "summary": [{"type": "summary_text", "text": "Synthetic metadata, not narration."}]}
    body["output"].insert(0 if before else 1, reasoning)
    requests = []
    def transport(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=body)
    provider = ResponsesStoryboardContentProvider(selected, controller=SyntheticBoundary(selected),
        credential_resolver=lambda _: SYNTHETIC_KEY, transport=httpx.MockTransport(transport))
    result = await provider.generate_for_job(document(), **bindings(document()))
    assert requests[0]["reasoning"] == {"effort": "none"}
    assert result.profile_sha256 == selected.sha256 and not result.facts_verified
    assert "Synthetic metadata" not in result.result.script


def test_reasoning_effort_changes_profile_and_request_hash_preserves_v1():
    old = profile()
    raw = old.model_dump(mode="json"); raw.pop("reasoning_effort")
    assert old.sha256 == hashlib.sha256(canonical_bytes(raw)).hexdigest()
    none, low = luna_profile(), luna_profile().model_copy(update={"reasoning_effort": "low"})
    assert none.sha256 != low.sha256
    requests = [ResponsesStoryboardContentProvider(p)._request_payload(document()) for p in (none, low)]
    assert canonical_bytes(requests[0]) != canonical_bytes(requests[1])
    assert "reasoning" not in ResponsesStoryboardContentProvider(old)._request_payload(document())
    assert ContentProviderProfile.model_validate(none.model_dump()).sha256 == none.sha256
    with pytest.raises(ValidationError): profile(model="gpt-6-luna")
    with pytest.raises(ValidationError): profile(reasoning_effort="none")
    with pytest.raises(ValidationError): luna_profile().model_validate({**none.model_dump(), "reasoning_effort":"automatic"})


@pytest.mark.parametrize("mutation", ["tool", "refusal", "two_messages", "two_texts", "empty_message",
    "wrong_role", "incomplete_message", "reasoning_as_text", "reasoning_status", "reasoning_missing_id", "reasoning_tool"])
def test_reasoning_parser_still_rejects_refusal_tools_or_ambiguity(mutation):
    output = response_body()["output"]
    reasoning = {"type":"reasoning", "id":"rs_synthetic", "summary":[]}
    output.insert(0, reasoning)
    if mutation == "tool": output.append({"type":"function_call", "name":"read_secret"})
    elif mutation == "refusal": output[1]["content"] = [{"type":"refusal", "refusal":"No"}]
    elif mutation == "two_messages": output.append(copy.deepcopy(output[1]))
    elif mutation == "two_texts": output[1]["content"] *= 2
    elif mutation == "empty_message": output[1]["content"] = []
    elif mutation == "wrong_role": output[1]["role"] = "user"
    elif mutation == "incomplete_message": output[1]["status"] = "incomplete"
    elif mutation == "reasoning_as_text": reasoning["summary"] = [{"type":"output_text", "text":"{}"}]
    elif mutation == "reasoning_status": reasoning["status"] = "incomplete"
    elif mutation == "reasoning_missing_id": del reasoning["id"]
    elif mutation == "reasoning_tool": reasoning["tool_calls"] = []
    with pytest.raises(ValueError): single_structured_output_text(output)


def luna_scope():
    scope, _, _ = synthetic_scope()
    selected = luna_profile()
    raw = scope.model_dump(mode="json")
    raw.update(model=selected.model, profile=selected.model_dump(mode="json"), profile_sha256=selected.sha256)
    for item in raw["allowed_operations"]:
        item["operation_key"] = "mvp1-content_generation-" + digest({
            **{k:raw[k] for k in ("source_commit", "profile_sha256", "workspace_id", "project_id")},
            **{k:item[k] for k in ("asset_id", "asset_hash")}})
    return raw, selected


def test_luna_profile_roundtrips_through_independent_scope_and_factory():
    raw, selected = luna_scope()
    loaded = Mvp1AdmissionScope.model_validate(raw)
    assert loaded.profile_sha256 == selected.sha256 and not loaded.execution_authorized
    settings = Settings(_env_file=None, content_generation_provider="responses", content_generation_model="gpt-6-luna",
        content_generation_reasoning_effort="none", content_generation_input_vnd_per_million_tokens=100,
        content_generation_output_vnd_per_million_tokens=200, content_generation_estimated_cost_vnd=50)
    created = create_storyboard_content_provider(settings)
    assert created.profile.sha256 == loaded.profile_sha256
    assert created.readiness() == "AUTHORITY_REQUIRED"
    with pytest.raises(ValidationError): Settings(_env_file=None, content_generation_reasoning_effort="automatic")
    raw["profile"]["reasoning_effort"] = "low"
    with pytest.raises(ValidationError): Mvp1AdmissionScope.model_validate(raw)


async def test_luna_zero_call_public_admission_uses_durable_lane_no_key_or_reservation(env, synthetic_public_file_custody):
    from datetime import datetime, timezone
    raw, selected = luna_scope()
    scope = Mvp1AdmissionScope.model_validate(raw)
    settings, _, _ = configured(env.tmp, scope, selected)
    repository = ProviderSafetyRepository(env.factory)
    forbidden = Mock(side_effect=AssertionError("no protected backend call"))
    lane = create_mvp1_lane_bindings(settings, capability="content_generation", repository=repository,
        resolver_transport=forbidden)
    provider = ResponsesStoryboardContentProvider(selected, controller=lane["controller"], credential_resolver=lane["credential_resolver"])
    item = scope.allowed_operations[0]
    _, _, doc = synthetic_scope()
    prepared = provider.prepare_zero_call(doc, workspace_id=scope.workspace_id, project_id=scope.project_id,
        job_id="job_synthetic", source_version_id=item.asset_id, input_sha256=item.asset_hash, operation_key=item.operation_key)
    assert prepared["provider_call_performed"] is False and prepared["budget_reserved_vnd"] == 0
    forbidden.assert_not_called()
    state = await repository.snapshot(now=datetime.now(timezone.utc), stale_after_seconds=900)
    assert state.operations_total == state.attempts_recorded == state.reserved_today_vnd == 0


TEXT = "Xin chào Tên Mẫu. Giữ nguyên tiếng Việt."


def synthetic_events(profile, *, text=TEXT):
    commands = realtime_commands(profile, text)
    binding = commands[1]["response"]["metadata"]
    part = dict(response_id="resp_synthetic", item_id="item_synthetic", output_index=0, content_index=0)
    pcm = b"\x01\x00" * 2400  # 100 ms synthetic PCM, not Vietnamese speech.
    item = {"id":"item_synthetic", "type":"message", "role":"assistant", "status":"completed",
        "content":[{"type":"output_audio", "transcript":text}]}
    events = [
        {"type":"session.created"},
        {"type":"session.updated", "session":copy.deepcopy(commands[0]["session"])},
        {"type":"response.created", "response":{"id":"resp_synthetic", "status":"in_progress", "metadata":binding}},
        {"type":"response.output_item.added", "response_id":"resp_synthetic", "output_index":0, "item":item},
        {"type":"response.content_part.added", **part, "part":{"type":"output_audio", "transcript":""}},
        {"type":"response.output_audio.delta", **part, "delta":base64.b64encode(pcm).decode()},
        {"type":"response.output_audio_transcript.delta", **part, "delta":text},
        {"type":"response.output_audio_transcript.done", **part, "transcript":text},
        {"type":"response.output_audio.done", **part},
        {"type":"response.content_part.done", **part, "part":{"type":"output_audio", "transcript":text}},
        {"type":"response.output_item.done", "response_id":"resp_synthetic", "output_index":0, "item":item},
        {"type":"response.done", "response":{"id":"resp_synthetic", "status":"completed", "status_details":None,
            "output":[item], "metadata":binding, "usage":{"input_tokens":20, "output_tokens":10, "total_tokens":30,
                "output_token_details":{"text_tokens":4,"audio_tokens":6}}}}]
    for i, event in enumerate(events): event["event_id"] = f"event_synthetic_{i}"
    return events


class SyntheticExchange:
    def __init__(self, events): self.stream, self.calls = events, 0
    async def events(self, commands):
        self.calls += 1
        assert [c["type"] for c in commands] == ["session.update", "response.create"]
        for event in self.stream: yield event


@pytest.mark.parametrize("voice", ["marin", "cedar"])
async def test_realtime_candidate_to_existing_audio_contract_actual_decode_no_word_times(tmp_path, voice):
    selected = RealtimeTTSProfile(voice_id=voice)
    exchange = SyntheticExchange(synthetic_events(selected))
    candidate = RealtimeVietnameseTTSMigrationCandidate(selected, exchange=exchange)
    prepared = candidate.prepare_zero_call(text=TEXT)
    assert exchange.calls == 0 and not prepared["provider_call_performed"] and not prepared["credential_read_performed"]
    result = await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"synthetic.wav")
    with wave.open(str(result.path)) as wav:
        assert wav.getnframes() == 2400 and wav.getframerate() == 24000 and wav.getnchannels() == 1
    assert result.duration_seconds == 0.1 and result.evidence.decoded_duration_seconds == 0.1
    assert result.evidence.timing.source == "NONE" and result.evidence.timing.words == []
    assert not result.evidence.human_quality_accepted
    assert result.evidence.modelled_cost_vnd is None and result.evidence.out_of_pocket_spend_vnd is None
    assert result.evidence.usage["output_token_details"]["audio_tokens"] == 6
    assert result.evidence.profile_sha256 == selected.sha256
    assert TTSArtifactEvidence.model_validate_json(result.evidence.model_dump_json()).profile.sha256 == selected.sha256
    with pytest.raises(ProviderEnablementError, match="NO_RETRY"):
        await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"second.wav")
    assert exchange.calls == 1


@pytest.mark.parametrize("mutation", ["model", "voice", "format", "vad", "tools", "session_missing", "second_response",
    "foreign_response", "foreign_item", "index", "pcm", "duplicate", "no_audio", "no_done", "error", "refusal",
    "narration", "tokens", "token_details", "ambiguous", "failed"])
async def test_realtime_candidate_mapping_failures_do_not_persist_or_retry(tmp_path, mutation):
    profile = RealtimeTTSProfile(voice_id="marin")
    events = synthetic_events(profile)
    session = events[1]["session"]
    if mutation == "model": session["model"] = "other"
    elif mutation == "voice": session["audio"]["output"]["voice"] = "cedar"
    elif mutation == "format": session["audio"]["output"]["format"]["rate"] = 16000
    elif mutation == "vad": session["audio"]["input"]["turn_detection"] = {"type":"server_vad"}
    elif mutation == "tools": session["tools"] = [{"type":"function"}]
    elif mutation == "session_missing": del events[1]
    elif mutation == "second_response": events.insert(3,{**copy.deepcopy(events[2]),"event_id":"event_extra"})
    elif mutation == "foreign_response": events[5]["response_id"] = "resp_other"
    elif mutation == "foreign_item": events[5]["item_id"] = "item_other"
    elif mutation == "index": events[5]["output_index"] = 1
    elif mutation == "pcm": events[5]["delta"] = "!"
    elif mutation == "duplicate": events.insert(6,copy.deepcopy(events[5]))
    elif mutation == "no_audio": del events[5]
    elif mutation == "no_done": events.pop()
    elif mutation == "error": events[5]["type"] = "error"
    elif mutation == "refusal": events[4]["part"]["type"] = "refusal"
    elif mutation == "narration": events[7]["transcript"] = "Lời bị sửa hoặc mất."
    elif mutation == "tokens": events[-1]["response"]["usage"]["input_tokens"] = True
    elif mutation == "token_details": del events[-1]["response"]["usage"]["output_token_details"]
    elif mutation == "ambiguous": events[-1]["response"]["output"] *= 2
    elif mutation == "failed": events[-1]["response"]["status"] = "failed"
    exchange = SyntheticExchange(events)
    candidate = RealtimeVietnameseTTSMigrationCandidate(profile, exchange=exchange)
    with pytest.raises(ProviderEnablementError, match="RESPONSE_INVALID"):
        await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"out.wav")
    assert not (tmp_path/"out.wav").exists()
    with pytest.raises(ProviderEnablementError, match="NO_RETRY"):
        await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"out.wav")
    assert exchange.calls == 1


async def test_realtime_default_has_no_live_transport_or_key_path(tmp_path):
    candidate = RealtimeVietnameseTTSMigrationCandidate(RealtimeTTSProfile(voice_id="cedar"))
    assert candidate.prepare_zero_call(text=TEXT)["full_preflight"] == "NOT_RUN"
    with pytest.raises(ProviderEnablementError, match="PROTECTED_EXCHANGE_NOT_ADMITTED"):
        await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"out.wav")
    scope, _, _ = synthetic_scope("tts")
    raw = scope.model_dump(mode="json")
    raw.update(profile=candidate.profile.model_dump(mode="json"), profile_sha256=candidate.profile.sha256,
        model=candidate.profile.model)
    with pytest.raises(ValidationError): Mvp1AdmissionScope.model_validate(raw)
    # The historical character-priced scope explicitly cannot authorize Realtime.
    assert not Settings(_env_file=None).audio_external_execution_enabled


@pytest.mark.parametrize("case", ["language", "empty", "oversize", "existing", "symlink", "parent_symlink", "audio_limit"])
async def test_realtime_input_custody_and_size_limits(tmp_path, case):
    selected = RealtimeTTSProfile(voice_id="marin", max_audio_seconds=1)
    events = synthetic_events(selected)
    exchange = SyntheticExchange(events)
    candidate = RealtimeVietnameseTTSMigrationCandidate(selected, exchange=exchange)
    text, language, output = TEXT, "vi", tmp_path/"out.wav"
    if case == "language": language = "en"
    elif case == "empty": text = "  "
    elif case == "oversize": text = "a" * 4097
    elif case in {"existing", "symlink"}:
        original = tmp_path/"original.wav"; original.write_bytes(b"original-must-be-preserved")
        if case == "existing": output = original
        else: output.symlink_to(original)
    elif case == "parent_symlink":
        folder = tmp_path/"folder"; folder.mkdir()
        link = tmp_path/"link"; link.symlink_to(folder, target_is_directory=True)
        output = link/"out.wav"
    else: events[5]["delta"] = base64.b64encode(b"\x01\x00" * 24001).decode()
    with pytest.raises(ProviderEnablementError):
        await candidate.synthesize(text=text, language=language, output_path=output)
    assert exchange.calls == (1 if case == "audio_limit" else 0)
    if case in {"existing", "symlink"}: assert original.read_bytes() == b"original-must-be-preserved"


async def test_realtime_cancellation_and_transport_ambiguity_consume_local_candidate(tmp_path):
    class Uncertain:
        async def events(self, commands):
            raise RuntimeError("synthetic-private-error-must-not-be-logged")
            yield
    candidate = RealtimeVietnameseTTSMigrationCandidate(RealtimeTTSProfile(voice_id="marin"), exchange=Uncertain())
    with pytest.raises(ProviderEnablementError) as error:
        await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"out.wav")
    assert "private-error" not in str(error.value)
    with pytest.raises(ProviderEnablementError, match="NO_RETRY"):
        await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"out.wav")


async def test_realtime_late_file_creation_cannot_overwrite_existing_asset(tmp_path):
    selected = RealtimeTTSProfile(voice_id="marin")
    output = tmp_path/"out.wav"
    class LateFile(SyntheticExchange):
        async def events(self, commands):
            output.write_bytes(b"late-user-asset")
            async for event in super().events(commands): yield event
    candidate = RealtimeVietnameseTTSMigrationCandidate(selected, exchange=LateFile(synthetic_events(selected)))
    with pytest.raises(ProviderEnablementError, match="PERSISTENCE_FAILED_NO_RETRY"):
        await candidate.synthesize(text=TEXT, language="vi", output_path=output)
    assert output.read_bytes() == b"late-user-asset"
    assert list(tmp_path.iterdir()) == [output]


async def test_realtime_cancelled_candidate_never_retries(tmp_path):
    class Cancelled:
        async def events(self, commands):
            raise asyncio.CancelledError()
            yield
    candidate = RealtimeVietnameseTTSMigrationCandidate(RealtimeTTSProfile(voice_id="marin"), exchange=Cancelled())
    with pytest.raises(asyncio.CancelledError):
        await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"out.wav")
    with pytest.raises(ProviderEnablementError, match="NO_RETRY"):
        await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"out.wav")


@pytest.mark.parametrize("changes", [{"model":"gpt-4o-mini-tts"},{"voice_id":"other"},{"locale":"en-US"},
    {"alignment_capability":"provider_word"},{"sample_rate":16000}])
def test_realtime_profile_rejects_wrong_identity_or_fake_alignment(changes):
    with pytest.raises(ValidationError): RealtimeTTSProfile.model_validate({**RealtimeTTSProfile(voice_id="marin").model_dump(), **changes})


@pytest.mark.parametrize("case", ["success", "wrong_ack", "socket_failure", "secret_echo"])
async def test_websocket_candidate_one_connection_waits_for_ack_and_no_retry(tmp_path, case):
    selected = RealtimeTTSProfile(voice_id="marin")
    events = synthetic_events(selected)
    sent, connections = [], []
    class Socket:
        async def __aenter__(self):
            if case == "socket_failure": raise RuntimeError(SYNTHETIC_KEY)
            return self
        async def __aexit__(self, *args): return False
        async def send(self, wire): sent.append(json.loads(wire))
        def __aiter__(self): return self.stream()
        async def stream(self):
            for index, event in enumerate(events):
                if index <= 1: assert len(sent) == 1
                else: assert len(sent) == 2
                if case == "wrong_ack" and index == 1:
                    event["session"]["model"] = "different"
                if case == "secret_echo" and index == 1:
                    yield json.dumps({"type":"error", "message":SYNTHETIC_KEY}); return
                yield json.dumps(event)
    def connector(uri, **options):
        connections.append(uri)
        assert uri == "wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1-mini"
        assert options["proxy"] is None and options["compression"] is None
        return Socket()
    exchange = WebSocketRealtimeExchange(selected, api_key=SYNTHETIC_KEY, connector=connector)
    candidate = RealtimeVietnameseTTSMigrationCandidate(selected, exchange=exchange)
    if case == "success":
        result = await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"out.wav")
        assert result.duration_seconds == 0.1
        assert [s["type"] for s in sent] == ["session.update", "response.create"]
    else:
        with pytest.raises(ProviderEnablementError) as error:
            await candidate.synthesize(text=TEXT, language="vi", output_path=tmp_path/"out.wav")
        assert SYNTHETIC_KEY not in str(error.value) and not (tmp_path/"out.wav").exists()
        assert len(sent) <= 1
    assert len(connections) == 1
    assert exchange._key is None
    with pytest.raises(ProviderEnablementError, match="NO_RETRY"):
        async for _ in exchange.events(realtime_commands(selected, TEXT)): pass
    assert len(connections) == 1


def test_owner_candidate_document_has_only_two_unapproved_voice_profiles():
    from pathlib import Path
    path = Path(__file__).resolve().parents[3]/"docs/acceptance/mvp1/provider-selection-candidates/OWNER_SELECTION_CANDIDATE.json"
    candidate = json.loads(path.read_text())
    assert candidate["status"] == "DRAFT_NOT_APPROVED_NOT_EXECUTION_AUTHORITY"
    assert not candidate["external_execution_authorized"]
    assert candidate["content"]["candidate_model"] == "gpt-6-luna"
    assert candidate["content"]["reasoning_effort"] == "none"
    assert candidate["content"]["full_profile_sha256"] is None
    assert candidate["tts"]["voice_candidates"] == ["marin", "cedar"]
    for voice in candidate["tts"]["voice_candidates"]:
        selected = RealtimeTTSProfile(voice_id=voice)
        assert selected.sha256 == candidate["tts"]["candidate_profile_sha256"][voice]
    assert not candidate["tts"]["selection_final"] and not candidate["tts"]["vietnamese_human_quality_accepted"]
    assert candidate["asr"]["status"] == "HOST_REMEDIATION_REQUIRED"
    assert not candidate["asr"]["installed"] and not candidate["asr"]["spent_context_reused"]


def test_realtime_redirect_is_never_followed():
    error = RuntimeError("synthetic redirect failure")
    assert _NoRedirectConnect.process_redirect(None, error) is error
