from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from app.asr_prompt_profile import prompt_profile_sha256, w1_prompt_profile

REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs/acceptance/v3-01"
TERMS = ("Ngọc Phương Đông", "Vinhomes Green Paradise", "Cần Giờ", "tham quan sa bàn", "chính sách bán hàng")


@pytest.fixture(scope="module")
def evaluator():
    path = DOCS / "tools/v3_01_asr_post_run_evaluator.py"
    spec = importlib.util.spec_from_file_location("w1_quality_evaluator_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    def bound_evaluate(payload, policy=None, *, expected_asr_prompt_profile_id="asr-whisper-vi-w1-v1"):
        return module.evaluate(payload, policy, expected_asr_prompt_profile_id=expected_asr_prompt_profile_id)
    return SimpleNamespace(evaluate=bound_evaluate, AsrEvaluationPolicy=module.AsrEvaluationPolicy)


def synthetic_payload(slot=2):
    """Synthetic success envelope for OFFLINE tests; never an acceptance operation receipt."""
    payload = json.loads((DOCS / "fixtures/asr-post-run/pass.json").read_text(encoding="utf-8"))
    manifest = json.loads((DOCS / "assets/V3-01-RC11-ASR-ASSET-MANIFEST.json").read_text(encoding="utf-8"))
    row = manifest["assets"][slot - 1]
    reference = (REPO / row["reference_transcript_path"]).read_text(encoding="utf-8")
    payload["operation"]["operation_id"] = f"synthetic-w1-quality-unit-slot-{slot}"
    profile = w1_prompt_profile()
    payload["binding"].update(
        provider="openai-transcription", model="whisper-1", capability="asr", language="vi",
        asset_sha256=row["sha256"], asset_duration_seconds=row["duration_seconds"],
        asr_prompt_profile=profile.model_dump(mode="json"),
        asr_prompt_profile_sha256=prompt_profile_sha256(profile),
    )
    payload["reference"].update(
        transcript=reference, transcript_path=row["reference_transcript_path"],
        transcript_sha256=row["reference_transcript_sha256"], critical_terms=row["critical_terms"],
    )
    transcript = payload["provider_transcript"]
    transcript.update(text=reference, provider_duration_seconds=row["duration_seconds"])
    transcript["provenance"].update(
        asr_prompt_profile=profile.model_dump(mode="json"),
        asr_prompt_profile_sha256=prompt_profile_sha256(profile),
    )
    words = reference.split()
    step = row["duration_seconds"] / len(words)
    transcript["segments"] = [{
        "start_seconds": 0, "end_seconds": row["duration_seconds"], "text": reference,
        "speaker": None, "confidence": None,
        "words": [{"start_seconds": i * step, "end_seconds": (i + 1) * step,
                   "text": word, "confidence": None} for i, word in enumerate(words)],
    }]
    return payload


@pytest.mark.parametrize("slot", [1, 2])
def test_same_canonical_profile_and_exact_reference_offline_pass(evaluator, slot):
    payload = synthetic_payload(slot)
    before = copy.deepcopy(payload)
    schema = json.loads((DOCS / "schemas/asr-post-run-input.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    result = evaluator.evaluate(payload)
    assert result["verdict"] == "PASS", result["reasons"]
    assert result["critical_terms"]["normalized_recall"] == 1.0
    assert len(result["critical_terms"]["terms"]) == 8
    guard = result["w1_prompt_quality"]
    assert guard["insertion_guard_passed"] and guard["negative_control"] == (slot == 2)
    assert guard["human_audio_review"] == "NOT_PERFORMED_BY_MACHINE_GUARD"
    assert payload == before
    Draft202012Validator(json.loads((DOCS / "schemas/asr-post-run-evaluation.schema.json").read_text())).validate(result)


@pytest.mark.parametrize("term", TERMS)
def test_asset02_prompt_keyword_insertion_fails_even_with_all_eight_terms(evaluator, term):
    payload = synthetic_payload()
    payload["provider_transcript"]["text"] += " " + unicodedata.normalize("NFD", term.upper())
    result = evaluator.evaluate(payload)
    assert result["critical_terms"]["normalized_recall"] == 1.0
    assert result["wer"]["passed"]
    assert result["verdict"] == "FAIL"
    assert "W1_PROMPT_TERM_INSERTION" in result["reasons"]["fail"]
    assert any(row["excess_count"] == 1 for row in result["w1_prompt_quality"]["terms"])


def test_asset01_duplicate_prompt_phrase_also_fails(evaluator):
    payload = synthetic_payload(1)
    payload["provider_transcript"]["text"] += " Ngọc Phương Đông"
    result = evaluator.evaluate(payload)
    assert "W1_PROMPT_TERM_INSERTION" in result["reasons"]["fail"]


@pytest.mark.parametrize("source", ["binding", "provenance"])
@pytest.mark.parametrize("key", ["asr_prompt_profile", "asr_prompt_profile_sha256"])
@pytest.mark.parametrize("mode", ["missing", "null", "tamper"])
def test_missing_or_mismatched_profile_cannot_downgrade_to_w0(evaluator, source, key, mode):
    payload = synthetic_payload()
    target = payload["binding"] if source == "binding" else payload["provider_transcript"]["provenance"]
    if mode == "missing":
        target.pop(key)
    elif mode == "null":
        target[key] = None
    elif key.endswith("sha256"):
        target[key] = "0" * 64
    else:
        target[key]["prompt"] += " other"
    result = evaluator.evaluate(payload)
    assert result["verdict"] == "FAIL"
    assert "W1_PROFILE_BINDING_INVALID" in result["reasons"]["fail"]


@pytest.mark.parametrize("field", ["transcript", "transcript_path", "transcript_sha256", "critical_terms", "asset_sha256"])
def test_exact_reference_and_eight_term_set_cannot_be_replaced(evaluator, field):
    payload = synthetic_payload()
    if field == "asset_sha256":
        payload["binding"][field] = "1" * 64
    elif field == "critical_terms":
        payload["reference"][field] = payload["reference"][field][:7]
    else:
        payload["reference"][field] += "tampered"
    result = evaluator.evaluate(payload)
    assert "W1_APPROVED_REFERENCE_BINDING_INVALID" in result["reasons"]["fail"]


@pytest.mark.parametrize("policy", [{"maximum_wer": 0.16}, {"minimum_critical_term_recall": 0.875}])
def test_w1_does_not_allow_relaxed_quality_policy(evaluator, policy):
    result = evaluator.evaluate(synthetic_payload(), evaluator.AsrEvaluationPolicy(**policy))
    assert "W1_QUALITY_THRESHOLD_RELAXATION_FORBIDDEN" in result["reasons"]["fail"]


def test_missing_receipt_still_review_and_secret_failure_still_fail(evaluator):
    payload = synthetic_payload()
    payload["receipts"]["cost_receipt_present"] = False
    assert evaluator.evaluate(payload)["verdict"] == "REVIEW_REQUIRED"
    payload["receipts"]["secret_scan"].update(status="FAIL", finding_count=1)
    assert evaluator.evaluate(payload)["verdict"] == "FAIL"
    payload = synthetic_payload()
    payload["provider_transcript"] = None
    result = evaluator.evaluate(payload)
    assert result["verdict"] == "REVIEW_REQUIRED"
    assert "W1_PROVIDER_TRANSCRIPT_UNAVAILABLE" in result["reasons"]["review_required"]


def test_input_schema_profile_constant_tracks_canonical_model():
    schema = json.loads((DOCS / "schemas/asr-post-run-input.schema.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["w1_profile"]["const"] == w1_prompt_profile().model_dump(mode="json")


def test_historical_rc15_w0_is_never_reclassified_or_rewritten(evaluator):
    receipt = DOCS / "evidence/rc15-asr-operation-1/operation-1-evaluator-input.json"
    before = receipt.read_bytes()
    result = evaluator.evaluate(json.loads(before), expected_asr_prompt_profile_id=None)
    assert result["verdict"] == "FAIL"
    assert result["critical_terms"]["normalized_recall"] == 0.625
    assert "w1_prompt_quality" not in result
    assert hashlib.sha256(receipt.read_bytes()).hexdigest() == hashlib.sha256(before).hexdigest()


def test_stripping_all_receipt_metadata_cannot_disable_trusted_w1_guard(evaluator):
    payload = synthetic_payload()
    payload["provider_transcript"]["text"] += " Ngọc Phương Đông"
    for target in (payload["binding"], payload["provider_transcript"]["provenance"]):
        target.pop("asr_prompt_profile")
        target.pop("asr_prompt_profile_sha256")
    result = evaluator.evaluate(payload)
    assert result["verdict"] == "FAIL"
    assert "W1_PROFILE_BINDING_INVALID" in result["reasons"]["fail"]
    assert "W1_PROMPT_TERM_INSERTION" in result["reasons"]["fail"]


@pytest.mark.parametrize("expected", [None, "", "W2"])
def test_w1_receipt_cannot_self_select_or_change_expected_profile(evaluator, expected):
    result = evaluator.evaluate(synthetic_payload(), expected_asr_prompt_profile_id=expected)
    assert result["verdict"] == "FAIL"
    assert "W1_PROFILE_BINDING_INVALID" in result["reasons"]["fail"]
