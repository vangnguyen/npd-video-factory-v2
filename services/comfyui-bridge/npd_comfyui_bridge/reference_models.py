"""Authenticated service assertions authorize reference use, not publication."""
from datetime import timedelta
from typing import Literal
from pydantic import AwareDatetime, Field, StrictBool, model_validator
from .model_base import StrictModel


class ReferenceAdmission(StrictModel):
    schema_version: Literal['vf-reference-admission-v1'] = 'vf-reference-admission-v1'
    workspace_id: str = Field(min_length=1, max_length=200, pattern=r'^\S+$')
    project_id: str = Field(min_length=1, max_length=200, pattern=r'^\S+$')
    asset_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,120}\.(png|jpg|jpeg)$')
    content_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    mime_type: Literal['image/png', 'image/jpeg']
    rights_status: Literal['owned', 'licensed', 'verified', 'unknown', 'restricted']
    authorization_kind: Literal['registered_rights', 'explicit_owner_override']
    rights_receipt_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    fixture: StrictBool = False

    @model_validator(mode='after')
    def binding(self):
        if (self.expires_at <= self.issued_at or self.expires_at - self.issued_at > timedelta(hours=1)
                or self.rights_status == 'restricted'
                or self.authorization_kind == 'registered_rights' and self.rights_status not in {'owned', 'licensed', 'verified'}
                or self.authorization_kind == 'explicit_owner_override' and (self.rights_status != 'unknown' or self.fixture)
                or (self.asset_id.endswith('.png')) != (self.mime_type == 'image/png')):
            raise ValueError('REFERENCE_ADMISSION_INVALID')
        return self


class ReferenceUpload(StrictModel):
    schema_version: Literal['vf-reference-upload-v1'] = 'vf-reference-upload-v1'
    workspace_id: str = Field(min_length=1, max_length=200, pattern=r'^\S+$')
    project_id: str = Field(min_length=1, max_length=200, pattern=r'^\S+$')
    reference_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    target_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    filename: str = Field(pattern=r'^vfref_[a-f0-9]{64}\.(png|jpg)$')
    content_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    state: Literal['intent', 'confirmed']
    fixture: StrictBool
    created_at: AwareDatetime
    updated_at: AwareDatetime
    estimated_cost_vnd: None = None
    actual_cost_vnd: None = None
