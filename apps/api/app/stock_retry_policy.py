"""Typed stock wire observations shared by SQL and Native, without IO/imports.

Quota headers are observations about scheduling, never billing, remaining
credits, independent rights, provider health, or real-provider acceptance.
"""
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
import math

MAX_COOLDOWN_SECONDS = 366 * 86400
DEFAULT_RETRY_SECONDS = 5.0


def _clock(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('STOCK_RETRY_CLOCK_INVALID')
    return float(value)


def _header(headers, name):
    if headers is None:
        return None
    value = headers.get(name)
    if value is None:
        value = headers.get(name.lower())
    return value.strip() if isinstance(value, str) and len(value) <= 128 else None


def retry_delay(headers, observed_at):
    """Prefer Retry-After seconds/date; reset headers contain UNIX timestamps."""
    stamp = _clock(observed_at)
    value = _header(headers, 'Retry-After')
    if value:
        if value.isascii() and value.isdigit():
            return float(min(MAX_COOLDOWN_SECONDS, int(value)))
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is not None:
                return min(MAX_COOLDOWN_SECONDS, max(0.0, date.timestamp() - stamp))
        except (TypeError, ValueError, OverflowError):
            pass
    reset = _header(headers, 'X-RateLimit-Reset')
    if reset and reset.isascii() and reset.isdigit():
        return float(min(MAX_COOLDOWN_SECONDS, max(0, int(reset) - stamp)))
    return DEFAULT_RETRY_SECONDS


@dataclass(frozen=True)
class StockWireBackoff:
    observed_at: float
    blocked_until: float
    delay_seconds: float
    status_code: int
    basis: str
    remaining: int | None = None
    reset_epoch: float | None = None


def wire_backoff(status_code, headers, observed_at, request_class):
    """Return only validated backoff evidence; unavailable metrics stay absent."""
    stamp = _clock(observed_at)
    if type(status_code) is not int or not 100 <= status_code <= 599:
        raise ValueError('STOCK_RETRY_STATUS_INVALID')
    if request_class not in {'api', 'cdn'}:
        raise ValueError('STOCK_RETRY_REQUEST_CLASS_INVALID')
    remaining = _header(headers, 'X-RateLimit-Remaining')
    reset = _header(headers, 'X-RateLimit-Reset')
    if request_class == 'api' and 200 <= status_code < 300 and remaining and reset:
        if len(remaining) <= 32 and remaining.isascii() and remaining.isdigit() and int(remaining) == 0 \
                and len(reset) <= 32 and reset.isascii() and reset.isdigit():
            epoch = int(reset)
            if stamp < epoch <= stamp + MAX_COOLDOWN_SECONDS:
                return StockWireBackoff(stamp, float(epoch), float(epoch - stamp), status_code,
                    'successful_api_quota_exhaustion', remaining=0, reset_epoch=float(epoch))
    if status_code == 429 or status_code in {500, 502, 503, 504} \
            and (_header(headers, 'Retry-After') or reset):
        delay = retry_delay(headers, stamp)
        return StockWireBackoff(stamp, stamp + delay, delay, status_code, 'retryable_wire_response')
    return None
