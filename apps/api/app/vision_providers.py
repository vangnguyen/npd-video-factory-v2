from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from .auto_edit_models import MediaMetadata, SceneRead
from .provider_safety import ProviderExecutionTrace
from .vision_models import NormalizedBox


class VisionProviderNotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderObjectDetection:
    label: str
    category: str
    confidence: float
    bounding_box: NormalizedBox
    track_hint: str | None = None


@dataclass(frozen=True)
class ProviderOCRDetection:
    text: str
    language: str
    confidence: float
    bounding_box: NormalizedBox


@dataclass(frozen=True)
class ProviderVisionFrame:
    timestamp_seconds: float
    evidence_frame_reference: str
    caption: str
    scene_description: str
    semantic_label: str
    environment: str
    action: str
    objects: tuple[ProviderObjectDetection, ...]
    ocr: tuple[ProviderOCRDetection, ...]
    primary_subject_box: NormalizedBox | None
    saliency_box: NormalizedBox | None
    headroom_ratio: float
    visual_balance_score: float
    safe_crop: bool
    quality_score: float
    black_frame: bool
    blur_score: float
    overexposed: bool
    underexposed: bool
    low_resolution: bool
    watermark_or_logo_detected: bool
    frozen_or_duplicate: bool
    quality_issues: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class ProviderVisionResult:
    frames: tuple[ProviderVisionFrame, ...]
    provenance: dict[str, object]
    actual_cost_vnd: Decimal | None = None


class VisionProvider(Protocol):
    key: str
    model: str
    external_call: bool
    paid: bool
    credential_alias: str | None
    estimated_cost_vnd: Decimal | None

    async def analyze(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        scenes: list[SceneRead],
        asset_id: str,
        checksum_sha256: str,
        sample_interval_seconds: float,
        execution_trace: ProviderExecutionTrace | None = None,
    ) -> ProviderVisionResult: ...


def _sample_times(duration: float, scenes: list[SceneRead], interval: float) -> list[float]:
    candidates = {round(min(duration - 0.001, max(0.0, scene.start_seconds + (scene.end_seconds - scene.start_seconds) / 2)), 3) for scene in scenes}
    cursor = min(interval / 2, max(0.0, duration - 0.001))
    while cursor < duration and len(candidates) < 120:
        candidates.add(round(min(duration - 0.001, cursor), 3))
        cursor += interval
    return sorted(value for value in candidates if value >= 0)


def _scene_for_time(scenes: list[SceneRead], timestamp: float) -> SceneRead | None:
    return next(
        (scene for scene in scenes if scene.start_seconds <= timestamp < scene.end_seconds),
        scenes[-1] if scenes else None,
    )


class DeterministicVisionProvider:
    """Offline structured fixture. It never claims to be real pixel-model evidence."""

    key = "fixture-vision"
    model = "deterministic-vision-v2-05"
    external_call = False
    paid = False
    credential_alias = None
    estimated_cost_vnd = Decimal("0")

    async def analyze(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        scenes: list[SceneRead],
        asset_id: str,
        checksum_sha256: str,
        sample_interval_seconds: float,
        execution_trace: ProviderExecutionTrace | None = None,
    ) -> ProviderVisionResult:
        del execution_trace
        if not path.is_file():
            raise FileNotFoundError(path)
        duration = float(metadata.duration_seconds or 0)
        if duration <= 0:
            raise ValueError("vision analysis requires positive media duration")
        labels = ("project_overview", "location", "amenity", "customer_action")
        environments = ("outdoor_property", "map_graphic", "residential_amenity", "sales_cta")
        ocr_texts = ("VINHOMES", "VỊ TRÍ DỰ ÁN", "TIỆN ÍCH", "ĐĂNG KÝ TƯ VẤN")
        frames: list[ProviderVisionFrame] = []
        for index, timestamp in enumerate(_sample_times(duration, scenes, sample_interval_seconds)):
            scene = _scene_for_time(scenes, timestamp)
            scene_index = scene.ordinal if scene else index
            phase = scene_index % len(labels)
            center_x = 0.5 + 0.09 * math.sin(index * 0.65)
            subject_box = NormalizedBox(
                x=round(max(0.05, min(0.75, center_x - 0.15)), 4),
                y=0.2,
                width=0.3,
                height=0.48,
            )
            primary_category = "person" if phase in {2, 3} else "building"
            primary_label = "người tư vấn" if primary_category == "person" else "dự án bất động sản"
            objects = (
                ProviderObjectDetection(
                    label=primary_label,
                    category=primary_category,
                    confidence=0.9,
                    bounding_box=subject_box,
                    track_hint="primary-subject",
                ),
                ProviderObjectDetection(
                    label="logo thương hiệu",
                    category="logo",
                    confidence=0.88,
                    bounding_box=NormalizedBox(x=0.04, y=0.04, width=0.18, height=0.09),
                    track_hint="brand-logo",
                ),
            )
            ocr = (
                ProviderOCRDetection(
                    text=ocr_texts[phase],
                    language="vi",
                    confidence=0.94,
                    bounding_box=NormalizedBox(x=0.12, y=0.72, width=0.76, height=0.12),
                ),
            )
            low_resolution = bool((metadata.width or 0) < 720 or (metadata.height or 0) < 720)
            issues = ("low_resolution",) if low_resolution else ()
            semantic_label = scene.semantic_label if scene else labels[phase]
            description = scene.description if scene else f"Khung hình {labels[phase]}"
            frames.append(
                ProviderVisionFrame(
                    timestamp_seconds=timestamp,
                    evidence_frame_reference=f"asset://{asset_id}#t={timestamp:.3f}",
                    caption=f"Khung hình {labels[phase]} có chủ thể chính và chữ tiếng Việt.",
                    scene_description=description,
                    semantic_label=semantic_label,
                    environment=environments[phase],
                    action="presenting_property" if primary_category == "person" else "showing_property",
                    objects=objects,
                    ocr=ocr,
                    primary_subject_box=subject_box,
                    saliency_box=subject_box,
                    headroom_ratio=0.2,
                    visual_balance_score=0.86,
                    safe_crop=True,
                    quality_score=0.74 if low_resolution else 0.92,
                    black_frame=False,
                    blur_score=0.08,
                    overexposed=False,
                    underexposed=False,
                    low_resolution=low_resolution,
                    watermark_or_logo_detected=True,
                    frozen_or_duplicate=False,
                    quality_issues=issues,
                    confidence=0.91,
                )
            )
        return ProviderVisionResult(
            frames=tuple(frames),
            provenance={
                "fixture": True,
                "mock_tested": True,
                "real_provider_tested": False,
                "external_call": False,
                "paid": False,
                "source_checksum": checksum_sha256,
                "structured_output": True,
            },
        )


class ContractOnlyVisionProvider:
    key = "vision-not-configured"
    model = "not-configured"
    external_call = False
    paid = False
    credential_alias = None
    estimated_cost_vnd = Decimal("0")

    async def analyze(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        scenes: list[SceneRead],
        asset_id: str,
        checksum_sha256: str,
        sample_interval_seconds: float,
        execution_trace: ProviderExecutionTrace | None = None,
    ) -> ProviderVisionResult:
        del (
            path,
            metadata,
            scenes,
            asset_id,
            checksum_sha256,
            sample_interval_seconds,
            execution_trace,
        )
        raise VisionProviderNotConfigured(
            "Live Vision provider is not configured; select an owner-approved adapter and credentials."
        )
