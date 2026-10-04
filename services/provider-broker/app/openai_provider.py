"""One official SDK factory, fixed endpoints/payload, terminal errors only."""
from __future__ import annotations

import logging
import re
import time

import httpx
from openai import AsyncOpenAI, APIStatusError

from .config import Config, MODEL, ORIGIN, cloud_credential_context_present
from .models import BrokerCanaryObservedUsage, CanaryResult
from .security import SecurityError, read_secret


def fixed_responses_payload():
    return {"model": MODEL, "reasoning": {"effort": "none"}, "input": "Return exactly OK.",
        "max_output_tokens": 16, "store": False}


def silence_provider_logging():
    for name in tuple(logging.root.manager.loggerDict) + ("openai", "httpx", "httpcore"):
        if name.split(".")[0] in {"openai", "httpx", "httpcore"}:
            logging.getLogger(name).setLevel(logging.CRITICAL)
            logging.getLogger(name).disabled = True


def openai_client_factory(config: Config):
    if not config.valid() or cloud_credential_context_present():
        raise SecurityError("BROKER_RUNTIME_CREDENTIAL_PATH_BLOCKED")
    silence_provider_logging()
    # Direct VPS TLS with server-side file credential. Never ambient API keys,
    # Codex Cloud placeholders, caller proxy settings or alternate transports.
    key = read_secret(config.api_key_file)
    return AsyncOpenAI(api_key=key, base_url=ORIGIN, max_retries=0,
        timeout=config.timeout_seconds, http_client=httpx.AsyncClient(
            timeout=config.timeout_seconds, verify=True, trust_env=False, follow_redirects=False))


def safe_request_id(value):
    pattern = r"(?:req_[A-Za-z0-9_.-]{1,160}|[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})"
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else None


def failure_code(status, kind):
    if status == 401: return "BROKER_OPENAI_KEY_INVALID"
    if status == 403:
        return "BROKER_OPENAI_PROJECT_PERMISSION_BLOCKED" if kind == "model" else "BROKER_OPENAI_RESPONSES_PERMISSION_BLOCKED"
    if status == 429: return "BROKER_OPENAI_QUOTA_OR_RATE_BLOCKED"
    if status is not None and status >= 500: return "BROKER_OPENAI_PROVIDER_FAILURE"
    if status == 400 and kind == "responses": return "BROKER_RESPONSES_REQUEST_CONTRACT_ERROR"
    return "BROKER_OPENAI_RESPONSE_INVALID"


class OpenAIProvider:
    def __init__(self, config: Config):
        self.config = config

    async def canary(self, kind):
        if kind not in ("model", "responses"):
            raise SecurityError("BROKER_FIXED_ENDPOINT_REQUIRED")
        started = time.monotonic()
        result = CanaryResult(code="BROKER_OPENAI_TRANSPORT_UNCERTAIN", provider_call_count=0)
        try:
            async with openai_client_factory(self.config) as client:
                result.provider_call_count = 1  # One attempt, even after ambiguous transport.
                if kind == "model":
                    raw = await client.models.with_raw_response.retrieve(MODEL)
                else:
                    raw = await client.responses.with_raw_response.create(**fixed_responses_payload())
                result.provider_http_status = raw.status_code
                result.safe_openai_request_id = safe_request_id(raw.headers.get("x-request-id"))
                parsed = raw.parse()
                # Async SDK raw response parsing may be awaitable.
                import inspect
                if inspect.isawaitable(parsed): parsed = await parsed
                body = parsed.model_dump()
                if kind == "model":
                    if raw.status_code == 200 and body.get("id") == MODEL:
                        result.code = "BROKER_MODEL_AUTH_PASS"
                        result.returned_model = MODEL
                    else:
                        result.code = failure_code(raw.status_code, kind)
                else:
                    output = body.get("output")
                    usage = body.get("usage")
                    valid = (raw.status_code == 200 and body.get("status") == "completed" and body.get("model") == MODEL
                        and isinstance(output, list) and len(output) == 1 and isinstance(output[0], dict)
                        and output[0].get("type") == "message" and isinstance(output[0].get("content"), list)
                        and len(output[0]["content"]) == 1 and isinstance(output[0]["content"][0], dict)
                        and output[0]["content"][0].get("type") == "output_text"
                        and isinstance(output[0]["content"][0].get("text"), str)
                        and output[0]["content"][0]["text"].strip() == "OK"
                        and isinstance(usage, dict) and type(usage.get("input_tokens")) is int
                        and type(usage.get("output_tokens")) is int and usage["input_tokens"] >= 0
                        and 0 <= usage["output_tokens"] <= 16)
                    if valid:
                        result.code = "BROKER_RESPONSES_CANARY_PASS"
                        result.returned_model, result.response_status = MODEL, "completed"
                        response_id = body.get("id")
                        if isinstance(response_id, str) and re.fullmatch(r"resp_[A-Za-z0-9_-]{1,160}", response_id):
                            result.response_id = response_id
                        result.BROKER_CANARY_OBSERVED_USAGE = BrokerCanaryObservedUsage(
                            input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"])
                    else:
                        result.code = failure_code(raw.status_code, kind)
        except APIStatusError as exc:
            result.provider_http_status = exc.status_code
            result.safe_openai_request_id = safe_request_id(exc.response.headers.get("x-request-id"))
            result.code = failure_code(exc.status_code, kind)
        except SecurityError as exc:
            # Only our static error codes, never an SDK error/body/credential repr.
            result.code = str(exc)
        except Exception:
            result.code = "BROKER_OPENAI_TRANSPORT_UNCERTAIN"
        result.latency_ms = round((time.monotonic()-started)*1000, 3)
        return result
