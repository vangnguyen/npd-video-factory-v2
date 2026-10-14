"""Isolated real local narration -> six SQL variants. Explicit manual fixtures.

No inference is performed by --prepare. --execute requires a pinned clean base
and a new owned root; there is deliberately no resume/retry switch. Real local
VieNeu, Remotion and FullQC results never imply Owner or speech acceptance.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
import secrets
import importlib.metadata
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone

REPO = Path(__file__).resolve().parents[1]
RUNTIME = Path('C:/vfns-sql-vieneu-c1')
LOG = Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007')
UNIT_TEXTS = (
    'Giọng Thùy Dung đọc thử tại Hà Nội, trên hình nền minh họa do chương trình tạo.',
    'Sáu định dạng giữ nguyên lời đọc; mỗi bản con phải được xem lại riêng.',
)
SCRIPT = '\n'.join(UNIT_TEXTS)
PROFILE_REFS = ['youtube-landscape@1', 'youtube-shorts@1', 'tiktok-short@1',
                'instagram-reel@1', 'social-square@1', 'social-feed@1']
FIXTURE_COMMENT = ('AUTOMATED INDEPENDENT FIXTURE REVIEW ONLY; not Owner UAT, '
                   'human listening, speech quality or rights transfer.')
SOURCE_FILES = ['apps/api/app/config.py', 'apps/api/app/main.py',
    'apps/api/app/production_service.py', 'apps/api/app/production_repository.py',
    'apps/api/app/production_routes.py', 'apps/api/app/production_audio.py',
    'apps/api/app/production_qc.py', 'apps/api/app/production_logic.py',
    'apps/api/app/sql_tts_artifact_reuse.py', 'apps/api/app/narration_pacing.py',
    'apps/api/app/content_service.py', 'apps/api/app/storyboard_timeline.py',
    'apps/api/app/sql_variant_narration_activation.py', 'apps/api/app/sql_variant_narration_runtime.py',
    'apps/api/app/sql_variant_narration_routes.py', 'apps/api/app/sql_variant_narration_repository.py',
    'apps/api/app/sql_variant_narration_service.py', 'apps/api/app/sql_variant_narration_copy.py',
    'apps/api/app/sql_variant_narration_render.py', 'apps/api/app/sql_variant_narration_projection.py',
    'apps/api/app/sql_variant_repository.py', 'apps/api/app/sql_variant_storyboard_copy.py',
    'apps/api/app/sql_variant_derivation_repository.py', 'apps/api/app/sql_variant_api_service.py',
    'apps/api/app/vieneu_contracts.py', 'apps/api/app/vieneu_tts_provider.py',
    'services/worker/npd_worker/main.py', 'scripts/vieneu-local-server.py',
    'scripts/north_star_sql_variant_source_render.py', 'scripts/north_star_sql_spoken_variants.py',
    'scripts/north_star_sql_vieneu_windows_bootstrap.py',
    'packages/contracts/timeline-render.schema.json', 'packages/contracts/timeline.schema.json']


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as f:
        json.dump(value, f, indent=2, ensure_ascii=True, allow_nan=False); f.write('\n')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, text=True).strip()


def source_manifest():
    return [{'path':p, 'bytes':(REPO/p).stat().st_size, 'sha256':sha(REPO/p)} for p in SOURCE_FILES]


def owned_listener(server, command, root, started_wall):
    script="""$p=(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 18083 -State Listen -ErrorAction Stop).OwningProcess
$s=Get-CimInstance Win32_Process -Filter ('ProcessId='+$p)
[pscustomobject]@{pid=$s.ProcessId;parent_pid=$s.ParentProcessId;executable=$s.ExecutablePath;command_line=$s.CommandLine;creation_time=$s.CreationDate.ToUniversalTime().ToString('o')}|ConvertTo-Json -Compress"""
    value=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',script],text=True))
    qualification=json.loads((LOG/'sql-spoken-six-runtime-qualification-n1.json').read_bytes())
    base=qualification['environment']['base_executable']
    if value['pid']!=server.pid and value['parent_pid']!=server.pid:
        raise RuntimeError('SPOKEN_LISTENER_NOT_OWNED')
    if Path(value['executable']).resolve() not in {Path(base).resolve(),Path(command[0]).resolve()}:
        raise RuntimeError('SPOKEN_LISTENER_EXECUTABLE_CHANGED')
    shell=ctypes.WinDLL('shell32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    shell.CommandLineToArgvW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype=ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes=[wintypes.HLOCAL];kernel.LocalFree.restype=wintypes.HLOCAL
    count=ctypes.c_int();argv=shell.CommandLineToArgvW(value['command_line'],ctypes.byref(count))
    try:actual=[argv[i] for i in range(count.value)]
    finally:kernel.LocalFree(argv)
    normalize=lambda x:str(x).casefold().replace('\\','/')
    if [normalize(v) for v in actual[1:]] != [normalize(v) for v in command[1:]]:
        raise RuntimeError('SPOKEN_LISTENER_ARGUMENTS_CHANGED')
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];kernel.TerminateProcess.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    kernel.GetProcessTimes.restype=wintypes.BOOL
    handle=kernel.OpenProcess(0x00100000|0x0001|0x1000,False,value['pid'])
    if not handle or kernel.WaitForSingleObject(handle,0)!=258:
        if handle:kernel.CloseHandle(handle)
        raise RuntimeError('SPOKEN_LISTENER_NOT_LIVE')
    created=wintypes.FILETIME();exited=wintypes.FILETIME();system=wintypes.FILETIME();user=wintypes.FILETIME()
    if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(system),ctypes.byref(user)):
        kernel.CloseHandle(handle);raise RuntimeError('SPOKEN_LISTENER_CREATION_UNKNOWN')
    created_seconds=((created.dwHighDateTime<<32)|created.dwLowDateTime)/10000000-11644473600
    cim_created=datetime.fromisoformat(value['creation_time'].replace('Z','+00:00')).timestamp()
    now_owner=subprocess.check_output(['powershell','-NoProfile','-Command',
        '(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 18083 -State Listen -ErrorAction Stop).OwningProcess'],text=True).strip()
    if created_seconds<started_wall-.2 or abs(created_seconds-cim_created)>.1 or now_owner!=str(value['pid']):
        kernel.CloseHandle(handle);raise RuntimeError('SPOKEN_LISTENER_CURRENT_CUSTODY_CHANGED')
    write(root/'owned-listener-process.json',{'pid':value['pid'],'parent_pid':value['parent_pid'],
        'popen_pid':server.pid,'executable':value['executable'],'exact_arguments_verified':True,
        'qualified_base_interpreter':base,'creation_time':value['creation_time'],
        'launch_time_UTC_seconds':started_wall,'held_process_creation_seconds':created_seconds,
        'held_process_handle':True,'port_rechecked_after_handle':True})
    return kernel,handle


def prepare(args):
    if git('rev-parse', 'HEAD') != args.expected_head or git('diff', '--name-only'):
        raise RuntimeError('SPOKEN_FROZEN_BASE_REQUIRED')
    if Path(sys.executable).resolve() != (RUNTIME/'venv/Scripts/python.exe').resolve():
        raise RuntimeError('SPOKEN_QUALIFIED_INTERPRETER_REQUIRED')
    if args.root.exists() or args.root.parent.resolve() != Path('C:/').resolve() \
            or not args.root.name.startswith('vfns-sql-spoken-six-'):
        raise RuntimeError('SPOKEN_NEW_OWNED_ROOT_REQUIRED')
    if len(UNIT_TEXTS) != 2 or any(len(t) > 180 for t in UNIT_TEXTS):
        raise RuntimeError('SPOKEN_EXACT_TWO_SEMANTIC_UNITS_REQUIRED')
    qualified_report=LOG/'sql-spoken-six-runtime-qualification-n1.json'
    if sha(qualified_report)!='f32136cbd732fe3d7f6fa6827b7cb75c2e2ee2f12124ffd1e10b7f66a53a012c':
        raise RuntimeError('SPOKEN_QUALIFIED_RUNTIME_REPORT_CHANGED')
    qualification = json.loads(qualified_report.read_bytes())
    if qualification['status'] != 'PRESET_CONSTRUCTOR_QUALIFIED_NO_INFERENCE':
        raise RuntimeError('SPOKEN_RUNTIME_NOT_CONFIGURED')
    installed=json.loads((RUNTIME/'install-manifest-corrected-n2.json').read_bytes())
    for pin in installed['packages']:
        if importlib.metadata.version(pin['name'])!=pin['version']:
            raise RuntimeError('SPOKEN_EXACT_RUNTIME_VERSION_CHANGED')
    for row in qualification['model_files']:
        if sha(row['path']) != row['sha256']:
            raise RuntimeError('SPOKEN_PINNED_MODEL_CHANGED')
    with socket.socket() as s:
        s.settimeout(.3)
        if s.connect_ex(('127.0.0.1', 18083)) == 0:
            raise RuntimeError('SPOKEN_PORT_ALREADY_OWNED_NO_REUSE')
    return {'schema_version':'sql-spoken-six-preflight.v1', 'base_head':args.expected_head,
        'root':str(args.root), 'source':source_manifest(), 'runtime_report_sha256':sha(LOG/'sql-spoken-six-runtime-qualification-n1.json'),
        'model_files':qualification['model_files'], 'profile_sha256':qualification['profile_sha256'],
        'script':SCRIPT, 'script_sha256':hashlib.sha256(SCRIPT.encode()).hexdigest(),
        'semantic_units':[{'text':t, 'text_sha256':hashlib.sha256(t.encode()).hexdigest()} for t in UNIT_TEXTS],
        'maximum_synthesis_requests':2, 'automatic_retry':False, 'child_inferences':0,
        'manual_script_scenes_and_visual_fixture':True, 'genuine_tts_not_mock':True,
        'speech_quality_accepted':False, 'owner_uat_accepted':False, 'production_deployed':False}


class FixtureQueue:
    """In-memory delivery only; all job state and worker execution are actual SQL."""
    def __init__(self):
        self.items = asyncio.Queue(); self.dispatches = []
    async def rpush(self, key, value):
        self.dispatches.append((key, value)); await self.items.put(value)
    async def brpoplpush(self, source, target, timeout):
        return await self.items.get()
    async def lrem(self, *args):
        return 1


async def drain(task):
    while not task.done():
        try: await asyncio.shield(task)
        except asyncio.CancelledError: pass
    return task.result()


async def worker_one(env, queued):
    from npd_worker.main import run_production_render_queue
    entered = asyncio.Event(); done = asyncio.Event(); original = env.processor.process; result = []
    async def capture(render_id):
        if render_id != queued.render_id: raise RuntimeError('SPOKEN_QUEUE_IDENTITY_CHANGED')
        entered.set()
        try:
            value = await original(render_id); result.append(value); return value
        finally: done.set()
    env.processor.process = capture
    task = asyncio.create_task(run_production_render_queue(env.queue, env.processor))
    try:
        await asyncio.wait_for(entered.wait(), 10)
        await asyncio.wait_for(done.wait(), 1500)
    finally:
        task.cancel()
        try: await drain(task)
        except asyncio.CancelledError: pass
        env.processor.process = original
    if not result: raise RuntimeError('SPOKEN_WORKER_FAILED_WITHOUT_RESULT')
    return result[0]


async def create_environment(args, root):
    from types import SimpleNamespace
    from fastapi import FastAPI, Depends
    from app import main as product
    from app.config import Settings
    from app.db import Base, create_engine, create_session_factory
    from app.repositories import PlatformRepository
    from app.platform_models import WorkspaceCreate, ProjectCreate
    from app.object_storage import LocalObjectStorageProvider
    from app.auto_edit_repository import AutoEditRepository
    from app.timeline_repository import TimelineRepository
    from app.timeline_service import TimelineService, TimelineContractValidator
    from app.media_intelligence_repository import MediaIntelligenceRepository
    from app.content_service import ContentService
    from app.production_repository import ProductionRepository
    from app.production_service import ProductionPackageService, ProductionRenderProcessor
    from app.production_logic import TimelineRenderContractValidator
    from app.production_audio import AudioMixEngine, create_audio_tts_provider
    from app.production_qc import FullProductionQC
    from app.sql_variant_narration_runtime import create_variant_narration_runtime, register_variant_narration_routes
    from app.sql_variant_api_service import configure_sql_variant_api
    from app.human_auth import authorize_human_request, HumanAuthRegistry, HumanAuthVerifier, HumanRateLimiter
    from app.content_routes import router as content_router
    from app.timeline_routes import router as timeline_router
    from app.production_routes import router as production_router
    from auth_test_support import MemoryRateStore
    from north_star_sql_variant_source_render import PrivateLocalRenderer, renderer_preflight
    settings = Settings(_env_file=None, audio_tts_provider='vieneu', vieneu_voice_id='Thùy Dung',
        vieneu_local_execution_enabled=True, sql_variant_narration_reuse_enabled=True,
        provider_external_execution_enabled=False, provider_paid_execution_enabled=False,
        audio_external_execution_enabled=False, provider_global_kill_switch_engaged=True)
    engine = create_engine('sqlite+aiosqlite:///'+str(root/'dev.db'))
    async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    factory = create_session_factory(engine); platform = PlatformRepository(factory)
    old_settings = product.settings
    try:
        product.settings = settings
        registry = product.normalize_provider_definitions(product._provider_definitions(
            product.uploaded_audio_provider(settings), product.auto_edit_transcription_provider(settings)))
    finally: product.settings = old_settings
    await platform.seed_providers(registry)
    write(root/'provider-registry-initial.json', registry)
    workspace = await platform.create_workspace(WorkspaceCreate(slug='spoken-local-fixture',
        name='Local real speech, manual visual/script fixture', owner_ref='fixture-not-Owner-UAT'))
    project = await platform.create_project(workspace.workspace_id, ProjectCreate(slug='spoken-master', name='Spoken master fixture'))
    storage = LocalObjectStorageProvider(root/'objects'); await storage.ensure_ready()
    assets = AutoEditRepository(factory); timeline = TimelineRepository(factory)
    timeline_service = TimelineService(repository=timeline, platform=platform, auto_edit_repository=assets,
        media_repository=MediaIntelligenceRepository(factory), object_storage=storage,
        validator=TimelineContractValidator(REPO/'packages/contracts/timeline.schema.json'))
    runtime = create_variant_narration_runtime(session_factory=factory, object_storage=storage, assets=assets, enabled=True)
    repository = ProductionRepository(factory, variant_narration_fence=runtime.fence, variant_narration_admission=runtime.admission)
    queue = FixtureQueue()
    package = ProductionPackageService(repository=repository, timeline_repository=timeline, asset_repository=assets, queue=queue, settings=settings)
    content = ContentService(platform)
    tts = create_audio_tts_provider(settings); calls = []
    original_synthesis = type(tts).synthesize
    phase = {'value':'master-initial'}
    async def counted_synthesis(actual_provider, **kwargs):
        if phase['value'] != 'master-initial' or len(calls) >= len(UNIT_TEXTS):
            raise RuntimeError('SPOKEN_NO_ADDITIONAL_INFERENCE_ALLOWED')
        text = kwargs['text']
        if text != UNIT_TEXTS[len(calls)]: raise RuntimeError('SPOKEN_SEMANTIC_UNIT_DRIFT')
        write(root/f'dispatch-{len(calls):02d}.json', {'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'phase':phase['value'], 'retry':False, 'request_number':len(calls)+1})
        calls.append(text)
        return await original_synthesis(actual_provider, **kwargs)
    # Process-local dispatch observer preserves the actual cloned provider's
    # scope/guard and invokes its original implementation, never a test voice.
    type(tts).synthesize = counted_synthesis
    renderer_info = renderer_preflight(args.renderer_root); write(root/'renderer-preflight.json', renderer_info)
    receipts = root/'renderer-receipts'; receipts.mkdir()
    renderer = PrivateLocalRenderer(renderer_root=args.renderer_root, receipt_root=receipts)
    processor = ProductionRenderProcessor(repository=repository, platform=platform, asset_repository=assets,
        object_storage=storage, renderer=renderer, qc=FullProductionQC(), tts_provider=tts, audio_engine=AudioMixEngine(),
        manifest_validator=TimelineRenderContractValidator(REPO/'packages/contracts/timeline-render.schema.json'),
        staging_root=root/'render-stage', brand_name='Explicit local spoken fixture', variant_narration_loader=runtime.loader)
    app = FastAPI(); deps=[Depends(authorize_human_request)]
    for router in (content_router, timeline_router, production_router): app.include_router(router, dependencies=deps)
    configure_sql_variant_api(app, session_factory=factory, object_storage=storage)
    register_variant_narration_routes(app)
    app.state.content_service=content; app.state.timeline_service=timeline_service
    app.state.production_package_service=package; app.state.sql_variant_narration_runtime=runtime
    app.state.object_storage=storage; app.state.database_session_factory=factory
    app.state.production_render_download_root=root/'downloads'
    tokens={};headers={};now=datetime.now(timezone.utc)
    for role in ('editor','reviewer'):
        token_id='spoken-'+role;token='vf1.'+token_id+'.'+secrets.token_urlsafe(36)
        subject='usr:spoken-fixture-'+role
        tokens[token_id]={'token_id':token_id,'token_sha256':hashlib.sha256(token.encode()).hexdigest(),
            'subject':subject,'display_name':'Explicit fixture '+role,'platform_role':None,
            'workspace_roles':{workspace.workspace_id:role},'issued_at':now.isoformat(),'not_before':now.isoformat(),
            'expires_at':(now+timedelta(hours=2)).isoformat(),'enabled':True}
        headers[role]={'Authorization':'Bearer '+token}
    app.state.platform_repository=platform;app.state.human_api_enabled=True;app.state.human_write_enabled=True
    app.state.human_auth_verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate({'version':1,'tokens':tokens}),max_token_ttl_seconds=86400)
    app.state.human_rate_limiter=HumanRateLimiter(MemoryRateStore(),requests_per_minute=1000)
    return SimpleNamespace(engine=engine, factory=factory, platform=platform, workspace=workspace, project=project,
        assets=assets, storage=storage, timeline=timeline, timeline_service=timeline_service, content=content,
        repository=repository, package=package, runtime=runtime, queue=queue, processor=processor,
        renderer=renderer, app=app, headers=headers, calls=calls, phase=phase,
        editor='usr:spoken-fixture-editor',reviewer='usr:spoken-fixture-reviewer')


async def api(env, method, path, body=None, *, role='editor'):
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(env.app), base_url='http://owned-sql-fixture', headers=env.headers[role]) as c:
        response = await c.request(method, '/api/v1'+path, json=body)
    if not 200 <= response.status_code < 300:
        raise RuntimeError('SPOKEN_API_'+str(response.status_code)+':'+response.text[:500])
    return response.json()


async def package(env, project):
    from app.production_models import ProductionPackageRead
    return ProductionPackageRead.model_validate(await api(env,'POST',f'/projects/{project}/production-package',{}))


async def render(env, project, kind, profile, folder, *, selection=None, approval=None, family=None):
    from app.production_models import RenderJobRead
    p=await package(env,project)
    body={'expected_timeline_version':p.timeline_version,'expected_subtitle_version':p.subtitle.version,
        'expected_audio_version':p.audio_mix.version,'profile':profile,'actor_ref':'untrusted-body-fixture'}
    if selection:
        body['selection']=selection
        path=f'/projects/{env.project.project_id}/variant-families/{family}/children/{project}/narration-review-render'
    elif kind=='review':path=f'/projects/{project}/review-render'
    else:path=f'/projects/{project}/final-render';body['approval_id']=approval
    queued=RenderJobRead.model_validate(await api(env,'POST',path,body))
    write(folder/f'{kind}-queued.json',queued.model_dump(mode='json'))
    done=await worker_one(env,queued);write(folder/f'{kind}-render.json',done.model_dump(mode='json'))
    if done.status not in {'awaiting_review','ready'} or done.qc_status!='passed':
        raise RuntimeError('SPOKEN_RENDER_REJECTED:'+str(done.error_code))
    asset=await env.assets.get_asset(done.output_asset_id)
    original=env.storage._path(asset.object_key)
    with original.open('rb') as src,(folder/f'{kind}.mp4').open('xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
    if sha(original)!=sha(folder/f'{kind}.mp4'):raise RuntimeError('SPOKEN_RENDERED_COPY_CHANGED')
    write(folder/f'{kind}-qc.json',done.qc_report);return done


async def fixture_approval(env, project, review, folder):
    requested=await api(env,'POST',f'/projects/{project}/approvals', {'review_render_id':review.render_id,
        'requester_ref':env.editor, 'note':FIXTURE_COMMENT})
    approved=await api(env,'POST',f"/projects/{project}/approvals/{requested['approval_id']}/decision",{
        'decision':'approved','reviewer_ref':env.reviewer,'comment':FIXTURE_COMMENT},role='reviewer')
    write(folder/'fixture-approval.json',approved);return approved['approval_id']


async def prepare_master(root, env):
    from app.content_models import ContentDocument,StoryboardScene
    from app.timeline_models import TimelineSnapshot
    master=root/'master';master.mkdir()
    scenes=[];cursor=0
    for i,text in enumerate(UNIT_TEXTS):
        scenes.append(StoryboardScene(scene_id=f'scene_spoken_{i:02d}', narration=text,
            duration_seconds=max(4,math.ceil((len(text.split())/2.4+1)*10)/10),pause_after_seconds=.18,
            media_strategy='motion_graphic',script_start=cursor,script_end=cursor+len(text)))
        cursor+=len(text)+1
    document=ContentDocument(input_kind='script',original_text=SCRIPT,script=SCRIPT,scenes=scenes,
        protected_terms=['Thùy Dung','Hà Nội'],approved=True,generator='fixture-storyboard-v1')
    content=await api(env,'PUT',f'/projects/{env.project.project_id}/content',{'document':document.model_dump(mode='json')})
    built=await api(env,'POST',f'/projects/{env.project.project_id}/timeline',{'source_kind':'storyboard_media','content_version_id':content['project_version_id']})
    canvas=TimelineSnapshot.model_validate(built['snapshot']).model_copy(update={
        'width':1920,'height':1080,'aspect_ratio':'16:9'})
    env.timeline_service.validator.validate(canvas)
    built=(await env.timeline.commit_mutation(project_id=env.project.project_id,expected_version=built['current_version'],
        snapshot=canvas,mutation={'type':'explicit-fixture-master-canvas','aspect_ratio':'16:9'},actor_ref=env.editor)).model_dump(mode='json')
    write(master/'manual-script-fixture.json',content);write(master/'initial-timeline.json',built)
    plan=built['snapshot']['metadata']['narration_plan']
    if [u['text'] for u in plan['units']]!=list(UNIT_TEXTS):raise RuntimeError('SPOKEN_PLAN_UNIT_DRIFT')
    write(root/'semantic-unit-budget.json',{'maximum_requests':len(plan['units']),'plan':plan,'retry':False,'children_request_cap':0})
    return master


async def run_flow(args, root, env):
    from app.content_models import ContentDocument
    from app.sql_variant_models import FamilyReserveRequest,digest
    from app.sql_variant_narration_models import NarrationReuseRequest
    from app.sql_variant_narration_projection import narration_projection,child_cues
    from app.timeline_models import TimelineSnapshot
    master=await prepare_master(root,env)
    initial=master/'initial-review';initial.mkdir()
    review=await render(env,env.project.project_id,'review','review-960x540',initial)
    env.phase['value']='no-more-inference'
    # Supported successful own-review reflow; cache binds immutable same content.
    reflow=await api(env,'POST',f'/projects/{env.project.project_id}/narration-reflow',{
        'expected_timeline_version':review.timeline_version,'review_render_id':review.render_id})
    write(master/'measured-reflow.json',reflow)
    tightened=master/'measured-review';tightened.mkdir()
    review=await render(env,env.project.project_id,'review','review-960x540',tightened)
    approval=await fixture_approval(env,env.project.project_id,review,tightened)
    final_folder=master/'approved-final';final_folder.mkdir()
    final=await render(env,env.project.project_id,'final','landscape-1920x1080',final_folder,approval=approval)
    if len(env.calls)!=len(UNIT_TEXTS):raise RuntimeError('SPOKEN_MASTER_CALL_COUNT_CHANGED')
    print(json.dumps({'checkpoint':'MASTER_REAL_QC_PASSED','master_review':review.render_id,'master_final':final.render_id,
        'maximum_requests':len(UNIT_TEXTS),'actual_provider_requests':len(env.calls),'fixture_approval_not_owner':True}),flush=True)
    families=env.app.state.sql_variant_api_service.families
    available=await families.availability(env.workspace.workspace_id,env.project.project_id)
    reserve=FamilyReserveRequest(expected_project_version=available.binding.project_version,
        expected_timeline_version=available.binding.timeline_version,expected_timeline_version_id=available.binding.timeline_version_id,
        expected_binding_sha256=available.binding_sha256,catalog_ref=available.catalog.catalog_ref,catalog_sha256=available.catalog_sha256,
        profile_refs=PROFILE_REFS,request_key='spoken-six-real-family-01',acknowledge_draft_derivation=True)
    prefix=f'/projects/{env.project.project_id}/variant-families'
    family=(await api(env,'POST',prefix,reserve.model_dump(mode='json')))['family'];write(root/'family-reserved.json',family)
    members=[]
    for member in family['members']:
        current=await families.get(env.workspace.workspace_id,env.project.project_id,family['family_id'])
        result=await api(env,'POST',prefix+'/'+family['family_id']+'/derive',{
            'schema_version':'sql-variant-storyboard-derive.v1','expected_version':current.version,
            'expected_snapshot_sha256':current.snapshot_sha256,'member_id':member['member_id'],
            'request_key':'spoken-child-'+member['member_id'],'acknowledge_unapproved_child':True})
        receipt=result['receipt'];project=receipt['result']['child_project_id']
        folder=root/'children'/member['profile']['target'];folder.mkdir(parents=True)
        write(folder/'derivation-receipt.json',receipt)
        members.append((member,project,folder))
    # Fresh child script/package, preserving exact approved master audio clock.
    source_timeline=await env.timeline.get_timeline(env.project.project_id)
    source_package=await env.repository.get_package(env.project.project_id)
    source_projection=narration_projection(source_timeline.snapshot.model_dump(mode='json'),source_package.subtitle.cues,source_package.audio_mix.config.voice)
    for member,project,folder in members:
        old_content=await env.content.latest(project)
        child_document=ContentDocument.model_validate(old_content.snapshot['content'])
        child_document=child_document.model_copy(update={'approved':True,'scenes':[s.model_copy(update={
            'media_strategy':'motion_graphic','asset_id':None,'analysis_id':None}) for s in child_document.scenes]})
        changed=await api(env,'PUT',f'/projects/{project}/content',{'expected_content_version_id':old_content.project_version_id,'document':child_document.model_dump(mode='json')})
        current=await env.timeline.get_timeline(project)
        rebuilt=await api(env,'POST',f'/projects/{project}/timeline',{'source_kind':'storyboard_media',
            'content_version_id':changed['project_version_id'],'expected_timeline_version':current.current_version})
        snapshot=TimelineSnapshot.model_validate(rebuilt['snapshot'])
        value=snapshot.model_dump(mode='json');source=source_timeline.snapshot.model_dump(mode='json')
        for kind in ('source','subtitles'):
            targets=[c for t in value['tracks'] if (t['track_id']=='trk_storyboard' if kind=='source' else t['kind']==kind) for c in t['clips']]
            originals=[c for t in source['tracks'] if (t['track_id']=='trk_storyboard' if kind=='source' else t['kind']==kind) for c in t['clips']]
            if len(targets)!=len(originals) or any(t['locked'] for t in value['tracks']):raise RuntimeError('SPOKEN_CHILD_CLOCK_NOT_EDITABLE')
            for target,original in zip(targets,originals,strict=True):
                if target['label']!=original['label']:raise RuntimeError('SPOKEN_CHILD_SCRIPT_CHANGED')
                for field in ('timeline_start','duration'):
                    target[field]=original[field]
                if kind=='subtitles':
                    for field in ('source_start','source_end'):target[field]=original[field]
        value['duration_seconds']=source['duration_seconds']
        value['metadata']['narration_reflow']=copy.deepcopy(source['metadata']['narration_reflow'])
        value['metadata']['fixture_clock_projection']={'source_project_id':env.project.project_id,
            'source_review_render_id':review.render_id,'source_clock_sha256':digest(source_projection),
            'source_approval_transferred':False,'fixture_editor_operation':True}
        # Canvas IDs/child assets and content stay child-owned; CAS creates a new draft.
        value['aspect_ratio']=member['profile']['aspect_ratio']
        value['width']=member['profile']['width'];value['height']=member['profile']['height']
        env.timeline_service.validator.validate(TimelineSnapshot.model_validate(value))
        fresh=await env.timeline.commit_mutation(project_id=project,expected_version=rebuilt['current_version'],
            snapshot=TimelineSnapshot.model_validate(value),mutation={'type':'explicit-fixture-preserve-source-narration-clock',
                'source_review_render_id':review.render_id,'approval_transferred':False},actor_ref=env.editor)
        p=await package(env,project)
        if narration_projection(fresh.snapshot.model_dump(mode='json'),child_cues(fresh.snapshot.model_dump(mode='json')),p.audio_mix.config.voice)!=source_projection:
            raise RuntimeError('SPOKEN_EXACT_CHILD_PROJECTION_REQUIRED')
        write(folder/'fresh-child-script.json',changed);write(folder/'fresh-child-timeline.json',fresh.model_dump(mode='json'))
    current=await families.get(env.workspace.workspace_id,env.project.project_id,family['family_id'])
    write(root/'family-final-version.json',current.model_dump(mode='json'))
    for member,project,folder in members:
        child=await env.timeline.get_timeline(project);child_content=await env.content.latest(project);p=await package(env,project)
        units=review.manifest['narration']['timing']
        request=NarrationReuseRequest(enabled=True,expected_version=current.version,expected_snapshot_sha256=current.snapshot_sha256,
            request_key='spoken-narration-'+member['member_id'],member_id=member['member_id'],child_project_id=project,
            expected_child_content_version_id=child_content.project_version_id,expected_child_timeline_version_id=child.current_version_id,
            expected_child_timeline_version=child.current_version,source_review_render_id=review.render_id,source_approval_id=approval,
            expected_source_manifest_sha256=digest(review.manifest),expected_semantic_sha256=digest(source_projection),
            expected_profile_sha256s=[u['provider_evidence']['profile_sha256'] for u in units],
            expected_normalization_sha256s=[u['provider_evidence']['usage']['normalization_record_sha256'] for u in units],
            voice_config=p.audio_mix.config.voice,acknowledge_fresh_child_review=True)
        path=prefix+'/'+family['family_id']+'/children/'+project
        imported=(await api(env,'POST',path+'/narration-reuse',request.model_dump(mode='json')))['receipt']
        write(folder/'narration-receipt.json',imported)
        selection={'enabled':True,'receipt_id':imported['receipt_id'],'family_id':family['family_id'],
            'member_id':member['member_id'],'master_project_id':env.project.project_id,
            'input_sha256':imported['input_sha256'],'result_sha256':imported['result_sha256']}
        child_review=await render(env,project,'review',member['profile']['review_profile'],folder,
            selection=selection,family=family['family_id'])
        child_approval=await fixture_approval(env,project,child_review,folder)
        child_final=await render(env,project,'final',member['profile']['final_profile'],folder,approval=child_approval)
        if len(env.calls)!=2:raise RuntimeError('SPOKEN_CHILD_INFERENCE_OCCURRED')
    return {'master_project_id':env.project.project_id,'master_review_id':review.render_id,'master_final_id':final.render_id,
        'family_id':family['family_id'],'children':[{'project_id':p,'profile':m['profile']} for m,p,f in members],
        'provider_requests':len(env.calls),'child_synthesis_requests':0,'actual_local_renders':env.renderer.completed,
        'all_actual_FullQC_passed':True,'approval_fixture_only':True,'Owner_UAT':False,'speech_quality_accepted':False}


async def export_sql(env, root):
    from sqlalchemy import select
    from app.db import Base
    from app.sql_variant_repository import record_value
    async with env.factory() as s:
        rows={m.class_.__tablename__:[record_value(r) for r in (await s.scalars(select(m.class_))).all()]
            for m in Base.registry.mappers}
    write(root/'sql-rows-before-stop.json',rows)
    with sqlite3.connect(root/'dev.db') as source,sqlite3.connect(root/'cold.db') as target:source.backup(target)
    return rows


async def execute(args, preflight):
    root=args.root;root.mkdir(exist_ok=False);write(root/'preflight.json',preflight)
    write(root/'exclusive-attempt-marker.json',{'state':'STARTED','resume_allowed':False,'source_head':args.expected_head})
    env=None;server=None;listener=None;outcome={'status':'NOT_COMPLETED','Owner_UAT':False,'inferences_retry':False};start=time.perf_counter()
    sys.path[:0]=[str(REPO/'apps/api'),str(REPO/'apps/api/tests'),str(REPO/'services/worker'),str(REPO/'scripts')]
    server_log=(root/'local-server.log').open('xb')
    try:
        env=await create_environment(args,root)
        command=[sys.executable,'-I','-B',str(REPO/'scripts/north_star_sql_vieneu_windows_bootstrap.py'),
            '--model','C:/NPD-Video-Factory/runtime/models/vieneu-v3-turbo','--codec','C:/NPD-Video-Factory/runtime/models/moss-codec',
            '--sdk-source','C:/NPD-Video-Factory/runtime/sdk/vieneu-85344322','--cache',str(root/'speech-cache'),'--threads','2']
        started_wall=time.time()
        server=subprocess.Popen(command,stdout=server_log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        write(root/'owned-server-process.json',{'pid':server.pid,'command':command,'loopback':'127.0.0.1:18083','production':False})
        for _ in range(120):
            if server.poll() is not None:raise RuntimeError('SPOKEN_SERVER_START_FAILED')
            with socket.socket() as s:
                s.settimeout(.2)
                if s.connect_ex(('127.0.0.1',18083))==0:break
            await asyncio.sleep(.25)
        else:raise RuntimeError('SPOKEN_SERVER_START_TIMEOUT')
        listener=owned_listener(server,command,root,started_wall)
        outcome=await asyncio.wait_for(run_flow(args,root,env),2400);outcome['status']='LOCAL_REAL_SPOKEN_SIX_PASSED'
    except BaseException as exc:
        outcome.update(status='REJECTED_OR_INCOMPLETE',error_type=type(exc).__name__,error=str(exc));traceback.print_exc()
        print(json.dumps({'checkpoint':'MASTER_OR_CHILD_FAILED','reason':str(exc),'no_retry':True}),flush=True)
    finally:
        if listener is not None:
            kernel,handle=listener
            try:
                if kernel.WaitForSingleObject(handle,0)==258:
                    kernel.TerminateProcess(handle,0)
                    if kernel.WaitForSingleObject(handle,15000)!=0:
                        outcome['owned_listener_cleanup']='DRAIN_TIMEOUT'
                else:outcome['owned_listener_cleanup']='ALREADY_EXITED'
            finally:kernel.CloseHandle(handle)
        if server is not None and server.poll() is None:
            # Only this subprocess is owned. All generated raw/cache/intent files remain.
            server.terminate()
            try:await asyncio.to_thread(server.wait,15)
            except subprocess.TimeoutExpired:server.kill();await asyncio.to_thread(server.wait,15)
        server_log.close()
        if env is not None:
            await export_sql(env,root);await env.engine.dispose()
            outcome['provider_requests_observed']=len(env.calls)
        outcome['elapsed_seconds']=time.perf_counter()-start
        outcome['source_before_after_unchanged']=source_manifest()==preflight['source']
        outcome['model_before_after_unchanged']=all(sha(p['path'])==p['sha256'] for p in preflight['model_files'])
        cache=root/'speech-cache';records=[json.loads(p.read_bytes()) for p in sorted(cache.glob('*.json'))] if cache.exists() else []
        outcome['completed_engine_infer_calls_observed']=sum(r.get('engine_infer_calls',0) for r in records)
        outcome['successful_server_synthesis_records']=len(records)
        outcome['exclusive_server_intents']=len(list(cache.glob('*.intent'))) if cache.exists() else 0
        outcome['unknown_server_intents_preserved']=outcome['exclusive_server_intents']-len(records)
        outcome['engine_infer_calls_total_known']=outcome['unknown_server_intents_preserved']==0
        outcome['engine_infer_calls_observed']=outcome['completed_engine_infer_calls_observed'] if outcome['engine_infer_calls_total_known'] else None
        write(root/'outcome.json',outcome)
        write(root/'full-file-manifest.json',{'files':[{'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':sha(p)}
            for p in sorted(root.rglob('*')) if p.is_file()]})
    print(json.dumps(outcome,ensure_ascii=True),flush=True)
    return 0 if outcome['status']=='LOCAL_REAL_SPOKEN_SIX_PASSED' else 1


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--expected-head',required=True)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--renderer-root',type=Path,default=Path('C:/vfns01/renderer'))
    parser.add_argument('--execute',action='store_true');parser.add_argument('--prepare-output',type=Path)
    parser.add_argument('--sql-preflight',action='store_true')
    args=parser.parse_args();preflight=prepare(args)
    if args.execute and args.sql_preflight:parser.error('choose one execution mode')
    if args.sql_preflight:
        return asyncio.run(sql_preflight(args,preflight))
    if not args.execute:
        if not args.prepare_output:parser.error('--prepare-output required without execution')
        write(args.prepare_output,preflight);print(json.dumps({'status':'PREPARED_NO_INFERENCE','maximum_requests':2,'source_files':len(preflight['source'])}));return 0
    return asyncio.run(execute(args,preflight))


async def sql_preflight(args,preflight):
    """Actual isolated SQL/auth/routes/queued intent, no server/worker or voice."""
    args.root.mkdir(exist_ok=False);write(args.root/'preflight.json',preflight)
    sys.path[:0]=[str(REPO/'apps/api'),str(REPO/'apps/api/tests'),str(REPO/'services/worker'),str(REPO/'scripts')]
    env=await create_environment(args,args.root)
    try:
        await prepare_master(args.root,env)
        p=await package(env,env.project.project_id)
        queued=await api(env,'POST',f'/projects/{env.project.project_id}/review-render',{
            'expected_timeline_version':p.timeline_version,'expected_subtitle_version':p.subtitle.version,
            'expected_audio_version':p.audio_mix.version,'profile':'review-960x540'})
        assert queued['status']=='queued' and not env.calls and env.renderer.calls==0
        write(args.root/'queued-no-worker.json',queued);await export_sql(env,args.root)
        print(json.dumps({'status':'ACTUAL_SQL_AUTH_PREFLIGHT_PASSED','provider_calls':0,'model_calls':0,
            'worker_calls':0,'server_started':False,'source_head':args.expected_head,'root':str(args.root)}))
        return 0
    finally:await env.engine.dispose()


if __name__=='__main__':
    raise SystemExit(main())
