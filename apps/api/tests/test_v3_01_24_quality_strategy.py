from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from app.auto_edit_providers import (
    PositiveDurationTranscriptRequired,
    ProviderSegment,
    ProviderTranscript,
    ProviderWord,
    require_positive_duration_transcript,
)
from app.config import Settings
from app.provider_ci_provenance import (
    provider_ci_provenance_sha256,
    validate_provider_acceptance_ci_provenance,
)
from app.provider_gate_loader import canonical_sha256
from app.provider_safety import ProviderRightsEvidence


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs" / "acceptance" / "v3-01"
STRATEGY = DOCS / "contracts" / "V3-01-24-ASR-QUALITY-STRATEGY.v1.json"
RECEIPTS = DOCS / "evidence" / "rc15-asr-operation-1"
BASE = "5a8c96da6816ad6f424eaaa3952947738d4c49d5"
RC15 = "7d1290aacac61df98a51544731243e5e322a8644"
TREE_SHA256 = "9fab766b285eb2db580032b914eb2ccdf474d18b3958fd218a73a22fb75701e8"
KEYWORDS = (
    "Ngọc Phương Đông", "Vinhomes Green Paradise", "Cần Giờ",
    "tham quan sa bàn", "chính sách bán hàng",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def strategy() -> dict:
    return _load(STRATEGY)


@pytest.fixture(scope="module")
def evaluator():
    path = DOCS / "tools" / "v3_01_asr_post_run_evaluator.py"
    spec = importlib.util.spec_from_file_location("v3_01_24_offline_strategy_evaluator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_strategy_is_only_a_proposal_on_the_verified_post_pr52_base(strategy) -> None:
    assert strategy["work_package"] == "V3-01-24"
    assert strategy["status"] == "PROPOSED_NOT_APPROVED"
    assert strategy["reference_date"] == "2026-09-08"
    assert strategy["base_main"] == BASE
    assert strategy["executable_rc"] == {
        "tag": "vf-v3-01-rc15", "commit": RC15, "tree_sha256": TREE_SHA256,
    }
    checkpoint = strategy["post_merge_review"]
    assert checkpoint["pr"] == 52
    assert checkpoint["approved_head"] == "c092827223406f0489ad1e57a414e073f371c3df"
    assert checkpoint["main_ci_run_id"] == 34241909331
    assert checkpoint["main_ci_conclusion"] == "success"
    assert checkpoint["main_ci_jobs"] == "5/5"
    assert checkpoint["canonical_runtime_tree_changed"] is False
    # Offline evaluator source changed in #52; runtime-tree equality must not be
    # misrepresented as equality of every executable artifact in the repository.
    assert checkpoint["offline_evaluator_source_changed"] is True
    assert checkpoint["offline_evaluator_schema_changed"] is True
    assert checkpoint["all_executable_source_unchanged"] is False
    assert checkpoint["strategy_pr_requires_new_rc"] is False
    assert checkpoint["new_rc_created"] is False


def test_post_merge_dual_ci_roles_and_hash_are_not_interchangeable(strategy) -> None:
    record = _load(REPO / strategy["post_merge_review"]["provenance_path"])
    provenance = validate_provider_acceptance_ci_provenance(
        record["contract"],
        expected_executable_rc_commit=RC15,
        expected_governance_main_commit=BASE,
        expected_executable_rc_ci_run_id=34142662132,
        expected_governance_main_ci_run_id=34241909331,
    )
    assert provider_ci_provenance_sha256(provenance) == record["provenance_sha256"]
    assert provenance.executable_tree_sha256 == provenance.governance_executable_tree_sha256 == TREE_SHA256
    assert provenance.executable_rc_ci.jobs_succeeded == provenance.governance_main_ci.jobs_succeeded == 5
    assert record["provider_calls"] == record["credential_reads"] == 0
    assert Decimal(record["reservation_vnd"]) == 0
    assert record["production_verdict"] == "NO-GO"


def test_strategy_has_no_runtime_authority_or_side_effects(strategy) -> None:
    assert strategy["safety"] == {
        "provider_calls": 0, "credential_reads": 0, "live_reservations": 0,
        "spend_vnd": "0", "external_execution": False, "paid_execution": False,
        "runtime_budget_vnd": "0", "kill_switch_engaged": True,
        "bundle_mounted": False, "live_authority": False, "new_operations": [],
        "new_automations": [], "deploy": False, "publish": False, "public_ingress": False,
    }
    assert all(candidate["new_execution_authorized"] is False for candidate in strategy["candidates"])
    settings = Settings(_env_file=None)
    assert settings.transcription_provider == "fixture"
    assert settings.openai_transcription_model == ""
    assert settings.provider_external_execution_enabled is False
    assert settings.provider_paid_execution_enabled is False
    assert settings.provider_verified_gate_bundle_enabled is False
    assert settings.provider_global_kill_switch_engaged is True
    assert settings.provider_per_operation_limit_vnd == settings.provider_daily_limit_vnd == Decimal("0")


def test_historical_rc15_quality_failure_is_not_rewritten(strategy) -> None:
    historical = strategy["historical"]
    assert historical["operation_id"] == "v3-01-rc15-openai-transcription-asr-call-01"
    assert historical["provider"] == "SUCCESS"
    assert historical["structured_transcript"] == historical["timestamp_validation"] == "PASS"
    assert historical["acceptance"] == "FAIL"
    assert historical["consumed"] is True
    assert historical["retrospective_pass"] is False
    assert (historical["critical_terms_passed"], historical["critical_terms_required"]) == (5, 8)
    assert historical["words"] == 412 and historical["boundary_points"] == 27
    assert Decimal(historical["wer_percent"]) == Decimal("9.6618")
    assert Decimal(historical["actual_cost_vnd"]) == Decimal("326.294996")
    assert historical["operation_2"] == "NOT_APPROVED_LOCKED"
    assert historical["asr_consecutive_pass"] == "0/2"
    assert historical["vision_consecutive_pass"] == "2/2"
    assert historical["production"] == "NO-GO"


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("operation-1-result.json", "ef06ffc48495e207ae7e827207ff67ee7b345b3323c702c1852b39a27a2d5099"),
        ("operation-1-evaluator-input.json", "80dfdbe7b8afe38eda7086d452e393d8893fdcca2c562174c055abe91a889474"),
        ("operation-1-post-run-evaluation.json", "08d71d294dc602e219d09d824c9d66e834a6c713f36f4a94368f5034598ffda9"),
    ],
)
def test_original_rc15_receipts_remain_exact(filename: str, expected: str) -> None:
    assert _sha(RECEIPTS / filename) == expected
    manifest = _load(RECEIPTS / "manifest.json")
    record = next(row for row in manifest["files"] if row["path"] == filename)
    assert record["role"] == "original_immutable"
    assert record["sha256"] == expected


def test_three_model_comparison_preserves_unproven_quality_and_timing(strategy) -> None:
    models = {row["model"]: row for row in strategy["models"]}
    assert set(models) == {"whisper-1", "gpt-transcribe", "gpt-4o-transcribe"}
    whisper = models["whisper-1"]
    assert whisper["native_word_timing"] == whisper["native_segment_timing"] == "DOCUMENTED_AND_RC15_OBSERVED"
    assert whisper["strict_flow_a"] == "EVIDENCE_LAYER_COMPATIBLE_DOWNSTREAM_POSITIVE_DURATION_GATED"
    for name in ("gpt-transcribe", "gpt-4o-transcribe"):
        assert models[name]["native_word_timing"] == models[name]["native_segment_timing"] == "NOT_PROVEN"
        assert models[name]["strict_flow_a"] == "STRICT_FLOW_A_INCOMPATIBLE"
        assert models[name]["npd_latency_evidence_ms"] is None
    assert all(row["new_quality"] == "UNKNOWN" and row["new_latency_guarantee"] is None for row in models.values())
    assert all(row["estimated_8_of_8_probability"] is None for row in strategy["candidates"])


def test_w0_request_profile_records_omitted_prompt_and_temperature(strategy) -> None:
    baseline = next(row for row in strategy["candidates"] if row["id"] == "W0")
    assert baseline["role"] == "BASELINE_RECORDED_NO_REPLAY"
    assert baseline["prompt"] is None and baseline["temperature"] is None
    assert baseline["temperature_policy"] == "OMITTED"
    assert baseline["runtime_wired"] is True
    assert baseline["new_execution_authorized"] is False
    assert baseline["quality_evidence"] == "RC15_OP1_FAIL_5_OF_8"
    source = ast.parse((REPO / "apps/api/app/openai_transcription_provider.py").read_text(encoding="utf-8"))
    request = next(
        node for node in ast.walk(source)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "build_request"
    )
    data = next(keyword.value for keyword in request.keywords if keyword.arg == "data")
    assert isinstance(data, ast.Dict)
    assert {key.value for key in data.keys if isinstance(key, ast.Constant)} == {
        "model", "language", "response_format", "timestamp_granularities[]",
    }


@pytest.mark.parametrize("candidate_id", ["W1", "W2"])
def test_prompt_candidates_are_bounded_proposals_not_token_count_claims(strategy, evaluator, candidate_id) -> None:
    row = next(row for row in strategy["candidates"] if row["id"] == candidate_id)
    proposal = strategy["prompt_contract_proposal"]
    assert row["model"] == "whisper-1" and row["language"] == "vi"
    assert row["response_format"] == "verbose_json"
    assert row["timestamp_granularities"] == ["segment", "word"]
    assert row["prompt_status"] == "PROPOSED_NOT_APPROVED"
    assert row["runtime_wired"] is False and row["new_execution_authorized"] is False
    assert row["same_prompt_for_both_assets"] is True
    assert row["temperature"] is None and row["temperature_policy"] == "OMITTED"
    assert row["quality_evidence"] == "NOT_TESTED"
    assert 0 < len(row["prompt"].encode("utf-8")) <= proposal["proposed_utf8_byte_cap"] == 224
    assert proposal["documented_whisper_limit_tokens"] == 224
    assert proposal["tokenizer_exact_count"] == "NOT_COMPUTED"
    assert proposal["tokenizer_requirement"] == "PIN_WHISPER_MULTILINGUAL_TOKENIZER_AND_VERIFY_BEFORE_FUTURE_GATING"
    assert proposal["truncate"] is False
    assert tuple(proposal["keywords"]) == KEYWORDS
    for term in KEYWORDS:
        assert evaluator._contains_phrase(evaluator.normalized_tokens(row["prompt"]), evaluator.normalized_tokens(term))


def test_second_asset_is_a_reference_only_negative_insertion_control(strategy, evaluator) -> None:
    manifest = _load(REPO / strategy["assets_manifest"]["path"])
    reference1 = (REPO / manifest["assets"][0]["reference_transcript_path"]).read_text(encoding="utf-8")
    reference2 = (REPO / manifest["assets"][1]["reference_transcript_path"]).read_text(encoding="utf-8")
    for term in KEYWORDS:
        tokens = evaluator.normalized_tokens(term)
        assert evaluator._contains_phrase(evaluator.normalized_tokens(reference1), tokens)
        assert not evaluator._contains_phrase(evaluator.normalized_tokens(reference2), tokens)
    control = strategy["negative_insertion_control"]
    assert control["asset_02_reference_lacks_all_five_prompt_terms"] is True
    assert control["same_prompt_for_both_assets"] is True
    assert control["design_status"] == "REFERENCE_INSPECTION_ONLY_NOT_EXECUTED"
    assert control["require_compare_occurrence_counts_and_human_audio_review"] is True
    assert control["broader_generalization"] == "UNKNOWN"
    assert control["additional_assets_require_owner_rights"] is True


def test_assets_transcripts_and_rights_are_unchanged(strategy) -> None:
    entry = strategy["assets_manifest"]
    assert entry["sha256"] == "0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0"
    assert _sha(REPO / entry["path"]) == entry["sha256"]
    expected = [
        ("fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef", "585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e", "5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091"),
        ("dce36c5246c17e0385842006dcb0088a8c97a79d3009796815c2564c075cf20b", "0bff8c2b403cee452fac00f71b84759988ea515027fda6bd49be76ae382c1fef", "972dcc752b6bc606a655f272472128a8e6c47fa7858f2bd0cc8e9b9f8c4e4323"),
    ]
    manifest = _load(REPO / entry["path"])
    for row, (asset_sha, transcript_sha, rights_sha) in zip(manifest["assets"], expected, strict=True):
        assert _sha(REPO / row["path"]) == row["sha256"] == asset_sha
        assert _sha(REPO / row["reference_transcript_path"]) == row["reference_transcript_sha256"] == transcript_sha
        assert len(row["critical_terms"]) == 8
        rights = ProviderRightsEvidence.model_validate(_load(REPO / row["rights_record_path"]))
        assert canonical_sha256(rights) == rights_sha
    assert entry["rights_revalidation_required_before_future_execution"] is True
    assert manifest["owner_confirmation"]["voice_processing_consent"] is True
    assert all(manifest["owner_confirmation"][name] is False for name in ("publishing_allowed", "training_allowed", "resale_allowed"))


def test_quality_and_matching_thresholds_are_not_relaxed(strategy, evaluator) -> None:
    policy = strategy["evaluation"]
    assert Decimal(policy["wer_max_percent"]) == Decimal("15")
    assert policy["critical_terms_required_per_asset"] == policy["critical_terms_total_per_asset"] == 8
    assert policy["matching"] == "EXACT_CONTIGUOUS_NORMALIZED_TOKENS"
    assert policy["preserve_vietnamese_diacritics"] is True
    for name in ("fuzzy", "synonyms", "semantic_matching", "partial_phrase", "post_correction", "reference_rewrite", "provider_transcript_mutation"):
        assert policy[name] is False
    assert evaluator.AsrEvaluationPolicy().maximum_wer == 0.15
    assert evaluator.AsrEvaluationPolicy().minimum_critical_term_recall == 1.0
    reference = evaluator.normalized_tokens("Ngọc Phương Đông")
    assert not evaluator._contains_phrase(evaluator.normalized_tokens("Ngoc Phuong Dong"), reference)
    assert not evaluator._contains_phrase(evaluator.normalized_tokens("Ngọc mới Phương Đông"), reference)


def test_positive_duration_wrapper_remains_an_independent_boundary(strategy) -> None:
    point = ProviderWord(1.0, 1.0, "điểm", None, "provider_boundary_point")
    following = ProviderWord(1.0, 2.0, "tiếp", None)
    transcript = ProviderTranscript(
        "vi", None,
        (ProviderSegment(0.0, 2.0, "điểm tiếp", None, None, (point, following)),),
        {"source": "synthetic_offline_contract"},
    )
    before = copy.deepcopy(transcript)
    with pytest.raises(PositiveDurationTranscriptRequired, match="POSITIVE_DURATION_TRANSCRIPT_REQUIRED"):
        require_positive_duration_transcript(transcript)
    assert transcript == before
    assert point.start_seconds == point.end_seconds == 1.0
    assert strategy["evaluation"]["positive_duration_wrapper_unchanged"] is True
    assert strategy["evaluation"]["downstream_boundary_points"] == "POSITIVE_DURATION_TRANSCRIPT_REQUIRED"


def test_future_w1_requires_source_rc_and_separate_gates(strategy) -> None:
    recommendation = strategy["recommendation"]
    assert recommendation["next"] == "W1"
    assert recommendation["fallback"] == "W2"
    assert recommendation["owner_decision"] == "PENDING"
    assert recommendation["fresh_operation_ids_and_window_required"] is True
    assert recommendation["g01"] == "REBIND_MODEL_RC_REQUEST_PROFILE_SCOPE"
    assert recommendation["g02"] == "REBIND_COST_TIMEOUT_SCOPE_NO_AUTOMATIC_INCREASE"
    assert recommendation["g03"] == "REVALIDATE_SAME_ASSET_REFERENCE_RIGHTS_AND_CONTEXT_SCOPE"
    for row in strategy["candidates"][1:]:
        assert row["requires_source_remediation"] is True
        assert row["requires_new_executable_rc_before_live"] is True
    required = set(strategy["prompt_contract_proposal"]["binding_required"])
    assert required >= {"profile_id", "exact_utf8_sha256", "byte_length", "token_count_and_tokenizer_identity", "temperature_omission_policy", "rc_commit", "scope_hash"}
    assert strategy["prompt_contract_proposal"]["authority_model"] == "ASR_REQUEST_PROFILE_IN_SCOPE_NOT_MONEY_LIMITS"


def test_external_references_are_official_and_not_contacted(strategy) -> None:
    assert len(strategy["sources"]) >= 6
    for source in strategy["sources"]:
        url = urlsplit(source["url"])
        assert url.scheme == "https"
        assert url.hostname == "developers.openai.com"
        assert url.username is None and url.password is None
        assert url.path.startswith("/api/")
