"""Read-only SQL preparation of an exact S5 import request; no byte/provider IO."""
import copy
from typing import Literal

from pydantic import Field
from sqlalchemy import select, text

from .db import VideoProjectORM
from .production_db import ProductionPackageORM, ProductionApprovalORM, ProductionRenderJobORM, AudioMixVersionORM
from .production_models import MixConfig
from .timeline_db import TimelineORM, TimelineVersionORM
from .sql_variant_db import SqlVariantMemberORM
from .sql_variant_models import Contract, digest
from .sql_variant_repository import SqlVariantError
from .sql_variant_narration_models import NarrationReuseRequest
from .sql_variant_narration_projection import narration_projection, child_cues

INTERNAL_KEY = 'read-only-narration-proposal'


class NarrationProposalRead(Contract):
    schema_version: Literal['sql-variant-narration-proposal.v1'] = 'sql-variant-narration-proposal.v1'
    workspace_id: str
    master_project_id: str
    child_project_id: str
    family_id: str
    member_id: str
    actor_ref: str
    family_version: int = Field(ge=1)
    family_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    child_timeline_id: str
    child_timeline_version_id: str
    child_timeline_version: int = Field(ge=1)
    child_content_version_id: str
    source_current: Literal[True] = True
    child_script_approved: Literal[True] = True
    source_record_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_template: dict
    proposal_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    unit_count: int = Field(ge=1, le=300)
    duration_seconds: float = Field(gt=0, le=600, allow_inf_nan=False)
    downloads: Literal[0] = 0
    copies: Literal[0] = 0
    queue_calls: Literal[0] = 0
    provider_calls: Literal[0] = 0
    new_inferences: Literal[0] = 0
    cost_writes: Literal[0] = 0
    automatic_execution: Literal[False] = False
    human_review_required: Literal[True] = True
    approval_transferred: Literal[False] = False
    rights_authority_transferred: Literal[False] = False
    publishing_enabled: Literal[False] = False
    owner_uat_accepted: Literal[False] = False


async def read_narration_proposal(repository, workspace, master, family_id, child_id, *, actor_ref):
    """One point-in-time read snapshot. Existing POST rechecks every captured pin.

    SQLite gets an explicit read transaction. PostgreSQL gets read-only repeatable
    read locally on this session; no process-wide isolation or writer locks change.
    No no-op UPDATE is allowed: shared capture is explicitly called lock=False.
    """
    repository.families.actor(actor_ref)
    async with repository.session_factory() as session:
        dialect = session.get_bind().dialect.name
        if dialect == 'sqlite':
            await session.execute(text('BEGIN'))
        elif dialect == 'postgresql':
            await session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
            await session.execute(text('SET TRANSACTION READ ONLY'))
        else:
            raise SqlVariantError('SQL_VARIANT_NARRATION_PROPOSAL_STORAGE_NOT_CONFIGURED')
        family, _ = await repository._family(session, workspace, master, family_id, lock=False)
        member = await session.scalar(select(SqlVariantMemberORM).where(
            SqlVariantMemberORM.family_id == family_id, SqlVariantMemberORM.workspace_id == workspace,
            SqlVariantMemberORM.child_project_id == child_id))
        child = await session.scalar(select(VideoProjectORM).where(VideoProjectORM.project_id == child_id,
            VideoProjectORM.workspace_id == workspace))
        timeline = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == child_id,
            TimelineORM.workspace_id == workspace))
        package = await session.scalar(select(ProductionPackageORM).where(ProductionPackageORM.project_id == master,
            ProductionPackageORM.workspace_id == workspace))
        if member is None or child is None or timeline is None:
            raise KeyError('SQL_VARIANT_NOT_FOUND')
        approval = await session.get(ProductionApprovalORM, package.current_approval_id) if package else None
        source = await session.get(ProductionRenderJobORM, approval.preview_render_id) if approval else None
        audio = await session.get(AudioMixVersionORM, source.audio_version_id) if source else None
        version = await session.get(TimelineVersionORM, timeline.current_version_id)
        if approval is None or source is None or audio is None or version is None:
            raise SqlVariantError('SQL_VARIANT_NARRATION_APPROVED_SOURCE_REQUIRED')
        voice = MixConfig.model_validate(audio.config_json).voice
        manifest = copy.deepcopy(source.manifest_json)
        units = (manifest.get('narration') or {}).get('timing')
        if not isinstance(units, list) or not 0 < len(units) <= 300:
            raise SqlVariantError('SQL_VARIANT_NARRATION_PROVIDER_PROOF_CHANGED')
        try:
            profiles = [unit['provider_evidence']['profile_sha256'] for unit in units]
            normalizations = [unit['provider_evidence']['usage']['normalization_record_sha256'] for unit in units]
            projection = narration_projection(version.snapshot_json, child_cues(version.snapshot_json), voice)
            payload = NarrationReuseRequest(enabled=True, expected_version=family.version,
                expected_snapshot_sha256=family.snapshot_sha256, request_key=INTERNAL_KEY,
                member_id=member.member_id, child_project_id=child_id,
                expected_child_content_version_id=child.current_version_id,
                expected_child_timeline_version_id=timeline.current_version_id,
                expected_child_timeline_version=timeline.current_version, source_review_render_id=source.render_id,
                source_approval_id=approval.approval_id, expected_source_manifest_sha256=digest(manifest),
                expected_semantic_sha256=digest(projection), expected_profile_sha256s=profiles,
                expected_normalization_sha256s=normalizations, voice_config=voice,
                acknowledge_fresh_child_review=True)
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, SqlVariantError):
                raise
            raise SqlVariantError('SQL_VARIANT_NARRATION_PROVIDER_PROOF_CHANGED') from None
        # The shared verifier includes latest content, original approved manifest,
        # source/child semantics, exact voice and raw-asset metadata/provenance.
        capture = await repository._capture(session, workspace, master, family_id, payload,
            lock=False, actor_ref=actor_ref)
        if capture['child_content']['snapshot']['content'].get('approved') is not True:
            raise SqlVariantError('SQL_VARIANT_NARRATION_CHILD_SCRIPT_REVIEW_REQUIRED')
        value = dict(schema_version='sql-variant-narration-proposal.v1', workspace_id=workspace,
            master_project_id=master, child_project_id=child_id, family_id=family_id,
            member_id=member.member_id, actor_ref=actor_ref, family_version=family.version,
            family_snapshot_sha256=family.snapshot_sha256, child_timeline_id=timeline.timeline_id,
            child_timeline_version_id=timeline.current_version_id, child_timeline_version=timeline.current_version,
            child_content_version_id=child.current_version_id, source_record_sha256=digest(capture),
            request_template=payload.model_dump(mode='json', exclude={'request_key'}),
            unit_count=len(units), duration_seconds=projection['duration_seconds'])
        # Include all explicit safety fields in the public checksum. Clients use
        # these server hashes literally rather than recreating Python float JSON.
        proposed = NarrationProposalRead.model_validate({**value, 'proposal_sha256': '0' * 64})
        body = proposed.model_dump(mode='json', exclude={'proposal_sha256'})
        return proposed.model_copy(update={'proposal_sha256': digest(body)})
