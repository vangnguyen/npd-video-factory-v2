"""Synthetic physical PCM custody/clock checks; no DSP, renderer or listening."""
import copy
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import wave

import pytest
from jsonschema import Draft202012Validator,ValidationError

from app.object_storage import sha256_file
from app.platform_models import AssetRegister
from app.production_models import ProductionPackageCreateRequest,RenderCreateRequest
from app.sql_tts_artifact_reuse import (MAX_BYTES,PREPARED_AUDIO_MAX_DURATION_SECONDS,
    PREPARED_AUDIO_HEADER_MAX_BYTES,prepared_audio_byte_limit,prepared_pcm,prepared_final_audio,
    canonical_audio_binding,asset_proof,TTSReuseRejected)
from test_sql_tts_artifact_reuse import final
from test_mvp1_multi_input import env,author,timeline,ROOT


def sparse_pcm(path,duration,channels=2,*,junk_bytes=0):
    """Sparse zero samples are actual readable file bytes, not a media claim."""
    frames=int(duration*48000);payload=frames*channels*2
    junk=b'JUNK'+struct.pack('<I',junk_bytes)+b'\0'*junk_bytes if junk_bytes else b''
    fmt=struct.pack('<HHIIHH',1,channels,48000,48000*channels*2,channels*2,16)
    header=b'RIFF'+struct.pack('<I',36+len(junk)+payload)+b'WAVEfmt '+struct.pack('<I',16)+fmt+junk \
        +b'data'+struct.pack('<I',payload)
    with path.open('xb') as out:
        out.write(header);out.seek(len(header)+payload-1);out.write(b'\0')
    return len(header)+payload


@pytest.mark.parametrize('duration',[480,600])
def test_stream_pcm_accepts_existing_max_duration_without_reading_all_frames(tmp_path,duration,monkeypatch):
    path=tmp_path/'owned-synthetic.wav'
    assert sparse_pcm(path,duration)==duration*192000+44
    sizes=[];original=wave.Wave_read.readframes
    def bounded(sound,count):
        sizes.append(count)
        assert 0<count<=48000
        return original(sound,count)
    monkeypatch.setattr(wave.Wave_read,'readframes',bounded)
    prepared_pcm(path,duration)
    assert sum(sizes)==duration*48000
    assert path.stat().st_size>90_000_000 and MAX_BYTES==20_000_000


def test_duration_limit_matches_existing_renderer_and_rejects_601_before_file_access(tmp_path):
    schema=json.loads((ROOT/'packages/contracts/timeline-render.schema.json').read_text())
    duration_schema=schema['properties']['metadata']['properties']['duration_seconds']
    assert duration_schema['maximum']==PREPARED_AUDIO_MAX_DURATION_SECONDS==600
    Draft202012Validator(duration_schema).validate(600)
    with pytest.raises(ValidationError):Draft202012Validator(duration_schema).validate(601)
    with pytest.raises(TTSReuseRejected,match='DURATION_INVALID'):
        prepared_pcm(tmp_path/'intentionally-missing.wav',601)
    for value in (True,0,-1,float('nan'),float('inf'),'600'):
        with pytest.raises(TTSReuseRejected,match='DURATION_INVALID'):prepared_audio_byte_limit(value)


def test_wav_header_and_truncation_are_bounded_against_actual_canonical_clock(tmp_path):
    oversized=tmp_path/'oversized-header.wav'
    sparse_pcm(oversized,480,channels=1,junk_bytes=PREPARED_AUDIO_HEADER_MAX_BYTES)
    # Stereo download ceiling alone is not enough to bound mono WAV metadata.
    assert oversized.stat().st_size<prepared_audio_byte_limit(480)
    with pytest.raises(TTSReuseRejected,match='HEADER_LIMIT'):prepared_pcm(oversized,480)
    truncated=tmp_path/'truncated.wav';sparse_pcm(truncated,600)
    with truncated.open('r+b') as out:out.truncate(truncated.stat().st_size-2)
    with pytest.raises(TTSReuseRejected,match='TRUNCATED'):prepared_pcm(truncated,600)
    mismatched=tmp_path/'wrong-clock.wav';sparse_pcm(mismatched,480)
    with pytest.raises(TTSReuseRejected,match='CLOCK_INVALID'):prepared_pcm(mismatched,600)


async def approved_source(env,duration):
    version=await author(env,original='Explicit fixture source, no generated speech.')
    first=await timeline(env,version)
    shape=first.snapshot.model_copy(deep=True);shape.duration_seconds=duration
    visual=next(t for t in shape.tracks if t.type=='video').clips[0];visual.duration=duration
    current=await env.timeline.commit_mutation(project_id=env.project.project_id,expected_version=first.current_version,
        snapshot=shape,mutation={'type':'explicit-synthetic-pcm-duration-fixture'},actor_ref='fixture-editor')
    package=await env.package.create_or_refresh(env.project.project_id,
        ProductionPackageCreateRequest(expected_timeline_version=current.current_version))
    review=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(
        expected_timeline_version=current.current_version,expected_subtitle_version=package.subtitle.version,
        expected_audio_version=package.audio_mix.version))
    await env.production.start_render(review.render_id)
    proofs={};ids={}
    for name,channels in (('narration-track',1),('audio-mix',2)):
        path=env.tmp/(name+'.wav');sparse_pcm(path,duration,channels)
        key=f'workspaces/{env.workspace.workspace_id}/projects/{env.project.project_id}/bounds/{name}.wav'
        stored=await env.storage.put_file(object_key=key,path=path,content_type='audio/wav')
        asset=await env.platform.register_asset(env.project.project_id,AssetRegister(asset_class='render',kind=name,
            project_version_id=version.project_version_id,filename=path.name,object_key=stored.object_key,
            content_type='audio/wav',size_bytes=stored.size_bytes,checksum_sha256=stored.checksum_sha256,
            storage_provider=env.storage.name,provenance={'fixture':True,'synthetic_pcm':True,
                'actual_renderer_calls':0,'actual_dsp_calls':0,'human_accepted':False}))
        ids[name]=asset.asset_id;proofs[name]=asset_proof(asset)
    # Deliberate review-state fixture. This does not claim that silence passed
    # real audio QC or that an Owner reviewed it.
    manifest={'narration':{'provider':'explicit-synthetic-pcm-fixture','fixture':True,'timing':[],
        'canonical_audio_binding':canonical_audio_binding(review,current.snapshot.model_dump(mode='json'),
            package.subtitle,package.audio_mix.config)},'mix':{'fixture':True,'actual_dsp_calls':0},
        'supporting_asset_ids':ids,'supporting_audio_proofs':proofs,'publishing_allowed':False}
    reviewed=await env.production.complete_render(review.render_id,output_asset_id=ids['audio-mix'],
        qc_report={'status':'passed','fixture_only':True,'real_media_quality_accepted':False},manifest=manifest)
    target=await final(env,reviewed)
    await env.production.start_render(target.render_id)
    return reviewed,target,current.snapshot.model_dump(mode='json'),package,proofs


@pytest.mark.asyncio
@pytest.mark.parametrize('duration',[480,600])
async def test_approved_source_helper_copies_long_pcm_under_actual_sql_current_and_hash_proof(env,duration):
    reviewed,target,snapshot,package,proofs=await approved_source(env,duration)
    workdir=env.tmp/'owned-copy';workdir.mkdir()
    before=copy.deepcopy((await env.production.get_render(reviewed.render_id)).manifest)
    narration,_=await prepared_final_audio(repository=env.production,assets=env.assets,storage=env.storage,render=target,
        snapshot=snapshot,subtitles=package.subtitle,config=package.audio_mix.config,workdir=workdir)
    for name,filename in (('narration-track','narration.wav'),('audio-mix','audio-mix.wav')):
        assert sha256_file(workdir/filename)==proofs[name]['checksum_sha256']
    assert (await env.production.get_render(reviewed.render_id)).manifest==before
    receipt=narration['prepared_audio_reuse']
    assert receipt['provider_calls']==receipt['new_inferences']==receipt['credential_reads']==0
    assert receipt['approved_audio_preserved'] is True and receipt['owner_uat_accepted'] is False


@pytest.mark.asyncio
async def test_out_of_contract_source_clock_blocks_before_any_repository_or_download():
    class Denied:
        def __getattr__(self,name):raise AssertionError('601s must be rejected before source access: '+name)
    with pytest.raises(TTSReuseRejected,match='DURATION_INVALID'):
        await prepared_final_audio(repository=Denied(),assets=Denied(),storage=Denied(),render=Denied(),
            snapshot={'duration_seconds':601},subtitles=Denied(),config=Denied(),workdir=Path('unread'))
