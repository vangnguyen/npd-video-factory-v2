"""Versioned Owner-controlled, bounded recurring collection intent."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from .analytics_models import AnalyticsProviderMode
from .analytics_official import AnalyticsQuery
from .models import StrictModel


class AnalyticsRefreshCreate(StrictModel):
    schema_version: Literal['analytics-refresh-plan-v1'] = 'analytics-refresh-plan-v1'
    publication_id: str = Field(pattern=r'^pub_[A-Za-z0-9_-]{4,60}$')
    provider_mode: AnalyticsProviderMode = 'fixture'
    fixture_profile: Literal['normal', 'winner_candidate', 'underperforming', 'insufficient_data'] = 'normal'
    first_run_at: datetime
    interval_hours: StrictInt = Field(default=24, ge=1, le=168)
    max_runs: StrictInt = Field(default=7, ge=1, le=365)
    query_policy: Literal['cumulative', 'fixed_dates', 'rolling_complete_days'] = 'cumulative'
    query: dict | None = None
    lookback_days: StrictInt | None = Field(default=None, ge=1, le=366)
    include_revenue: StrictBool = False
    enabled: StrictBool = False
    acknowledged_read_only: StrictBool = False

    @model_validator(mode='after')
    def validate_intent(self):
        if self.first_run_at.tzinfo is None or self.first_run_at.utcoffset() is None:
            raise ValueError('first_run_at must include a timezone')
        self.first_run_at = self.first_run_at.astimezone(timezone.utc)
        if self.enabled and not self.acknowledged_read_only:
            raise ValueError('enabled refresh requires explicit read-only acknowledgment')
        if self.provider_mode == 'fixture':
            if self.query_policy != 'cumulative' or self.query is not None or self.lookback_days is not None or self.include_revenue:
                raise ValueError('fixture refresh has no real report query')
        elif self.fixture_profile != 'normal':
            raise ValueError('fixture profile applies only to fixture refresh')
        if self.query_policy == 'fixed_dates':
            if self.query is None or self.lookback_days is not None:
                raise ValueError('fixed dates require one explicit report query')
            self.query = AnalyticsQuery.model_validate(self.query).model_dump(mode='json')
            if self.include_revenue != self.query['include_revenue']:
                raise ValueError('revenue intent must match the fixed report query')
        elif self.query_policy == 'rolling_complete_days':
            if self.lookback_days is None or self.query is not None:
                raise ValueError('rolling reports require a lookback count')
        elif self.query is not None or self.lookback_days is not None or self.include_revenue:
            raise ValueError('cumulative counters do not accept a report interval')
        return self

    def query_at(self, instant):
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError('collection instant must include a timezone')
        if self.query_policy == 'fixed_dates': return dict(self.query)
        if self.query_policy == 'cumulative': return None
        end = instant.astimezone(timezone.utc).date() - timedelta(days=1)
        start = end - timedelta(days=self.lookback_days - 1)
        return AnalyticsQuery(start_date=start, end_date=end, include_revenue=self.include_revenue).model_dump(mode='json')


class AnalyticsRefreshStateChange(StrictModel):
    expected_revision: StrictInt = Field(ge=1)
    enabled: StrictBool
    acknowledged_read_only: StrictBool = False

    @model_validator(mode='after')
    def acknowledge(self):
        if self.enabled and not self.acknowledged_read_only:
            raise ValueError('enabled refresh requires explicit read-only acknowledgment')
        return self


class AnalyticsRefreshRead(StrictModel):
    schema_version: Literal['analytics-refresh-plan-v1'] = 'analytics-refresh-plan-v1'
    plan_id: str
    workspace_id: str
    project_id: str
    publication_id: str
    platform: str
    provider_key: str
    target_binding_sha256: str | None
    config: AnalyticsRefreshCreate
    revision: int
    enabled: bool
    run_count: int
    max_runs: int
    next_due_at: datetime
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    recommendation_only: Literal[True] = True
    publishing_enabled_by_plan: Literal[False] = False
