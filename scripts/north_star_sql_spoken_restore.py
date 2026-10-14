"""Viewer-only cold proof of an actual spoken family; never constructs TTS."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
from datetime import datetime,timedelta,timezone

REPO=Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def files(root):
    result=[]
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise RuntimeError('SPOKEN_COLD_LINK_REJECTED')
        if p.is_file():result.append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':sha(p)})
    return result


def write(path,value):
    with path.open('x',encoding='utf8',newline='\n') as f:json.dump(value,f,indent=2,ensure_ascii=True);f.write('\n')


async def run(args):
    original=args.source.resolve();target=args.target
    if target.exists() or target.parent.resolve()!=Path('C:/').resolve() or not target.name.startswith('vfns-sql-spoken-cold-'):
        raise RuntimeError('SPOKEN_COLD_NEW_ROOT_REQUIRED')
    outcome=json.loads((original/'outcome.json').read_bytes())
    if outcome['status']!='LOCAL_REAL_SPOKEN_SIX_PASSED':raise RuntimeError('SPOKEN_COLD_COMPLETED_FAMILY_REQUIRED')
    baseline=files(original);target.mkdir(exist_ok=False)
    with sqlite3.connect((original/'cold.db').as_uri()+'?mode=ro&immutable=1',uri=True) as source,sqlite3.connect(target/'restored.db') as destination:
        source.backup(destination)
    shutil.copytree(original/'objects',target/'objects')
    assert files(original/'objects')==files(target/'objects')
    db_sha=sha(target/'restored.db')
    sys.path[:0]=[str(REPO/'apps/api'),str(REPO/'apps/api/tests')]
    from app import main as product  # model registration only; lifespan never runs.
    from app.db import create_engine,create_session_factory,Base
    from app.repositories import PlatformRepository
    from app.auto_edit_repository import AutoEditRepository
    from app.timeline_repository import TimelineRepository
    from app.content_service import ContentService
    from app.production_repository import ProductionRepository
    from app.production_service import ProductionPackageService
    from app.object_storage import LocalObjectStorageProvider
    from app.human_auth import HumanAuthRegistry,HumanAuthVerifier,HumanRateLimiter,authorize_human_request
    from app.sql_variant_api_service import configure_sql_variant_api
    from app.sql_variant_narration_runtime import create_variant_narration_runtime,register_variant_narration_routes
    from app.sql_variant_repository import record_value
    from app.production_routes import router
    from auth_test_support import MemoryRateStore
    from fastapi import FastAPI,Depends
    from sqlalchemy import select
    from types import SimpleNamespace
    import httpx
    engine=create_engine('sqlite+aiosqlite:///file:'+str((target/'restored.db').as_posix())+'?mode=ro&immutable=1&uri=true')
    factory=create_session_factory(engine);platform=PlatformRepository(factory);assets=AutoEditRepository(factory)
    storage=LocalObjectStorageProvider(target/'objects');timeline=TimelineRepository(factory)
    runtime=create_variant_narration_runtime(session_factory=factory,object_storage=storage,assets=assets,enabled=True)
    repository=ProductionRepository(factory,variant_narration_fence=runtime.fence,variant_narration_admission=runtime.admission)
    def denied(*a,**kw):raise RuntimeError('SPOKEN_COLD_NO_QUEUE_PROVIDER_WORKER')
    service=ProductionPackageService(repository=repository,timeline_repository=timeline,asset_repository=assets,
        queue=SimpleNamespace(rpush=denied),settings=SimpleNamespace(audio_tts_provider='contract'))
    app=FastAPI();app.include_router(router,dependencies=[Depends(authorize_human_request)])
    app.state.platform_repository=platform;app.state.database_session_factory=factory
    app.state.auto_edit_repository=assets
    app.state.production_package_service=service;app.state.object_storage=storage;app.state.production_render_download_root=target/'downloads'
    app.state.sql_variant_narration_runtime=runtime;configure_sql_variant_api(app,session_factory=factory,object_storage=storage)
    register_variant_narration_routes(app)
    now=datetime.now(timezone.utc);token='vf1.spoken-cold.'+secrets.token_urlsafe(36)
    app.state.human_auth_verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate({'version':1,'tokens':{'spoken-cold':{
        'token_id':'spoken-cold','token_sha256':hashlib.sha256(token.encode()).hexdigest(),'subject':'usr:spoken-cold-viewer',
        'display_name':'Explicit cold fixture viewer','platform_role':None,'workspace_roles':{'*':'viewer'},
        'issued_at':now.isoformat(),'not_before':now.isoformat(),'expires_at':(now+timedelta(hours=1)).isoformat(),'enabled':True}}}),max_token_ttl_seconds=86400)
    app.state.human_rate_limiter=HumanRateLimiter(MemoryRateStore(),requests_per_minute=1000)
    app.state.human_api_enabled=True;app.state.human_write_enabled=False
    async def rows():
        async with factory() as s:return {m.class_.__tablename__:[record_value(v) for v in
            (await s.scalars(select(m.class_).order_by(*m.class_.__table__.primary_key.columns))).all()] for m in Base.registry.mappers}
    before=await rows();responses=[];content=ContentService(platform)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-cold-fixture',headers={'Authorization':'Bearer '+token}) as c:
            projects=[outcome['master_project_id'],*[p['project_id'] for p in outcome['children']]]
            for project in projects:
                current=await timeline.get_timeline(project);script=await content.latest(project)
                assert current and script and script.snapshot['content']['approved']
                for suffix in ('production-package','production-history'):
                    r=await c.get(f'/api/v1/projects/{project}/{suffix}');assert r.status_code==200
                    responses.append({'path':suffix,'project_id':project,'status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),'json':r.json()})
                async with factory() as s:
                    from app.production_db import ProductionRenderJobORM
                    renders=(await s.scalars(select(ProductionRenderJobORM).where(ProductionRenderJobORM.project_id==project,
                        ProductionRenderJobORM.status.in_(['awaiting_review','ready'])))).all()
                assert len(renders)==2
                for render in renders:
                    r=await c.get(f'/api/v1/projects/{project}/renders/{render.render_id}');assert r.status_code==200
                    asset=await assets.get_asset(render.output_asset_id)
                    media=await c.get(f'/api/v1/projects/{project}/renders/{render.render_id}/content');assert media.status_code==200
                    assert hashlib.sha256(media.content).hexdigest()==asset.checksum_sha256 and len(media.content)==asset.size_bytes
                    responses.append({'render_id':render.render_id,'project_id':project,'status':r.status_code,
                        'body_sha256':hashlib.sha256(r.content).hexdigest(),'media_sha256':asset.checksum_sha256,'bytes':asset.size_bytes})
            for child in outcome['children']:
                p=original/'children'/child['profile']['target']/'narration-receipt.json';receipt=json.loads(p.read_bytes())
                route=f"/api/v1/projects/{outcome['master_project_id']}/variant-families/{outcome['family_id']}/children/{child['project_id']}/narration-receipts/{receipt['receipt_id']}"
                response=await c.get(route);assert response.status_code==200 and response.json()==receipt
            blocked=await c.post('/api/v1/projects/'+outcome['master_project_id']+'/review-render',content=b'{not parsed}')
            assert blocked.status_code in {403,503}
        assert before==await rows() and sha(target/'restored.db')==db_sha and files(original)==baseline
        report={'schema_version':'sql-spoken-six-cold-proof.v1','status':'ACTUAL_VIEWER_SQL_MEDIA_COLD_PASSED','source_root':str(original),
            'target_root':str(target),'original_all_file_hashes_unchanged':True,'restored_db_sha256':db_sha,'restored_db_unchanged':True,
            'table_counts':{k:len(v) for k,v in before.items()},'API_responses':responses,'model_inferences':0,'provider_calls':0,
            'workers':0,'lifespan':0,'Redis':0,'Viewer_only':True,'Owner_UAT':False,'source_object_manifest':files(target/'objects')}
        write(target/'cold-proof.json',report);print(json.dumps({'status':report['status'],'response_count':len(responses),'report_sha256':sha(target/'cold-proof.json')}))
        return 0
    finally:await engine.dispose()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--target',type=Path,required=True)
    raise SystemExit(asyncio.run(run(p.parse_args())))
