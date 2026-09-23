"""Offline Vietnamese TTS readiness fixtures; never a provider execution path.

The two WAVs are deliberately non-speech tones.  They exercise artifact,
binding, and review-package plumbing without suggesting voice acceptance.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import unicodedata
import wave
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from .providers import TTSProvider, VoiceResult


SCRIPT_PATHS = (
    "docs/acceptance/v3-01/templates/V3-01-TTS-REFERENCE-SCRIPT-01.txt",
    "docs/acceptance/v3-01/templates/V3-01-TTS-REFERENCE-SCRIPT-02.txt",
)
PRONUNCIATION_PATH = "docs/acceptance/v3-01/templates/V3-01-TTS-PRONUNCIATION-SET.json"
MOCK_MODEL = "deterministic-tone-fixture-v1"
MOCK_VOICE = "non-speech-fixture"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def estimate_character_cost_vnd(
    text: str,
    *,
    usd_per_million_characters: Decimal,
    planning_fx_vnd_per_usd: Decimal,
) -> int:
    """Conservative whole-VND estimate, ignoring any free-tier allowance.

    Price and FX are explicit inputs because neither is execution authority.
    The caller must count the actual submitted payload if SSML is added later.
    """
    if not text or unicodedata.normalize("NFC", text) != text:
        raise ValueError("billable text must be nonempty NFC Unicode")
    if usd_per_million_characters <= 0 or planning_fx_vnd_per_usd <= 0:
        raise ValueError("price and planning FX must be positive")
    amount = Decimal(len(text)) * usd_per_million_characters * planning_fx_vnd_per_usd / Decimal(1_000_000)
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


class MockToneTTSAdapter:
    """TTSProvider-compatible fixture with no network, secret, or spend path."""

    voice = MOCK_VOICE

    async def synthesize(self, *, text: str, language: str, output_path: Path) -> VoiceResult:
        if language != "vi" or not text.strip():
            raise ValueError("fixture requires nonempty Vietnamese text")
        if unicodedata.normalize("NFC", text) != text:
            raise ValueError("fixture text must be NFC Unicode")
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        frequency = 250 + int.from_bytes(digest[:2], "big") % 550
        sample_rate = 16_000
        frames = sample_rate // 2
        pcm = bytearray()
        for index in range(frames):
            fade = min(1.0, index / 240, (frames - 1 - index) / 240)
            sample = int(3500 * fade * math.sin(2 * math.pi * frequency * index / sample_rate))
            pcm.extend(struct.pack("<h", sample))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm)
        return VoiceResult(
            path=output_path,
            duration_seconds=0.5,
            provider=MOCK_MODEL,
            voice=MOCK_VOICE,
        )


def _load_inputs(repo_root: Path) -> tuple[list[tuple[str, str, str]], str, list[str]]:
    scripts: list[tuple[str, str, str]] = []
    for relative in SCRIPT_PATHS:
        raw = (repo_root / relative).read_bytes()
        text = raw.decode("utf-8")
        if not text.strip() or unicodedata.normalize("NFC", text) != text:
            raise ValueError("reference script is empty or not NFC")
        scripts.append((relative, text, sha256_bytes(raw)))
    if scripts[0][2] == scripts[1][2]:
        raise ValueError("the two reference scripts must be distinct")

    pronunciation_raw = (repo_root / PRONUNCIATION_PATH).read_bytes()
    pronunciation = json.loads(pronunciation_raw)
    if pronunciation.get("record_kind") != "vietnamese_tts_pronunciation_set":
        raise ValueError("pronunciation set has the wrong record kind")
    terms = [item["text"] for item in pronunciation["terms"]]
    if not terms or len(set(terms)) != len(terms):
        raise ValueError("pronunciation terms must be unique and nonempty")
    combined = " ".join(item[1] for item in scripts)
    if any(term not in combined for term in terms):
        raise ValueError("a critical pronunciation term is absent from both scripts")
    return scripts, sha256_bytes(pronunciation_raw), terms


async def build_mock_two_output_manifest(repo_root: Path, output_dir: Path) -> dict[str, object]:
    """Create only two non-speech fixture WAVs and a reproducible manifest."""
    scripts, pronunciation_sha, terms = _load_inputs(repo_root)
    adapter: TTSProvider = MockToneTTSAdapter()
    outputs: list[dict[str, object]] = []
    for index, (relative, text, script_sha) in enumerate(scripts, 1):
        name = f"tts-mock-{index:02d}.wav"
        result = await adapter.synthesize(text=text, language="vi", output_path=output_dir / name)
        raw = result.path.read_bytes()
        with wave.open(str(result.path), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16_000:
                raise ValueError("fixture WAV format mismatch")
            if wav.getnframes() != 8_000:
                raise ValueError("fixture WAV duration mismatch")
        outputs.append(
            {
                "slot": index,
                "script_path": relative,
                "script_sha256": script_sha,
                "script_characters_including_newline": len(text),
                "audio_file": name,
                "audio_sha256": sha256_bytes(raw),
                "duration_seconds": result.duration_seconds,
                "provider": result.provider,
                "voice": result.voice,
                "human_voice_evidence": False,
            }
        )
    if outputs[0]["audio_sha256"] == outputs[1]["audio_sha256"]:
        raise ValueError("mock outputs must be distinct")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "record_kind": "v3_01_tts_two_output_mock_readiness",
        "status": "MOCK_ONLY_NOT_HUMAN_ACCEPTED",
        "model": MOCK_MODEL,
        "voice": MOCK_VOICE,
        "language": "vi",
        "pronunciation_set_path": PRONUNCIATION_PATH,
        "pronunciation_set_sha256": pronunciation_sha,
        "critical_terms": terms,
        "outputs": outputs,
        "g11_tts_review": {
            "status": "NOT_REVIEWED",
            "required_devices": ["headphones", "phone_speaker"],
            "required_profile": "female_perceived_25_30_soft_warm_professional",
            "native_vietnamese": "NOT_TESTED",
            "proper_name_pronunciation": "NOT_TESTED",
            "foreign_accent": "NOT_TESTED",
            "robotic_cadence": "NOT_TESTED",
            "swallowed_syllables": "NOT_TESTED",
        },
        "safety": {
            "credentials_read": 0,
            "budget_reserved_vnd": 0,
            "real_provider_calls": 0,
            "actual_cost_vnd": 0,
            "real_provider_selected": False,
            "production_eligible": False,
        },
    }
    manifest["manifest_sha256"] = sha256_bytes(canonical_json_bytes(manifest))
    return manifest
