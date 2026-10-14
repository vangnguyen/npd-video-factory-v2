"""Opt-in queue admission; immutable selector and verified actor before handoff."""
import copy
from typing import Literal
from types import SimpleNamespace
from sqlalchemy import select, update
from .sql_variant_models import Contract, digest
from .sql_variant_repository import SqlVariantError
from .sql_variant_db import SqlVariantArtifactReceiptORM
from .sql_variant_narration_models import NarrationReuseRequest, NarrationReuseRead
from .sql_variant_narration_render import VariantNarrationRenderRequest
from .sql_variant_narration_projection import narration_projection
from .production_models import RenderCreateRequest
from .production_db import SubtitleVersionORM, AudioMixVersionORM, ProductionPackageORM
from .timeline_db import TimelineVersionORM
from .sql_tts_artifact_reuse import canonical_audio_binding


class NarrationMutationRead(Contract):
    receipt: NarrationReuseRead
    replayed: bool


class NarrationAvailabilityRead(Contract):
    state: Literal['CONFIGURED', 'NOT_CONFIGURED']
    reason_code: str | None
    source_current: bool
    source_current_reason: str | None
    family_version: int
    family_snapshot_sha256: str
    new_inferences: Literal[0] = 0
    human_review_required: Literal[True] = True
    production_accepted: Literal[False] = False


class NarrationReviewCreateRequest(RenderCreateRequest):
    selection: VariantNarrationRenderRequest


class VariantNarrationQueueUnknownError(RuntimeError):
    def __init__(self, render_id):
        self.render_id = render_id
        super().__init__('SQL_VARIANT_NARRATION_QUEUE_OUTCOME_UNKNOWN')


class VariantNarrationAdmission:
    def __init__(self, repository, copier, loader, fence):
        self.repository, self.copier, self.loader, self.fence = repository, copier, loader, fence
        self._storage = copier.storage
        self._root = (str(copier.storage.root), str(copier.storage._io_root))

    def configured(self):
        from .object_storage import LocalObjectStorageProvider
        from .sql_variant_narration_render import VariantNarrationReviewLoader, VariantNarrationTerminalFence
        if (type(self._storage) is not LocalObjectStorageProvider or self.copier.storage is not self._storage
                or (str(self._storage.root), str(self._storage._io_root)) != self._root
                or type(self.loader) is not VariantNarrationReviewLoader or self.loader.enabled is not True
                or self.loader.repository is not self.repository or self.loader.copier is not self.copier
                or self.loader.assets.session_factory is not self.repository.session_factory
                or type(self.fence) is not VariantNarrationTerminalFence
                or self.fence.repository is not self.repository or self.fence.copier is not self.copier):
            raise SqlVariantError('SQL_VARIANT_NARRATION_NOT_CONFIGURED')

    async def lock_selection(self, session, child, selection, actor_ref):
        self.configured()
        selection = VariantNarrationRenderRequest.model_validate(selection)
        if selection.enabled is not True:
            raise SqlVariantError('SQL_VARIANT_NARRATION_NOT_CONFIGURED')
        self.repository.families.actor(actor_ref)
        # Read the immutable receipt only to obtain its workspace, then take the
        # same master→family→child lock order as import and terminal completion.
        receipt = await session.get(SqlVariantArtifactReceiptORM, selection.receipt_id)
        if receipt is None:
            raise KeyError('narration receipt')
        workspace = receipt.workspace_id
        await self.repository._family(session, workspace, selection.master_project_id, selection.family_id, lock=True)
        await self.repository.families._project(session, workspace, child, lock=True)
        receipt = await session.get(SqlVariantArtifactReceiptORM, selection.receipt_id, with_for_update=True, populate_existing=True)
        self.repository.validate(receipt)
        if (receipt.state, receipt.family_id, receipt.member_id, receipt.input_json['child_project_id'],
                receipt.input_sha256, receipt.result_sha256) != ('ready', selection.family_id, selection.member_id,
                child, selection.input_sha256, selection.result_sha256):
            raise SqlVariantError('SQL_VARIANT_NARRATION_CHANGED')
        target_package = await session.scalar(select(ProductionPackageORM).where(
            ProductionPackageORM.project_id == child, ProductionPackageORM.workspace_id == workspace))
        package_ids = {receipt.input_json['source_package']['package_id']}
        if target_package is not None:
            package_ids.add(target_package.package_id)
        for package_id in sorted(package_ids):
            await session.execute(update(ProductionPackageORM).where(ProductionPackageORM.package_id == package_id)
                .values(updated_at=ProductionPackageORM.updated_at))
            await session.get(ProductionPackageORM, package_id, with_for_update=True, populate_existing=True)
        await self.repository.validate_result(session, receipt)
        payload = NarrationReuseRequest.model_validate({**receipt.input_json['request'], 'request_key': 'internal-s5-admission'})
        current = await self.repository._capture(session, workspace, selection.master_project_id,
            selection.family_id, payload, actor_ref=receipt.actor_ref)
        if current != receipt.input_json:
            raise SqlVariantError('SQL_VARIANT_NARRATION_CHANGED')
        if current['child_content']['snapshot']['content'].get('approved') is not True:
            raise SqlVariantError('SQL_VARIANT_NARRATION_CHILD_SCRIPT_REVIEW_REQUIRED')
        return receipt

    async def package_binding(self, session, package, receipt):
        from .production_models import MixConfig, SubtitleCue, SubtitleStyle
        timeline = await session.get(TimelineVersionORM, package.timeline_version_id, populate_existing=True)
        subtitle = await session.get(SubtitleVersionORM, package.current_subtitle_version_id, populate_existing=True)
        audio = await session.get(AudioMixVersionORM, package.current_audio_version_id, populate_existing=True)
        if timeline is None or subtitle is None or audio is None:
            raise SqlVariantError('SQL_VARIANT_NARRATION_CHANGED')
        config = MixConfig.model_validate(audio.config_json)
        subtitles = SimpleNamespace(cues=[SubtitleCue.model_validate(c) for c in subtitle.cues_json],
            style=SubtitleStyle.model_validate(subtitle.style_json))
        if narration_projection(timeline.snapshot_json, subtitles.cues, config.voice) != receipt.input_json['projection']:
            raise SqlVariantError('SQL_VARIANT_NARRATION_SEMANTICS_CHANGED')
        render = SimpleNamespace(workspace_id=package.workspace_id, project_id=package.project_id,
            timeline_version_id=package.timeline_version_id, subtitle_version_id=subtitle.subtitle_version_id,
            audio_version_id=audio.audio_version_id)
        return canonical_audio_binding(render, timeline.snapshot_json, subtitles, config)

    async def capture(self, session, package, receipt, selection, actor_ref):
        binding = await self.package_binding(session, package, receipt)
        value = {'schema_version': 'sql-variant-narration-admission.v1', 'selection': copy.deepcopy(selection),
            'actor_ref': actor_ref, 'receipt_actor_ref': receipt.actor_ref,
            'child_content_version_id': receipt.input_json['child_content']['project_version_id'],
            'canonical_audio_binding_sha256': digest(binding)}
        return {**value, 'admission_sha256': digest(value)}

    async def recheck(self, session, render):
        self.configured()
        manifest = render.manifest_json
        value = manifest.get('variant_narration_admission')
        selection = manifest.get('variant_narration_request')
        if (not isinstance(value, dict) or value.get('selection') != selection
                or value.get('actor_ref') != manifest.get('requested_by')
                or value.get('admission_sha256') != digest({k: v for k, v in value.items() if k != 'admission_sha256'})):
            raise SqlVariantError('SQL_VARIANT_NARRATION_ADMISSION_CHANGED')
        receipt = await self.lock_selection(session, render.project_id, selection, value['actor_ref'])
        package = await session.get(ProductionPackageORM, render.package_id, populate_existing=True)
        if package is None or await self.capture(session, package, receipt, selection, value['actor_ref']) != value:
            raise SqlVariantError('SQL_VARIANT_NARRATION_ADMISSION_CHANGED')
        if (render.timeline_version_id, render.subtitle_version_id, render.audio_version_id) != (
                package.timeline_version_id, package.current_subtitle_version_id, package.current_audio_version_id):
            raise SqlVariantError('SQL_VARIANT_NARRATION_CHANGED')
