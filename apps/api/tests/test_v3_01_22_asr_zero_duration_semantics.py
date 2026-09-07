from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

import app.provider_safety_db  # noqa: F401
from app.auto_edit_providers import (
    PositiveDurationTranscriptRequired,
    ProviderSegment,
    ProviderTranscript,
    ProviderWord,
    require_positive_duration_transcript,
)
from app.db import Base, create_engine, create_session_factory
from app.provider_safety import (
    ProviderBudgetPolicy,
    ProviderCallContext,
    ProviderCircuitPolicy,
    ProviderRetryPolicy,
    ProviderSafetyController,
    ProviderSafetyPolicy,
)
from app.provider_safety_durable import DurableProviderSafetyController
from app.provider_safety_repository import ProviderSafetyRepository


REPO = Path(__file__).resolve().parents[3]
DOCS = REPO / "docs" / "acceptance" / "v3-01"
FIXTURE = DOCS / "fixtures" / "asr-post-run" / "pass.json"
REPORT_DIR = (
    REPO
    / "evidence"
    / "v3-01"
    / "vf-v3-01-20260907T145428Z-46937d9-rc14-asr-forensics"
)
REPORT = REPORT_DIR / "rc14-asr-operation-1-word-timestamp-forensics.json"
REPORT_SCHEMA = DOCS / "schemas" / "asr-word-timestamp-forensic-report.schema.json"
ZERO_INDEXES = [
    5, 7, 10, 17, 25, 38, 59, 64, 66, 86, 87, 114, 135, 139,
    140, 146, 169, 185, 186, 197, 226, 230, 265, 271, 295, 345, 373,
]


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _evaluator():
    path = DOCS / "tools" / "v3_01_asr_post_run_evaluator.py"
    spec = importlib.util.spec_from_file_location("v3_01_asr_post_run_evaluator_v30122", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _evaluate(payload: dict[str, object]) -> dict[str, object]:
    return _evaluator().evaluate(payload)


def _fixture() -> dict[str, object]:
    return copy.deepcopy(_load(FIXTURE))


def _boundary_transcript() -> ProviderTranscript:
    return ProviderTranscript(
        language="vi",
        confidence=None,
        segments=(
            ProviderSegment(
                start_seconds=0.0,
                end_seconds=1.0,
                text="Ngọc Phương",
                speaker=None,
                confidence=None,
                words=(
                    ProviderWord(0.0, 0.4, "Ngọc", None),
                    ProviderWord(
                        0.4,
                        0.4,
                        "Phương",
                        None,
                        timing_semantics="provider_boundary_point",
                    ),
                ),
            ),
        ),
        provenance={"original_evidence": True},
        actual_cost_vnd=Decimal("0"),
    )


def _active_policy() -> ProviderSafetyPolicy:
    return ProviderSafetyPolicy(
        external_execution_enabled=True,
        paid_execution_enabled=True,
        global_kill_switch_engaged=False,
        credential_gate_approved=True,
        rights_gate_approved=True,
        budget=ProviderBudgetPolicy(
            approved=True,
            owner_approval_id="V3-01-APP-999",
            per_operation_limit_vnd=Decimal("1"),
            daily_limit_vnd=Decimal("2"),
        ),
        retry=ProviderRetryPolicy(
            max_attempts=1,
            provider_http_timeout_seconds=5,
            controller_hard_timeout_seconds=10,
            max_elapsed_seconds=10,
            max_concurrent_calls=1,
        ),
        circuit=ProviderCircuitPolicy(failure_threshold=3, cooldown_seconds=10),
    )


def _context(operation_key: str) -> ProviderCallContext:
    return ProviderCallContext(
        operation_key=operation_key,
        workspace_id="wsp_offline_timestamp",
        project_id="prj_offline_timestamp",
        provider_key="fixture-transcription",
        model="fixture-zero-duration-boundary",
        capability="asr",
        operation="flow_a_asr",
        external_call=True,
        paid=False,
        estimated_cost_vnd=Decimal("0"),
        credential_alias="secret://openai/offline-test-alias",
        rights_required=False,
        rights=[],
    )


def test_forensic_report_is_complete_schema_valid_and_hash_bound() -> None:
    report = _load(REPORT)
    schema = _load(REPORT_SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)

    recorded_sha = report.pop("report_sha256")
    assert recorded_sha == hashlib.sha256(
        _evaluator().canonical_json_bytes(report)
    ).hexdigest()
    assert report["source"]["sha256"] == (
        "2d65b3e4c1ec1afc5f6b262a1ea294c811be5dba9718a06992da9fe3a8d2b1bd"
    )
    assert report["population"] == {
        "source_duration_seconds": 120.852,
        "segment_count": 20,
        "word_count": 413,
        "positive_duration_word_count": 386,
        "zero_duration_word_count": 27,
        "zero_duration_percent": 6.53753,
        "all_diagnostic_words_accounted_for": True,
    }


def test_forensic_report_accounts_for_every_word_without_inventing_text() -> None:
    report = _load(REPORT)
    words = report["words"]
    assert [word["word_index"] for word in words] == list(range(413))
    assert all(word["token_text"] is None for word in words)
    assert all(word["punctuation_characteristics"] is None for word in words)
    zero_words = [word for word in words if word["zero_duration"]]
    assert [word["word_index"] for word in zero_words] == ZERO_INDEXES
    assert all(word["raw_start_seconds"] == word["raw_end_seconds"] for word in zero_words)
    assert all(word["inside_source_duration"] for word in zero_words)
    assert all(word["inside_selected_segment"] for word in zero_words)
    assert all(word["monotonic"] for word in zero_words)
    assert all(not word["overlaps_previous_word"] for word in zero_words)
    assert all(
        "matches_next_word_start" in word["zero_duration_categories"]
        for word in zero_words
    )
    assert report["aggregate"]["duplicate_zero_timestamp_groups"] == [
        [86, 87], [139, 140], [185, 186]
    ]
    assert report["aggregate"]["transcript_coverage"] is None
    assert report["conclusions"]["historical_rc14_verdict_changed"] is False


@pytest.mark.parametrize(
    ("shape", "expected_zero"),
    [
        ("one", 1),
        ("consecutive", 2),
        ("segment_start", 1),
        ("segment_end", 1),
        ("duplicate_boundary", 2),
    ],
)
def test_evaluator_accepts_anchored_boundary_points_as_provider_evidence(
    shape: str, expected_zero: int
) -> None:
    payload = _fixture()
    first = payload["provider_transcript"]["segments"][0]["words"]
    if shape == "one":
        first[1]["start_seconds"] = first[1]["end_seconds"] = 0.4
        first[2]["start_seconds"] = 0.4
    elif shape in {"consecutive", "duplicate_boundary"}:
        first[1]["start_seconds"] = first[1]["end_seconds"] = 0.4
        first[2]["start_seconds"] = first[2]["end_seconds"] = 0.4
        first[3]["start_seconds"] = 0.4
    elif shape == "segment_start":
        first[0]["start_seconds"] = first[0]["end_seconds"] = 0.0
        first[1]["start_seconds"] = 0.0
    else:
        first[3]["end_seconds"] = 2.4
        first[4]["start_seconds"] = first[4]["end_seconds"] = 2.4

    result = _evaluate(payload)

    assert result["verdict"] == "PASS"
    assert result["timestamps"]["passed"] is True
    assert result["timestamps"]["zero_duration_words"] == expected_zero
    assert result["timestamps"]["unanchored_boundary_points"] == 0
    assert result["timestamps"]["timestamp_token_coverage"] == 1.0
    assert result["timestamps"]["downstream_positive_duration_ready"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "isolated_zero",
        "inverted",
        "negative",
        "outside_source",
        "outside_segment",
        "invalid_segment_order",
        "coverage_mismatch",
    ],
)
def test_evaluator_keeps_unsafe_or_unverifiable_timing_fail_closed(mutation: str) -> None:
    payload = _fixture()
    segments = payload["provider_transcript"]["segments"]
    word = segments[0]["words"][1]
    if mutation == "isolated_zero":
        word["start_seconds"] = word["end_seconds"] = 0.6
    elif mutation == "inverted":
        word["start_seconds"], word["end_seconds"] = 0.9, 0.4
    elif mutation == "negative":
        word["start_seconds"] = -0.1
    elif mutation == "outside_source":
        segments[-1]["words"][-1]["end_seconds"] = 7.0
    elif mutation == "outside_segment":
        segments[0]["words"][-1]["end_seconds"] = 2.6
    elif mutation == "invalid_segment_order":
        segments[1]["start_seconds"] = 2.3
    else:
        segments[0]["words"][0]["text"] = "không-khớp"

    result = _evaluate(payload)

    assert result["verdict"] == "FAIL"
    assert "TIMESTAMP_CONTRACT_FAILED" in result["reasons"]["fail"]
    assert result["timestamps"]["downstream_positive_duration_ready"] is False
    if mutation == "isolated_zero":
        assert result["timestamps"]["unanchored_boundary_points"] == 1


def test_positive_duration_projection_never_repairs_or_drops_boundary_words() -> None:
    transcript = _boundary_transcript()
    with pytest.raises(PositiveDurationTranscriptRequired) as captured:
        require_positive_duration_transcript(transcript)
    assert captured.value.code == "POSITIVE_DURATION_TRANSCRIPT_REQUIRED"
    assert captured.value.blocked_word_paths == ("$.segments[0].words[1]",)
    assert transcript.segments[0].words[1].start_seconds == 0.4
    assert transcript.segments[0].words[1].end_seconds == 0.4
    assert len(transcript.segments[0].words) == 2


@pytest.mark.asyncio
async def test_boundary_transcript_value_has_durable_and_non_durable_controller_parity(
    tmp_path: Path,
) -> None:
    transcript = _boundary_transcript()
    memory = ProviderSafetyController(_active_policy())
    memory_result = await memory.execute(
        _context("offline-zero-duration-memory"),
        lambda: _return(transcript),
        actual_cost=lambda value: value.actual_cost_vnd,
    )

    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'durable.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = ProviderSafetyRepository(create_session_factory(engine))
    await repository.ensure_state()
    durable = DurableProviderSafetyController(
        _active_policy(),
        repository=repository,
        clock=lambda: datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
        operation_lease_seconds=20,
        operation_retention_days=400,
    )
    durable_result = await durable.execute(
        _context("offline-zero-duration-durable"),
        lambda: _return(transcript),
        actual_cost=lambda value: value.actual_cost_vnd,
    )
    await engine.dispose()

    for result in (memory_result, durable_result):
        point = result.value.segments[0].words[1]
        assert point.timing_semantics == "provider_boundary_point"
        assert point.start_seconds == point.end_seconds == 0.4
        with pytest.raises(PositiveDurationTranscriptRequired):
            require_positive_duration_transcript(result.value)
    assert memory_result.receipt.status == durable_result.receipt.status == "succeeded"


async def _return(value):
    return value
