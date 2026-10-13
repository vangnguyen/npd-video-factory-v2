"""Final completion races after the approved PCM has already been copied."""
import asyncio
import copy
import httpx
import pytest
from sqlalchemy import update
from app.main import app
from app.production_db import AudioMixVersionORM
from app.production_models import ApprovalRequest
from app.production_service import DeterministicTimelineRenderEngine
from app.content_models import ContentDocument,ContentSaveRequest
from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
from test_sql_tts_artifact_reuse import env,ready,processor,final


@pytest.mark.asyncio
@pytest.mark.parametrize('writer',['generic_content','new_approval','audio_config_hash','content_save'])
async def test_completion_rechecks_current_approval_and_content_after_renderer(env,writer):
    state,job,version,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    target=await final(env,reviewed)
    entered=asyncio.Event();resume=asyncio.Event()
    class PausedRenderer(DeterministicTimelineRenderEngine):
        async def render(self,**args):
            entered.set();await resume.wait()
            return await super().render(**args)
    class DeniedProvider:
        def __getattr__(self,name):raise AssertionError('Final completion never calls provider: '+name)
    process=processor(env,DeniedProvider());process.renderer=PausedRenderer()
    task=asyncio.create_task(process.process(target.render_id))
    try:
        await asyncio.wait_for(entered.wait(),10)
        if writer=='generic_content':
            install_test_human_auth(app,platform_repository=env.platform,platform_role=None,
                workspace_roles={env.workspace.workspace_id:'editor'})
            value=copy.deepcopy(version.snapshot);value['content']['script']='Explicit changed completion fixture.'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture',
                    headers=TEST_HUMAN_HEADERS) as client:
                response=await client.post(f'/api/v1/projects/{env.project.project_id}/versions',
                    json={'label':'mvp1-content','snapshot':value,'provenance':{'fixture':True}})
            assert response.status_code==201,response.text
            assert (await env.production.get_render(target.render_id)).status=='running'
        elif writer=='new_approval':
            await env.package.request_approval(env.project.project_id,ApprovalRequest(review_render_id=reviewed.render_id))
            assert (await env.production.get_render(target.render_id)).status=='running'
        elif writer=='audio_config_hash':
            async with env.factory() as session,session.begin():
                audio=await session.get(AudioMixVersionORM,target.audio_version_id)
                value=copy.deepcopy(audio.config_json);value['voice']['gain_db']=1
                await session.execute(update(AudioMixVersionORM).where(AudioMixVersionORM.audio_version_id==audio.audio_version_id)
                    .values(config_json=value))
        else:
            from app.content_service import prepare_document
            document=prepare_document(ContentDocument(input_kind='script',original_text='Explicit standard save control.'))
            await env.content.save(env.project.project_id,ContentSaveRequest(expected_content_version_id=version.project_version_id,
                document=document.model_copy(update={'approved':True})))
        resume.set();result=await task
        assert result.status in {'failed','stale'},result.status
        if writer=='generic_content':assert 'TTS_REUSE_CONTENT_VERSION_STALE' in result.failure_reason
        if writer=='audio_config_hash':assert 'TTS_REUSE_CANONICAL_INPUT_CHANGED' in result.failure_reason
        if writer=='new_approval':assert 'current approved review' in result.failure_reason
        assert len(state['calls'])==1 and result.output_asset_id is None
        assert 'prepared_audio_reuse' not in result.manifest.get('narration',{})
    finally:
        resume.set()
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
