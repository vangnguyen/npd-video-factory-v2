"""Finite Owner consent for one original render; incompatible with asset consent."""
from decimal import Decimal
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator
from app.models import StrictModel
from .costs import amount


class RenderAnalyze(StrictModel):
    schema_version:Literal['native-render-vision-analyze-v1']='native-render-vision-analyze-v1'
    revision:StrictInt=Field(ge=1)
    render_job_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    profile_id:str=Field(pattern=r'^nrvp_[a-f0-9]{32}$')
    expected_configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_render_input_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_rendered_frame_analysis:Literal[True]
    acknowledged_protocol_mock:StrictBool=False
    max_operation_cost_vnd:Decimal=Field(gt=0,le=1000000000000)
    valid_for_seconds:StrictInt=Field(default=600,ge=60,le=900)
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')

    @field_validator('acknowledged_rendered_frame_analysis',mode='before')
    @classmethod
    def rendered_consent(cls,value):
        if value is not True:raise ValueError('Separate raw rendered-frame acknowledgement required')
        return value

    @field_validator('max_operation_cost_vnd',mode='before')
    @classmethod
    def explicit_money(cls,value):
        try:return amount(value)
        except Exception:raise ValueError('Explicit finite bounded VND ceiling required') from None


class RenderAction(StrictModel):
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
