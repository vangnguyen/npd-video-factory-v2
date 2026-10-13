"""Independent zero-dispatch job input (safe for the shared JobRecord union)."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator

class VariantEvidenceImportInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['variant_evidence_import']='variant_evidence_import'
    audio_id:str=Field(pattern=r'^aud_[a-f0-9]{24}$')
    receipt_id:str=Field(pattern=r'^vfr_[a-f0-9]{32}$')
    source_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    input_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    actor_ref:str=Field(min_length=1,max_length=160)
    provider_calls:Literal[0]=0

    @model_validator(mode='before')
    @classmethod
    def zero_calls(cls,value):
        if isinstance(value,dict) and ('provider_calls' in value and type(value['provider_calls'])is not int):
            raise ValueError('SQL_VARIANT_IMPORT_CALL_COUNT_INVALID')
        return value
