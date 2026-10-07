"""Typed, response-bound provider timestamps; collection/receipt time is never a fallback."""
import hashlib
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from .models import StrictModel

VERSION = 'publication-time-evidence-v1'
PROVIDERS = {'youtube': 'youtube-analytics-api', 'tiktok': 'tiktok-video-insights-api'}


def remote_digest(remote):
    return hashlib.sha256(remote.encode()).hexdigest()


def aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('PUBLICATION_TIME_CLOCK_INVALID')
    return value.astimezone(timezone.utc)


def iso_time(value, observed):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
        return None
    try:
        parsed = aware(datetime.fromisoformat(value.replace('Z', '+00:00')))
        return parsed if datetime(1970, 1, 1, tzinfo=timezone.utc) < parsed <= aware(observed) else None
    except (ValueError, OverflowError): return None


class PublicationTimeEvidence(StrictModel):
    schema_version: Literal['publication-time-evidence-v1'] = VERSION
    platform: Literal['youtube', 'tiktok']
    provider_key: str
    publication_id: str
    remote_post_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    target_binding_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    response_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    operation: Literal['video_ownership', 'metrics']
    provider_field: Literal['snippet.publishedAt', 'create_time']
    reported_at: datetime | None
    verified_posted_at: datetime | None
    observed_at: datetime
    state: Literal['verified_provider_posted_time', 'unavailable']
    reason: Literal['provider_posted_time', 'missing_or_invalid_timestamp', 'future_timestamp',
        'youtube_upload_or_publication_semantics_ambiguous']
    basis: Literal['provider_posted_time', 'ambiguous_upload_or_publication', 'unavailable']
    timezone: Literal['UTC'] = 'UTC'
    public_exposure_time_verified: Literal[False] = False
    mock: StrictBool
    external_call: StrictBool

    @model_validator(mode='before')
    @classmethod
    def timestamp_types(cls, values):
        if isinstance(values, dict):
            for key in ('reported_at', 'verified_posted_at', 'observed_at'):
                child = values.get(key)
                if child is not None and not isinstance(child, datetime) and not (
                    isinstance(child, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', child)):
                    raise ValueError('PUBLICATION_TIME_VALUE_INVALID')
        return values

    @model_validator(mode='after')
    def coherent(self):
        if self.provider_key != PROVIDERS[self.platform] or self.external_call == self.mock:
            raise ValueError('PUBLICATION_TIME_SCOPE_INVALID')
        observed = aware(self.observed_at)
        for value in (self.reported_at, self.verified_posted_at):
            if value is not None and not datetime(1970, 1, 1, tzinfo=timezone.utc) < aware(value) <= observed:
                raise ValueError('PUBLICATION_TIME_VALUE_INVALID')
        if self.platform == 'youtube':
            if (self.operation != 'video_ownership' or self.provider_field != 'snippet.publishedAt'
                or self.verified_posted_at is not None or self.state != 'unavailable'
                or self.basis not in ('ambiguous_upload_or_publication', 'unavailable')):
                raise ValueError('PUBLICATION_TIME_SEMANTICS_INVALID')
        elif self.operation != 'metrics' or self.provider_field != 'create_time':
            raise ValueError('PUBLICATION_TIME_SEMANTICS_INVALID')
        if self.state == 'verified_provider_posted_time':
            if (self.platform != 'tiktok' or self.reported_at is None or self.reported_at != self.verified_posted_at
                or self.reason != 'provider_posted_time' or self.basis != 'provider_posted_time'):
                raise ValueError('PUBLICATION_TIME_SEMANTICS_INVALID')
        elif self.verified_posted_at is not None or self.reason == 'provider_posted_time' or self.basis == 'provider_posted_time':
            raise ValueError('PUBLICATION_TIME_SEMANTICS_INVALID')
        return self


def provider_time(*, platform, video, observed_at, publication_id, remote_id, target_sha256,
                  response_sha256, mock, external_call):
    observed_at = aware(observed_at)
    raw = (video.get('snippet') or {}).get('publishedAt') if platform == 'youtube' else video.get('create_time')
    reported = None; reason = 'missing_or_invalid_timestamp'
    if platform == 'youtube':
        reported = iso_time(raw, observed_at)
        if reported is not None: reason = 'youtube_upload_or_publication_semantics_ambiguous'
    elif type(raw) is int and 0 < raw <= 2**63 - 1:
        try:
            parsed = datetime.fromtimestamp(raw, timezone.utc)
            if parsed <= observed_at: reported = parsed; reason = 'provider_posted_time'
            else: reason = 'future_timestamp'
        except (ValueError, OverflowError, OSError): pass
    verified = reported if platform == 'tiktok' else None
    return PublicationTimeEvidence(platform=platform, provider_key=PROVIDERS[platform],
        publication_id=publication_id, remote_post_sha256=remote_digest(remote_id),
        target_binding_sha256=target_sha256, response_sha256=response_sha256,
        operation='video_ownership' if platform == 'youtube' else 'metrics',
        provider_field='snippet.publishedAt' if platform == 'youtube' else 'create_time',
        reported_at=reported, verified_posted_at=verified, observed_at=observed_at,
        state='verified_provider_posted_time' if verified else 'unavailable', reason=reason,
        basis='provider_posted_time' if verified else 'ambiguous_upload_or_publication' if reported else 'unavailable',
        mock=mock, external_call=external_call)


def bound_time(evidence, *, platform, provider_key, publication_id, remote_id, target_sha256,
               collected_at, mock, external_call, source_kind):
    """Accept only a typed timestamp bound to the exact persisted successful read observation."""
    try:
        if source_kind != 'official_api' or not isinstance(evidence, dict) or evidence.get('account_match') is not True:
            return None
        value = PublicationTimeEvidence.model_validate(evidence.get('publication_time'))
        if (value.platform != platform or value.provider_key != provider_key or value.publication_id != publication_id
            or value.remote_post_sha256 != remote_digest(remote_id) or value.target_binding_sha256 != target_sha256
            or evidence.get('target_binding_sha256') != target_sha256
            or aware(value.observed_at) != aware(collected_at) or value.mock != mock or value.external_call != external_call):
            return None
        observations = evidence.get('request_observations')
        if not isinstance(observations, list) or sum(isinstance(item, dict) and item.get('operation') == value.operation
            and item.get('status') == 200 and item.get('response_sha256') == value.response_sha256
            and item.get('mock') is mock and item.get('external_call') is external_call for item in observations) != 1:
            return None
        return value
    except (ValueError, TypeError, AttributeError): return None


def posting_window(evidence, feature, *, platform, provider_key, publication_id, remote_id,
                   target_sha256, collected_at, mock, external_call, source_kind):
    value = bound_time(evidence, platform=platform, provider_key=provider_key, publication_id=publication_id,
        remote_id=remote_id, target_sha256=target_sha256, collected_at=collected_at, mock=mock,
        external_call=external_call, source_kind=source_kind)
    if (value is None or value.verified_posted_at is None or feature.publishing_time is None
        or (feature.evidence_json or {}).get('publication_time') != value.model_dump(mode='json')
        or (feature.evidence_json or {}).get('publishing_time_source') != value.provider_field
        or (feature.evidence_json or {}).get('exact_publishing_time_available') is not True): return None
    try:
        # SQLite's DateTime columns discard UTC offsets; normalize its stored value explicitly.
        stored = feature.publishing_time
        if stored.tzinfo is None: stored = stored.replace(tzinfo=timezone.utc)
        if aware(stored) != aware(value.verified_posted_at): return None
        posted = aware(value.verified_posted_at)
        return f'UTC:{posted.strftime("%a")}:{posted.hour // 4 * 4:02d}-{posted.hour // 4 * 4 + 4:02d}:provider-posted'
    except (ValueError, TypeError, AttributeError): return None
