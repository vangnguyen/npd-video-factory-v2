"""Scoped SQL family reservations, without child creation or provider execution.

S1 freezes actual source metadata and version graphs. It does not attest byte
custody or upload trust; those require a later verified artifact import step.
"""
from __future__ import annotations
import base64
import copy
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import uuid

from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from .db import AssetORM, ProjectVersionORM, VideoProjectORM, utc_now
from .timeline_db import TimelineORM, TimelineVersionORM
from .timeline_models import TimelineSnapshot
from .auto_edit_db import (AutoEditAnalysisORM, TranscriptORM, TranscriptSegmentORM,
    TranscriptWordORM, SceneORM, SilenceDecisionORM, HighlightORM, UploadSessionORM)
from .production_db import (ProductionPackageORM, ProductionRenderJobORM, ProductionApprovalORM,
    AudioMixVersionORM, SubtitleVersionORM)
from .uploaded_audio_db import UploadedAudioORM, UploadedAudioVersionORM
from .vision_db import (VisionAnalysisORM, VisionFrameORM, VisionSceneInsightORM,
    VisionSubjectTrackORM, VisionReframePlanORM)
from .sql_variant_db import (SqlVariantFamilyORM, SqlVariantMemberORM,
    SqlVariantArtifactReceiptORM, SqlVariantEventORM)
from .sql_variant_models import (AssetProof, AssetReceiptRead, AssetReceiptReserveRequest,
    FamilyMemberRead, FamilyPage, FamilyRead, FamilyReserveRequest, FamilySnapshot,
    FamilyVersionRequest, MasterBinding, NoAuthority, RecordProof, VariantAvailability,
    VariantCatalog, VariantProfile, as_utc, canonical, default_catalog, digest)


class SqlVariantError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def identity(prefix, value):
    return prefix + uuid.uuid5(uuid.NAMESPACE_URL, 'sql-master-variants.v1/' + value).hex


def request_parts(payload):
    body = payload.model_dump(mode='json', exclude={'request_key'})
    return body, digest(body), hashlib.sha256(payload.request_key.encode()).hexdigest()


def record_value(row):
    value = {}
    for column in row.__table__.columns:
        item = getattr(row, column.name)
        if isinstance(item, datetime):
            item = as_utc(item).isoformat()
        elif isinstance(item, Decimal):
            item = str(item)
        value[column.name] = copy.deepcopy(item)
    canonical(value)
    return value


class SqlVariantFamilyRepository:
    def __init__(self, session_factory, *, catalog=None, max_families_per_master=50):
        # Constructor does no SQL/file/provider IO and retains no mutable DTO.
        value = catalog or default_catalog()
        self._catalog = canonical(VariantCatalog.model_validate_json(value.model_dump_json()).model_dump(mode='json'))
        if type(max_families_per_master) is not int or not 1 <= max_families_per_master <= 1000:
            raise ValueError('SQL_VARIANT_FAMILY_LIMIT_INVALID')
        self.session_factory = session_factory
        self.max_families_per_master = max_families_per_master

    def catalog(self):
        return VariantCatalog.model_validate_json(self._catalog)

    @staticmethod
    def actor(actor_ref):
        if not isinstance(actor_ref, str) or not actor_ref.strip() or len(actor_ref) > 160 or any(ord(c) < 32 for c in actor_ref):
            raise SqlVariantError('SQL_VARIANT_ACTOR_REQUIRED')

    async def _project(self, session, workspace, master, *, lock=False):
        if lock:
            result = await session.execute(update(VideoProjectORM).where(
                VideoProjectORM.project_id == master, VideoProjectORM.workspace_id == workspace)
                .values(updated_at=VideoProjectORM.updated_at))
            if result.rowcount != 1:
                raise KeyError('SQL_VARIANT_MASTER_NOT_FOUND')
        query = select(VideoProjectORM).where(VideoProjectORM.project_id == master,
            VideoProjectORM.workspace_id == workspace).execution_options(populate_existing=True)
        if lock:
            query = query.with_for_update()
        row = await session.scalar(query)
        if row is None:
            raise KeyError('SQL_VARIANT_MASTER_NOT_FOUND')
        return row

    async def _proof(self, session, model, owner, condition):
        query = select(model).where(condition).order_by(*model.__table__.primary_key.columns).limit(50001)
        rows = (await session.scalars(query.execution_options(populate_existing=True))).all()
        if len(rows) > 50000:
            raise SqlVariantError('SQL_VARIANT_SOURCE_PROOF_LIMIT')
        return RecordProof(table=model.__tablename__, owner_ref=owner, count=len(rows),
            sha256=digest([record_value(row) for row in rows]))

    async def _analysis_proofs(self, session, analysis, selected=None):
        records = [RecordProof(table='auto_edit_analyses', owner_ref=analysis.analysis_id, count=1,
            sha256=digest([record_value(analysis)]))]
        transcripts = (await session.scalars(select(TranscriptORM).where(TranscriptORM.analysis_id == analysis.analysis_id)
            .order_by(TranscriptORM.version).limit(1001).execution_options(populate_existing=True))).all()
        if len(transcripts) > 1000 or any(t.asset_id != analysis.asset_id for t in transcripts):
            raise SqlVariantError('SQL_VARIANT_TRANSCRIPT_SOURCE_CHANGED_OR_LIMIT')
        if selected is None and transcripts:
            selected = transcripts[-1].transcript_id
        if selected is not None and selected not in {t.transcript_id for t in transcripts}:
            raise SqlVariantError('SQL_VARIANT_TRANSCRIPT_SELECTION_CHANGED')
        records.append(RecordProof(table='transcripts', owner_ref=analysis.analysis_id, count=len(transcripts),
            sha256=digest([record_value(t) for t in transcripts])))
        transcript_ids = [t.transcript_id for t in transcripts]
        for model in (TranscriptSegmentORM, TranscriptWordORM):
            records.append(await self._proof(session, model, analysis.analysis_id, model.transcript_id.in_(transcript_ids)))
        for model in (SceneORM, SilenceDecisionORM, HighlightORM):
            records.append(await self._proof(session, model, analysis.analysis_id, model.analysis_id == analysis.analysis_id))
        return records, selected

    async def _binding(self, session, workspace, master):
        project = await self._project(session, workspace, master)
        timeline = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == master,
            TimelineORM.workspace_id == workspace).execution_options(populate_existing=True))
        if timeline is None:
            raise SqlVariantError('SQL_VARIANT_CANONICAL_TIMELINE_REQUIRED')
        version = await session.get(TimelineVersionORM, timeline.current_version_id, populate_existing=True)
        if version is None or version.project_id != master or version.timeline_id != timeline.timeline_id \
                or version.version != timeline.current_version:
            raise SqlVariantError('SQL_VARIANT_CANONICAL_VERSION_CHANGED')
        try:
            snapshot = TimelineSnapshot.model_validate(version.snapshot_json)
        except ValueError:
            raise SqlVariantError('SQL_VARIANT_CANONICAL_INPUT_INVALID') from None
        records = [RecordProof(table='video_projects', owner_ref=master, count=1, sha256=digest([record_value(project)])),
            RecordProof(table='timeline_versions', owner_ref=version.timeline_version_id, count=1, sha256=digest([record_value(version)]))]
        for version_id in sorted({v for v in (project.current_version_id, timeline.source_content_version_id) if v}):
            content = await session.get(ProjectVersionORM, version_id, populate_existing=True)
            if content is None or (content.workspace_id, content.project_id) != (workspace, master):
                raise SqlVariantError('SQL_VARIANT_PROJECT_VERSION_SCOPE_CHANGED')
            records.append(RecordProof(table='project_versions', owner_ref=version_id, count=1, sha256=digest([record_value(content)])))
        asset_ids = {clip.asset_id for track in snapshot.tracks for clip in track.clips if clip.asset_id}
        selected_transcript_id = (snapshot.metadata.get('transcript_revision') or {}).get('transcript_id')
        captured_analyses = set()
        if timeline.source_analysis_id:
            mode = 'video_analysis'
            analysis = await session.get(AutoEditAnalysisORM, timeline.source_analysis_id, populate_existing=True)
            if analysis is None or (analysis.workspace_id, analysis.project_id) != (workspace, master) or analysis.status != 'succeeded':
                raise SqlVariantError('SQL_VARIANT_SOURCE_ANALYSIS_NOT_READY')
            if snapshot.metadata.get('source_analysis_id') != analysis.analysis_id:
                raise SqlVariantError('SQL_VARIANT_SOURCE_ANALYSIS_BINDING_CHANGED')
            asset_ids.add(analysis.asset_id)
            graph, selected_transcript_id = await self._analysis_proofs(session, analysis, selected_transcript_id)
            records.extend(graph)
            captured_analyses.add(analysis.analysis_id)
        else:
            mode = snapshot.metadata.get('source_kind')
            if mode not in {'storyboard_media', 'mixed'} or snapshot.metadata.get('content_version_id') != timeline.source_content_version_id:
                raise SqlVariantError('SQL_VARIANT_SOURCE_CONTENT_BINDING_CHANGED')
            latest = await session.scalar(select(ProjectVersionORM).where(ProjectVersionORM.project_id == master,
                ProjectVersionORM.workspace_id == workspace, ProjectVersionORM.label == 'mvp1-content')
                .order_by(ProjectVersionORM.ordinal.desc()).limit(1))
            if latest is None or latest.project_version_id != timeline.source_content_version_id:
                raise SqlVariantError('SQL_VARIANT_SOURCE_CONTENT_STALE')
            if selected_transcript_id is not None:
                raise SqlVariantError('SQL_VARIANT_TRANSCRIPT_SELECTION_CHANGED')
        # Mixed/storyboard source clips may have independent ASR evidence.
        additional = {c.metadata.get('analysis_id') for t in snapshot.tracks for c in t.clips if c.metadata.get('analysis_id')}
        for analysis_id in sorted(additional - captured_analyses):
            row = await session.get(AutoEditAnalysisORM, analysis_id, populate_existing=True)
            if row is None or (row.workspace_id, row.project_id) != (workspace, master) or row.status != 'succeeded':
                raise SqlVariantError('SQL_VARIANT_SOURCE_ANALYSIS_NOT_READY')
            asset_ids.add(row.asset_id)
            graph, _ = await self._analysis_proofs(session, row)
            records.extend(graph)
            captured_analyses.add(row.analysis_id)
        for audio_id, value in sorted((snapshot.metadata.get('uploaded_audio_bindings_v1') or {}).items()):
            parent = await session.get(UploadedAudioORM, audio_id, populate_existing=True)
            if parent is None or (parent.workspace_id, parent.project_id) != (workspace, master) or value.get('audio_id') != audio_id:
                raise SqlVariantError('SQL_VARIANT_AUDIO_BINDING_SCOPE_CHANGED')
            selected = await session.get(UploadedAudioVersionORM, value.get('transcript_id'), populate_existing=True)
            if selected is None or selected.audio_id != audio_id or selected.transcript_json != value.get('transcript') \
                    or selected.transcript_sha256 != value.get('transcript_sha256'):
                raise SqlVariantError('SQL_VARIANT_AUDIO_TRANSCRIPT_BINDING_CHANGED')
            asset_ids.add(parent.asset_id)
            records.append(RecordProof(table='uploaded_audio_transcriptions', owner_ref=audio_id, count=1,
                sha256=digest([record_value(parent)])))
            records.append(await self._proof(session, UploadedAudioVersionORM, audio_id, UploadedAudioVersionORM.audio_id == audio_id))
        visions = (await session.scalars(select(VisionAnalysisORM).where(VisionAnalysisORM.project_id == master,
            VisionAnalysisORM.workspace_id == workspace, VisionAnalysisORM.analysis_id.in_(captured_analyses))
            .order_by(VisionAnalysisORM.vision_analysis_id).limit(101).execution_options(populate_existing=True))).all()
        if len(visions) > 100:
            raise SqlVariantError('SQL_VARIANT_VISION_HISTORY_LIMIT')
        for vision in visions:
            if vision.asset_id not in asset_ids:
                raise SqlVariantError('SQL_VARIANT_VISION_SOURCE_CHANGED')
            records.append(RecordProof(table='vision_analyses', owner_ref=vision.vision_analysis_id, count=1,
                sha256=digest([record_value(vision)])))
            for model in (VisionFrameORM, VisionSceneInsightORM, VisionSubjectTrackORM, VisionReframePlanORM):
                records.append(await self._proof(session, model, vision.vision_analysis_id, model.vision_analysis_id == vision.vision_analysis_id))
        package = await session.scalar(select(ProductionPackageORM).where(ProductionPackageORM.project_id == master,
            ProductionPackageORM.workspace_id == workspace).execution_options(populate_existing=True))
        if package:
            records.append(RecordProof(table='production_packages', owner_ref=package.package_id, count=1, sha256=digest([record_value(package)])))
            for model, ref in ((AudioMixVersionORM, package.current_audio_version_id),
                               (SubtitleVersionORM, package.current_subtitle_version_id),
                               (ProductionApprovalORM, package.current_approval_id),
                               (ProductionRenderJobORM, package.latest_review_render_id)):
                if not ref:
                    continue
                row = await session.get(model, ref, populate_existing=True)
                if row is None or row.project_id != master:
                    raise SqlVariantError('SQL_VARIANT_PRODUCTION_SCOPE_CHANGED')
                records.append(RecordProof(table=model.__tablename__, owner_ref=ref, count=1, sha256=digest([record_value(row)])))
                if isinstance(row, AudioMixVersionORM):
                    music = (row.config_json.get('music') or {}).get('asset_id')
                    if music:
                        asset_ids.add(music)
                if isinstance(row, ProductionRenderJobORM):
                    manifest = row.manifest_json or {}
                    asset_ids.update(a for a in (manifest.get('supporting_asset_ids') or {}).values() if a)
                    asset_ids.update(unit['provider_audio_asset_id'] for unit in (manifest.get('narration') or {}).get('timing', []) if unit.get('provider_audio_asset_id'))
        assets = []
        captured_versions = {p.owner_ref for p in records if p.table == 'project_versions'}
        if len(asset_ids) > 5000:
            raise SqlVariantError('SQL_VARIANT_SOURCE_ASSET_LIMIT')
        for asset_id in sorted(asset_ids):
            asset = await session.get(AssetORM, asset_id, populate_existing=True)
            if asset is None or (asset.workspace_id, asset.project_id) != (workspace, master):
                raise SqlVariantError('SQL_VARIANT_SOURCE_ASSET_SCOPE_CHANGED')
            if asset.project_version_id and asset.project_version_id not in captured_versions:
                asset_version = await session.get(ProjectVersionORM, asset.project_version_id, populate_existing=True)
                if asset_version is None or (asset_version.workspace_id, asset_version.project_id) != (workspace, master):
                    raise SqlVariantError('SQL_VARIANT_ASSET_VERSION_SCOPE_CHANGED')
                records.append(RecordProof(table='project_versions', owner_ref=asset_version.project_version_id,
                    count=1, sha256=digest([record_value(asset_version)])))
                captured_versions.add(asset_version.project_version_id)
            assets.append(AssetProof(asset_id=asset.asset_id, workspace_id=workspace, project_id=master,
                project_version_id=asset.project_version_id, asset_class=asset.asset_class, kind=asset.kind,
                content_type=asset.content_type, size_bytes=asset.size_bytes, checksum_sha256=asset.checksum_sha256,
                storage_provider=asset.storage_provider, object_key_sha256=hashlib.sha256(asset.object_key.encode()).hexdigest(),
                record_sha256=digest(record_value(asset))))
            upload_ref = asset.provenance.get('source_reference') if asset.provenance.get('source_type') == 'user_upload' else None
            if asset.provenance.get('source_type') == 'user_upload' and not upload_ref:
                raise SqlVariantError('SQL_VARIANT_UPLOAD_REFERENCE_CHANGED')
            if upload_ref:
                upload = await session.get(UploadSessionORM, upload_ref, populate_existing=True)
                if upload is None or (upload.workspace_id, upload.project_id, upload.asset_id) != (workspace, master, asset_id):
                    raise SqlVariantError('SQL_VARIANT_UPLOAD_REFERENCE_CHANGED')
                records.append(RecordProof(table='upload_sessions', owner_ref=upload_ref, count=1, sha256=digest([record_value(upload)])))
        return MasterBinding(workspace_id=workspace, master_project_id=master, project_version=project.version,
            project_current_version_id=project.current_version_id, timeline_id=timeline.timeline_id,
            timeline_version_id=version.timeline_version_id, timeline_version=version.version,
            timeline_snapshot_sha256=digest(version.snapshot_json), source_mode=mode,
            source_analysis_id=timeline.source_analysis_id, source_content_version_id=timeline.source_content_version_id,
            selected_transcript_id=selected_transcript_id, records=records, assets=assets)

    async def availability(self, workspace_id, master_project_id):
        async with self.session_factory() as session:
            binding = await self._binding(session, workspace_id, master_project_id)
            catalog = self.catalog()
            return VariantAvailability(catalog=catalog, catalog_sha256=digest(catalog.model_dump(mode='json')),
                binding=binding, binding_sha256=digest(binding.model_dump(mode='json')))

    @staticmethod
    def _ids(workspace, master, key_sha, request_sha, profile_ref=None):
        family = identity('vfa_', workspace + '/' + master + '/' + key_sha + '/' + request_sha)
        if profile_ref is None:
            return family
        return identity('vfm_', family + '/' + profile_ref), identity('prj_', workspace + '/' + family + '/' + profile_ref)

    async def _read(self, session, row):
        try:
            snapshot = FamilySnapshot.model_validate(row.snapshot_json)
            request = FamilyReserveRequest.model_validate({**snapshot.request, 'request_key': 'internal-variant-history-key'})
            if digest(row.snapshot_json) != row.snapshot_sha256 or digest(row.result_json) != row.result_sha256 \
                    or digest(snapshot.request) != row.request_sha256 or snapshot.request_sha256 != row.request_sha256 \
                    or digest(snapshot.binding.model_dump(mode='json')) != snapshot.binding_sha256 \
                    or digest(snapshot.catalog.model_dump(mode='json')) != snapshot.catalog_sha256 \
                    or snapshot.binding_sha256 != request.expected_binding_sha256 \
                    or snapshot.catalog_sha256 != request.catalog_sha256 or snapshot.catalog.catalog_ref != request.catalog_ref \
                    or (row.workspace_id, row.master_project_id, row.master_timeline_version_id) != (
                        snapshot.binding.workspace_id, snapshot.binding.master_project_id, snapshot.binding.timeline_version_id) \
                    or (request.expected_project_version, request.expected_timeline_version, request.expected_timeline_version_id) != (
                        snapshot.binding.project_version, snapshot.binding.timeline_version, snapshot.binding.timeline_version_id) \
                    or row.family_id != self._ids(row.workspace_id, row.master_project_id, row.request_key_sha256, row.request_sha256):
                raise ValueError()
            original = await session.get(TimelineVersionORM, row.master_timeline_version_id)
            if original is None or original.project_id != row.master_project_id or original.timeline_id != snapshot.binding.timeline_id \
                    or original.version != snapshot.binding.timeline_version or digest(original.snapshot_json) != snapshot.binding.timeline_snapshot_sha256:
                raise ValueError()
            for proof in snapshot.binding.records:
                if proof.table == 'project_versions':
                    source_version = await session.get(ProjectVersionORM, proof.owner_ref, populate_existing=True)
                    if source_version is None or (source_version.workspace_id, source_version.project_id) != (row.workspace_id, row.master_project_id) \
                            or proof.count != 1 or proof.sha256 != digest([record_value(source_version)]):
                        raise ValueError()
            profiles = {p.profile_ref: p for p in snapshot.catalog.profiles}
            members = (await session.scalars(select(SqlVariantMemberORM).where(SqlVariantMemberORM.family_id == row.family_id))).all()
            ordered = {m.profile_ref: m for m in members}
            if len(members) != len(request.profile_refs) or set(ordered) != set(request.profile_refs):
                raise ValueError()
            reads = []
            for ref in request.profile_refs:
                member = ordered[ref]
                expected_id, expected_project = self._ids(row.workspace_id, row.master_project_id, row.request_key_sha256, row.request_sha256, ref)
                profile = VariantProfile.model_validate(member.profile_json)
                if profile != profiles.get(ref) or digest(member.profile_json) != member.profile_sha256 \
                        or member.member_id != expected_id or member.planned_project_id != expected_project \
                        or member.workspace_id != row.workspace_id or member.child_project_id is not None \
                        or member.initial_timeline_version_id is not None or member.state != row.state:
                    raise ValueError()
                reads.append(FamilyMemberRead(member_id=member.member_id, family_id=row.family_id,
                    workspace_id=row.workspace_id, profile=profile, planned_project_id=member.planned_project_id,
                    state=member.state))
            expected_result = {'schema_version': 'sql-variant-reservation-result.v1',
                'members': [{'member_id': m.member_id, 'profile_ref': m.profile.profile_ref,
                    'planned_project_id': m.planned_project_id} for m in reads],
                'safety': NoAuthority().model_dump(mode='json')}
            if row.result_json != expected_result or row.state not in {'reserved', 'cancelled'} or row.version < 1:
                raise ValueError()
            events = (await session.scalars(select(SqlVariantEventORM).where(SqlVariantEventORM.family_id == row.family_id)
                .order_by(SqlVariantEventORM.version))).all()
            if len(events) != row.version or row.version != (1 if row.state == 'reserved' else 2):
                raise ValueError()
            for index, event in enumerate(events, 1):
                if event.version != index or event.workspace_id != row.workspace_id \
                        or event.event_id != identity('vfe_', row.family_id + '/' + str(index)) \
                        or digest(event.payload_json) != event.payload_sha256:
                    raise ValueError()
                if index == 1:
                    expected_payload = {'from_version': None, 'to_version': 1, 'profiles': request.profile_refs,
                        'safety': NoAuthority().model_dump(mode='json')}
                    if event.event_type != 'family.reserved' or event.request_key_sha256 != row.request_key_sha256 \
                            or event.request_sha256 != row.request_sha256 or event.actor_ref != row.actor_ref or event.payload_json != expected_payload:
                        raise ValueError()
                else:
                    cancellation = FamilyVersionRequest.model_validate({**event.payload_json['request'], 'request_key': 'internal-cancel-history-key'})
                    if event.event_type != 'family.cancelled' or digest(event.payload_json['request']) != event.request_sha256 \
                            or cancellation.expected_version != 1 or cancellation.expected_snapshot_sha256 != row.snapshot_sha256 \
                            or event.payload_json != {'from_version': 1, 'to_version': 2, 'snapshot_sha256': row.snapshot_sha256,
                                'request': cancellation.model_dump(mode='json', exclude={'request_key'}), 'safety': NoAuthority().model_dump(mode='json')}:
                        raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise SqlVariantError('SQL_VARIANT_FAMILY_EVIDENCE_CHANGED') from None
        source_current, reason = True, None
        try:
            current = await self._binding(session, row.workspace_id, row.master_project_id)
            if digest(current.model_dump(mode='json')) != snapshot.binding_sha256:
                source_current, reason = False, 'SQL_VARIANT_MASTER_BINDING_CHANGED'
        except (SqlVariantError, KeyError, ValueError):
            source_current, reason = False, 'SQL_VARIANT_MASTER_NOT_CURRENT'
        return FamilyRead(family_id=row.family_id, workspace_id=row.workspace_id, master_project_id=row.master_project_id,
            version=row.version, state=row.state, snapshot=snapshot, snapshot_sha256=row.snapshot_sha256,
            result=copy.deepcopy(row.result_json), result_sha256=row.result_sha256, source_current=source_current,
            source_current_reason=reason, members=reads, actor_ref=row.actor_ref, created_at=as_utc(row.created_at))

    async def reserve(self, workspace_id, master_project_id, payload: FamilyReserveRequest, *, actor_ref):
        self.actor(actor_ref)
        payload = FamilyReserveRequest.model_validate(payload.model_dump())
        body, request_sha, key_sha = request_parts(payload)
        for _ in range(2):
            try:
                async with self.session_factory() as session, session.begin():
                    await self._project(session, workspace_id, master_project_id, lock=True)
                    prior = await session.scalar(select(SqlVariantFamilyORM).where(
                        SqlVariantFamilyORM.workspace_id == workspace_id, SqlVariantFamilyORM.master_project_id == master_project_id,
                        SqlVariantFamilyORM.request_key_sha256 == key_sha))
                    if prior:
                        if prior.request_sha256 != request_sha:
                            raise SqlVariantError('SQL_VARIANT_IDEMPOTENCY_CONFLICT')
                        if prior.actor_ref != actor_ref:
                            raise SqlVariantError('SQL_VARIANT_ACTOR_CHANGED')
                        return await self._read(session, prior), True
                    catalog = self.catalog()
                    if payload.catalog_ref != catalog.catalog_ref or payload.catalog_sha256 != digest(catalog.model_dump(mode='json')):
                        raise SqlVariantError('SQL_VARIANT_CATALOG_CHANGED')
                    by_ref = {p.profile_ref: p for p in catalog.profiles}
                    if any(ref not in by_ref for ref in payload.profile_refs):
                        raise SqlVariantError('SQL_VARIANT_PROFILE_UNKNOWN')
                    binding = await self._binding(session, workspace_id, master_project_id)
                    if (binding.project_version, binding.timeline_version, binding.timeline_version_id) != (
                            payload.expected_project_version, payload.expected_timeline_version, payload.expected_timeline_version_id) \
                            or digest(binding.model_dump(mode='json')) != payload.expected_binding_sha256:
                        raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
                    count = await session.scalar(select(func.count()).select_from(SqlVariantFamilyORM).where(
                        SqlVariantFamilyORM.workspace_id == workspace_id, SqlVariantFamilyORM.master_project_id == master_project_id))
                    if count >= self.max_families_per_master:
                        raise SqlVariantError('SQL_VARIANT_FAMILY_LIMIT')
                    family_id = self._ids(workspace_id, master_project_id, key_sha, request_sha)
                    snapshot = FamilySnapshot(binding=binding, binding_sha256=payload.expected_binding_sha256,
                        catalog=catalog, catalog_sha256=payload.catalog_sha256, request=body, request_sha256=request_sha)
                    stamp = utc_now()
                    result = {'schema_version': 'sql-variant-reservation-result.v1', 'members': [],
                        'safety': NoAuthority().model_dump(mode='json')}
                    family = SqlVariantFamilyORM(family_id=family_id, workspace_id=workspace_id, master_project_id=master_project_id,
                        master_timeline_version_id=binding.timeline_version_id, version=1, state='reserved',
                        request_key_sha256=key_sha, request_sha256=request_sha, snapshot_json=snapshot.model_dump(mode='json'),
                        snapshot_sha256=digest(snapshot.model_dump(mode='json')), result_json=copy.deepcopy(result), result_sha256=digest(result),
                        actor_ref=actor_ref, created_at=stamp, updated_at=stamp)
                    session.add(family)
                    await session.flush()
                    for ref in payload.profile_refs:
                        member_id, planned_project = self._ids(workspace_id, master_project_id, key_sha, request_sha, ref)
                        if await session.get(VideoProjectORM, planned_project) is not None:
                            raise SqlVariantError('SQL_VARIANT_PLANNED_PROJECT_COLLISION')
                        profile = by_ref[ref].model_dump(mode='json')
                        session.add(SqlVariantMemberORM(member_id=member_id, family_id=family_id, workspace_id=workspace_id,
                            profile_ref=ref, profile_json=profile, profile_sha256=digest(profile), planned_project_id=planned_project,
                            state='reserved', created_at=stamp, updated_at=stamp))
                        result['members'].append({'member_id': member_id, 'profile_ref': ref, 'planned_project_id': planned_project})
                    family.result_json = copy.deepcopy(result)
                    family.result_sha256 = digest(result)
                    self._event(session, family, 'family.reserved', key_sha, request_sha, actor_ref,
                        {'from_version': None, 'to_version': 1, 'profiles': payload.profile_refs, 'safety': NoAuthority().model_dump(mode='json')})
                    await session.flush()
                    return await self._read(session, family), False
            except IntegrityError:
                continue
        raise SqlVariantError('SQL_VARIANT_RESERVATION_CONFLICT')

    @staticmethod
    def _event(session, family, event_type, key_sha, request_sha, actor, payload):
        session.add(SqlVariantEventORM(event_id=identity('vfe_', family.family_id + '/' + str(family.version)),
            family_id=family.family_id, workspace_id=family.workspace_id, version=family.version, event_type=event_type,
            request_key_sha256=key_sha, request_sha256=request_sha, actor_ref=actor,
            payload_json=payload, payload_sha256=digest(payload), created_at=utc_now()))

    async def get(self, workspace_id, master_project_id, family_id):
        async with self.session_factory() as session:
            await self._project(session, workspace_id, master_project_id)
            row = await session.scalar(select(SqlVariantFamilyORM).where(SqlVariantFamilyORM.family_id == family_id,
                SqlVariantFamilyORM.workspace_id == workspace_id, SqlVariantFamilyORM.master_project_id == master_project_id))
            return await self._read(session, row) if row else None

    async def list(self, workspace_id, master_project_id, *, limit=25, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise SqlVariantError('SQL_VARIANT_PAGE_INVALID')
        after = None
        if cursor is not None:
            try:
                if not isinstance(cursor, str) or not 1 <= len(cursor) <= 1024:
                    raise ValueError()
                after = json.loads(base64.urlsafe_b64decode(cursor + '=' * (-len(cursor) % 4)))
                if not isinstance(after, list) or len(after) != 4 or after[:2] != [workspace_id, master_project_id]:
                    raise ValueError()
                stamp = datetime.fromisoformat(after[2])
                if stamp.tzinfo is None or not isinstance(after[3], str) or not after[3].startswith('vfa_'):
                    raise ValueError()
            except (ValueError, TypeError, UnicodeError):
                raise SqlVariantError('SQL_VARIANT_CURSOR_INVALID') from None
        async with self.session_factory() as session:
            await self._project(session, workspace_id, master_project_id)
            query = select(SqlVariantFamilyORM).where(SqlVariantFamilyORM.workspace_id == workspace_id,
                SqlVariantFamilyORM.master_project_id == master_project_id)
            if after:
                query = query.where((SqlVariantFamilyORM.created_at < stamp) | (
                    (SqlVariantFamilyORM.created_at == stamp) & (SqlVariantFamilyORM.family_id < after[3])))
            rows = (await session.scalars(query.order_by(SqlVariantFamilyORM.created_at.desc(),
                SqlVariantFamilyORM.family_id.desc()).limit(limit + 1))).all()
            next_cursor = None
            if len(rows) > limit:
                final = rows[limit - 1]
                next_cursor = base64.urlsafe_b64encode(canonical([workspace_id, master_project_id,
                    as_utc(final.created_at).isoformat(), final.family_id])).decode().rstrip('=')
            return FamilyPage(items=[await self._read(session, r) for r in rows[:limit]], next_cursor=next_cursor)

    async def cancel(self, workspace_id, master_project_id, family_id, payload: FamilyVersionRequest, *, actor_ref):
        self.actor(actor_ref)
        payload = FamilyVersionRequest.model_validate(payload.model_dump())
        body, request_sha, key_sha = request_parts(payload)
        async with self.session_factory() as session, session.begin():
            await self._project(session, workspace_id, master_project_id, lock=True)
            row = await session.scalar(select(SqlVariantFamilyORM).where(SqlVariantFamilyORM.family_id == family_id,
                SqlVariantFamilyORM.workspace_id == workspace_id, SqlVariantFamilyORM.master_project_id == master_project_id).with_for_update())
            if row is None:
                raise KeyError('SQL_VARIANT_FAMILY_NOT_FOUND')
            await self._read(session, row)
            prior = await session.scalar(select(SqlVariantEventORM).where(SqlVariantEventORM.family_id == family_id,
                SqlVariantEventORM.request_key_sha256 == key_sha))
            if prior:
                if prior.event_type != 'family.cancelled' or prior.request_sha256 != request_sha or prior.actor_ref != actor_ref:
                    raise SqlVariantError('SQL_VARIANT_IDEMPOTENCY_CONFLICT')
                return await self._read(session, row), True
            if row.version != payload.expected_version or row.snapshot_sha256 != payload.expected_snapshot_sha256:
                raise SqlVariantError('SQL_VARIANT_VERSION_CHANGED')
            if row.state != 'reserved':
                raise SqlVariantError('SQL_VARIANT_STATE_CHANGED')
            prior_version = row.version
            row.version += 1
            row.state = 'cancelled'
            row.updated_at = utc_now()
            await session.execute(update(SqlVariantMemberORM).where(SqlVariantMemberORM.family_id == family_id).values(state='cancelled', updated_at=row.updated_at))
            await session.execute(update(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.family_id == family_id,
                SqlVariantArtifactReceiptORM.state == 'reserved').values(state='cancelled', updated_at=row.updated_at))
            self._event(session, row, 'family.cancelled', key_sha, request_sha, actor_ref,
                {'from_version': prior_version, 'to_version': row.version, 'snapshot_sha256': row.snapshot_sha256,
                    'request': body, 'safety': NoAuthority().model_dump(mode='json')})
            await session.flush()
            return await self._read(session, row), False

    async def reserve_asset_receipt(self, workspace_id, master_project_id, family_id, payload: AssetReceiptReserveRequest, *, actor_ref):
        self.actor(actor_ref)
        payload = AssetReceiptReserveRequest.model_validate(payload.model_dump())
        body, request_sha, key_sha = request_parts(payload)
        async with self.session_factory() as session, session.begin():
            await self._project(session, workspace_id, master_project_id, lock=True)
            row = await session.scalar(select(SqlVariantFamilyORM).where(SqlVariantFamilyORM.family_id == family_id,
                SqlVariantFamilyORM.workspace_id == workspace_id, SqlVariantFamilyORM.master_project_id == master_project_id).with_for_update())
            if row is None:
                raise KeyError('SQL_VARIANT_FAMILY_NOT_FOUND')
            family = await self._read(session, row)
            prior = await session.scalar(select(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.family_id == family_id,
                SqlVariantArtifactReceiptORM.request_key_sha256 == key_sha))
            if prior:
                if prior.request_sha256 != request_sha or prior.actor_ref != actor_ref:
                    raise SqlVariantError('SQL_VARIANT_IDEMPOTENCY_CONFLICT')
                return self._receipt_read(prior, family), True
            if row.state != 'reserved' or row.version != payload.expected_version or row.snapshot_sha256 != payload.expected_snapshot_sha256:
                raise SqlVariantError('SQL_VARIANT_VERSION_CHANGED')
            if not family.source_current:
                raise SqlVariantError('SQL_VARIANT_MASTER_BINDING_CHANGED')
            member = next((m for m in family.members if m.member_id == payload.member_id), None)
            source = next((a for a in family.snapshot.binding.assets if a.asset_id == payload.source_asset_id), None)
            if member is None or source is None or source.record_sha256 != payload.expected_source_record_sha256:
                raise SqlVariantError('SQL_VARIANT_RECEIPT_SOURCE_OR_MEMBER_CHANGED')
            value = {'schema_version': 'sql-variant-asset-reservation-input.v1', 'workspace_id': workspace_id,
                'family_id': family_id, 'member_id': member.member_id, 'planned_project_id': member.planned_project_id,
                'family_snapshot_sha256': family.snapshot_sha256, 'source': source.model_dump(mode='json'),
                'request': body, 'safety': NoAuthority().model_dump(mode='json')}
            receipt_id = identity('vfr_', member.member_id + '/' + digest(value))
            existing = await session.get(SqlVariantArtifactReceiptORM, receipt_id)
            if existing is not None:
                raise SqlVariantError('SQL_VARIANT_RECEIPT_ALREADY_RESERVED')
            receipt = SqlVariantArtifactReceiptORM(receipt_id=receipt_id, family_id=family_id, member_id=member.member_id,
                workspace_id=workspace_id, kind='asset', state='reserved', request_key_sha256=key_sha,
                request_sha256=request_sha, input_json=value, input_sha256=digest(value), actor_ref=actor_ref)
            session.add(receipt)
            await session.flush()
            return self._receipt_read(receipt, family), False

    @staticmethod
    def _receipt_read(row, family):
        try:
            value = row.input_json
            source = AssetProof.model_validate(value['source'])
            request = AssetReceiptReserveRequest.model_validate({**value['request'], 'request_key': 'internal-receipt-history-key'})
            member = next((m for m in family.members if m.member_id == row.member_id), None)
            frozen = next((a for a in family.snapshot.binding.assets if a.asset_id == source.asset_id), None)
            expected = {'schema_version': 'sql-variant-asset-reservation-input.v1', 'workspace_id': family.workspace_id,
                'family_id': family.family_id, 'member_id': row.member_id, 'planned_project_id': member.planned_project_id if member else None,
                'family_snapshot_sha256': family.snapshot_sha256, 'source': frozen.model_dump(mode='json') if frozen else None,
                'request': request.model_dump(mode='json', exclude={'request_key'}), 'safety': NoAuthority().model_dump(mode='json')}
            if row.workspace_id != family.workspace_id or row.family_id != family.family_id or value != expected \
                    or digest(value) != row.input_sha256 or row.receipt_id != identity('vfr_', row.member_id + '/' + row.input_sha256) \
                    or row.kind != 'asset' or row.state not in {'reserved', 'cancelled'} or row.state != family.state \
                    or digest(value['request']) != row.request_sha256 or request.member_id != row.member_id \
                    or request.source_asset_id != source.asset_id or request.expected_source_record_sha256 != source.record_sha256 \
                    or request.expected_snapshot_sha256 != family.snapshot_sha256 or request.expected_version != 1 \
                    or any(v is not None for v in (row.result_json, row.result_sha256, row.claim_id, row.lease_until, row.target_asset_id)):
                raise ValueError()
            return AssetReceiptRead(receipt_id=row.receipt_id, family_id=row.family_id, member_id=row.member_id,
                workspace_id=row.workspace_id, state=row.state, input=copy.deepcopy(value), input_sha256=row.input_sha256,
                request_sha256=row.request_sha256, actor_ref=row.actor_ref)
        except (ValueError, TypeError, KeyError):
            raise SqlVariantError('SQL_VARIANT_RECEIPT_EVIDENCE_CHANGED') from None

    async def get_asset_receipt(self, workspace_id, master_project_id, family_id, receipt_id):
        async with self.session_factory() as session:
            await self._project(session, workspace_id, master_project_id)
            row = await session.scalar(select(SqlVariantFamilyORM).where(SqlVariantFamilyORM.family_id == family_id,
                SqlVariantFamilyORM.workspace_id == workspace_id, SqlVariantFamilyORM.master_project_id == master_project_id))
            if row is None:
                return None
            family = await self._read(session, row)
            receipt = await session.scalar(select(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.receipt_id == receipt_id,
                SqlVariantArtifactReceiptORM.family_id == family_id, SqlVariantArtifactReceiptORM.workspace_id == workspace_id))
            return self._receipt_read(receipt, family) if receipt else None
