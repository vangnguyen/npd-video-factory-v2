"""Native requests select owned references; no client URI, graph or provider result."""
from typing import Literal,Annotated
from pydantic import Field,StrictBool,StrictInt,model_validator,field_validator
from . import ingestion
from app.models import StrictModel


class GenerationReference(StrictModel):
    asset_id:str=Field(pattern=r'^[a-f0-9]{32}\.(jpg|png)$')
    asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


class CommonParameters(StrictModel):
    prompt:str=Field(min_length=1,max_length=4000,pattern=r'\S')
    negative_prompt:str=Field(default='',max_length=2000)
    aspect_ratio:Literal['9:16','16:9','1:1','4:5']='9:16'
    seed:StrictInt=Field(default=1,ge=0,le=2_147_483_647)
    references:list[GenerationReference]=Field(default_factory=list,max_length=10)


class NativeImageParameters(CommonParameters):
    modality:Literal['image']='image'
    operation:Literal['generate','image_to_image','variation','inpaint','upscale']='generate'
    style:str=Field(default='cinematic',min_length=1,max_length=160)
    quality:Literal['draft','standard','high']='draft'
    mask:GenerationReference|None=None
    upscale_factor:Literal[2,4]|None=None

    @field_validator('upscale_factor',mode='before')
    @classmethod
    def exact_scale(cls,value):
        if value is not None and type(value) is not int:raise ValueError('GENERATION_SCALE_INVALID')
        return value

    @model_validator(mode='after')
    def references_required(self):
        if self.operation!='generate' and not self.references:raise ValueError('GENERATION_REFERENCE_REQUIRED')
        if (self.operation=='inpaint')!=(self.mask is not None):raise ValueError('GENERATION_MASK_OPERATION_MISMATCH')
        if self.operation!='upscale' and self.upscale_factor is not None:raise ValueError('GENERATION_SCALE_OPERATION_MISMATCH')
        if self.operation=='upscale' and self.upscale_factor is None:self.upscale_factor=2
        return self


class NativeVideoParameters(CommonParameters):
    modality:Literal['video']='video'
    mode:Literal['text_to_video','image_to_video','reference_assisted']='text_to_video'
    duration_seconds:float=Field(default=5,gt=0,le=30,allow_inf_nan=False,strict=True)

    @model_validator(mode='after')
    def references_required(self):
        if self.mode!='text_to_video' and not self.references:raise ValueError('GENERATION_REFERENCE_REQUIRED')
        return self


class GenerationCreate(StrictModel):
    revision:StrictInt=Field(ge=1)
    parameters:Annotated[NativeImageParameters|NativeVideoParameters,Field(discriminator='modality')]
    external_acknowledged:StrictBool=False
    fixture_acknowledged:StrictBool=False
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')


class GenerationAction(StrictModel):
    expected_fingerprint:str=Field(pattern=r'^[a-f0-9]{64}$')


class GenerationImport(GenerationAction):
    revision:StrictInt=Field(ge=1)
    expected_asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged:StrictBool=False
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
