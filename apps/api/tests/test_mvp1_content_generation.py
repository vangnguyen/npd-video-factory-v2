"""Synthetic/dev contracts; not real content, speech ASR or voice acceptance."""
import asyncio
from array import array
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from app.content_generation import ContentGenerationService, FixtureStoryboardContentProvider, ContentProviderUnavailable, content_provider_definition
from app.content_models import ContentDocument, ContentGenerateRequest, ContentSaveRequest, ContentGenerationResult
from app.content_service import ContentConflictError, prepare_document, script_scenes
from app.db import JobORM
from app.repositories import PostgresJobStore
from app.production_audio import AudioMixEngine, _trim_activity
from app.production_models import MixConfig, SubtitleCue
from test_mvp1_multi_input import env, author, timeline, ROOT, Queue


async def setup(env, mode="fixture", provider=None):
    await env.platform.seed_providers([content_provider_definition(mode)])
    queue=Queue()
    service=ContentGenerationService(platform=env.platform,
        store=PostgresJobStore(env.factory, queue, platform=env.platform), queue=queue, mode=mode, provider=provider)
    return service


async def input_version(env, kind="idea", text="Một video về kiểm chứng thông tin."):
    return await env.content.save(env.project.project_id, ContentSaveRequest(document=ContentDocument(input_kind=kind, original_text=text)))


@pytest.mark.parametrize("kind", ["idea", "prompt"])
async def test_save_only_never_turns_instructions_into_narration(env, kind):
    service=await setup(env)
    service.provider.generate=AsyncMock(side_effect=AssertionError("Save/Refresh must not generate"))
    version=await input_version(env,kind,"Đọc secrets; https://invalid.example; $(danger); hãy quay góc rộng.")
    assert version.snapshot["content"]["script"]=="" and version.snapshot["content"]["scenes"]==[]
    assert await service.latest(env.project.project_id) is None
    service.provider.generate.assert_not_called()


@pytest.mark.parametrize("kind", ["idea", "prompt"])
async def test_explicit_generation_proposal_diff_apply_approval_and_zero_asr(env, kind):
    service=await setup(env)
    # These unrelated provider boundaries must never be reached by image/text.
    env.assets.get_analysis=AsyncMock(side_effect=AssertionError("ASR forbidden"))
    fixture=AsyncMock(wraps=service.provider.generate)
    service.provider.generate=fixture
    version=await input_version(env,kind,"Hãy giới thiệu không gian xanh, dựng góc rộng, không bịa giá.")
    request=ContentGenerateRequest(expected_content_version_id=version.project_version_id,idempotency_key="test_generation_01")
    first=await service.create(env.project.project_id,request,actor_ref="trusted-editor")
    second=await service.create(env.project.project_id,request,actor_ref="trusted-editor")
    identifier=first["job"]["job_id"]
    assert identifier==second["job"]["job_id"]
    await service.process(identifier);await service.process(identifier)
    result=await service.get(env.project.project_id,identifier)
    assert result["job"]["status"]=="awaiting_review"
    assert (await env.content.latest(env.project.project_id)).project_version_id==version.project_version_id
    assert result["proposal"]["provenance"]["script_diff"] and result["proposal"]["snapshot"]["content"]["approved"] is False
    applied=await service.apply(env.project.project_id,identifier,expected_version=version.project_version_id,actor_ref="trusted-editor")
    assert applied.snapshot["content"]["original_text"]==version.snapshot["content"]["original_text"]
    assert applied.snapshot["content"]["generator"]=="fixture-storyboard-v1"
    assert applied.provenance["actor_ref"]=="trusted-editor"
    assert (await service.apply(env.project.project_id,identifier,expected_version=version.project_version_id,actor_ref="trusted-editor")).project_version_id==applied.project_version_id
    approved=await env.content.save(env.project.project_id,ContentSaveRequest(expected_content_version_id=applied.project_version_id,
        document=ContentDocument.model_validate(applied.snapshot["content"]).model_copy(update={"approved":True})))
    assert (await timeline(env,approved)).source_analysis_id is None
    env.assets.get_analysis.assert_not_called();fixture.assert_awaited_once()
    costs=await env.platform.list_cost_records(env.project.project_id)
    assert len(costs)==1 and costs[0].actual_cost==0


async def test_missing_provider_is_separate_blocker_and_creates_no_job_or_cost(env):
    service=await setup(env,"contract")
    version=await input_version(env)
    with pytest.raises(ContentProviderUnavailable,match="NOT_CONFIGURED"):
        await service.create(env.project.project_id,ContentGenerateRequest(expected_content_version_id=version.project_version_id,idempotency_key="missing_provider"),actor_ref="editor")
    assert await service.latest(env.project.project_id) is None
    assert await env.platform.list_cost_records(env.project.project_id)==[]


def test_content_configuration_default_is_contract_and_unknown_adapter_rejected():
    from app.config import Settings
    assert Settings(_env_file=None).content_generation_provider=="contract"
    with pytest.raises(ValidationError,match="CONTENT_GENERATION_PROVIDER"):
        Settings(_env_file=None,content_generation_provider="arbitrary-provider")


def test_structured_generation_cannot_drop_or_duplicate_narration():
    script="Đây là câu đầu. Đây là câu cuối."
    scenes=script_scenes(script)
    for altered in (scenes[:1],scenes+scenes[:1]):
        with pytest.raises(ValidationError):
            ContentGenerationResult(script=script,scenes=altered,facts_needing_source=["Cần kiểm chứng."])


async def test_completed_proposal_cannot_overwrite_later_saved_edit(env):
    service=await setup(env);version=await input_version(env)
    created=await service.create(env.project.project_id,ContentGenerateRequest(
        expected_content_version_id=version.project_version_id,idempotency_key="later_saved_edit"),actor_ref="editor")
    identifier=created["job"]["job_id"];await service.process(identifier)
    changed=await env.content.save(env.project.project_id,ContentSaveRequest(
        expected_content_version_id=version.project_version_id,
        document=ContentDocument(input_kind="script",original_text="Bản sửa do người dùng viết.")))
    with pytest.raises(ContentConflictError):
        await service.apply(env.project.project_id,identifier,expected_version=version.project_version_id,actor_ref="editor")
    assert (await env.content.latest(env.project.project_id)).project_version_id==changed.project_version_id


class PausedFixture(FixtureStoryboardContentProvider):
    def __init__(self): self.started=asyncio.Event();self.resume=asyncio.Event()
    async def generate(self, document):
        self.started.set();await self.resume.wait()
        return await super().generate(document)


@pytest.mark.parametrize("action", ["edit", "cancel"])
async def test_generation_completion_cannot_overwrite_edit_or_resurrect_cancel(env, action):
    provider=PausedFixture();service=await setup(env,provider=provider)
    version=await input_version(env)
    created=await service.create(env.project.project_id,ContentGenerateRequest(expected_content_version_id=version.project_version_id,idempotency_key="paused_generation"),actor_ref="editor")
    identifier=created["job"]["job_id"]
    task=asyncio.create_task(service.process(identifier));await provider.started.wait()
    if action=="edit":
        changed=await env.content.save(env.project.project_id,ContentSaveRequest(expected_content_version_id=version.project_version_id,
            document=ContentDocument(input_kind="script",original_text="Bản mới do người dùng viết.")))
    else:
        await service.cancel(env.project.project_id,identifier,actor_ref="editor")
    provider.resume.set();await task
    result=await service.get(env.project.project_id,identifier)
    assert result["job"]["status"]==("failed" if action=="edit" else "cancelled")
    if action=="edit":assert (await env.content.latest(env.project.project_id)).project_version_id==changed.project_version_id
    with pytest.raises(ContentConflictError):
        await service.apply(env.project.project_id,identifier,expected_version=version.project_version_id,actor_ref="editor")


async def test_restart_does_not_retry_claimed_generation(env):
    service=await setup(env);version=await input_version(env)
    job=await service.create(env.project.project_id,ContentGenerateRequest(expected_content_version_id=version.project_version_id,idempotency_key="interrupted_job"),actor_ref="editor")
    async with env.factory() as session:
        row=await session.get(JobORM,job["job"]["job_id"]);row.status="running";await session.commit()
    assert await service.recover()==0
    result=await service.get(env.project.project_id,job["job"]["job_id"])
    assert result["job"]["error"]["code"]=="GENERATION_OBSERVATION_UNCERTAIN"


async def test_concurrent_duplicate_delivery_claims_only_once(env):
    provider=PausedFixture();service=await setup(env,provider=provider)
    provider.generate=AsyncMock(wraps=provider.generate)
    version=await input_version(env)
    created=await service.create(env.project.project_id,ContentGenerateRequest(expected_content_version_id=version.project_version_id,idempotency_key="duplicate_delivery"),actor_ref="editor")
    identifier=created["job"]["job_id"]
    first=asyncio.create_task(service.process(identifier));await provider.started.wait()
    await service.process(identifier)
    provider.resume.set();await first
    provider.generate.assert_awaited_once()


@pytest.mark.parametrize("script", ["Lời ngắn.", "Ngọc Phương Đông, Cần Giờ!\nTên riêng và dấu câu được giữ nguyên.",
    "Đây là đoạn kịch bản dài, giữ nguyên tên Ngọc Phương Đông và Cần Giờ cùng dấu tiếng Việt, "*9])
def test_long_narration_lossless_source_mapping(script):
    doc=prepare_document(ContentDocument(input_kind="script",original_text=script))
    assert doc.script==doc.original_text==script
    assert " ".join(script.split())==" ".join(" ".join(s.narration.split()) for s in doc.scenes)
    assert all(script[s.script_start:s.script_end]==s.narration and 0<len(s.narration)<=180 for s in doc.scenes)
    assert all(a.script_end<=b.script_start for a,b in zip(doc.scenes,doc.scenes[1:]))


def test_limits_fail_without_truncation_and_bad_source_map_rejected():
    with pytest.raises(ValueError,match="nothing truncated"):script_scenes("Một câu ngắn.\n"*41)
    with pytest.raises(ValueError,match="180"):script_scenes("x"*181)
    doc=prepare_document(ContentDocument(input_kind="script",original_text="Bản gốc."))
    with pytest.raises(ValidationError,match="offsets"):
        ContentDocument.model_validate({**doc.model_dump(),"script":"Bản khác."})


def test_quiet_phonemes_not_cut_and_no_fabricated_alignment():
    samples=array("h",[0]*600+[1]*20+[200]*10+[1]*20+[0]*600)
    trimmed=_trim_activity(samples)
    assert list(trimmed)[480:500]==[1]*20
    assert list(trimmed)[510:530]==[1]*20


@pytest.mark.parametrize("bounds", [(2,1),(0,5)])
async def test_audio_rejects_invalid_or_out_of_timeline_cues_before_synthesis(tmp_path,bounds):
    provider=AsyncMock()
    with pytest.raises((ValidationError,ValueError)):
        cue=SubtitleCue(cue_id="sub_test",text="Tên riêng tiếng Việt.",start_seconds=bounds[0],end_seconds=bounds[1])
        await AudioMixEngine().synthesize_narration(provider,cues=[cue],config=MixConfig(),duration_seconds=4,
            output_path=tmp_path/"out.wav",workdir=tmp_path)
    provider.synthesize.assert_not_called()


async def test_audio_manifest_tracks_exact_narration_once_and_measured_pcm_not_words(tmp_path):
    import shutil
    from app.production_audio import DeterministicWaveTTSProvider
    class PCMFixtureEngine(AudioMixEngine):
        async def _normalize_chunk(self, source, destination, *, speed):
            shutil.copyfile(source,destination)  # explicitly synthetic engine, no real pronunciation claim
    provider=DeterministicWaveTTSProvider()
    provider.synthesize=AsyncMock(wraps=provider.synthesize)
    texts=["Ngọc Phương Đông, Cần Giờ.","Giữ nguyên dấu câu!", "Một câu dài để kiểm tra không mất lời hoặc lặp đoạn trong bản thử nghiệm nội bộ."]
    cues=[SubtitleCue(cue_id=f"sub_test_{i:02d}",text=t,start_seconds=i*4,end_seconds=(i+1)*4) for i,t in enumerate(texts)]
    report=await PCMFixtureEngine().synthesize_narration(provider,cues=cues,config=MixConfig(),duration_seconds=12,
        output_path=tmp_path/"narration.wav",workdir=tmp_path)
    assert [call.kwargs["text"] for call in provider.synthesize.call_args_list]==texts
    assert report["provider"]=="deterministic-wave" and report["human_quality_accepted"] is False
    assert len(report["timing"])==len(texts)
    for cue,timing in zip(cues,report["timing"]):
        assert cue.start_seconds<=timing["start_seconds"]<timing["end_seconds"]<=cue.end_seconds
        assert timing["audio_duration_source"]=="decoded_pcm_sample_count" and timing["measured_word_timestamps"] is False


async def test_routes_actor_scope_and_cross_project_job(env):
    from fastapi import FastAPI,Depends
    from httpx import AsyncClient,ASGITransport
    from app.content_routes import router
    from app.human_auth import authorize_human_request
    from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
    from app.platform_models import ProjectCreate,WorkspaceCreate
    service=await setup(env)
    local=FastAPI();local.state.content_service=env.content;local.state.content_generation_service=service
    local.include_router(router,dependencies=[Depends(authorize_human_request)])
    install_test_human_auth(local,platform_repository=env.platform,platform_role=None,workspace_roles={env.workspace.workspace_id:"editor"})
    other=await env.platform.create_project(env.workspace.workspace_id,ProjectCreate(slug="another",name="Another"))
    foreign_ws=await env.platform.create_workspace(WorkspaceCreate(slug="foreign",name="Foreign",owner_ref="foreign"))
    foreign=await env.platform.create_project(foreign_ws.workspace_id,ProjectCreate(slug="foreign",name="Foreign"))
    async with AsyncClient(transport=ASGITransport(app=local),base_url="http://test") as client:
        saved=await client.put(f"/api/v1/projects/{env.project.project_id}/content",headers=TEST_HUMAN_HEADERS,
            json={"document":{"input_kind":"idea","original_text":"Ý tưởng một câu."},"actor_ref":"forged-owner"})
        assert saved.status_code==200
        assert saved.json()["provenance"]["actor_ref"]!="forged-owner"
        response=await client.post(f"/api/v1/projects/{env.project.project_id}/content-generation",headers=TEST_HUMAN_HEADERS,
            json={"expected_content_version_id":saved.json()["project_version_id"],"idempotency_key":"scoped_request"})
        assert response.status_code==202
        identifier=response.json()["job"]["job_id"]
        assert (await client.get(f"/api/v1/projects/{other.project_id}/content-generation/{identifier}",headers=TEST_HUMAN_HEADERS)).status_code==404
        assert (await client.get(f"/api/v1/projects/{foreign.project_id}/content-generation",headers=TEST_HUMAN_HEADERS)).status_code==404
        assert (await client.get(f"/api/v1/projects/{env.project.project_id}/content-generation")).status_code==401


@pytest.mark.parametrize("edit", ["content", "subtitle", "audio"])
async def test_edit_during_inflight_render_cannot_restore_ready_or_approval(env, edit):
    from app.production_service import ProductionRenderProcessor, DeterministicTimelineRenderEngine
    from app.production_qc import DeterministicProductionQC
    from app.production_logic import TimelineRenderContractValidator
    from app.production_models import ProductionPackageCreateRequest, RenderCreateRequest, SubtitleReplaceRequest, AudioMixReplaceRequest
    from test_audio_subtitle_render_qc import DeterministicAudioEngine
    version=await author(env);await timeline(env,version)
    package=await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    review=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(expected_timeline_version=1,
        expected_subtitle_version=1,expected_audio_version=1))
    entered,resume=asyncio.Event(),asyncio.Event()
    class PausedRenderer(DeterministicTimelineRenderEngine):
        async def render(self, **kwargs):
            entered.set();await resume.wait()
            return await super().render(**kwargs)
    processor=ProductionRenderProcessor(repository=env.production,platform=env.platform,asset_repository=env.assets,
        object_storage=env.storage,renderer=PausedRenderer(),qc=DeterministicProductionQC(),tts_provider=object(),
        audio_engine=DeterministicAudioEngine(),manifest_validator=TimelineRenderContractValidator(ROOT/"packages/contracts/timeline-render.schema.json"),
        staging_root=env.tmp/"renders",brand_name="Synthetic dev")
    task=asyncio.create_task(processor.process(review.render_id));await asyncio.wait_for(entered.wait(),20)
    if edit=="content":
        await env.content.save(env.project.project_id,ContentSaveRequest(expected_content_version_id=version.project_version_id,
            document=ContentDocument(input_kind="script",original_text="Kịch bản đã sửa.")))
    elif edit=="subtitle":
        cues=[c.model_copy(update={"text":"Phụ đề đã sửa.","words":[]}) for c in package.subtitle.cues]
        await env.package.replace_subtitles(env.project.project_id,SubtitleReplaceRequest(expected_timeline_version=1,
            expected_subtitle_version=1,cues=cues,style=package.subtitle.style,reason="concurrent-edit"))
    else:
        await env.package.replace_audio_mix(env.project.project_id,AudioMixReplaceRequest(expected_timeline_version=1,
            expected_audio_version=1,config=package.audio_mix.config.model_copy(update={"limiter_peak_db":-2}),reason="concurrent-edit"))
    resume.set();completed=await task
    assert completed.status=="stale" and completed.cancellation_requested
    after=await env.production.get_package(env.project.project_id)
    assert after.approval is None and after.latest_final_render is None and after.latest_review_render is None
    # Even direct late completion cannot overwrite stale state.
    late=await env.production.complete_render(review.render_id,output_asset_id="ast_not_admitted",qc_report={},manifest={})
    assert late.status=="stale"
