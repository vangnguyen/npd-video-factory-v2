"""Loopback-only development UI harness: real persistence/media, explicit fixture ASR.

This is not production configuration or provider acceptance. All data is fresh,
render/publish/provider dispatch is unavailable, and existing installations are untouched.
"""
from __future__ import annotations
import argparse
from contextlib import asynccontextmanager
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'apps/api'), str(ROOT/'apps/api/tests')]
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from test_auto_edit_analysis import setup_services, upload_fixture
from auth_test_support import install_test_human_auth, TEST_HUMAN_TOKEN
from app.auto_edit_models import AutoEditAnalysisRequest
from app.auto_edit_providers import FFprobeMediaProbe, FFmpegMediaSignalProvider
from app.auto_edit_routes import router as auto_edit_router
from app.timeline_routes import router as timeline_router
from app.timeline_repository import TimelineRepository
from app.timeline_service import TimelineService, TimelineContractValidator
from app.timeline_models import TimelineCreateRequest
from app.human_auth import authorize_human_request, principal_from


def create_harness(data_dir: Path):
    @asynccontextmanager
    async def lifespan(app):
        engine,sessions,platform,repo,uploads,analyses,project,version = await setup_services(data_dir)
        media = data_dir/'synthetic-tone-not-speech.mp4'
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:raise RuntimeError('FFmpeg must be configured for local media measurement')
        subprocess.run([ffmpeg,'-v','error','-nostdin','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=16',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=8','-af','adelay=4000,apad=whole_dur=16',
            '-c:v','libx264','-preset','ultrafast','-c:a','aac','-t','16',str(media)],check=True,timeout=60)
        uploads.media_probe = FFprobeMediaProbe()
        uploads.max_upload_size_bytes = 10*1024*1024
        analyses.signal_provider = FFmpegMediaSignalProvider()
        await platform.seed_providers([{'provider_key':analyses.signal_provider.key,'display_name':'Local FFmpeg measurement',
            'capability':'media_analysis','adapter':'app.auto_edit_providers.FFmpegMediaSignalProvider',
            'routing_mode':'primary','status':'healthy','enabled':True,'supports_dry_run':True}])
        upload = await upload_fixture(uploads,project,version,media.read_bytes())
        result = await analyses.analyze(project.project_id,AutoEditAnalysisRequest(asset_id=upload.asset_id,top_highlights=5))
        timelines = TimelineRepository(sessions)
        app.state.timeline_service = TimelineService(repository=timelines, platform=platform, auto_edit_repository=repo,
            media_repository=None, validator=TimelineContractValidator(ROOT/'packages/contracts/timeline.schema.json'))
        app.state.auto_edit_analysis_service = analyses
        app.state.upload_service = uploads
        install_test_human_auth(app, platform_repository=platform)
        app.state.fixture = {'platform':platform,'project':project,'analyses':analyses,'repo':repo}
        timeline = await app.state.timeline_service.create(project.project_id,TimelineCreateRequest(analysis_id=result.analysis_id,
                                                           silence_decision_ids=[],actor_ref='offline-fixture'))
        (data_dir/'fixture-session.json').write_text(json.dumps({'token':TEST_HUMAN_TOKEN,'project_id':project.project_id,
            'url':'loopback only','fixture_asr':True,'measured_media':True,'real_provider_acceptance':False}),encoding='utf-8')
        (data_dir/'analysis.json').write_text(result.model_dump_json(indent=2),encoding='utf-8')
        (data_dir/'timeline.json').write_text(timeline.model_dump_json(indent=2),encoding='utf-8')
        try:yield
        finally:await engine.dispose()
    app = FastAPI(lifespan=lifespan)
    deps = [Depends(authorize_human_request)]
    app.include_router(timeline_router, dependencies=deps)
    app.include_router(auto_edit_router, dependencies=deps)

    @app.get('/api/v1/auth/session', dependencies=deps)
    async def session(request: Request):
        principal = principal_from(request)
        return {'display_name':'Offline fixture — ASR mô phỏng','platform_role':principal.platform_role,
                'subject':principal.subject,'fixture':True}
    @app.get('/api/v1/workspaces', dependencies=deps)
    async def workspaces():return await app.state.fixture['platform'].list_workspaces()
    @app.get('/api/v1/workspaces/{workspace_id}/projects', dependencies=deps)
    async def projects(workspace_id: str):return await app.state.fixture['platform'].list_projects(workspace_id)
    @app.get('/api/v1/projects/{project_id}/assets', dependencies=deps)
    async def assets(project_id: str):return await app.state.fixture['platform'].list_assets(project_id)
    @app.get('/api/v1/projects/{project_id}/media-plans', dependencies=deps)
    async def plans(project_id: str):return []
    @app.get('/api/v1/projects/{project_id}/publications', dependencies=deps)
    async def publications(project_id: str):return []
    @app.get('/api/v1/publishing-platforms', dependencies=deps)
    async def platforms():return []
    @app.get('/api/v1/analytics-providers', dependencies=deps)
    async def analytics_providers():return []
    @app.get('/api/v1/projects/{project_id}/analytics', dependencies=deps)
    async def analytics(project_id: str):return {'latest_sync':None,'latest_snapshot':None,'latest_assessment':None,'history_count':0,'learning_insights':[]}
    @app.get('/api/v1/projects/{project_id}/content', dependencies=deps)
    async def content(project_id: str):return None
    @app.get('/api/v1/projects/{project_id}/content-provider', dependencies=deps)
    async def provider(project_id: str):return {'status':'NOT_CONFIGURED'}
    @app.get('/api/v1/projects/{project_id}/content-generation', dependencies=deps)
    async def generation(project_id: str):return {'job':None,'proposal':None,'provider_status':'NOT_CONFIGURED'}
    @app.get('/api/v1/projects/{project_id}/production-package', dependencies=deps)
    async def package(project_id: str):raise HTTPException(404, detail={'message':'Fixture: production dispatch disabled'})
    @app.get('/')
    async def studio():return FileResponse(ROOT/'apps/studio-web/studio.html')
    app.mount('/',StaticFiles(directory=ROOT/'apps/studio-web'))
    return app


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--port',type=int,default=18031)
    args=parser.parse_args()
    args.data_dir.mkdir(parents=True,exist_ok=False)
    uvicorn.run(create_harness(args.data_dir),host='127.0.0.1',port=args.port,log_level='warning')
