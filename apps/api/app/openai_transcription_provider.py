from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .auto_edit_models import MediaMetadata
from .auto_edit_providers import (
    ProviderNotConfigured,
    ProviderSegment,
    ProviderTranscript,
    ProviderWord,
)
from .models import StrictModel
from .provider_safety import (
    ProviderErrorEvidence,
    ProviderExecutionTrace,
    ProviderJsonShapeType,
    ProviderRequestDispatchState,
    ProviderResponseMetadata,
    ProviderRateLimitError,
    ProviderTimeoutEnvelope,
    ProviderTimeoutError,
    ProviderTransientError,
    ProviderValidationIssue,
    ProviderValidationIssueKind,
)


OpenAITranscriptionModel = Literal[
    "whisper-1",
    "gpt-transcribe",
    "gpt-4o-transcribe",
]
CompatibilityStatus = Literal["SUPPORTED", "UNSUPPORTED", "UNRESOLVED"]
ModelSelectionStatus = Literal["PROPOSED_NOT_APPROVED"]

_OFFICIAL_GUIDE = "https://developers.openai.com/api/docs/guides/speech-to-text"
_OFFICIAL_API = (
    "https://developers.openai.com/api/reference/resources/audio/"
    "subresources/transcriptions/methods/create"
)
_CHECKED_ON = date(2026, 9, 3)
_SUPPORTED_MEDIA_KINDS = {"audio", "video"}
_SUPPORTED_FILE_SUFFIXES = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}
_ASR_RESPONSE_FIELDS = ("task", "language", "duration", "text", "segments", "words")
_SECRET_TEXT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"(?i)(bearer\s+)\S+"),
    re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)\S+"),
)


class OpenAIAsrCompatibilityRow(StrictModel):
    """Dated offline capability evidence; this is never runtime authority."""

    model: OpenAITranscriptionModel
    selection_status: ModelSelectionStatus = "PROPOSED_NOT_APPROVED"
    transcript_text: CompatibilityStatus
    segment_timestamps: CompatibilityStatus
    word_timestamps: CompatibilityStatus
    language: CompatibilityStatus
    usage_or_duration: CompatibilityStatus
    provider_request_id: CompatibilityStatus
    deterministic_provider_transcript_mapping: CompatibilityStatus
    strict_flow_a_compatible: bool
    checked_on: date = _CHECKED_ON
    evidence_kind: Literal["official_contract_and_recorded_fixture"] = (
        "official_contract_and_recorded_fixture"
    )
    official_references: tuple[str, ...]
    live_api_calls: Literal[0] = 0
    credential_reads: Literal[0] = 0
    spend_vnd: Literal[0] = 0
    notes: tuple[str, ...]

    @model_validator(mode="after")
    def validate_strict_compatibility(self) -> "OpenAIAsrCompatibilityRow":
        required = (
            self.transcript_text,
            self.segment_timestamps,
            self.word_timestamps,
            self.language,
            self.usage_or_duration,
            self.provider_request_id,
            self.deterministic_provider_transcript_mapping,
        )
        if self.strict_flow_a_compatible != all(item == "SUPPORTED" for item in required):
            raise ValueError("strict Flow A compatibility must derive from every required field")
        return self


def openai_asr_compatibility_matrix() -> tuple[OpenAIAsrCompatibilityRow, ...]:
    """Return the reviewed, zero-call matrix for the three required candidates.

    The current OpenAI speech-to-text guide states that native word/segment
    timestamp granularities are supported only by ``whisper-1``.  Selection is
    still an owner decision, so even the compatible row remains proposed.
    """

    common_refs = (_OFFICIAL_GUIDE, _OFFICIAL_API)
    return (
        OpenAIAsrCompatibilityRow(
            model="whisper-1",
            transcript_text="SUPPORTED",
            segment_timestamps="SUPPORTED",
            word_timestamps="SUPPORTED",
            language="SUPPORTED",
            usage_or_duration="SUPPORTED",
            provider_request_id="SUPPORTED",
            deterministic_provider_transcript_mapping="SUPPORTED",
            strict_flow_a_compatible=True,
            official_references=common_refs
            + ("https://developers.openai.com/api/docs/models/whisper-1",),
            notes=(
                "verbose_json exposes language, duration, segments and words",
                "native word timing satisfies the strict Flow A timestamp contract",
                "provider confidence is not fabricated and maps to null",
            ),
        ),
        OpenAIAsrCompatibilityRow(
            model="gpt-transcribe",
            transcript_text="SUPPORTED",
            segment_timestamps="UNSUPPORTED",
            word_timestamps="UNSUPPORTED",
            language="UNRESOLVED",
            usage_or_duration="SUPPORTED",
            provider_request_id="SUPPORTED",
            deterministic_provider_transcript_mapping="UNSUPPORTED",
            strict_flow_a_compatible=False,
            official_references=common_refs
            + ("https://developers.openai.com/api/docs/models/gpt-transcribe",),
            notes=(
                "current official guide reserves timestamp granularities for whisper-1",
                "no alignment layer is introduced by V3-01-18",
                "model selection remains an owner gate",
            ),
        ),
        OpenAIAsrCompatibilityRow(
            model="gpt-4o-transcribe",
            transcript_text="SUPPORTED",
            segment_timestamps="UNSUPPORTED",
            word_timestamps="UNSUPPORTED",
            language="UNRESOLVED",
            usage_or_duration="SUPPORTED",
            provider_request_id="SUPPORTED",
            deterministic_provider_transcript_mapping="UNSUPPORTED",
            strict_flow_a_compatible=False,
            official_references=common_refs
            + ("https://developers.openai.com/api/docs/models/gpt-4o-transcribe",),
            notes=(
                "current official guide reserves timestamp granularities for whisper-1",
                "token usage does not replace native segment and word timing",
                "model selection remains an owner gate",
            ),
        ),
    )


def compatible_openai_asr_models() -> frozenset[str]:
    return frozenset(
        row.model for row in openai_asr_compatibility_matrix() if row.strict_flow_a_compatible
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _redact_provider_text(value: object, *, limit: int) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    redacted = value.strip()
    for pattern in _SECRET_TEXT_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted[:limit]


def _safe_request_id(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    if re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", candidate):
        return candidate
    return "sha256:" + hashlib.sha256(candidate.encode("utf-8")).hexdigest()


def _exception_type_chain(error: BaseException) -> tuple[str, ...]:
    chain: list[str] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and len(chain) < 8 and id(current) not in seen:
        seen.add(id(current))
        chain.append(type(current).__name__)
        current = current.__cause__ or current.__context__
    return tuple(chain)


def _json_shape_type(value: object) -> ProviderJsonShapeType:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    return "number"


def _response_metadata(payload: object) -> ProviderResponseMetadata:
    if not isinstance(payload, dict):
        return ProviderResponseMetadata(top_level_type=_json_shape_type(payload))
    present = tuple(field for field in _ASR_RESPONSE_FIELDS if field in payload)
    missing = tuple(field for field in _ASR_RESPONSE_FIELDS if field not in payload)
    field_types = {field: _json_shape_type(payload[field]) for field in present}
    segments = payload.get("segments")
    words = payload.get("words")
    return ProviderResponseMetadata(
        top_level_type="object",
        allowed_fields_present=present,
        missing_required_fields=missing,
        field_types=field_types,
        segment_count=len(segments) if isinstance(segments, list) else None,
        word_count=len(words) if isinstance(words, list) else None,
        unknown_top_level_field_count=len(set(payload) - set(_ASR_RESPONSE_FIELDS)),
    )


class _ResponseContractViolation(ValueError):
    def __init__(
        self,
        *,
        path: str,
        code: str,
        kind: ProviderValidationIssueKind,
    ) -> None:
        super().__init__(code)
        self.path = path
        self.code = code
        self.kind = kind


def _validation_path(location: tuple[object, ...]) -> str:
    path = "$"
    for item in location:
        if isinstance(item, int) and item >= 0:
            path += f"[{item}]"
        elif isinstance(item, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,79}", item):
            path += f".{item}"
        else:
            return "$"
    return path


def _validation_issue_kind(code: str) -> ProviderValidationIssueKind:
    if code == "missing":
        return "missing"
    if "type" in code or code.endswith("_parsing"):
        return "type"
    if any(part in code for part in ("greater_than", "less_than", "range")):
        return "range"
    if "overlap" in code or "monotonic" in code:
        return "ordering"
    if "segment" in code or "mapping" in code or "bound" in code:
        return "mapping"
    return "invalid"


def _validation_issues(error: BaseException) -> tuple[ProviderValidationIssue, ...]:
    if isinstance(error, _ResponseContractViolation):
        return (
            ProviderValidationIssue(
                path=error.path,
                code=error.code,
                kind=error.kind,
            ),
        )
    if isinstance(error, ValidationError):
        issues: list[ProviderValidationIssue] = []
        for item in error.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        )[:32]:
            code = str(item.get("type") or "value_error")[:120]
            issues.append(
                ProviderValidationIssue(
                    path=_validation_path(tuple(item.get("loc") or ())),
                    code=code,
                    kind=_validation_issue_kind(code),
                )
            )
        return tuple(issues)
    return (
        ProviderValidationIssue(path="$", code="value_error", kind="invalid"),
    )


def _provider_error_fields(
    response_bytes: bytes,
) -> tuple[str | None, str | None, str | None, str | None]:
    try:
        payload = json.loads(response_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, None, None, None
    if not isinstance(payload, dict) or not isinstance(payload.get("error"), dict):
        return None, None, None, None
    error = payload["error"]
    return (
        _redact_provider_text(error.get("type"), limit=160),
        _redact_provider_text(error.get("code"), limit=160),
        _redact_provider_text(error.get("param"), limit=160),
        _redact_provider_text(error.get("message"), limit=1000),
    )


def _error_evidence(
    *,
    category: Literal[
        "http_provider_error",
        "transport_error",
        "response_parse_failure",
        "structured_output_incomplete",
        "structured_output_validation",
        "usage_receipt_missing",
        "usage_receipt_invalid",
    ],
    code: str,
    retryable: bool,
    http_status: int | None = None,
    response_bytes: bytes | None = None,
    provider_request_id: object = None,
    client_request_id: str | None = None,
    provider_error_type: object = None,
    provider_error_code: object = None,
    provider_error_parameter: object = None,
    provider_error_message: object = None,
    request_sha256: str | None = None,
    elapsed_ms: float | None = None,
    request_dispatch_state: ProviderRequestDispatchState | None = None,
    exception_chain: tuple[str, ...] = (),
    validation_issues: tuple[ProviderValidationIssue, ...] = (),
    response_metadata: ProviderResponseMetadata | None = None,
) -> ProviderErrorEvidence:
    return ProviderErrorEvidence(
        category=category,
        phase=(
            "structured_output_validation"
            if category == "structured_output_validation"
            else None
        ),
        code=code,
        http_status=http_status,
        provider_error_type=_redact_provider_text(provider_error_type, limit=160),
        provider_error_code=_redact_provider_text(provider_error_code, limit=160),
        provider_error_parameter=_redact_provider_text(provider_error_parameter, limit=160),
        provider_error_message=_redact_provider_text(provider_error_message, limit=1000),
        provider_request_id=_safe_request_id(provider_request_id),
        client_request_id=client_request_id,
        request_sha256=request_sha256,
        response_sha256=(
            hashlib.sha256(response_bytes).hexdigest() if response_bytes is not None else None
        ),
        validation_issues=validation_issues,
        response_metadata=response_metadata,
        elapsed_ms=elapsed_ms,
        request_dispatch_state=request_dispatch_state,
        exception_chain=exception_chain,
        retryable=retryable,
        secret_recorded=False,
    )


class OpenAITranscriptionResponseError(RuntimeError):
    """A transcription response failed the strict, secret-safe contract."""

    def __init__(
        self,
        message: str,
        *,
        error_evidence: ProviderErrorEvidence,
    ) -> None:
        super().__init__(message)
        self.code = error_evidence.code
        self.error_evidence = error_evidence


class _ProviderWord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    word: str = Field(min_length=1, max_length=240)
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_window(self) -> "_ProviderWord":
        if self.end <= self.start:
            raise ValueError("provider word end must follow start")
        return self


class _ProviderSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_window(self) -> "_ProviderSegment":
        if self.end <= self.start:
            raise ValueError("provider segment end must follow start")
        return self


class _WhisperVerboseResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task: Literal["transcribe"]
    language: str = Field(min_length=2, max_length=80)
    duration: float = Field(gt=0)
    text: str = Field(min_length=1)
    segments: list[_ProviderSegment] = Field(min_length=1)
    words: list[_ProviderWord] = Field(min_length=1)


def _normalize_language(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    if normalized in {"vi", "vi-vn", "vietnamese", "tiếng việt", "tieng viet"}:
        return "vi"
    return normalized


def _validate_ordered_windows(
    windows: list[tuple[float, float]],
    *,
    label: str,
    media_duration_seconds: float,
) -> None:
    previous_end = -1.0
    for index, (start, end) in enumerate(windows):
        path = f"$.{label}[{index}]"
        if start < 0 or end <= start:
            raise _ResponseContractViolation(
                path=path,
                code="invalid_timestamp_window",
                kind="range",
            )
        if start < previous_end - 1e-6:
            raise _ResponseContractViolation(
                path=path,
                code="timestamp_overlap",
                kind="ordering",
            )
        if end > media_duration_seconds + 0.05:
            raise _ResponseContractViolation(
                path=path,
                code="timestamp_out_of_range",
                kind="range",
            )
        previous_end = end


class OpenAITranscriptionProvider:
    """Fail-closed Audio Transcriptions adapter for strict Flow A evidence.

    This class contains no authority. ``ProviderSafetyController`` must approve
    the operation before this method is reached, and checked-in settings keep
    that controller closed.
    """

    key = "openai-transcription"
    capability = "asr"
    external_call = True
    paid = True

    def __init__(
        self,
        *,
        model: OpenAITranscriptionModel,
        credential_alias: str | None,
        credential_resolver: Callable[[str], str],
        base_url: str = "https://api.openai.com",
        language: Literal["vi"] = "vi",
        provider_http_timeout_seconds: float = 90.0,
        controller_hard_timeout_seconds: float = 120.0,
        max_file_bytes: int = 25_000_000,
        max_duration_seconds: float = 600.0,
        estimated_cost_vnd: Decimal = Decimal("0"),
        vnd_per_minute: Decimal = Decimal("0"),
        transport: httpx.AsyncBaseTransport | None = None,
        allow_zero_cost_contract_test: bool = False,
        monotonic_clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        if model not in compatible_openai_asr_models():
            raise ValueError(
                "OpenAI ASR model is not compatible with the strict native timestamp contract"
            )
        if base_url.rstrip("/") != "https://api.openai.com":
            raise ValueError("OpenAI transcription base URL must be the official HTTPS API origin")
        timeout_envelope = ProviderTimeoutEnvelope(
            provider_http_timeout_seconds=provider_http_timeout_seconds,
            controller_hard_timeout_seconds=controller_hard_timeout_seconds,
        )
        if not 1 <= max_file_bytes <= 25_000_000:
            raise ValueError("OpenAI transcription file bound must be between 1 and 25000000 bytes")
        if not 1 <= max_duration_seconds <= 3_600:
            raise ValueError("OpenAI transcription duration bound must be between 1 and 3600 seconds")
        if estimated_cost_vnd < 0 or vnd_per_minute < 0:
            raise ValueError("OpenAI transcription VND costs cannot be negative")
        self.model = model
        self.credential_alias = credential_alias or None
        self.estimated_cost_vnd = estimated_cost_vnd
        self._credential_resolver = credential_resolver
        self._base_url = base_url.rstrip("/")
        self.language = language
        self.timeout_envelope = timeout_envelope
        self.provider_http_timeout_seconds = timeout_envelope.provider_http_timeout_seconds
        self.controller_hard_timeout_seconds = timeout_envelope.controller_hard_timeout_seconds
        self.max_file_bytes = max_file_bytes
        self.max_duration_seconds = max_duration_seconds
        self.response_format = "verbose_json"
        self.timestamp_granularities = ("segment", "word")
        self._vnd_per_minute = vnd_per_minute
        self._transport = transport
        self._allow_zero_cost_contract_test = allow_zero_cost_contract_test
        self._monotonic_clock = monotonic_clock

    def __repr__(self) -> str:
        return (
            f"OpenAITranscriptionProvider(model={self.model!r}, "
            "credential_alias=<redacted>)"
        )

    async def transcribe(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        checksum_sha256: str,
        execution_trace: ProviderExecutionTrace | None = None,
    ) -> ProviderTranscript:
        trace = execution_trace or ProviderExecutionTrace(monotonic=self._monotonic_clock)
        trace.begin()
        trace.mark("request_build")
        if metadata.media_kind not in _SUPPORTED_MEDIA_KINDS:
            raise ValueError("OpenAI transcription accepts only trusted audio or video media")
        duration = float(metadata.duration_seconds or 0)
        if duration <= 0 or duration > self.max_duration_seconds:
            raise ValueError("OpenAI transcription input duration is missing or exceeds its bound")
        if not path.is_file():
            raise FileNotFoundError(path)
        source_suffix = path.suffix.lower()
        if source_suffix not in _SUPPORTED_FILE_SUFFIXES:
            raise ValueError("OpenAI transcription input uses an unsupported file extension")
        file_size = path.stat().st_size
        if file_size <= 0 or file_size > self.max_file_bytes:
            raise ValueError("OpenAI transcription input file is empty or exceeds its bound")
        source_bytes = path.read_bytes()
        actual_source_hash = hashlib.sha256(source_bytes).hexdigest()
        if actual_source_hash != checksum_sha256:
            raise ValueError("OpenAI transcription source checksum mismatch")

        if not self._allow_zero_cost_contract_test and (
            self.estimated_cost_vnd <= 0 or self._vnd_per_minute <= 0
        ):
            raise ProviderNotConfigured(
                "OpenAI transcription VND cost envelope requires a separate G-02 approval"
            )
        alias = self.credential_alias
        if not alias:
            raise ProviderNotConfigured("OpenAI transcription credential alias is not configured")
        trace.mark("credential_resolution")
        api_key = self._credential_resolver(alias).strip()
        if not api_key:
            raise ProviderNotConfigured("OpenAI transcription credential alias cannot be resolved")

        request_manifest = {
            "endpoint": "/v1/audio/transcriptions",
            "model": self.model,
            "language": self.language,
            "response_format": self.response_format,
            "timestamp_granularities": list(self.timestamp_granularities),
            "source_sha256": actual_source_hash,
            "source_bytes": file_size,
            "source_duration_seconds": duration,
            "source_file_suffix": source_suffix,
            "content_type": metadata.detected_content_type,
        }
        request_sha256 = hashlib.sha256(_canonical_json(request_manifest)).hexdigest()
        client_request_id = "vf-" + uuid.uuid4().hex
        trace.mark(
            "http_request_dispatch",
            dispatch_state="possibly_sent",
            client_request_id=client_request_id,
        )
        timeout = httpx.Timeout(
            self.provider_http_timeout_seconds,
            connect=min(15.0, self.provider_http_timeout_seconds),
        )
        response: httpx.Response | None = None
        response_bytes: bytes | None = None
        provider_request_id: str | None = None
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=timeout,
                transport=self._transport,
            ) as client:
                request = client.build_request(
                    "POST",
                    "/v1/audio/transcriptions",
                    data={
                        "model": self.model,
                        "language": self.language,
                        "response_format": "verbose_json",
                        "timestamp_granularities[]": ["segment", "word"],
                    },
                    files={
                        "file": (
                            f"acceptance-input{source_suffix}",
                            source_bytes,
                            metadata.detected_content_type,
                        )
                    },
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "X-Client-Request-Id": client_request_id,
                    },
                )
                response = await client.send(request, stream=True)
                provider_request_id = _safe_request_id(response.headers.get("x-request-id"))
                trace.mark(
                    "http_response_read",
                    dispatch_state="response_headers_received",
                    provider_request_id=provider_request_id,
                )
                response_bytes = await response.aread()
        except httpx.TimeoutException as exc:
            if isinstance(exc, httpx.PoolTimeout):
                trace.mark("http_connection_pool", dispatch_state="not_sent")
                timeout_kind = "pool"
            elif isinstance(exc, httpx.ConnectTimeout):
                trace.mark("http_connect", dispatch_state="not_sent")
                timeout_kind = "connect"
            elif isinstance(exc, httpx.WriteTimeout):
                trace.mark("http_request_write", dispatch_state="possibly_sent")
                timeout_kind = "write"
            elif isinstance(exc, httpx.ReadTimeout):
                if trace.request_dispatch_state != "response_headers_received":
                    trace.mark("http_response_wait", dispatch_state="possibly_sent")
                timeout_kind = "read"
            else:
                timeout_kind = "transport"
            timeout_evidence = trace.timeout_evidence(
                code="PROVIDER_TIMEOUT",
                timeout_kind=timeout_kind,
                timeout_envelope=self.timeout_envelope,
                error=exc,
                retryable=True,
                provider_error_message="OpenAI transcription transport timed out",
            ).model_copy(update={"request_sha256": request_sha256})
            raise ProviderTimeoutError(error_evidence=timeout_evidence) from exc
        except httpx.RequestError as exc:
            raise ProviderTransientError(
                "OPENAI_TRANSCRIPTION_NETWORK_ERROR",
                error_evidence=_error_evidence(
                    category="transport_error",
                    code="OPENAI_TRANSCRIPTION_NETWORK_ERROR",
                    retryable=True,
                    client_request_id=client_request_id,
                    request_sha256=request_sha256,
                    elapsed_ms=trace.elapsed_ms(),
                    request_dispatch_state=trace.request_dispatch_state,
                    exception_chain=_exception_type_chain(exc),
                    provider_error_type=type(exc).__name__,
                    provider_error_message="OpenAI transcription transport failed",
                ),
            ) from exc
        finally:
            if response is not None:
                await response.aclose()

        if response is None or response_bytes is None:
            raise RuntimeError("OpenAI transcription transport completed without a response")
        latency_ms = trace.elapsed_ms()
        trace.mark(
            "response_parse",
            dispatch_state="response_headers_received",
            provider_request_id=provider_request_id,
        )
        error_type, error_code, error_parameter, error_message = _provider_error_fields(
            response_bytes
        )
        if response.status_code == 429:
            raise ProviderRateLimitError(
                error_evidence=_error_evidence(
                    category="http_provider_error",
                    code="OPENAI_TRANSCRIPTION_RATE_LIMITED",
                    retryable=True,
                    http_status=response.status_code,
                    response_bytes=response_bytes,
                    provider_request_id=provider_request_id,
                    client_request_id=client_request_id,
                    provider_error_type=error_type,
                    provider_error_code=error_code,
                    provider_error_parameter=error_parameter,
                    provider_error_message=error_message,
                    request_sha256=request_sha256,
                    elapsed_ms=latency_ms,
                    request_dispatch_state=trace.request_dispatch_state,
                )
            )
        if response.status_code in {408, 409} or response.status_code >= 500:
            raise ProviderTransientError(
                "OPENAI_TRANSCRIPTION_TRANSIENT_HTTP",
                error_evidence=_error_evidence(
                    category="http_provider_error",
                    code="OPENAI_TRANSCRIPTION_TRANSIENT_HTTP",
                    retryable=True,
                    http_status=response.status_code,
                    response_bytes=response_bytes,
                    provider_request_id=provider_request_id,
                    client_request_id=client_request_id,
                    provider_error_type=error_type,
                    provider_error_code=error_code,
                    provider_error_parameter=error_parameter,
                    provider_error_message=error_message,
                    request_sha256=request_sha256,
                    elapsed_ms=latency_ms,
                    request_dispatch_state=trace.request_dispatch_state,
                ),
            )
        if response.status_code >= 400:
            evidence = _error_evidence(
                category="http_provider_error",
                code="OPENAI_TRANSCRIPTION_HTTP_ERROR",
                retryable=False,
                http_status=response.status_code,
                response_bytes=response_bytes,
                provider_request_id=provider_request_id,
                client_request_id=client_request_id,
                provider_error_type=error_type,
                provider_error_code=error_code,
                provider_error_parameter=error_parameter,
                provider_error_message=error_message,
                request_sha256=request_sha256,
                elapsed_ms=latency_ms,
                request_dispatch_state=trace.request_dispatch_state,
            )
            raise OpenAITranscriptionResponseError(
                f"OpenAI transcription request was rejected with HTTP {response.status_code}",
                error_evidence=evidence,
            )
        if provider_request_id is None:
            evidence = _error_evidence(
                category="structured_output_incomplete",
                code="OPENAI_TRANSCRIPTION_REQUEST_ID_MISSING",
                retryable=False,
                response_bytes=response_bytes,
                client_request_id=client_request_id,
                request_sha256=request_sha256,
                elapsed_ms=latency_ms,
                request_dispatch_state=trace.request_dispatch_state,
                provider_error_message="provider request ID is missing",
            )
            raise OpenAITranscriptionResponseError(
                "OpenAI transcription response omitted the provider request ID",
                error_evidence=evidence,
            )
        try:
            raw_payload = json.loads(response_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            evidence = _error_evidence(
                category="response_parse_failure",
                code="OPENAI_TRANSCRIPTION_RESPONSE_JSON_INVALID",
                retryable=False,
                response_bytes=response_bytes,
                provider_request_id=provider_request_id,
                client_request_id=client_request_id,
                request_sha256=request_sha256,
                elapsed_ms=latency_ms,
                request_dispatch_state=trace.request_dispatch_state,
                exception_chain=_exception_type_chain(exc),
                provider_error_type=type(exc).__name__,
                provider_error_message="OpenAI transcription returned invalid JSON",
            )
            raise OpenAITranscriptionResponseError(
                "OpenAI transcription returned invalid JSON",
                error_evidence=evidence,
            ) from exc
        try:
            payload = _WhisperVerboseResponse.model_validate(raw_payload)
            transcript = self._map_response(
                payload,
                media_duration_seconds=duration,
                source_checksum=actual_source_hash,
                request_sha256=request_sha256,
                response_sha256=hashlib.sha256(response_bytes).hexdigest(),
                provider_request_id=provider_request_id,
                client_request_id=client_request_id,
                latency_ms=latency_ms,
                credential_alias=alias,
            )
        except (ValidationError, ValueError) as exc:
            evidence = _error_evidence(
                category="structured_output_validation",
                code="OPENAI_TRANSCRIPTION_RESPONSE_INVALID",
                retryable=False,
                response_bytes=response_bytes,
                provider_request_id=provider_request_id,
                client_request_id=client_request_id,
                http_status=response.status_code,
                request_sha256=request_sha256,
                elapsed_ms=latency_ms,
                request_dispatch_state=trace.request_dispatch_state,
                exception_chain=_exception_type_chain(exc),
                validation_issues=_validation_issues(exc),
                response_metadata=_response_metadata(raw_payload),
                provider_error_type=type(exc).__name__,
                provider_error_message="OpenAI transcription response failed strict validation",
            )
            raise OpenAITranscriptionResponseError(
                "OpenAI transcription response failed strict validation",
                error_evidence=evidence,
            ) from exc
        return transcript

    def _map_response(
        self,
        payload: _WhisperVerboseResponse,
        *,
        media_duration_seconds: float,
        source_checksum: str,
        request_sha256: str,
        response_sha256: str,
        provider_request_id: str,
        client_request_id: str,
        latency_ms: float,
        credential_alias: str,
    ) -> ProviderTranscript:
        language = _normalize_language(payload.language)
        if language != self.language:
            raise _ResponseContractViolation(
                path="$.language",
                code="language_mismatch",
                kind="invalid",
            )
        if payload.duration > media_duration_seconds + 0.5:
            raise _ResponseContractViolation(
                path="$.duration",
                code="duration_out_of_range",
                kind="range",
            )

        segment_windows = [(item.start, item.end) for item in payload.segments]
        word_windows = [(item.start, item.end) for item in payload.words]
        _validate_ordered_windows(
            segment_windows,
            label="segments",
            media_duration_seconds=media_duration_seconds,
        )
        _validate_ordered_windows(
            word_windows,
            label="words",
            media_duration_seconds=media_duration_seconds,
        )

        assigned_word_indexes: set[int] = set()
        segments: list[ProviderSegment] = []
        for segment_index, segment in enumerate(payload.segments):
            mapped_words: list[ProviderWord] = []
            for index, word in enumerate(payload.words):
                midpoint = (word.start + word.end) / 2
                if segment.start - 0.05 <= midpoint <= segment.end + 0.05:
                    if index in assigned_word_indexes:
                        raise _ResponseContractViolation(
                            path=f"$.words[{index}]",
                            code="word_maps_to_multiple_segments",
                            kind="mapping",
                        )
                    if word.start < segment.start - 0.05 or word.end > segment.end + 0.05:
                        raise _ResponseContractViolation(
                            path=f"$.words[{index}]",
                            code="word_outside_segment",
                            kind="mapping",
                        )
                    assigned_word_indexes.add(index)
                    mapped_words.append(
                        ProviderWord(
                            start_seconds=round(word.start, 6),
                            end_seconds=round(word.end, 6),
                            text=word.word.strip(),
                            confidence=None,
                        )
                    )
            if not mapped_words:
                raise _ResponseContractViolation(
                    path=f"$.segments[{segment_index}]",
                    code="segment_without_word_timestamps",
                    kind="mapping",
                )
            segments.append(
                ProviderSegment(
                    start_seconds=round(segment.start, 6),
                    end_seconds=round(segment.end, 6),
                    text=segment.text.strip(),
                    speaker=None,
                    confidence=None,
                    words=tuple(mapped_words),
                )
            )
        if len(assigned_word_indexes) != len(payload.words):
            raise _ResponseContractViolation(
                path="$.words",
                code="unbound_word_timestamps",
                kind="mapping",
            )

        duration_minutes = Decimal(str(payload.duration)) / Decimal("60")
        actual_cost = (duration_minutes * self._vnd_per_minute).quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        )
        cost_receipt = {
            "currency": "VND",
            "basis": "provider_native_duration",
            "duration_seconds": str(payload.duration),
            "vnd_per_minute": str(self._vnd_per_minute),
            "actual_cost_vnd": str(actual_cost),
            "estimated_cost_vnd": str(self.estimated_cost_vnd),
        }
        return ProviderTranscript(
            language=language,
            confidence=None,
            segments=tuple(segments),
            provenance={
                "fixture": False,
                "external_call": True,
                "paid_call": True,
                "provider": self.key,
                "model": self.model,
                "source_checksum": source_checksum,
                "request_sha256": request_sha256,
                "response_sha256": response_sha256,
                "provider_request_id": provider_request_id,
                "client_request_id": client_request_id,
                "latency_ms": latency_ms,
                "provider_duration_seconds": payload.duration,
                "cost_receipt": cost_receipt,
                "credential_alias_sha256": hashlib.sha256(
                    credential_alias.encode("utf-8")
                ).hexdigest(),
                "confidence_semantics": "provider_not_supplied_null_not_fabricated",
                "timestamp_source": "provider_native_word_and_segment",
                "original_evidence": True,
                "secret_recorded": False,
            },
            actual_cost_vnd=actual_cost,
        )
