import json
import logging

import httpx
import pytest

from npd_provider_broker import openai_provider as provider
from npd_provider_broker.security import SecurityError

pytestmark = pytest.mark.asyncio
SYNTHETIC_KEY = "offline-api-fixture"


def model_body():
    return {"id":"gpt-6-luna", "object":"model", "created":0, "owned_by":"openai"}


def responses_body():
    return {"id":"resp_offline", "object":"response", "created_at":0, "status":"completed",
            "error":None, "incomplete_details":None, "instructions":None, "metadata":{},
            "model":"gpt-6-luna", "parallel_tool_calls":False, "tools":[], "tool_choice":"auto",
            "temperature":1, "top_p":1,
            "output":[{"id":"msg_offline", "type":"message", "role":"assistant", "status":"completed",
                       "content":[{"type":"output_text", "text":"OK", "annotations":[]}]}],
            "usage":{"input_tokens":9, "output_tokens":1, "total_tokens":10,
                     "input_tokens_details":{"cached_tokens":0}, "output_tokens_details":{"reasoning_tokens":0}}}


def sdk_mock(monkeypatch, handler):
    original = httpx.AsyncClient
    constructors = []
    class client(original):
        def __init__(self, **kwargs):
            constructors.append(dict(kwargs))
            super().__init__(**kwargs, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(provider.httpx, "AsyncClient", client)
    monkeypatch.setattr(provider, "read_secret", lambda path:SYNTHETIC_KEY)
    return constructors


async def test_both_canaries_use_one_official_sdk_factory(config, monkeypatch):
    calls=[]
    def handler(request):
        calls.append((request.method, str(request.url), json.loads(request.content) if request.content else None))
        assert request.headers["authorization"] == "Bearer "+SYNTHETIC_KEY
        return httpx.Response(200, json=model_body() if request.method=="GET" else responses_body(),
                              headers={"x-request-id":"req_offline"})
    constructors=sdk_mock(monkeypatch,handler)
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-must-not-be-used")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://invalid.example")
    instance=provider.OpenAIProvider(config)
    model=await instance.canary("model")
    response=await instance.canary("responses")
    assert model.code=="BROKER_MODEL_AUTH_PASS"
    assert response.code=="BROKER_RESPONSES_CANARY_PASS"
    assert response.response_id=="resp_offline" and response.safe_openai_request_id=="req_offline"
    assert response.BROKER_CANARY_OBSERVED_USAGE.model_dump()=={
        "input_tokens":9,"output_tokens":1,"provider_billing_observed":False}
    assert calls==[("GET","https://api.openai.com/v1/models/gpt-6-luna",None),
                   ("POST","https://api.openai.com/v1/responses",provider.fixed_responses_payload())]
    assert len(constructors)==2
    assert all(c==dict(timeout=30,verify=True,trust_env=False,follow_redirects=False) for c in constructors)
    async with provider.openai_client_factory(config) as client:
        assert client.max_retries==0 and str(client.base_url)=="https://api.openai.com/v1/"


@pytest.mark.parametrize("kind,status,code",[
    ("model",401,"BROKER_OPENAI_KEY_INVALID"), ("model",403,"BROKER_OPENAI_PROJECT_PERMISSION_BLOCKED"),
    ("responses",400,"BROKER_RESPONSES_REQUEST_CONTRACT_ERROR"),
    ("responses",401,"BROKER_OPENAI_KEY_INVALID"), ("responses",403,"BROKER_OPENAI_RESPONSES_PERMISSION_BLOCKED"),
    ("responses",429,"BROKER_OPENAI_QUOTA_OR_RATE_BLOCKED"),
    ("responses",500,"BROKER_OPENAI_PROVIDER_FAILURE"), ("model",503,"BROKER_OPENAI_PROVIDER_FAILURE")])
async def test_error_is_one_attempt_and_does_not_disclose(config,monkeypatch,caplog,kind,status,code):
    calls=[]
    def handler(request):
        calls.append(request.method)
        return httpx.Response(status,json={"error":{"message":SYNTHETIC_KEY,"type":"synthetic","code":"synthetic"}},
                              headers={"x-request-id":"req_error"})
    sdk_mock(monkeypatch,handler)
    caplog.set_level(logging.DEBUG)
    result=await provider.OpenAIProvider(config).canary(kind)
    assert result.code==code and result.provider_http_status==status
    assert result.provider_call_count==1 and result.retries==0 and len(calls)==1
    assert SYNTHETIC_KEY not in result.model_dump_json()+caplog.text
    assert "Authorization" not in caplog.text and "Bearer" not in caplog.text


async def test_ambiguous_transport_never_retries(config,monkeypatch):
    calls=[]
    def handler(request):
        calls.append(1)
        raise httpx.ReadTimeout(SYNTHETIC_KEY,request=request)
    sdk_mock(monkeypatch,handler)
    result=await provider.OpenAIProvider(config).canary("responses")
    assert result.code=="BROKER_OPENAI_TRANSPORT_UNCERTAIN"
    assert result.provider_call_count==1 and result.retries==0 and calls==[1]
    assert SYNTHETIC_KEY not in result.model_dump_json()


@pytest.mark.parametrize("mutation",["wrong_model","incomplete","refusal","tool","two_outputs","bad_usage","too_many_tokens","wrong_text"])
async def test_response_contract_rejected_without_retry(config,monkeypatch,mutation):
    body=responses_body()
    if mutation=="wrong_model": body["model"]="other-model"
    elif mutation=="incomplete": body["status"]="incomplete"
    elif mutation=="refusal": body["output"][0]["content"]=[{"type":"refusal","refusal":"no"}]
    elif mutation=="tool": body["output"]=[{"type":"function_call","id":"fc_1","call_id":"c_1","name":"bad","arguments":"{}"}]
    elif mutation=="two_outputs": body["output"]*=2
    elif mutation=="bad_usage": body["usage"]=None
    elif mutation=="too_many_tokens": body["usage"]["output_tokens"]=17
    elif mutation=="wrong_text": body["output"][0]["content"][0]["text"]="anything else"
    calls=[]
    def handler(request):
        calls.append(1);return httpx.Response(200,json=body)
    sdk_mock(monkeypatch,handler)
    result=await provider.OpenAIProvider(config).canary("responses")
    assert result.code!="BROKER_RESPONSES_CANARY_PASS" and calls==[1]


@pytest.mark.parametrize("variable",["NPD_VF_CONTENT_API_KEY","CODEX_PROXY_CERT"])
async def test_cloud_context_blocked_before_key_read(config,monkeypatch,variable):
    monkeypatch.setenv(variable,"synthetic-presence-only")
    monkeypatch.setattr(provider,"read_secret",lambda path:pytest.fail("key must not be read in Cloud"))
    with pytest.raises(SecurityError,match="BROKER_RUNTIME_CREDENTIAL_PATH_BLOCKED"):
        provider.openai_client_factory(config)


async def test_arbitrary_endpoint_never_opens_client(config,monkeypatch):
    monkeypatch.setattr(provider,"openai_client_factory",lambda c:pytest.fail("client must not open"))
    with pytest.raises(SecurityError,match="BROKER_FIXED_ENDPOINT_REQUIRED"):
        await provider.OpenAIProvider(config).canary("https://invalid.example/anything")
