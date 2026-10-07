"""Recurring intent only: no runtime activation or observed analytics."""
from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from app.analytics_refresh_models import AnalyticsRefreshCreate, AnalyticsRefreshStateChange


def payload(**changes):
    return {'publication_id': 'pub_refresh_fixture', 'first_run_at': '2026-10-08T07:00:00+07:00', **changes}


def test_plan_defaults_disable_execution_and_normalize_offset():
    plan = AnalyticsRefreshCreate.model_validate(payload())
    assert not plan.enabled and not plan.acknowledged_read_only and plan.fixture_profile == 'normal'
    assert plan.first_run_at == datetime(2026, 10, 8, tzinfo=timezone.utc)
    assert plan.interval_hours == 24 and plan.max_runs == 7 and plan.query_at(plan.first_run_at) is None


@pytest.mark.parametrize('changes', [{'enabled': True}, {'enabled': 1}, {'interval_hours': True}, {'interval_hours': '24'},
    {'interval_hours': 0}, {'max_runs': 366}, {'lookback_days': 2}, {'first_run_at': '2026-10-08T07:00:00'},
    {'provider_mode': 'official', 'fixture_profile': 'winner_candidate'}, {'provider_mode': 'official', 'include_revenue': True}])
def test_invalid_or_implicit_refresh_intent_is_rejected(changes):
    with pytest.raises(ValidationError): AnalyticsRefreshCreate.model_validate(payload(**changes))


def test_rolling_report_uses_requested_complete_utc_days_without_claiming_observed_coverage():
    plan = AnalyticsRefreshCreate.model_validate(payload(provider_mode='official', query_policy='rolling_complete_days', lookback_days=7))
    query = plan.query_at(datetime(2026, 10, 8, 1, tzinfo=timezone(timedelta(hours=7))))
    assert query == {'start_date': '2026-09-30', 'end_date': '2026-10-06', 'include_revenue': False}
    assert plan.query is None and 'coverage_end_date' not in query


def test_fixed_report_query_and_revenue_intent_are_explicit_and_stable():
    query = {'start_date': '2026-10-01', 'end_date': '2026-10-07', 'include_revenue': True}
    with pytest.raises(ValidationError):
        AnalyticsRefreshCreate.model_validate(payload(provider_mode='official', query_policy='fixed_dates', query=query))
    plan = AnalyticsRefreshCreate.model_validate(payload(provider_mode='official', query_policy='fixed_dates', query=query, include_revenue=True))
    result = plan.query_at(plan.first_run_at); result['start_date'] = '1900-01-01'
    assert plan.query_at(plan.first_run_at) == query


def test_state_change_requires_explicit_enable_ack_and_positive_revision():
    assert not AnalyticsRefreshStateChange(expected_revision=1, enabled=False).enabled
    with pytest.raises(ValidationError): AnalyticsRefreshStateChange(expected_revision=1, enabled=True)
    with pytest.raises(ValidationError): AnalyticsRefreshStateChange(expected_revision=True, enabled=False)
    assert AnalyticsRefreshStateChange(expected_revision=2, enabled=True, acknowledged_read_only=True).enabled
