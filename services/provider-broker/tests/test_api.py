import asyncio
import json
import logging
import os

import httpx
import pytest

from npd_provider_broker import main, security
from npd_provider_broker.models import CanaryResult

pytestmark=pytest.mark.asyncio
DECISION="VF-MVP1-VPS-PROVIDER-BROKER-BOOTSTRAP-21"
TOKEN="offline-internal-token"
HEADERS={"Authorization":"Bearer "+TOKEN}
BODY={"owner_decision_id":DECISION}
MODEL="/internal/canary/openai-model"
RESPONSES="/internal/canary/openai-responses"
CONTENT="/internal/content/generate"


class FakeProvider:
    def __init__(self): self.calls=[];self.model_pass=True;self.raise_error=False
    async def canary(self,kind):
        self.calls.append(kind)
        if self.raise_error: raise RuntimeError("synthetic-provider-body-must-not-escape")
        await asyncio.sleep(0)
        return CanaryResult(code=("BROKER_MODEL_AUTH_PASS" if kind=="model" else "BROKER_RESPONSES_CANARY_PASS")
                            if self.model_pass else "BROKER_OPENAI_KEY_INVALID",provider_http_status=200 if self.model_pass else 401)


@pytest.fixture
def fixture_app(config,monkeypatch):
    # Synthetic fixture custody only: GitHub runner is non-root. Production custody
    # remains strict root:root/0600 and is tested separately.
    monkeypatch.setattr(main,"probe_file",lambda path:{"exists":True,"non_empty":True,"permissions_valid":True})
    def read(path):
        assert path==config.token_file, "API must never read the provider key"
        return TOKEN
    monkeypatch.setattr(security,"read_secret",read)
    def directory(path): path.mkdir(parents=True,exist_ok=True,mode=0o700)
    monkeypatch.setattr(main,"secure_directory",directory)
    provider=FakeProvider()
    return main.create_app(config,provider=provider),provider


def client(app): return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://broker.test")


async def test_health_ready_do_not_read_secrets_or_call_provider(fixture_app,monkeypatch):
    app,provider=fixture_app
    monkeypatch.setattr(security,"read_secret",lambda path:pytest.fail("diagnostics must not read key/token"))
    async with client(app) as c:
        assert (await c.get("/healthz")).json()==dict(status="ok",service="npd-provider-broker",provider="openai",version="0.1.0")
        ready=await c.get("/readyz")
        assert ready.status_code==200 and ready.json()["openai_secret_present"] is True
    assert provider.calls==[]


@pytest.mark.parametrize("path",[MODEL,RESPONSES,CONTENT])
@pytest.mark.parametrize("header",[{}, {"Authorization":"Bearer wrong"}, {"Authorization":"API-key wrong"}])
async def test_all_provider_endpoints_authenticated(fixture_app,path,header):
    app,provider=fixture_app
    async with client(app) as c:
        response=await c.post(path,json={} if path==CONTENT else BODY,headers=header)
        assert response.status_code==401
    assert provider.calls==[]


async def test_duplicate_authorization_is_rejected(fixture_app):
    app,provider=fixture_app
    async with client(app) as c:
        result=await c.post(MODEL,json=BODY,headers=[("Authorization","Bearer "+TOKEN)]*2)
    assert result.status_code==401 and provider.calls==[]


@pytest.mark.parametrize("extra",[{"model":"other"},{"api_key":"do-not-echo"},{"endpoint":"https://invalid.example"},
                                {"input":"business-data"},{"tools":[{}]},{"Authorization":"do-not-echo"}])
async def test_no_arbitrary_payload_or_credentials(fixture_app,extra):
    app,provider=fixture_app
    async with client(app) as c:
        result=await c.post(MODEL,json={**BODY,**extra},headers=HEADERS)
    assert result.status_code==400 and result.json()=={"code":"BROKER_REQUEST_CONTRACT_INVALID"}
    assert "do-not-echo" not in result.text and provider.calls==[]


@pytest.mark.parametrize("body",[{}, {"prompt":"business-data"},{"execution_authorized":True}])
async def test_content_always_disabled(fixture_app,body):
    app,provider=fixture_app
    async with client(app) as c: result=await c.post(CONTENT,json=body,headers=HEADERS)
    assert result.status_code==403 and result.json()["code"]=="BROKER_CONTENT_EXECUTION_DISABLED"
    assert provider.calls==[]


async def test_unknown_path_body_limit_method_and_no_log_disclosure(fixture_app,caplog):
    app,provider=fixture_app
    caplog.set_level(logging.DEBUG)
    async with client(app) as c:
        assert (await c.get("/v1/responses/do-not-echo?api_key=do-not-echo")).status_code==404
        assert (await c.post(MODEL,content=b"x"*1025,headers=HEADERS)).status_code==413
        assert (await c.get(MODEL,headers=HEADERS)).status_code==405
        result=await c.post(MODEL,json=BODY,headers={**HEADERS,"X-Request-ID":"do-not-echo"})
    assert result.status_code==200 and TOKEN not in caplog.text and "do-not-echo" not in caplog.text
    assert "Bearer" not in caplog.text
    assert provider.calls==["model"]


async def test_sequence_once_across_recreated_app(fixture_app,config,caplog):
    app,provider=fixture_app
    caplog.set_level(logging.INFO,logger="npd.provider_broker")
    async with client(app) as c:
        assert (await c.post(RESPONSES,json=BODY,headers=HEADERS)).status_code==409
        assert (await c.post(MODEL,json=BODY,headers=HEADERS)).status_code==200
        assert (await c.post(MODEL,json=BODY,headers=HEADERS)).status_code==409
        assert (await c.post(RESPONSES,json=BODY,headers=HEADERS)).status_code==200
    async with client(main.create_app(config,provider=provider)) as c:
        assert (await c.post(RESPONSES,json=BODY,headers=HEADERS)).status_code==409
    assert provider.calls==["model","responses"]
    assert TOKEN not in caplog.text
    assert sorted(p.name for p in (config.claims_dir/DECISION).iterdir())==[
        "model.consumed.json","model.result.json","responses.consumed.json","responses.result.json"]


async def test_failed_model_stops_responses(fixture_app):
    app,provider=fixture_app;provider.model_pass=False
    async with client(app) as c:
        assert (await c.post(MODEL,json=BODY,headers=HEADERS)).status_code==502
        assert (await c.post(RESPONSES,json=BODY,headers=HEADERS)).status_code==409
        assert (await c.post(MODEL,json=BODY,headers=HEADERS)).status_code==409
    assert provider.calls==["model"]


async def test_ambiguous_attempt_remains_consumed(fixture_app):
    app,provider=fixture_app;provider.raise_error=True
    async with client(app) as c:
        response=await c.post(MODEL,json=BODY,headers=HEADERS)
        assert response.status_code==400 and "synthetic-provider" not in response.text
        assert (await c.post(MODEL,json=BODY,headers=HEADERS)).status_code==409
        assert (await c.post(RESPONSES,json=BODY,headers=HEADERS)).status_code==409
    assert provider.calls==["model"]


async def test_concurrent_claim_is_atomic(fixture_app):
    app,provider=fixture_app
    async with client(app) as c:
        responses=await asyncio.gather(*(c.post(MODEL,json=BODY,headers=HEADERS) for _ in range(3)))
    assert sorted(r.status_code for r in responses)==[200,409,409] and provider.calls==["model"]


async def test_source_change_cannot_reuse_model_pass(fixture_app,config):
    app,provider=fixture_app
    async with client(app) as c: assert (await c.post(MODEL,json=BODY,headers=HEADERS)).status_code==200
    marker=config.claims_dir/DECISION/"model.consumed.json"
    marker.write_text(json.dumps({"source_head":"b"*40}))
    async with client(app) as c: assert (await c.post(RESPONSES,json=BODY,headers=HEADERS)).status_code==409
    assert provider.calls==["model"]
