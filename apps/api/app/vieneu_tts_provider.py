"""Local, preset-only adapter; no OpenAI identity, resolver or ambient secrets."""
from __future__ import annotations
import asyncio
import hashlib
import io
import copy
import time
import wave
from pathlib import Path
import httpx
from .content_service import canonical_bytes
from .providers import TTSNotConfiguredError, VoiceResult
from .tts_evidence import SpeechTimingEvidence, TTSArtifactEvidence
from .vieneu_contracts import VieNeuTTSProfile, SELECTED_VOICE, SELECTED_PROFILE_SHA


class VieNeuTTSProvider:
    def __init__(self, profile: VieNeuTTSProfile, *, local_execution_enabled=False, transport=None,
                 selected_voice_only=False):
        self.profile = VieNeuTTSProfile.model_validate(profile.model_dump(mode="json"))
        self.selected_voice_only = selected_voice_only
        if selected_voice_only and self.profile.sha256 != SELECTED_PROFILE_SHA:
            raise TTSNotConfiguredError("VIENEU_SELECTED_PROFILE_MISMATCH")
        self.model, self.voice = profile.model, profile.voice_id
        self.enabled, self.transport = local_execution_enabled, transport
        self._guard = None
        self._scope = None
        server = Path(__file__).resolve().parents[3] / "scripts/vieneu-local-server.py"
        self.server_sha = hashlib.sha256(server.read_bytes()).hexdigest()

    def bind_render_scope(self, *, workspace_id, project_id, content_version_id, render_id, before_unit):
        bound = copy.copy(self)
        bound._scope = dict(workspace_id=str(workspace_id), project_id=str(project_id),
            content_version_id=str(content_version_id), render_id=str(render_id))
        bound._guard = before_unit
        return bound

    async def _current(self):
        if self._guard:
            await self._guard()

    def for_render_voice(self, config):
        if config.speed != 1 or config.instructions:
            raise TTSNotConfiguredError("VIENEU_STYLE_OR_SPEED_UNSUPPORTED")
        # Historical generic 'vi' means the explicitly configured audition
        # preset. A named UI choice is validated, not aliased to another voice.
        voice = self.voice if config.voice == "vi" else config.voice
        if self.selected_voice_only and voice != SELECTED_VOICE:
            raise TTSNotConfiguredError("VIENEU_SELECTED_VOICE_CHANGE_REQUIRES_OWNER_REVIEW")
        selected = self.profile.model_dump(mode="json")
        selected["voice_id"] = voice
        return type(self)(VieNeuTTSProfile.model_validate(selected),
            local_execution_enabled=self.enabled, transport=self.transport,
            selected_voice_only=self.selected_voice_only)

    async def synthesize(self, *, text: str, language: str, output_path: Path) -> VoiceResult:
        if not self.enabled:
            raise TTSNotConfiguredError("VIENEU_LOCAL_EXECUTION_DISABLED")
        if language != "vi" or not isinstance(text, str) or not text.strip() or len(text) > 4096:
            raise ValueError("VIENEU_INPUT_INVALID")
        await self._current()
        payload = {"profile": self.profile.model_dump(mode="json"), "text": text,
                   "scope": self._scope, "format": "wav"}
        request_sha = hashlib.sha256(canonical_bytes(payload)).hexdigest()
        output_path = Path(output_path)
        cached = output_path.with_suffix(output_path.suffix + ".vieneu.json")
        if output_path.is_symlink() or cached.is_symlink():
            raise ValueError("VIENEU_OUTPUT_CUSTODY_INVALID")
        if output_path.exists() or cached.exists():
            if not output_path.is_file() or not cached.is_file():
                raise ValueError("VIENEU_OUTPUT_CONFLICT")
            evidence = TTSArtifactEvidence.model_validate_json(cached.read_bytes())
            if evidence.request_sha256 != request_sha or evidence.audio_sha256 != hashlib.sha256(output_path.read_bytes()).hexdigest():
                raise ValueError("VIENEU_OUTPUT_CONFLICT")
            await self._current()
            return VoiceResult(path=output_path, duration_seconds=evidence.decoded_duration_seconds,
                provider="vieneu-tts", voice=self.voice, evidence=evidence)
        started = time.monotonic()
        max_bytes = self.profile.max_audio_seconds * 48000 * 2 + 1024
        try:
            async with httpx.AsyncClient(transport=self.transport, trust_env=False,
                    follow_redirects=False, timeout=self.profile.timeout_seconds) as client:
                async with client.stream("POST", self.profile.endpoint + "/v1/audio/speech", json=payload) as response:
                    if response.status_code != 200:
                        raise TTSNotConfiguredError("VIENEU_LOCAL_SYNTHESIS_FAILED_NO_RETRY")
                    identity = response.headers.get("x-vieneu-profile-sha256")
                    server_sha = response.headers.get("x-vieneu-server-sha256", "")
                    if identity != self.profile.sha256 or server_sha != self.server_sha:
                        raise ValueError("VIENEU_SERVER_IDENTITY_MISMATCH")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > max_bytes:
                            raise ValueError("VIENEU_AUDIO_TOO_LARGE")
                    metadata_sha = response.headers.get("x-vieneu-normalization-sha256", "")
                    if len(metadata_sha) != 64 or any(c not in "0123456789abcdef" for c in metadata_sha):
                        raise ValueError("VIENEU_NORMALIZATION_PROVENANCE_MISSING")
            with wave.open(io.BytesIO(raw), "rb") as audio:
                if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) != (1, 2, 48000, "NONE"):
                    raise ValueError("VIENEU_AUDIO_FORMAT_INVALID")
                frames = audio.readframes(audio.getnframes())
                if not frames or len(frames) != audio.getnframes() * 2:
                    raise ValueError("VIENEU_AUDIO_EMPTY_OR_TRUNCATED")
                duration = len(frames) / 96000
            if duration > self.profile.max_audio_seconds:
                raise ValueError("VIENEU_AUDIO_TOO_LARGE")
        except asyncio.CancelledError:
            raise
        except (ValueError, TTSNotConfiguredError):
            raise
        except Exception:
            # Neither service response nor exception strings enter logs/evidence.
            raise TTSNotConfiguredError("VIENEU_LOCAL_OUTPUT_INVALID_OR_UNCERTAIN_NO_RETRY") from None
        await self._current()  # late completion must not revive stale content/approval
        audio_sha = hashlib.sha256(raw).hexdigest()
        evidence = TTSArtifactEvidence(version=3, profile=self.profile, profile_sha256=self.profile.sha256,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(), audio_sha256=audio_sha,
            request_sha256=request_sha, decoded_duration_seconds=duration,
            latency_seconds=time.monotonic()-started,
            timing=SpeechTimingEvidence(source="ESTIMATED_SEGMENT", reference_text=text,
                audio_sha256=audio_sha, duration_seconds=duration),
            usage={"local_service": True, "credential_mode": "none/local_service",
                "server_source_sha256": server_sha, "normalization_record_sha256": metadata_sha,
                "word_alignment": "WORD_ALIGNMENT_OPEN", "local_compute_cost": "NOT_METERED"},
            out_of_pocket_spend_vnd=0)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Fresh files only. No overwrite of a competing/stale job's artifacts.
        with output_path.open("xb") as target:
            target.write(raw)
        with cached.open("xb") as target:
            target.write(canonical_bytes(evidence.model_dump(mode="json")))
        return VoiceResult(path=output_path, duration_seconds=duration,
            provider="vieneu-tts", voice=self.voice, evidence=evidence)
