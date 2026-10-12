import copy
import hashlib
from decimal import Decimal

import pytest

from app.assemblyai_asr_profile import assemblyai_asr_profile, assemblyai_profile_sha256
from app.assemblyai_studio_profile import studio_profile, studio_profile_sha256, studio_request
from app.assemblyai_studio_transcription_provider import AssemblyAIStudioTranscriptionProvider
from app.auto_edit_models import MediaMetadata


class Transport:
    def __init__(self, language):
        self.language=language;self.calls=[]
        text='Xin chào.' if language=='vi' else 'Hello world.'
        self.result={'id':'studio-asr-fixture','status':'completed','language_code':language,
            'speech_model_used':'universal-3-5-pro','text':text,
            'words':[{'text':w,'start':i*250,'end':i*250+200,'confidence':.9} for i,w in enumerate(text.split())],
            'fixture':True}
    async def upload(self,*args):
        self.calls.append('upload');return 'https://cdn.assemblyai.com/studio-asr-fixture.wav'
    async def create_transcript(self,request,*args):
        self.calls.append(copy.deepcopy(request));return {'id':'studio-asr-fixture'}
    async def get_transcript(self,*args):
        self.calls.append('get');return self.result


async def execute(tmp_path, language, result_language, **options):
    path=tmp_path/'synthetic-provider-payload.wav';path.write_bytes(b'EXPLICIT MOCK AUDIO')
    transport=Transport(result_language)
    for key,value in options.pop('result_changes',{}).items():transport.result[key]=value
    provider=AssemblyAIStudioTranscriptionProvider(profile=studio_profile(language),
        credential_resolver=lambda _:'mock-private-key',transport=transport,poll_interval_seconds=0.,**options)
    result=await provider.transcribe(path,metadata=MediaMetadata(media_kind='audio',detected_content_type='audio/wav',duration_seconds=1.),
        checksum_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return result,transport,provider


@pytest.mark.asyncio
@pytest.mark.parametrize('language,result_language',[('vi','vi'),('en','en'),('auto','vi'),('auto','en')])
async def test_general_requests_native_positive_timing_and_actual_language(tmp_path,language,result_language):
    before=assemblyai_profile_sha256(assemblyai_asr_profile())
    result,transport,provider=await execute(tmp_path,language,result_language)
    request=transport.calls[1]
    assert request==studio_request(studio_profile(language),'https://cdn.assemblyai.com/studio-asr-fixture.wav')
    assert 'prompt' not in request and 'keyterms_prompt' not in request
    assert ('language_code' in request) != ('language_detection' in request)
    assert result.language==result_language and result.segments[0].words[1].start_seconds==.25
    assert result.provenance['profile_sha256']==studio_profile_sha256(studio_profile(language))
    assert result.provenance['estimated_cost_vnd'] is None and result.actual_cost_vnd is None
    assert before==assemblyai_profile_sha256(assemblyai_asr_profile())
    with pytest.raises(ValueError,match='ALREADY_DISPATCHED'):
        await provider.transcribe(tmp_path/'synthetic-provider-payload.wav',metadata=MediaMetadata(media_kind='audio',detected_content_type='audio/wav',duration_seconds=1.),checksum_sha256='a'*64)


@pytest.mark.asyncio
@pytest.mark.parametrize('language,result_language,changes,code',[
    ('vi','en',{},'LANGUAGE_MISMATCH'),('auto','fr',{},'LANGUAGE_MISMATCH'),
    ('en','en',{'speech_model_used':'universal-2'},'NO_FALLBACK'),
    ('en','en',{'words':[{'text':'Hello','start':1,'end':1}]},'INTERVAL_INVALID'),
    ('en','en',{'text':'Invented missing words.'},'COVERAGE_INVALID'),
])
async def test_provider_language_model_timing_and_text_are_never_fabricated(tmp_path,language,result_language,changes,code):
    with pytest.raises(ValueError,match=code):await execute(tmp_path,language,result_language,result_changes=changes)


def test_profile_and_runtime_tampering_are_rejected_before_credential_read(tmp_path):
    profile=studio_profile('en').model_dump(mode='json');profile['prompt']='reference transcript'
    with pytest.raises(ValueError):AssemblyAIStudioTranscriptionProvider(profile=profile,credential_resolver=lambda _:None)
    with pytest.raises(ValueError):studio_profile('fr')
    with pytest.raises(ValueError):AssemblyAIStudioTranscriptionProvider(profile=studio_profile('en'),credential_resolver=lambda _:None,vnd_per_minute=Decimal('NaN'))


@pytest.mark.asyncio
async def test_mutated_runtime_language_is_rejected_before_any_credential_or_transport(tmp_path):
    calls=[];transport=Transport('en');provider=AssemblyAIStudioTranscriptionProvider(profile=studio_profile('en'),
        credential_resolver=lambda alias:calls.append(alias),transport=transport)
    path=tmp_path/'mock.wav';path.write_bytes(b'explicit fixture');provider.language='vi'
    with pytest.raises(ValueError,match='CONFIGURATION_CHANGED'):
        await provider.transcribe(path,metadata=MediaMetadata(media_kind='audio',detected_content_type='audio/wav',duration_seconds=1.),
            checksum_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert calls==[] and transport.calls==[]
