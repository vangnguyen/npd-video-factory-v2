from __future__ import annotations

import hashlib
import json
import wave
from decimal import Decimal
from pathlib import Path

import pytest

from app.config import Settings
from app.provider_gate_loader import (
    OpenAIAsrGateBundle,
    ProviderApprovalRecord,
    canonical_sha256,
    load_verified_provider_gate_bundle,
)
from app.provider_safety import ProviderRightsEvidence


REPO_ROOT = Path(__file__).resolve().parents[3]
ACCEPTANCE_ROOT = REPO_ROOT / "docs" / "acceptance" / "v3-01"
BUNDLE_PATH = ACCEPTANCE_ROOT / "V3-01-GATE-RC11-OPENAI-ASR-A.json"
EXPECTED_RC = "207ff9fee5557eb0976f575c9263b61d995b20a0"
EXPECTED_BUNDLE_SHA = "4f8edd02ec62182404976de16e8d75b39ddbbbbe96c0d78efd46e3a97d6ace46"
EXPECTED_SCOPE_SHA = "7368b506b8971b190a1828ecab588dfe6b46a7e354d00c4d7cf2f35c1cc2c39a"

ASSETS = (
    {
        "name": "g03-asr-vi-owned-01.wav",
        "sha256": "fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef",
        "bytes": 5_800_940,
        "duration": 120.852,
        "transcript": "g03-asr-vi-owned-01.txt",
        "transcript_sha256": "585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e",
        "rights": "V3-01-RIGHTS-ASR-001.json",
        "rights_sha256": "5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091",
    },
    {
        "name": "g03-asr-vi-owned-02.wav",
        "sha256": "dce36c5246c17e0385842006dcb0088a8c97a79d3009796815c2564c075cf20b",
        "bytes": 6_460_396,
        "duration": 134.59066666666666,
        "transcript": "g03-asr-vi-owned-02.txt",
        "transcript_sha256": "0bff8c2b403cee452fac00f71b84759988ea515027fda6bd49be76ae382c1fef",
        "rights": "V3-01-RIGHTS-ASR-002.json",
        "rights_sha256": "972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323",
    },
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rc11_asr_bundle_loads_with_exact_hash_pins() -> None:
    assert _sha256(BUNDLE_PATH) == EXPECTED_BUNDLE_SHA
    scope = load_verified_provider_gate_bundle(
        BUNDLE_PATH,
        expected_bundle_sha256=EXPECTED_BUNDLE_SHA,
        expected_rc_commit=EXPECTED_RC,
        expected_rc_tag="vf-v3-01-rc11",
    )

    assert scope.execution_scope_sha256 == EXPECTED_SCOPE_SHA
    assert scope.provider_key == "openai-transcription"
    assert scope.model == "whisper-1"
    assert scope.capability == "asr"
    assert scope.credential_alias == "secret://openai/codex-video"
    assert scope.per_operation_limit_vnd == Decimal("500")
    assert scope.acceptance_window_limit_vnd == Decimal("1250")
    assert scope.vnd_per_minute == Decimal("162")
    assert scope.provider_http_timeout_seconds == 90
    assert scope.controller_hard_timeout_seconds == 120
    assert scope.allowed_operations[0].operation_key == (
        "v3-01-rc11-openai-transcription-asr-call-01"
    )
    assert scope.allowed_operations[1].operation_key == (
        "v3-01-rc11-openai-transcription-asr-call-02"
    )


def test_rc11_asr_bundle_embeds_exact_external_records() -> None:
    payload = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
    bundle = OpenAIAsrGateBundle.model_validate(payload)

    for key, filename in (
        ("credential_approval", "V3-01-APP-044.json"),
        ("budget_approval", "V3-01-APP-045.json"),
        ("rights_approval", "V3-01-APP-046.json"),
    ):
        external = ProviderApprovalRecord.model_validate(
            json.loads((ACCEPTANCE_ROOT / "approvals" / filename).read_text(encoding="utf-8"))
        )
        embedded = getattr(bundle, key)
        assert embedded.record == external
        assert embedded.record_sha256 == canonical_sha256(external)

    for index, asset in enumerate(ASSETS):
        external = ProviderRightsEvidence.model_validate(
            json.loads(
                (ACCEPTANCE_ROOT / "rights" / str(asset["rights"])).read_text(
                    encoding="utf-8"
                )
            )
        )
        embedded = bundle.rights_records[index]
        assert embedded.record == external
        assert embedded.record_sha256 == asset["rights_sha256"]
        assert embedded.record_sha256 == canonical_sha256(external)


def test_rc11_asr_assets_transcripts_and_owner_manifest_are_exact() -> None:
    manifest_path = ACCEPTANCE_ROOT / "assets" / "V3-01-RC11-ASR-ASSET-MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert _sha256(manifest_path) == (
        "0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0"
    )
    assert manifest["owner_confirmation"] == {
        "decision": "APPROVED",
        "recorded_at_utc": "2026-09-03T07:05:17Z",
        "content_matches_reference_transcript": True,
        "voice_processing_consent": True,
        "publishing_allowed": False,
        "training_allowed": False,
        "resale_allowed": False,
    }

    modeled_total = Decimal("0")
    for index, asset in enumerate(ASSETS):
        wav_path = ACCEPTANCE_ROOT / "assets" / str(asset["name"])
        transcript_path = ACCEPTANCE_ROOT / "transcripts" / str(asset["transcript"])
        assert _sha256(wav_path) == asset["sha256"]
        assert wav_path.stat().st_size == asset["bytes"]
        assert _sha256(transcript_path) == asset["transcript_sha256"]

        with wave.open(str(wav_path), "rb") as recording:
            assert recording.getnchannels() == 1
            assert recording.getframerate() == 24_000
            assert recording.getsampwidth() == 2
            duration = recording.getnframes() / recording.getframerate()
        assert duration == pytest.approx(asset["duration"], abs=0.000001)
        assert 90 <= duration <= 180
        assert manifest["assets"][index]["sha256"] == asset["sha256"]
        assert manifest["assets"][index]["reference_transcript_sha256"] == (
            asset["transcript_sha256"]
        )
        assert manifest["assets"][index]["critical_terms"]
        modeled_total += Decimal(str(duration)) * Decimal("162") / Decimal("60")

    assert modeled_total < Decimal("1250")
    assert all(
        Decimal(str(asset["duration"])) * Decimal("162") / Decimal("60")
        < Decimal("500")
        for asset in ASSETS
    )


def test_rc11_asr_checked_in_defaults_remain_fail_closed() -> None:
    settings = Settings(_env_file=None)
    assert settings.transcription_provider == "fixture"
    assert settings.openai_transcription_model == ""
    assert settings.provider_verified_gate_bundle_enabled is False
    assert settings.provider_external_execution_enabled is False
    assert settings.provider_paid_execution_enabled is False
    assert settings.provider_global_kill_switch_engaged is True
    assert settings.provider_per_operation_limit_vnd == Decimal("0")
    assert settings.provider_daily_limit_vnd == Decimal("0")
