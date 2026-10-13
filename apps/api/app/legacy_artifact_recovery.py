"""Recorded vid_ object recovery only; local resolver/history are unchanged."""
import copy
from pathlib import Path

from .artifacts import ArtifactAccessError, recorded_artifact, recorded_artifact_path
from .verified_artifact_delivery import RecordedArtifactRead, ArtifactDeliveryRejected, deliver_verified_artifact, legacy_sql_snapshot


def recovery_identity(record, artifact):
    return {'job_id':record.job_id, 'workspace_id':record.workspace_id, 'project_id':record.project_id,
        'project_version_id':record.project_version_id, 'status':str(record.status),
        'request':record.request.model_dump(mode='json'), 'artifact':artifact.model_dump(mode='json')}


async def recover_legacy_artifact(*, root, record, artifact_name, store, storage):
    # Preserve existing vid_/recorded-name/path validation before any IO.
    recorded_artifact_path(root, record, artifact_name)
    artifact = recorded_artifact(record, artifact_name).model_copy(deep=True)
    expected = copy.deepcopy(recovery_identity(record, artifact))
    proof = RecordedArtifactRead(artifact.object_key, record.workspace_id, record.project_id,
        artifact.size_bytes, artifact.checksum_sha256, artifact.storage_provider, allow_empty=True)
    if storage.name != proof.storage_provider:
        raise ArtifactDeliveryRejected('ARTIFACT_READ_PROVIDER_CHANGED')
    frozen = await legacy_sql_snapshot(store.session_factory, record.job_id)
    if (frozen is None or frozen['workspace_id']!=record.workspace_id or frozen['project_id']!=record.project_id
            or frozen['project_version_id']!=record.project_version_id or frozen['status']!=str(record.status)
            or frozen['request_json']!=expected['request']
            or [entry for entry in frozen['artifacts_json'] if entry.get('name')==artifact_name]!=[expected['artifact']]):
        raise ArtifactAccessError('recorded artifact changed')

    async def current():
        latest = await legacy_sql_snapshot(store.session_factory, record.job_id)
        if latest != frozen:
            raise ArtifactAccessError('recorded artifact changed')

    # Recovery does not overwrite a retained local artifact or guess nullable
    # metadata. Its private, fixed-name file lives only for this response.
    return await deliver_verified_artifact(proof=proof, storage=storage,
        staging_root=Path(root)/'.artifact-downloads', basename='artifact.bin', filename=artifact_name,
        media_type=artifact.content_type, current=current)
