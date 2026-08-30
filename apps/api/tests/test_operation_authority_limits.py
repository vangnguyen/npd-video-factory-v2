from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from app.provider_gate_loader import (
    ProviderGateBundle,
    ProviderOperationAuthorityLimits,
    ProviderOperationAuthorityLimitsError,
    validate_operation_authority_limits,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
RC6_BUNDLE_PATH = (
    REPO_ROOT
    / "docs"
    / "acceptance"
    / "v3-01"
    / "V3-01-GATE-RC6-OPENAI-VISION-A.json"
)


def _rc6_bundle() -> ProviderGateBundle:
    return ProviderGateBundle.model_validate_json(RC6_BUNDLE_PATH.read_text(encoding="utf-8"))


def _canonical_limits() -> dict[str, object]:
    return {
        "currency": "VND",
        "images": 1,
        "max_dimension_pixels": 2048,
        "image_detail": "high",
        "input_token_ceiling": 16_384,
        "max_output_tokens": 4_096,
        "per_operation_limit_vnd": "500",
        "acceptance_window_limit_vnd": "1250",
        "timeout_seconds": 60,
        "max_concurrent_calls": 1,
        "max_attempts": 1,
        "automatic_retry": False,
        "model_fallback": False,
    }


def test_rc6_bundle_passes_the_canonical_runner_limits_contract_offline() -> None:
    bundle = _rc6_bundle()

    limits = validate_operation_authority_limits(
        _canonical_limits(),
        budget=bundle.budget,
    )

    assert limits == ProviderOperationAuthorityLimits.from_gate_budget(bundle.budget)
    assert limits.per_operation_limit_vnd == Decimal("500")
    assert limits.acceptance_window_limit_vnd == Decimal("1250")
    assert limits.same_utc_day_runtime_daily_limit_vnd == Decimal("1250")
    assert set(limits.model_dump(mode="json")) == set(_canonical_limits())
    assert "daily_limit_vnd" not in ProviderOperationAuthorityLimits.model_fields
    assert "reservation_vnd" not in ProviderOperationAuthorityLimits.model_fields


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("missing", None),
        ("legacy_field", None),
        ("wrong_integer_type", "2048"),
        ("wrong_boolean_type", "false"),
        ("wrong_vnd_type", 500),
        ("wrong_vnd_amount", "501"),
        ("wrong_window_amount", "1000"),
        ("daily_alias", "1250"),
    ],
)
def test_authority_limits_fail_closed_on_missing_wrong_type_name_or_amount(
    mutation: str,
    value: object,
) -> None:
    payload = deepcopy(_canonical_limits())
    if mutation == "missing":
        payload.pop("acceptance_window_limit_vnd")
    elif mutation == "legacy_field":
        payload["reservation_vnd"] = payload.pop("per_operation_limit_vnd")
    elif mutation == "wrong_integer_type":
        payload["max_dimension_pixels"] = value
    elif mutation == "wrong_boolean_type":
        payload["automatic_retry"] = value
    elif mutation == "wrong_vnd_type":
        payload["per_operation_limit_vnd"] = value
    elif mutation == "wrong_vnd_amount":
        payload["per_operation_limit_vnd"] = value
    elif mutation == "wrong_window_amount":
        payload["acceptance_window_limit_vnd"] = value
    elif mutation == "daily_alias":
        payload["daily_limit_vnd"] = value
    else:  # pragma: no cover - parameter list is exhaustive
        raise AssertionError(mutation)

    with pytest.raises(ProviderOperationAuthorityLimitsError):
        validate_operation_authority_limits(payload, budget=_rc6_bundle().budget)


def test_rc6_legacy_runner_shape_reproduces_the_exact_pre_call_mismatch() -> None:
    legacy_rc6_runner_limits = {
        "images": 1,
        "max_dimension_pixels": 2048,
        "image_detail": "high",
        "input_token_ceiling": 16_384,
        "max_output_tokens": 4_096,
        "reservation_vnd": "500",
        "timeout_seconds": 60,
        "max_concurrent_calls": 1,
        "max_attempts": 1,
        "automatic_retry": False,
        "model_fallback": False,
    }

    with pytest.raises(
        ProviderOperationAuthorityLimitsError,
        match="operation authority limits are invalid",
    ):
        validate_operation_authority_limits(
            legacy_rc6_runner_limits,
            budget=_rc6_bundle().budget,
        )


def test_canonical_contract_rejects_window_limit_that_cannot_cover_two_slots() -> None:
    payload = _canonical_limits()
    payload["acceptance_window_limit_vnd"] = "999"

    with pytest.raises(ProviderOperationAuthorityLimitsError):
        validate_operation_authority_limits(payload, budget=_rc6_bundle().budget)
