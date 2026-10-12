"""Measured temporal template tracking; no semantic/face inference or probabilities."""
from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import Field

from .models import StrictModel
from .vision_models import NormalizedBox

ALGORITHM = "local-template-ncc-v2"


class TrackingConfiguration(StrictModel):
    seed_box: NormalizedBox
    sample_interval_seconds: float = Field(default=.2, ge=.1, le=10)
    minimum_match: float = Field(default=.8, ge=.6, le=1)
    ambiguity_margin: float = Field(default=.04, ge=.01, le=.3)
    search_radius: float = Field(default=.12, ge=.02, le=.3)
    minimum_texture_std: float = Field(default=8, ge=1, le=64)


class TrackingObservation(StrictModel):
    timestamp_seconds: float = Field(ge=0)
    status: Literal["seed", "tracked", "low_texture", "lost", "ambiguous", "stopped_after_loss"]
    bounding_box: NormalizedBox | None
    normalized_cross_correlation: float | None = Field(default=None, ge=-1, le=1)
    competing_peak_margin: float | None = Field(default=None, ge=0, le=2)
    confidence: None = None
    confidence_basis: Literal["measured template similarity; not calibrated confidence"] = "measured template similarity; not calibrated confidence"


def _frame(value, minimum=16):
    image = np.asarray(value, dtype=np.float64)
    if image.ndim != 2 or min(image.shape) < minimum or max(image.shape) > 512 or not np.isfinite(image).all() or image.min() < 0 or image.max() > 255:
        raise ValueError("Tracking requires finite bounded decoded grayscale pixels")
    return image


def normalized_correlation(image, template):
    """FFT cross-correlation with exact window sums; independently checked in tests."""
    image, template = _frame(image, minimum=4), np.asarray(template, dtype=np.float64)
    if template.ndim != 2 or min(template.shape) < 4 or not np.isfinite(template).all() or template.min() < 0 or template.max() > 255:
        raise ValueError("Invalid template")
    height, width = template.shape
    if height > image.shape[0] or width > image.shape[1]:
        raise ValueError("Template outside decoded frame")
    centered = template - template.mean()
    energy = float(np.square(centered).sum())
    if energy <= 1e-12:
        return np.full((image.shape[0] - height + 1, image.shape[1] - width + 1), -1., dtype=np.float64)
    shape = tuple(1 << (size + patch - 2).bit_length() for size, patch in zip(image.shape, template.shape))
    convolution = np.fft.irfft2(np.fft.rfft2(image, s=shape) * np.fft.rfft2(centered[::-1, ::-1], s=shape), s=shape)
    numerator = convolution[height - 1:image.shape[0], width - 1:image.shape[1]]

    def sums(value):
        integral = np.pad(value.cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))
        return integral[height:, width:] - integral[:-height, width:] - integral[height:, :-width] + integral[:-height, :-width]

    total, squared = sums(image), sums(np.square(image))
    variance = np.maximum(0., squared - np.square(total) / template.size)
    denominator = np.sqrt(variance * energy)
    return np.clip(np.divide(numerator, denominator, out=np.full_like(numerator, -1.), where=denominator > 1e-10), -1., 1.)


class LocalTemplateTrackingProvider:
    provider_key = "local-numpy-template-tracking"
    model = ALGORITHM
    semantic_inference_performed = False

    def __init__(self, configuration: TrackingConfiguration):
        self.configuration = configuration
        self.template = None
        self.shape = None
        self.position = None
        self.previous_time = -1.
        self.stopped = False

    def observe(self, pixels, timestamp_seconds):
        original = _frame(pixels)
        # A separable binomial low-pass reduces phase sensitivity from decoded
        # resize/subpixel motion. Keep the immutable seed and safety thresholds.
        padded = np.pad(original, ((0, 0), (1, 1)), mode="edge")
        horizontal = (padded[:, :-2] + 2 * padded[:, 1:-1] + padded[:, 2:]) / 4
        padded = np.pad(horizontal, ((1, 1), (0, 0)), mode="edge")
        image = (padded[:-2] + 2 * padded[1:-1] + padded[2:]) / 4
        if not math.isfinite(timestamp_seconds) or timestamp_seconds < 0 or timestamp_seconds <= self.previous_time:
            raise ValueError("Decoded source timestamps must strictly increase")
        self.previous_time = timestamp_seconds
        height, width = image.shape
        if self.shape is not None and image.shape != self.shape:
            raise ValueError("Decoded geometry changed inside a track")
        self.shape = image.shape
        if self.stopped:
            return TrackingObservation(timestamp_seconds=timestamp_seconds, status="stopped_after_loss", bounding_box=None)
        if self.template is None:
            box = self.configuration.seed_box
            left, top = int(round(box.x * width)), int(round(box.y * height))
            right, bottom = min(width, int(round((box.x + box.width) * width))), min(height, int(round((box.y + box.height) * height)))
            self.template = image[top:bottom, left:right].copy()
            if min(self.template.shape) < 4:
                raise ValueError("Seed is too small in decoded pixels")
            self.position = left, top
            if float(original[top:bottom, left:right].std()) < self.configuration.minimum_texture_std:
                self.stopped = True
                return TrackingObservation(timestamp_seconds=timestamp_seconds, status="low_texture", bounding_box=None)
            return TrackingObservation(timestamp_seconds=timestamp_seconds, status="seed", bounding_box=self._box(width, height), normalized_cross_correlation=1.)

        radius_x, radius_y = max(2, int(round(width * self.configuration.search_radius))), max(2, int(round(height * self.configuration.search_radius)))
        left, top = self.position
        patch_h, patch_w = self.template.shape
        x0, y0 = max(0, left - radius_x), max(0, top - radius_y)
        x1, y1 = min(width, left + patch_w + radius_x), min(height, top + patch_h + radius_y)
        correlations = normalized_correlation(image[y0:y1, x0:x1], self.template)
        y, x = np.unravel_index(int(correlations.argmax()), correlations.shape)
        score = float(correlations[y, x])
        # Adjacent pixel translations are one peak, not independent subjects.
        competitors = correlations.copy()
        competitors[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = -1.
        margin = max(0., score - float(competitors.max()))
        status = "lost" if score < self.configuration.minimum_match else "ambiguous" if margin < self.configuration.ambiguity_margin else "tracked"
        if status != "tracked":
            self.stopped = True
            box = None
        else:
            self.position = x0 + int(x), y0 + int(y)
            box = self._box(width, height)
        return TrackingObservation(timestamp_seconds=timestamp_seconds, status=status, bounding_box=box,
            normalized_cross_correlation=round(score, 9), competing_peak_margin=round(margin, 9))

    def _box(self, width, height):
        left, top = self.position
        patch_h, patch_w = self.template.shape
        return NormalizedBox(x=left / width, y=top / height, width=patch_w / width, height=patch_h / height)
