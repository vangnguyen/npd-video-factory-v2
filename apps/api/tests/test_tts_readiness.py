from __future__ import annotations

import asyncio
import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from app.tts_readiness import (
    PRONUNCIATION_PATH,
    SCRIPT_PATHS,
    MockToneTTSAdapter,
    build_mock_two_output_manifest,
    canonical_json_bytes,
    estimate_character_cost_vnd,
    sha256_bytes,
)


REPO = Path(__file__).resolve().parents[3]


def test_two_output_mock_is_distinct_deterministic_and_not_human_evidence(tmp_path: Path) -> None:
    first = asyncio.run(build_mock_two_output_manifest(REPO, tmp_path / "first"))
    second = asyncio.run(build_mock_two_output_manifest(REPO, tmp_path / "second"))
    assert first == second
    assert len(first["outputs"]) == 2
    assert first["outputs"][0]["script_sha256"] != first["outputs"][1]["script_sha256"]
    assert first["outputs"][0]["audio_sha256"] != first["outputs"][1]["audio_sha256"]
    assert first["status"] == "MOCK_ONLY_NOT_HUMAN_ACCEPTED"
    assert first["g11_tts_review"]["status"] == "NOT_REVIEWED"
    assert first["safety"] == {
        "credentials_read": 0,
        "budget_reserved_vnd": 0,
        "real_provider_calls": 0,
        "actual_cost_vnd": 0,
        "real_provider_selected": False,
        "production_eligible": False,
    }
    digest = first.pop("manifest_sha256")
    assert digest == sha256_bytes(canonical_json_bytes(first))
    for index in (1, 2):
        name = f"tts-mock-{index:02d}.wav"
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes()


def test_mock_adapter_fails_closed_on_language_and_empty_input(tmp_path: Path) -> None:
    adapter = MockToneTTSAdapter()
    with pytest.raises(ValueError, match="Vietnamese"):
        asyncio.run(adapter.synthesize(text="xin chào", language="en", output_path=tmp_path / "x.wav"))
    with pytest.raises(ValueError, match="nonempty"):
        asyncio.run(adapter.synthesize(text="  ", language="vi", output_path=tmp_path / "x.wav"))
    assert not (tmp_path / "x.wav").exists()


def test_mock_adapter_does_not_read_credentials_or_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("fixture attempted network access")

    # Windows asyncio creates its own loopback socketpair.  Create the loop
    # before forbidding application network access, then restore before close.
    loop = asyncio.new_event_loop()
    try:
        with monkeypatch.context() as guarded:
            guarded.setattr(socket.socket, "connect", forbidden)
            guarded.setenv("OPENAI_API_KEY", "test-sentinel-not-a-real-key")
            manifest = loop.run_until_complete(build_mock_two_output_manifest(REPO, tmp_path))
    finally:
        loop.close()
    assert manifest["safety"]["credentials_read"] == 0
    assert "test-sentinel" not in json.dumps(manifest)


def test_missing_critical_term_blocks_harness(tmp_path: Path) -> None:
    for relative in SCRIPT_PATHS:
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("Xin chào Việt Nam.", encoding="utf-8")
    pronunciation = tmp_path / PRONUNCIATION_PATH
    pronunciation.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / PRONUNCIATION_PATH, pronunciation)
    with pytest.raises(ValueError, match="distinct"):
        asyncio.run(build_mock_two_output_manifest(tmp_path, tmp_path / "out"))
    (tmp_path / SCRIPT_PATHS[1]).write_text("Một đoạn văn khác.", encoding="utf-8")
    with pytest.raises(ValueError, match="critical pronunciation term"):
        asyncio.run(build_mock_two_output_manifest(tmp_path, tmp_path / "out"))


def test_cost_model_counts_all_unicode_characters_and_ignores_free_tier() -> None:
    assert estimate_character_cost_vnd(
        "Cần Giờ\n",
        usd_per_million_characters=Decimal("16"),
        planning_fx_vnd_per_usd=Decimal("27000"),
    ) == 4
    with pytest.raises(ValueError, match="NFC"):
        estimate_character_cost_vnd(
            "Ca\u0302n",
            usd_per_million_characters=Decimal("16"),
            planning_fx_vnd_per_usd=Decimal("27000"),
        )
    with pytest.raises(ValueError, match="positive"):
        estimate_character_cost_vnd(
            "Cần Giờ",
            usd_per_million_characters=Decimal("0"),
            planning_fx_vnd_per_usd=Decimal("27000"),
        )


def test_g11_tts_package_cannot_claim_mock_voice_acceptance() -> None:
    path = REPO / "docs/acceptance/v3-01/reviews/master-parallel-tts/g11-tts-listening.template.json"
    review = json.loads(path.read_text(encoding="utf-8"))
    assert review["decision"] == "REVIEW_REQUIRED"
    assert review["human_voice_accepted"] is False
    assert review["provider"] is None
    assert review["model"] is None
    assert review["voice"] is None
    assert len(review["outputs"]) == 2
    assert all(output["real_audio_sha256"] is None for output in review["outputs"])
    assert all(not output["headphones_full_listen"] for output in review["outputs"])
    assert all(not output["phone_speaker_full_listen"] for output in review["outputs"])
    assert all(term["result"] == "NOT_REVIEWED" for output in review["outputs"] for term in output["critical_terms"])
    assert review["final_full_video_g11"] == "SEPARATE_27_CHECK_GATE_REQUIRED"
    assert review["provider_calls"] == 0


def test_review_template_script_hashes_are_exact() -> None:
    path = REPO / "docs/acceptance/v3-01/reviews/master-parallel-tts/g11-tts-listening.template.json"
    review = json.loads(path.read_text(encoding="utf-8"))
    bindings = review["input_bindings"]
    for index, relative in enumerate(SCRIPT_PATHS, 1):
        assert bindings[f"script_{index:02d}_sha256"] == sha256_bytes((REPO / relative).read_bytes())
        text = (REPO / relative).read_text(encoding="utf-8")
        expected = {item["text"] for item in json.loads((REPO / PRONUNCIATION_PATH).read_text(encoding="utf-8"))["terms"] if item["text"] in text}
        actual = {term["text"] for term in review["outputs"][index - 1]["critical_terms"]}
        assert actual == expected
    assert bindings["pronunciation_set_sha256"] == sha256_bytes((REPO / PRONUNCIATION_PATH).read_bytes())
