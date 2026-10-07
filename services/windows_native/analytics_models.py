"""Native analytics requests remain explicit, scoped and provider-neutral."""
from datetime import datetime
from typing import Literal
from pydantic import Field, StrictBool, field_validator, model_validator
from . import ingestion
from app.models import StrictModel


class NativeAnalyticsRequest(StrictModel):
    schema_version: Literal['native-analytics-request-v1'] = 'native-analytics-request-v1'
    publication_id: str = Field(pattern=r'^npub_[a-f0-9]{32}$')
    provider_mode: Literal['fixture','official'] = 'official'
    trigger: Literal['initial','manual_refresh','scheduled_refresh'] = 'initial'
    scheduled_for: datetime | None = None
    fixture_profile: Literal['winner_candidate','normal','underperforming','insufficient_data','rate_limited'] | None = None
    fixture_acknowledged: StrictBool = False
    request_key: str = Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')

    @field_validator('scheduled_for', mode='before')
    @classmethod
    def explicit_time(cls,value):
        if value is not None:
            if not isinstance(value,(str,datetime)): raise ValueError('NATIVE_ANALYTICS_TIME_INVALID')
            try: parsed=datetime.fromisoformat(value) if isinstance(value,str) else value
            except ValueError: raise ValueError('NATIVE_ANALYTICS_TIME_INVALID') from None
            if parsed.tzinfo is None: raise ValueError('NATIVE_ANALYTICS_TIME_INVALID')
        return value

    @model_validator(mode='after')
    def bind_mode(self):
        if self.provider_mode=='fixture':
            if not self.fixture_acknowledged or self.fixture_profile is None:
                raise ValueError('NATIVE_ANALYTICS_EXPLICIT_FIXTURE_ACK_REQUIRED')
        elif self.fixture_acknowledged or self.fixture_profile is not None:
            raise ValueError('NATIVE_ANALYTICS_OFFICIAL_CANNOT_USE_FIXTURE')
        if (self.trigger=='scheduled_refresh') != (self.scheduled_for is not None):
            raise ValueError('NATIVE_ANALYTICS_SCHEDULE_TRIGGER_REQUIRED')
        return self


class NativeAnalyticsAction(StrictModel):
    expected_fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
