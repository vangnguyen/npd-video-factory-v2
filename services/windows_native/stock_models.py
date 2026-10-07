"""Native stock requests select saved evidence; clients cannot supply URLs/licenses."""
from typing import Literal
from pydantic import Field,StrictBool,StrictInt
from . import ingestion
from app.models import StrictModel


class StockAcknowledgment(StrictModel):
    revision:StrictInt=Field(ge=1)
    external_acknowledged:StrictBool=False
    fixture_acknowledged:StrictBool=False
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')


class StockSearch(StockAcknowledgment):
    provider:Literal['pexels','pixabay']
    query:str=Field(min_length=1,max_length=200)
    media_type:Literal['image','video']='video'
    orientation:Literal['portrait','landscape','square','any']='portrait'
    limit:StrictInt=Field(default=5,ge=1,le=20)


class StockDownload(StockAcknowledgment):
    search_id:str=Field(pattern=r'^nstk_[a-f0-9]{32}$')
    candidate_id:str=Field(pattern=r'^smc_[a-f0-9]{24}$')
    expected_result_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_candidate_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


class StockAction(StrictModel):
    expected_fingerprint:str=Field(pattern=r'^[a-f0-9]{64}$')


class StockImport(StockAction):
    revision:StrictInt=Field(ge=1)
    expected_asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged:StrictBool=False
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')
