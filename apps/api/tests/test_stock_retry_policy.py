"""Pure scheduling observations; no provider request, credential or database."""
from email.utils import formatdate
import math
import pytest

from app.stock_retry_policy import MAX_COOLDOWN_SECONDS, retry_delay, wire_backoff

NOW = 1_800_000_000.25


@pytest.mark.parametrize(('headers', 'expected'), [
    ({'Retry-After': '60'}, 60),
    ({'retry-after': ' 60 '}, 60),
    ({'Retry-After': '0'}, 0),
    ({'Retry-After': formatdate(NOW + 90, usegmt=True)}, 89.75),
    ({'Retry-After': formatdate(NOW - 90, usegmt=True)}, 0),
    ({'X-RateLimit-Reset': str(int(NOW) + 600)}, 599.75),
    ({'Retry-After': '60', 'X-RateLimit-Reset': str(int(NOW) + 600)}, 60),
    ({'Retry-After': 'invalid', 'X-RateLimit-Reset': str(int(NOW) + 600)}, 599.75),
    ({'Retry-After': '-1'}, 5),
    ({'Retry-After': 'NaN'}, 5),
    ({'Retry-After': 60}, 5),
    ({'Retry-After': '9' * 200}, 5),
    ({'Retry-After': str(MAX_COOLDOWN_SECONDS + 1)}, MAX_COOLDOWN_SECONDS),
    ({}, 5),
])
def test_retry_seconds_dates_unix_resets_and_invalid_inputs_are_explicit(headers, expected):
    assert retry_delay(headers, NOW) == expected


def test_monthly_success_quota_zero_is_exact_and_different_from_health_or_cdn():
    reset = int(NOW) + 31 * 86400
    headers = {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(reset)}
    observed = wire_backoff(200, headers, NOW, 'api')
    assert observed.remaining == 0
    assert observed.reset_epoch == reset == observed.blocked_until
    assert observed.delay_seconds == reset - NOW
    assert observed.basis == 'successful_api_quota_exhaustion'
    assert wire_backoff(200, headers, NOW, 'cdn') is None
    assert wire_backoff(200, {}, NOW, 'api') is None
    assert not hasattr(observed, 'healthy') and not hasattr(observed, 'billed_cost')


@pytest.mark.parametrize('headers', [
    {'X-RateLimit-Remaining': '0'},
    {'X-RateLimit-Reset': str(int(NOW) + 600)},
    {'X-RateLimit-Remaining': '1', 'X-RateLimit-Reset': str(int(NOW) + 600)},
    {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(int(NOW) - 1)},
    {'X-RateLimit-Remaining': True, 'X-RateLimit-Reset': str(int(NOW) + 600)},
    {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': 'NaN'},
    {'X-RateLimit-Remaining': '0', 'X-RateLimit-Reset': str(int(NOW) + MAX_COOLDOWN_SECONDS + 1)},
])
def test_success_without_valid_future_zero_quota_is_not_backoff(headers):
    assert wire_backoff(200, headers, NOW, 'api') is None


def test_retryable_wire_response_only_uses_observed_allowed_status_and_headers():
    observed = wire_backoff(429, {}, NOW, 'api')
    assert observed.delay_seconds == 5 and observed.remaining is None and observed.reset_epoch is None
    assert wire_backoff(503, {}, NOW, 'api') is None
    assert wire_backoff(503, {'Retry-After': '60'}, NOW, 'cdn').delay_seconds == 60
    assert wire_backoff(404, {'Retry-After': '60'}, NOW, 'api') is None


@pytest.mark.parametrize('value', [True, -1, math.nan, math.inf, '1800000000'])
def test_invalid_clock_does_not_create_a_provider_reset(value):
    with pytest.raises(ValueError, match='STOCK_RETRY_CLOCK_INVALID'):
        retry_delay({'Retry-After': '60'}, value)
