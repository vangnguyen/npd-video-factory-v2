"""Owned real FFmpeg media + genuine ingest; explicit saved-ASR fixtures only.

No ASR/model/provider/network runs. Fixture evidence is never real-provider UAT.
"""
import asyncio
import copy
import hashlib
import io
import re
import shutil
import subprocess
import wave
from decimal import Decimal
from types import SimpleNamespace
import pytest
from sqlalchemy import select,func
from app.db import AssetORM,JobORM,ProjectVersionORM,VideoProjectORM,utc_now
from app.auto_edit_db import UploadSessionORM,AutoEditAnalysisORM,TranscriptORM,TranscriptWordORM
from app.auto_edit_models import UploadInitRequest,UploadCompleteRequest,AutoEditAnalysisRequest
from app.auto_edit_providers import FFprobeMediaProbe,ProviderTranscript,ProviderSegment,ProviderWord,require_positive_duration_transcript
from app.auto_edit_service import UploadService
from app.media_security import DeterministicMediaMalwareScanner
from app.timeline_models import TimelineCreateRequest,TimelineMutationRequest,TimelineOperation
from app.sql_variant_models import FamilyReserveRequest,FamilyVersionRequest,digest,canonical
from app.sql_variant_repository import SqlVariantFamilyRepository,SqlVariantError,record_value
from app.sql_variant_uploaded_repository import SqlUploadedDerivationRepository
from app.sql_variant_uploaded_copy import LocalEvidenceCopier
from app.sql_variant_uploaded_custody import trusted_derivative_source
from app.sql_variant_derivation_service import SqlStoryboardDerivationService
from app.sql_variant_db import SqlVariantArtifactReceiptORM
from app.sql_variant_uploaded_models import DeriveUploadedRequest
from app.timeline_db import TimelineORM,TimelineVersionORM
from app.uploaded_audio_db import UploadedAudioORM,UploadedAudioVersionORM
from app.production_db import ProductionPackageORM,ProductionApprovalORM
from test_sql_variant_family import env
from test_auto_edit_analysis import bytes_stream

async def ingest(env,path,kind,mime,*,rights='unknown'):
    raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    service=UploadService(repository=env.assets,platform=env.platform,object_storage=env.storage,
        media_probe=FFprobeMediaProbe(),malware_scanner=DeterministicMediaMalwareScanner(),staging_root=env.tmp/'upload-stage',
        default_part_size_bytes=65536,max_part_size_bytes=131072,max_upload_size_bytes=8*1024*1024)
    upload=await service.initialize(UploadInitRequest(project_id=env.project.project_id,filename='supplied.bin',
        media_kind=kind,content_type=mime,size_bytes=len(raw),checksum_sha256=sha,part_size_bytes=65536,
        rights_status=rights,license='explicit-first-party-generated-test-media' if rights=='owned' else 'user-provided'))
    for part in range(1,upload.total_parts+1):
        data=raw[(part-1)*65536:part*65536]
        await service.store_part(upload.upload_id,part,bytes_stream(data),expected_part_sha256=hashlib.sha256(data).hexdigest())
    completed=await service.complete(upload.upload_id,UploadCompleteRequest(checksum_sha256=sha))
    return await env.assets.get_asset(completed.asset_id),completed.media_metadata

async def uploaded(env,*,audio=False,boundary=False,mixed=False,reviewed_audio=False,async_video=False,flac=False):
    ffmpeg=shutil.which('ffmpeg');assert ffmpeg,'Owned real media test requires FFmpeg'
    path=env.tmp/'owned-source.mp4'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=c=blue:s=320x240:r=24:d=3',
        '-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(path)],check=True,timeout=30)
    # Only this first-party generated source receives a fixture rights decision.
    # Derived assets still receive unknown rights and no inherited approval.
    asset,media=await ingest(env,path,'video','video/mp4',rights='owned' if mixed else 'unknown')
    request=AutoEditAnalysisRequest(asset_id=asset.asset_id)
    analysis,_=await env.assets.create_analysis(project_id=env.project.project_id,asset=asset,fingerprint=digest(['explicit-saved-fixture',asset.checksum_sha256]),
        configuration=request,source_media=media,provenance={'fixture':True,'source_asset_checksum':asset.checksum_sha256,'provider_calls':0})
    transcript=ProviderTranscript(language='vi',confidence=None,segments=(ProviderSegment(.1,1.,'Xin chào.',None,None,
        (ProviderWord(.1,.4,'Xin',.9),ProviderWord(.4,1.,'chào.',.8))),),
        provenance={'fixture':True,'raw_model_result':{'source_project_id':env.project.project_id,'raw_words':[.1,.4,1.]},'original_evidence':True})
    projected=require_positive_duration_transcript(transcript)
    if boundary:
        from app.asr_derived_timing import derive_positive_duration_transcript
        raw=ProviderTranscript(language='vi',confidence=None,segments=(ProviderSegment(.1,1.,'Xin chào.',None,None,
            (ProviderWord(.1,.1,'Xin',None,timing_semantics='provider_boundary_point'),ProviderWord(.1,1.,'chào.',None))),),provenance={'fixture':True})
        projected=derive_positive_duration_transcript(raw)
    await env.assets.save_analysis_results(analysis_id=analysis,asset_id=asset.asset_id,provider_key='explicit-saved-asr-fixture',
        transcript=projected,scenes=[dict(ordinal=0,start_seconds=0.,end_seconds=3.,semantic_label='Owned test color',
            description='Explicit scene fixture',subjects=[],quality_score=.7,motion_score=.1,speech_score=.3,confidence=.5,evidence={'fixture':True})],
        silence_decisions=[dict(start_seconds=1.3,end_seconds=1.8,padding_before_seconds=.08,padding_after_seconds=.08,enabled=False,
            reason='Explicit silence fixture',conflicts_with_speech=False,evidence={'fixture':True})],
        highlights=[dict(scene_ordinal=0,rank=1,highlight_score=.6,reason='Explicit highlight fixture',recommended_start=0.,recommended_end=2.,
            recommended_platform='youtube_shorts',evidence={'fixture':True})])
    built=await env.service.create(env.project.project_id,TimelineCreateRequest(analysis_id=analysis))
    if mixed:
        from test_mvp1_multi_input import author,timeline
        from app.content_models import StoryboardScene
        version=await author(env,scenes=[StoryboardScene(scene_id='scene_mixed_fixture',narration='Cảnh video đã có.',
            media_strategy='user_asset',asset_id=asset.asset_id,analysis_id=analysis,source_start=0.,duration_seconds=2.)])
        built=await timeline(env,version,kind='mixed',expected=1)
    if audio:await saved_audio(env,built,reviewed=reviewed_audio,flac=flac)
    if async_video:await saved_video_job(env,analysis,asset,request)
    families=SqlVariantFamilyRepository(env.factory);available=await families.availability(env.workspace.workspace_id,env.project.project_id)
    payload=FamilyReserveRequest(expected_project_version=available.binding.project_version,expected_timeline_version=available.binding.timeline_version,
        expected_timeline_version_id=available.binding.timeline_version_id,expected_binding_sha256=available.binding_sha256,
        catalog_ref=available.catalog.catalog_ref,catalog_sha256=available.catalog_sha256,profile_refs=[p.profile_ref for p in available.catalog.profiles],
        request_key='saved-uploaded-family-fixture',acknowledge_draft_derivation=True)
    family,_=await families.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    repo=SqlUploadedDerivationRepository(families);copier=LocalEvidenceCopier(env.storage)
    return families,family,repo,SqlStoryboardDerivationService(repo,copier),analysis

async def saved_video_job(env,analysis,asset,configuration):
    """Explicit historic job fixture; uses real source/custody FKs, no worker."""
    from app.auto_edit_job_db import AutoEditJobORM
    from app.auto_edit_job_repository import immutable
    from app.auto_edit_source_custody import trusted_video_snapshot
    from app.models import AutoEditAnalysisJobInput
    source=await trusted_video_snapshot(env.assets,env.project.project_id,asset.asset_id,'local',1024*1024)
    provider={'fixture':True,'provider_key':'explicit-saved-asr-fixture','max_source_bytes':1024*1024,'paid':False,'external_call':False}
    request=AutoEditAnalysisJobInput(analysis_id=analysis,source_sha256=asset.checksum_sha256,
        provider_binding_sha256=digest(provider),actor_ref='fixture-editor').model_dump(mode='json')
    relation=AutoEditJobORM(relation_id='vre_'+digest(analysis)[:24],analysis_id=analysis,job_id='job_saved_video_fixture',
        workspace_id=env.workspace.workspace_id,project_id=env.project.project_id,source_json=source,
        configuration_json=configuration.model_dump(mode='json'),provider_json=provider,actor_ref='fixture-editor',request_json=request)
    relation.custody_sha256=digest(immutable(relation))
    async with env.factory() as session,session.begin():
        session.add(JobORM(job_id=relation.job_id,workspace_id=env.workspace.workspace_id,project_id=env.project.project_id,
            status='awaiting_review',stage='awaiting_review',progress=100,request_json=request,artifacts_json=[]));await session.flush()
        session.add(relation)

async def saved_audio(env,built,*,reviewed=False,flac=False):
    from app.uploaded_audio_service import normalize_evidence
    from app.uploaded_audio_timeline import apply
    from app.uploaded_audio_models import AudioCaptionApply
    path=env.tmp/'owned-audio.wav'
    with wave.open(str(path),'wb') as sound:
        sound.setnchannels(1);sound.setsampwidth(2);sound.setframerate(16000);sound.writeframes(b'\0\0'*32000)
    if flac:
        encoded=env.tmp/'owned-audio.flac'
        subprocess.run([shutil.which('ffmpeg'),'-v','error','-i',str(path),'-c:a','flac',str(encoded)],check=True,timeout=30)
        path=encoded
    asset,media=await ingest(env,path,'audio','audio/flac' if flac else 'audio/wav')
    audio='aud_'+digest(asset.asset_id)[:24];job='job_saved_audio_fixture'
    evidence={'language':'vi','confidence':None,'segments':[dict(start_seconds=.1,end_seconds=.9,text='Âm thanh.',speaker=None,confidence=None,
        words=[dict(start_seconds=.1,end_seconds=.4,text='Âm',confidence=.9),dict(start_seconds=.4,end_seconds=.9,text='thanh.',confidence=.8)])],
        'provenance':{'fixture':True,'raw_provider_result':{'original_project_id':env.project.project_id}},'actual_cost_vnd':None}
    parent=UploadedAudioORM(audio_id=audio,workspace_id=env.workspace.workspace_id,project_id=env.project.project_id,asset_id=asset.asset_id,
        job_id=job,source_sha256=asset.checksum_sha256,source_size_bytes=asset.size_bytes,request_key_sha256=digest('saved-fixture'),request_sha256=digest('saved-fixture-body'),
        configuration_json={'provider':{'provider_key':'explicit-saved-asr-fixture'}},media_metadata_json=media.model_dump(mode='json'),
        original_evidence_json=evidence,original_evidence_sha256=digest(evidence),current_version=1)
    first=normalize_evidence(evidence,parent,created_at=utc_now());body=first.model_dump(mode='json')
    current=first
    if reviewed:
        from app.transcript_word_review import revised,WordReview
        segment=first.segments[0]
        current=revised(first,WordReview(expected_version=1,expected_transcript_id=first.transcript_id,acknowledged=True,
            segments=[dict(segment_id=segment.segment_id,start_seconds=.1,end_seconds=.9,words=[dict(word_id=w.word_id,text=w.text,
                start_seconds=w.start_seconds,end_seconds=w.end_seconds) for w in segment.words])]),duration=2.,actor_ref='fixture-editor')
        parent.current_version=2
    async with env.factory() as session,session.begin():
        session.add(JobORM(job_id=job,workspace_id=env.workspace.workspace_id,project_id=env.project.project_id,status='awaiting_review',stage='awaiting_review',progress=100,
            request_json={'kind':'uploaded_audio_transcription','audio_id':audio,'source_sha256':asset.checksum_sha256,'provider_binding_sha256':digest(parent.configuration_json['provider']),
                'actor_ref':'fixture-editor'},artifacts_json=[]));await session.flush()
        session.add(parent);await session.flush()
        session.add(UploadedAudioVersionORM(transcript_id=first.transcript_id,audio_id=audio,version=1,transcript_json=body,transcript_sha256=digest(body),actor_ref='fixture-editor'))
        if reviewed:
            updated=current.model_dump(mode='json')
            session.add(UploadedAudioVersionORM(transcript_id=current.transcript_id,audio_id=audio,version=2,
                transcript_json=updated,transcript_sha256=digest(updated),actor_ref='fixture-editor'))
        row=await session.get(TimelineVersionORM,built.current_version_id)
        selected=built.snapshot.model_copy(deep=True)
        # Explicit fixture decision: retain video captions disabled, review uploaded narration instead.
        for track in selected.tracks:
            if track.kind=='subtitles':track.disabled=True
        updated,_=apply(selected,current,AudioCaptionApply(source_sha256=asset.checksum_sha256,expected_transcript_id=current.transcript_id,
            expected_version=current.version,acknowledged=True,idempotency_key='explicit-saved-audio-binding',mute_original=True,
            expected_timeline_version=1,source_start=0.,source_end=2.,timeline_start=0.,speed=1.),source_duration=2.)
        row.snapshot_json=updated.model_dump(mode='json')

def request(family,member=None,key='explicit-uploaded-derivation'):
    return DeriveUploadedRequest(expected_version=family.version,expected_snapshot_sha256=family.snapshot_sha256,
        member_id=(member or family.members[0]).member_id,request_key=key,acknowledge_unapproved_child=True)

async def original_rows(env):
    async with env.factory() as session:
        result={}
        for model in (VideoProjectORM,AssetORM,TimelineORM,TimelineVersionORM,AutoEditAnalysisORM,TranscriptORM,TranscriptWordORM,
            UploadedAudioORM,UploadedAudioVersionORM,UploadSessionORM,JobORM):
            condition=model.project_id==env.project.project_id if hasattr(model,'project_id') else True
            records=(await session.scalars(select(model).where(condition).order_by(*model.__table__.primary_key.columns))).all()
            result[model.__tablename__]=canonical([record_value(row) for row in records])
        return result

@pytest.mark.asyncio
async def test_real_owned_video_derives_six_exact_independent_graphs_and_canonical_reviews(env):
    families,family,repo,service,analysis=await uploaded(env)
    source=await env.assets.get_analysis(analysis);children=[]
    original=await original_rows(env)
    for index,member in enumerate(family.members):
        current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
        result,replay=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(current,member,f'explicit-uploaded-{index}'),actor_ref='fixture-editor')
        assert result.state=='ready' and not replay and result.safety.provider_calls==0
        children.append(result.result['child_project_id']);child=await env.timeline.get_timeline(children[-1])
        assert child.approval_status=='draft' and child.approved_timeline_version is None and child.latest_preview_id is None
        assert child.source_analysis_id==result.result['identity_map'][analysis] and child.source_content_version_id is None
        imported=await env.assets.get_analysis(child.source_analysis_id)
        assert imported.configuration.asset_id==imported.asset_id
        assert imported.transcript.analysis_id==child.source_analysis_id
        for a,b in zip(source.transcript.segments,imported.transcript.segments):
            assert re.fullmatch(r'seg_[a-f0-9]{24}',b.segment_id)
            assert (a.text,a.start_seconds,a.end_seconds,a.confidence)==(b.text,b.start_seconds,b.end_seconds,b.confidence)
            assert [(w.text,w.start_seconds,w.end_seconds,w.confidence) for w in a.words]==[(w.text,w.start_seconds,w.end_seconds,w.confidence) for w in b.words]
            assert all(re.fullmatch(r'wrd_[a-f0-9]{24}',w.word_id) for w in b.words)
        assert imported.provenance['original_record']['provenance_json']==source.provenance
        assert child.snapshot.metadata['transcript_revision']['transcript_id']==imported.transcript.transcript_id
        for old,new in result.result['asset_map'].items():
            a=await env.assets.get_asset(old);b=await env.assets.get_asset(new)
            assert a.object_key!=b.object_key and env.storage._path(a.object_key).read_bytes()==env.storage._path(b.object_key).read_bytes()
            assert env.storage._path(a.object_key).stat().st_ino!=env.storage._path(b.object_key).stat().st_ino
            assert b.provenance['rights_status']=='unknown'
            async with env.factory() as session:
                project=await session.get(VideoProjectORM,b.project_id);asset=await session.get(AssetORM,new)
                _,custody=await trusted_derivative_source(session,project,asset)
                assert custody['new_scan_claimed'] is False
    assert len(set(children))==6
    # Only transcript/word rows are global here; original IDs retain their exact values.
    after=await original_rows(env)
    for table in ('video_projects','assets','timeline_versions','auto_edit_analyses','upload_sessions','jobs'):assert after[table]==original[table]
    async with env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(UploadSessionORM))==1
        assert await session.scalar(select(func.count()).select_from(JobORM))==0
        assert await session.scalar(select(func.count()).select_from(ProductionApprovalORM))==0

@pytest.mark.asyncio
async def test_saved_uploaded_audio_has_independent_parent_history_and_zero_dispatch_audit(env):
    families,family,repo,service,analysis=await uploaded(env,audio=True)
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    child=result.result['child_project_id'];timeline=await env.timeline.get_timeline(child)
    async with env.factory() as session:
        parent=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==env.project.project_id))
        imported=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==child))
        assert imported.job_id!=parent.job_id and imported.asset_id!=parent.asset_id
        assert imported.original_evidence_json==parent.original_evidence_json and imported.original_evidence_sha256==parent.original_evidence_sha256
        job=await session.get(JobORM,imported.job_id)
        assert job.status=='awaiting_review' and job.request_json['kind']=='variant_evidence_import' and job.request_json['provider_calls']==0
        assert imported.claim_id is None and imported.lease_expires_at is None
        version=await session.scalar(select(UploadedAudioVersionORM).where(UploadedAudioVersionORM.audio_id==imported.audio_id))
        binding=timeline.snapshot.metadata['uploaded_audio_bindings_v1'][imported.audio_id]
        assert binding['transcript']==version.transcript_json and binding['transcript_sha256']==version.transcript_sha256
        from app.uploaded_audio_repository import UploadedAudioRepository
        assert len(await UploadedAudioRepository(env.factory).versions(session,imported))==1
        assert await session.scalar(select(func.count()).select_from(UploadSessionORM))==2
    replay,replayed=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    assert replayed and replay==result

@pytest.mark.asyncio
async def test_child_word_review_uses_existing_canonical_engine_and_preserves_originals(env):
    from app.transcript_word_editing import edit_transcript_words
    from app.transcript_word_review import WordReview
    families,family,repo,service,analysis=await uploaded(env)
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    child=result.result['child_project_id'];imported=await env.assets.get_analysis(result.result['identity_map'][analysis])
    base=imported.transcript;segment=base.segments[0]
    payload=WordReview(expected_version=base.version,expected_transcript_id=base.transcript_id,expected_timeline_version=1,acknowledged=True,
        segments=[dict(segment_id=segment.segment_id,start_seconds=segment.start_seconds,end_seconds=segment.end_seconds,
            words=[dict(word_id=w.word_id,text=('Chào' if i==0 else w.text),start_seconds=w.start_seconds,end_seconds=w.end_seconds) for i,w in enumerate(segment.words)])])
    revised=await edit_transcript_words(env.assets,child,imported.analysis_id,payload,'fixture-editor')
    assert revised.transcript.version==2
    changed=await env.timeline.get_timeline(child)
    assert changed.current_version==2 and changed.approval_status=='draft'
    assert changed.snapshot.metadata['transcript_revision']['transcript_id']==revised.transcript.transcript_id
    assert (await env.assets.get_analysis(analysis)).transcript.version==1
    assert (await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)).source_current
    async with env.factory() as session:
        original=await session.get(TranscriptORM,base.transcript_id)
        assert original.is_original_evidence and original.provenance_json['new_inference_calls']==0

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['word','asset_key','origin_scan','raw_audio','audit_job'])
async def test_rehashed_or_foreign_import_metadata_cannot_launder_ready_receipt(env,change):
    families,family,repo,service,analysis=await uploaded(env,audio=change in {'raw_audio','audit_job'})
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    child=result.result['child_project_id']
    async with env.factory() as session,session.begin():
        if change=='word':
            word=await session.scalar(select(TranscriptWordORM).where(TranscriptWordORM.word_id.in_(list(result.result['identity_map'].values()))))
            word.start_seconds+=.01
        elif change=='asset_key':
            asset=await session.get(AssetORM,next(iter(result.result['asset_map'].values())))
            asset.object_key=asset.object_key.replace('/projects/'+child+'/', '/projects/prj_foreign/')
        elif change=='origin_scan':
            upload=await session.scalar(select(UploadSessionORM).where(UploadSessionORM.project_id==env.project.project_id))
            upload.quarantine_state='rejected'
        elif change=='raw_audio':
            audio=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==child))
            changed=copy.deepcopy(audio.original_evidence_json);changed['segments'][0]['text']='Tampered raw'
            audio.original_evidence_json=changed;audio.original_evidence_sha256=digest(changed)
        else:
            audio=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==child))
            job=await session.get(JobORM,audio.job_id)
            changed=copy.deepcopy(job.request_json);changed['actor_ref']='fixture-other-editor'
            job.request_json=changed;audio.request_sha256=digest(changed)
    if change=='origin_scan':
        async with env.factory() as session:
            project=await session.get(VideoProjectORM,child);asset=await session.get(AssetORM,next(iter(result.result['asset_map'].values())))
            with pytest.raises(ValueError,match='CUSTODY_CHANGED'):await trusted_derivative_source(session,project,asset)
    else:
        with pytest.raises(SqlVariantError,match='EVIDENCE_CHANGED'):
            await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)

@pytest.mark.asyncio
async def test_raw_boundary_points_and_separate_positive_projection_are_not_rewritten(env):
    families,family,repo,service,analysis=await uploaded(env,boundary=True)
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    mapped=result.result['identity_map'];child_analysis=mapped[analysis]
    async with env.factory() as session:
        master=(await session.scalars(select(TranscriptORM).where(TranscriptORM.analysis_id==analysis).order_by(TranscriptORM.version))).all()
        child=(await session.scalars(select(TranscriptORM).where(TranscriptORM.analysis_id==child_analysis).order_by(TranscriptORM.version))).all()
        assert len(master)==len(child)==2 and child[0].is_original_evidence and not child[1].is_original_evidence
        for a,b in zip(master,child):
            words=(await session.scalars(select(TranscriptWordORM).where(TranscriptWordORM.transcript_id==a.transcript_id).order_by(TranscriptWordORM.ordinal))).all()
            derived=(await session.scalars(select(TranscriptWordORM).where(TranscriptWordORM.transcript_id==b.transcript_id).order_by(TranscriptWordORM.ordinal))).all()
            assert [(w.text,w.start_seconds,w.end_seconds,w.confidence) for w in words]==[(w.text,w.start_seconds,w.end_seconds,w.confidence) for w in derived]
            assert b.provenance_json['inherited_original_provenance']==a.provenance_json
        raw=await session.scalar(select(TranscriptWordORM).where(TranscriptWordORM.transcript_id==child[0].transcript_id).order_by(TranscriptWordORM.ordinal))
        assert raw.start_seconds==raw.end_seconds==.1
    selected=await env.assets.get_analysis(child_analysis)
    assert selected.transcript.version==2
    canonical_child=await env.timeline.get_timeline(result.result['child_project_id'])
    assert canonical_child.snapshot.metadata['transcript_revision']['transcript_id']==selected.transcript.transcript_id

@pytest.mark.asyncio
async def test_mixed_storyboard_child_keeps_content_draft_and_analysis_clocks_independent(env):
    families,family,repo,service,analysis=await uploaded(env,mixed=True)
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    version=await env.platform.get_version(result.result['content_version_id'])
    assert version.snapshot['content']['approved'] is False
    scene=version.snapshot['content']['scenes'][0]
    assert scene['analysis_id']==result.result['identity_map'][analysis]
    assert scene['asset_id'] in result.result['asset_map'].values()
    child=await env.timeline.get_timeline(result.result['child_project_id'])
    assert child.source_analysis_id is None and child.source_content_version_id==version.project_version_id
    assert child.source_kind=='mixed' and child.snapshot.metadata['source_kind']=='mixed'
    assert child.snapshot.tracks[0].clips[0].source_start==0. and child.snapshot.tracks[0].clips[0].source_end==2.

@pytest.mark.asyncio
async def test_reviewed_audio_history_maps_keys_values_and_selected_snapshot_without_raw_changes(env):
    families,family,repo,service,analysis=await uploaded(env,audio=True,reviewed_audio=True)
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    async with env.factory() as session:
        parent=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==env.project.project_id))
        child=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==result.result['child_project_id']))
        from app.uploaded_audio_repository import UploadedAudioRepository
        originals=await UploadedAudioRepository(env.factory).versions(session,parent)
        derived=await UploadedAudioRepository(env.factory).versions(session,child)
        assert len(originals)==len(derived)==2
        mapping=result.result['identity_map'];old=originals[1];new=derived[1]
        assert new.provenance['derived_from_transcript_id']==derived[0].transcript_id
        assert new.provenance['segment_id_mapping']=={mapping[k]:mapping[v] for k,v in old.provenance['segment_id_mapping'].items()}
        assert new.provenance['reviewed_segment_ids']==[mapping[s] for s in old.provenance['reviewed_segment_ids']]
        assert child.original_evidence_json==parent.original_evidence_json
        assert [[(w.text,w.start_seconds,w.end_seconds,w.confidence) for s in t.segments for w in s.words] for t in originals]==[
            [(w.text,w.start_seconds,w.end_seconds,w.confidence) for s in t.segments for w in s.words] for t in derived]
    canonical_child=await env.timeline.get_timeline(result.result['child_project_id'])
    binding=canonical_child.snapshot.metadata['uploaded_audio_bindings_v1'][child.audio_id]
    assert binding['transcript']==new.model_dump(mode='json') and binding['transcript_sha256']==digest(binding['transcript'])

@pytest.mark.asyncio
async def test_concurrent_replay_and_family_cancel_never_create_child_or_dispatch_again(env):
    from test_sql_variant_storyboard_derivation import PausedCopier
    families,family,repo,service,analysis=await uploaded(env)
    paused=PausedCopier(service.copier);service=SqlStoryboardDerivationService(repo,paused);payload=request(family)
    running=asyncio.create_task(service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,payload,actor_ref='fixture-editor'))
    await asyncio.wait_for(paused.entered.wait(),10)
    current,replayed=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,payload,actor_ref='fixture-editor')
    assert replayed and current.state=='pending' and paused.calls==1
    family=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    await families.cancel(env.workspace.workspace_id,env.project.project_id,family.family_id,
        FamilyVersionRequest(expected_version=family.version,expected_snapshot_sha256=family.snapshot_sha256,request_key='explicit-import-cancel'),actor_ref='fixture-editor')
    paused.release.set()
    with pytest.raises(SqlVariantError,match='CONFLICT'):await running
    observed,replayed=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,payload,actor_ref='fixture-editor')
    assert replayed and observed.state=='cancelled' and paused.calls==1
    async with env.factory() as session:
        assert await session.get(VideoProjectORM,family.members[0].planned_project_id) is None
        assert await session.scalar(select(func.count()).select_from(JobORM))==0

@pytest.mark.asyncio
async def test_expired_actual_child_flush_rolls_back_entire_import_and_holds_orphans(env,monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    families,family,repo,service,analysis=await uploaded(env)
    repo.lease_seconds=5;original=AsyncSession.flush;delayed=False
    async def slow(session,*args,**kwargs):
        nonlocal delayed
        child=any(isinstance(row,VideoProjectORM) and row.project_id==family.members[0].planned_project_id for row in session.new)
        await original(session,*args,**kwargs)
        if child and not delayed:
            delayed=True;await asyncio.sleep(5.5)
    monkeypatch.setattr(AsyncSession,'flush',slow)
    with pytest.raises(SqlVariantError,match='LEASE_EXPIRED'):
        await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    assert delayed
    async with env.factory() as session:
        receipt=await session.scalar(select(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.kind=='uploaded_evidence_derivation'))
        assert receipt.state=='unknown' and receipt.error_code=='SQL_VARIANT_DERIVATION_LEASE_EXPIRED'
        assert await session.get(VideoProjectORM,family.members[0].planned_project_id) is None
        assert await session.scalar(select(func.count()).select_from(JobORM))==0
    replay,replayed=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    assert replayed and replay.state=='unknown'

@pytest.mark.asyncio
async def test_late_bytes_after_terminal_sql_flush_roll_back_ready_events_and_graph(env,monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    families,family,repo,service,analysis=await uploaded(env)
    original=AsyncSession.flush;mutated=False
    async def change(session,*args,**kwargs):
        nonlocal mutated
        receipt=next((r for r in session.identity_map.values() if isinstance(r,SqlVariantArtifactReceiptORM)
            and r.kind=='uploaded_evidence_derivation' and r.state=='ready'),None)
        await original(session,*args,**kwargs)
        if receipt and not mutated:
            mutated=True;item=next(iter(receipt.result_json['copies'].values()));path=env.storage._path(item['object_key'])
            raw=bytearray(path.read_bytes());raw[-1]^=1;path.write_bytes(raw)
    monkeypatch.setattr(AsyncSession,'flush',change)
    with pytest.raises(SqlVariantError,match='COPY_RESULT_CHANGED'):
        await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    assert mutated
    async with env.factory() as session:
        receipt=await session.scalar(select(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.kind=='uploaded_evidence_derivation'))
        assert receipt.state=='unknown' and receipt.result_json is None
        assert await session.get(VideoProjectORM,family.members[0].planned_project_id) is None
        assert await session.scalar(select(func.count()).select_from(AutoEditAnalysisORM))==1
    current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
    assert current.state=='recovery_required' and current.version==3 and current.safety.child_projects_created==0
