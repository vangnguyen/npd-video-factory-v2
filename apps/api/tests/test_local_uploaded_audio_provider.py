"""Owned files and explicit CPU fixtures; no model inference/network/download."""
import asyncio
import copy
from dataclasses import replace
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import wave
import pytest
from app.config import Settings
from app.auto_edit_models import MediaMetadata
from app.auto_edit_providers import (ProviderTranscript, ProviderSegment, ProviderWord,
    ProviderNotConfigured, require_positive_duration_transcript, PositiveDurationTranscriptRequired)
from app.local_asr_profile import digest, profile
from app.local_asr_runtime import file_sha
from app import local_uploaded_audio_provider as local
from app.uploaded_audio_runtime import provider_from_settings


def wav(frames=16000):
    output=io.BytesIO()
    with wave.open(output,'wb') as sound:
        sound.setnchannels(1);sound.setsampwidth(2);sound.setframerate(16000)
        sound.writeframes(b'\0\0'*frames)
    return output.getvalue()


@pytest.fixture
def custody(tmp_path):
    model=tmp_path/'model';model.mkdir();(model/'model.bin').write_bytes(b'EXPLICIT SYNTHETIC MODEL CUSTODY, NEVER LOADED')
    python=tmp_path/'python';python.write_bytes(b'EXPLICIT SYNTHETIC PYTHON CUSTODY, NEVER EXECUTED')
    decoder=tmp_path/'ffmpeg';decoder.write_bytes(b'EXPLICIT SYNTHETIC DECODER CUSTODY, NEVER EXECUTED')
    manifest=tmp_path/'runtime.json'
    model_record={'schema_version':'local-asr-model.v1','provider':'faster-whisper',
        'model':'Systran/faster-whisper-base','revision':'explicit-synthetic-model-revision','license':'MIT',
        'files':{'model.bin':{'bytes':(model/'model.bin').stat().st_size,'sha256':file_sha(model/'model.bin')}}}
    manifest.write_text(json.dumps({'version':'local-asr-runtime.v1','enabled':True,'python':str(python),
        'python_sha256':file_sha(python),'model_root':str(model),'model_manifest_sha256':digest(model_record),
        'cpu_threads':2,'timeout_seconds':300}),encoding='utf-8')
    with patch.object(local.runtime_module,'model_manifest',return_value=model_record), \
        patch.object(local.profile_module,'model_manifest',return_value=model_record), \
        patch.object(local,'model_manifest',return_value=model_record):
        yield SimpleNamespace(manifest=manifest,decoder=decoder,model=model,python=python,root=tmp_path,
            kwargs={'manifest':manifest,'manifest_sha256':file_sha(manifest),'decoder':decoder,'decoder_sha256':file_sha(decoder)})


def metadata(duration=1):
    return MediaMetadata(media_kind='audio',detected_content_type='audio/wav',duration_seconds=duration,
        audio_channels=1,audio_sample_rate=16000)


class ExplicitCpuFixture:
    calls=0;boundary=False;outside=False;cancelled=False;wait=None
    def __init__(self,manifest,language,model_key='base'):
        self.profile=profile(language,model_key);self.raw_result=None
    async def transcribe(self,path,*,metadata,checksum_sha256,execution_trace=None):
        type(self).calls+=1
        if type(self).wait is not None:
            try:await type(self).wait.wait()
            except asyncio.CancelledError:type(self).cancelled=True;raise
        first=ProviderWord(.1,.1 if type(self).boundary else .4,'Xin',.8,
            timing_semantics='provider_boundary_point' if type(self).boundary else 'positive_interval')
        end=1.1 if type(self).outside else .8
        self.raw_result={'fixture':True,'model_inferences':0,'source_sha256':checksum_sha256,
            'language':'en' if self.profile['language']=='auto' else self.profile['language'],
            'segments':[{'start':.1,'end':end,'text':'Xin chào.'}]}
        return ProviderTranscript(language=self.raw_result['language'],confidence=None,
            segments=(ProviderSegment(.1,end,'Xin chào.',None,None,(first,ProviderWord(.4,end,'chào.',.3))),),
            provenance={'fixture':True,'local_inference':False,'model_inferences':0,'word_alignment_source':'model_estimate',
                'requested_language':self.profile['language'],'source_checksum':checksum_sha256})


def fixture_decoder(offset=0, broken=None):
    async def decode(arguments, *, timeout):
        assert '-protocol_whitelist' in arguments and arguments[arguments.index('-protocol_whitelist')+1]=='file,pipe'
        assert arguments[arguments.index('-af')+1]=='aresample=16000,asettb=1/16000,ashowinfo'
        assert '-copyts' in arguments and '-start_at_zero' in arguments and '-xerror' in arguments
        target=Path(arguments[-1]);target.write_bytes(wav())
        if broken=='truncated':target.write_bytes(target.read_bytes()[:-8])
        pts=int(offset*16000)
        if broken in {'gap','overlap'}:
            second=pts+9000 if broken=='gap' else pts+7000
            return (f'[Parsed_ashowinfo_2] n:0 pts:{pts} pts_time:{pts/16000} fmt:s16 channels:1 rate:16000 nb_samples:8000\n'
                f'[Parsed_ashowinfo_2] n:1 pts:{second} pts_time:{second/16000} fmt:s16 channels:1 rate:16000 nb_samples:8000\n').encode()
        return f'[Parsed_ashowinfo_2] n:0 pts:{pts} pts_time:{pts/16000} fmt:s16 channels:1 rate:16000 nb_samples:16000\n'.encode()
    return decode


@pytest.fixture(autouse=True)
def reset_fixture():
    ExplicitCpuFixture.calls=0;ExplicitCpuFixture.boundary=False;ExplicitCpuFixture.outside=False
    ExplicitCpuFixture.cancelled=False;ExplicitCpuFixture.wait=None


def test_default_and_disabled_selection_remain_not_configured():
    settings=Settings(_env_file=None)
    assert not settings.local_asr_enabled and provider_from_settings(settings).key=='transcription-not-configured'
    assert provider_from_settings(SimpleNamespace(transcription_provider='local_cpu',local_asr_enabled=False)).key=='transcription-not-configured'
    with pytest.raises(ValueError):Settings(_env_file=None,transcription_provider='local_cpu',local_asr_enabled=True)
    with pytest.raises(ValueError):Settings(_env_file=None,local_asr_model_key='phowhisper-small')


def test_explicit_config_does_not_auto_discover_or_download_missing_runtime(tmp_path):
    values=dict(transcription_provider='local_cpu',local_asr_enabled=True,local_asr_runtime_manifest=tmp_path/'missing.json',
        local_asr_runtime_manifest_sha256='a'*64,local_asr_decoder_sha256='b'*64,ffmpeg_path=str(tmp_path/'missing-ffmpeg'))
    settings=Settings(_env_file=None,**values)
    assert provider_from_settings(settings).key=='transcription-not-configured'
    with pytest.raises(ValueError):Settings(_env_file=None,**{**values,'ffmpeg_path':'ffmpeg'})


def test_public_binding_contains_digests_sizes_and_profiles_without_private_paths(custody):
    provider=local.LocalUploadedAudioProvider(**custody.kwargs,language='vi')
    public=provider.immutable_binding
    assert public['schema_version']=='sql-local-audio-runtime.v1' and public['cpu_threads']==2
    assert str(custody.root) not in json.dumps(public)
    assert public['model_files']['model.bin']['sha256']==file_sha(custody.model/'model.bin')
    assert public['decoder']['bytes']==custody.decoder.stat().st_size
    public['profile']['language']='en';assert provider.immutable_binding['profile']['language']=='vi'
    provider.verify();assert not ExplicitCpuFixture.calls


@pytest.mark.parametrize('target',['model','python','decoder','manifest','language','profile'])
def test_runtime_and_configuration_mutations_fail_before_decode_or_inference(custody,target):
    provider=local.LocalUploadedAudioProvider(**custody.kwargs)
    if target=='model':(custody.model/'model.bin').write_bytes(b'altered same owned fixture')
    elif target in {'python','decoder'}:getattr(custody,target).write_bytes(b'altered owned binary fixture')
    elif target=='manifest':custody.manifest.write_text('{}',encoding='utf-8')
    elif target=='language':provider.language='vi'
    else:provider._binding['profile']['language']='vi'
    with pytest.raises((ValueError,ProviderNotConfigured)):provider.verify()
    assert ExplicitCpuFixture.calls==0


@pytest.mark.asyncio
@pytest.mark.parametrize('language',['vi','en','auto'])
async def test_normalized_derived_projection_preserves_raw_model_words_and_requires_review(custody,language):
    source=custody.root/'source.wav';source.write_bytes(wav(32000));sha=file_sha(source)
    provider=local.LocalUploadedAudioProvider(**custody.kwargs,language=language)
    with patch.object(local,'bounded_process',side_effect=fixture_decoder(.25)),patch.object(local,'LocalCpuTranscriptionProvider',ExplicitCpuFixture):
        value=await provider.transcribe(source,metadata=metadata(2),checksum_sha256=sha)
    assert value.language==('en' if language=='auto' else language) and value.confidence is None
    assert value.segments[0].words[0].start_seconds==.35 and value.segments[0].words[0].end_seconds==.65
    raw=value.provenance['provider_pcm_transcript'];assert raw['segments'][0]['words'][0]['start_seconds']==.1
    assert raw['segments'][0]['words'][0]['end_seconds']==.4 and file_sha(source)==sha
    assert value.provenance['source_clock_projection']['observed_clock_tolerance_samples']==1
    assert value.provenance['raw_model_result']['fixture'] and value.provenance['fixture']
    assert value.provenance['owner_uat_accepted'] is False and value.provenance['publishing_enabled'] is False
    assert value.actual_cost_vnd==0 and value.provenance['operating_electricity_hardware_cost_vnd'] is None
    assert ExplicitCpuFixture.calls==1


@pytest.mark.asyncio
@pytest.mark.parametrize('broken',['gap','overlap','truncated'])
async def test_unmeasured_or_discontinuous_pcm_rejects_before_inference(custody,broken):
    source=custody.root/'source.wav';source.write_bytes(wav());provider=local.LocalUploadedAudioProvider(**custody.kwargs)
    with patch.object(local,'bounded_process',side_effect=fixture_decoder(broken=broken)),patch.object(local,'LocalCpuTranscriptionProvider',ExplicitCpuFixture):
        with pytest.raises((ValueError,local.LocalAudioRejected)):
            await provider.transcribe(source,metadata=metadata(),checksum_sha256=file_sha(source))
    assert ExplicitCpuFixture.calls==0


@pytest.mark.asyncio
async def test_boundary_points_are_retained_and_interval_consumers_fail_closed_without_imputation(custody):
    source=custody.root/'source.wav';source.write_bytes(wav());provider=local.LocalUploadedAudioProvider(**custody.kwargs)
    ExplicitCpuFixture.boundary=True
    with patch.object(local,'bounded_process',side_effect=fixture_decoder()),patch.object(local,'LocalCpuTranscriptionProvider',ExplicitCpuFixture):
        value=await provider.transcribe(source,metadata=metadata(),checksum_sha256=file_sha(source))
    word=value.segments[0].words[0]
    assert word.start_seconds==word.end_seconds==.1 and word.timing_semantics=='provider_boundary_point'
    assert value.provenance['provider_pcm_transcript']['segments'][0]['words'][0]['end_seconds']==.1
    with pytest.raises(PositiveDurationTranscriptRequired):require_positive_duration_transcript(value)


@pytest.mark.asyncio
async def test_provider_outside_actual_clock_rejected_without_clipping(custody):
    source=custody.root/'source.wav';source.write_bytes(wav());provider=local.LocalUploadedAudioProvider(**custody.kwargs)
    ExplicitCpuFixture.outside=True
    with patch.object(local,'bounded_process',side_effect=fixture_decoder()),patch.object(local,'LocalCpuTranscriptionProvider',ExplicitCpuFixture):
        with pytest.raises(local.LocalAudioRejected,match='OUTSIDE_DECODED_CLOCK'):
            await provider.transcribe(source,metadata=metadata(),checksum_sha256=file_sha(source))
    assert provider.raw_result['model_result']['fixture']
    assert provider.raw_result['source_projection_validated'] is False


@pytest.mark.asyncio
async def test_normalizer_failure_retains_raw_result_without_second_inference(custody):
    class RejectedCpuFixture(ExplicitCpuFixture):
        async def transcribe(self,*args,**kwargs):
            await super().transcribe(*args,**kwargs)
            raise ValueError('EXPLICIT SYNTHETIC NORMALIZATION FAILURE')
    source=custody.root/'source.wav';source.write_bytes(wav());provider=local.LocalUploadedAudioProvider(**custody.kwargs)
    with patch.object(local,'bounded_process',side_effect=fixture_decoder()),patch.object(local,'LocalCpuTranscriptionProvider',RejectedCpuFixture):
        with pytest.raises(local.LocalAudioEvidenceRejected,match='NORMALIZATION_REJECTED') as caught:
            await provider.transcribe(source,metadata=metadata(),checksum_sha256=file_sha(source))
    assert provider.raw_result['model_result']['fixture']
    assert provider.raw_result['provider_result_normalized'] is False
    assert provider.raw_result['source_projection_validated'] is False
    assert caught.value.evidence['model_result']['fixture']
    assert caught.value.evidence_sha256==digest(caught.value.evidence)
    provider.raw_result={'unrelated_shared_diagnostic':True}
    assert caught.value.evidence['model_result']['fixture']


@pytest.mark.asyncio
async def test_concurrent_rejected_calls_keep_independent_source_evidence(custody):
    first=custody.root/'first.wav';first.write_bytes(wav(32000))
    second=custody.root/'second.wav';second.write_bytes(wav(64000))
    provider=local.LocalUploadedAudioProvider(**custody.kwargs)
    entered=[0];both=asyncio.Event()
    class ConcurrentRejectedFixture(ExplicitCpuFixture):
        async def transcribe(self,*args,**kwargs):
            await super().transcribe(*args,**kwargs)
            entered[0]+=1;self.raw_result['invocation']=entered[0]
            if entered[0]==2:both.set()
            await asyncio.wait_for(both.wait(),5)
            raise ValueError('EXPLICIT NORMALIZATION REJECTION')
    with patch.object(local,'bounded_process',side_effect=fixture_decoder()),patch.object(local,'LocalCpuTranscriptionProvider',ConcurrentRejectedFixture):
        results=await asyncio.gather(provider.transcribe(first,metadata=metadata(2),checksum_sha256=file_sha(first)),
            provider.transcribe(second,metadata=metadata(4),checksum_sha256=file_sha(second)),return_exceptions=True)
    assert all(isinstance(value,local.LocalAudioEvidenceRejected) for value in results)
    assert [value.evidence['source_sha256'] for value in results]==[file_sha(first),file_sha(second)]
    assert [value.evidence['source_size_bytes'] for value in results]==[first.stat().st_size,second.stat().st_size]
    assert {value.evidence['model_result']['invocation'] for value in results}=={1,2}
    assert all(value.evidence_sha256==digest(value.evidence) and value.evidence['human_accepted'] is False for value in results)


@pytest.mark.asyncio
async def test_durable_cancel_callback_stops_current_cpu_task_and_drains_cleanup(custody):
    source=custody.root/'source.wav';source.write_bytes(wav());provider=local.LocalUploadedAudioProvider(**custody.kwargs)
    ExplicitCpuFixture.wait=asyncio.Event();cancelled=[False]
    async def check():return cancelled[0]
    with patch.object(local,'bounded_process',side_effect=fixture_decoder()),patch.object(local,'LocalCpuTranscriptionProvider',ExplicitCpuFixture):
        task=asyncio.create_task(provider.transcribe(source,metadata=metadata(),checksum_sha256=file_sha(source),is_cancelled=check))
        for _ in range(100):
            if ExplicitCpuFixture.calls:break
            await asyncio.sleep(.01)
        assert ExplicitCpuFixture.calls==1;cancelled[0]=True
        with pytest.raises(local.LocalAudioRejected,match='CANCELLED'):await task
    assert ExplicitCpuFixture.cancelled


@pytest.mark.asyncio
async def test_actual_owned_child_timeout_and_output_bound_are_drained_without_model():
    with pytest.raises(TimeoutError):
        await local.bounded_process([sys.executable,'-I','-c','import time; time.sleep(5)'],timeout=.05)
    with pytest.raises(local.LocalAudioRejected,match='OUTPUT_LIMIT'):
        await local.bounded_process([sys.executable,'-I','-c','import sys; sys.stderr.write("x"*1000000)'],
            timeout=5,maximum_stderr=128)
