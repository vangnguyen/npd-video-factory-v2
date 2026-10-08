"""Explicit canonical family edits and scoped source-narration derivations."""
from typing import Literal
from pydantic import Field,StrictInt,model_validator
from app.models import StrictModel

ID=r'^[a-f0-9]{32}$'
SHA=r'^[a-f0-9]{64}$'
SCHEMA='native-narrated-narration-derivation-v1'


class Create(StrictModel):
    schema_version:Literal['native-narrated-variant-request-v1']='native-narrated-variant-request-v1'
    revision:StrictInt=Field(ge=1)
    expected_version:StrictInt=Field(ge=1)
    expected_prepared_reference_sha256:str=Field(pattern=SHA)
    profile_refs:list[str]=Field(min_length=1,max_length=6)
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.profile_refs))!=len(self.profile_refs) or any(not 1<=len(v)<=100 for v in self.profile_refs):
            raise ValueError('NARRATED_VARIANT_PROFILES_INVALID')
        return self


class Derivation(StrictModel):
    schema_version:Literal['native-narrated-narration-derivation-v1']=SCHEMA
    batch_id:str=Field(pattern=r'^nnvb_[a-f0-9]{32}$')
    workspace_id:str=Field(pattern=r'^wsp_[A-Za-z0-9_-]{1,100}$')
    master_project_id:str=Field(pattern=ID)
    child_project_id:str=Field(pattern=ID)
    source_project_id:str=Field(pattern=ID)
    source_narration_job_id:str=Field(pattern=ID)
    source_snapshot_sha256:str=Field(pattern=SHA)
    source_approval_sha256:str=Field(pattern=SHA)
    source_plan_sha256:str=Field(pattern=SHA)
    source_voice_sha256:str=Field(pattern=SHA)
    voice_input_sha256:str=Field(pattern=SHA)
    source_prepared_reference_sha256:str=Field(pattern=SHA)
    approval_inherited:Literal[False]=False
    rights_authority_inherited:Literal[False]=False
    new_inference_calls:Literal[0]=0
    human_review_required:Literal[True]=True
    @model_validator(mode='before')
    @classmethod
    def strict_safety_flags(cls,value):
        if isinstance(value,dict):
            for key,expected in [('approval_inherited',False),('rights_authority_inherited',False),('human_review_required',True)]:
                if key in value and value[key] is not expected:raise ValueError('Derivation safety flag must be a boolean')
            if 'new_inference_calls' in value and (type(value['new_inference_calls']) is not int or value['new_inference_calls']!=0):
                raise ValueError('Derivation does not dispatch inference')
        return value
