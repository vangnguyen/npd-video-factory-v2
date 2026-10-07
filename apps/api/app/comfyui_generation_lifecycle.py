"""Trusted server hooks for durable job observation and targeted cancellation.

Hooks never receive provider text, result bodies, prompts, references or secrets.
They do not grant provider configuration, publishing or retry authority.
"""
from copy import deepcopy
from typing import Literal
from pydantic import Field,StrictInt
from .models import StrictModel


class GenerationObservation(StrictModel):
    schema_version:Literal['comfyui-generation-observation-v1']='comfyui-generation-observation-v1'
    phase:Literal['submitted','polled','cancel_requested','cancel_response']
    provider_job_id:str=Field(pattern=r'^cui_[A-Za-z0-9_-]{1,80}$')
    workspace_id:str=Field(min_length=1,max_length=200)
    workflow_id:str=Field(pattern=r'^[a-z0-9][a-z0-9-]{2,80}$')
    workflow_version:str|None=Field(default=None,min_length=1,max_length=40)
    status:Literal['queued','running','succeeded','failed','cancelled','timed_out']
    progress:StrictInt|None=Field(default=None,ge=0,le=100)


def cancellation_requested(hook):
    if hook is None:return False
    value=hook()
    if type(value) is not bool:raise ValueError('COMFYUI_CANCEL_HOOK_INVALID')
    return value


async def observe(hook,job,phase):
    if hook is None:return
    try:
        value=GenerationObservation(phase=phase,provider_job_id=job['job_id'],workspace_id=job['workspace_id'],
            workflow_id=job['workflow_id'],workflow_version=job.get('workflow_version'),status=job['status'],progress=job.get('progress'))
    except (ValueError,KeyError,TypeError):raise ValueError('COMFYUI_JOB_OBSERVATION_INVALID') from None
    await hook(deepcopy(value.model_dump(mode='json')))
