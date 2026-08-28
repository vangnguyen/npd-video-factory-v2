from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol

import httpx
from pydantic import Field, ValidationError, model_validator

from .auto_edit_models import MediaMetadata, SceneRead
from .models import StrictModel
from .provider_safety import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderTransientError,
)
from .vision_models import NormalizedBox
from .vision_providers import (
    ProviderObjectDetection,
    ProviderOCRDetection,
    ProviderVisionFrame,
    ProviderVisionResult,
    VisionProviderNotConfigured,
)


_SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
_CATEGORY = Literal["person", "face", "product", "object", "building", "logo", "text"]


class OpenAIVisionResponseError(RuntimeError):
    """A provider response failed the strict, secret-safe contract."""


class VisionFrameExtractionError(RuntimeError):
    """Trusted media could not be converted into bounded Vision input frames."""


class _ObjectOutput(StrictModel):
    label: str = Field(min_length=1, max_length=160)
    category: _CATEGORY
    confidence: float = Field(ge=0, le=1)
    bounding_box: NormalizedBox
    track_hint: str | None = Field(default=None, max_length=120)


class _OCROutput(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    language: str = Field(min_length=2, max_length=16)
    confidence: float = Field(ge=0, le=1)
    bounding_box: NormalizedBox


class _FrameOutput(StrictModel):
    frame_index: int = Field(ge=0, le=31)
    caption: str = Field(min_length=1, max_length=1000)
    scene_description: str = Field(min_length=1, max_length=2000)
    semantic_label: str = Field(min_length=1, max_length=240)
    environment: str = Field(min_length=1, max_length=240)
    action: str = Field(min_length=1, max_length=240)
    objects: list[_ObjectOutput] = Field(max_length=100)
    ocr: list[_OCROutput] = Field(max_length=100)
    primary_subject_box: NormalizedBox | None
    saliency_box: NormalizedBox | None
    headroom_ratio: float = Field(ge=0, le=1)
    visual_balance_score: float = Field(ge=0, le=1)
    safe_crop: bool
    quality_score: float = Field(ge=0, le=1)
    black_frame: bool
    blur_score: float = Field(ge=0, le=1)
    overexposed: bool
    underexposed: bool
    low_resolution: bool
    watermark_or_logo_detected: bool
    frozen_or_duplicate: bool
    quality_issues: list[str] = Field(max_length=40)
    confidence: float = Field(ge=0, le=1)


class _VisionOutput(StrictModel):
    frames: list[_FrameOutput] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_unique_indexes(self) -> "_VisionOutput":
        indexes = [frame.frame_index for frame in self.frames]
        if len(indexes) != len(set(indexes)):
            raise ValueError("frame indexes must be unique")
        return self


@dataclass(frozen=True)
class ExtractedVisionFrame:
    timestamp_seconds: float
    evidence_frame_reference: str
    content_type: str
    payload: bytes
    sha256: str


class VisionFrameExtractor(Protocol):
    async def extract(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        scenes: list[SceneRead],
        asset_id: str,
        sample_interval_seconds: float,
    ) -> tuple[ExtractedVisionFrame, ...]: ...


def _bounded_sample_times(
    duration: float,
    scenes: list[SceneRead],
    interval: float,
    maximum: int,
) -> list[float]:
    if duration <= 0:
        raise VisionFrameExtractionError("video duration must be positive")
    candidates: set[float] = set()
    for scene in scenes:
        midpoint = scene.start_seconds + (scene.end_seconds - scene.start_seconds) / 2
        candidates.add(round(min(duration - 0.001, max(0.0, midpoint)), 3))
    cursor = min(interval / 2, max(0.0, duration - 0.001))
    while cursor < duration and len(candidates) < maximum * 3:
        candidates.add(round(min(duration - 0.001, cursor), 3))
        cursor += interval
    ordered = sorted(value for value in candidates if value >= 0)
    if len(ordered) <= maximum:
        return ordered
    if maximum == 1:
        return [ordered[len(ordered) // 2]]
    selected = {
        ordered[round(index * (len(ordered) - 1) / (maximum - 1))]
        for index in range(maximum)
    }
    return sorted(selected)


class FFmpegVisionFrameExtractor:
    """Extracts bounded JPEG evidence without mutating the trusted source asset."""

    def __init__(
        self,
        executable: str = "ffmpeg",
        *,
        max_frames: int = 8,
        max_image_bytes: int = 4 * 1024 * 1024,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not executable.strip():
            raise ValueError("ffmpeg executable is required")
        if not 1 <= max_frames <= 32:
            raise ValueError("Vision frame limit must be between 1 and 32")
        if not 64 * 1024 <= max_image_bytes <= 20 * 1024 * 1024:
            raise ValueError("Vision image byte limit is outside the supported range")
        if timeout_seconds <= 0:
            raise ValueError("Vision extraction timeout must be positive")
        self.executable = executable
        self.max_frames = max_frames
        self.max_image_bytes = max_image_bytes
        self.timeout_seconds = timeout_seconds

    async def extract(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        scenes: list[SceneRead],
        asset_id: str,
        sample_interval_seconds: float,
    ) -> tuple[ExtractedVisionFrame, ...]:
        if not path.is_file():
            raise FileNotFoundError(path)
        if metadata.media_kind in {"image", "logo"}:
            payload = path.read_bytes()
            content_type = metadata.detected_content_type.lower()
            self._validate_image(payload, content_type)
            return (
                ExtractedVisionFrame(
                    timestamp_seconds=0.0,
                    evidence_frame_reference=f"asset://{asset_id}#frame=0",
                    content_type=content_type,
                    payload=payload,
                    sha256=hashlib.sha256(payload).hexdigest(),
                ),
            )
        if metadata.media_kind != "video":
            raise VisionFrameExtractionError("Vision accepts only trusted image or video media")

        times = _bounded_sample_times(
            float(metadata.duration_seconds or 0),
            scenes,
            sample_interval_seconds,
            self.max_frames,
        )
        frames: list[ExtractedVisionFrame] = []
        for timestamp in times:
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "-v",
                "error",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                "scale='min(1280,iw)':-2",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout_seconds
                )
            except TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise VisionFrameExtractionError("Vision frame extraction timed out") from exc
            if process.returncode != 0:
                raise VisionFrameExtractionError("Vision frame extraction failed")
            self._validate_image(stdout, "image/jpeg")
            frames.append(
                ExtractedVisionFrame(
                    timestamp_seconds=timestamp,
                    evidence_frame_reference=f"asset://{asset_id}#t={timestamp:.3f}",
                    content_type="image/jpeg",
                    payload=stdout,
                    sha256=hashlib.sha256(stdout).hexdigest(),
                )
            )
        if not frames:
            raise VisionFrameExtractionError("Vision frame extraction returned no evidence")
        return tuple(frames)

    def _validate_image(self, payload: bytes, content_type: str) -> None:
        if content_type not in _SUPPORTED_IMAGE_TYPES:
            raise VisionFrameExtractionError("unsupported Vision image content type")
        if not payload or len(payload) > self.max_image_bytes:
            raise VisionFrameExtractionError("Vision image payload is empty or exceeds its bound")
        signatures = {
            "image/jpeg": payload.startswith(b"\xff\xd8\xff"),
            "image/png": payload.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": len(payload) >= 12
            and payload.startswith(b"RIFF")
            and payload[8:12] == b"WEBP",
        }
        if not signatures[content_type]:
            raise VisionFrameExtractionError("Vision image signature does not match content type")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _response_text(payload: dict[str, object]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if (
                    isinstance(part, dict)
                    and part.get("type") == "output_text"
                    and isinstance(part.get("text"), str)
                    and part["text"].strip()
                ):
                    return part["text"]
    raise OpenAIVisionResponseError("OpenAI Vision response has no structured output text")


class OpenAIVisionProvider:
    """Fail-closed Responses API adapter; authorization remains in ProviderSafetyController."""

    key = "openai-vision"
    external_call = True
    paid = True

    def __init__(
        self,
        *,
        credential_alias: str | None,
        credential_resolver: Callable[[str], str],
        frame_extractor: VisionFrameExtractor,
        model: str = "gpt-5-mini",
        base_url: str = "https://api.openai.com",
        timeout_seconds: float = 60.0,
        image_detail: Literal["low", "high", "auto"] = "high",
        max_dimension_pixels: int = 2048,
        input_token_ceiling: int = 16_384,
        max_output_tokens: int = 8000,
        estimated_cost_vnd: Decimal = Decimal("0"),
        input_vnd_per_million_tokens: Decimal = Decimal("0"),
        cached_input_vnd_per_million_tokens: Decimal = Decimal("0"),
        output_vnd_per_million_tokens: Decimal = Decimal("0"),
        transport: httpx.AsyncBaseTransport | None = None,
        allow_zero_cost_contract_test: bool = False,
    ) -> None:
        if model != "gpt-5-mini":
            raise ValueError("V3-01-09 is locked to gpt-5-mini")
        if base_url.rstrip("/") != "https://api.openai.com":
            raise ValueError("OpenAI Vision base URL must be the official HTTPS API origin")
        if timeout_seconds <= 0:
            raise ValueError("OpenAI Vision timeout must be positive")
        if not 32 <= max_dimension_pixels <= 65_535:
            raise ValueError("OpenAI Vision maximum dimension is invalid")
        if input_token_ceiling < 1:
            raise ValueError("OpenAI Vision input-token ceiling must be positive")
        if not 256 <= max_output_tokens <= 32768:
            raise ValueError("OpenAI Vision output-token bound is invalid")
        costs = (
            estimated_cost_vnd,
            input_vnd_per_million_tokens,
            cached_input_vnd_per_million_tokens,
            output_vnd_per_million_tokens,
        )
        if any(value < 0 for value in costs):
            raise ValueError("OpenAI Vision VND costs cannot be negative")
        self.model = model
        self.credential_alias = credential_alias or None
        self.estimated_cost_vnd = estimated_cost_vnd
        self._credential_resolver = credential_resolver
        self._frame_extractor = frame_extractor
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self.timeout_seconds = timeout_seconds
        self.image_detail = image_detail
        self.max_frames = int(getattr(frame_extractor, "max_frames", 8))
        self.max_dimension_pixels = max_dimension_pixels
        self.input_token_ceiling = input_token_ceiling
        self.max_output_tokens = max_output_tokens
        self._input_rate = input_vnd_per_million_tokens
        self._cached_input_rate = cached_input_vnd_per_million_tokens
        self._output_rate = output_vnd_per_million_tokens
        self._transport = transport
        self._allow_zero_cost_contract_test = allow_zero_cost_contract_test

    def __repr__(self) -> str:
        return f"OpenAIVisionProvider(model={self.model!r}, credential_alias=<redacted>)"

    async def analyze(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        scenes: list[SceneRead],
        asset_id: str,
        checksum_sha256: str,
        sample_interval_seconds: float,
    ) -> ProviderVisionResult:
        if metadata.width is None or metadata.height is None:
            raise VisionFrameExtractionError("Vision input dimensions are required")
        if max(metadata.width, metadata.height) > self.max_dimension_pixels:
            raise VisionFrameExtractionError("Vision input exceeds the approved dimension limit")
        alias = self.credential_alias
        if not alias:
            raise VisionProviderNotConfigured("OpenAI Vision credential alias is not configured")
        api_key = self._credential_resolver(alias).strip()
        if not api_key:
            raise VisionProviderNotConfigured("OpenAI Vision credential alias cannot be resolved")
        if not self._allow_zero_cost_contract_test and (
            self.estimated_cost_vnd <= 0 or self._input_rate <= 0 or self._output_rate <= 0
        ):
            raise VisionProviderNotConfigured(
                "OpenAI Vision VND cost envelope requires a separate G-02 configuration"
            )

        extracted = await self._frame_extractor.extract(
            path,
            metadata=metadata,
            scenes=scenes,
            asset_id=asset_id,
            sample_interval_seconds=sample_interval_seconds,
        )
        if len(extracted) != self.max_frames:
            raise VisionFrameExtractionError(
                "Vision evidence frame count does not match the approved frame limit"
            )
        request_payload = self._request_payload(extracted)
        request_bytes = _canonical_json(request_payload)
        started = time.perf_counter()
        timeout = httpx.Timeout(self._timeout_seconds, connect=min(15.0, self._timeout_seconds))
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/v1/responses",
                    content=request_bytes,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError() from exc
        except httpx.RequestError as exc:
            raise ProviderTransientError("OPENAI_VISION_NETWORK_ERROR") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        if response.status_code == 429:
            raise ProviderRateLimitError()
        if response.status_code in {408, 409} or response.status_code >= 500:
            raise ProviderTransientError("OPENAI_VISION_TRANSIENT_HTTP")
        if response.status_code >= 400:
            raise OpenAIVisionResponseError(
                f"OpenAI Vision request was rejected with HTTP {response.status_code}"
            )
        response_bytes = response.content
        try:
            response_payload = response.json()
            if not isinstance(response_payload, dict):
                raise TypeError("response root must be an object")
            if response_payload.get("status") not in {None, "completed"}:
                raise OpenAIVisionResponseError("OpenAI Vision response did not complete")
            structured = _VisionOutput.model_validate_json(_response_text(response_payload))
        except (json.JSONDecodeError, TypeError, ValidationError) as exc:
            raise OpenAIVisionResponseError(
                "OpenAI Vision response failed strict structured-output validation"
            ) from exc

        expected_indexes = set(range(len(extracted)))
        actual_indexes = {frame.frame_index for frame in structured.frames}
        if actual_indexes != expected_indexes:
            raise OpenAIVisionResponseError(
                "OpenAI Vision response does not cover every supplied evidence frame exactly once"
            )
        output_by_index = {frame.frame_index: frame for frame in structured.frames}
        frames = tuple(
            self._map_frame(source, output_by_index[index])
            for index, source in enumerate(extracted)
        )
        usage = response_payload.get("usage")
        cost_receipt, actual_cost = self._cost_receipt(usage)
        response_id = response_payload.get("id")
        provenance: dict[str, object] = {
            "fixture": False,
            "mock_tested": self._transport is not None,
            "real_provider_tested": False,
            "external_call": True,
            "paid": True,
            "structured_output": True,
            "source_checksum": checksum_sha256,
            "provider": "openai",
            "model_requested": self.model,
            "model_returned": str(response_payload.get("model") or self.model),
            "request_sha256": hashlib.sha256(request_bytes).hexdigest(),
            "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
            "provider_response_id_sha256": (
                hashlib.sha256(str(response_id).encode("utf-8")).hexdigest()
                if response_id
                else None
            ),
            "latency_ms": latency_ms,
            "credential_alias_sha256": hashlib.sha256(alias.encode("utf-8")).hexdigest(),
            "artifact_evidence": [
                {
                    "frame_index": index,
                    "timestamp_seconds": frame.timestamp_seconds,
                    "evidence_frame_reference": frame.evidence_frame_reference,
                    "sha256": frame.sha256,
                    "content_type": frame.content_type,
                }
                for index, frame in enumerate(extracted)
            ],
            "cost_receipt": cost_receipt,
            "secret_recorded": False,
        }
        return ProviderVisionResult(
            frames=frames,
            provenance=provenance,
            actual_cost_vnd=actual_cost,
        )

    def _request_payload(
        self, frames: tuple[ExtractedVisionFrame, ...]
    ) -> dict[str, object]:
        content: list[dict[str, object]] = [
            {
                "type": "input_text",
                "text": (
                    "Analyze each supplied real-estate media frame in order. Return exactly one "
                    "structured record for every frame_index. Describe only visible evidence; do "
                    "not infer prices, legal claims, project identity, or unreadable text. Bounding "
                    "boxes use normalized x/y/width/height in [0,1]. OCR must preserve visible "
                    "Vietnamese diacritics. Evaluate composition, primary subject, safe crop, image "
                    "quality, watermark/logo presence, and calibrated confidence."
                ),
            }
        ]
        for index, frame in enumerate(frames):
            content.append(
                {
                    "type": "input_text",
                    "text": f"frame_index={index}; timestamp_seconds={frame.timestamp_seconds:.3f}",
                }
            )
            content.append(
                {
                    "type": "input_image",
                    "image_url": (
                        f"data:{frame.content_type};base64,"
                        f"{base64.b64encode(frame.payload).decode('ascii')}"
                    ),
                    "detail": self.image_detail,
                }
            )
        return {
            "model": self.model,
            "store": False,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "npd_vision_analysis",
                    "strict": True,
                    "schema": _VisionOutput.model_json_schema(),
                }
            },
            "max_output_tokens": self.max_output_tokens,
        }

    @staticmethod
    def _map_frame(
        source: ExtractedVisionFrame,
        output: _FrameOutput,
    ) -> ProviderVisionFrame:
        return ProviderVisionFrame(
            timestamp_seconds=source.timestamp_seconds,
            evidence_frame_reference=source.evidence_frame_reference,
            caption=output.caption,
            scene_description=output.scene_description,
            semantic_label=output.semantic_label,
            environment=output.environment,
            action=output.action,
            objects=tuple(
                ProviderObjectDetection(
                    label=item.label,
                    category=item.category,
                    confidence=item.confidence,
                    bounding_box=item.bounding_box,
                    track_hint=item.track_hint,
                )
                for item in output.objects
            ),
            ocr=tuple(
                ProviderOCRDetection(
                    text=item.text,
                    language=item.language,
                    confidence=item.confidence,
                    bounding_box=item.bounding_box,
                )
                for item in output.ocr
            ),
            primary_subject_box=output.primary_subject_box,
            saliency_box=output.saliency_box,
            headroom_ratio=output.headroom_ratio,
            visual_balance_score=output.visual_balance_score,
            safe_crop=output.safe_crop,
            quality_score=output.quality_score,
            black_frame=output.black_frame,
            blur_score=output.blur_score,
            overexposed=output.overexposed,
            underexposed=output.underexposed,
            low_resolution=output.low_resolution,
            watermark_or_logo_detected=output.watermark_or_logo_detected,
            frozen_or_duplicate=output.frozen_or_duplicate,
            quality_issues=tuple(output.quality_issues),
            confidence=output.confidence,
        )

    def _cost_receipt(
        self, usage: object
    ) -> tuple[dict[str, object], Decimal | None]:
        if not isinstance(usage, dict):
            return (
                {
                    "currency": "VND",
                    "status": "pending",
                    "reason": "provider_usage_missing",
                    "actual_cost_vnd": None,
                },
                None,
            )
        try:
            input_tokens = max(0, int(usage.get("input_tokens", 0)))
            output_tokens = max(0, int(usage.get("output_tokens", 0)))
            details = usage.get("input_tokens_details")
            cached_tokens = (
                max(0, int(details.get("cached_tokens", 0)))
                if isinstance(details, dict)
                else 0
            )
        except (TypeError, ValueError) as exc:
            raise OpenAIVisionResponseError("OpenAI Vision usage receipt is malformed") from exc
        cached_tokens = min(cached_tokens, input_tokens)
        if input_tokens > self.input_token_ceiling:
            raise OpenAIVisionResponseError("OpenAI Vision input usage exceeds its accounting ceiling")
        if output_tokens > self.max_output_tokens:
            raise OpenAIVisionResponseError("OpenAI Vision output usage exceeds its configured ceiling")
        uncached_tokens = input_tokens - cached_tokens
        million = Decimal("1000000")
        actual = (
            Decimal(uncached_tokens) * self._input_rate
            + Decimal(cached_tokens) * self._cached_input_rate
            + Decimal(output_tokens) * self._output_rate
        ) / million
        actual = actual.quantize(Decimal("0.000001"))
        return (
            {
                "currency": "VND",
                "status": (
                    "contract_test_zero"
                    if self._allow_zero_cost_contract_test
                    and self._input_rate == 0
                    and self._output_rate == 0
                    else (
                        "contract_test_calculated"
                        if self._transport is not None
                        else "actual"
                    )
                ),
                "input_tokens": input_tokens,
                "cached_input_tokens": cached_tokens,
                "output_tokens": output_tokens,
                "input_vnd_per_million_tokens": str(self._input_rate),
                "cached_input_vnd_per_million_tokens": str(self._cached_input_rate),
                "output_vnd_per_million_tokens": str(self._output_rate),
                "actual_cost_vnd": str(actual),
                "calculation_version": "openai-token-usage-v1",
            },
            actual,
        )
