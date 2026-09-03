from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs" / "acceptance" / "v3-01"
SCHEMAS = DOCS / "schemas"
FIXTURES = DOCS / "fixtures" / "asr-post-run"
TEMPLATES = DOCS / "templates"
CONTRACTS = DOCS / "contracts"
RC11 = "207ff9fee5557eb0976f575c9263b61d995b20a0"
GOVERNANCE_BASE = "8ad490c02c36aafe9447a3eb0766a1d1f1f122d7"


def load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validator(name: str) -> Draft202012Validator:
    schema = load_json(SCHEMAS / name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def load_evaluator():
    path = DOCS / "tools" / "v3_01_asr_post_run_evaluator.py"
    spec = importlib.util.spec_from_file_location("v3_01_asr_post_run_evaluator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def evaluator():
    return load_evaluator()


@pytest.mark.parametrize(
    "schema_name",
    [
        "asr-post-run-input.schema.json",
        "asr-post-run-evaluation.schema.json",
        "flow-a-real-media-acceptance.schema.json",
        "flow-a-real-media-run-reference.schema.json",
        "tts-production-gate.schema.json",
        "human-quality-review.schema.json",
        "offline-preparation-manifest.schema.json",
    ],
)
def test_offline_prep_schemas_are_valid_draft_2020_12(schema_name: str) -> None:
    validator(schema_name)


@pytest.mark.parametrize(
    ("fixture_name", "expected_verdict"),
    [
        ("pass.json", "PASS"),
        ("review-required.json", "REVIEW_REQUIRED"),
        ("fail.json", "FAIL"),
    ],
)
def test_asr_evaluator_fixtures_validate_and_have_expected_verdict(
    evaluator, fixture_name: str, expected_verdict: str
) -> None:
    payload = load_json(FIXTURES / fixture_name)
    validator("asr-post-run-input.schema.json").validate(payload)

    result = evaluator.evaluate(payload)

    validator("asr-post-run-evaluation.schema.json").validate(result)
    assert result["verdict"] == expected_verdict
    assert result["safety"] == {
        "provider_calls_performed_by_evaluator": 0,
        "credential_reads_performed_by_evaluator": 0,
        "budget_reserved_vnd_by_evaluator": "0",
        "spend_vnd_by_evaluator": "0",
        "runtime_authority_granted": False,
        "production_verdict": "NO-GO",
    }


def test_asr_evaluation_hash_is_canonical_and_deterministic(evaluator) -> None:
    payload = load_json(FIXTURES / "pass.json")
    first = evaluator.evaluate(payload)
    second = evaluator.evaluate(copy.deepcopy(payload))
    recorded = first.pop("evaluation_sha256")
    second_recorded = second.pop("evaluation_sha256")

    assert first == second
    assert recorded == second_recorded
    assert recorded == hashlib.sha256(evaluator.canonical_json_bytes(first)).hexdigest()


def test_normalization_preserves_vietnamese_diacritics_and_critical_terms_in_wer(evaluator) -> None:
    assert evaluator.normalized_tokens("NGỌC, Phương Đông!") == ["ngọc", "phương", "đông"]
    assert evaluator.normalized_tokens("Ngoc Phuong Dong") != ["ngọc", "phương", "đông"]

    payload = load_json(FIXTURES / "pass.json")
    payload["provider_transcript"]["text"] = payload["provider_transcript"]["text"].replace(
        "Ngọc Phương Đông", "Ngoc Phuong Dong"
    )
    result = evaluator.evaluate(payload)

    assert result["wer"]["edit_errors"] >= 3
    assert result["critical_terms"]["critical_terms_included_in_wer"] is True
    assert result["critical_terms"]["terms"][0]["passed"] is False


@pytest.mark.parametrize(
    "mutation",
    ["negative", "outside_source", "word_outside_segment", "overlap", "coverage"],
)
def test_timestamp_contract_fails_closed(evaluator, mutation: str) -> None:
    payload = load_json(FIXTURES / "pass.json")
    segments = payload["provider_transcript"]["segments"]
    if mutation == "negative":
        segments[0]["words"][0]["start_seconds"] = -0.1
    elif mutation == "outside_source":
        segments[-1]["end_seconds"] = 7.0
    elif mutation == "word_outside_segment":
        segments[0]["words"][0]["end_seconds"] = segments[0]["end_seconds"] + 0.2
    elif mutation == "overlap":
        segments[1]["start_seconds"] = 1.0
    else:
        segments[-1]["words"][-1]["text"] = "không-khớp"

    result = evaluator.evaluate(payload)

    assert result["verdict"] == "FAIL"
    assert "TIMESTAMP_CONTRACT_FAILED" in result["reasons"]["fail"]


def test_missing_receipts_are_review_required_and_secret_failure_is_fail(evaluator) -> None:
    review_payload = load_json(FIXTURES / "pass.json")
    review_payload["receipts"]["cost_receipt_present"] = False
    review = evaluator.evaluate(review_payload)
    assert review["verdict"] == "REVIEW_REQUIRED"
    assert "EVIDENCE_MISSING_OR_INVALID:COST_RECEIPT" in review["reasons"]["review_required"]

    fail_payload = load_json(FIXTURES / "pass.json")
    fail_payload["receipts"]["secret_scan"] = {"status": "FAIL", "finding_count": 1}
    failed = evaluator.evaluate(fail_payload)
    assert failed["verdict"] == "FAIL"
    assert "SECRET_CONTAINMENT_FAILED" in failed["reasons"]["fail"]


def test_input_schema_rejects_unknown_fields() -> None:
    payload = load_json(FIXTURES / "pass.json")
    payload["runtime_authority"] = True
    with pytest.raises(ValidationError):
        validator("asr-post-run-input.schema.json").validate(payload)


def test_fixture_reference_checksum_is_exact() -> None:
    assert sha256_file(FIXTURES / "reference-pass.txt") == (
        "acbf26ba6f7b02cbdd46aa48818250c85198c7182cc323e18463546b1384e5c5"
    )


def test_flow_a_contract_and_two_prepared_references_are_hash_bound() -> None:
    contract = load_json(CONTRACTS / "V3-01-FLOW-A-REAL-MEDIA-ACCEPTANCE.v1.json")
    validator("flow-a-real-media-acceptance.schema.json").validate(contract)
    assert contract["baseline"] == {
        "executable_rc_tag": "vf-v3-01-rc11",
        "executable_rc_commit": RC11,
        "governance_base_commit": GOVERNANCE_BASE,
    }
    assert contract["consecutive_runs"]["required"] == 2
    assert contract["safety"]["acceptance_axis_promoted"] is False

    references = []
    for slot in (1, 2):
        record = load_json(TEMPLATES / f"V3-01-FLOW-A-REAL-MEDIA-RUN-{slot:02d}.json")
        validator("flow-a-real-media-run-reference.schema.json").validate(record)
        asr = record["asr_reference"]
        assert sha256_file(REPO / asr["asset_path"]) == asr["asset_sha256"]
        assert sha256_file(REPO / asr["transcript_path"]) == asr["transcript_sha256"]
        assert (REPO / asr["rights_record_path"]).is_file()
        assert record["visual_source"] is None
        assert record["expected_scene_boundaries_seconds"] is None
        assert record["expected_subject_reframe_zones"] is None
        assert record["expected_subtitle_cues"] is None
        assert record["acceptance_effect"] == "NONE"
        references.append(record)
    assert references[0]["asr_reference"]["asset_sha256"] != references[1]["asr_reference"]["asset_sha256"]


def test_tts_gate_is_research_only_with_distinct_inputs_and_no_runtime_authority() -> None:
    contract = load_json(CONTRACTS / "V3-01-19-VIETNAMESE-TTS-PRODUCTION-GATE.v1.json")
    validator("tts-production-gate.schema.json").validate(contract)
    assert contract["provider_selection"] == "NOT_APPROVED"
    assert len(contract["candidates"]) >= 5
    assert {row["class"] for row in contract["candidates"]} >= {
        "local_open_source",
        "cloud",
        "paid_api",
        "custom_self_hosted",
    }
    assert all(row["selection_status"] != "APPROVED" for row in contract["candidates"])
    scripts = [REPO / path for path in contract["reference_scripts"]]
    assert all(path.is_file() and path.read_text(encoding="utf-8").strip() for path in scripts)
    assert sha256_file(scripts[0]) != sha256_file(scripts[1])
    pronunciation = load_json(REPO / contract["pronunciation_set"])
    assert len(pronunciation["terms"]) >= 8
    assert all(term["substitution_allowed"] is False for term in pronunciation["terms"])
    assert contract["safety"] == {
        "provider_calls": 0,
        "credential_reads": 0,
        "reservation_vnd": "0",
        "spend_vnd": "0",
        "runtime_wired": False,
        "provider_selected": False,
        "production_verdict": "NO-GO",
    }


def test_g11_template_is_unexecuted_and_accept_requires_complete_pass() -> None:
    schema_validator = validator("human-quality-review.schema.json")
    template = load_json(TEMPLATES / "V3-01-G11-HUMAN-QUALITY-REVIEW.template.json")
    schema_validator.validate(template)
    assert len(template["checks"]) == 27
    assert {item["category"] for item in template["checks"]} == {
        "VISUAL",
        "SUBTITLE",
        "VOICE",
        "AUDIO",
        "CONTENT",
    }
    assert all(item["result"] == "NOT_REVIEWED" for item in template["checks"])
    assert template["decision"] == "REVIEW_REQUIRED"
    assert template["safety"]["production_verdict"] == "NO-GO"

    invalid_accept = copy.deepcopy(template)
    invalid_accept["status"] = "COMPLETE"
    invalid_accept["decision"] = "ACCEPT"
    with pytest.raises(ValidationError):
        schema_validator.validate(invalid_accept)


def test_offline_evaluator_has_no_network_or_runtime_imports() -> None:
    path = DOCS / "tools" / "v3_01_asr_post_run_evaluator.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imports.isdisjoint({"httpx", "requests", "openai", "urllib", "socket", "subprocess"})


def test_new_markdown_local_links_resolve() -> None:
    documents = [
        DOCS / "46_V3_01_ASR_POST_RUN_AND_FLOW_A_PREPARATION.md",
        DOCS / "47_V3_01_19_VIETNAMESE_TTS_PRODUCTION_GATE.md",
        DOCS / "48_V3_01_G11_HUMAN_QUALITY_GATE.md",
        TEMPLATES / "V3_01_ASR_OPERATION_EVIDENCE_REVIEW.md",
        TEMPLATES / "V3_01_FLOW_A_REAL_MEDIA_RUN_REVIEW.md",
        TEMPLATES / "V3_01_FLOW_A_REAL_MEDIA_CONSECUTIVE_REVIEW.md",
        TEMPLATES / "V3_01_G11_HUMAN_QUALITY_CHECKLIST.md",
    ]
    pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    for document in documents:
        for target in pattern.findall(document.read_text(encoding="utf-8")):
            if target.startswith(("https://", "http://", "#", "mailto:")):
                continue
            local = target.split("#", 1)[0]
            assert (document.parent / local).resolve().exists(), f"{document}: {target}"


def test_offline_preparation_manifest_has_complete_valid_checksums() -> None:
    manifest = load_json(DOCS / "V3-01-OFFLINE-PREPARATION-MANIFEST.json")
    validator("offline-preparation-manifest.schema.json").validate(manifest)
    files = manifest["files"]
    paths = [item["path"] for item in files]
    assert manifest["file_count"] == len(files) == len(set(paths))
    assert paths == sorted(paths)
    for item in files:
        path = REPO / item["path"]
        assert path.is_file(), item["path"]
        assert sha256_file(path) == item["sha256"], item["path"]
    assert manifest["safety"] == {
        "provider_calls": 0,
        "credential_reads": 0,
        "reservation_vnd": "0",
        "spend_vnd": "0",
        "operation_1_executed": False,
        "operation_2_authorized": False,
        "runtime_authority_granted": False,
        "production_verdict": "NO-GO",
    }
