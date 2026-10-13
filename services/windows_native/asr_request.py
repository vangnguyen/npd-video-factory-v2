"""Freeze explicit Studio language selection without changing legacy ASR jobs."""
from typing import Literal

from .contracts import WorkflowError, digest
from .ingestion import API_ROOT
from app.models import StrictModel
from app.assemblyai_studio_profile import studio_profile, studio_profile_sha256, AssemblyAIStudioProfile


class NativeAsrRequest(StrictModel):
    language: Literal['vi', 'en', 'auto']
    provider: Literal['assemblyai','local-whisper']='assemblyai'
    model_key: Literal['base','small','phowhisper-small']|None=None


def bind(value):
    try:
        request = NativeAsrRequest.model_validate(value)
        if request.provider=='local-whisper':
            from app.local_asr_profile import profile,digest
            key=request.model_key or 'base';local=profile(request.language,key)
            saved={'language':request.language,'provider':'local-whisper'}
            if key!='base':saved['model_key']=key
            return {'request':saved,'profile':local,'profile_sha256':digest(local)}
        if request.model_key is not None:raise ValueError('ASR_PROVIDER_MODEL_MISMATCH')
        profile = studio_profile(request.language)
        return {'request': {'language':request.language},
            'profile': profile.model_dump(mode='json'), 'profile_sha256': studio_profile_sha256(profile)}
    except (ValueError, TypeError):
        raise WorkflowError('ASR_LANGUAGE_REQUEST_INVALID', 400) from None


def from_snapshot(snapshot):
    saved = snapshot.get('asr_request')
    if saved is None:
        return None
    try:
        expected = bind(saved['request'])
        if saved != expected:
            raise ValueError()
        if saved['request'].get('provider')=='local-whisper':return saved['profile']
        return AssemblyAIStudioProfile.model_validate(saved['profile'])
    except (KeyError, ValueError, TypeError, WorkflowError):
        raise WorkflowError('ASR_LANGUAGE_PROFILE_BINDING_CHANGED') from None


def from_job(job):
    profile = from_snapshot(job['snapshot'])
    if profile is not None:
        identity = digest({'project_id':job['project_id'],'revision':job['revision'],'kind':'asr'})
        expected = digest({'original_identity':identity,'asr_request':job['snapshot']['asr_request']})
        if job['kind']!='asr' or job.get('request_sha')!=expected:
            raise WorkflowError('ASR_LANGUAGE_JOB_BINDING_CHANGED')
    return profile
