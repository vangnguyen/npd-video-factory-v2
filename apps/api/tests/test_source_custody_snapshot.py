"""Coherent point-in-time SQLite custody reads; owned rows, no inference."""
import asyncio
import threading

import pytest
from sqlalchemy import select,text
from sqlalchemy.ext.asyncio import AsyncSession,async_sessionmaker,create_async_engine

from app.auto_edit_db import AutoEditAnalysisORM,SceneORM
from app.auto_edit_repository import AutoEditRepository
from app.db import AssetORM,VideoProjectORM
from app.frozen_storage_read import asset_custody
from app.timeline_service import PreviewCancelledError
from test_bounded_service_sources import source,env,preview_fixture


@pytest.mark.asyncio
async def test_sqlite_wal_read_graph_has_one_snapshot_across_concurrent_committed_writer(source):
    async with source.engine.connect() as connection:
        assert (await connection.scalar(text('PRAGMA journal_mode=WAL'))).lower()=='wal'
    entered,release=asyncio.Event(),asyncio.Event()
    class PausedReadSession(AsyncSession):
        async def scalars(self,statement,*args,**kwargs):
            result=await super().scalars(statement,*args,**kwargs)
            if 'FROM assets' in str(statement):
                entered.set();await release.wait()
            return result
    reads=AutoEditRepository(async_sessionmaker(source.engine,class_=PausedReadSession,expire_on_commit=False))
    second=create_async_engine(source.engine.url)
    writers=async_sessionmaker(second,expire_on_commit=False)
    before_base=source.base.model_dump(mode='json');before_asset=asset_custody(source.asset)
    before_project=await source.platform.get_project(source.project.project_id)
    task=asyncio.create_task(reads.read_source_snapshot(project_id=source.project.project_id,
        asset_ids=(source.asset.asset_id,),analysis_id=source.base.analysis_id))
    try:
        await asyncio.wait_for(entered.wait(),5)
        async with writers() as session,session.begin():
            asset=await session.get(AssetORM,source.asset.asset_id);asset.version+=1
            analysis=await session.get(AutoEditAnalysisORM,source.base.analysis_id)
            analysis.provenance_json={**analysis.provenance_json,'writer_committed_fixture':True}
            scene=await session.scalar(select(SceneORM).where(SceneORM.analysis_id==source.base.analysis_id))
            scene.evidence_json={**scene.evidence_json,'writer_committed_fixture':True}
            project=await session.get(VideoProjectORM,source.project.project_id);project.version+=1
        # WAL writer committed while the separate read session is still paused.
        assert not task.done()
        release.set();snapshot=await task
        assert snapshot['analysis'].model_dump(mode='json')==before_base
        assert asset_custody(snapshot['assets'][source.asset.asset_id])==before_asset
        assert snapshot['project']['version']==before_project.version
        current=await source.repo.read_source_snapshot(project_id=source.project.project_id,
            asset_ids=(source.asset.asset_id,),analysis_id=source.base.analysis_id)
        assert current['assets'][source.asset.asset_id].version==source.asset.version+1
        assert current['analysis'].provenance['writer_committed_fixture'] is True
        assert current['analysis'].scenes[0].evidence['writer_committed_fixture'] is True
        assert current['project']['version']==before_project.version+1
    finally:
        release.set();await asyncio.gather(task,return_exceptions=True);await second.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('changed',['analysis','asset','project','provider'])
async def test_vision_final_coherent_await_checks_current_graph_and_provider(source,changed):
    original=source.repo.read_source_snapshot;calls=[]
    async def final_read(**kwargs):
        calls.append(kwargs)
        if changed=='provider':source.vision.provider.model='explicit-late-drift'
        else:
            async with source.sessions() as session,session.begin():
                if changed=='analysis':
                    row=await session.get(AutoEditAnalysisORM,source.base.analysis_id)
                    row.provenance_json={**row.provenance_json,'late_fixture_change':True}
                elif changed=='asset':
                    row=await session.get(AssetORM,source.asset.asset_id);row.version+=1
                else:
                    row=await session.get(VideoProjectORM,source.project.project_id);row.version+=1
        return await original(**kwargs)
    source.repo.read_source_snapshot=final_read
    with pytest.raises(ValueError,match='CUSTODY_CHANGED'):
        await source.vision._download_vision_source(source.base,source.asset,source.tmp/'source')
    assert len(calls)==1 and source.asr.calls==source.signals.calls==0


@pytest.mark.asyncio
async def test_preview_all_source_rows_are_checked_after_last_asset_hash_wait(env,monkeypatch):
    import app.timeline_service as module
    service,preview,first,renderer=await preview_fixture(env)
    # A second independent registered asset, preserving both source histories.
    from app.platform_models import AssetRegister
    path=env.tmp/'second.png';path.write_bytes((env.tmp/'input.png').read_bytes())
    stored=await env.storage.put_file(object_key=f'workspaces/{env.workspace.workspace_id}/projects/{env.project.project_id}/inputs/second.png',
        path=path,content_type='image/png')
    second=await env.platform.register_asset(env.project.project_id,AssetRegister(asset_class='source',kind='image',
        filename='second.png',object_key=stored.object_key,content_type=stored.content_type,size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256,storage_provider='local',provenance={'fixture':True,'rights_status':'owned'}))
    targets=[]
    for ordinal,asset in enumerate((first,second)):
        target=env.tmp/f'admitted{ordinal}.png'
        await service._download_preview_asset(preview,asset,target);targets.append(target)
    assets={first.asset_id:(first,targets[0]),second.asset_id:(second,targets[1])}
    original=module.sha256_file;entered,release=threading.Event(),threading.Event()
    def pause_last(target):
        value=original(target)
        if target==targets[1]:entered.set();assert release.wait(10)
        return value
    monkeypatch.setattr(module,'sha256_file',pause_last)
    task=asyncio.create_task(service._assert_preview_sources_current(preview,assets))
    try:
        assert await asyncio.to_thread(entered.wait,5)
        async with env.factory() as session,session.begin():
            row=await session.get(AssetORM,first.asset_id);row.version+=1
        release.set()
        with pytest.raises(RuntimeError,match='CUSTODY_CHANGED'):await task
        assert renderer.render.calls==0
    finally:release.set();await asyncio.gather(task,return_exceptions=True)
