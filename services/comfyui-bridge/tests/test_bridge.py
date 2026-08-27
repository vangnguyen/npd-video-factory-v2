from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from npd_comfyui_bridge.backend import DeterministicMockComfyUIBackend
from npd_comfyui_bridge.models import BridgeJobCreate
from npd_comfyui_bridge.service import ComfyUIBridgeService
from npd_comfyui_bridge.workflows import WorkflowRegistry


MANIFEST = Path(__file__).parents[3] / "workflows" / "comfyui" / "manifest.json"


async def wait_terminal(service: ComfyUIBridgeService, job_id: str):
    for _ in range(200):
        job = await service.get(job_id)
        assert job is not None
        if job.status in {"succeeded", "failed", "cancelled", "timed_out"}:
            return job
        await asyncio.sleep(0.005)
    raise AssertionError("ComfyUI bridge fixture job did not reach a terminal state")


def text_to_image_request(client_request_id: str = "fixture-request-001") -> BridgeJobCreate:
    return BridgeJobCreate(
        workflow_id="npd-text-to-image-v1",
        workflow_version="1.0.0",
        client_request_id=client_request_id,
        inputs={
            "prompt": "original real-estate establishing shot",
            "negative_prompt": "logos, watermarks",
            "aspect_ratio": "9:16",
            "reference_images": [],
            "style": "cinematic",
            "seed": 7,
            "quality": "draft",
            "operation": "generate",
        },
    )


def test_manifest_is_versioned_and_strictly_allowlisted() -> None:
    registry = WorkflowRegistry(MANIFEST)
    assert registry.manifest.manifest_version == "v2-06.1"
    assert len(registry.manifest.workflows) == 8
    assert {item.capability for item in registry.manifest.workflows} == {
        "text_to_image",
        "image_to_image",
        "inpainting",
        "outpainting",
        "upscale",
        "background_replacement",
        "image_to_video",
        "video_generation",
    }
    with pytest.raises(KeyError, match="approved allowlist"):
        registry.get("user-supplied-arbitrary-graph")
    with pytest.raises(KeyError, match="version"):
        registry.get("npd-text-to-image-v1", "99.0.0")


@pytest.mark.asyncio
async def test_submit_progress_result_and_idempotency() -> None:
    service = ComfyUIBridgeService(
        WorkflowRegistry(MANIFEST), DeterministicMockComfyUIBackend(delay_seconds=0.002)
    )
    first = await service.submit(text_to_image_request())
    replay = await service.submit(text_to_image_request())
    assert replay.job_id == first.job_id
    result = await wait_terminal(service, first.job_id)
    assert result.status == "succeeded"
    assert result.progress == 100
    assert result.result is not None
    assert result.result["fixture"] is True
    assert result.result["workflow_id"] == "npd-text-to-image-v1"
    assert len(result.result["checksum_sha256"]) == 64


@pytest.mark.asyncio
async def test_idempotency_key_reuse_with_different_payload_is_rejected() -> None:
    service = ComfyUIBridgeService(
        WorkflowRegistry(MANIFEST), DeterministicMockComfyUIBackend(delay_seconds=0.002)
    )
    original = text_to_image_request("fixture-request-conflict")
    await service.submit(original)
    conflicting = original.model_copy(
        update={"inputs": {**original.inputs, "prompt": "different prompt"}}
    )
    with pytest.raises(ValueError, match="reused"):
        await service.submit(conflicting)


@pytest.mark.asyncio
async def test_invalid_input_is_rejected_before_queueing() -> None:
    service = ComfyUIBridgeService(
        WorkflowRegistry(MANIFEST), DeterministicMockComfyUIBackend()
    )
    payload = text_to_image_request("fixture-request-invalid").model_copy(
        update={"inputs": {"prompt": "missing seed and aspect ratio"}}
    )
    with pytest.raises(Exception, match="required"):
        await service.submit(payload)


@pytest.mark.asyncio
async def test_cancelled_job_can_be_retried() -> None:
    service = ComfyUIBridgeService(
        WorkflowRegistry(MANIFEST), DeterministicMockComfyUIBackend(delay_seconds=0.05)
    )
    job = await service.submit(text_to_image_request("fixture-request-cancel"))
    cancelled = await service.cancel(job.job_id)
    assert cancelled.status == "cancelled"
    retried = await service.retry(job.job_id)
    assert retried.retry_count == 1
    result = await wait_terminal(service, job.job_id)
    assert result.status == "succeeded"


@pytest.mark.asyncio
async def test_timeout_is_terminal_and_retryable() -> None:
    registry = WorkflowRegistry(MANIFEST)
    registry.get("npd-text-to-image-v1").timeout_seconds = 0.005
    backend = DeterministicMockComfyUIBackend(delay_seconds=0.02)
    service = ComfyUIBridgeService(registry, backend)
    job = await service.submit(text_to_image_request("fixture-request-timeout"))
    timed_out = await wait_terminal(service, job.job_id)
    assert timed_out.status == "timed_out"
    assert timed_out.error_code == "TIMEOUT"
    registry.get("npd-text-to-image-v1").timeout_seconds = 1
    retried = await service.retry(job.job_id)
    assert retried.retry_count == 1
    assert (await wait_terminal(service, job.job_id)).status == "succeeded"


@pytest.mark.asyncio
async def test_failed_job_can_retry_without_changing_workflow_contract() -> None:
    backend = DeterministicMockComfyUIBackend(delay_seconds=0.001, fail=True)
    service = ComfyUIBridgeService(WorkflowRegistry(MANIFEST), backend)
    job = await service.submit(text_to_image_request("fixture-request-failure"))
    failed = await wait_terminal(service, job.job_id)
    assert failed.status == "failed"
    assert failed.error_code == "EXECUTION_FAILED"
    backend.fail = False
    await service.retry(job.job_id)
    result = await wait_terminal(service, job.job_id)
    assert result.status == "succeeded"
    assert result.workflow_version == "1.0.0"


def load_bridge_app(monkeypatch, *, execution_enabled: bool):
    monkeypatch.setenv("COMFYUI_WORKFLOW_MANIFEST", str(MANIFEST))
    monkeypatch.setenv("COMFYUI_EXECUTION_ENABLED", str(execution_enabled).lower())
    monkeypatch.setenv("COMFYUI_BACKEND", "mock" if execution_enabled else "disabled")
    monkeypatch.setenv("APP_ENV", "development")
    sys.modules.pop("npd_comfyui_bridge.main", None)
    return importlib.import_module("npd_comfyui_bridge.main").app


@pytest.mark.asyncio
async def test_bridge_http_contract_reports_disabled_backend(monkeypatch) -> None:
    bridge_app = load_bridge_app(monkeypatch, execution_enabled=False)
    async with AsyncClient(transport=ASGITransport(app=bridge_app), base_url="http://test") as client:
        assert (await client.get("/healthz")).json() == {
            "status": "ok",
            "backend_configured": False,
        }
        ready = await client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json() == {
            "status": "not_configured",
            "execution_enabled": False,
            "approved_workflows": 8,
        }
        rejected = await client.post("/v1/jobs", json=text_to_image_request().model_dump(mode="json"))
        assert rejected.status_code == 503
        assert rejected.json()["detail"]["error"]["code"] == "COMFYUI_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_bridge_http_contract_queues_allowlisted_mock(monkeypatch) -> None:
    bridge_app = load_bridge_app(monkeypatch, execution_enabled=True)
    async with AsyncClient(transport=ASGITransport(app=bridge_app), base_url="http://test") as client:
        response = await client.post(
            "/v1/jobs", json=text_to_image_request("fixture-request-http").model_dump(mode="json")
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        for _ in range(100):
            result = await client.get(f"/v1/jobs/{job_id}")
            assert result.status_code == 200
            if result.json()["status"] == "succeeded":
                break
            await asyncio.sleep(0.005)
        else:
            raise AssertionError("mock bridge HTTP job did not finish")
        assert result.json()["result"]["fixture"] is True
