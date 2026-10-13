"""Typed opt-in review loader and transaction-bound S5 completion fence."""
import asyncio
import copy
from pathlib import Path
from pydantic import Field
from sqlalchemy import update
from .sql_variant_models import Contract,digest
from .sql_variant_narration_models import VariantNarrationRenderProof,NarrationReuseRequest
from .sql_variant_narration_repository import rejected
from .sql_variant_narration_projection import narration_projection
from .sql_tts_artifact_reuse import canonical_audio_binding,asset_proof,pcm,prepared_pcm,validate_evidence,MAX_BYTES,prepared_audio_byte_limit
from .production_db import ProductionPackageORM,ProductionRenderJobORM
from .db import AssetORM
from .sql_variant_db import SqlVariantArtifactReceiptORM
from .frozen_storage_read import frozen_asset_read,completed_read
from .verified_artifact_delivery import RecordedArtifactRead,verified_output_handle,unchanged_descriptor


class VariantNarrationRenderRequest(Contract):
    enabled: bool = False
    receipt_id: str = Field(min_length=1,max_length=64)
    family_id: str = Field(min_length=1,max_length=64)
    member_id: str = Field(min_length=1,max_length=64)
    master_project_id: str = Field(min_length=1,max_length=64)
    input_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    result_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class VariantNarrationTerminalFence:
    def __init__(self,repository,copier):
        self.repository,self.copier=repository,copier

    async def lock(self,session,render,value):
        proof=VariantNarrationRenderProof.model_validate(value)
        if (proof.workspace_id,proof.child_project_id)!=(render.workspace_id,render.project_id):rejected()
        # Existing family writers use master→family; content writers use project
        # before package. Hold these locks through the authoritative render write.
        await self.repository._family(session,proof.workspace_id,proof.master_project_id,proof.family_id,lock=True)
        await self.repository.families._project(session,proof.workspace_id,proof.child_project_id,lock=True)
        receipt=await session.get(SqlVariantArtifactReceiptORM,proof.receipt_id,with_for_update=True,populate_existing=True)
        self.repository.validate(receipt)
        if (receipt.family_id,receipt.member_id,receipt.workspace_id,receipt.input_sha256,receipt.result_sha256)!=(
                proof.family_id,proof.member_id,proof.workspace_id,proof.input_sha256,proof.result_sha256):rejected()
        for pid in sorted({receipt.input_json['source_package']['package_id'],render.package_id}):
            await session.execute(update(ProductionPackageORM).where(ProductionPackageORM.package_id==pid)
                .values(updated_at=ProductionPackageORM.updated_at))
            await session.get(ProductionPackageORM,pid,with_for_update=True,populate_existing=True)
        await session.get(ProductionRenderJobORM,receipt.input_json['source_render']['render_id'],with_for_update=True,populate_existing=True)
        return proof

    async def guard(self,session,render,proof,*,terminal=False):
        receipt=await session.get(SqlVariantArtifactReceiptORM,proof.receipt_id,populate_existing=True)
        self.repository.validate(receipt)
        await self.repository.validate_result(session,receipt)
        payload=NarrationReuseRequest.model_validate({**receipt.input_json['request'],'request_key':'internal-s5-terminal-key'})
        current=await self.repository._capture(session,proof.workspace_id,proof.master_project_id,proof.family_id,payload,actor_ref=receipt.actor_ref)
        if current!=receipt.input_json:rejected()
        expected='awaiting_review' if render.render_kind=='review' else 'ready'
        if render.cancellation_requested or render.status!=(expected if terminal else 'running') or render.invalidated_at is not None:rejected()
        from .production_repository import ProductionRepository
        repository=ProductionRepository(self.repository.session_factory)
        context=await session.get(ProductionPackageORM,render.package_id,populate_existing=True)
        from .timeline_db import TimelineVersionORM
        from .production_db import SubtitleVersionORM,AudioMixVersionORM
        timeline=await session.get(TimelineVersionORM,render.timeline_version_id,populate_existing=True)
        subtitle=await session.get(SubtitleVersionORM,render.subtitle_version_id,populate_existing=True)
        audio=await session.get(AudioMixVersionORM,render.audio_version_id,populate_existing=True)
        from .production_models import MixConfig,SubtitleCue,SubtitleStyle
        from types import SimpleNamespace
        if timeline is None or subtitle is None or audio is None or context is None:rejected()
        config=MixConfig.model_validate(audio.config_json)
        subtitles=SimpleNamespace(cues=[SubtitleCue.model_validate(c) for c in subtitle.cues_json],style=SubtitleStyle.model_validate(subtitle.style_json))
        binding=canonical_audio_binding(render,timeline.snapshot_json,subtitles,config)
        if digest(binding)!=proof.canonical_audio_binding_sha256:rejected()
        if (render.timeline_version_id,render.timeline_version)!=(payload.expected_child_timeline_version_id,payload.expected_child_timeline_version):rejected()
        if narration_projection(timeline.snapshot_json,subtitles.cues,config.voice)!=receipt.input_json['projection']:rejected()
        # Existing final/source rules require a running DTO. For the final
        # pre-commit read the row's terminal state is validated above, while
        # canonical/package/own-approval checks use a detached status view.
        from types import SimpleNamespace
        check_render=SimpleNamespace(**{c.key:getattr(render,c.key) for c in render.__table__.columns})
        check_render.status='running'
        await repository._assert_audio_reuse_current_locked(session,check_render,context,binding)
        held=await self.copier.hold(receipt.result_json['copies'],receipt.input_json)
        try:
            # Observe SQL after bytes, then descriptor stamps without another
            # await. This protects the last writer guard as well as the loader.
            current=await self.repository._capture(session,proof.workspace_id,proof.master_project_id,proof.family_id,payload,actor_ref=receipt.actor_ref)
            if current!=receipt.input_json:rejected()
            await repository._assert_audio_reuse_current_locked(session,check_render,context,binding)
            held.guard()
        finally:held.close()


class VariantNarrationReviewLoader:
    def __init__(self,repository,copier,assets,*,enabled=False):
        if type(enabled) is not bool:raise ValueError('S5_ENABLED_BOOL_REQUIRED')
        self.repository,self.copier,self.assets,self.enabled=repository,copier,assets,enabled

    async def prepare(self,render,snapshot,subtitles,config,workdir,value):
        request=VariantNarrationRenderRequest.model_validate(value)
        if not self.enabled or request.enabled is not True:rejected('SQL_VARIANT_NARRATION_NOT_CONFIGURED')
        if render.render_kind!='review':rejected('SQL_VARIANT_NARRATION_FRESH_REVIEW_REQUIRED')
        receipt=await self.repository.get(render.workspace_id,request.master_project_id,request.family_id,request.receipt_id,require_current=True)
        if receipt.state!='ready' or (receipt.member_id,receipt.child_project_id,receipt.input_sha256,receipt.result_sha256)!=(
                request.member_id,render.project_id,request.input_sha256,request.result_sha256):rejected()
        original=await self.repository.input(render.workspace_id,request.master_project_id,request.family_id,request.receipt_id)
        if original['child_content']['snapshot']['content'].get('approved') is not True:rejected('SQL_VARIANT_NARRATION_CHILD_SCRIPT_REVIEW_REQUIRED')
        if narration_projection(snapshot,subtitles.cues,config.voice)!=original['projection']:rejected()
        binding=canonical_audio_binding(render,snapshot,subtitles,config)
        proof=VariantNarrationRenderProof(receipt_id=request.receipt_id,family_id=request.family_id,member_id=request.member_id,
            workspace_id=render.workspace_id,master_project_id=request.master_project_id,child_project_id=render.project_id,
            input_sha256=receipt.input_sha256,result_sha256=receipt.result_sha256,canonical_audio_binding_sha256=digest(binding))
        narration=copy.deepcopy(original['original_narration'])
        old_cues=[c['cue_id'] for c in original['source_subtitle']['cues_json']]
        mapping=dict(zip(old_cues,[c.cue_id for c in subtitles.cues],strict=True))
        copied=receipt.result['copies'];handles=[]
        async def current():
            now=await self.repository.get(render.workspace_id,request.master_project_id,request.family_id,request.receipt_id,require_current=True)
            if now!=receipt:rejected()
        try:
            for old,source in original['source_assets'].items():
                asset=await self.assets.get_asset(copied[old]['asset_id'])
                if asset is None or asset_proof(asset)!=copied[old]['asset_proof']:rejected()
                name='narration.wav' if source['kind']=='narration-track' else next(
                    u['provider_audio_file'] for u in narration['timing'] if u['provider_audio_asset_id']==old)
                path=Path(workdir)/name
                if path.exists() or path.is_symlink():rejected('SQL_VARIANT_NARRATION_OUTPUT_CONFLICT')
                maximum=prepared_audio_byte_limit(original['projection']['duration_seconds']) if name=='narration.wav' else MAX_BYTES
                read=frozen_asset_read(asset,workspace_id=render.workspace_id,project_id=render.project_id,
                    storage=self.copier.storage,maximum=maximum)
                await read.download(self.copier.storage,path)
                await completed_read(asyncio.to_thread(self.copier.verify_pcm,path,source,original))
                file_proof=RecordedArtifactRead(asset.object_key,asset.workspace_id,asset.project_id,asset.size_bytes,asset.checksum_sha256,asset.storage_provider)
                handle,info=await completed_read(asyncio.to_thread(verified_output_handle,path,file_proof),
                    dispose_cancelled_result=lambda result:result[0].close())
                handles.append((handle,info))
            await current()
            for handle,info in handles:unchanged_descriptor(handle,info)
        finally:
            for handle,_ in handles:handle.close()
        for unit in narration['timing']:
            unit['cue_ids']=[mapping[c] for c in unit.get('cue_ids',[])]
            unit['provider_audio_asset_id']=copied[unit['provider_audio_asset_id']]['asset_id']
            unit['provider_audio_asset_proof']=copied[next(old for old,c in copied.items() if c['asset_id']==unit['provider_audio_asset_id'])]['asset_proof']
            unit['prepared_audio_reused']=True
            unit.pop('raw_audio_reuse',None)
            unit.pop('raw_audio_cache_origin',None)
            # Historical provider evidence/request/cost remains byte-for-byte JSON.
        for cue in narration.get('caption_schedule',[]):cue['cue_id']=mapping[cue['cue_id']]
        narration.pop('original_audio',None)  # Parent premix is not this capability.
        narration['variant_narration_reuse']=proof.model_dump(mode='json')
        return narration
