"""Owned SQLite/ASGI producer process; actual exit after core transaction commit."""
import asyncio,json,os,sys
from pathlib import Path
from types import SimpleNamespace
import httpx
from app.db import create_engine,create_session_factory
from app.repositories import PlatformRepository
from test_service_api import application,signed
from test_agent_hub_bridge import FakeRedis

async def main():
    root=Path(sys.argv[1]).resolve();marker=json.loads((root/'fixture.json').read_bytes())
    assert marker['real_provider_calls']==0 and marker['Owner_UAT'] is False
    engine=create_engine('sqlite+aiosqlite:///'+(root/'bridge.db').as_posix());factory=create_session_factory(engine)
    platform=PlatformRepository(factory);workspace=await platform.get_workspace(marker['workspace_id'])
    app=application(SimpleNamespace(platform=platform,workspace=workspace,redis=FakeRedis()))
    if sys.argv[2]=='crash':
        async def crash(*_):os._exit(71)
        app.state.service_api_repository.complete=crash
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://explicit-process-fixture') as client:
            response=await signed(client,'POST','/v1/projects',{'workspace_id':workspace.workspace_id,
                'slug':'actual-process-recovery-fixture','name':'Explicit fresh process fixture','niche':'technology'},
                key='actual-process-recovery-fixture-key')
            print(json.dumps({'pid':os.getpid(),'status':response.status_code,'result':response.json(),
                'idempotent_replay':response.headers.get('X-Idempotent-Replay'),'real_provider_calls':0,'Owner_UAT':False}),flush=True)
    finally:await engine.dispose()

if __name__=='__main__':asyncio.run(main())
