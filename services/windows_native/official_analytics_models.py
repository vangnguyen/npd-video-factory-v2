"""Explicit finite read consent, separate from publication and fixture analytics."""
from typing import Literal
from datetime import date
from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator
from . import ingestion
from app.models import StrictModel
from app.analytics_official import AnalyticsQuery


class Collect(StrictModel):
    schema_version: Literal['native-official-analytics-request-v1'] = 'native-official-analytics-request-v1'
    publication_id: str = Field(pattern=r'^nopu_[a-f0-9]{32}$')
    expected_publication_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_receipt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    account_ref: str = Field(pattern=r'^npac_[a-f0-9]{32}$')
    expected_configuration_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    query: AnalyticsQuery
    acknowledged_read_only: Literal[True]
    acknowledged_protocol_mock: StrictBool = False
    acknowledged_bounded_retries: StrictBool = False
    max_attempts: StrictInt = Field(default=1, ge=1, le=3)
    valid_for_seconds: StrictInt = Field(default=900, ge=60, le=3600)
    request_key: str = Field(min_length=16, max_length=200, pattern=r'^[A-Za-z0-9_-]+$')

    @field_validator('acknowledged_read_only', mode='before')
    @classmethod
    def explicit(cls, value):
        if value is not True:
            raise ValueError('Explicit read-only acknowledgement required')
        return value

    @field_validator('query', mode='before')
    @classmethod
    def dates(cls, value):
        if isinstance(value, AnalyticsQuery): value = value.model_dump(mode='python', warnings=False)
        if not isinstance(value, dict) or any(type(value.get(k)) not in (str, date) for k in ('start_date','end_date')):
            raise ValueError('Explicit calendar dates required')
        return value

    @model_validator(mode='after')
    def bounded(self):
        if self.max_attempts > 1 and self.acknowledged_bounded_retries is not True:
            raise ValueError('Separate bounded retry acknowledgement required')
        return self


class Cancel(StrictModel):
    expected_snapshot_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class CounterCollect(Collect):
    """An exact TikTok receipt post, with no invented reporting date interval."""
    schema_version: Literal['native-official-analytics-request-v2'] = 'native-official-analytics-request-v2'
    query: None = Field(...)
    metric_scope: Literal['cumulative_video_counters']
    remote_post_id: str = Field(pattern=r'^[1-9][0-9]{0,18}$')

    @field_validator('query', mode='before')
    @classmethod
    def dates(cls, value):
        if value is not None:
            raise ValueError('Cumulative counters have no reporting date query')
        return value

    @field_validator('remote_post_id')
    @classmethod
    def post(cls, value):
        if int(value) > 2**63 - 1:
            raise ValueError('An actual TikTok video ID is required')
        return value


def parse_collect(value):
    """Closed version dispatch; an unknown version never falls back to v1."""
    if not isinstance(value, dict):
        raise ValueError('Explicit analytics request required')
    version = value.get('schema_version', 'native-official-analytics-request-v1')
    if version == 'native-official-analytics-request-v1':
        return Collect.model_validate(value)
    if version == 'native-official-analytics-request-v2':
        return CounterCollect.model_validate(value)
    raise ValueError('Unknown analytics request version')
