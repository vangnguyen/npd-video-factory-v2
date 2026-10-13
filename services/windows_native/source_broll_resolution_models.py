"""Explicit Source B-roll orchestration requests; no client URI/graph/license."""
from typing import Literal
from pydantic import Field, StrictBool, model_validator
from . import ingestion
from app.models import StrictModel

HASH=r'^[a-f0-9]{64}$'
IDENTITY=r'^nbr_[a-f0-9]{32}$'

class Create(StrictModel):
    revision:int=Field(ge=1,strict=True)
    expected_timeline_version:int=Field(ge=1,strict=True)
    media_plan_id:str=Field(pattern=r'^mpl_[a-f0-9]{24}$')
    expected_plan_version:int=Field(ge=1,strict=True)
    expected_plan_sha256:str=Field(pattern=HASH)
    item_ids:list[str]=Field(min_length=1,max_length=20)
    stock_providers:list[Literal['pexels','pixabay']]=Field(default_factory=lambda:['pexels','pixabay'],max_length=2)
    fixture_acknowledged:StrictBool=False
    external_acknowledged:StrictBool=False
    seed:int=Field(default=1,ge=0,le=2147483647,strict=True)
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
    @model_validator(mode='after')
    def unique(self):
        if len(set(self.item_ids))!=len(self.item_ids) or len(set(self.stock_providers))!=len(self.stock_providers):
            raise ValueError('unique item/provider selections required')
        return self

class Step(StrictModel):
    revision:int=Field(ge=1,strict=True)
    expected_resolution_version:int=Field(ge=1,strict=True)
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')

class Apply(Step):
    expected_timeline_version:int=Field(ge=1,strict=True)
    replace_plan_clips:StrictBool=False
    acknowledged:StrictBool=False
    @model_validator(mode='after')
    def reviewed(self):
        if not self.acknowledged:raise ValueError('explicit canonical apply required')
        return self
