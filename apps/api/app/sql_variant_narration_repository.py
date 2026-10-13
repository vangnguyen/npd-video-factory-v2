"""Independent S5 receipt states in the existing additive family receipt table."""
import copy
from datetime import timedelta
import hashlib
import uuid
from sqlalchemy import select, update
from .db import AssetORM, ProjectVersionORM, VideoProjectORM, utc_now
from .timeline_db import TimelineORM, TimelineVersionORM
from .production_db import ProductionPackageORM, ProductionRenderJobORM, ProductionApprovalORM, SubtitleVersionORM, AudioMixVersionORM
from .production_repository import ProductionRepository
from .production_models import SubtitleCue, MixConfig
from .sql_variant_db import SqlVariantFamilyORM, SqlVariantMemberORM, SqlVariantArtifactReceiptORM
from .sql_variant_repository import SqlVariantError, record_value, identity, request_parts, as_utc
from .sql_variant_models import digest
from .sql_variant_derivation_repository import validate_completed
from .sql_tts_artifact_reuse import asset_proof
from .sql_variant_narration_models import NarrationReuseRequest, NarrationReuseRead
from .sql_variant_narration_projection import narration_projection, child_cues, source_units, source_asset_limit

KIND='approved_narration_reuse'


def rejected(code='SQL_VARIANT_NARRATION_CHANGED'):
    raise SqlVariantError(code)


def target_key(workspace,child,receipt,asset):
    return f'workspaces/{workspace}/projects/{child}/variant-narration/{receipt}/{asset}.wav'


class SqlVariantNarrationRepository:
    def __init__(self,families,*,lease_seconds=720):
        if type(lease_seconds) is not int or not 30<=lease_seconds<=3600:raise ValueError('S5_LEASE_INVALID')
        self.families,self.session_factory,self.lease_seconds=families,families.session_factory,lease_seconds

    async def _family(self,session,workspace,master,family_id,*,lock):
        await self.families._project(session,workspace,master,lock=lock)
        query=select(SqlVariantFamilyORM).where(SqlVariantFamilyORM.family_id==family_id,
            SqlVariantFamilyORM.workspace_id==workspace,SqlVariantFamilyORM.master_project_id==master)
        if lock:query=query.with_for_update()
        family=await session.scalar(query.execution_options(populate_existing=True))
        if family is None:raise KeyError('SQL_VARIANT_FAMILY_NOT_FOUND')
        read=await self.families._read(session,family)
        if family.state in {'cancelled','failed','recovery_required'} or not read.source_current:
            rejected('SQL_VARIANT_NARRATION_MASTER_NOT_CURRENT')
        return family,read

    async def _capture(self,session,workspace,master,family_id,payload,*,lock=True,check_version=True,actor_ref):
        family,read=await self._family(session,workspace,master,family_id,lock=lock)
        if check_version and (family.version!=payload.expected_version or family.snapshot_sha256!=payload.expected_snapshot_sha256):
            rejected('SQL_VARIANT_VERSION_CHANGED')
        member=await session.get(SqlVariantMemberORM,payload.member_id,populate_existing=True)
        if member is None or (member.family_id,member.workspace_id,member.child_project_id)!=(family_id,workspace,payload.child_project_id):
            rejected('SQL_VARIANT_NARRATION_CHILD_LINEAGE_REQUIRED')
        derivation=await session.scalar(select(SqlVariantArtifactReceiptORM).where(
            SqlVariantArtifactReceiptORM.family_id==family_id,SqlVariantArtifactReceiptORM.member_id==member.member_id,
            SqlVariantArtifactReceiptORM.kind.in_(['storyboard_derivation','uploaded_evidence_derivation']),
            SqlVariantArtifactReceiptORM.state=='ready'))
        if derivation is None or derivation.result_json.get('child_project_id')!=member.child_project_id:
            rejected('SQL_VARIANT_NARRATION_CHILD_LINEAGE_REQUIRED')
        await validate_completed(session,derivation)
        child=await self.families._project(session,workspace,member.child_project_id,lock=lock)
        current=await session.scalar(select(TimelineORM).where(TimelineORM.project_id==child.project_id,
            TimelineORM.workspace_id==workspace).execution_options(populate_existing=True))
        content=await session.get(ProjectVersionORM,payload.expected_child_content_version_id,populate_existing=True)
        timeline=await session.get(TimelineVersionORM,payload.expected_child_timeline_version_id,populate_existing=True)
        latest=await session.scalar(select(ProjectVersionORM).where(ProjectVersionORM.project_id==child.project_id,
            ProjectVersionORM.workspace_id==workspace,ProjectVersionORM.label=='mvp1-content').order_by(ProjectVersionORM.ordinal.desc()).limit(1))
        if (content is None or timeline is None or current is None or latest is None
                or (content.workspace_id,content.project_id,child.current_version_id,latest.project_version_id)
                !=(workspace,child.project_id,content.project_version_id,content.project_version_id)
                or (timeline.project_id,timeline.timeline_id,timeline.version)!=(child.project_id,current.timeline_id,payload.expected_child_timeline_version)
                or current.current_version_id!=timeline.timeline_version_id or current.current_version!=timeline.version
                or current.source_content_version_id!=content.project_version_id):
            rejected('SQL_VARIANT_NARRATION_CHILD_NOT_CURRENT')
        source=await session.get(ProductionRenderJobORM,payload.source_review_render_id,populate_existing=True)
        approval=await session.get(ProductionApprovalORM,payload.source_approval_id,populate_existing=True)
        package=await session.get(ProductionPackageORM,source.package_id,populate_existing=True) if source else None
        if (source is None or approval is None or package is None or source.render_kind!='review'
                or source.status!='awaiting_review' or source.qc_status!='passed' or source.cancellation_requested
                or source.invalidated_at is not None or (source.workspace_id,source.project_id)!=(workspace,master)
                or approval.preview_render_id!=source.render_id or approval.project_id!=master):
            rejected('SQL_VARIANT_NARRATION_APPROVED_SOURCE_REQUIRED')
        ProductionRepository._assert_approval_current(package,approval)
        # Master binding already includes the current approval and review rows.
        for obj in (source,approval,package):
            proof=next((p for p in read.snapshot.binding.records if p.table==obj.__tablename__
                and p.owner_ref in {getattr(obj,'render_id',None),getattr(obj,'approval_id',None),getattr(obj,'package_id',None)}),None)
            if proof is None or proof.count!=1 or proof.sha256!=digest([record_value(obj)]):rejected()
        manifest=copy.deepcopy(source.manifest_json)
        if digest(manifest)!=payload.expected_source_manifest_sha256:rejected()
        subtitle=await session.get(SubtitleVersionORM,source.subtitle_version_id,populate_existing=True)
        audio=await session.get(AudioMixVersionORM,source.audio_version_id,populate_existing=True)
        original_timeline=await session.get(TimelineVersionORM,source.timeline_version_id,populate_existing=True)
        if subtitle is None or audio is None or original_timeline is None:rejected()
        config=MixConfig.model_validate(audio.config_json)
        if config.voice.model_dump(mode='json')!=payload.voice_config.model_dump(mode='json'):rejected()
        original=narration_projection(original_timeline.snapshot_json,[SubtitleCue.model_validate(c) for c in subtitle.cues_json],config.voice)
        target=narration_projection(timeline.snapshot_json,child_cues(timeline.snapshot_json),payload.voice_config)
        if original!=target or digest(target)!=payload.expected_semantic_sha256:rejected('SQL_VARIANT_NARRATION_SEMANTICS_CHANGED')
        narration,units=source_units(manifest,original,payload.expected_profile_sha256s,payload.expected_normalization_sha256s)
        source_ids={manifest.get('supporting_asset_ids',{}).get('narration-track'):'narration-track'}
        source_ids.update({u['provider_audio_asset_id']:'tts-provider-source' for u in units})
        if None in source_ids:rejected('SQL_VARIANT_NARRATION_SOURCE_REQUIRED')
        sources={}
        for asset_id,kind in sorted(source_ids.items()):
            asset=await session.get(AssetORM,asset_id,populate_existing=True)
            proof=next((p for p in read.snapshot.binding.assets if p.asset_id==asset_id),None)
            if (asset is None or proof is None or digest(record_value(asset))!=proof.record_sha256
                    or (asset.workspace_id,asset.project_id,asset.asset_class,asset.kind,asset.content_type,asset.storage_provider)
                    !=(workspace,master,'render',kind,'audio/wav','local')
                    or not 0<asset.size_bytes<=source_asset_limit(kind,original['duration_seconds'])):
                rejected('SQL_VARIANT_NARRATION_ASSET_CHANGED')
            expected=manifest.get('supporting_audio_proofs',{}).get(kind) if kind=='narration-track' else next(
                u['provider_audio_asset_proof'] for u in units if u['provider_audio_asset_id']==asset_id)
            if asset_proof(asset)!=expected:rejected('SQL_VARIANT_NARRATION_ASSET_CHANGED')
            sources[asset_id]=record_value(asset)
        body,_,_=request_parts(payload)
        return {'schema_version':'sql-variant-narration-input.v1','workspace_id':workspace,'master_project_id':master,
            'family_id':family_id,'member_id':member.member_id,'child_project_id':child.project_id,
            'family_snapshot_sha256':family.snapshot_sha256,'family_version':family.version,
            'derivation_receipt':record_value(derivation),'child_project':record_value(child),
            'child_content':record_value(content),'child_timeline':record_value(timeline),'request':body,
            'source_package':record_value(package),'source_render':record_value(source),'source_approval':record_value(approval),
            'source_subtitle':record_value(subtitle),'source_audio':record_value(audio),'source_timeline':record_value(original_timeline),
            'projection':target,'original_narration':narration,'source_assets':sources,'actor_ref':actor_ref}

    @staticmethod
    def read(row):
        return NarrationReuseRead(receipt_id=row.receipt_id,family_id=row.family_id,member_id=row.member_id,
            workspace_id=row.workspace_id,child_project_id=row.input_json['child_project_id'],state=row.state,
            input_sha256=row.input_sha256,result_sha256=row.result_sha256,result=copy.deepcopy(row.result_json),
            error_code=row.error_code,actor_ref=row.actor_ref)

    @staticmethod
    def validate(row):
        if row is None or row.kind!=KIND or digest(row.input_json)!=row.input_sha256 \
                or digest(row.input_json['request'])!=row.request_sha256 \
                or row.receipt_id!=identity('vfr_',row.member_id+'/narration/'+row.input_sha256) \
                or (row.workspace_id,row.family_id,row.member_id,row.actor_ref)!=(row.input_json['workspace_id'],
                    row.input_json['family_id'],row.input_json['member_id'],row.input_json['actor_ref']):rejected()
        if row.state=='ready' and (row.result_json is None or digest(row.result_json)!=row.result_sha256):rejected()
        if row.state not in {'pending','ready','unknown','cancelled'}:rejected()

    @staticmethod
    def active(row,claim):
        SqlVariantNarrationRepository.validate(row)
        if row.state!='pending' or row.claim_id!=claim:rejected('SQL_VARIANT_NARRATION_CLAIM_CHANGED')
        if row.lease_until is None or as_utc(row.lease_until)<=utc_now():rejected('SQL_VARIANT_NARRATION_LEASE_EXPIRED')

    async def claim(self,workspace,master,family,payload,*,actor_ref):
        self.families.actor(actor_ref)
        payload=NarrationReuseRequest.model_validate(payload.model_dump())
        if payload.enabled is not True:rejected('SQL_VARIANT_NARRATION_DISABLED')
        body,request_sha,key_sha=request_parts(payload)
        async with self.session_factory() as session,session.begin():
            await self._family(session,workspace,master,family,lock=True)
            prior=await session.scalar(select(SqlVariantArtifactReceiptORM).where(
                SqlVariantArtifactReceiptORM.family_id==family,SqlVariantArtifactReceiptORM.request_key_sha256==key_sha).with_for_update())
            if prior is not None:
                self.validate(prior)
                if prior.request_sha256!=request_sha or prior.actor_ref!=actor_ref:rejected('SQL_VARIANT_IDEMPOTENCY_CONFLICT')
                if prior.state=='pending' and (prior.lease_until is None or as_utc(prior.lease_until)<=utc_now()):
                    prior.state='unknown';prior.claim_id=None;prior.lease_until=None;prior.error_code='SQL_VARIANT_NARRATION_LEASE_EXPIRED'
                return self.read(prior),None,True
            value=await self._capture(session,workspace,master,family,payload,actor_ref=actor_ref)
            input_sha=digest(value);rid=identity('vfr_',payload.member_id+'/narration/'+input_sha)
            if await session.get(SqlVariantArtifactReceiptORM,rid) is not None:rejected('SQL_VARIANT_IDEMPOTENCY_CONFLICT')
            claim=uuid.uuid4().hex
            row=SqlVariantArtifactReceiptORM(receipt_id=rid,family_id=family,member_id=payload.member_id,workspace_id=workspace,
                kind=KIND,state='pending',request_key_sha256=key_sha,request_sha256=request_sha,input_json=value,
                input_sha256=input_sha,claim_id=claim,lease_until=utc_now()+timedelta(seconds=self.lease_seconds),actor_ref=actor_ref)
            session.add(row);await session.flush()
            return self.read(row),{'claim_id':claim,'input':copy.deepcopy(value)},False

    async def guard(self,workspace,master,family,rid,claim):
        async with self.session_factory() as session,session.begin():
            row=await session.get(SqlVariantArtifactReceiptORM,rid)
            self.active(row,claim)
            payload=NarrationReuseRequest.model_validate({**row.input_json['request'],'request_key':'internal-s5-guard-key'})
            value=await self._capture(session,workspace,master,family,payload,actor_ref=row.actor_ref)
            if value!=row.input_json:rejected()
            self.active(row,claim)

    async def unknown(self,workspace,family,rid,claim,code):
        async with self.session_factory() as session,session.begin():
            await session.execute(update(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.receipt_id==rid,
                SqlVariantArtifactReceiptORM.family_id==family,SqlVariantArtifactReceiptORM.workspace_id==workspace,
                SqlVariantArtifactReceiptORM.kind==KIND,SqlVariantArtifactReceiptORM.state=='pending',
                SqlVariantArtifactReceiptORM.claim_id==claim).values(state='unknown',claim_id=None,lease_until=None,
                error_code=code,updated_at=utc_now()))

    async def get(self,workspace,master,family,rid,*,require_current=False):
        async with self.session_factory() as session:
            row=await session.get(SqlVariantArtifactReceiptORM,rid)
            self.validate(row)
            if (row.workspace_id,row.family_id)!=(workspace,family):raise KeyError('SQL_VARIANT_NARRATION_NOT_FOUND')
            if row.input_json['master_project_id']!=master:raise KeyError('SQL_VARIANT_NARRATION_NOT_FOUND')
            if require_current:
                payload=NarrationReuseRequest.model_validate({**row.input_json['request'],'request_key':'internal-s5-read-key'})
                value=await self._capture(session,workspace,master,family,payload,lock=False,actor_ref=row.actor_ref)
                if value!=row.input_json:rejected()
                await self.validate_result(session,row)
            return self.read(row)

    async def input(self,workspace,master,family,rid):
        async with self.session_factory() as session:
            row=await session.get(SqlVariantArtifactReceiptORM,rid)
            self.validate(row)
            if (row.workspace_id,row.family_id,row.input_json['master_project_id'])!=(workspace,family,master):
                raise KeyError('SQL_VARIANT_NARRATION_NOT_FOUND')
            return copy.deepcopy(row.input_json)

    @staticmethod
    async def validate_result(session,row):
        if row.state!='ready':rejected('SQL_VARIANT_NARRATION_READY_REQUIRED')
        result=row.result_json
        if result.get('schema_version')!='sql-variant-narration-result.v1' or result.get('input_sha256')!=row.input_sha256 \
                or set(result['copies'])!=set(row.input_json['source_assets']):rejected()
        required={'schema_version','input_sha256','copies','source_review_render_id','source_approval_id',
            'source_manifest_sha256','human_review_required','approval_transferred','rights_authority_transferred',
            'new_inferences','provider_calls','operating_cost_vnd','publishing_enabled'}
        request=row.input_json['request']
        if (set(result)!=required or result['source_review_render_id']!=request['source_review_render_id']
                or result['source_approval_id']!=request['source_approval_id']
                or result['source_manifest_sha256']!=request['expected_source_manifest_sha256']
                or result['human_review_required'] is not True or result['approval_transferred'] is not False
                or result['rights_authority_transferred'] is not False or result['publishing_enabled'] is not False
                or type(result['new_inferences']) is not int or result['new_inferences']!=0
                or type(result['provider_calls']) is not int or result['provider_calls']!=0
                or result['operating_cost_vnd'] is not None):rejected()
        for old,copy_proof in result['copies'].items():
            source=row.input_json['source_assets'][old]
            if (copy_proof['object_key'],copy_proof['sha256'],copy_proof['size_bytes'],copy_proof['content_type'],copy_proof['storage_provider'])!=(
                    target_key(row.workspace_id,row.input_json['child_project_id'],row.receipt_id,old),
                    source['checksum_sha256'],source['size_bytes'],'audio/wav','local'):rejected()
            asset=await session.get(AssetORM,copy_proof['asset_id'],populate_existing=True)
            if (asset is None or asset_proof(asset)!=copy_proof['asset_proof'] or asset.project_id!=row.input_json['child_project_id']
                    or asset.workspace_id!=row.workspace_id or asset.asset_class!='generated'
                    or asset.kind!=('variant-narration-source' if source['kind']=='narration-track' else 'variant-tts-source')
                    or asset.provenance.get('narration_receipt_id')!=row.receipt_id
                    or asset.provenance.get('parent_record_sha256')!=digest(source)
                    or asset.provenance.get('rights_status')!='unknown' or asset.provenance.get('human_accepted') is not False):rejected()

    async def complete(self,workspace,master,family,rid,claim,copies,*,verify):
        async with self.session_factory() as session,session.begin():
            await self._family(session,workspace,master,family,lock=True)
            row=await session.get(SqlVariantArtifactReceiptORM,rid,with_for_update=True,populate_existing=True)
            self.active(row,claim);lease=row.lease_until
            payload=NarrationReuseRequest.model_validate({**row.input_json['request'],'request_key':'internal-s5-complete-key'})
            current=await self._capture(session,workspace,master,family,payload,actor_ref=row.actor_ref)
            if current!=row.input_json:rejected()
            held=await verify(copies,row.input_json)
            try:
                self.active(row,claim)
                if set(copies)!=set(current['source_assets']):rejected('SQL_VARIANT_NARRATION_COPY_CHANGED')
                result_copies={}
                for old,source in current['source_assets'].items():
                    copied=copies[old]
                    key=target_key(workspace,current['child_project_id'],rid,old)
                    if (copied['object_key'],copied['sha256'],copied['size_bytes'],copied['content_type'],copied['storage_provider'])!=(
                            key,source['checksum_sha256'],source['size_bytes'],'audio/wav','local'):rejected()
                    asset=AssetORM(asset_id=identity('ast_',rid+'/'+old),workspace_id=workspace,project_id=current['child_project_id'],
                        project_version_id=payload.expected_child_content_version_id,asset_class='generated',
                        kind='variant-narration-source' if source['kind']=='narration-track' else 'variant-tts-source',
                        filename=old+'.wav',object_key=key,content_type='audio/wav',size_bytes=source['size_bytes'],
                        checksum_sha256=source['checksum_sha256'],storage_provider='local',
                        provenance={'schema_version':'sql-variant-narration-custody.v1','narration_receipt_id':rid,
                            'parent_project_id':master,'parent_asset_id':old,'parent_record_sha256':digest(source),
                            'source_bytes_verified':True,'source_type':'variant_narration_copy','rights_status':'unknown',
                            'human_accepted':False,'production_eligible':False,'approval_transferred':False})
                    session.add(asset);await session.flush()
                    result_copies[old]={**copied,'asset_id':asset.asset_id,'asset_proof':asset_proof(asset)}
                result={'schema_version':'sql-variant-narration-result.v1','input_sha256':row.input_sha256,
                    'copies':result_copies,'source_review_render_id':payload.source_review_render_id,
                    'source_approval_id':payload.source_approval_id,'source_manifest_sha256':payload.expected_source_manifest_sha256,
                    'human_review_required':True,'approval_transferred':False,'rights_authority_transferred':False,
                    'new_inferences':0,'provider_calls':0,'operating_cost_vnd':None,'publishing_enabled':False}
                # Last source/target SQL read follows all flush/verification awaits.
                current=await self._capture(session,workspace,master,family,payload,actor_ref=row.actor_ref)
                if current!=row.input_json:rejected()
                self.active(row,claim)
                result_sha=digest(result)
                changed=await session.execute(update(SqlVariantArtifactReceiptORM).where(
                    SqlVariantArtifactReceiptORM.receipt_id==rid,SqlVariantArtifactReceiptORM.state=='pending',
                    SqlVariantArtifactReceiptORM.claim_id==claim,SqlVariantArtifactReceiptORM.lease_until==lease,
                    SqlVariantArtifactReceiptORM.lease_until>utc_now(),SqlVariantArtifactReceiptORM.input_sha256==row.input_sha256,
                    SqlVariantArtifactReceiptORM.actor_ref==row.actor_ref).values(state='ready',claim_id=None,lease_until=None,
                        result_json=result,result_sha256=result_sha,updated_at=utc_now()).execution_options(synchronize_session=False))
                if changed.rowcount!=1:rejected('SQL_VARIANT_NARRATION_CLAIM_CHANGED')
                await session.refresh(row);await self.validate_result(session,row)
                if as_utc(lease)<=utc_now() or row.result_sha256!=result_sha or row.state!='ready':rejected('SQL_VARIANT_NARRATION_LEASE_EXPIRED')
                held.guard()
                return self.read(row)
            finally:
                held.close()
