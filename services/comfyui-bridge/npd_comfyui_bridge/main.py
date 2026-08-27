from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, status

from .backend import DeterministicMockComfyUIBackend, DisabledComfyUIBackend
from .models import BridgeJobCreate, BridgeJobRead
from .service import ComfyUIBridgeService
from .workflows import WorkflowRegistry


manifest_path = Path(
    os.getenv("COMFYUI_WORKFLOW_MANIFEST", "/workspace/workflows/comfyui/manifest.json")
)
backend_name = os.getenv("COMFYUI_BACKEND", "disabled").casefold()
execution_enabled = os.getenv("COMFYUI_EXECUTION_ENABLED", "false").casefold() == "true"
app_env = os.getenv("APP_ENV", "development").casefold()
if app_env == "production" and backend_name == "mock":
    raise RuntimeError("mock ComfyUI backend is prohibited in production")
registry = WorkflowRegistry(manifest_path)
backend = (
    DeterministicMockComfyUIBackend()
    if execution_enabled and backend_name == "mock"
    else DisabledComfyUIBackend()
)
service = ComfyUIBridgeService(registry, backend)
app = FastAPI(title="NPD ComfyUI Bridge", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {"status": "ok", "backend_configured": backend.configured}


@app.get("/readyz")
async def readyz() -> dict[str, object]:
    return {
        "status": "ready" if backend.configured else "not_configured",
        "execution_enabled": execution_enabled,
        "approved_workflows": len(registry.manifest.workflows),
    }


@app.post("/v1/jobs", response_model=BridgeJobRead, status_code=status.HTTP_202_ACCEPTED)
async def submit(payload: BridgeJobCreate) -> BridgeJobRead:
    try:
        return await service.submit(payload)
    except KeyError as exc:
        raise HTTPException(404, detail={"error": {"code": "WORKFLOW_NOT_APPROVED", "message": str(exc)}}) from exc
    except RuntimeError as exc:
        raise HTTPException(503, detail={"error": {"code": "COMFYUI_NOT_CONFIGURED", "message": str(exc)}}) from exc
    except Exception as exc:
        raise HTTPException(422, detail={"error": {"code": "INVALID_WORKFLOW_INPUT", "message": str(exc)}}) from exc


@app.get("/v1/jobs/{job_id}", response_model=BridgeJobRead)
async def get_job(job_id: str) -> BridgeJobRead:
    result = await service.get(job_id)
    if result is None:
        raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "Job not found."}})
    return result


@app.post("/v1/jobs/{job_id}/cancel", response_model=BridgeJobRead)
async def cancel(job_id: str) -> BridgeJobRead:
    try:
        return await service.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "Job not found."}}) from exc


@app.post("/v1/jobs/{job_id}/retry", response_model=BridgeJobRead)
async def retry(job_id: str) -> BridgeJobRead:
    try:
        return await service.retry(job_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "Job not found."}}) from exc
    except ValueError as exc:
        raise HTTPException(409, detail={"error": {"code": "INVALID_JOB_STATE", "message": str(exc)}}) from exc
    except RuntimeError as exc:
        raise HTTPException(503, detail={"error": {"code": "COMFYUI_NOT_CONFIGURED", "message": str(exc)}}) from exc
