"""Zero-dispatch import of saved video/audio graphs into independently owned drafts.

The S2 claim/lease/closed-byte fences remain the completion authority. Original
provider evidence and original upload scans are historical, never a new call.
"""
import copy
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from sqlalchemy import select, DateTime
from sqlalchemy.exc import IntegrityError
from .auto_edit_db import (AutoEditAnalysisORM, TranscriptORM, TranscriptSegmentORM,
    TranscriptWordORM, SceneORM, SilenceDecisionORM, HighlightORM, UploadSessionORM)
from .uploaded_audio_db import UploadedAudioORM, UploadedAudioVersionORM
from .auto_edit_job_db import AutoEditJobORM
from .db import AssetORM, JobORM, JobEventORM, ProjectVersionORM, VideoProjectORM, utc_now
from .timeline_db import TimelineORM, TimelineVersionORM
from .sql_variant_db import SqlVariantArtifactReceiptORM, SqlVariantMemberORM
from .sql_variant_models import FamilySnapshot, VariantProgressSafety, canonical, digest
from .sql_variant_repository import SqlVariantError, identity, record_value, request_parts
from .sql_variant_uploaded_models import DeriveUploadedRequest,UploadedDerivationRead,VariantEvidenceImportInput
from .sql_variant_derivation_repository import SqlStoryboardDerivationRepository, target_key as storyboard_target_key
from .object_storage import validate_object_key
from .sql_variant_uploaded_identity import id_map, rows, rebind, rebind_provenance, derive_uploaded, audio_versions

KIND='uploaded_evidence_derivation'
SCHEMA='sql-variant-uploaded-input.v1'
GRAPH_MODELS={m.__tablename__:m for m in (AutoEditAnalysisORM,TranscriptORM,TranscriptSegmentORM,
    TranscriptWordORM,SceneORM,SilenceDecisionORM,HighlightORM,UploadedAudioORM,UploadedAudioVersionORM)}

def target_key(workspace,child,member,source_id,mime):
    suffix={'video/mp4':'mp4','video/webm':'webm','audio/flac':'flac'}.get(mime)
    if suffix is None:return storyboard_target_key(workspace,child,member,source_id,mime)
    return validate_object_key(f'workspaces/{workspace}/projects/{child}/variant-imports/{member}/{source_id}.{suffix}')

def is_uploaded(value):return value.get('schema_version')==SCHEMA

def fields(model, value):
    result=copy.deepcopy(value)
    for column in model.__table__.columns:
        if column.name in result and isinstance(column.type, DateTime):
            if isinstance(result[column.name],str):result[column.name]=datetime.fromisoformat(result[column.name])
    return result

def validate_input(receipt,family,members):
    value=receipt.input_json;member=next(m for m in members if m.member_id==receipt.member_id)
    snapshot=FamilySnapshot.model_validate(family.snapshot_json);binding=snapshot.binding
    required={'schema_version','workspace_id','master_project_id','family_id','member_id','planned_project_id',
        'family_snapshot_sha256','profile','request','source_mode','source_content','source_timeline','source_assets','source_graph',
        'source_uploads','source_jobs','source_job_relations','safety'}
    request=DeriveUploadedRequest.model_validate({**value['request'],'request_key':'internal-import-history-key'})
    if (set(value)!=required or not is_uploaded(value) or receipt.kind!=KIND
        or receipt.workspace_id!=family.workspace_id or receipt.family_id!=family.family_id
        or (value['workspace_id'],value['master_project_id'],value['family_id'],value['member_id'],value['planned_project_id'])
        !=(family.workspace_id,family.master_project_id,family.family_id,member.member_id,member.planned_project_id)
        or value['family_snapshot_sha256']!=family.snapshot_sha256 or value['profile']!=member.profile_json
        or value['source_mode']!=binding.source_mode or digest(value['source_timeline'])!=binding.timeline_snapshot_sha256
        or digest(value)!=receipt.input_sha256 or digest(value['request'])!=receipt.request_sha256
        or request.member_id!=member.member_id or request.expected_snapshot_sha256!=family.snapshot_sha256
        or value['safety']!=VariantProgressSafety().model_dump(mode='json')
        or receipt.receipt_id!=identity('vfr_',member.member_id+'/uploaded/'+receipt.input_sha256)):
        raise ValueError('invalid uploaded derivative input')
    if value['source_content'] is not None:
        content=value['source_content'];proof=next(p for p in binding.records if p.table=='project_versions' and p.owner_ref==binding.source_content_version_id)
        if digest([content])!=proof.sha256:raise ValueError('content changed')
    elif binding.source_content_version_id is not None:raise ValueError('content missing')
    expected={(p.table,p.owner_ref) for p in binding.records if p.table in GRAPH_MODELS}
    seen=set()
    for group in value['source_graph']:
        key=(group['table'],group['owner_ref'])
        proof=next(p for p in binding.records if (p.table,p.owner_ref)==key)
        if (key in seen or key not in expected or set(group)!={'table','owner_ref','rows'}
            or len(group['rows'])!=proof.count or digest(group['rows'])!=proof.sha256):raise ValueError('graph changed')
        seen.add(key)
    if seen!=expected:raise ValueError('graph incomplete')
    if not value['source_graph']:raise ValueError('not an uploaded graph')
    expected_jobs={p['job_id'] for p in rows(value,'uploaded_audio_transcriptions')}
    for relation in value['source_job_relations']:
        expected_jobs.add(relation['job_id'])
        if (relation['project_id'],relation['workspace_id'])!=(family.master_project_id,family.workspace_id):raise ValueError('source job scope changed')
    if set(value['source_jobs'])!=expected_jobs:raise ValueError('source jobs changed')
    for job in value['source_jobs'].values():
        if (job['project_id'],job['workspace_id'],job['status'])!=(family.master_project_id,family.workspace_id,'awaiting_review'):
            raise ValueError('source job not stable')
    for parent in rows(value,'uploaded_audio_transcriptions'):
        job=value['source_jobs'][parent['job_id']]
        if (job['request_json'].get('kind'),job['request_json'].get('audio_id'),job['request_json'].get('source_sha256'),
            job['request_json'].get('provider_binding_sha256'))!=('uploaded_audio_transcription',parent['audio_id'],parent['source_sha256'],
                digest(parent['configuration_json']['provider'])):raise ValueError('audio job lineage changed')
        if parent['claim_id'] is not None or parent['lease_expires_at'] is not None:raise ValueError('audio source still claimed')
    from .auto_edit_job_repository import check
    for relation in value['source_job_relations']:
        check(SimpleNamespace(**relation),SimpleNamespace(**value['source_jobs'][relation['job_id']]))
        if relation['claim_id'] is not None or relation['lease_expires_at'] is not None:raise ValueError('video source still claimed')
    uploads=value['source_uploads']
    for old,asset in value['source_assets'].items():
        proof=next(p for p in binding.assets if p.asset_id==old)
        if digest(asset)!=proof.record_sha256 or asset['storage_provider']!='local':raise ValueError('asset changed')
        if asset['asset_class']=='source' and asset['kind'] in {'video','audio'}:
            upload=uploads[old];p=next(p for p in binding.records if p.table=='upload_sessions' and p.owner_ref==upload['upload_id'])
            if (asset['provenance'].get('source_type')!='user_upload' or asset['provenance'].get('source_reference')!=upload['upload_id']
                or digest([upload])!=p.sha256 or upload['asset_id']!=old or upload['project_id']!=family.master_project_id
                or upload['workspace_id']!=family.workspace_id or upload['quarantine_state']!='trusted'
                or upload['trusted_at'] is None or upload['status'] not in {'completed','completed_duplicate'}
                or upload['scan_checksum_sha256']!=asset['checksum_sha256']
                or upload['media_metadata_json']!=asset['provenance'].get('media_metadata')):raise ValueError('upload changed')
    id_map(value)

def make_result(value,copies):
    if set(copies)!=set(value['source_assets']):raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
    for old,item in copies.items():
        source=value['source_assets'][old]
        if (set(item)!={'object_key','sha256','size_bytes','content_type','storage_provider','dimensions'}
            or (item['object_key'],item['sha256'],item['size_bytes'],item['content_type'],item['storage_provider']) != (
                target_key(value['workspace_id'],value['planned_project_id'],value['member_id'],old,source['content_type']),
                source['checksum_sha256'],source['size_bytes'],source['content_type'],'local')):raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
        dims=item['dimensions']
        if source['content_type'].startswith('image/'):
            if (not isinstance(dims,list) or len(dims)!=2 or any(type(n)is not int or not 1<=n<=32768 for n in dims)
                or dims[0]*dims[1]>40_000_000):raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
        elif dims is not None:raise SqlVariantError('SQL_VARIANT_COPY_RESULT_CHANGED')
    ids,content,timeline=derive_uploaded(value,copies)
    return {'schema_version':'sql-variant-uploaded-result.v1','child_project_id':value['planned_project_id'],
        'content_version_id':ids['content_version_id'],'content_sha256':digest(content),
        'timeline_id':ids['timeline_id'],'timeline_version_id':ids['timeline_version_id'],'timeline_sha256':digest(timeline),
        'asset_map':ids['assets'],'identity_map':ids['graph'],'copies':copy.deepcopy(copies),
        'original_graph_sha256':digest(value['source_graph']),'original_uploads_sha256':digest(value['source_uploads']),
        'original_jobs_sha256':digest(value['source_jobs']),'original_job_relations_sha256':digest(value['source_job_relations']),
        'safety':VariantProgressSafety(child_projects_created=1,source_bytes_verified=True).model_dump(mode='json'),
        'human_review_required':True,'rights_review_required':True,'reframe_attention_required':True,
        'raw_evidence_rewritten':False,'new_provider_billed_cost_vnd':0,'operating_cost_vnd':None}

async def capture_graph(session,binding):
    graph=[]
    for proof in binding.records:
        model=GRAPH_MODELS.get(proof.table)
        if model is None:continue
        owner=proof.owner_ref
        if model is AutoEditAnalysisORM:condition=model.analysis_id==owner
        elif model is TranscriptORM:condition=model.analysis_id==owner
        elif model in (TranscriptSegmentORM,TranscriptWordORM):
            condition=model.transcript_id.in_(select(TranscriptORM.transcript_id).where(TranscriptORM.analysis_id==owner))
        elif model in (SceneORM,SilenceDecisionORM,HighlightORM):condition=model.analysis_id==owner
        elif model is UploadedAudioORM:condition=model.audio_id==owner
        else:condition=model.audio_id==owner
        found=(await session.scalars(select(model).where(condition).order_by(*model.__table__.primary_key.columns)
            .execution_options(populate_existing=True))).all()
        # Transcript proofs use version order; version identities are not ordered UUIDs.
        if model is TranscriptORM:found.sort(key=lambda r:r.version)
        records=[record_value(r) for r in found]
        if len(records)!=proof.count or digest(records)!=proof.sha256:raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
        graph.append({'table':proof.table,'owner_ref':owner,'rows':records})
    return graph

class SqlUploadedDerivationRepository(SqlStoryboardDerivationRepository):
    kind=KIND
    target_key=staticmethod(target_key)
    async def _load(self,session,workspace,master,family_id):
        row,current=await super()._load(session,workspace,master,family_id)
        # Stable parent jobs are separate from S1's unchanged fingerprint. Lock
        # the original Job rows after Project/Timeline/Family; no wire/copy here.
        pending=(await session.scalars(select(SqlVariantArtifactReceiptORM).where(
            SqlVariantArtifactReceiptORM.family_id==family_id,SqlVariantArtifactReceiptORM.kind==KIND,
            SqlVariantArtifactReceiptORM.state=='pending'))).all()
        for receipt in pending:
            await self._source_jobs_current(session,receipt,lock=True,require_current=False)
        return row,current

    @staticmethod
    async def _source_jobs_current(session,receipt,*,lock=False,require_current=True):
        for job_id,original in sorted(receipt.input_json['source_jobs'].items()):
            job=await session.get(JobORM,job_id,with_for_update=lock,populate_existing=True)
            if require_current and (job is None or record_value(job)!=original):raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
        for original in receipt.input_json['source_job_relations']:
            relation=await session.get(AutoEditJobORM,original['relation_id'],populate_existing=True,with_for_update=lock)
            if require_current and (relation is None or record_value(relation)!=original):raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')

    async def guard(self,workspace,master,family_id,receipt_id,claim_id):
        async with self.session_factory() as session,session.begin():
            row,current=await self._load(session,workspace,master,family_id)
            receipt=await session.get(SqlVariantArtifactReceiptORM,receipt_id);self._active(row,receipt,claim_id)
            if not current.source_current:raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
            await self._source_jobs_current(session,receipt)
            self._active(row,receipt,claim_id)

    async def _completion_fence(self,session,family,receipt,claim_id,expected):
        await super()._completion_fence(session,family,receipt,claim_id,expected)
        await self._source_jobs_current(session,receipt)
        self._assert_pending_fence(family,receipt,claim_id,expected)
    @staticmethod
    def read(row):
        ready=row.state=='ready'
        return UploadedDerivationRead(receipt_id=row.receipt_id,family_id=row.family_id,member_id=row.member_id,
            workspace_id=row.workspace_id,state=row.state,input_sha256=row.input_sha256,request_sha256=row.request_sha256,
            result=copy.deepcopy(row.result_json),result_sha256=row.result_sha256,error_code=row.error_code,actor_ref=row.actor_ref,
            safety=VariantProgressSafety(child_projects_created=int(ready),source_bytes_verified=ready))
    async def claim(self,workspace,master,family_id,payload,*,actor_ref):
        self.families.actor(actor_ref);payload=DeriveUploadedRequest.model_validate(payload.model_dump())
        body,request_sha,key_sha=request_parts(payload)
        async with self.session_factory() as session,session.begin():
            row,family=await self._load(session,workspace,master,family_id)
            prior=await session.scalar(select(SqlVariantArtifactReceiptORM).where(
                SqlVariantArtifactReceiptORM.family_id==family_id,SqlVariantArtifactReceiptORM.request_key_sha256==key_sha))
            if prior:
                if prior.kind!=KIND or prior.request_sha256!=request_sha or prior.actor_ref!=actor_ref:raise SqlVariantError('SQL_VARIANT_IDEMPOTENCY_CONFLICT')
                return self.read(prior),None,True
            if row.version!=payload.expected_version or row.snapshot_sha256!=payload.expected_snapshot_sha256:raise SqlVariantError('SQL_VARIANT_VERSION_CHANGED')
            if row.state not in {'reserved','needs_attention','review_required'}:raise SqlVariantError('SQL_VARIANT_STATE_CHANGED')
            if not family.source_current:raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
            member=await session.get(SqlVariantMemberORM,payload.member_id)
            if member is None or (member.family_id,member.workspace_id,member.state)!=(family_id,workspace,'reserved'):raise SqlVariantError('SQL_VARIANT_MEMBER_CHANGED')
            binding=family.snapshot.binding;version=await session.get(TimelineVersionORM,binding.timeline_version_id)
            graph=await capture_graph(session,binding)
            if not graph:raise SqlVariantError('SQL_VARIANT_S3_SOURCE_UNSUPPORTED')
            from .uploaded_audio_repository import UploadedAudioRepository
            # Source hashes alone cannot attest normalized audio lineage.
            for group in graph:
                if group['table']=='uploaded_audio_transcriptions':
                    for original in group['rows']:
                        parent=await session.get(UploadedAudioORM,original['audio_id'])
                        await UploadedAudioRepository(self.session_factory).versions(session,parent)
            source_jobs={}
            job_ids={r['job_id'] for g in graph if g['table']=='uploaded_audio_transcriptions' for r in g['rows']}
            analysis_ids=[r['analysis_id'] for g in graph if g['table']=='auto_edit_analyses' for r in g['rows']]
            relations=(await session.scalars(select(AutoEditJobORM).where(AutoEditJobORM.analysis_id.in_(analysis_ids))
                .order_by(AutoEditJobORM.relation_id))).all()
            job_ids.update(r.job_id for r in relations)
            for job_id in sorted(job_ids):
                job=await session.get(JobORM,job_id,with_for_update=True)
                if job is None:raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
                source_jobs[job_id]=record_value(job)
            content=await session.get(ProjectVersionORM,binding.source_content_version_id) if binding.source_content_version_id else None
            used={c['asset_id'] for t in version.snapshot_json['tracks'] for c in t['clips'] if c.get('asset_id')}
            used.update(r['asset_id'] for g in graph if g['table'] in {'auto_edit_analyses','uploaded_audio_transcriptions'} for r in g['rows'])
            if content:used.update(s['asset_id'] for s in content.snapshot['content']['scenes'] if s.get('asset_id'))
            sources,uploads={},{}
            for old in sorted(used):
                asset=await session.get(AssetORM,old);proof=next(p for p in binding.assets if p.asset_id==old)
                if digest(record_value(asset))!=proof.record_sha256:raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
                if asset.storage_provider!='local':raise SqlVariantError('SQL_VARIANT_STORAGE_NOT_CONFIGURED')
                target_key(workspace,member.planned_project_id,member.member_id,old,asset.content_type)
                sources[old]=record_value(asset)
                if asset.asset_class=='source' and asset.kind in {'video','audio'}:
                    upload=await session.get(UploadSessionORM,asset.provenance.get('source_reference',''))
                    if upload is None:raise SqlVariantError('SQL_VARIANT_TRUSTED_SOURCE_REQUIRED')
                    uploads[old]=record_value(upload)
            value={'schema_version':SCHEMA,'workspace_id':workspace,'master_project_id':master,'family_id':family_id,
                'member_id':member.member_id,'planned_project_id':member.planned_project_id,'family_snapshot_sha256':family.snapshot_sha256,
                'profile':copy.deepcopy(member.profile_json),'request':body,'source_mode':binding.source_mode,
                'source_content':record_value(content) if content else None,'source_timeline':copy.deepcopy(version.snapshot_json),
                'source_assets':sources,'source_graph':graph,'source_uploads':uploads,'source_jobs':source_jobs,
                'source_job_relations':[record_value(r) for r in relations],'safety':VariantProgressSafety().model_dump(mode='json')}
            if len(canonical(value))>32*1024*1024:raise SqlVariantError('SQL_VARIANT_SOURCE_PROOF_LIMIT')
            claim='vfc_'+uuid.uuid4().hex
            receipt=SqlVariantArtifactReceiptORM(receipt_id=identity('vfr_',member.member_id+'/uploaded/'+digest(value)),
                family_id=family_id,member_id=member.member_id,workspace_id=workspace,kind=KIND,state='pending',
                request_key_sha256=key_sha,request_sha256=request_sha,input_json=value,input_sha256=digest(value),actor_ref=actor_ref,
                claim_id=claim,lease_until=utc_now()+timedelta(seconds=self.lease_seconds))
            session.add(receipt);member.state=row.state='deriving'
            self.event(self.families,session,row,receipt,'claim',{'claim_id':claim})
            await session.flush();await self.families._read(session,row)
            return self.read(receipt),{'input':copy.deepcopy(value),'claim_id':claim},False

    async def complete(self,workspace,master,family_id,receipt_id,claim_id,copies,*,verify):
        try:
            async with self.session_factory() as session,session.begin():
                family,current=await self._load(session,workspace,master,family_id)
                receipt=await session.get(SqlVariantArtifactReceiptORM,receipt_id);self._active(family,receipt,claim_id)
                expected={'version':family.version,'snapshot_sha256':family.snapshot_sha256,'input_sha256':receipt.input_sha256,
                    'request_sha256':receipt.request_sha256,'actor_ref':receipt.actor_ref,'lease_until':receipt.lease_until}
                if not current.source_current:raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
                await verify(copies);self._active(family,receipt,claim_id)
                await self._source_jobs_current(session,receipt)
                result=make_result(receipt.input_json,copies)
                await write_child(session,receipt,copies)
                member=await session.get(SqlVariantMemberORM,receipt.member_id)
                await self._completion_fence(session,family,receipt,claim_id,expected)
                receipt.state,receipt.result_json,receipt.result_sha256='ready',result,digest(result)
                receipt.claim_id=receipt.lease_until=None;receipt.updated_at=utc_now()
                member.child_project_id,member.initial_timeline_version_id,member.state=result['child_project_id'],result['timeline_version_id'],'needs_attention'
                family.state='needs_attention'
                self.event(self.families,session,family,receipt,'complete',{'result_sha256':receipt.result_sha256,'child_project_id':result['child_project_id']})
                await session.flush();final=await self.families._read(session,family)
                await verify(copies)
                await self._source_jobs_current(session,receipt)
                if not final.source_current:raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
                self._assert_closed_fence(family,receipt,expected,digest(result))
                return self.read(receipt)
        except IntegrityError:raise SqlVariantError('SQL_VARIANT_DERIVATION_CONFLICT') from None

async def write_child(session,receipt,copies):
    value=receipt.input_json;ids,content,snapshot=derive_uploaded(value,copies);mapping=ids['graph']
    master=await session.get(VideoProjectORM,value['master_project_id']);child_id=value['planned_project_id']
    lineage={'source_type':'uploaded_variant_derivative','derivation_receipt_id':receipt.receipt_id,
        'parent_project_id':master.project_id,'input_sha256':receipt.input_sha256,'approval_inherited':False,
        'rights_override_inherited':False,'publishing_enabled':False,'external_call':False,'new_inference_calls':0}
    session.add(VideoProjectORM(project_id=child_id,workspace_id=value['workspace_id'],slug='variant-'+value['member_id'][4:],
        name=master.name[:180]+' · '+value['profile']['target'],niche=master.niche,status='draft',current_version_id=ids['content_version_id'],provenance=lineage))
    await session.flush()
    session.add(ProjectVersionORM(project_version_id=ids['content_version_id'],workspace_id=value['workspace_id'],project_id=child_id,
        ordinal=1,label='mvp1-content' if content else 'variant-uploaded-draft',snapshot={'content':content} if content else {'derivative':lineage},
        provenance={**lineage,'approved':False,'content_sha256':digest(content)}))
    await session.flush()
    for old,new in ids['assets'].items():
        source=value['source_assets'][old];copied=copies[old]
        session.add(AssetORM(asset_id=new,workspace_id=value['workspace_id'],project_id=child_id,project_version_id=ids['content_version_id'],
            asset_class=source['asset_class'],kind=source['kind'],filename=old+'.'+copied['object_key'].rsplit('.',1)[-1],
            object_key=copied['object_key'],content_type=copied['content_type'],size_bytes=copied['size_bytes'],checksum_sha256=copied['sha256'],
            storage_provider=copied['storage_provider'],provenance={**lineage,'source_type':'verified_variant_derivative',
                'parent_asset_id':old,'parent_record_sha256':digest(source),'source_bytes_verified':True,
                'rights_status':'unknown','license':None,'media_metadata':copy.deepcopy(source['provenance'].get('media_metadata')),
                'production_eligible':source['provenance'].get('production_eligible') is not False}))
    await session.flush()
    # Rows retain typed parent evidence; only relational identities are derived.
    for table in ('auto_edit_analyses','transcripts','transcript_segments','transcript_words','scenes','silence_decisions','highlights'):
        model=GRAPH_MODELS[table]
        for original in rows(value,table):
            new=video_record(receipt,ids,table,original)
            session.add(model(**fields(model,new)))
        await session.flush()
    normalized=audio_versions(value,ids)
    for original in rows(value,'uploaded_audio_transcriptions'):
        new=copy.deepcopy(original);audio=mapping[original['audio_id']];job=identity('job_vimport_',value['member_id']+'/'+original['audio_id'])
        # This is a durable import audit, never queued or attached to the master model job.
        request=VariantEvidenceImportInput(audio_id=audio,receipt_id=receipt.receipt_id,source_sha256=original['source_sha256'],
            input_sha256=receipt.input_sha256,actor_ref=receipt.actor_ref).model_dump(mode='json')
        session.add(JobORM(job_id=job,workspace_id=value['workspace_id'],project_id=child_id,project_version_id=ids['content_version_id'],
            status='awaiting_review',stage='awaiting_review',progress=100,request_json=request,artifacts_json=[],created_at=utc_now(),updated_at=utc_now()))
        await session.flush()
        session.add(JobEventORM(event_id=identity('evt_',job+'/import'),job_id=job,workspace_id=value['workspace_id'],
            event_type='variant.evidence.imported',to_status='awaiting_review',to_stage='awaiting_review',to_progress=100,
            actor_ref=receipt.actor_ref,payload_json={'receipt_id':receipt.receipt_id,'input_sha256':receipt.input_sha256,
                'provider_calls':0,'new_inference_calls':0,'approval_inherited':False}))
        new.update(audio_id=audio,asset_id=mapping[original['asset_id']],job_id=job,project_id=child_id,workspace_id=value['workspace_id'],
            claim_id=None,lease_expires_at=None,request_key_sha256=digest([receipt.receipt_id,original['audio_id']]),
            request_sha256=digest(request),configuration_json={**copy.deepcopy(original['configuration_json']),
                'variant_import':{**lineage,'parent_audio_id':original['audio_id'],'parent_job_id':original['job_id'],
                    'original_record_sha256':digest(original),'new_provider_billed_cost_vnd':0,'operating_cost_vnd':None}})
        session.add(UploadedAudioORM(**fields(UploadedAudioORM,new)));await session.flush()
        for version in rows(value,'uploaded_audio_transcript_versions'):
            if version['audio_id']!=original['audio_id']:continue
            body=normalized[version['transcript_id']]
            session.add(UploadedAudioVersionORM(transcript_id=body['transcript_id'],audio_id=audio,version=version['version'],
                transcript_json=body,transcript_sha256=digest(body),actor_ref=receipt.actor_ref,created_at=datetime.fromisoformat(version['created_at'])))
        await session.flush()
    source_analysis=mapping.get(value['source_timeline']['metadata'].get('source_analysis_id'))
    timeline=TimelineORM(timeline_id=ids['timeline_id'],workspace_id=value['workspace_id'],project_id=child_id,
        project_version_id=ids['content_version_id'],source_analysis_id=source_analysis,source_content_version_id=ids['content_version_id'] if content else None,
        current_version_id=ids['timeline_version_id'],current_version=1,approval_status='draft')
    session.add(timeline);await session.flush()
    session.add(TimelineVersionORM(timeline_version_id=ids['timeline_version_id'],timeline_id=ids['timeline_id'],project_id=child_id,
        version=1,snapshot_json=snapshot,mutation_json={'type':'uploaded_variant_derivative','receipt_id':receipt.receipt_id,
            'source_timeline_sha256':digest(value['source_timeline']),'input_sha256':receipt.input_sha256},actor_ref=receipt.actor_ref))

async def validate_completed(session,receipt):
    value=receipt.input_json;result=make_result(value,receipt.result_json['copies'])
    if result!=receipt.result_json:raise ValueError('import output changed')
    ids,content,snapshot=derive_uploaded(value,result['copies'])
    child=await session.get(VideoProjectORM,value['planned_project_id'])
    first=await session.get(TimelineVersionORM,ids['timeline_version_id'])
    version=await session.get(ProjectVersionORM,ids['content_version_id'])
    if (child is None or child.workspace_id!=receipt.workspace_id or first is None or first.snapshot_json!=snapshot
        or first.project_id!=child.project_id or first.version!=1 or first.actor_ref!=receipt.actor_ref
        or version is None or version.project_id!=child.project_id
        or content is not None and version.snapshot!={'content':content}):raise ValueError('child history changed')
    for old,new in ids['assets'].items():
        asset=await session.get(AssetORM,new);copied=result['copies'][old];source=value['source_assets'][old]
        if (asset is None or (asset.project_id,asset.workspace_id,asset.object_key,asset.checksum_sha256,asset.size_bytes,
                asset.asset_class,asset.kind,asset.project_version_id)!=(child.project_id,receipt.workspace_id,copied['object_key'],
                copied['sha256'],copied['size_bytes'],source['asset_class'],source['kind'],ids['content_version_id'])
            or asset.provenance.get('parent_record_sha256')!=digest(source) or asset.provenance.get('derivation_receipt_id')!=receipt.receipt_id
            or asset.provenance.get('media_metadata')!=source['provenance'].get('media_metadata')):raise ValueError('asset custody changed')
    for original in rows(value,'auto_edit_analyses'):
        current=await session.get(AutoEditAnalysisORM,ids['graph'][original['analysis_id']])
        if current is None or current.provenance_json.get('original_record')!=original or current.project_id!=child.project_id:raise ValueError('analysis origin changed')
    from .sql_variant_uploaded_identity import TABLE_IDS
    for table in ('auto_edit_analyses','transcripts','transcript_segments','transcript_words','scenes','silence_decisions','highlights'):
        for original in rows(value,table):
            expected=video_record(receipt,ids,table,original)
            current=await session.get(GRAPH_MODELS[table],expected[TABLE_IDS[table]])
            if current is None:raise ValueError('immutable imported graph changed')
            actual=record_value(current)
            if table=='auto_edit_analyses':
                # Existing word/text edits append immutable transcripts and update
                # only these analysis freshness flags. Do not freeze child editing.
                actual['updated_at']=expected['updated_at']
                flags={'human_transcript_revision','semantic_analysis_refresh_required'}
                before={k:v for k,v in expected['provenance_json'].items() if k not in flags}
                after={k:v for k,v in actual['provenance_json'].items() if k not in flags}
                if before!=after:raise ValueError('analysis origin changed')
                if actual['provenance_json']!=expected['provenance_json']:
                    latest=await session.scalar(select(TranscriptORM).where(TranscriptORM.analysis_id==current.analysis_id)
                        .order_by(TranscriptORM.version.desc()).limit(1))
                    if (latest is None or latest.provenance_json.get('human_edit') is not True
                        or actual['provenance_json'].get('human_transcript_revision')!=latest.version
                        or actual['provenance_json'].get('semantic_analysis_refresh_required') is not True):
                        raise ValueError('invalid analysis edit history')
                actual['provenance_json']=expected['provenance_json']
            if actual!=expected:raise ValueError('immutable imported graph changed')
    for original in rows(value,'uploaded_audio_transcriptions'):
        current=await session.get(UploadedAudioORM,ids['graph'][original['audio_id']])
        job=await session.get(JobORM,current.job_id) if current else None
        expected_job=identity('job_vimport_',value['member_id']+'/'+original['audio_id'])
        expected_request=VariantEvidenceImportInput(audio_id=ids['graph'][original['audio_id']],receipt_id=receipt.receipt_id,
            source_sha256=original['source_sha256'],input_sha256=receipt.input_sha256,actor_ref=receipt.actor_ref).model_dump(mode='json')
        if (current is None or current.original_evidence_json!=original['original_evidence_json']
            or current.original_evidence_sha256!=original['original_evidence_sha256'] or job is None
            or (job.project_id,job.workspace_id,job.project_version_id,job.status,job.stage,job.progress)!=(child.project_id,
                receipt.workspace_id,ids['content_version_id'],'awaiting_review','awaiting_review',100)
            or job.request_json!=expected_request or job.job_id!=expected_job or current.request_sha256!=digest(expected_request)
            or (current.asset_id,current.project_id,current.workspace_id)!=(ids['assets'][original['asset_id']],child.project_id,receipt.workspace_id)
            or current.claim_id is not None or current.lease_expires_at is not None):raise ValueError('audio origin changed')
        audit=await session.get(JobEventORM,identity('evt_',expected_job+'/import'))
        if (audit is None or audit.job_id!=expected_job or audit.actor_ref!=receipt.actor_ref or audit.event_type!='variant.evidence.imported'
            or audit.payload_json!={'receipt_id':receipt.receipt_id,'input_sha256':receipt.input_sha256,
                'provider_calls':0,'new_inference_calls':0,'approval_inherited':False}):raise ValueError('import audit changed')
        if (current.configuration_json.get('variant_import',{}).get('original_record_sha256')!=digest(original)
            or current.source_sha256!=original['source_sha256'] or current.source_size_bytes!=original['source_size_bytes']
            or current.media_metadata_json!=original['media_metadata_json']
            or current.configuration_json.get('provider')!=original['configuration_json'].get('provider')):raise ValueError('audio source changed')
    normalized=audio_versions(value,ids)
    for original in rows(value,'uploaded_audio_transcript_versions'):
        expected=normalized[original['transcript_id']]
        current=await session.get(UploadedAudioVersionORM,expected['transcript_id'])
        if (current is None or current.audio_id!=ids['graph'][original['audio_id']] or current.transcript_json!=expected
            or current.transcript_sha256!=digest(expected) or current.actor_ref!=receipt.actor_ref
            or record_value(current)['created_at']!=original['created_at']):raise ValueError('audio history changed')

def video_record(receipt,ids,table,original):
    value=receipt.input_json;mapping=ids['graph'];new=copy.deepcopy(original)
    lineage={'source_type':'uploaded_variant_derivative','derivation_receipt_id':receipt.receipt_id,
        'parent_project_id':value['master_project_id'],'input_sha256':receipt.input_sha256,'approval_inherited':False,
        'rights_override_inherited':False,'publishing_enabled':False,'external_call':False,'new_inference_calls':0}
    for key in ('analysis_id','asset_id','transcript_id','segment_id','word_id','scene_id','decision_id','highlight_id'):
        if new.get(key) is not None:new[key]=mapping[new[key]]
    if table=='auto_edit_analyses':
        configuration=rebind(original['configuration_json'],mapping);configuration['acceptance_operation_id']=None
        new.update(project_id=value['planned_project_id'],workspace_id=value['workspace_id'],project_version_id=ids['content_version_id'],
            configuration_json=configuration,fingerprint=digest([receipt.input_sha256,original['analysis_id']]),
            provenance_json={**copy.deepcopy(original['provenance_json']),**lineage,
                'original_record':copy.deepcopy(original),'original_record_sha256':digest(original),'origin_provider_result_reused':True})
    elif table=='transcripts':
        new['provenance_json']={**rebind_provenance(original['provenance_json'],mapping),**lineage,
            'inherited_original_provenance':copy.deepcopy(original['provenance_json']),
            'original_record_sha256':digest(original),'recognition_review_required':True}
    elif table in {'scenes','silence_decisions','highlights'}:
        new['evidence_json']={**rebind(original['evidence_json'],mapping),**lineage,
            'inherited_original_evidence':copy.deepcopy(original['evidence_json']),'original_record_sha256':digest(original)}
    return new
