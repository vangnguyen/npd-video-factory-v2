"""Synthetic offline canary qualification; sockets and real HTTP requests are forbidden."""
import ast
import hashlib
import importlib.util
import json
import socket
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from app.codex_cloud_content_http import (
    CANARY_REQUEST_SHA256, CodexCloudContentHTTPClient, ContentAuthProbeApproval,
    ContentResponsesCanaryApproval, ContentHTTPPathError, canary_request_payload,
    current_source_head as actual_source_head,
)
from app.codex_cloud_content_secret import CodexCloudContentSecretTransport, NETWORK_SECRET_VARIABLE
from app.mvp1_provider_admission import digest, canonical
from test_codex_cloud_content_http import resolver_for, approval_for
from test_codex_cloud_content_secret import records, active_scope, ShapeForbidden

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("responses_canary", ROOT / "scripts/content-cloud-responses-canary.py")
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    blocked = Mock(side_effect=AssertionError("offline qualification cannot call network"))
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(httpx.AsyncClient, "request", blocked)
    monkeypatch.setattr(httpx.Client, "request", blocked)
    monkeypatch.setattr("app.codex_cloud_content_http.current_source_head", lambda: "a"*40)
    yield blocked
    blocked.assert_not_called()


@pytest.fixture
def binding(records, monkeypatch):
    _, manifest, scope, _ = records
    monkeypatch.setenv(NETWORK_SECRET_VARIABLE, "synthetic-canary-opaque-never-log")
    return scope, manifest["admission_raw_file_sha256"]


def approved(scope, raw_sha, **changes):
    now = datetime.now(timezone.utc)
    data = dict(owner_decision_id="VF-MVP1-SYNTHETIC-CANARY-TEST", approved_by="Owner (GitHub: vangnguyen)",
        source_head="a"*40, content_scope_sha256=digest(scope.model_dump(mode="json")),
        content_scope_raw_sha256=raw_sha, valid_from_utc=now-timedelta(seconds=1),
        expires_at_utc=now+timedelta(minutes=1), responses_canary_authorized=True)
    return ContentResponsesCanaryApproval.model_validate(data | changes)


def response_body(**changes):
    return {"id":"resp_synthetic", "model":"gpt-6-luna", "status":"completed",
        "output":[{"type":"message", "content":[{"type":"output_text", "text":"OK"}]}],
        "usage":{"input_tokens":9, "output_tokens":1}} | changes


def test_payload_is_fixed_public_and_fresh():
    expected = {"model":"gpt-6-luna", "reasoning":{"effort":"none"}, "input":"Return exactly OK.",
        "max_output_tokens":16, "store":False}
    assert canary_request_payload() == expected
    assert CANARY_REQUEST_SHA256 == hashlib.sha256(canonical(expected)).hexdigest()
    changed = canary_request_payload(); changed['reasoning']['effort'] = 'low'
    assert canary_request_payload() == expected


@pytest.mark.parametrize("changes", [{"method":"GET"}, {"path":"/v1/models/gpt-6-luna"},
    {"credential_host":"evil.invalid"}, {"model":"arbitrary"}, {"network_secret_variable":"OPENAI_API_KEY"},
    {"backend_id":"arbitrary"}, {"credential_alias":"secret://arbitrary"},
    {"content_execution_authorized":True}, {"content_budget_authorized":True},
    {"automatic_retry":True}, {"max_attempts":2}, {"canary_request_sha256":"b"*64}, {"headers":{}}])
def test_approval_rejects_arbitrary_authority_and_destination(binding, changes):
    scope, raw_sha = binding
    with pytest.raises(ValidationError): approved(scope, raw_sha, **changes)


@pytest.mark.parametrize("minutes", [0,61])
def test_approval_window_is_utc_and_at_most_sixty_minutes(binding, minutes):
    scope, raw_sha = binding
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        approved(scope, raw_sha, valid_from_utc=now, expires_at_utc=now+timedelta(minutes=minutes))
    with pytest.raises(ValidationError):
        approved(scope, raw_sha, valid_from_utc=now.replace(tzinfo=None), expires_at_utc=(now+timedelta(minutes=1)).replace(tzinfo=None))


@pytest.mark.parametrize("change", ["default_disabled", "expired", "future", "head", "raw_sha", "canonical_sha", "active_content", "model_copy"])
async def test_invalid_approval_rejected_before_placeholder_or_client(binding, monkeypatch, change):
    scope, raw_sha = binding
    if change == "active_content": scope = active_scope(scope)
    now = datetime.now(timezone.utc)
    changes = {"default_disabled":{"responses_canary_authorized":False},
        "expired":{"valid_from_utc":now-timedelta(minutes=2),"expires_at_utc":now-timedelta(minutes=1)},
        "future":{"valid_from_utc":now+timedelta(minutes=1),"expires_at_utc":now+timedelta(minutes=2)},
        "head":{"source_head":"b"*40}, "raw_sha":{"content_scope_raw_sha256":"b"*64},
        "canonical_sha":{"content_scope_sha256":"b"*64}}.get(change,{})
    approval = approved(scope, raw_sha, **changes)
    if change == "model_copy": approval = approval.model_copy(update={"content_budget_authorized":True})
    handoff = Mock(side_effect=AssertionError("handoff forbidden"))
    constructor = Mock(side_effect=AssertionError("HTTP constructor forbidden"))
    monkeypatch.setattr(CodexCloudContentSecretTransport,"_placeholder_handoff",handoff)
    monkeypatch.setattr(httpx,"AsyncClient",constructor)
    resolver = resolver_for(scope,raw_sha)
    with pytest.raises((ContentHTTPPathError,ValidationError)):
        await CodexCloudContentHTTPClient(resolver,timeout_seconds=90).responses_canary(canary_request_payload(),approval)
    assert resolver._claimed == set()
    handoff.assert_not_called(); constructor.assert_not_called()


@pytest.mark.parametrize("changes", [{"input":"business content"}, {"model":"arbitrary"}, {"tools":[]},
    {"conversation":"arbitrary"}, {"instructions":"business"}, {"max_output_tokens":2048},
    {"reasoning":{"effort":"low"}}, {"headers":{"Authorization":"synthetic-invalid"}},
    {"store":True}, {"endpoint":"https://evil.invalid"}, {"metadata":{}}])
async def test_arbitrary_payload_rejected_before_handoff(binding, monkeypatch, changes):
    scope, raw_sha = binding
    handoff = Mock(side_effect=AssertionError("handoff forbidden"))
    monkeypatch.setattr(CodexCloudContentSecretTransport,"_placeholder_handoff",handoff)
    resolver = resolver_for(scope,raw_sha)
    with pytest.raises(ContentHTTPPathError,match="FIXED_PAYLOAD_REQUIRED"):
        await CodexCloudContentHTTPClient(resolver,timeout_seconds=90).responses_canary(canary_request_payload()|changes,approved(scope,raw_sha))
    assert resolver._claimed == set(); handoff.assert_not_called()


async def test_canary_does_not_enable_content_and_approval_types_are_distinct(binding):
    scope, raw_sha = binding
    resolver = resolver_for(scope,raw_sha)
    client = CodexCloudContentHTTPClient(resolver,timeout_seconds=90)
    with pytest.raises(ContentHTTPPathError,match="CREDENTIAL_UNAVAILABLE"):
        await client.responses(canary_request_payload(),context=None)
    with pytest.raises(ContentHTTPPathError,match="CANARY_OWNER_AUTHORITY_REQUIRED"):
        await client.responses_canary(canary_request_payload(),approval_for(scope,raw_sha))
    with pytest.raises(ContentHTTPPathError,match="AUTH_PROBE_OWNER_AUTHORITY_REQUIRED"):
        await client.auth_probe(approved(scope,raw_sha))
    assert resolver._claimed == set() and not scope.execution_authorized


@pytest.mark.parametrize('argument', ['headers','path','host','model','transport'])
async def test_canary_public_method_accepts_no_caller_auth_or_routing_options(binding,argument):
    scope,raw_sha=binding
    resolver=resolver_for(scope,raw_sha)
    with pytest.raises(TypeError):
        await CodexCloudContentHTTPClient(resolver,timeout_seconds=90).responses_canary(
            canary_request_payload(),approved(scope,raw_sha),**{argument:'arbitrary'})
    assert resolver._claimed == set()


async def test_canary_snapshots_trusted_payload_before_async_entry(binding,monkeypatch):
    scope,raw_sha=binding
    caller_owned=canary_request_payload()
    sent=[]
    class OfflineClient:
        def __init__(self,**kwargs): pass
        async def __aenter__(self):
            caller_owned['input']='unapproved business text during await'
            caller_owned['reasoning']['effort']='low'
            return self
        async def __aexit__(self,*args): pass
        async def post(self,path,*,headers,json):
            assert path=='/v1/responses'
            sent.append(json)
            return httpx.Response(200)
    monkeypatch.setattr(httpx,'AsyncClient',OfflineClient)
    await CodexCloudContentHTTPClient(resolver_for(scope,raw_sha),timeout_seconds=90).responses_canary(
        caller_owned,approved(scope,raw_sha))
    assert sent==[canary_request_payload()]


def test_actual_source_head_checks_tracked_state_and_repository(monkeypatch):
    calls=[]
    def check_call(command,**kwargs):
        calls.append(command)
    def check_output(command,**kwargs):
        calls.append(command)
        return 'a'*40+'\n'
    monkeypatch.setattr('app.codex_cloud_content_http.subprocess.check_call',check_call)
    monkeypatch.setattr('app.codex_cloud_content_http.subprocess.check_output',check_output)
    assert actual_source_head() == 'a'*40
    assert calls == [['git','diff','--quiet','HEAD','--'],['git','rev-parse','HEAD']]
    def dirty(*args,**kwargs): raise RuntimeError('synthetic dirty tracked source')
    monkeypatch.setattr('app.codex_cloud_content_http.subprocess.check_call',dirty)
    with pytest.raises(ContentHTTPPathError,match='SOURCE_HEAD_UNAVAILABLE'): actual_source_head()


def test_same_opaque_handoff_identity_and_local_claim_no_shape_or_logging(binding, monkeypatch, capsys, caplog):
    scope, raw_sha = binding
    opaque = ShapeForbidden("synthetic opaque no inspection")
    monkeypatch.setattr("app.codex_cloud_content_secret.os.environ",{NETWORK_SECRET_VARIABLE:opaque})
    resolver = resolver_for(scope,raw_sha)
    approval = approved(scope,raw_sha)
    assert resolver.resolve_for_responses_canary(approval) is opaque
    with pytest.raises(RuntimeError,match="ALREADY_CLAIMED"):
        resolver.resolve_for_responses_canary(approval)
    assert resolver._claimed == {"responses-canary:"+approval.owner_decision_id}
    assert opaque not in repr(resolver) and opaque not in caplog.text
    captured=capsys.readouterr(); assert captured.out == captured.err == ''


async def test_missing_proxy_blocks_canary_before_handoff(binding, monkeypatch):
    scope, raw_sha = binding
    monkeypatch.setenv("NO_PROXY","api.openai.com"); monkeypatch.setenv("no_proxy","api.openai.com")
    resolver = resolver_for(scope,raw_sha)
    with pytest.raises(ContentHTTPPathError,match="PLACEHOLDER_ESCAPED_PROXY_CONTEXT"):
        await CodexCloudContentHTTPClient(resolver,timeout_seconds=90).responses_canary(canary_request_payload(),approved(scope,raw_sha))
    assert resolver._claimed == set()


async def test_no_ambient_key_fallback_and_safe_error_logging(binding, monkeypatch, caplog, capsys):
    scope, raw_sha = binding
    monkeypatch.delenv(NETWORK_SECRET_VARIABLE)
    monkeypatch.setenv("OPENAI_API_KEY","synthetic-fallback-forbidden")
    with pytest.raises(ContentHTTPPathError,match="CREDENTIAL_UNAVAILABLE"):
        await CodexCloudContentHTTPClient(resolver_for(scope,raw_sha),timeout_seconds=90).responses_canary(canary_request_payload(),approved(scope,raw_sha))
    captured=capsys.readouterr(); assert captured.out == captured.err == ''
    assert 'synthetic-fallback' not in caplog.text


def test_script_default_and_missing_required_pins_are_offline(binding, monkeypatch, capsys):
    scope, raw_sha = binding
    blocked=Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(CodexCloudContentHTTPClient,'responses_canary',blocked)
    assert script.main([]) == 0
    assert json.loads(capsys.readouterr().out)['responses_canary_call_count'] == 0
    assert script.main(['canary']) == 2
    assert json.loads(capsys.readouterr().out)['provider_call_count'] == 0
    result=script.diagnose(scope,raw_sha)
    assert result['placeholder_identity_match'] and not result['execution_authorized']
    assert result['responses_canary_call_count'] == result['budget_reservations'] == 0
    blocked.assert_not_called()


async def test_cross_process_claim_binds_decision_not_new_window_or_directory_and_no_ledger(binding, monkeypatch, tmp_path, capsys, caplog):
    scope, raw_sha = binding
    original = scope.model_dump(mode='json')
    monkeypatch.setattr(script,'CANARY_CLAIMS_ROOT',tmp_path/'claims')
    ledger=Mock(side_effect=AssertionError('no ledger access'))
    monkeypatch.setattr(sqlite3,'connect',ledger)
    calls=[]
    async def fake(self,payload,approval):
        assert payload == canary_request_payload()
        calls.append(approval.owner_decision_id)
        return httpx.Response(200,json=response_body(),headers={'x-request-id':'req_synthetic'})
    monkeypatch.setattr(CodexCloudContentHTTPClient,'responses_canary',fake)
    first=await script.canary(scope,raw_sha,approved(scope,raw_sha),output_dir=tmp_path/'first')
    assert first['status'] == 'CONTENT_RESPONSES_CANARY_PASS'
    assert first['CANARY_OBSERVED_USAGE'] == {'input_tokens':9,'output_tokens':1,'modeled_cost_vnd':'0.042000','provider_billing_observed':False}
    with pytest.raises(FileExistsError):
        await script.canary(scope,raw_sha,approved(scope,raw_sha),output_dir=tmp_path/'second')
    assert len(calls) == 1 and scope.model_dump(mode='json') == original
    assert first['content_operations'] == first['budget_reservations'] == first['new_conservative_charges'] == 0
    ledger.assert_not_called()
    saved=(tmp_path/'first'/'CANARY_RESULT.json').read_text()
    assert 'synthetic-canary-opaque-never-log' not in saved+caplog.text
    assert 'Authorization' not in saved
    captured=capsys.readouterr(); assert captured.out == captured.err == ''


@pytest.mark.parametrize('status,classification', [(401,'POST_AUTH_OR_KEY_PERMISSION_BLOCKER'),
    (403,'KEY_ENDPOINT_PERMISSION_OR_PROJECT_ACCESS_BLOCKER'),(400,'PAYLOAD_COMPATIBILITY_BLOCKER'),
    (429,'RATE_OR_QUOTA_BLOCKER'),(503,'PROVIDER_SERVER_FAILURE')])
async def test_future_http_failure_is_terminal_no_retry_and_error_body_not_recorded(binding, monkeypatch, tmp_path,status,classification):
    scope, raw_sha = binding
    monkeypatch.setattr(script,'CANARY_CLAIMS_ROOT',tmp_path/'claims')
    calls=[]
    async def fake(*args):
        calls.append(status)
        return httpx.Response(status,json={'error':{'type':'invalid_request_error','code':'invalid_api_key',
            'message':'synthetic-canary-opaque-never-log'}},headers={'Authorization':'synthetic-canary-opaque-never-log'})
    monkeypatch.setattr(CodexCloudContentHTTPClient,'responses_canary',fake)
    result=await script.canary(scope,raw_sha,approved(scope,raw_sha),output_dir=tmp_path/'result')
    assert result['classification'] == classification and len(calls)==1
    assert result['canary_resolver_detached'] and not result['execution_authorized']
    assert 'synthetic-canary-opaque-never-log' not in json.dumps(result)
    with pytest.raises(FileExistsError):
        await script.canary(scope,raw_sha,approved(scope,raw_sha),output_dir=tmp_path/'again')
    assert len(calls) == 1


async def test_ambiguous_transport_consumes_claim_and_no_retry(binding, monkeypatch,tmp_path):
    scope, raw_sha=binding
    monkeypatch.setattr(script,'CANARY_CLAIMS_ROOT',tmp_path/'claims')
    calls=[]
    async def fake(*args):
        calls.append(1)
        raise httpx.ReadTimeout('synthetic sensitive details never serialized')
    monkeypatch.setattr(CodexCloudContentHTTPClient,'responses_canary',fake)
    result=await script.canary(scope,raw_sha,approved(scope,raw_sha),output_dir=tmp_path/'result')
    assert result['classification']=='TRANSPORT_UNCERTAIN'
    assert 'synthetic sensitive' not in json.dumps(result)
    with pytest.raises(FileExistsError): await script.canary(scope,raw_sha,approved(scope,raw_sha),output_dir=tmp_path/'again')
    assert calls==[1]


def test_no_second_http_implementation_or_ledger_symbols_in_script():
    source=(ROOT/'scripts/content-cloud-responses-canary.py').read_text()
    tree=ast.parse(source)
    awaits=[node for node in ast.walk(tree) if isinstance(node,ast.Await)]
    assert len(awaits)==1 and awaits[0].value.func.attr=='responses_canary'
    for forbidden in ('provider_safety_operations','provider_safety_attempts','provider_safety_budget_days',
                      'create_mvp1_lane_bindings','sqlite3','requests','urllib','OPENAI_API_KEY','curl'):
        assert forbidden not in source


@pytest.mark.parametrize('body', [response_body(model='arbitrary'),response_body(status='incomplete'),
    response_body(output=[{'type':'function_call'}]), response_body(output=[{'type':'message','content':[{'type':'refusal'}]}]),
    response_body(output=[{'type':'message','content':['malformed']}]),
    response_body(usage={'input_tokens':True,'output_tokens':1}),
    response_body(usage={'input_tokens':9,'output_tokens':17})])
def test_completed_response_requires_ack_model_and_valid_usage(binding,body):
    scope,_=binding
    assert script.classify(httpx.Response(200,json=body),scope)['status'] != 'CONTENT_RESPONSES_CANARY_PASS'


def test_error_classification_survives_plaintext_and_sensitive_metadata_is_discarded(binding):
    scope,_=binding
    secret='synthetic opaque sensitive provider echo'
    result=script.classify(httpx.Response(401,text=secret,headers={'x-request-id':secret}),scope)
    assert result['classification']=='POST_AUTH_OR_KEY_PERMISSION_BLOCKER'
    result=script.classify(httpx.Response(400,json={'id':secret,'model':secret,'status':secret,
        'error':{'type':secret,'code':secret,'message':secret}},headers={'x-request-id':secret}),scope)
    assert result['classification']=='PAYLOAD_COMPATIBILITY_BLOCKER'
    assert secret not in json.dumps(result)
