from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.provider_ci_provenance import (
    EXECUTABLE_TREE_PATHS,
    ProviderCiProvenanceError,
    executable_tree_sha256,
    provider_ci_provenance_sha256,
    validate_provider_acceptance_ci_provenance,
)


RC_COMMIT = "256bda59eed028ddd642cdb0988c409c489fd655"
GOVERNANCE_COMMIT = "e48d7edebcbfb1bd4113c2e40ab4ce46c186f6e4"
RC_CI_RUN_ID = 33449162326
GOVERNANCE_CI_RUN_ID = 33499392585
EXECUTABLE_TREE_SHA256 = "a" * 64
REPO_ROOT = Path(__file__).resolve().parents[3]


def _ci_run(*, role: str, run_id: int, commit: str) -> dict[str, object]:
    return {
        "role": role,
        "workflow_name": "Video Factory V2 CI",
        "run_id": run_id,
        "commit_sha": commit,
        "status": "completed",
        "conclusion": "success",
        "jobs_total": 5,
        "jobs_succeeded": 5,
        "completed_at_utc": "2026-09-01T14:00:00Z",
    }


def _payload() -> dict[str, object]:
    return {
        "version": 1,
        "executable_rc_commit": RC_COMMIT,
        "governance_main_commit": GOVERNANCE_COMMIT,
        "executable_rc_ci": _ci_run(
            role="executable_rc",
            run_id=RC_CI_RUN_ID,
            commit=RC_COMMIT,
        ),
        "governance_main_ci": _ci_run(
            role="governance_main",
            run_id=GOVERNANCE_CI_RUN_ID,
            commit=GOVERNANCE_COMMIT,
        ),
        "executable_tree_sha256": EXECUTABLE_TREE_SHA256,
        "governance_executable_tree_sha256": EXECUTABLE_TREE_SHA256,
        "governance_changed_paths": [
            "apps/api/tests/test_provider_gate_loader.py",
            "docs/acceptance/v3-01/38_V3_01_RC9_VISION_ACCEPTANCE_WINDOW.md",
            "evidence/v3-01/rc9/provider/rc9-vision-gate-rebind.json",
        ],
    }


def _validate(payload: object):
    return validate_provider_acceptance_ci_provenance(
        payload,
        expected_executable_rc_commit=RC_COMMIT,
        expected_governance_main_commit=GOVERNANCE_COMMIT,
        expected_executable_rc_ci_run_id=RC_CI_RUN_ID,
        expected_governance_main_ci_run_id=GOVERNANCE_CI_RUN_ID,
    )


def test_dual_ci_provenance_binds_both_successful_runs_and_stable_hash() -> None:
    provenance = _validate(_payload())

    assert provenance.executable_rc_ci.run_id == RC_CI_RUN_ID
    assert provenance.governance_main_ci.run_id == GOVERNANCE_CI_RUN_ID
    assert provenance.executable_tree_sha256 == (
        provenance.governance_executable_tree_sha256
    )
    assert provider_ci_provenance_sha256(provenance) == (
        provider_ci_provenance_sha256(_validate(_payload()))
    )


def test_swapped_ci_ids_fail_closed() -> None:
    payload = _payload()
    payload["executable_rc_ci"]["run_id"] = GOVERNANCE_CI_RUN_ID
    payload["governance_main_ci"]["run_id"] = RC_CI_RUN_ID

    with pytest.raises(
        ProviderCiProvenanceError,
        match="executable rc ci run mismatch",
    ) as error:
        _validate(payload)
    assert error.value.code == "EXECUTABLE_RC_CI_RUN_MISMATCH"


def test_one_ci_run_cannot_substitute_for_both_roles() -> None:
    payload = _payload()
    payload["governance_main_ci"]["run_id"] = RC_CI_RUN_ID

    with pytest.raises(ProviderCiProvenanceError) as error:
        _validate(payload)
    assert error.value.code == "CI_PROVENANCE_INVALID"


def test_stale_governance_ci_fails_closed() -> None:
    payload = _payload()
    payload["governance_main_ci"]["run_id"] = 33490000000

    with pytest.raises(
        ProviderCiProvenanceError,
        match="governance main ci run mismatch",
    ) as error:
        _validate(payload)
    assert error.value.code == "GOVERNANCE_MAIN_CI_RUN_MISMATCH"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("executable_rc_commit", "b" * 40),
        ("governance_main_commit", "c" * 40),
    ],
)
def test_wrong_authority_commit_sha_fails_closed(field: str, value: str) -> None:
    payload = _payload()
    payload[field] = value
    if field == "executable_rc_commit":
        payload["executable_rc_ci"]["commit_sha"] = value
    else:
        payload["governance_main_ci"]["commit_sha"] = value

    with pytest.raises(ProviderCiProvenanceError):
        _validate(payload)


@pytest.mark.parametrize("role", ["executable_rc_ci", "governance_main_ci"])
def test_failed_or_incomplete_ci_fails_closed(role: str) -> None:
    for mutation in (
        {"conclusion": "failure"},
        {"status": "in_progress"},
        {"jobs_succeeded": 4},
    ):
        payload = _payload()
        payload[role].update(mutation)
        with pytest.raises(ProviderCiProvenanceError) as error:
            _validate(payload)
        assert error.value.code == "CI_PROVENANCE_INVALID"


def test_governance_runtime_file_change_fails_closed() -> None:
    payload = _payload()
    payload["governance_changed_paths"] = [
        "apps/api/app/openai_vision_provider.py",
        "docs/acceptance/v3-01/38_V3_01_RC9_VISION_ACCEPTANCE_WINDOW.md",
    ]

    with pytest.raises(ProviderCiProvenanceError) as error:
        _validate(payload)
    assert error.value.code == "CI_PROVENANCE_INVALID"


def test_governance_executable_tree_drift_fails_closed() -> None:
    payload = _payload()
    payload["governance_executable_tree_sha256"] = "b" * 64

    with pytest.raises(ProviderCiProvenanceError) as error:
        _validate(payload)
    assert error.value.code == "CI_PROVENANCE_INVALID"


@pytest.mark.parametrize(
    "missing",
    [
        "executable_rc_ci",
        "governance_main_ci",
        "executable_tree_sha256",
        "governance_executable_tree_sha256",
        "governance_changed_paths",
    ],
)
def test_missing_provenance_field_fails_closed(missing: str) -> None:
    payload = _payload()
    payload.pop(missing)

    with pytest.raises(ProviderCiProvenanceError) as error:
        _validate(payload)
    assert error.value.code == "CI_PROVENANCE_INVALID"


def test_legacy_single_ci_field_fails_closed() -> None:
    payload = _payload()
    payload.pop("executable_rc_ci")
    payload.pop("governance_main_ci")
    payload["exact_main_ci_run_id"] = GOVERNANCE_CI_RUN_ID

    with pytest.raises(ProviderCiProvenanceError) as error:
        _validate(payload)
    assert error.value.code == "CI_PROVENANCE_INVALID"


def test_changed_paths_must_be_complete_canonical_sorted_input() -> None:
    payload = _payload()
    payload["governance_changed_paths"] = list(
        reversed(payload["governance_changed_paths"])
    )

    with pytest.raises(ProviderCiProvenanceError) as error:
        _validate(payload)
    assert error.value.code == "CI_PROVENANCE_INVALID"


def test_extra_field_fails_closed() -> None:
    payload = deepcopy(_payload())
    payload["governance_main_ci"]["replacement_for_executable_ci"] = True

    with pytest.raises(ProviderCiProvenanceError) as error:
        _validate(payload)
    assert error.value.code == "CI_PROVENANCE_INVALID"


def test_executable_tree_binding_is_canonical_and_complete() -> None:
    objects = {
        path: format(index + 1, "040x")
        for index, path in enumerate(EXECUTABLE_TREE_PATHS)
    }

    assert executable_tree_sha256(objects) == executable_tree_sha256(
        dict(reversed(list(objects.items())))
    )


@pytest.mark.parametrize("mutation", ["missing", "extra", "invalid_object"])
def test_executable_tree_binding_fails_closed(mutation: str) -> None:
    objects = {
        path: format(index + 1, "040x")
        for index, path in enumerate(EXECUTABLE_TREE_PATHS)
    }
    if mutation == "missing":
        objects.pop(EXECUTABLE_TREE_PATHS[0])
    elif mutation == "extra":
        objects["apps/api/tests"] = "f" * 40
    elif mutation == "invalid_object":
        objects[EXECUTABLE_TREE_PATHS[0]] = "not-a-git-object"
    else:  # pragma: no cover - parameter list is exhaustive
        raise AssertionError(mutation)

    with pytest.raises(ProviderCiProvenanceError):
        executable_tree_sha256(objects)


def test_checked_in_rc9_dual_ci_diagnosis_is_canonical_and_zero_call() -> None:
    evidence_path = REPO_ROOT / (
        "docs/acceptance/v3-01/evidence/rc9-openai-vision-operation-1/"
        "dual-ci-provenance-pass.json"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    provenance = _validate(evidence["contract"])

    assert provider_ci_provenance_sha256(provenance) == (
        evidence["provenance_sha256"]
    )
    assert evidence["credential_reads"] == 0
    assert evidence["provider_calls"] == 0
    assert evidence["reservation_vnd"] == "0"
    assert evidence["production_verdict"] == "NO-GO"
