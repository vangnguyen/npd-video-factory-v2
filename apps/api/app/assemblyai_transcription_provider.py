"""One-upload/one-job AssemblyAI adapter for the direct Flow-A ASR path.

The adapter has no authority of its own.  Runtime policy, custody, budget and
Owner gates remain the responsibility of the single-dispatch controller.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import unicodedata
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Protocol

import httpx

from .assemblyai_asr_profile import (
    ASSEMBLYAI_CREDENTIAL_ALIAS,
    ASSEMBLYAI_LANGUAGE,
    ASSEMBLYAI_MODEL,
    AssemblyAIAsrProfile,
    assemblyai_profile_sha256,
    validate_assemblyai_profile,
)
from .auto_edit_models import MediaMetadata
from .auto_edit_providers import ProviderSegment, ProviderTranscript, ProviderWord
from .provider_safety import ProviderExecutionTrace, ProviderTimeoutEnvelope


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _lexical_tokens(value: str) -> tuple[str, ...]:
    """Token identity used only to prove provider text/word coverage.

    NFKC and case folding do not remove Vietnamese diacritics.  The provider
    transcript and the provider word payload remain byte-preserved elsewhere.
    """

    return tuple(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold()))


class AssemblyAITransport(Protocol):
    async def upload(self, audio: bytes, credential: str, timeout: float) -> str: ...
    async def create_transcript(
        self, request: dict[str, object], credential: str, timeout: float,
    ) -> dict[str, object]: ...
    async def get_transcript(
        self, transcript_id: str, credential: str, timeout: float,
    ) -> dict[str, object]: ...


class _HttpAssemblyAITransport:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _headers(credential: str) -> dict[str, str]:
        return {"authorization": credential}

    async def upload(self, audio: bytes, credential: str, timeout: float) -> str:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self.base_url + "/v2/upload", headers=self._headers(credential), content=audio,
            )
        response.raise_for_status()
        data = response.json()
        value = data.get("upload_url") if isinstance(data, dict) else None
        if not isinstance(value, str) or not value:
            raise ValueError("ASSEMBLYAI_UPLOAD_ACKNOWLEDGEMENT_INVALID")
        return value

    async def create_transcript(
        self, request: dict[str, object], credential: str, timeout: float,
    ) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self.base_url + "/v2/transcript", headers=self._headers(credential), json=request,
            )
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("ASSEMBLYAI_JOB_ACKNOWLEDGEMENT_INVALID")
        return value

    async def get_transcript(
        self, transcript_id: str, credential: str, timeout: float,
    ) -> dict[str, object]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                self.base_url + "/v2/transcript/" + transcript_id,
                headers=self._headers(credential),
            )
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise ValueError("ASSEMBLYAI_RESULT_INVALID")
        return value


class AssemblyAITranscriptionProvider:
    """Strict direct-ASR adapter with provider-native positive word intervals."""

    key = "assemblyai-transcription"
    capability = "asr"
    external_call = True
    paid = True

    def __init__(
        self,
        *,
        model: str,
        credential_alias: str,
        credential_resolver: Callable[[str], str],
        profile: AssemblyAIAsrProfile | dict[str, object],
        language: str = ASSEMBLYAI_LANGUAGE,
        base_url: str = "https://api.assemblyai.com",
        provider_http_timeout_seconds: float = 90.0,
        controller_hard_timeout_seconds: float = 180.0,
        max_file_bytes: int = 25_000_000,
        max_duration_seconds: float = 600.0,
        estimated_cost_vnd: Decimal = Decimal("0"),
        vnd_per_minute: Decimal = Decimal("139.5"),
        transport: AssemblyAITransport | None = None,
        poll_interval_seconds: float = 1.0,
        monotonic_clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.asr_prompt_profile = validate_assemblyai_profile(profile)
        if model != ASSEMBLYAI_MODEL:
            raise ValueError("ASSEMBLYAI_MODEL_NOT_ALLOWLISTED")
        if language != ASSEMBLYAI_LANGUAGE:
            raise ValueError("ASSEMBLYAI_LANGUAGE_NOT_ALLOWLISTED")
        if credential_alias != ASSEMBLYAI_CREDENTIAL_ALIAS:
            raise ValueError("ASSEMBLYAI_CREDENTIAL_ALIAS_NOT_ALLOWLISTED")
        if base_url.rstrip("/") != "https://api.assemblyai.com":
            raise ValueError("ASSEMBLYAI_API_ORIGIN_NOT_ALLOWLISTED")
        if not 1 <= max_file_bytes <= 25_000_000 or not 1 <= max_duration_seconds <= 3_600:
            raise ValueError("ASSEMBLYAI_INPUT_BOUND_INVALID")
        if estimated_cost_vnd < 0 or vnd_per_minute <= 0:
            raise ValueError("ASSEMBLYAI_COST_INVALID")
        envelope = ProviderTimeoutEnvelope(
            provider_http_timeout_seconds=provider_http_timeout_seconds,
            controller_hard_timeout_seconds=controller_hard_timeout_seconds,
        )
        self.model = model
        self.language = language
        self.credential_alias = credential_alias
        self.estimated_cost_vnd = estimated_cost_vnd
        self._vnd_per_minute = vnd_per_minute
        self.provider_http_timeout_seconds = envelope.provider_http_timeout_seconds
        self.controller_hard_timeout_seconds = envelope.controller_hard_timeout_seconds
        self.max_file_bytes = max_file_bytes
        self.max_duration_seconds = max_duration_seconds
        self.response_format = "json"
        self.timestamp_granularities = ("word",)
        self._credential_resolver = credential_resolver
        self._transport = transport or _HttpAssemblyAITransport(base_url)
        self._poll_interval_seconds = poll_interval_seconds
        self._monotonic = monotonic_clock
        self._upload_started = False
        self._job_creation_started = False
        self._transcript_id: str | None = None

    def __repr__(self) -> str:
        return "AssemblyAITranscriptionProvider(model='universal-3-5-pro', credential_alias=<redacted>)"

    async def transcribe(
        self,
        path: Path,
        *,
        metadata: MediaMetadata,
        checksum_sha256: str,
        execution_trace: ProviderExecutionTrace | None = None,
        expected_asr_prompt_profile: AssemblyAIAsrProfile | dict[str, object] | None = None,
        on_http_dispatch: Callable[[str, str], Awaitable[None]] | None = None,
        **_: object,
    ) -> ProviderTranscript:
        trace = execution_trace or ProviderExecutionTrace(monotonic=self._monotonic)
        trace.begin()
        profile = validate_assemblyai_profile(self.asr_prompt_profile)
        if expected_asr_prompt_profile is not None and profile != validate_assemblyai_profile(expected_asr_prompt_profile):
            raise ValueError("ASSEMBLYAI_PROFILE_BINDING_MISMATCH")
        if self._upload_started or self._job_creation_started or self._transcript_id is not None:
            raise ValueError("ASSEMBLYAI_OPERATION_ALREADY_DISPATCHED")
        if metadata.media_kind not in {"audio", "video"}:
            raise ValueError("ASSEMBLYAI_MEDIA_KIND_INVALID")
        duration = float(metadata.duration_seconds or 0)
        if duration <= 0 or duration > self.max_duration_seconds:
            raise ValueError("ASSEMBLYAI_DURATION_INVALID")
        if not path.is_file():
            raise FileNotFoundError(path)
        audio = path.read_bytes()
        if not audio or len(audio) > self.max_file_bytes:
            raise ValueError("ASSEMBLYAI_FILE_SIZE_INVALID")
        if hashlib.sha256(audio).hexdigest() != checksum_sha256:
            raise ValueError("ASSEMBLYAI_ASSET_HASH_MISMATCH")

        intent = {
            "provider": self.key,
            "model": self.model,
            "language_code": self.language,
            "profile_sha256": assemblyai_profile_sha256(profile),
            "asset_sha256": checksum_sha256,
            "asset_bytes": len(audio),
        }
        intent_sha256 = hashlib.sha256(_canonical(intent)).hexdigest()
        client_request_id = "assemblyai-" + intent_sha256[:32]

        # The resolver is invoked once.  No exception below includes its value.
        try:
            credential = self._credential_resolver(self.credential_alias).strip()
        except Exception:
            raise ValueError("ASSEMBLYAI_CREDENTIAL_UNAVAILABLE") from None
        if not credential:
            raise ValueError("ASSEMBLYAI_CREDENTIAL_UNAVAILABLE")

        started = self._monotonic()
        if on_http_dispatch is not None:
            await on_http_dispatch(intent_sha256, client_request_id)
        self._upload_started = True
        try:
            upload_url = await self._transport.upload(
                audio, credential, self.provider_http_timeout_seconds,
            )
        except Exception:
            raise ValueError("ASSEMBLYAI_UPLOAD_STATE_UNCERTAIN") from None
        upload_identity = hashlib.sha256(upload_url.encode()).hexdigest()
        request = {
            "audio_url": upload_url,
            "speech_models": [self.model],
            "language_code": self.language,
            "keyterms_prompt": list(profile.keyterms),
            "prompt": profile.context_prompt,
        }
        safe_request = {**request, "audio_url": "sha256:" + upload_identity}
        request_sha256 = hashlib.sha256(_canonical(safe_request)).hexdigest()
        self._job_creation_started = True
        try:
            acknowledgement = await self._transport.create_transcript(
                request, credential, self.provider_http_timeout_seconds,
            )
        except Exception:
            raise ValueError("PROVIDER_JOB_ID_UNCERTAIN") from None
        transcript_id = acknowledgement.get("id")
        if not isinstance(transcript_id, str) or not transcript_id:
            raise ValueError("PROVIDER_JOB_ID_UNCERTAIN")
        self._transcript_id = transcript_id

        while True:
            if self._monotonic() - started > self.controller_hard_timeout_seconds:
                raise ValueError("ASSEMBLYAI_OBSERVATION_UNCERTAIN")
            try:
                result = await self._transport.get_transcript(
                    transcript_id, credential, self.provider_http_timeout_seconds,
                )
            except Exception:
                raise ValueError("ASSEMBLYAI_OBSERVATION_UNCERTAIN") from None
            if result.get("id") != transcript_id:
                raise ValueError("ASSEMBLYAI_TRANSCRIPT_ID_SUBSTITUTION")
            status = result.get("status")
            if status == "completed":
                break
            if status == "error":
                raise ValueError("ASSEMBLYAI_PROVIDER_ERROR")
            if status not in {"queued", "processing"}:
                raise ValueError("ASSEMBLYAI_JOB_STATE_INVALID")
            await asyncio.sleep(self._poll_interval_seconds)

        text = result.get("text")
        words_payload = result.get("words")
        if not isinstance(text, str) or not text or not isinstance(words_payload, list) or not words_payload:
            raise ValueError("ASSEMBLYAI_COMPLETE_RESULT_INCOMPLETE")
        words: list[ProviderWord] = []
        previous_end_ms = 0
        for index, item in enumerate(words_payload):
            if not isinstance(item, dict):
                raise ValueError("ASSEMBLYAI_WORDS_PAYLOAD_INVALID")
            start, end, word = item.get("start"), item.get("end"), item.get("text")
            if type(start) is not int or type(end) is not int or not isinstance(word, str) or not word:
                raise ValueError("ASSEMBLYAI_WORDS_PAYLOAD_INVALID")
            if start < 0 or end <= start:
                raise ValueError("ASSEMBLYAI_WORD_INTERVAL_INVALID")
            if index and start < previous_end_ms:
                raise ValueError("ASSEMBLYAI_WORD_TIMING_NON_MONOTONIC")
            if end > round(duration * 1000) + 1:
                raise ValueError("ASSEMBLYAI_WORD_TIMING_OUT_OF_AUDIO")
            confidence = item.get("confidence")
            if confidence is not None and not isinstance(confidence, (int, float)):
                raise ValueError("ASSEMBLYAI_WORDS_PAYLOAD_INVALID")
            words.append(ProviderWord(
                start_seconds=start / 1000,
                end_seconds=end / 1000,
                text=word,
                confidence=float(confidence) if confidence is not None else None,
                timing_semantics="positive_interval",
            ))
            previous_end_ms = end
        word_tokens = tuple(
            token
            for item in words_payload
            for token in _lexical_tokens(str(item["text"]))
        )
        if word_tokens != _lexical_tokens(text):
            raise ValueError("ASSEMBLYAI_TRANSCRIPT_WORD_COVERAGE_INVALID")
        raw_sha = hashlib.sha256(_canonical(result)).hexdigest()
        transcript_sha = hashlib.sha256(text.encode()).hexdigest()
        words_sha = hashlib.sha256(_canonical(words_payload)).hexdigest()
        cost = (self._vnd_per_minute * Decimal(str(duration)) / Decimal("60")).quantize(Decimal("0.000001"))
        segment = ProviderSegment(
            start_seconds=words[0].start_seconds,
            end_seconds=words[-1].end_seconds,
            text=text,
            speaker=None,
            confidence=None,
            words=tuple(words),
        )
        return ProviderTranscript(
            language=self.language,
            confidence=None,
            segments=(segment,),
            provenance={
                "provider": self.key,
                "model": self.model,
                "profile_id": profile.profile_id,
                "profile_sha256": assemblyai_profile_sha256(profile),
                "request_sha256": request_sha256,
                "transcript_id": transcript_id,
                "provider_request_id": transcript_id,
                "raw_response_sha256": raw_sha,
                "response_sha256": raw_sha,
                "transcript_sha256": transcript_sha,
                "words_sha256": words_sha,
                "upload_identity_sha256": upload_identity,
                "word_timing_source": "provider_native_word_timestamps",
                "timestamp_source": "provider_native_word_timestamps",
                "segment_timing_source": "segment_envelope_derived_from_provider_word_bounds",
                "provider_transcript_immutable": True,
                "asr_prompt_profile": profile.model_dump(mode="json"),
                "asr_prompt_profile_sha256": assemblyai_profile_sha256(profile),
                "original_evidence": True,
                "secret_recorded": False,
                "provider_credit_debit": result.get("credit_debit"),
                "latency_ms": round((self._monotonic() - started) * 1000, 3),
            },
            actual_cost_vnd=cost,
        )
