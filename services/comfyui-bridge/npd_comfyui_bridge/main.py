from __future__ import annotations

import os
import hmac
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.responses import Response
import hashlib

from .runtime import select_backend
from .models import BridgeJobCreate, BridgeJobRead
from .service import ComfyUIBridgeService
from .job_store import SQLiteBridgeJobStore
from .workflows import WorkflowRegistry
from .binary_artifacts import ArtifactError, BinaryArtifactStore, FFmpegMediaValidator


manifest_path = Path(
    os.getenv("COMFYUI_WORKFLOW_MANIFEST", "/workspace/workflows/comfyui/manifest.json")
)
backend_name = os.getenv("COMFYUI_BACKEND", "disabled").casefold()
execution_enabled = os.getenv("COMFYUI_EXECUTION_ENABLED", "false").casefold() == "true"
app_env = os.getenv("APP_ENV", "development").casefold()
if app_env == "production" and backend_name == "mock":
    raise RuntimeError("mock ComfyUI backend is prohibited in production")
registry = WorkflowRegistry(manifest_path)
service_token = os.getenv('COMFYUI_BRIDGE_TOKEN', '')
if service_token and (len(service_token) < 32 or len(service_token) > 8192 or any(c.isspace() for c in service_token)):
    raise RuntimeError('COMFYUI_BRIDGE_TOKEN_INVALID')
job_store = SQLiteBridgeJobStore(Path(os.getenv('COMFYUI_JOB_STORE_PATH', '/workspace/storage/comfyui-bridge/jobs.sqlite3')))
try:
    artifacts = BinaryArtifactStore(
        Path(os.getenv('COMFYUI_ARTIFACT_ROOT', '/workspace/storage/comfyui-bridge/artifacts')),
        validator=FFmpegMediaValidator(ffmpeg=os.getenv('COMFYUI_FFMPEG_PATH'), ffprobe=os.getenv('COMFYUI_FFPROBE_PATH')))
    backend = select_backend(environment=os.environ, registry=registry, job_store=job_store, artifacts=artifacts)
    service = ComfyUIBridgeService(registry, backend, job_store=job_store,
        max_concurrent_jobs=int(os.getenv('COMFYUI_MAX_CONCURRENT_JOBS', '1')),
        max_queued_jobs=int(os.getenv('COMFYUI_MAX_QUEUED_JOBS', '32')),
        max_retries=int(os.getenv('COMFYUI_MAX_RETRIES', '3')))
except Exception:
    job_store.close()
    raise


@asynccontextmanager
async def lifespan(_app):
    try:
        yield
    finally:
        await service.close()


app = FastAPI(title="NPD ComfyUI Bridge", version="0.2.0", lifespan=lifespan)
app.state.bridge_service = service
app.state.binary_artifact_store = artifacts


async def require_service(authorization: str | None = Header(default=None),
                          x_vf_workspace_id: str | None = Header(default=None)):
    if not service_token:
        raise HTTPException(503, detail={'error': {'code': 'BRIDGE_AUTH_NOT_CONFIGURED'}})
    if not authorization or not hmac.compare_digest(authorization.encode(), ('Bearer ' + service_token).encode()):
        raise HTTPException(401, detail={'error': {'code': 'SERVICE_AUTH_REQUIRED'}})
    if not x_vf_workspace_id or len(x_vf_workspace_id) > 200 or any(c.isspace() for c in x_vf_workspace_id):
        raise HTTPException(422, detail={'error': {'code': 'WORKSPACE_SCOPE_REQUIRED'}})
    return x_vf_workspace_id


async def scoped_job(job_id, workspace_id):
    result = await service.get(job_id)
    if result is None or result.workspace_id != workspace_id:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}})
    return result


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {"status": "ok", "backend_configured": backend.configured}


@app.get("/readyz")
async def readyz() -> dict[str, object]:
    return {
        "status": "ready" if backend.configured and service_token else "not_configured",
        "execution_enabled": execution_enabled,
        "approved_workflows": len(registry.manifest.workflows),
    }


@app.post("/v1/jobs", response_model=BridgeJobRead, status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_service)])
async def submit(payload: BridgeJobCreate, workspace_id: str = Depends(require_service)) -> BridgeJobRead:
    if payload.workspace_id != workspace_id:
        raise HTTPException(422, detail={'error': {'code': 'WORKSPACE_SCOPE_MISMATCH'}})
    try:
        return await service.submit(payload)
    except KeyError as exc:
        raise HTTPException(404, detail={"error": {"code": "WORKFLOW_NOT_APPROVED"}}) from exc
    except RuntimeError as exc:
        code = str(exc) if str(exc) in {'BRIDGE_QUEUE_FULL', 'BRIDGE_SHUTTING_DOWN', 'BRIDGE_STORE_LIMIT_REACHED'} else 'COMFYUI_NOT_CONFIGURED'
        raise HTTPException(503, detail={"error": {"code": code}}) from exc
    except Exception as exc:
        raise HTTPException(422, detail={"error": {"code": "INVALID_WORKFLOW_INPUT"}}) from exc


@app.get('/v1/jobs', response_model=list[BridgeJobRead], dependencies=[Depends(require_service)])
async def list_jobs(limit: int = Query(default=100, ge=1, le=200), workspace_id: str = Depends(require_service)):
    return await service.list_jobs(limit=limit, workspace_id=workspace_id)


@app.get('/v1/jobs/{job_id}/events', dependencies=[Depends(require_service)])
async def job_events(job_id: str, workspace_id: str = Depends(require_service)):
    await scoped_job(job_id, workspace_id)
    try:
        return await service.events(job_id)
    except KeyError as exc:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}}) from exc


@app.get("/v1/jobs/{job_id}", response_model=BridgeJobRead, dependencies=[Depends(require_service)])
async def get_job(job_id: str, workspace_id: str = Depends(require_service)) -> BridgeJobRead:
    return await scoped_job(job_id, workspace_id)


async def scoped_artifact(job_id, artifact_id, workspace_id):
    job = await scoped_job(job_id, workspace_id)
    result = job.result or {}
    if job.status != 'succeeded' or result.get('artifact_reference') != 'vf-artifact://' + artifact_id:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}})
    try:
        registered = app.state.binary_artifact_store.read(workspace_id=workspace_id, job_id=job_id, artifact_id=artifact_id)
        document = registered.document
        if (document['checksum_sha256'] != result.get('checksum_sha256')
                or document['provenance']['workflow_id'] != job.workflow_id
                or document['provenance']['workflow_version'] != job.workflow_version
                or document['fixture'] != result.get('fixture')):
            raise ArtifactError('ARTIFACT_JOB_BINDING_INVALID')
        return registered
    except ArtifactError:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}}) from None


@app.get('/v1/jobs/{job_id}/artifacts/{artifact_id}/metadata', dependencies=[Depends(require_service)])
async def artifact_metadata(job_id: str, artifact_id: str, workspace_id: str = Depends(require_service)):
    registered = await scoped_artifact(job_id, artifact_id, workspace_id)
    return registered.document


@app.get('/v1/jobs/{job_id}/artifacts/{artifact_id}', dependencies=[Depends(require_service)])
async def download_artifact(job_id: str, artifact_id: str, workspace_id: str = Depends(require_service)):
    registered = await scoped_artifact(job_id, artifact_id, workspace_id)
    content = registered.path.read_bytes()
    if hashlib.sha256(content).hexdigest() != registered.document['checksum_sha256']:
        raise HTTPException(404, detail={'error': {'code': 'NOT_FOUND'}})
    return Response(content=content, media_type=registered.document['mime_type'], headers={
        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store',
        'Content-Disposition': 'attachment; filename="' + registered.path.name + '"',
        'X-VF-Content-SHA256': registered.document['checksum_sha256']})


@app.post("/v1/jobs/{job_id}/cancel", response_model=BridgeJobRead, dependencies=[Depends(require_service)])
async def cancel(job_id: str, workspace_id: str = Depends(require_service)) -> BridgeJobRead:
    await scoped_job(job_id, workspace_id)
    try:
        return await service.cancel(job_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "Job not found."}}) from exc


@app.post("/v1/jobs/{job_id}/retry", response_model=BridgeJobRead, dependencies=[Depends(require_service)])
async def retry(job_id: str, workspace_id: str = Depends(require_service)) -> BridgeJobRead:
    await scoped_job(job_id, workspace_id)
    try:
        return await service.retry(job_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "Job not found."}}) from exc
    except ValueError as exc:
        raise HTTPException(409, detail={"error": {"code": "INVALID_JOB_STATE"}}) from exc
    except RuntimeError as exc:
        raise HTTPException(503, detail={"error": {"code": "COMFYUI_NOT_CONFIGURED"}}) from exc
