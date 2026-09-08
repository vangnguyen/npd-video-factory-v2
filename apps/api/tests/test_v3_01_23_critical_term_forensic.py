from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / "docs/acceptance/v3-01/tools/v3_01_23_asr_critical_term_forensic.py"
EVIDENCE = ROOT / "docs/acceptance/v3-01/evidence/rc15-asr-operation-1"
SPEC = importlib.util.spec_from_file_location("asr_critical_term_forensic", TOOL)
assert SPEC and SPEC.loader
FORENSIC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FORENSIC)


def test_recorded_forensic_report_is_exactly_reproducible_and_bound() -> None:
    before = {name: hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest() for name in FORENSIC.SOURCE_SHA256}
    actual = FORENSIC.build_report(ROOT)
    saved = json.loads((EVIDENCE / "critical-term-forensic.json").read_bytes())
    assert actual == saved
    unsigned = {key: value for key, value in actual.items() if key != "report_sha256"}
    assert actual["report_sha256"] == hashlib.sha256(FORENSIC.canonical_bytes(unsigned)).hexdigest()
    assert actual["source_sha256"] == before == FORENSIC.SOURCE_SHA256
    assert before == {name: hashlib.sha256((EVIDENCE / name).read_bytes()).hexdigest() for name in before}
    assert actual["grain"] == {
        "critical_terms": 8,
        "failed_critical_terms": 3,
        "provider_normalized_tokens": 412,
        "provider_word_objects": 412,
        "reference_normalized_tokens": 414,
        "segments": 17,
    }


def test_all_six_failed_occurrences_keep_exact_provider_words_timing_and_context() -> None:
    report = FORENSIC.build_report(ROOT)
    expected = {
        "Vinhomes Green Paradise": [
            ("Vinhome Bring Paradise", [76, 77, 78], [2], 18.700001, 20.32, 2),
            ("ping home ring paradise", [280, 281, 282, 283], [10], 79.040001, 80.480003, 3),
        ],
        "tham quan sa bàn": [
            ("thăm quan xa bàn", [159, 160, 161, 162], [5], 45.139999, 46.02, 2),
            ("thăm quan xa bàn", [290, 291, 292, 293], [10], 83.519997, 84.279999, 2),
        ],
        "chính sách bán hàng": [
            ("chính xác bán hàng", [185, 186, 187, 188], [6], 53.18, 53.84, 1),
            ("chính xác bán hàng", [299, 300, 301, 302], [10], 86.080002, 86.879997, 1),
        ],
    }
    for finding in report["findings"]:
        assert finding["classification"] == "PROVIDER_MISRECOGNITION"
        assert finding["reference_occurrence_count"] == 2
        assert finding["provider_exact_normalized_occurrence_count"] == 0
        assert finding["critical_term_accepted"] is False
        actual = []
        for occurrence in finding["observed_occurrences"]:
            actual.append((occurrence["observed_phrase"], occurrence["global_word_indexes"], occurrence["segment_indexes"],
                           occurrence["start_seconds"], occurrence["end_seconds"], occurrence["diagnostic_token_edit_distance"]))
            assert occurrence["diagnostic_edit_distance_used_for_acceptance"] is False
            assert all(word["confidence"] is None for word in occurrence["words"])
            assert all(segment["confidence"] is None for segment in occurrence["segments"])
            assert occurrence["previous_word"]["global_word_index"] == occurrence["global_word_indexes"][0] - 1
            assert occurrence["next_word"]["global_word_index"] == occurrence["global_word_indexes"][-1] + 1
        assert actual == expected[finding["expected_phrase"]]


def test_classification_is_reference_relative_not_a_new_acoustic_claim() -> None:
    report = FORENSIC.build_report(ROOT)
    basis = report["reference_basis"]
    assert basis["owner_confirmation"]["content_matches_reference_transcript"] is True
    assert basis["owner_confirmation"]["recorded_at_utc"] == "2026-09-03T07:05:17Z"
    assert basis["new_acoustic_listening_performed"] is False
    assert basis["independent_acoustic_ground_truth"] == "NOT_REVERIFIED"
    assert "did not newly listen" in basis["caveat"]
    assert report["strict_evaluator_snapshot"]["verdict"] == "FAIL"
    assert report["strict_evaluator_snapshot"]["critical_terms"]["normalized_recall"] == 0.625
    assert report["strict_evaluator_snapshot"]["wer"]["wer"] == 0.096618
    assert report["invariants"]["historical_verdict_changed"] is False
    assert report["safety"] == {"provider_calls": 0, "credential_reads": 0, "reservation_vnd": "0",
                                "spend_vnd": "0", "runtime_authority": False,
                                "operation_2": "NOT_APPROVED_LOCKED", "production_verdict": "NO-GO"}


@pytest.mark.parametrize(("expected", "observed", "reference", "verified", "classification"), [
    ("tham quan sa bàn", "thăm quan xa bàn", "tham quan sa bàn", True, "PROVIDER_MISRECOGNITION"),
    ("chính sách bán hàng", "chính xác bán hàng", "chính sách bán hàng", True, "PROVIDER_MISRECOGNITION"),
    ("Cần Giờ", "cần giờ", "Cần Giờ", True, "NORMALIZATION_ONLY"),
    ("tham quan sa bàn", "thăm quan xa bàn", "tham quan sa bàn", False, "UNKNOWN"),
    ("tham quan sa bàn", "", "tham quan sa bàn", True, "UNKNOWN"),
    ("tham quan sa bàn", "thăm quan xa bàn", "a different reference", True, "REFERENCE_MISMATCH"),
])
def test_unsupported_attribution_does_not_become_provider_misrecognition(
    expected: str, observed: str, reference: str, verified: bool, classification: str,
) -> None:
    assert FORENSIC.classify(expected, observed, reference, owner_reference_verified=verified) == classification


@pytest.mark.parametrize(("source", "tokens"), [
    ("  CẦN\tGiờ?! ", ["cần", "giờ"]),
    ("Ca\u0302\u0300n Gio\u031b\u0300", ["cần", "giờ"]),
    ("tham/quan—sa bàn", ["tham", "quan", "sa", "bàn"]),
    ("thăm quan xa bàn", ["thăm", "quan", "xa", "bàn"]),
    ("chính xác bán hàng", ["chính", "xác", "bán", "hàng"]),
])
def test_normalization_preserves_vietnamese_spelling_and_diacritics(source: str, tokens: list[str]) -> None:
    assert FORENSIC.normalized_tokens(source) == tokens


def test_edit_distance_is_diagnostic_and_never_accepts_a_near_match() -> None:
    expected = FORENSIC.normalized_tokens("chính sách bán hàng")
    observed = FORENSIC.normalized_tokens("chính xác bán hàng")
    assert FORENSIC.diagnostic_edit_distance(expected, observed) == 1
    assert FORENSIC.phrase_starts(observed, expected) == []
    assert FORENSIC.classify("chính sách bán hàng", "chính xác bán hàng", "chính sách bán hàng",
                             owner_reference_verified=True) == "PROVIDER_MISRECOGNITION"


def test_exact_source_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    wrong = tmp_path / "changed.json"
    wrong.write_text('{"forensic":"tampered"}', encoding="utf-8")
    with pytest.raises(FORENSIC.ForensicBindingError, match="FORENSIC_SOURCE_HASH_MISMATCH"):
        FORENSIC._load_exact(wrong, FORENSIC.SOURCE_SHA256["operation-1-result.json"])


def test_helper_has_no_provider_credential_or_write_dependency() -> None:
    tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    imports = {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    assert imports <= {"__future__", "argparse", "hashlib", "json", "sys", "unicodedata", "pathlib", "typing"}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {"write_text", "write_bytes", "request", "post", "urlopen", "getenv", "environ", "reserve"}
