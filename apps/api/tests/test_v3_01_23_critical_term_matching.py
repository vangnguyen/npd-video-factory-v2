from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import unicodedata
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from app.auto_edit_providers import (
    PositiveDurationTranscriptRequired,
    ProviderSegment,
    ProviderTranscript,
    ProviderWord,
    require_positive_duration_transcript,
)


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs" / "acceptance" / "v3-01"
FIXTURE = DOCS / "fixtures" / "asr-post-run" / "pass.json"
TERMS = (
    "Ngọc Phương Đông",
    "Vinhomes Green Paradise",
    "Cần Giờ",
    "đăng ký tư vấn",
    "tham quan sa bàn",
    "ngân sách dự kiến",
    "chính sách bán hàng",
    "đồng Việt Nam",
)
PREFIX = (
    "Đây là dữ liệu giả lập dùng để kiểm tra bộ đánh giá ngoại tuyến. "
    "Những câu này giữ đủ ngữ cảnh để lỗi tên riêng không bị che bởi "
    "ngưỡng tỷ lệ lỗi từ chung. Nội dung cần kiểm tra là: "
)


@pytest.fixture(scope="module")
def evaluator() -> ModuleType:
    path = DOCS / "tools" / "v3_01_asr_post_run_evaluator.py"
    spec = importlib.util.spec_from_file_location("v3_01_23_term_matcher_tests", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fixture() -> dict[str, Any]:
    # Only synthetic copies are edited. Original fixtures and historical receipts
    # are never rewritten, and no provider, credential or live ledger is used.
    return copy.deepcopy(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _text_fixture(
    *, reference: str, hypothesis: str, terms: tuple[str, ...]
) -> dict[str, Any]:
    payload = _fixture()
    payload["operation"]["operation_id"] = "fixture-v3-01-23-critical-term-test"
    payload["reference"] = {
        "transcript": reference,
        "transcript_path": "fixture://v3-01-23/synthetic-reference",
        "transcript_sha256": hashlib.sha256(reference.encode("utf-8")).hexdigest(),
        "critical_terms": list(terms),
    }
    # These evenly spaced intervals are synthetic fixture input, not alignment
    # of real audio or a reconstruction of any RC operation's timestamps.
    tokens = hypothesis.split()
    step = 5.8 / len(tokens)
    payload["provider_transcript"]["text"] = hypothesis
    payload["provider_transcript"]["segments"] = [
        {
            "start_seconds": 0.0,
            "end_seconds": 5.8,
            "text": hypothesis,
            "speaker": None,
            "confidence": None,
            "words": [
                {
                    "start_seconds": round(index * step, 6),
                    "end_seconds": round((index + 1) * step, 6),
                    "text": token,
                    "confidence": None,
                }
                for index, token in enumerate(tokens)
            ],
        }
    ]
    return payload


def _evaluate_without_mutation(
    evaluator: ModuleType, payload: dict[str, Any]
) -> dict[str, Any]:
    before = copy.deepcopy(payload)
    fixture_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    evaluator._validate_input(payload, DOCS / "schemas" / "asr-post-run-input.schema.json")
    result = evaluator.evaluate(payload)
    assert payload == before
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == fixture_hash
    assert evaluator.evaluate(payload) == result
    assert result["normalization"] == {
        "unicode": "NFKC",
        "case": "casefold",
        "punctuation_and_symbols": "replace_with_space",
        "whitespace": "collapse_by_tokenization",
        "vietnamese_diacritics": "preserved",
    }
    assert result["safety"]["provider_calls_performed_by_evaluator"] == 0
    assert result["safety"]["credential_reads_performed_by_evaluator"] == 0
    assert result["safety"]["budget_reserved_vnd_by_evaluator"] == "0"
    assert result["safety"]["spend_vnd_by_evaluator"] == "0"
    assert result["safety"]["runtime_authority_granted"] is False
    assert result["safety"]["production_verdict"] == "NO-GO"
    assert result["critical_terms"]["critical_terms_included_in_wer"] is True
    assert result["timestamps"]["passed"] is True
    return result


@pytest.mark.parametrize(
    ("term", "hypothesis_phrase", "matches"),
    [
        pytest.param("Ngọc Phương Đông", "Ngọc Phương Đông", True, id="exact-vietnamese"),
        pytest.param("Ngọc Phương Đông", "ngỌc PHƯƠNG đông", True, id="casefold"),
        pytest.param("Ngọc Phương Đông", "Ngọc, Phương—Đông!", True, id="punctuation"),
        pytest.param("Ngọc Phương Đông", "Ngọc \tPhương\nĐông", True, id="whitespace"),
        pytest.param(
            "Ngọc Phương Đông",
            unicodedata.normalize("NFD", "Ngọc Phương Đông"),
            True,
            id="nfc-nfd-equivalence",
        ),
        pytest.param("Ngọc Phương Đông", "Ngọc Đông", False, id="missing-word"),
        pytest.param(
            "Vinhomes Green Paradise", "Vinhome Bring Paradise", False, id="wrong-project"
        ),
        pytest.param("Cần Giờ", "Căn Giờ", False, id="diacritic-semantic-difference"),
        pytest.param("Ngọc Phương Đông", "Ngọc Phương Đôngx", False, id="partial-token"),
        pytest.param("Ngọc Phương Đông", "Phương Ngọc Đông", False, id="reordered-words"),
        pytest.param("Ngọc Phương Đông", "Ngọc Công ty Phương Đông", False, id="inserted-words"),
        pytest.param(
            "Ngọc Phương Đông",
            "Ngọc Phương Đông Ngọc Phương Đông",
            True,
            id="duplicate-occurrence-does-not-inflate-recall",
        ),
        pytest.param("Ngọc Phương Đông", "NgọcPhương Đông", False, id="joined-tokens"),
        pytest.param(
            "Vinhomes Green Paradise", "Vin homes Green Paradise", False, id="split-token"
        ),
        pytest.param(
            "Ngọc Phương Đông", "Ngọc Phương Phương Đông", False, id="internal-duplicate"
        ),
    ],
)
def test_critical_term_requires_contiguous_diacritic_preserving_tokens(
    evaluator: ModuleType, term: str, hypothesis_phrase: str, matches: bool
) -> None:
    payload = _text_fixture(
        reference=PREFIX + term,
        hypothesis=PREFIX + hypothesis_phrase,
        terms=(term,),
    )
    result = _evaluate_without_mutation(evaluator, payload)
    (row,) = result["critical_terms"]["terms"]
    assert row["present_in_reference"] is True
    assert row["normalized_match"] is matches
    assert row["passed"] is matches
    assert result["critical_terms"]["normalized_recall"] == (1.0 if matches else 0.0)
    assert result["wer"]["passed"] is True
    assert result["wer"]["threshold"] == 0.15
    assert result["verdict"] == ("PASS" if matches else "FAIL")
    assert result["reasons"]["fail"] == (
        [] if matches else ["CRITICAL_TERM_RECALL_BELOW_1_0"]
    )


@pytest.mark.parametrize(
    ("replacements", "expected_count", "expected_verdict"),
    [
        pytest.param({}, 8, "PASS", id="8-of-8-pass"),
        pytest.param(
            {"Vinhomes Green Paradise": "Vinhome Bring Paradise"},
            7,
            "FAIL",
            id="7-of-8-fail",
        ),
        pytest.param(
            {
                "Vinhomes Green Paradise": "Vinhome Bring Paradise",
                "tham quan sa bàn": "thăm quan xa bàn",
                "chính sách bán hàng": "chính xác bán hàng",
            },
            5,
            "FAIL",
            id="5-of-8-fail",
        ),
    ],
)
def test_aggregate_critical_recall_does_not_inherit_overall_wer_pass(
    evaluator: ModuleType,
    replacements: dict[str, str],
    expected_count: int,
    expected_verdict: str,
) -> None:
    reference = PREFIX + "; ".join(TERMS)
    hypothesis = PREFIX + "; ".join(replacements.get(term, term) for term in TERMS)
    payload = _text_fixture(reference=reference, hypothesis=hypothesis, terms=TERMS)
    result = _evaluate_without_mutation(evaluator, payload)
    rows = result["critical_terms"]["terms"]
    assert len(rows) == 8
    assert sum(row["passed"] for row in rows) == expected_count
    assert {row["term"] for row in rows if not row["passed"]} == set(replacements)
    assert result["critical_terms"]["normalized_recall"] == expected_count / 8
    assert result["wer"]["passed"] is True
    assert result["wer"]["threshold"] == 0.15
    assert result["verdict"] == expected_verdict
    assert result["reasons"]["fail"] == (
        [] if expected_count == 8 else ["CRITICAL_TERM_RECALL_BELOW_1_0"]
    )
    assert result["timestamps"]["downstream_positive_duration_ready"] is True


def test_normalized_duplicate_expected_term_fails_instead_of_inflating_recall(
    evaluator: ModuleType,
) -> None:
    payload = _text_fixture(
        reference=PREFIX + "Ngọc Phương Đông",
        hypothesis=PREFIX + "Ngọc Phương Đông",
        terms=("Ngọc Phương Đông", "ngọc phương đông"),
    )
    result = _evaluate_without_mutation(evaluator, payload)
    assert [row["passed"] for row in result["critical_terms"]["terms"]] == [True, False]
    assert result["critical_terms"]["normalized_recall"] == 0.5
    assert result["verdict"] == "FAIL"


def test_normalization_does_not_rewrite_provider_text_or_positive_duration_contract(
    evaluator: ModuleType,
) -> None:
    payload = _fixture()
    word = payload["provider_transcript"]["segments"][0]["words"][1]
    word["end_seconds"] = word["start_seconds"]
    original = copy.deepcopy(payload["provider_transcript"])
    segments = tuple(
        ProviderSegment(
            start_seconds=segment["start_seconds"],
            end_seconds=segment["end_seconds"],
            text=segment["text"],
            speaker=segment["speaker"],
            confidence=segment["confidence"],
            words=tuple(
                ProviderWord(
                    start_seconds=item["start_seconds"],
                    end_seconds=item["end_seconds"],
                    text=item["text"],
                    confidence=item["confidence"],
                    timing_semantics=(
                        "provider_boundary_point"
                        if item["start_seconds"] == item["end_seconds"]
                        else "positive_interval"
                    ),
                )
                for item in segment["words"]
            ),
        )
        for segment in original["segments"]
    )
    provider_transcript = ProviderTranscript(
        language="vi", confidence=None, segments=segments, provenance={"fixture": True}
    )
    before = copy.deepcopy(provider_transcript)
    with pytest.raises(
        PositiveDurationTranscriptRequired, match="POSITIVE_DURATION_TRANSCRIPT_REQUIRED"
    ):
        require_positive_duration_transcript(provider_transcript)

    result = _evaluate_without_mutation(evaluator, payload)
    assert result["critical_terms"]["normalized_recall"] == 1.0
    assert result["timestamps"]["zero_duration_words"] == 1
    assert result["timestamps"]["downstream_positive_duration_ready"] is False
    assert payload["provider_transcript"] == original
    assert provider_transcript == before
    with pytest.raises(
        PositiveDurationTranscriptRequired, match="POSITIVE_DURATION_TRANSCRIPT_REQUIRED"
    ):
        require_positive_duration_transcript(provider_transcript)
