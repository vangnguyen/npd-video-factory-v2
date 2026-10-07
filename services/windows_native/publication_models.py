"""Native distribution intents over the shared provider-neutral publishing contract."""
from typing import Literal
from datetime import datetime
from pydantic import Field, StrictInt, field_validator
from . import ingestion  # Established provider-free API contract path in the locked Native runtime.
from app.models import StrictModel
from app.publishing_models import PublicationMetadata, PublishingPlatform


class NativePublicationCreate(StrictModel):
    schema_version: Literal['native-publication-request-v1'] = 'native-publication-request-v1'
    revision: StrictInt = Field(ge=1)
    final_job_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    platform: PublishingPlatform
    mode: Literal['dry_run'] = 'dry_run'
    metadata: PublicationMetadata
    request_key: str = Field(min_length=16, max_length=200, pattern=r'^[A-Za-z0-9_-]+$')

    @field_validator('metadata', mode='before')
    @classmethod
    def explicit_schedule(cls, value):
        scheduled = value.get('scheduled_at') if isinstance(value, dict) else getattr(value, 'scheduled_at', None)
        if scheduled is not None:
            if not isinstance(scheduled, (str, datetime)):
                raise ValueError('NATIVE_PUBLICATION_TIME_INVALID')
            try: parsed = datetime.fromisoformat(scheduled) if isinstance(scheduled, str) else scheduled
            except ValueError: raise ValueError('NATIVE_PUBLICATION_TIME_INVALID') from None
            if parsed.tzinfo is None: raise ValueError('NATIVE_PUBLICATION_TIME_INVALID')
        return value


class NativePublishApproval(StrictModel):
    expected_fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_artifact_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged: Literal[True]

    @field_validator('acknowledged', mode='before')
    @classmethod
    def explicit_ack(cls, value):
        if value is not True: raise ValueError('NATIVE_PUBLISH_REVIEW_REQUIRED')
        return value


class NativePublicationAction(StrictModel):
    expected_fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
