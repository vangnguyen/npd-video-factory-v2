"""Explicit bounded descriptive learning; no execution or provider grant."""
from typing import Literal
from pydantic import Field,StrictBool,field_validator
from . import ingestion
from app.models import StrictModel
from app.learning_models import LearningPolicy

class Create(StrictModel):
    schema_version:Literal['native-official-learning-request-v1']='native-official-learning-request-v1'
    assessment_id:str=Field(pattern=r'^nowa_[a-f0-9]{32}$')
    expected_assessment_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    policy:LearningPolicy=Field(default_factory=LearningPolicy)
    acknowledged_recommendation_only:Literal[True]
    acknowledged_protocol_mock:StrictBool=False
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('acknowledged_recommendation_only',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('Explicit recommendation-only acknowledgement required')
        return value
