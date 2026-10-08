"""Native refresh intent reuses the provider-neutral bounded report policy."""
from datetime import datetime
from typing import Literal
from pydantic import Field, StrictBool, field_validator, model_validator
from app.analytics_refresh_models import AnalyticsRefreshCreate, AnalyticsRefreshStateChange
from app.models import StrictModel
from .channel_profiles import AnalyticsProfile


class NativeAnalyticsRefreshCreate(AnalyticsRefreshCreate):
    schema_version: Literal['native-analytics-refresh-plan-v1'] = 'native-analytics-refresh-plan-v1'
    publication_id: str = Field(pattern=r'^npub_[a-f0-9]{32}$')
    provider_mode: Literal['fixture', 'official'] = 'official'
    fixture_profile: Literal['normal', 'winner_candidate', 'underperforming', 'insufficient_data', 'rate_limited'] = 'normal'
    fixture_acknowledged: StrictBool = False
    request_key: str = Field(min_length=16, max_length=200, pattern=r'^[A-Za-z0-9_-]+$')

    @field_validator('first_run_at', mode='before')
    @classmethod
    def explicit_time(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError('NATIVE_ANALYTICS_REFRESH_TIME_INVALID')
        return value

    @model_validator(mode='after')
    def explicit_source(self):
        if (self.provider_mode == 'fixture') != self.fixture_acknowledged:
            raise ValueError('NATIVE_ANALYTICS_REFRESH_EXPLICIT_SOURCE_REQUIRED')
        return self


class NativeAnalyticsRefreshState(AnalyticsRefreshStateChange):
    fixture_acknowledged: StrictBool = False


class NativeAnalyticsRefreshTick(StrictModel):
    schema_version: Literal['native-analytics-refresh-tick-v1'] = 'native-analytics-refresh-tick-v1'


class NativeRuntimeAnalyticsProfile(StrictModel):
    schema_version: Literal['native-runtime-analytics-profile-v1'] = 'native-runtime-analytics-profile-v1'
    profile_ref: Literal['native-recorded-fixture-analytics@1', 'native-official-analytics@1']
    provider_mode: Literal['fixture', 'official']
    provider_key: str
    provider_status: Literal['EXPLICIT_FIXTURE', 'NOT_CONFIGURED']
    channel_profile_ref: str | None
    channel_selection_sha256: str | None = Field(pattern=r'^[a-f0-9]{64}$')
    channel_analytics_profile: AnalyticsProfile | None
    publication_binding_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    missing_metric_policy: Literal['null'] = 'null'
    learning_mode: Literal['recommendation_only'] = 'recommendation_only'
    external_calls_enabled: Literal[False] = False
    publishing_enabled: Literal[False] = False

    @model_validator(mode='after')
    def consistent(self):
        fixture = self.provider_mode == 'fixture'
        if self.profile_ref != ('native-recorded-fixture-analytics@1' if fixture else 'native-official-analytics@1'):
            raise ValueError('NATIVE_ANALYTICS_PROFILE_SOURCE_CHANGED')
        if self.provider_status != ('EXPLICIT_FIXTURE' if fixture else 'NOT_CONFIGURED'):
            raise ValueError('NATIVE_ANALYTICS_PROFILE_STATUS_CHANGED')
        if any(v is not None for v in (self.channel_profile_ref, self.channel_selection_sha256, self.channel_analytics_profile)) != all(
            v is not None for v in (self.channel_profile_ref, self.channel_selection_sha256, self.channel_analytics_profile)):
            raise ValueError('NATIVE_ANALYTICS_PROFILE_CHANNEL_CHANGED')
        return self
