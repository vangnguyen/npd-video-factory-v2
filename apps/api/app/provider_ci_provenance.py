from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, ValidationError, field_validator, model_validator

from .models import StrictModel


ALLOWED_GOVERNANCE_PATH_PREFIXES = (
    "apps/api/tests/",
    "docs/acceptance/v3-01/",
    "evidence/v3-01/",
)
EXECUTABLE_TREE_PATHS = (
    ".env.example",
    ".github/workflows/ci.yml",
    "apps/api/app",
    "apps/api/pyproject.toml",
    "apps/studio-web",
    "deploy",
    "docker-compose.yml",
    "packages",
    "renderer",
    "scripts",
    "services",
    "workflows",
)


class ProviderCiProvenanceError(ValueError):
    """Raised when executable and governance CI lineage cannot be trusted."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProviderCiRunEvidence(StrictModel):
    """One completed CI run bound to exactly one commit and provenance role."""

    role: Literal["executable_rc", "governance_main"]
    workflow_name: Literal["Video Factory V2 CI"]
    run_id: int = Field(gt=0)
    commit_sha: str = Field(pattern=r"^[a-f0-9]{40}$")
    status: Literal["completed"]
    conclusion: Literal["success"]
    jobs_total: int = Field(gt=0)
    jobs_succeeded: int = Field(gt=0)
    completed_at_utc: datetime

    @field_validator("run_id", "jobs_total", "jobs_succeeded", mode="before")
    @classmethod
    def integers_must_be_json_integers(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("CI integer fields must be JSON integers")
        return value

    @field_validator("completed_at_utc")
    @classmethod
    def completed_timestamp_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("CI completion timestamp must be timezone aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def all_jobs_must_succeed(self) -> "ProviderCiRunEvidence":
        if self.jobs_succeeded != self.jobs_total:
            raise ValueError("every job in the bound CI run must succeed")
        return self


class ProviderAcceptanceCiProvenance(StrictModel):
    """Canonical dual-CI contract for a post-governance acceptance runner.

    The executable candidate and the governance merge have different CI roles.
    A single run can never satisfy both roles. The governance commit may change
    tests and acceptance evidence, but its selected executable tree must remain
    byte-identical to the locked RC.
    """

    version: Literal[1] = 1
    executable_rc_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    governance_main_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    executable_rc_ci: ProviderCiRunEvidence
    governance_main_ci: ProviderCiRunEvidence
    executable_tree_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    governance_executable_tree_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    governance_changed_paths: tuple[str, ...] = Field(min_length=1)

    @field_validator("governance_changed_paths", mode="before")
    @classmethod
    def paths_must_be_a_json_array(cls, value: object) -> object:
        if not isinstance(value, list):
            raise ValueError("governance changed paths must be a JSON array")
        return value

    @field_validator("governance_changed_paths")
    @classmethod
    def paths_must_be_canonical_and_allowlisted(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if tuple(sorted(set(value))) != value:
            raise ValueError("governance changed paths must be unique and sorted")
        for path in value:
            if (
                not path
                or "\\" in path
                or path.startswith("/")
                or any(part in {"", ".", ".."} for part in path.split("/"))
            ):
                raise ValueError("governance changed path is not canonical")
            if not path.startswith(ALLOWED_GOVERNANCE_PATH_PREFIXES):
                raise ValueError("governance diff contains a non-allowlisted path")
        return value

    @model_validator(mode="after")
    def bind_each_ci_run_to_its_own_role(self) -> "ProviderAcceptanceCiProvenance":
        if self.executable_rc_ci.role != "executable_rc":
            raise ValueError("executable RC CI role mismatch")
        if self.governance_main_ci.role != "governance_main":
            raise ValueError("governance main CI role mismatch")
        if self.executable_rc_ci.commit_sha != self.executable_rc_commit:
            raise ValueError("executable RC CI commit mismatch")
        if self.governance_main_ci.commit_sha != self.governance_main_commit:
            raise ValueError("governance main CI commit mismatch")
        if self.executable_rc_ci.run_id == self.governance_main_ci.run_id:
            raise ValueError("one CI run cannot satisfy both provenance roles")
        if self.executable_rc_commit == self.governance_main_commit:
            raise ValueError("governance main must be distinct from the executable RC")
        if (
            self.executable_tree_sha256
            != self.governance_executable_tree_sha256
        ):
            raise ValueError("governance merge changed the executable tree")
        return self


def validate_provider_acceptance_ci_provenance(
    payload: object,
    *,
    expected_executable_rc_commit: str,
    expected_governance_main_commit: str,
    expected_executable_rc_ci_run_id: int,
    expected_governance_main_ci_run_id: int,
) -> ProviderAcceptanceCiProvenance:
    """Strictly validate live-observed dual-CI provenance against authority."""

    try:
        provenance = ProviderAcceptanceCiProvenance.model_validate(payload)
    except ValidationError as exc:
        raise ProviderCiProvenanceError(
            "CI_PROVENANCE_INVALID",
            "CI provenance contract is invalid",
        ) from exc

    exact_values = (
        (
            provenance.executable_rc_commit,
            expected_executable_rc_commit,
            "EXECUTABLE_RC_COMMIT_MISMATCH",
        ),
        (
            provenance.governance_main_commit,
            expected_governance_main_commit,
            "GOVERNANCE_MAIN_COMMIT_MISMATCH",
        ),
        (
            provenance.executable_rc_ci.run_id,
            expected_executable_rc_ci_run_id,
            "EXECUTABLE_RC_CI_RUN_MISMATCH",
        ),
        (
            provenance.governance_main_ci.run_id,
            expected_governance_main_ci_run_id,
            "GOVERNANCE_MAIN_CI_RUN_MISMATCH",
        ),
    )
    for actual, expected, code in exact_values:
        if actual != expected:
            raise ProviderCiProvenanceError(code, code.replace("_", " ").lower())
    return provenance


def provider_ci_provenance_sha256(
    provenance: ProviderAcceptanceCiProvenance,
) -> str:
    """Return a deterministic hash suitable for an operation authority record."""

    encoded = json.dumps(
        provenance.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def executable_tree_sha256(tree_objects: dict[str, str]) -> str:
    """Hash the exact Git object IDs for every executable path.

    The collector must obtain these object IDs independently for the RC and
    governance commits. Missing, extra or malformed objects fail closed.
    """

    if set(tree_objects) != set(EXECUTABLE_TREE_PATHS):
        raise ProviderCiProvenanceError(
            "EXECUTABLE_TREE_PATH_SET_MISMATCH",
            "executable tree path set does not match the canonical contract",
        )
    if any(
        not isinstance(object_id, str)
        or len(object_id) != 40
        or any(character not in "0123456789abcdef" for character in object_id)
        for object_id in tree_objects.values()
    ):
        raise ProviderCiProvenanceError(
            "EXECUTABLE_TREE_OBJECT_INVALID",
            "executable tree contains an invalid Git object ID",
        )
    encoded = json.dumps(
        {path: tree_objects[path] for path in sorted(tree_objects)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
