from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from app.evidence_serialization import (
    canonical_evidence_bytes,
    canonical_evidence_sha256,
    canonical_evidence_value,
    write_evidence_bundle,
)
from app.vision_models import NormalizedBox
from app.vision_providers import (
    ProviderObjectDetection,
    ProviderOCRDetection,
    ProviderVisionFrame,
    ProviderVisionResult,
)


def recorded_frame() -> ProviderVisionFrame:
    return ProviderVisionFrame(
        timestamp_seconds=0.0,
        evidence_frame_reference="frame://owned/0001",
        caption="Căn góc nhìn ra công viên — đủ sáng",
        scene_description="Phòng khách có cửa kính lớn và cây xanh.",
        semantic_label="real_estate_interior",
        environment="indoor",
        action="static",
        objects=(
            ProviderObjectDetection(
                label="cửa sổ",
                category="object",
                confidence=0.94,
                bounding_box=NormalizedBox(x=0.1, y=0.2, width=0.5, height=0.6),
                track_hint=None,
            ),
        ),
        ocr=(
            ProviderOCRDetection(
                text="Ngọc Phương Đông",
                language="vi",
                confidence=0.98,
                bounding_box=NormalizedBox(x=0.2, y=0.8, width=0.4, height=0.1),
            ),
        ),
        primary_subject_box=NormalizedBox(x=0.2, y=0.1, width=0.6, height=0.8),
        saliency_box=None,
        headroom_ratio=0.12,
        visual_balance_score=0.91,
        safe_crop=True,
        quality_score=0.93,
        black_frame=False,
        blur_score=0.03,
        overexposed=False,
        underexposed=False,
        low_resolution=False,
        watermark_or_logo_detected=False,
        frozen_or_duplicate=False,
        quality_issues=(),
        confidence=0.95,
    )


def recorded_provider_success() -> ProviderVisionResult:
    return ProviderVisionResult(
        frames=(recorded_frame(),),
        provenance={
            "provider_key": "openai-vision",
            "model_requested": "gpt-5-mini",
            "model": "gpt-5-mini-2025-08-07",
            "provider_request_id": "req_recorded_success",
            "client_request_id": "vf-recorded-success",
            "request_sha256": "a" * 64,
            "response_sha256": "b" * 64,
            "latency_ms": 1240,
            "cost_receipt": {
                "status": "actual",
                "currency": "VND",
                "input_tokens": 1996,
                "output_tokens": 2371,
                "actual_cost_vnd": "137.6287",
            },
            "secret_recorded": False,
        },
        actual_cost_vnd=Decimal("137.6287"),
    )


def test_provider_vision_frame_serializes_nested_nullable_and_unicode() -> None:
    serialized = canonical_evidence_value(
        {
            "frame": recorded_frame(),
            "nullable": None,
            "list": ["Tiếng Việt", {"active": True}],
        }
    )

    assert serialized["frame"]["caption"] == "Căn góc nhìn ra công viên — đủ sáng"
    assert serialized["frame"]["objects"][0]["track_hint"] is None
    assert serialized["frame"]["objects"][0]["bounding_box"] == {
        "height": 0.6,
        "width": 0.5,
        "x": 0.1,
        "y": 0.2,
    }
    assert serialized["frame"]["ocr"][0]["text"] == "Ngọc Phương Đông"
    assert serialized["frame"]["quality_issues"] == []
    assert serialized["nullable"] is None


def test_canonical_json_and_sha_are_deterministic() -> None:
    first = {
        "z": recorded_frame(),
        "a": {"currency": "VND", "actual": Decimal("137.6287")},
    }
    second = {
        "a": {"actual": Decimal("137.6287"), "currency": "VND"},
        "z": recorded_frame(),
    }

    assert canonical_evidence_bytes(first) == canonical_evidence_bytes(second)
    assert canonical_evidence_sha256(first) == canonical_evidence_sha256(second)
    assert (
        canonical_evidence_sha256(first)
        == "59b90b3233255666262699c781c474521716b107c7854256d7033a6d04966480"
    )
    assert "Ngọc Phương Đông" in canonical_evidence_bytes(first).decode("utf-8")


def test_recorded_provider_success_writes_complete_offline_evidence(tmp_path: Path) -> None:
    output = tmp_path / "operation-result.json"
    result = recorded_provider_success()
    payload = {
        "evidence_version": 1,
        "verdict": "PASS",
        "production_verdict": "NO-GO",
        "execution": {
            "provider_result": result,
            "structured_frames": result.frames,
            "provider_provenance": result.provenance,
        },
    }

    receipt = write_evidence_bundle(
        output,
        payload,
        durable_fallback_context={"operation_status": "succeeded"},
    )
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert receipt.status == "written"
    assert receipt.evidence_path == output
    assert receipt.sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
    assert evidence["execution"]["structured_frames"][0]["caption"].startswith("Căn góc")
    provenance = evidence["execution"]["provider_provenance"]
    assert provenance["provider_request_id"] == "req_recorded_success"
    assert provenance["client_request_id"] == "vf-recorded-success"
    assert provenance["request_sha256"] == "a" * 64
    assert provenance["response_sha256"] == "b" * 64
    assert provenance["cost_receipt"]["actual_cost_vnd"] == "137.6287"
    assert evidence["execution"]["provider_result"]["actual_cost_vnd"] == "137.6287"


def test_serialization_failure_writes_review_required_durable_fallback(tmp_path: Path) -> None:
    output = tmp_path / "operation-result.json"
    durable_ledger = {
        "operation_key": "v3-01-rc6-openai-vision-call-01",
        "operation_status": "succeeded",
        "attempt_status": "succeeded",
        "attempt_count": 1,
        "actual_cost_vnd": Decimal("137.6287"),
        "usage": {"input_tokens": 1996, "output_tokens": 2371},
    }
    original_ledger = dict(durable_ledger)

    receipt = write_evidence_bundle(
        output,
        {"provider_result": object()},
        durable_fallback_context=durable_ledger,
    )
    fallback = json.loads(receipt.evidence_path.read_text(encoding="utf-8"))

    assert receipt.status == "fallback_written"
    assert receipt.error_code == "EVIDENCE_UNSUPPORTED_TYPE"
    assert output.exists() is False
    assert fallback["verdict"] == "REVIEW_REQUIRED"
    assert fallback["error"]["phase"] == "post_call_evidence_serialization"
    assert fallback["error"]["secret_recorded"] is False
    assert fallback["durable_context"]["operation_status"] == "succeeded"
    assert fallback["durable_context"]["actual_cost_vnd"] == "137.6287"
    assert durable_ledger == original_ledger


def test_secret_detection_keeps_only_minimal_fallback_context(tmp_path: Path) -> None:
    output = tmp_path / "operation-result.json"
    secret = "sk-" + ("x" * 24)

    receipt = write_evidence_bundle(
        output,
        {"provider_result": {"credential": secret}},
        durable_fallback_context={
            "operation_status": "succeeded",
            "unsafe_copy": secret,
        },
        forbidden_values=(secret,),
    )
    serialized = receipt.evidence_path.read_text(encoding="utf-8")
    fallback = json.loads(serialized)

    assert receipt.status == "fallback_written"
    assert receipt.error_code == "EVIDENCE_SECRET_DETECTED"
    assert secret not in serialized
    assert fallback["durable_context"] == {
        "reason": "fallback context failed secret containment",
        "status": "withheld",
    }
    assert fallback["error"]["secret_recorded"] is False
