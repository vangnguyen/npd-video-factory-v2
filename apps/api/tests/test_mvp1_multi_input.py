"""Synthetic contract tests. No provider result is production acceptance."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from app.main import app  # registers all existing ORM tables
from app.db import Base, create_engine, create_session_factory
from app.auto_edit_repository import AutoEditRepository
from app.content_models import ContentDocument, ContentSaveRequest, StoryboardScene
from app.content_service import ContentService, ContentConflictError
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.media_intelligence_logic import plan_storyboard_media
from app.object_storage import LocalObjectStorageProvider
from app.platform_models import AssetRegister, ProjectCreate, WorkspaceCreate
from app.repositories import PlatformRepository
from app.storyboard_timeline import template_png
from app.timeline_service import TimelineService, TimelineContractValidator
from app.timeline_models import TimelineCreateRequest, TimelineClip
from app.timeline_repository import TimelineRepository
from app.timeline_logic import TimelineEditError
from app.production_repository import ProductionRepository
from app.production_service import ProductionPackageService, ProductionRenderProcessor, DeterministicTimelineRenderEngine
from app.production_logic import derive_subtitle_cues, TimelineRenderContractValidator, ProductionContractError
from app.production_models import ProductionPackageCreateRequest, RenderCreateRequest, ApprovalRequest, ApprovalDecisionRequest, FinalRenderCreateRequest
from app.production_qc import DeterministicProductionQC
from test_audio_subtitle_render_qc import DeterministicAudioEngine

ROOT = Path(__file__).resolve().parents[3]

class Queue:
    def __init__(self): self.values=[]
    async def rpush(self, key, value): self.values.append((key,value))

@pytest.fixture
async def env(tmp_path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path}/dev.db")
    async with engine.begin() as connection: await connection.run_sync(Base.metadata.create_all)
    factory=create_session_factory(engine)
    platform=PlatformRepository(factory)
    await platform.seed_providers([{ "provider_key":key,"display_name":key,"capability":cap,
        "adapter":"offline-test","routing_mode":"primary","status":"healthy","enabled":True,
        "supports_dry_run":True,"metadata":{"paid":False,"fixture":True}}
        for key,cap in [("espeak","tts"),("remotion","rendering")]])
    workspace=await platform.create_workspace(WorkspaceCreate(slug="mvp-dev",name="MVP",owner_ref="dev"))
    project=await platform.create_project(workspace.workspace_id,ProjectCreate(slug="mvp-proof",name="MVP proof"))
    storage=LocalObjectStorageProvider(tmp_path/"objects");await storage.ensure_ready()
    assets=AutoEditRepository(factory); timeline=TimelineRepository(factory); queue=Queue()
    service=TimelineService(repository=timeline,platform=platform,auto_edit_repository=assets,
        media_repository=MediaIntelligenceRepository(factory), object_storage=storage,
        validator=TimelineContractValidator(ROOT/"packages/contracts/timeline.schema.json"))
    content=ContentService(platform); production=ProductionRepository(factory)
    package=ProductionPackageService(repository=production,timeline_repository=timeline,asset_repository=assets,
        queue=queue,settings=SimpleNamespace(audio_tts_provider="espeak"))
    yield SimpleNamespace(engine=engine,factory=factory,platform=platform,workspace=workspace,project=project,
        storage=storage,assets=assets,timeline=timeline,service=service,content=content,production=production,
        package=package,queue=queue,tmp=tmp_path)
    await engine.dispose()

async def image(env, project=None, rights="owned"):
    project=project or env.project
    path=env.tmp/"input.png";path.write_bytes(template_png())
    stored=await env.storage.put_file(object_key=f"workspaces/{project.workspace_id}/projects/{project.project_id}/inputs/photo.png",path=path,content_type="image/png")
    return await env.platform.register_asset(project.project_id,AssetRegister(asset_class="source",kind="image",filename="photo.png",object_key=stored.object_key,content_type=stored.content_type,size_bytes=stored.size_bytes,checksum_sha256=stored.checksum_sha256,storage_provider="local",provenance={"rights_status":rights,"media_metadata":{"width":270,"height":480,"duration_seconds":None}}))

async def author(env, scenes=None, kind="script", original="Đây là ảnh được phép sử dụng."):
    from app.content_service import prepare_document
    document=prepare_document(ContentDocument(input_kind=kind,original_text=original,scenes=scenes or []))
    return await env.content.save(env.project.project_id,ContentSaveRequest(document=document.model_copy(update={"approved":True})))

async def timeline(env, version, kind="storyboard_media", expected=None):
    return await env.service.create(env.project.project_id,TimelineCreateRequest(source_kind=kind,
        content_version_id=version.project_version_id,expected_timeline_version=expected))

@pytest.mark.parametrize("kind",["script","idea"])
async def test_text_only_persists_restart_and_timeline_without_asr(env,kind):
    poison=Mock(side_effect=AssertionError("image/text must never use ASR, resolver or budget"))
    env.assets.get_analysis=poison
    version=await author(env,kind=kind)
    loaded=await ContentService(PlatformRepository(env.factory)).latest(env.project.project_id)
    assert loaded.snapshot==version.snapshot
    built=await timeline(env,version)
    assert built.source_analysis_id is None and built.source_kind=="storyboard_media"
    assert built.snapshot.tracks[0].clips[0].source_end is None
    assert derive_subtitle_cues(built.snapshot)[0].words==[]
    poison.assert_not_called()
    assert (await timeline(env,version)).current_version==1
    assert (await author(env,kind=kind)).project_version_id==version.project_version_id

async def test_prompt_keeps_creative_instructions_separate(env):
    prompt="Hãy dùng góc quay rộng. Không bịa giá bán."
    version=await env.content.save(env.project.project_id,ContentSaveRequest(document=ContentDocument(input_kind="prompt",original_text=prompt)))
    assert version.snapshot["content"]["creative_instructions"]==prompt
    assert version.snapshot["content"]["script"]==""
    assert version.snapshot["content"]["scenes"]==[]
    with pytest.raises(TimelineEditError,match="APPROVAL"):
        await timeline(env,version)

async def test_prompt_with_explicit_narration_is_text_only_not_llm(env):
    from app.content_service import prepare_document
    prompt="Dùng bố cục sạch.\nLời đọc:\nĐây là nội dung được cung cấp.\nKhông tự thêm giá bán."
    doc=prepare_document(ContentDocument(input_kind="prompt",original_text=prompt))
    assert doc.original_text==prompt and doc.creative_instructions=="Dùng bố cục sạch."
    assert doc.script=="Đây là nội dung được cung cấp.\nKhông tự thêm giá bán."
    version=await env.content.save(env.project.project_id,ContentSaveRequest(document=doc.model_copy(update={"approved":True})))
    assert (await timeline(env,version)).source_analysis_id is None

def test_native_word_mapping_moves_without_inventing_intervals():
    from app.timeline_models import TimelineSnapshot, TimelineTrack
    clip=TimelineClip(clip_id="clip_words",kind="subtitle",label="Lời đọc",source_start=10,source_end=12,
        timeline_start=5,duration=2,metadata={"measured_source_words":[
            {"text":"Lời","start_seconds":10.2,"end_seconds":10.6},
            {"text":"đọc","start_seconds":11.0,"end_seconds":11.5}]})
    snapshot=TimelineSnapshot(duration_seconds=7,tracks=[TimelineTrack(track_id="trk_words",type="text",kind="subtitles",label="Words",order=0,clips=[clip])])
    cues=derive_subtitle_cues(snapshot)
    assert [(w.start_seconds,w.end_seconds) for w in cues[0].words]==[(5.2,5.6),(6,6.5)]

def test_historical_timeline_version_does_not_accept_still_extension():
    from app.timeline_models import TimelineSnapshot, TimelineTrack
    clip=TimelineClip(clip_id="clip_image",kind="image",label="Photo",duration=4,timeline_start=0)
    with pytest.raises(ValidationError,match="schema 1.1"):
        TimelineSnapshot(duration_seconds=4,tracks=[TimelineTrack(track_id="trk_image",type="video",kind="source",label="Photo",order=0,clips=[clip])])

@pytest.mark.parametrize("architecture",[False,True])
async def test_image_and_render_metadata_no_fake_duration(env,architecture):
    asset=await image(env)
    version=await author(env,[StoryboardScene(scene_id="scene_01",narration="Ảnh minh họa có nguồn.",media_strategy="user_asset",asset_id=asset.asset_id,architectural_render=architecture)])
    built=await timeline(env,version);clip=built.snapshot.tracks[0].clips[0]
    assert clip.source_end is None and clip.metadata["official_render"] is False
    assert clip.metadata["architectural_render"]==architecture
    assert asset.provenance["media_metadata"]["duration_seconds"] is None

async def test_cross_project_unknown_rights_and_official_render_fail(env):
    other=await env.platform.create_project(env.workspace.workspace_id,ProjectCreate(slug="other",name="Other"))
    cross=await image(env,other)
    version=await author(env,[StoryboardScene(scene_id="scene_01",narration="Test",media_strategy="user_asset",asset_id=cross.asset_id)])
    with pytest.raises(TimelineEditError,match="CROSS_PROJECT"): await timeline(env,version)
    foreign=await env.platform.get_version(version.project_version_id)
    with pytest.raises(KeyError): await env.service.create(other.project_id,TimelineCreateRequest(source_kind="storyboard_media",content_version_id=foreign.project_version_id))

async def test_explicit_ai_video_not_silently_downgraded(env):
    scene=StoryboardScene(scene_id="scene_01",narration="Nội dung",media_strategy="ai_video")
    version=await author(env,[scene]);plan=plan_storyboard_media(version.snapshot["content"])
    assert plan[0]["capability"]=="image_to_video" and plan[0]["status"]=="provider_not_configured"
    with pytest.raises(TimelineEditError,match="MEDIA_PROVIDER_NOT_CONFIGURED"):await timeline(env,version)
    assert (await env.content.latest(env.project.project_id)).snapshot==version.snapshot

async def test_spoken_video_cannot_bypass_analysis(env):
    path=env.tmp/"video.mp4";path.write_bytes(b"synthetic-not-media-test")
    stored=await env.storage.put_file(object_key=f"projects/{env.project.project_id}/video.mp4",path=path,content_type="video/mp4")
    asset=await env.platform.register_asset(env.project.project_id,AssetRegister(asset_class="source",kind="video",filename="video.mp4",object_key=stored.object_key,content_type="video/mp4",size_bytes=stored.size_bytes,checksum_sha256=stored.checksum_sha256,storage_provider="local",provenance={"rights_status":"owned"}))
    version=await author(env,[StoryboardScene(scene_id="scene_01",narration="Lời nói",media_strategy="user_asset",asset_id=asset.asset_id)])
    with pytest.raises(TimelineEditError,match="VIDEO_ANALYSIS_REQUIRED"):await timeline(env,version,"mixed")
    assert await env.timeline.get_timeline(env.project.project_id) is None

async def test_stale_content_and_versions_rejected(env):
    old=await author(env); built=await timeline(env,old)
    changed=ContentDocument.model_validate(old.snapshot["content"]).model_copy(update={"script":"Nội dung mới"})
    new=await env.content.save(env.project.project_id,ContentSaveRequest(expected_content_version_id=old.project_version_id,document=changed))
    with pytest.raises(TimelineEditError,match="STALE"):await timeline(env,old)
    with pytest.raises(ProductionContractError,match="STALE"):await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    with pytest.raises(ContentConflictError):await env.content.save(env.project.project_id,ContentSaveRequest(expected_content_version_id=old.project_version_id,document=changed.model_copy(update={"script":"Different"})))
    fresh=await timeline(env,new,expected=built.current_version)
    assert fresh.current_version==2 and fresh.source_content_version_id==new.project_version_id

async def test_review_final_approval_invalidates_on_edit_and_queue_idempotency(env):
    version=await author(env);await timeline(env,version)
    package=await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    processor=ProductionRenderProcessor(repository=env.production,platform=env.platform,asset_repository=env.assets,
        object_storage=env.storage,renderer=DeterministicTimelineRenderEngine(),qc=DeterministicProductionQC(),
        tts_provider=object(),audio_engine=DeterministicAudioEngine(),manifest_validator=TimelineRenderContractValidator(ROOT/"packages/contracts/timeline-render.schema.json"),staging_root=env.tmp/"renders",brand_name="Dev")
    request=RenderCreateRequest(expected_timeline_version=1,expected_subtitle_version=1,expected_audio_version=1)
    review=await env.package.enqueue_review(env.project.project_id,request)
    assert (await env.package.enqueue_review(env.project.project_id,request)).render_id==review.render_id
    completed=await processor.process(review.render_id)
    assert completed.status=="awaiting_review", completed.failure_reason
    approval=await env.package.request_approval(env.project.project_id,ApprovalRequest(review_render_id=review.render_id))
    approval=await env.package.decide_approval(env.project.project_id,approval.approval_id,ApprovalDecisionRequest(decision="approved",reviewer_ref="synthetic-test"))
    final_request=FinalRenderCreateRequest(expected_timeline_version=1,expected_subtitle_version=1,expected_audio_version=1,approval_id=approval.approval_id)
    final=await env.package.enqueue_final(env.project.project_id,final_request)
    assert (await processor.process(final.render_id)).status=="ready"
    document=ContentDocument.model_validate(version.snapshot["content"])
    edited=document.model_copy(update={"scenes":[document.scenes[0].model_copy(update={"narration":"Nội dung đã sửa."})]})
    await env.content.save(env.project.project_id,ContentSaveRequest(expected_content_version_id=version.project_version_id,document=edited))
    assert (await env.package.get_render(env.project.project_id,final.render_id)).status=="stale"
    with pytest.raises(ProductionContractError,match="STALE"):await env.package.enqueue_final(env.project.project_id,final_request)

@pytest.mark.parametrize("payload",[{}, {"source_kind":"storyboard_media"},{"source_kind":"mixed","analysis_id":"ana_fake"}])
def test_timeline_source_discriminator_requires_real_identity(payload):
    with pytest.raises(ValidationError):TimelineCreateRequest.model_validate(payload)

def test_image_cannot_fabricate_temporal_window():
    with pytest.raises(ValidationError):TimelineClip(clip_id="clip_image",kind="image",label="Photo",source_end=4,duration=4,timeline_start=0)

def test_limits_and_prompt_remains_inert():
    with pytest.raises(ValidationError):ContentDocument(input_kind="script",original_text="x"*20001)
    with pytest.raises(ValidationError):StoryboardScene(scene_id="../../secrets",narration="x")
    with pytest.raises(ValidationError):StoryboardScene(scene_id="scene_01",duration_seconds=999)
    injection="$(cat /etc/secret) <script>alert(1)</script>"
    doc=ContentDocument(input_kind="prompt",original_text=injection)
    from app.content_service import prepare_document
    assert prepare_document(doc).creative_instructions==injection

@pytest.mark.parametrize("case", ["unknown_rights", "unverified_official"])
async def test_image_rights_and_official_claims_are_not_inferred(env, case):
    asset = await image(env, rights="unknown" if case == "unknown_rights" else "owned")
    version = await author(env, [StoryboardScene(scene_id="scene_01", narration="Ảnh minh họa.",
        media_strategy="user_asset",asset_id=asset.asset_id,architectural_render=True,
        official_render=case == "unverified_official")])
    with pytest.raises(TimelineEditError, match="MEDIA_RIGHTS_REQUIRED|OFFICIAL_RENDER_PROVENANCE_REQUIRED"):
        await timeline(env, version)

async def test_real_no_audio_branch_does_not_create_synthetic_transcript_or_reserve(env):
    from app.auto_edit_service import AutoEditAnalysisService
    from app.auto_edit_providers import DeterministicMediaSignalProvider
    from app.auto_edit_models import AutoEditAnalysisRequest
    from unittest.mock import AsyncMock
    # Structural synthetic media metadata ONLY. Real ffprobe/FFmpeg proof is separate UI evidence.
    path=env.tmp/"silent.mp4";path.write_bytes(b"explicit-no-audio-structural-fixture")
    stored=await env.storage.put_file(object_key=f"projects/{env.project.project_id}/silent.mp4",path=path,content_type="video/mp4")
    asset=await env.platform.register_asset(env.project.project_id,AssetRegister(asset_class="source",kind="video",
        filename="silent.mp4",object_key=stored.object_key,content_type="video/mp4",size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256,storage_provider="local",provenance={"rights_status":"owned",
        "media_metadata":{"media_kind":"video","detected_content_type":"video/mp4","duration_seconds":6,"video_codec":"h264","audio_codec":None}}))
    boundary=SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("no ASR/budget boundary")))
    provider=SimpleNamespace(key="contract",model="none",transcribe=AsyncMock(side_effect=AssertionError("no ASR/resolver")))
    analysis_service=AutoEditAnalysisService(repository=env.assets,platform=env.platform,object_storage=env.storage,
        transcription_provider=provider,signal_provider=DeterministicMediaSignalProvider(),staging_root=env.tmp/"analysis",provider_safety=boundary)
    analysis=await analysis_service.analyze(env.project.project_id,AutoEditAnalysisRequest(asset_id=asset.asset_id))
    assert analysis.status=="succeeded" and analysis.transcript is None
    assert analysis.provenance["asr_state"]=="no_audio_stream"
    boundary.execute.assert_not_called();provider.transcribe.assert_not_called()
    version=await author(env,[StoryboardScene(scene_id="scene_01",narration="Video không có audio.",
        media_strategy="user_asset",asset_id=asset.asset_id,analysis_id=analysis.analysis_id,duration_seconds=6)])
    built=await timeline(env,version,"mixed")
    assert built.snapshot.tracks[0].clips[0].source_end==6
    assert not built.snapshot.tracks[2].clips
    # Existing MediaPlanner/B-roll consumer uses image display duration too.
    from app.timeline_logic import build_initial_timeline
    photo=await image(env)
    plan=SimpleNamespace(media_plan_id="mpl_dev",media_assets=[SimpleNamespace(media_asset_id="med_dev",
        asset_id=photo.asset_id,duration_seconds=None,source_type="owned",rights_status="owned",
        license="dev",production_eligible=True)],items=[SimpleNamespace(selected_media_asset_id="med_dev",
        media_plan_item_id="item_dev",broll=SimpleNamespace(placement_start_seconds=1,
            placement_end_seconds=3,search_query="Ảnh được phép"))])
    initial=build_initial_timeline(analysis=analysis,source_asset=asset,media_plan=plan,media_assets={photo.asset_id:photo})
    assert initial.schema_version=="1.1"
    assert initial.tracks[1].clips[0].kind=="image" and initial.tracks[1].clips[0].source_end is None
    env.service.validator.validate(initial)

async def test_cancelled_review_and_worker_replay_do_not_produce_duplicate_asset(env):
    version=await author(env);await timeline(env,version)
    await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    request=RenderCreateRequest(expected_timeline_version=1,expected_subtitle_version=1,expected_audio_version=1)
    review=await env.package.enqueue_review(env.project.project_id,request)
    await env.package.cancel_render(env.project.project_id,review.render_id,"test")
    processor=ProductionRenderProcessor(repository=env.production,platform=env.platform,asset_repository=env.assets,
        object_storage=env.storage,renderer=DeterministicTimelineRenderEngine(),qc=DeterministicProductionQC(),tts_provider=object(),
        audio_engine=DeterministicAudioEngine(),manifest_validator=TimelineRenderContractValidator(ROOT/"packages/contracts/timeline-render.schema.json"),staging_root=env.tmp/"renders",brand_name="Dev")
    assert (await processor.process(review.render_id)).status=="cancelled"
    assert (await processor.process(review.render_id)).output_asset_id is None
    assert await processor.recover_incomplete(env.queue)==0

def test_dev_migration_preserves_video_identity_and_rejects_empty_source(tmp_path):
    import importlib.util
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    spec=importlib.util.spec_from_file_location("mvp_migration",ROOT/"apps/api/migrations/versions/0016_mvp1_multi_input.py")
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    engine=sa.create_engine(f"sqlite:///{tmp_path}/migration.db")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE project_versions (project_version_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(sa.text("CREATE TABLE timelines (timeline_id VARCHAR(64) PRIMARY KEY, source_analysis_id VARCHAR(64) NOT NULL)"))
        connection.execute(sa.text("INSERT INTO timelines VALUES ('old','ana_existing')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(sa.text("SELECT source_analysis_id FROM timelines WHERE timeline_id='old'")).scalar()=="ana_existing"
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text("INSERT INTO timelines VALUES ('invalid',NULL,NULL)"))
        connection.execute(sa.text("INSERT INTO timelines VALUES ('story',NULL,'pver_dev')"))
        with Operations.context(MigrationContext.configure(connection)), pytest.raises(RuntimeError,match="cannot downgrade"):
            migration.downgrade()
    engine.dispose()

async def test_content_routes_reuse_workspace_and_role_admission(env):
    from fastapi import FastAPI, Depends
    from httpx import ASGITransport, AsyncClient
    from app.content_routes import router
    from app.human_auth import authorize_human_request
    from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
    local_app=FastAPI()
    local_app.state.content_service=env.content
    local_app.include_router(router,dependencies=[Depends(authorize_human_request)])
    install_test_human_auth(local_app,platform_repository=env.platform,platform_role=None,
        workspace_roles={env.workspace.workspace_id:"viewer"})
    other_ws=await env.platform.create_workspace(WorkspaceCreate(slug="other-ws",name="Other",owner_ref="other"))
    other=await env.platform.create_project(other_ws.workspace_id,ProjectCreate(slug="other",name="Other"))
    async with AsyncClient(transport=ASGITransport(app=local_app),base_url="http://test") as client:
        assert (await client.get(f"/api/v1/projects/{env.project.project_id}/content")).status_code==401
        assert (await client.get(f"/api/v1/projects/{other.project_id}/content",headers=TEST_HUMAN_HEADERS)).status_code==404
        assert (await client.put(f"/api/v1/projects/{env.project.project_id}/content",headers=TEST_HUMAN_HEADERS,
            json={"document":{"input_kind":"script","original_text":"Nội dung"}})).status_code==403
        assert (await client.get(f"/api/v1/projects/{env.project.project_id}/content",headers=TEST_HUMAN_HEADERS)).status_code==200
