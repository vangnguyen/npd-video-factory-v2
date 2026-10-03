"""Offline PCM/synthetic contract evidence, not voice/alignment acceptance."""
import asyncio
import hashlib
import shutil
from unittest.mock import Mock
import pytest
from sqlalchemy import event, select
from app.content_models import ContentDocument, ContentSaveRequest
from app.content_service import script_scenes, prepare_document, ContentConflictError
from app.narration_pacing import narration_plan, reflow_snapshot
from app.production_audio import AudioMixEngine, DeterministicWaveTTSProvider
from app.production_models import MixConfig, SubtitleStyle, SubtitleReplaceRequest
from app.production_logic import derive_subtitle_cues, ProductionContractError
from app.db import VideoProjectORM
from test_mvp1_multi_input import env, author, timeline
from app.db import JobORM


@pytest.mark.parametrize("phrase",["Cần Giờ","Ngọc Phương Đông","chính sách","chính sách bán hàng","Trung tâm Văn hóa Biển Xanh"])
@pytest.mark.parametrize("punctuation",["",", "])
def test_phrase_is_not_split_and_source_is_lossless(phrase,punctuation):
    script = ("nội dung được cung cấp "+punctuation)*3+phrase+" tiếp tục nội dung "*7
    scenes=script_scenes(script,[phrase])
    assert " ".join(script.split())==" ".join(" ".join(s.narration.split()) for s in scenes)
    assert any(phrase in s.narration for s in scenes)
    assert all(script[s.script_start:s.script_end]==s.narration for s in scenes)


def test_oversize_protected_phrase_fails_without_loss():
    phrase="Cụm từ không được chia "*5
    with pytest.raises(ValueError,match="STYLE_ADJUSTMENT"):
        script_scenes(phrase,[phrase])


async def test_measured_sentence_reflow_auto_and_locked_pause(env):
    text="Ngọc Phương Đông và Cần Giờ "*6+"có chính sách bán hàng."
    doc=prepare_document(ContentDocument(input_kind="script",original_text=text,
        protected_terms=["chính sách bán hàng"]))
    doc.scenes[1].duration_mode="locked"
    doc.scenes[1].duration_seconds=8
    doc.scenes[-1].pause_after_seconds=0.6
    version=await env.content.save(env.project.project_id,ContentSaveRequest(document=doc.model_copy(update={"approved":True})))
    built=await timeline(env,version)
    plan=built.snapshot.metadata["narration_plan"]
    assert len(plan["units"])<len(doc.scenes)  # one unit crosses visual/caption boundaries
    audio=AudioMixEngine(ffmpeg_path="not-invoked")
    async def normalize(source,target,*,speed):
        assert speed==1
        shutil.copyfile(source,target)
    audio._normalize_chunk=normalize
    measured=await audio.synthesize_planned_narration(DeterministicWaveTTSProvider(),
        cues=derive_subtitle_cues(built.snapshot), config=MixConfig(),duration_seconds=built.snapshot.duration_seconds,
        output_path=env.tmp/"voice.wav",workdir=env.tmp,plan=plan)
    assert measured["unit_count"]==1 and measured["timing"][0]["audio_duration_source"]=="decoded_pcm_sample_count"
    assert all(c["words"]==[] for c in measured["caption_schedule"])
    original=built.snapshot.model_dump(mode="json")
    reflowed=reflow_snapshot(built.snapshot,measured)
    assert built.snapshot.model_dump(mode="json")==original
    assert reflowed.tracks[0].clips[1].duration==8
    assert reflowed.duration_seconds<built.snapshot.duration_seconds
    assert reflowed.metadata["narration_reflow"]["word_alignment"]=="NOT_AVAILABLE"
    # actual version commit invalidates production approval/final via shared repository
    updated=await env.timeline.commit_mutation(project_id=env.project.project_id,expected_version=1,
        snapshot=reflowed,mutation={"type":"measured-narration-reflow"},actor_ref="synthetic-editor")
    assert updated.current_version==2 and updated.approval_status=="draft"
    poison=Mock(side_effect=AssertionError("no ASR/secret/budget"))
    env.assets.get_analysis=poison
    changed=measured.copy();changed["plan_sha256"]="0"*64
    with pytest.raises(ProductionContractError,match="PLAN_CHANGED"):
        reflow_snapshot(built.snapshot,changed)
    measured["timing"][0]["rendered_audio_duration_seconds"]=200
    with pytest.raises(ProductionContractError,match="DURATION_ADJUSTMENT"):
        reflow_snapshot(built.snapshot,measured)
    poison.assert_not_called()


async def test_audio_longer_than_slot_fails_no_speedup(env):
    version=await author(env,original="Một câu dài thử nghiệm.")
    built=await timeline(env,version)
    audio=AudioMixEngine(ffmpeg_path="not-invoked")
    async def normalize(source,target,*,speed): shutil.copyfile(source,target)
    audio._normalize_chunk=normalize
    with pytest.raises(ProductionContractError,match="DURATION_ADJUSTMENT"):
        await audio.synthesize_planned_narration(DeterministicWaveTTSProvider(),cues=derive_subtitle_cues(built.snapshot),
            config=MixConfig(),duration_seconds=0.1, output_path=env.tmp/"out.wav",workdir=env.tmp,
            plan=built.snapshot.metadata["narration_plan"])


async def test_word_highlight_without_words_is_explicitly_rejected(env):
    built=await timeline(env,await author(env))
    from app.production_models import ProductionPackageCreateRequest
    package=await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    assert package.subtitle.style.animation=="none"
    with pytest.raises(ProductionContractError,match="WORD_ALIGNMENT_UNAVAILABLE"):
        await env.package.replace_subtitles(env.project.project_id,SubtitleReplaceRequest(
            expected_timeline_version=1,expected_subtitle_version=1,cues=package.subtitle.cues,style=SubtitleStyle()))


async def test_postgres_two_saves_contend_real_row_lock_no_lost_update(env):
    if env.engine.dialect.name!="postgresql":
        pytest.skip("real PostgreSQL contention test; separate non-PG tests remain")
    old=await author(env)
    at_lock=asyncio.Event(); arrivals=0
    def before_execute(conn,cursor,statement,parameters,context,executemany):
        nonlocal arrivals
        if "FOR UPDATE" in statement and "video_projects" in statement:
            arrivals+=1
            if arrivals==2: at_lock.set()
    async with env.factory() as held:
        async with held.begin():
            await held.scalar(select(VideoProjectORM).where(VideoProjectORM.project_id==env.project.project_id).with_for_update())
            event.listen(env.engine.sync_engine,"before_cursor_execute",before_execute)
            jobs=[asyncio.create_task(env.content.save(env.project.project_id,ContentSaveRequest(
                expected_content_version_id=old.project_version_id,document=ContentDocument(input_kind="script",original_text=text))))
                for text in ["Bản thứ nhất.","Bản thứ hai."]]
            await asyncio.wait_for(at_lock.wait(),10)  # two DB queries, not sleep-based pseudo-concurrency
        results=await asyncio.gather(*jobs,return_exceptions=True)
    event.remove(env.engine.sync_engine,"before_cursor_execute",before_execute)
    assert sum(isinstance(r,ContentConflictError) for r in results)==1
    assert sum(not isinstance(r,Exception) for r in results)==1
    latest=await env.content.latest(env.project.project_id)
    assert latest.snapshot["content"]["original_text"] in {"Bản thứ nhất.","Bản thứ hai."}


@pytest.mark.parametrize("opponent",["edit","cancel"])
async def test_postgres_proposal_apply_races_transactionally(env,opponent):
    if env.engine.dialect.name!="postgresql":
        pytest.skip("real PostgreSQL transaction barrier")
    from test_mvp1_content_generation import setup,input_version
    from app.content_models import ContentGenerateRequest
    service=await setup(env);old=await input_version(env)
    created=await service.create(env.project.project_id,ContentGenerateRequest(
        expected_content_version_id=old.project_version_id,idempotency_key="transaction_barrier_apply"),actor_ref="editor")
    job_id=created["job"]["job_id"];await service.process(job_id)
    table=VideoProjectORM if opponent=="edit" else JobORM
    column=VideoProjectORM.project_id if opponent=="edit" else JobORM.job_id
    identifier=env.project.project_id if opponent=="edit" else job_id
    both_waiting=asyncio.Event();arrivals=0
    def observe(conn,cursor,statement,parameters,context,executemany):
        nonlocal arrivals
        if "FOR UPDATE" in statement and table.__tablename__ in statement:
            arrivals+=1
            if arrivals==2:both_waiting.set()
    async with env.factory() as held:
        async with held.begin():
            await held.scalar(select(table).where(column==identifier).with_for_update())
            event.listen(env.engine.sync_engine,"before_cursor_execute",observe)
            apply=asyncio.create_task(service.apply(env.project.project_id,job_id,expected_version=old.project_version_id,actor_ref="editor"))
            if opponent=="edit":
                other=asyncio.create_task(env.content.save(env.project.project_id,ContentSaveRequest(
                    expected_content_version_id=old.project_version_id,document=ContentDocument(input_kind="script",original_text="Bản chỉnh thủ công."))))
            else:
                other=asyncio.create_task(service.cancel(env.project.project_id,job_id,actor_ref="editor"))
            await asyncio.wait_for(both_waiting.wait(),10)
        results=await asyncio.gather(apply,other,return_exceptions=True)
    event.remove(env.engine.sync_engine,"before_cursor_execute",observe)
    current=await env.content.latest(env.project.project_id)
    job=(await service.get(env.project.project_id,job_id))["job"]
    if opponent=="edit":
        assert sum(isinstance(r,ContentConflictError) for r in results)==1
    if current.source_job_id==job_id:
        assert job["status"]=="succeeded"
    elif opponent=="cancel":
        assert job["status"]=="cancelled" and isinstance(results[0],ContentConflictError)
