from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import Config, SERVICE, VERSION, cloud_credential_context_present
from .models import CanaryRequest, DisabledContentRequest
from .openai_provider import OpenAIProvider, silence_provider_logging
from .security import SecurityError, authenticate, probe_file

logger = logging.getLogger("npd.provider_broker")
ALLOWED_PATHS = frozenset(("/healthz", "/readyz", "/internal/canary/openai-model",
    "/internal/canary/openai-responses", "/internal/content/generate"))


def readiness(config):
    key, token = probe_file(config.api_key_file), probe_file(config.token_file)
    valid = config.valid() and not cloud_credential_context_present()
    code = "BROKER_READY"
    if not key["exists"] or not key["non_empty"] or not token["exists"] or not token["non_empty"]:
        code = "BROKER_SECRET_NOT_INSTALLED"
    elif not key["permissions_valid"] or not token["permissions_valid"]:
        code = "BROKER_SECRET_PERMISSIONS_INVALID"
    elif not valid:
        code = "BROKER_CONFIGURATION_INVALID"
    return {"status": "ready" if code == "BROKER_READY" else "not_ready", "code": code,
        "openai_secret_present": key["exists"], "openai_secret_non_empty": key["non_empty"],
        "broker_token_present": token["exists"], "broker_token_non_empty": token["non_empty"],
        "secret_permissions_valid": key["permissions_valid"] and token["permissions_valid"],
        "configuration_valid": valid}


def secure_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise SecurityError("BROKER_CLAIM_CUSTODY_INVALID")


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def create_app(config=None, *, provider=None):
    config = config or Config.runtime()
    provider = provider or OpenAIProvider(config)
    silence_provider_logging()
    app = FastAPI(title=SERVICE, version=VERSION, docs_url=None, redoc_url=None, openapi_url=None,
        redirect_slashes=False)
    lock = asyncio.Lock()

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        correlation = str(uuid.uuid4())  # Never log caller-supplied IDs/paths/header values.
        request.state.correlation = correlation
        if request.url.path not in ALLOWED_PATHS:
            response = JSONResponse({"code":"BROKER_UNKNOWN_PATH"}, status_code=404)
        else:
            body = bytearray()
            try:
                async for part in request.stream():
                    if len(body)+len(part) > config.max_body_bytes:
                        response = JSONResponse({"code":"BROKER_BODY_TOO_LARGE"},status_code=413)
                        break
                    body.extend(part)
                else:
                    request._body = bytes(body)
                    response = await call_next(request)
            except Exception:
                response = JSONResponse({"code":"BROKER_REQUEST_REJECTED"},status_code=400)
        response.headers["X-Request-ID"] = correlation
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # FastAPI's default validation response can echo caller secrets.
        if request.url.path == "/internal/content/generate":
            return JSONResponse({"code":"BROKER_CONTENT_EXECUTION_DISABLED"},status_code=403)
        return JSONResponse({"code":"BROKER_REQUEST_CONTRACT_INVALID"},status_code=400)

    @app.exception_handler(SecurityError)
    async def security_error(request, exc):
        code = str(exc)
        return JSONResponse({"code":code},status_code=401 if code == "BROKER_UNAUTHORIZED" else 503)

    async def internal_auth(request: Request):
        authenticate(request.headers, config.token_file)

    @app.get("/healthz")
    async def health():
        return {"status":"ok", "service":SERVICE, "provider":"openai", "version":VERSION}

    @app.get("/readyz")
    async def ready():
        state = readiness(config)
        return JSONResponse(state,status_code=200 if state["status"] == "ready" else 503)

    async def execute(kind, body, request):
        if readiness(config)["status"] != "ready":
            return JSONResponse({"code":readiness(config)["code"]},status_code=503)
        async with lock:
            decision = config.claims_dir/body.owner_decision_id
            secure_directory(config.claims_dir)
            secure_directory(decision)
            sync_directory(config.claims_dir)
            sync_directory(config.claims_dir.parent)
            model_result = decision/"model.result.json"
            if kind == "responses":
                try:
                    previous = json.loads(model_result.read_text())
                    model_claim = json.loads((decision/"model.consumed.json").read_text())
                except (OSError, ValueError):
                    return JSONResponse({"code":"BROKER_MODEL_CANARY_PASS_REQUIRED"},status_code=409)
                if (not isinstance(previous,dict) or not isinstance(model_claim,dict)
                    or previous.get("code") != "BROKER_MODEL_AUTH_PASS"
                    or model_claim.get("source_head") != config.source_head):
                    return JSONResponse({"code":"BROKER_MODEL_CANARY_PASS_REQUIRED"},status_code=409)
            marker = decision/(kind+".consumed.json")
            try:
                fd = os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            except FileExistsError:
                return JSONResponse({"code":"BROKER_CANARY_ALREADY_CONSUMED"},status_code=409)
            with os.fdopen(fd,"w") as handle:
                json.dump({"owner_decision_id":body.owner_decision_id,"source_head":config.source_head,"retries":0},handle)
                handle.flush();os.fsync(handle.fileno())
            sync_directory(decision)  # Persist the consumed claim before dispatch.
            result = await provider.canary(kind)
            # Markers remain consumed even if persistence or transport fails.
            target = decision/(kind+".result.json")
            fd = os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"w") as handle:
                json.dump(result.model_dump(mode="json"),handle,sort_keys=True)
                handle.flush();os.fsync(handle.fileno())
            sync_directory(decision)
            event = {"timestamp":datetime.now(timezone.utc).isoformat(),"endpoint":request.url.path,
                "correlation_id":request.state.correlation,"provider":"openai","model":"gpt-6-luna",
                "status":result.code,"latency_ms":result.latency_ms,
                "safe_openai_request_id":result.safe_openai_request_id,
                "usage":result.BROKER_CANARY_OBSERVED_USAGE.model_dump() if result.BROKER_CANARY_OBSERVED_USAGE else None}
            logger.info(json.dumps(event,sort_keys=True))
            return JSONResponse(result.model_dump(mode="json"),status_code=200 if result.code.endswith("_PASS") else 502)

    @app.post("/internal/canary/openai-model",dependencies=[Depends(internal_auth)])
    async def model_canary(body: CanaryRequest, request: Request):
        return await execute("model",body,request)

    @app.post("/internal/canary/openai-responses",dependencies=[Depends(internal_auth)])
    async def responses_canary(body: CanaryRequest, request: Request):
        return await execute("responses",body,request)

    @app.post("/internal/content/generate",dependencies=[Depends(internal_auth)])
    async def content_disabled(body: DisabledContentRequest):
        return JSONResponse({"code":"BROKER_CONTENT_EXECUTION_DISABLED"},status_code=403)

    return app


app = create_app()
