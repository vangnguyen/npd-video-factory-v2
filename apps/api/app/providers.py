from __future__ import annotations

import asyncio
import hashlib
import time
import wave
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, Field

from .models import VideoJobCreate
from .profiles import get_niche_profile
from .tts_evidence import ProductionTTSProfile, SpeechTimingEvidence, TTSArtifactEvidence
from .content_service import canonical_bytes
from .storyboard_content_provider import ProviderEnablementError, http_failure


class ScriptResult(BaseModel):
    title: str
    hook: str
    body: list[str]
    cta: str
    full_narration: str


class StoryboardScene(BaseModel):
    id: str
    order: int = Field(ge=1)
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)
    role: str
    narration: str
    on_screen_text: str | None = None
    visual_query: str


class StoryboardResult(BaseModel):
    scenes: list[StoryboardScene]

    @property
    def duration_seconds(self) -> float:
        return sum(scene.duration_seconds for scene in self.scenes)


class VoiceResult(BaseModel):
    path: Path
    duration_seconds: float = Field(gt=0)
    provider: str
    voice: str
    evidence: TTSArtifactEvidence | None = None


class ContentProvider(Protocol):
    async def generate_script(self, request: VideoJobCreate) -> ScriptResult: ...
    async def generate_storyboard(self, request: VideoJobCreate, script: ScriptResult) -> StoryboardResult: ...


class TTSProvider(Protocol):
    async def synthesize(self, *, text: str, language: str, output_path: Path) -> VoiceResult: ...


class DeterministicContentProvider:
    """Offline test/dev provider backed by configurable niche profiles."""

    async def generate_script(self, request: VideoJobCreate) -> ScriptResult:
        project_name = " ".join(part.capitalize() for part in request.project.split("-"))
        profile = get_niche_profile(request.niche)
        hook = profile.hook_pattern.format(
            topic=request.topic,
            project_name=project_name,
        )
        body = list(profile.body_patterns)
        narration = " ".join([hook, *body, request.content.cta])
        return ScriptResult(title=request.topic, hook=hook, body=body, cta=request.content.cta, full_narration=narration)

    async def generate_storyboard(self, request: VideoJobCreate, script: ScriptResult) -> StoryboardResult:
        count = 6 if request.video.duration_seconds >= 30 else 4
        duration = request.video.duration_seconds / count
        roles = list(get_niche_profile(request.niche).scene_roles)
        narration_parts = (
            [script.hook, *script.body, script.cta]
            if count == 6
            else [script.hook, script.body[0], script.body[2], script.cta]
        )
        scenes: list[StoryboardScene] = []
        for index in range(count):
            role = roles[index] if index < len(roles) else "information"
            narration = narration_parts[min(index, len(narration_parts) - 1)]
            scenes.append(
                StoryboardScene(
                    id=f"scene_{index + 1:02d}",
                    order=index + 1,
                    start_seconds=round(index * duration, 3),
                    duration_seconds=round(duration, 3),
                    role=role,
                    narration=narration,
                    on_screen_text=narration[:90],
                    visual_query=f"{request.project} {role}",
                )
            )
        scenes[-1].duration_seconds = round(request.video.duration_seconds - scenes[-1].start_seconds, 3)
        return StoryboardResult(scenes=scenes)


class TTSNotConfiguredError(RuntimeError):
    pass


class UnconfiguredVietnameseTTSProvider:
    def __init__(self, reason="Vietnamese TTS provider is not configured"):
        self.reason = reason

    async def synthesize(self, *, text: str, language: str, output_path: Path) -> VoiceResult:
        if language != "vi":
            raise ValueError("Only Vietnamese TTS is configured for this pipeline")
        raise TTSNotConfiguredError(self.reason)


class EspeakVietnameseTTSProvider:
    """Offline CI/dev TTS adapter using espeak-ng inside the worker container."""

    def __init__(self, *, voice: str = "vi", rate: int = 145):
        self.voice = voice
        self.rate = rate

    async def synthesize(self, *, text: str, language: str, output_path: Path) -> VoiceResult:
        if language != "vi":
            raise ValueError("Only Vietnamese TTS is configured for this pipeline")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(
            "espeak-ng",
            "-v",
            self.voice,
            "-s",
            str(self.rate),
            "-w",
            str(output_path),
            text,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"espeak-ng failed: {detail or process.returncode}")

        duration = _wav_duration(output_path)
        return VoiceResult(
            path=output_path,
            duration_seconds=duration,
            provider="espeak-ng",
            voice=self.voice,
        )


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        frame_rate = wav.getframerate()
        frame_width = wav.getnchannels() * wav.getsampwidth()
        chunks: list[bytes] = []
        while chunk := wav.readframes(65_536):
            chunks.append(chunk)
        frames = b"".join(chunks)
    if frame_rate <= 0 or frame_width <= 0 or len(frames) % frame_width:
        raise RuntimeError("TTS provider produced an invalid WAV payload")
    duration = (len(frames) // frame_width) / float(frame_rate)
    if duration <= 0:
        raise RuntimeError("TTS provider produced empty audio")
    return duration


class OpenAIVietnameseTTSProvider:
    """Production TTS adapter for OpenAI's /v1/audio/speech endpoint.

    CI tests inject an httpx MockTransport, so no external request is required.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini-tts",
        voice: str = "marin",
        instructions: str = "",
        speed: float = 1,
        base_url: str = "https://api.openai.com",
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not api_key.strip():
            raise TTSNotConfiguredError("OPENAI_API_KEY is required when TTS_PROVIDER=openai")
        self.api_key = api_key
        self.model = model
        self.voice = voice
        self.instructions = instructions
        self.profile = ProductionTTSProfile(provider_key="openai-tts", model=model,
            voice_id=voice, speed=speed, style_instructions=self.instructions,
            alignment_capability="none")
        self.speed = speed
        if base_url.rstrip("/") != "https://api.openai.com":
            raise TTSNotConfiguredError("TTS provider endpoint is not allowlisted")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def synthesize(self, *, text: str, language: str, output_path: Path) -> VoiceResult:
        if language != "vi":
            raise ValueError("Only Vietnamese TTS is configured for this pipeline")
        text = text.strip()
        if not text:
            raise ValueError("TTS input text is empty")
        if len(text) > 4096:
            raise ValueError("TTS input exceeds the 4096-character speech endpoint limit")

        payload: dict[str, object] = {
            "model": self.model,
            "voice": self.voice,
            "input": text,
            "response_format": "wav",
            "speed": self.speed,
        }
        if self.instructions:
            payload["instructions"] = self.instructions

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self.timeout_seconds, connect=15.0)
        started = time.perf_counter()
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            transport=self.transport,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            try:
                response = await client.post("/v1/audio/speech", headers=headers, json=payload)
            except httpx.RequestError:
                raise ProviderEnablementError("TRANSPORT", "TTS_TRANSPORT_UNCERTAIN") from None

        if response.status_code != 200:
            failure = http_failure(response.status_code)
            # Preserve the historical safe HTTP status diagnostic, never body.
            raise ProviderEnablementError(failure.category, f"HTTP {response.status_code}")

        if not response.content:
            raise ProviderEnablementError("MAPPING", "TTS_AUDIO_EMPTY")
        if len(response.content) > 32_000_000:
            raise ProviderEnablementError("MAPPING", "TTS_AUDIO_TOO_LARGE")
        if self.api_key.encode() in response.content:
            raise ProviderEnablementError("AUTH", "TTS_SECRET_ECHO_REJECTED")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
        if temp_path.is_symlink() or output_path.is_symlink():
            raise ProviderEnablementError("MAPPING", "TTS_OUTPUT_SYMLINK_REJECTED")
        temp_path.write_bytes(response.content)
        try:
            duration = _wav_duration(temp_path)
            temp_path.replace(output_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise ProviderEnablementError("MAPPING", "TTS_WAV_INVALID") from None

        return VoiceResult(
            path=output_path,
            duration_seconds=duration,
            provider="openai",
            voice=self.voice,
            evidence=TTSArtifactEvidence(profile=self.profile, profile_sha256=self.profile.sha256,
                text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                audio_sha256=hashlib.sha256(response.content).hexdigest(),
                request_sha256=hashlib.sha256(canonical_bytes(payload)).hexdigest(),
                decoded_duration_seconds=duration, latency_seconds=time.perf_counter()-started,
                timing=SpeechTimingEvidence(source="NONE", duration_seconds=duration),
                usage={"submitted_characters": len(text), "provider_usage": "NOT_RETURNED_BY_WAV_RESPONSE"}),
        )
