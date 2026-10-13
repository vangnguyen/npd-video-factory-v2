"""Owned SQL variant/source-audio real render rehearsal; no ASR/TTS/publishing.

Fixture scene/transcript and approval decisions are explicit test data. Actual
FFmpeg/Remotion media and FullProductionQC results never imply Owner UAT.
Existing renderer source/dependencies are read-only; media serving is private
owned loopback only. All roots, originals, failed outputs and evidence retained.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import uuid
import zipfile

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'apps/api'),str(REPO/'apps/api/tests')]

from sqlalchemy import select
from app.db import Base
from app.auto_edit_models import AutoEditAnalysisRequest
from app.auto_edit_providers import ProviderTranscript,ProviderSegment,ProviderWord,require_positive_duration_transcript
from app.content_models import StoryboardScene
from app.timeline_models import TimelineCreateRequest
from app.production_models import (ProductionPackageCreateRequest,AudioMixReplaceRequest,MixConfig,
    VoiceConfig,RenderCreateRequest,FinalRenderCreateRequest,ApprovalRequest,ApprovalDecisionRequest)
from app.production_audio import AudioMixEngine
from app.production_service import ProductionRenderProcessor
from app.production_logic import TimelineRenderContractValidator
from app.production_qc import FullProductionQC
from app.sql_variant_models import FamilyReserveRequest,digest,canonical
from app.sql_variant_repository import SqlVariantFamilyRepository,record_value
from app.sql_variant_uploaded_repository import SqlUploadedDerivationRepository
from app.sql_variant_uploaded_copy import LocalEvidenceCopier
from app.sql_variant_uploaded_models import DeriveUploadedRequest
from app.sql_variant_derivation_service import SqlStoryboardDerivationService
from app.object_storage import LocalObjectStorageProvider
from app.auto_edit_repository import AutoEditRepository
from app.timeline_repository import TimelineRepository
from app.production_repository import ProductionRepository
from app.repositories import PlatformRepository
from app.db import create_engine,create_session_factory
from test_sql_variant_family import env as owned_environment
from test_sql_variant_uploaded_derivation import ingest
from test_mvp1_multi_input import author,timeline

ACTOR='fixture-editor-no-owner-uat'
REVIEWER='fixture-reviewer-no-human-listening-claim'
RENDERER_FILES=['app.ts','engine.ts','native-job-render.ts','native-job-cli.ts','contract.ts','types.ts',
    'index.ts','Root.tsx','TimelineRender.tsx','VerticalShort.tsx','subtitles.ts','reframe.ts']


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8',newline='\n') as out:
        out.write(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')


def plain(path):
    path=Path(path)
    if not path.is_absolute():raise ValueError('S6_ABSOLUTE_PATH_REQUIRED')
    for item in (path,*path.parents):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise ValueError('S6_REPARSE_OR_LINK_REJECTED')
    return path.resolve()


def owned_root(path):
    path=Path(path)
    parent=plain(Path('C:/vfct'))
    if path.parent.resolve()!=parent or not re.fullmatch(r'vsrender-[a-f0-9]{8}',path.name) or path.exists():
        raise ValueError('S6_NEW_OWNED_ROOT_REQUIRED')
    path.mkdir(exist_ok=False)
    plain(path)
    write(path/'ownership.json',dict(schema_version='sql-variant-source-render-owned-root.v1',
        fixture=True,production=False,root=str(path),delete_requested=False))
    return path


def renderer_preflight(renderer_root):
    root=plain(renderer_root)
    if root!=Path('C:/vfns01/renderer').resolve():raise ValueError('S6_PINNED_EXISTING_RENDERER_ROOT_REQUIRED')
    code={}
    for name in RENDERER_FILES:
        current=root/'src'/name;expected=REPO/'renderer/src'/name
        if sha(current)!=sha(expected):raise ValueError('S6_RENDERER_SOURCE_MISMATCH')
        code[name]=sha(current)
    for name in ('package.json','package-lock.json'):
        if sha(root/name)!=sha(REPO/'renderer'/name):raise ValueError('S6_RENDERER_DEPENDENCY_LOCK_MISMATCH')
        code[name]=sha(root/name)
    chrome=root/'node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe'
    loader=root/'node_modules/tsx/dist/loader.mjs'
    plain(chrome);plain(loader)
    installed={name:json.loads((root/'node_modules'/name/'package.json').read_text())['version']
               for name in ('@remotion/renderer','@remotion/bundler','remotion')}
    expected=json.loads((root/'package.json').read_text())['dependencies']['@remotion/renderer']
    if any(value!=expected for value in installed.values()):raise ValueError('S6_INSTALLED_REMOTION_VERSION_MISMATCH')
    return dict(source_sha256=code,root=str(root),loader=str(loader),
        browser_existing=True,browser_bytes=chrome.stat().st_size,
        dependency_version=expected,installed_versions=installed)


class NoTTS:
    def __init__(self):self.calls=0
    async def synthesize(self,*args,**kwargs):
        self.calls+=1;raise AssertionError('S6_NO_TTS_PROVIDER_DISPATCH_ALLOWED')


class PrivateLocalRenderer:
    """Orchestration adapter around exact existing private Remotion job engine."""
    def __init__(self,*,renderer_root,receipt_root):
        self.root=Path(renderer_root);self.receipt_root=Path(receipt_root);self.calls=0;self.completed=0
    async def render(self,*,render_id,manifest_path,output_path,is_cancelled):
        if await is_cancelled():raise RuntimeError('S6_CANCELLED_BEFORE_RENDER')
        work=plain(Path(manifest_path).parent)
        job=work/'private-remotion-job';job.mkdir(exist_ok=False)
        media=job/'media';media.mkdir(exist_ok=False)
        manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
        changed=copy.deepcopy(manifest);sources={};index=0
        def stage(value,extension):
            nonlocal index
            original=plain(Path(value))
            if work not in original.parents or original.stat().st_nlink!=1:
                raise ValueError('S6_PRIVATE_MEDIA_SCOPE_INVALID')
            if value not in sources:
                destination=media/f'media-{index:03d}{extension}';index+=1
                with original.open('rb') as source,destination.open('xb') as target:shutil.copyfileobj(source,target,1024*1024)
                if sha(original)!=sha(destination):raise ValueError('S6_PRIVATE_MEDIA_COPY_CHANGED')
                sources[value]=str(destination)
            return sources[value]
        changed['audio']['mix_uri']=stage(manifest['audio']['mix_uri'],'.wav')
        for clip in changed['visual_clips']:
            clip['uri']=stage(clip['uri'],'.mp4' if clip['type']=='video' else '.png')
        write(job/'timeline-render.json',changed)
        self.calls+=1
        command=[shutil.which('node'),'--import',(self.root/'node_modules/tsx/dist/loader.mjs').as_uri(),
                 str(self.root/'src/native-job-cli.ts'),str(job)]
        process=await asyncio.create_subprocess_exec(*command,cwd=self.root,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        try:
            stdout,stderr=await asyncio.wait_for(process.communicate(),180)
        except BaseException:
            if process.returncode is None:process.kill()
            await asyncio.shield(process.wait())
            raise
        log=self.receipt_root/f'{render_id}-renderer.json'
        events=[]
        for line in stdout.decode('utf-8','replace').splitlines():
            try:events.append(json.loads(line))
            except ValueError:raise RuntimeError('S6_RENDERER_NON_JSON_DIAGNOSTIC') from None
        write(log,dict(exit_code=process.returncode,events=events,
            stderr=stderr.decode('utf-8','replace'),owned_process_pid=process.pid,
            local_loopback_only=True,external_network_calls=0))
        if process.returncode!=0:raise RuntimeError('S6_LOCAL_REMOTION_FAILED')
        result=json.loads((job/'renderer-receipt.json').read_text())
        if result['fixture'] is not False or result['status']!='success':raise RuntimeError('S6_REAL_RENDER_RECEIPT_REQUIRED')
        self.completed+=1
        if await is_cancelled():raise RuntimeError('S6_CANCELLED_AFTER_RENDER')
        rendered=plain(job/'final.mp4')
        with rendered.open('rb') as source,Path(output_path).open('xb') as target:shutil.copyfileobj(source,target,1024*1024)
        if sha(rendered)!=sha(output_path):raise RuntimeError('S6_RENDERED_COPY_CHANGED')
        return {**result,'output_path':str(output_path),'local_loopback_only':True,'external_network_calls':0}


async def make_source(env,mode):
    source=env.tmp/'owned-motion-tone.mp4'
    subprocess.run([shutil.which('ffmpeg'),'-v','error','-f','lavfi','-i','testsrc2=s=640x360:r=30:d=2.4',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2.4','-af','volume=0.4',
        '-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True,timeout=30)
    asset,metadata=await ingest(env,source,'video','video/mp4')
    config=AutoEditAnalysisRequest(asset_id=asset.asset_id)
    analysis,_=await env.assets.create_analysis(project_id=env.project.project_id,asset=asset,
        fingerprint=digest(['owned-tone-schema-fixture',asset.checksum_sha256]),configuration=config,
        source_media=metadata,provenance={'fixture':True,'provider_calls':0,'real_asr':False,
            'source_asset_checksum':asset.checksum_sha256,'speech_recognition_claimed':False})
    transcript=ProviderTranscript(language='vi',confidence=None,
        segments=(ProviderSegment(.2,2.1,'Nguồn thử',None,None,
            (ProviderWord(.2,1.1,'Nguồn',None),ProviderWord(1.1,2.1,'thử',None))),),
        provenance={'fixture':True,'manually_supplied_caption_clock':True,'real_asr':False,
            'raw_provider_result':{'fixture':True,'provider_calls':0,'speech_not_inferred':True}})
    await env.assets.save_analysis_results(analysis_id=analysis,asset_id=asset.asset_id,
        provider_key='explicit-caption-scene-fixture-no-asr',transcript=require_positive_duration_transcript(transcript),
        scenes=[dict(ordinal=0,start_seconds=0.,end_seconds=2.4,semantic_label='Owned moving test pattern',
            description='Manual scene fixture; no Vision analysis.',subjects=[],quality_score=0.,motion_score=0.,
            speech_score=0.,confidence=0.,evidence={'fixture':True,'provider_calls':0})],
        silence_decisions=[],highlights=[],signal_evidence={'fixture':True,'actual_signal_analysis_claimed':False})
    built=await env.service.create(env.project.project_id,TimelineCreateRequest(analysis_id=analysis,actor_ref=ACTOR))
    if mode=='mixed':
        content=await author(env,[StoryboardScene(scene_id='scene_owned_tone',narration='Nguồn thử',
            media_strategy='user_asset',asset_id=asset.asset_id,analysis_id=analysis,source_start=0.,duration_seconds=2.4,
            original_audio='keep')],original='Explicit manually supplied synthetic tone-caption fixture.')
        built=await timeline(env,content,kind='mixed',expected=built.current_version)
    assert any(t.kind=='original_audio' and not t.muted and t.clips for t in built.snapshot.tracks)
    return asset,analysis


async def rows(env):
    async with env.factory() as session:
        return {mapper.class_.__tablename__:[record_value(row) for row in
            (await session.scalars(select(mapper.class_).order_by(*mapper.class_.__table__.primary_key.columns))).all()]
            for mapper in Base.registry.mappers}


async def run_mode(args,root,mode,renderer):
    folder=root/mode;folder.mkdir(exist_ok=False)
    generator=owned_environment.__wrapped__(folder)
    env=await anext(generator)
    try:
        source,analysis=await make_source(env,mode)
        families=SqlVariantFamilyRepository(env.factory)
        available=await families.availability(env.workspace.workspace_id,env.project.project_id)
        refs=['youtube-landscape@1','youtube-shorts@1','social-square@1','social-feed@1'][:args.limit]
        reserve=FamilyReserveRequest(expected_project_version=available.binding.project_version,
            expected_timeline_version=available.binding.timeline_version,expected_timeline_version_id=available.binding.timeline_version_id,
            expected_binding_sha256=available.binding_sha256,catalog_ref=available.catalog.catalog_ref,
            catalog_sha256=available.catalog_sha256,profile_refs=refs,request_key='actual-local-source-family-'+mode,
            acknowledge_draft_derivation=True)
        family,_=await families.reserve(env.workspace.workspace_id,env.project.project_id,reserve,actor_ref=ACTOR)
        write(args.output/f'{mode}-family-reserved.json',family.model_dump(mode='json'))
        write(args.output/f'{mode}-source-analysis.json',(await env.assets.get_analysis(analysis)).model_dump(mode='json'))
        baseline=await rows(env)
        tts=NoTTS()
        processor=ProductionRenderProcessor(repository=env.production,platform=env.platform,asset_repository=env.assets,
            object_storage=env.storage,renderer=renderer,qc=FullProductionQC(),tts_provider=tts,audio_engine=AudioMixEngine(),
            manifest_validator=TimelineRenderContractValidator(REPO/'packages/contracts/timeline-render.schema.json'),
            staging_root=folder/'production-stage',brand_name='Owned SQL variant fixture')
        derivative=SqlStoryboardDerivationService(SqlUploadedDerivationRepository(families),LocalEvidenceCopier(env.storage))
        children=[]
        for member in family.members:
            current=await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)
            derived,_=await derivative.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,
                DeriveUploadedRequest(expected_version=current.version,expected_snapshot_sha256=current.snapshot_sha256,
                    member_id=member.member_id,request_key='owned-source-render-'+member.member_id,
                    acknowledge_unapproved_child=True),actor_ref=ACTOR)
            child=derived.result['child_project_id'];target=args.output/mode/member.profile.target;target.mkdir(parents=True,exist_ok=False)
            write(target/'derivation-receipt.json',derived.model_dump(mode='json'))
            package=await env.package.create_or_refresh(child,ProductionPackageCreateRequest(expected_timeline_version=1,actor_ref=ACTOR))
            package=await env.package.replace_audio_mix(child,AudioMixReplaceRequest(expected_timeline_version=1,
                expected_audio_version=package.audio_mix.version,config=MixConfig(voice=VoiceConfig(enabled=False),original_audio_gain_db=0.),
                actor_ref=ACTOR,reason='Fixture explicitly keeps original synthetic tone; TTS disabled.'))
            for kind,profile in [('review',member.profile.review_profile),('final',member.profile.final_profile)]:
                shared=dict(expected_timeline_version=1,expected_subtitle_version=package.subtitle.version,
                    expected_audio_version=package.audio_mix.version,profile=profile,actor_ref=ACTOR)
                if kind=='review':queued=await env.package.enqueue_review(child,RenderCreateRequest(**shared))
                else:queued=await env.package.enqueue_final(child,FinalRenderCreateRequest(**shared,approval_id=approval.approval_id))
                completed=await processor.process(queued.render_id)
                write(target/f'{kind}-render.json',completed.model_dump(mode='json'))
                if completed.status not in {'awaiting_review','ready'} or completed.qc_status!='passed':
                    raise RuntimeError(f'S6_{kind.upper()}_FAILED:{completed.error_code}')
                artifact=await env.assets.get_asset(completed.output_asset_id)
                with env.storage._path(artifact.object_key).open('rb') as original,(target/f'{kind}.mp4').open('xb') as output:
                    shutil.copyfileobj(original,output,1024*1024)
                assert sha(target/f'{kind}.mp4')==artifact.checksum_sha256
                write(target/f'{kind}-manifest.json',completed.manifest)
                write(target/f'{kind}-qc.json',completed.qc_report)
                if kind=='review':
                    pending=await env.package.request_approval(child,ApprovalRequest(review_render_id=queued.render_id,requester_ref=ACTOR))
                    approval=await env.package.decide_approval(child,pending.approval_id,ApprovalDecisionRequest(decision='approved',
                        reviewer_ref=REVIEWER,comment='AUTOMATED FIXTURE DECISION ONLY; no human listening, Owner UAT or rights override.'))
                    write(target/'fixture-approval.json',approval.model_dump(mode='json'))
            canonical_child=await env.timeline.get_timeline(child)
            write(target/'timeline.json',canonical_child.model_dump(mode='json'))
            write(target/'cost.json',[record_value_placeholder(c) for c in await env.platform.list_cost_records(child)])
            children.append(dict(project_id=child,profile=member.profile.model_dump(mode='json'),path=str(target),
                final_sha256=sha(target/'final.mp4'),review_sha256=sha(target/'review.mp4')))
            print(json.dumps(dict(event='owned_variant_render_completed',mode=mode,target=member.profile.target,
                tts_calls=tts.calls,owner_uat=False)),flush=True)
        assert tts.calls==0
        final=await rows(env)
        for table,records in baseline.items():
            if table.startswith('sql_variant_'):continue
            by_key={canonical(row):row for row in final[table]}
            assert all(canonical(row) in by_key for row in records),(table,'original SQL row changed')
        write(args.output/f'{mode}-sql-events-cost.json',final)
        result=dict(mode=mode,workspace_id=env.workspace.workspace_id,master_project_id=env.project.project_id,
            family_id=family.family_id,children=children,tts_calls=tts.calls,real_asr=False,provider_wire_calls=0,
            fixture_approval_only=True,owner_uat=False,originals_unchanged=True,source_sha256=source.checksum_sha256,
            master_source_current=(await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)).source_current)
        assert result['master_source_current']
        await env.engine.dispose()
        backup=args.output/f'{mode}-state.zip'
        snapshot_db=folder/'cold-backup.sqlite'
        with sqlite3.connect(folder/'dev.db') as original,sqlite3.connect(snapshot_db) as copied:original.backup(copied)
        with zipfile.ZipFile(backup,'x',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot_db,'dev.db')
            for path in sorted(env.storage.root.rglob('*')):
                if path.is_file():archive.write(path,'objects/'+path.relative_to(env.storage.root).as_posix())
            archive.writestr('fixture-configuration.json',json.dumps(result,sort_keys=True))
        result['backup_sha256']=sha(backup)
        write(args.output/f'{mode}-result.json',result)
        return result
    finally:
        await generator.aclose()


def record_value_placeholder(value):
    return value.model_dump(mode='json')


async def main_async(args):
    if os.getenv('MVP1_TEST_PG_URL'):raise ValueError('S6_SQLITE_OWNED_ONLY')
    root=owned_root(args.root);args.output=Path(args.output)
    if args.output.exists():raise ValueError('S6_NEW_EVIDENCE_DIRECTORY_REQUIRED')
    args.output.mkdir(parents=True,exist_ok=False)
    runtime=renderer_preflight(Path(args.renderer_root))
    core_paths=['apps/api/app/production_service.py','apps/api/app/production_repository.py','apps/api/app/production_audio.py',
        'apps/api/app/production_qc.py','apps/api/app/sql_tts_artifact_reuse.py','apps/api/app/sql_variant_uploaded_repository.py',
        'apps/api/app/sql_variant_uploaded_custody.py','apps/api/app/sql_variant_uploaded_identity.py',
        'scripts/north_star_sql_variant_source_render.py','packages/contracts/timeline-render.schema.json']
    source_stamp={name:sha(REPO/name) for name in core_paths}
    runtime['api_source_sha256']=source_stamp
    runtime['head']=subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,capture_output=True,text=True,check=True).stdout.strip()
    write(args.output/'runtime-source.json',runtime)
    renderer=PrivateLocalRenderer(renderer_root=args.renderer_root,receipt_root=args.output)
    results=[]
    try:
        for mode in (['video_analysis','mixed'] if args.mode=='both' else [args.mode]):
            results.append(await run_mode(args,root,mode,renderer))
        if source_stamp!={name:sha(REPO/name) for name in core_paths}:
            raise RuntimeError('S6_SOURCE_CHANGED_DURING_REHEARSAL')
        if renderer_preflight(Path(args.renderer_root))['source_sha256']!=runtime['source_sha256']:
            raise RuntimeError('S6_RENDERER_SOURCE_CHANGED_DURING_REHEARSAL')
        write(args.output/'program-result.json',dict(schema_version='sql-variant-source-local-render-evidence.v1',
            results=results,owned_root=str(root),local_renderer_attempts=renderer.calls,
            real_remotion_completed=renderer.completed,external_network_calls=0,
            provider_wire_calls=0,tts_calls=0,model_inferences=0,production_deployed=False,owner_uat=False,
            selected_four_geometry_only=True,full_six_target_acceptance=False,source_rights_not_inherited=True,
            caption_clock_fixture=True,source_media_clock_ffprobe_measured=True,
            real_provider_acceptance=False,cold_restore_executed=False))
    except BaseException as exc:
        write(args.output/'failure.json',dict(schema_version='sql-variant-source-local-render-failure.v1',
            error_type=type(exc).__name__,reason=str(exc),owned_root=str(root),local_renderer_attempts=renderer.calls,
            real_remotion_completed=renderer.completed,
            partial_results=results,owner_uat=False,accepted_existing_artifacts_replaced=False))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--mode',choices=['video_analysis','mixed','both'],default='video_analysis')
    parser.add_argument('--limit',type=int,choices=[1,2,3,4],default=4)
    parser.add_argument('--renderer-root',default='C:/vfns01/renderer')
    asyncio.run(main_async(parser.parse_args()))
