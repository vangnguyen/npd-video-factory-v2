from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from html import escape
from typing import Any, Protocol,Callable,Awaitable

import httpx
from .media_generation_scope import current_generation_scope
from .media_generation_routes import generation_envelope, workflow_routes

from .media_intelligence_models import (
    ImageGenerationInput,
    StockMediaCandidateRead,
    VideoGenerationInput,
)


class MediaProviderNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderMaterializedMedia:
    filename: str
    content_type: str
    payload: bytes
    provider_job_id: str | None
    source_type: str
    rights_status: str
    license: str
    license_url: str | None
    provider_asset_id: str | None
    creator: str | None
    source_reference: str
    attribution_requirement: str | None
    width: int | None
    height: int | None
    duration_seconds: float | None
    orientation: str
    production_eligible: bool
    estimated_cost_vnd: Decimal | None
    actual_cost_vnd: Decimal | None
    external_call: bool
    paid: bool
    real_provider_tested: bool
    generation_provenance: dict[str, Any]


class StockMediaProvider(Protocol):
    key: str
    configured: bool
    external: bool
    paid: bool
    real_provider_tested: bool

    async def search_images(self, query: str, *, orientation: str, limit: int) -> list[StockMediaCandidateRead]: ...
    async def search_videos(self, query: str, *, orientation: str, limit: int) -> list[StockMediaCandidateRead]: ...
    async def get_asset(self, provider_asset_id: str) -> StockMediaCandidateRead: ...
    async def download_asset(self, candidate: StockMediaCandidateRead) -> ProviderMaterializedMedia: ...


class ImageGenerationProvider(Protocol):
    key: str
    model: str
    configured: bool
    external: bool
    paid: bool
    real_provider_tested: bool

    async def estimate_cost(self, payload: ImageGenerationInput) -> Decimal | None: ...
    async def generate(self, payload: ImageGenerationInput) -> ProviderMaterializedMedia: ...


class VideoGenerationProvider(Protocol):
    key: str
    model: str
    configured: bool
    external: bool
    paid: bool
    real_provider_tested: bool

    async def estimate_cost(self, payload: VideoGenerationInput) -> Decimal | None: ...
    async def generate(self, payload: VideoGenerationInput) -> ProviderMaterializedMedia: ...


def _stable_token(*parts: object, length: int = 16) -> str:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


class DeterministicStockMediaProvider:
    """Synthetic, copyright-safe stock contract fixture for local and CI use only."""

    key = "fixture-stock"
    configured = True
    external = False
    paid = False
    real_provider_tested = False

    def __init__(self) -> None:
        self._assets: dict[str, StockMediaCandidateRead] = {}

    async def search_images(
        self, query: str, *, orientation: str, limit: int
    ) -> list[StockMediaCandidateRead]:
        return self._search(query, orientation=orientation, media_type="image", limit=limit)

    async def search_videos(
        self, query: str, *, orientation: str, limit: int
    ) -> list[StockMediaCandidateRead]:
        return self._search(query, orientation=orientation, media_type="video", limit=limit)

    def _search(
        self, query: str, *, orientation: str, media_type: str, limit: int
    ) -> list[StockMediaCandidateRead]:
        normalized = " ".join(query.split())[:500]
        results: list[StockMediaCandidateRead] = []
        for ordinal in range(max(1, min(limit, 5))):
            asset_id = f"fixture-{media_type}-{_stable_token(normalized, orientation, ordinal)}"
            portrait = orientation == "portrait"
            square = orientation == "square"
            width = 1080 if portrait or square else 1920
            height = 1080 if square else (1920 if portrait else 1080)
            candidate = StockMediaCandidateRead(
                candidate_id=f"smc_{_stable_token(asset_id, 'candidate', length=24)}",
                provider=self.key,
                provider_asset_id=asset_id,
                creator="NPD deterministic fixture",
                source_reference=f"fixture://licensed-stock/{asset_id}",
                license="CC0-1.0 synthetic fixture",
                license_url="https://creativecommons.org/publicdomain/zero/1.0/",
                attribution_requirement=None,
                width=width,
                height=height,
                duration_seconds=5.0 if media_type == "video" else None,
                orientation=orientation if orientation in {"portrait", "landscape", "square"} else "unknown",
                media_type=media_type,
                semantic_score=round(max(0.55, 0.92 - ordinal * 0.08), 4),
                rights_status="licensed",
                production_eligible=False,
                estimated_cost_vnd=Decimal("0"),
                provenance={
                    "fixture": True,
                    "synthetic": True,
                    "external_call": False,
                    "paid": False,
                    "authorized_source": True,
                    "social_media_downloaded": False,
                    "real_provider_tested": False,
                    "query": normalized,
                },
            )
            self._assets[asset_id] = candidate
            results.append(candidate)
        return results

    async def get_asset(self, provider_asset_id: str) -> StockMediaCandidateRead:
        try:
            return self._assets[provider_asset_id]
        except KeyError as exc:
            raise KeyError(f"stock fixture asset not found: {provider_asset_id}") from exc

    async def download_asset(self, candidate: StockMediaCandidateRead) -> ProviderMaterializedMedia:
        if candidate.provider != self.key:
            raise ValueError("stock candidate belongs to a different provider")
        if candidate.media_type == "image":
            payload = _fixture_svg(
                title="Licensed stock fixture",
                subtitle=candidate.provenance.get("query", candidate.provider_asset_id),
                width=candidate.width or 1080,
                height=candidate.height or 1920,
            )
            filename = f"{candidate.provider_asset_id}.svg"
            content_type = "image/svg+xml"
        else:
            payload = json.dumps(
                {
                    "fixture": True,
                    "media_type": "video",
                    "provider_asset_id": candidate.provider_asset_id,
                    "duration_seconds": candidate.duration_seconds,
                    "notice": "Contract fixture only; not a playable production video.",
                },
                sort_keys=True,
            ).encode("utf-8")
            filename = f"{candidate.provider_asset_id}.video-fixture.json"
            content_type = "application/vnd.npd.video-fixture+json"
        return ProviderMaterializedMedia(
            filename=filename,
            content_type=content_type,
            payload=payload,
            provider_job_id=None,
            source_type="stock",
            rights_status="licensed",
            license=candidate.license,
            license_url=candidate.license_url,
            provider_asset_id=candidate.provider_asset_id,
            creator=candidate.creator,
            source_reference=candidate.source_reference,
            attribution_requirement=candidate.attribution_requirement,
            width=candidate.width,
            height=candidate.height,
            duration_seconds=candidate.duration_seconds,
            orientation=candidate.orientation,
            production_eligible=False,
            estimated_cost_vnd=Decimal("0"),
            actual_cost_vnd=Decimal("0"),
            external_call=False,
            paid=False,
            real_provider_tested=False,
            generation_provenance={
                "fixture": True,
                "synthetic": True,
                "real_provider_tested": False,
                "playable_video": candidate.media_type != "video",
            },
        )


class ContractOnlyStockMediaProvider:
    key = "stock-not-configured"
    configured = False
    external = True
    paid = False
    real_provider_tested = False

    async def search_images(self, query: str, *, orientation: str, limit: int) -> list[StockMediaCandidateRead]:
        raise MediaProviderNotConfigured("Stock media provider is not configured")

    async def search_videos(self, query: str, *, orientation: str, limit: int) -> list[StockMediaCandidateRead]:
        raise MediaProviderNotConfigured("Stock media provider is not configured")

    async def get_asset(self, provider_asset_id: str) -> StockMediaCandidateRead:
        raise MediaProviderNotConfigured("Stock media provider is not configured")

    async def download_asset(self, candidate: StockMediaCandidateRead) -> ProviderMaterializedMedia:
        raise MediaProviderNotConfigured("Stock media provider is not configured")


class DeterministicImageGenerationProvider:
    key = "fixture-image-generation"
    model = "deterministic-svg-v2-06"
    configured = True
    external = False
    paid = False
    real_provider_tested = False

    async def estimate_cost(self, payload: ImageGenerationInput) -> Decimal:
        return Decimal("0")

    async def generate(self, payload: ImageGenerationInput) -> ProviderMaterializedMedia:
        token = _stable_token(payload.model_dump_json())
        width, height = _aspect_dimensions(payload.aspect_ratio)
        content = _fixture_svg(
            title="AI image fixture",
            subtitle=payload.prompt,
            width=width,
            height=height,
        )
        return ProviderMaterializedMedia(
            filename=f"ai-image-{token}.svg",
            content_type="image/svg+xml",
            payload=content,
            provider_job_id=f"img_fixture_{token}",
            source_type="ai_generated",
            rights_status="verified",
            license="NPD synthetic fixture",
            license_url=None,
            provider_asset_id=f"img_fixture_{token}",
            creator="NPD deterministic generator",
            source_reference=f"fixture://ai-image/{token}",
            attribution_requirement=None,
            width=width,
            height=height,
            duration_seconds=None,
            orientation=_orientation(payload.aspect_ratio),
            production_eligible=False,
            estimated_cost_vnd=Decimal("0"),
            actual_cost_vnd=Decimal("0"),
            external_call=False,
            paid=False,
            real_provider_tested=False,
            generation_provenance={
                "provider": self.key,
                "model": self.model,
                "workflow": payload.operation,
                "seed": payload.seed,
                "prompt": payload.prompt,
                "negative_prompt": payload.negative_prompt,
                "style": payload.style,
                "quality": payload.quality,
                "fixture": True,
                "real_provider_tested": False,
            },
        )


class DeterministicVideoGenerationProvider:
    key = "fixture-video-generation"
    model = "deterministic-video-contract-v2-06"
    configured = True
    external = False
    paid = False
    real_provider_tested = False

    async def estimate_cost(self, payload: VideoGenerationInput) -> Decimal:
        return Decimal("0")

    async def generate(self, payload: VideoGenerationInput) -> ProviderMaterializedMedia:
        token = _stable_token(payload.model_dump_json())
        width, height = _aspect_dimensions(payload.aspect_ratio)
        content = json.dumps(
            {
                "fixture": True,
                "provider": self.key,
                "model": self.model,
                "mode": payload.mode,
                "prompt": payload.prompt,
                "negative_prompt": payload.negative_prompt,
                "reference_images": payload.reference_images,
                "duration_seconds": payload.duration_seconds,
                "aspect_ratio": payload.aspect_ratio,
                "seed": payload.seed,
                "notice": "Contract fixture only; not a playable production video.",
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        return ProviderMaterializedMedia(
            filename=f"ai-video-{token}.fixture.json",
            content_type="application/vnd.npd.video-generation-fixture+json",
            payload=content,
            provider_job_id=f"vid_fixture_{token}",
            source_type="ai_generated",
            rights_status="verified",
            license="NPD synthetic fixture",
            license_url=None,
            provider_asset_id=f"vid_fixture_{token}",
            creator="NPD deterministic generator",
            source_reference=f"fixture://ai-video/{token}",
            attribution_requirement=None,
            width=width,
            height=height,
            duration_seconds=payload.duration_seconds,
            orientation=_orientation(payload.aspect_ratio),
            production_eligible=False,
            estimated_cost_vnd=Decimal("0"),
            actual_cost_vnd=Decimal("0"),
            external_call=False,
            paid=False,
            real_provider_tested=False,
            generation_provenance={
                "provider": self.key,
                "model": self.model,
                "workflow": payload.mode,
                "seed": payload.seed,
                "prompt": payload.prompt,
                "fixture": True,
                "playable_video": False,
                "real_provider_tested": False,
            },
        )


class ContractOnlyImageGenerationProvider:
    key = "image-generation-not-configured"
    model = "not-configured"
    configured = False
    external = True
    paid = True
    real_provider_tested = False

    async def estimate_cost(self, payload: ImageGenerationInput) -> Decimal | None:
        return None

    async def generate(self, payload: ImageGenerationInput) -> ProviderMaterializedMedia:
        raise MediaProviderNotConfigured("Image generation provider is not configured")


class ContractOnlyVideoGenerationProvider:
    key = "video-generation-not-configured"
    model = "not-configured"
    configured = False
    external = True
    paid = True
    real_provider_tested = False

    async def estimate_cost(self, payload: VideoGenerationInput) -> Decimal | None:
        return None

    async def generate(self, payload: VideoGenerationInput) -> ProviderMaterializedMedia:
        raise MediaProviderNotConfigured("Video generation provider is not configured")


class ComfyUIBridgeGenerationProvider:
    """REST adapter to the allowlisted ComfyUI bridge. Disabled unless explicitly configured."""

    external = True
    paid = False
    real_provider_tested = False

    def __init__(
        self,
        *,
        bridge_url: str,
        modality: str,
        workflow_id: str,
        enabled: bool,
        timeout_seconds: float = 300,
        transport: httpx.AsyncBaseTransport | None = None,
        service_token: str = '',
        workflow_overrides: dict[str, str] | None = None,
        on_job:Callable[[dict[str,Any]],Awaitable[None]]|None=None,
        cancel_requested:Callable[[],bool]|None=None,
    ) -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self.modality = modality
        self.workflow_id = workflow_id
        self.workflow_routes = workflow_routes(modality, workflow_id, workflow_overrides)
        if service_token and (not 32 <= len(service_token) <= 8192 or any(c.isspace() for c in service_token)):
            raise ValueError('COMFYUI_SERVICE_TOKEN_INVALID')
        self._service_token = service_token
        self.configured = enabled and bool(self.bridge_url) and bool(service_token)
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.key = f"comfyui-{modality}"
        self.model = f"workflow:{workflow_id}"
        if (on_job is not None and not callable(on_job)) or (cancel_requested is not None and not callable(cancel_requested)):
            raise ValueError('COMFYUI_LIFECYCLE_HOOK_INVALID')
        self.on_job,self.cancel_requested=on_job,cancel_requested

    async def estimate_cost(self, payload: ImageGenerationInput | VideoGenerationInput) -> Decimal | None:
        return None # GPU compute cost requires configured accounting; absence is not zero.

    async def generate(self, payload: ImageGenerationInput | VideoGenerationInput) -> ProviderMaterializedMedia:
        return await self._run(payload)

    async def reconcile(self, payload: ImageGenerationInput | VideoGenerationInput, *, provider_job_id=None) -> ProviderMaterializedMedia:
        """Read an existing bound job; never resubmit or authorize bridge retry."""
        return await self._run(payload,reconcile=True,provider_job_id=provider_job_id)

    async def _run(self, payload: ImageGenerationInput | VideoGenerationInput, *, reconcile=False, provider_job_id=None) -> ProviderMaterializedMedia:
        if not self.configured:
            raise MediaProviderNotConfigured("ComfyUI bridge execution is not configured")
        from .comfyui_generation_lifecycle import cancellation_requested,observe
        if not reconcile and cancellation_requested(self.cancel_requested):raise RuntimeError('COMFYUI_CANCELLED_BEFORE_SUBMISSION')
        workspace_id, project_id, resolution_job_id = current_generation_scope()
        workflow_id, operation, inputs = generation_envelope(self.modality, payload, self.workflow_routes)
        bound_project = project_id if any(str(value).startswith('vf-reference://') for value in
            [*inputs.get('reference_images', []), inputs.get('mask_reference') or '']) else None
        started = asyncio.get_running_loop().time()
        binary_content, binary_metadata = None, None
        timeout = httpx.Timeout(self.timeout_seconds, connect=10)
        async with httpx.AsyncClient(
            base_url=self.bridge_url,
            timeout=timeout,
            transport=self.transport,
            headers={'Authorization': 'Bearer ' + self._service_token, 'X-VF-Workspace-Id': workspace_id},
            trust_env=False,
            follow_redirects=False,
        ) as client:
            request = {
                    "workflow_id": workflow_id,
                    "workspace_id": workspace_id,
                    **({'project_id': bound_project} if bound_project is not None else {}),
                    "inputs": inputs,
                    "client_request_id": _stable_token(workspace_id, project_id, resolution_job_id, payload.model_dump_json(), workflow_id),
                }
            if reconcile:
                from .comfyui_generation_reconciliation import lookup
                job = await lookup(client,request,provider_job_id=provider_job_id,timeout_seconds=self.timeout_seconds)
            else:
                response = await client.post('/v1/jobs',json=request)
                if response.status_code != 202:
                    raise RuntimeError(f"ComfyUI bridge rejected generation: HTTP {response.status_code}")
                job = response.json()
            job_id = str(job["job_id"])
            if (not re.fullmatch(r'cui_[A-Za-z0-9_-]{1,80}', job_id) or job.get('workspace_id') != workspace_id or
                    job.get('workflow_id') != workflow_id or bound_project is not None and job.get('project_id') != bound_project):
                raise ValueError('COMFYUI_JOB_BINDING_INVALID')
            await observe(self.on_job,job,'reconciled' if reconcile else 'submitted')
            deadline = asyncio.get_running_loop().time() + self.timeout_seconds
            cancel_sent=False
            while job.get("status") not in {"succeeded", "failed", "cancelled", "timed_out"}:
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError("ComfyUI bridge generation timed out")
                if not cancel_sent and cancellation_requested(self.cancel_requested):
                    # Target the persisted job only. No global interrupt or write retry.
                    await observe(self.on_job,job,'cancel_requested')
                    cancel_sent=True
                    cancelled=await client.post(f'/v1/jobs/{job_id}/cancel')
                    if cancelled.status_code!=200:raise RuntimeError('COMFYUI_TARGETED_CANCEL_HTTP_FAILED')
                    job=cancelled.json()
                    if (job.get('job_id')!=job_id or job.get('workspace_id')!=workspace_id or job.get('workflow_id')!=workflow_id
                            or bound_project is not None and job.get('project_id') != bound_project):
                        raise ValueError('COMFYUI_JOB_BINDING_INVALID')
                    await observe(self.on_job,job,'cancel_response')
                    if job.get('status') in {'succeeded','failed','cancelled','timed_out'}:break
                await asyncio.sleep(0.25)
                poll = await client.get(f"/v1/jobs/{job_id}")
                poll.raise_for_status()
                job = poll.json()
                if (job.get('job_id') != job_id or job.get('workspace_id') != workspace_id or
                        job.get('workflow_id') != workflow_id or bound_project is not None and job.get('project_id') != bound_project):
                    raise ValueError('COMFYUI_JOB_BINDING_INVALID')
                await observe(self.on_job,job,'polled')
            if job.get('status') == 'succeeded' and str((job.get('result') or {}).get('artifact_reference', '')).startswith('vf-artifact://'):
                from .comfyui_binary_result import registered_binary
                binary_content, binary_metadata = await registered_binary(client, job=job, workspace_id=workspace_id,
                    workflow_id=workflow_id, modality=self.modality, inputs=inputs, timeout_seconds=self.timeout_seconds)
        if job.get("status") != "succeeded":
            safe_code = job.get('error_code')
            if safe_code not in {'CANCELLED', 'TIMEOUT', 'EXECUTION_FAILED', 'RECOVERY_REQUIRED'}:
                safe_code = 'BRIDGE_FAILURE'
            raise RuntimeError(f"ComfyUI bridge generation failed: {safe_code}")
        result = job.get("result") or {}
        artifact_reference = str(result.get("artifact_reference") or f"comfyui://{job_id}")
        content = json.dumps(
            {
                "bridge_job_id": job_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "resolution_job_id": resolution_job_id,
                "artifact_reference": artifact_reference,
                "workflow_id": workflow_id,
                "notice": "Bridge artifact reference; binary registration is performed by the GPU deployment.",
            },
            sort_keys=True,
        ).encode("utf-8")
        media_type = "image" if self.modality == "image" else "video"
        extension = {'image/png': 'png', 'image/jpeg': 'jpg', 'video/mp4': 'mp4'}.get(binary_metadata['mime_type']) if binary_metadata else 'json'
        media = binary_metadata['media'] if binary_metadata else result
        return ProviderMaterializedMedia(
            filename=f"comfyui-{media_type}-{job_id}.{extension}",
            content_type=binary_metadata['mime_type'] if binary_metadata else "application/vnd.npd.comfyui-result+json",
            payload=binary_content if binary_metadata else content,
            provider_job_id=job_id,
            source_type="ai_generated",
            rights_status="unknown",
            license="provider-terms-review-required",
            license_url=None,
            provider_asset_id=job_id,
            creator="ComfyUI workflow",
            source_reference=artifact_reference,
            attribution_requirement=None,
            width=media.get("width"),
            height=media.get("height"),
            duration_seconds=media.get("duration_seconds"),
            orientation=('square' if media['width'] == media['height'] else 'landscape' if media['width'] > media['height'] else 'portrait') if binary_metadata else "unknown",
            production_eligible=False,
            estimated_cost_vnd=None,
            actual_cost_vnd=None,
            external_call=True,
            paid=False,
            real_provider_tested=False,
            generation_provenance={
                "provider": self.key,
                "model": f'workflow:{workflow_id}',
                "workflow": workflow_id,
                "workflow_version": job.get('workflow_version'),
                "operation": operation,
                "requested_operation": payload.operation if isinstance(payload, ImageGenerationInput) else payload.mode,
                "seed": payload.seed,
                "reference_images": payload.reference_images,
                "mask_reference": payload.mask_reference if isinstance(payload, ImageGenerationInput) else None,
                "upscale_factor": payload.upscale_factor if isinstance(payload, ImageGenerationInput) else None,
                "generation_time_seconds": round(asyncio.get_running_loop().time() - started, 6),
                "generation_time_basis": 'local adapter elapsed; not measured GPU execution',
                "bridge_job_id": job_id,
                "prompt": payload.prompt,
                "real_provider_tested": False,
                "gpu_compute_cost_verified": False,
                "fixture": bool(result.get('fixture')) or isinstance(self.transport, httpx.MockTransport),
                "mock_transport_used": isinstance(self.transport, httpx.MockTransport),
                "binary_artifact_registered": binary_metadata is not None,
                "registered_artifact": binary_metadata,
            },
        )


def _aspect_dimensions(aspect_ratio: str) -> tuple[int, int]:
    return {
        "9:16": (1080, 1920),
        "16:9": (1920, 1080),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350),
    }[aspect_ratio]


def _orientation(aspect_ratio: str) -> str:
    if aspect_ratio == "1:1":
        return "square"
    return "landscape" if aspect_ratio == "16:9" else "portrait"


def _fixture_svg(*, title: str, subtitle: str, width: int, height: int) -> bytes:
    safe_title = escape(title[:120])
    safe_subtitle = escape(" ".join(subtitle.split())[:180])
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#14213d"/>
<circle cx="{width * 0.72:.0f}" cy="{height * 0.28:.0f}" r="{min(width, height) * 0.18:.0f}" fill="#fca311" opacity="0.85"/>
<text x="{width * 0.08:.0f}" y="{height * 0.58:.0f}" fill="#ffffff" font-size="{max(28, width // 18)}" font-family="Arial, sans-serif" font-weight="700">{safe_title}</text>
<text x="{width * 0.08:.0f}" y="{height * 0.66:.0f}" fill="#e5e5e5" font-size="{max(18, width // 32)}" font-family="Arial, sans-serif">{safe_subtitle}</text>
</svg>"""
    return svg.encode("utf-8")
