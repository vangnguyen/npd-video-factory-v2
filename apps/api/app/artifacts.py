from __future__ import annotations

from pathlib import Path

from .models import Artifact, JobRecord


class ArtifactAccessError(ValueError):
    pass


def job_directory(root: Path, job_id: str) -> Path:
    if not job_id.startswith("vid_") or len(job_id) > 80:
        raise ArtifactAccessError("invalid job id")
    root_resolved = root.resolve()
    candidate = (root_resolved / job_id).resolve()
    if candidate.parent != root_resolved:
        raise ArtifactAccessError("job directory escaped storage root")
    return candidate


def recorded_artifact(record: JobRecord, artifact_name: str) -> Artifact:
    artifact = next((item for item in record.artifacts if item.name == artifact_name), None)
    if artifact is None:
        raise ArtifactAccessError("artifact not recorded for job")
    return artifact


def recorded_artifact_path(root: Path, record: JobRecord, artifact_name: str) -> Path:
    recorded_artifact(record, artifact_name)
    if Path(artifact_name).name != artifact_name:
        raise ArtifactAccessError("invalid artifact name")
    candidate = (job_directory(root, record.job_id) / artifact_name).resolve()
    expected_parent = job_directory(root, record.job_id)
    if candidate.parent != expected_parent:
        raise ArtifactAccessError("artifact escaped job directory")
    return candidate


def resolve_recorded_artifact(root: Path, record: JobRecord, artifact_name: str) -> Path:
    candidate = recorded_artifact_path(root, record, artifact_name)
    if not candidate.is_file():
        raise ArtifactAccessError("artifact file missing")
    return candidate
