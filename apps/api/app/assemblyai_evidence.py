"""Secret-free evidence contracts for AssemblyAI request/job/result custody."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field

from .models import StrictModel


class AssemblyAIRequestEvidence(StrictModel):
    provider: Literal["assemblyai-transcription"]
    model: Literal["universal-3-5-pro"]
    language: Literal["vi"]
    profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    upload_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    uploads_accepted: Literal[1]
    transcript_jobs_created: Literal[1]
    automatic_retry: Literal[False]
    model_fallback: Literal[False]


class AssemblyAIResultEvidence(StrictModel):
    provider: Literal["assemblyai-transcription"]
    model: Literal["universal-3-5-pro"]
    transcript_id: str = Field(min_length=1, max_length=200)
    status: Literal["completed", "error", "review_required"]
    raw_response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    transcript_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    words_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    word_count: int = Field(ge=0)
    positive_duration_words: int = Field(ge=0)
    zero_duration_words: Literal[0]
    negative_duration_words: Literal[0]
    modeled_cost_vnd: Decimal = Field(ge=0)
    provider_credit_debit: Decimal | None = Field(default=None, ge=0)
    out_of_pocket_spend_vnd: Decimal | None = Field(default=None, ge=0)
    secret_scan_findings: Literal[0]
