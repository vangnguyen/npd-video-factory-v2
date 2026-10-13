"""Explicit CPU fixtures plus measured MP4 decode; never load a speech model."""
import asyncio
import copy
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from app.auto_edit_models import MediaMetadata
from app.auto_edit_providers import ProviderNotConfigured, PositiveDurationTranscriptRequired, require_positive_duration_transcript
from app.local_asr_runtime import file_sha
from app import local_video_transcription_provider as video
from app.auto_edit_transcription_runtime import provider_from_settings
from test_local_uploaded_audio_provider import custody, ExplicitCpuFixture, fixture_decoder, reset_fixture


def media(duration=2):
    return MediaMetadata(media_kind='video', detected_content_type='video/mp4', duration_seconds=duration,
        width=160,height=90,fps=25,video_codec='h264',audio_codec='aac',audio_channels=1,audio_sample_rate=16000)
def source(custody):
    path=custody.root/'source.mp4';path.write_bytes(b'\0\0\0\x18ftypisom'+b'EXPLICIT SYNTHETIC VIDEO FIXTURE'*40);return path
def configured(custody,monkeypatch,**kwargs):
    monkeypatch.setattr(video,'bounded_process',fixture_decoder())
    monkeypatch.setattr(video,'LocalCpuTranscriptionProvider',ExplicitCpuFixture)
    return video.LocalVideoTranscriptionProvider(**custody.kwargs,language='vi',**kwargs)


def test_default_disabled_and_missing_video_runtime_do_not_discover_or_load(tmp_path):
    assert provider_from_settings(SimpleNamespace(transcription_provider='local_cpu',local_asr_enabled=False)).key=='transcription-not-configured'
    settings=SimpleNamespace(transcription_provider='local_cpu',local_asr_enabled=True,
        local_asr_runtime_manifest=tmp_path/'missing.json',local_asr_runtime_manifest_sha256='a'*64,
        ffmpeg_path=str(tmp_path/'missing-ffmpeg'),local_asr_decoder_sha256='b'*64,local_asr_language='vi',
        local_asr_model_key='small',local_asr_decoder_timeout_seconds=60,local_asr_video_max_file_bytes=200,
        upload_max_size_bytes=100,local_asr_max_duration_seconds=1800)
    assert provider_from_settings(settings).key=='transcription-not-configured'


def test_video_container_limit_is_clamped_to_upload_limit(monkeypatch):
    observed=[]
    monkeypatch.setattr(video,'LocalVideoTranscriptionProvider',lambda **kwargs:observed.append(kwargs) or object())
    settings=SimpleNamespace(transcription_provider='local_cpu',local_asr_enabled=True,local_asr_runtime_manifest='fixture',
        local_asr_runtime_manifest_sha256='a'*64,ffmpeg_path='fixture',local_asr_decoder_sha256='b'*64,
        local_asr_language='vi',local_asr_model_key='base',local_asr_decoder_timeout_seconds=60,
        local_asr_video_max_file_bytes=200,upload_max_size_bytes=100,local_asr_max_duration_seconds=20)
    provider_from_settings(settings);assert observed[0]['max_file_bytes']==100


@pytest.mark.asyncio
@pytest.mark.parametrize('offset',[0,.35])
async def test_video_projection_keeps_raw_pcm_words_and_observed_source_origin(custody,monkeypatch,offset):
    provider=configured(custody,monkeypatch);monkeypatch.setattr(video,'bounded_process',fixture_decoder(offset))
    path=source(custody);before=file_sha(path)
    result=await provider.transcribe(path,metadata=media(),checksum_sha256=before)
    assert ExplicitCpuFixture.calls==1 and result.provenance['fixture'] is True
    assert result.provenance['raw_model_result']['model_inferences']==0
    assert result.segments[0].words[0].start_seconds==.1+offset
    assert result.provenance['provider_pcm_transcript']['segments'][0]['words'][0]['start_seconds']==.1
    assert result.provenance['source_clock_projection']['offset_seconds']==offset
    assert not result.provenance['source_clock_projection']['bounds_clipped']
    assert file_sha(path)==before and result.provenance['owner_uat_accepted'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('broken',['gap','overlap','truncated'])
async def test_video_clock_rejects_before_cpu_fixture_without_repair(custody,monkeypatch,broken):
    provider=configured(custody,monkeypatch);monkeypatch.setattr(video,'bounded_process',fixture_decoder(broken=broken))
    path=source(custody)
    with pytest.raises(ValueError):await provider.transcribe(path,metadata=media(),checksum_sha256=file_sha(path))
    assert ExplicitCpuFixture.calls==0


@pytest.mark.asyncio
async def test_boundary_points_remain_raw_and_interval_consumer_is_blocked(custody,monkeypatch):
    provider=configured(custody,monkeypatch);ExplicitCpuFixture.boundary=True;path=source(custody)
    result=await provider.transcribe(path,metadata=media(),checksum_sha256=file_sha(path))
    word=result.segments[0].words[0];assert word.start_seconds==word.end_seconds==.1
    with pytest.raises(PositiveDurationTranscriptRequired):require_positive_duration_transcript(result)
    assert result.provenance['local_video_evidence']['model_result']['fixture'] is True


@pytest.mark.asyncio
async def test_normalizer_failure_has_request_scoped_raw_evidence(custody,monkeypatch):
    class Rejected(ExplicitCpuFixture):
        async def transcribe(self,*args,**kwargs):
            await super().transcribe(*args,**kwargs);raise ValueError('explicit fixture normalizer failure')
    provider=configured(custody,monkeypatch);monkeypatch.setattr(video,'LocalCpuTranscriptionProvider',Rejected);path=source(custody)
    with pytest.raises(video.LocalVideoEvidenceRejected) as caught:
        await provider.transcribe(path,metadata=media(),checksum_sha256=file_sha(path))
    assert caught.value.evidence['source_sha256']==file_sha(path)
    assert caught.value.evidence['provider_result_normalized'] is False
    assert caught.value.evidence['model_result']['fixture'] is True
    assert caught.value.evidence['immutable_binding']==provider.immutable_binding


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['model','decoder','python','manifest','source','unsupported_audio','overlong'])
async def test_video_custody_and_input_mutation_stops_before_cpu(custody,monkeypatch,mutation):
    provider=configured(custody,monkeypatch);path=source(custody);checksum=file_sha(path);metadata=media()
    if mutation=='model':(custody.model/'model.bin').write_bytes(b'changed owned fixture')
    elif mutation in {'decoder','python'}:getattr(custody,mutation).write_bytes(b'changed owned fixture')
    elif mutation=='manifest':custody.manifest.write_text('{}')
    elif mutation=='source':path.write_bytes(b'changed owned fixture')
    elif mutation=='unsupported_audio':metadata=metadata.model_copy(update={'media_kind':'audio'})
    else:metadata=metadata.model_copy(update={'duration_seconds':1801})
    with pytest.raises((ValueError,ProviderNotConfigured)):
        await provider.transcribe(path,metadata=metadata,checksum_sha256=checksum)
    assert ExplicitCpuFixture.calls==0


FFMPEG=Path('C:/Users/PC/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe')
@pytest.mark.asyncio
@pytest.mark.parametrize('delay',[0,.35])
async def test_actual_owned_mp4_decoder_uses_measured_clock_with_explicit_mock_cpu(custody,monkeypatch,delay):
    if not FFMPEG.is_file():pytest.skip('Owned Windows FFmpeg unavailable; physical decode acceptance not claimed')
    from app.auto_edit_providers import FFprobeMediaProbe
    path=custody.root/'physical-source.mp4'
    subprocess.run([str(FFMPEG),'-v','error','-nostdin','-f','lavfi','-i','color=black:s=160x90:r=25:d=3',
        '-itsoffset',str(delay),'-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=1',
        '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,capture_output=True,timeout=30)
    kwargs={**custody.kwargs,'decoder':FFMPEG,'decoder_sha256':file_sha(FFMPEG)}
    provider=video.LocalVideoTranscriptionProvider(**kwargs,language='vi')
    monkeypatch.setattr(video,'LocalCpuTranscriptionProvider',ExplicitCpuFixture)
    metadata=await FFprobeMediaProbe(str(FFMPEG.with_name('ffprobe.exe'))).probe(path,detected_content_type='video/mp4',media_kind='video')
    before=file_sha(path);result=await provider.transcribe(path,metadata=metadata,checksum_sha256=before)
    offset=result.provenance['decoded_audio_clock']['source_start_seconds']
    assert (offset==0 if delay==0 else offset>0)
    assert result.segments[0].words[0].start_seconds==.1+offset
    assert result.provenance['provider_pcm_transcript']['segments'][0]['words'][0]['start_seconds']==.1
    assert result.provenance['decoded_audio_clock']['source_end_seconds']<=metadata.duration_seconds
    assert result.provenance['fixture'] is True and ExplicitCpuFixture.calls==1 and file_sha(path)==before


@pytest.mark.asyncio
async def test_decoded_pcm_ceiling_rejects_oversized_fixture_before_model(custody,monkeypatch):
    provider=configured(custody,monkeypatch,max_duration_seconds=.05);path=source(custody)
    with pytest.raises(video.LocalVideoRejected,match='LOCAL_VIDEO_PCM_SIZE_LIMIT'):
        await provider.transcribe(path,metadata=media(.05),checksum_sha256=file_sha(path))
    assert ExplicitCpuFixture.calls==0
