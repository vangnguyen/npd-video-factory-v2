"""Explicit master-narration custody; it grants no child review/rights authority."""
from typing import Literal
from pydantic import Field
from .sql_variant_models import Contract, FamilyVersionRequest
from .production_models import VoiceConfig

SHA = r'^[a-f0-9]{64}$'


class NarrationReuseRequest(FamilyVersionRequest):
    schema_version: Literal['sql-variant-narration-request.v1'] = 'sql-variant-narration-request.v1'
    enabled: bool = False
    member_id: str = Field(pattern=r'^vfm_[a-f0-9]{32}$')
    child_project_id: str = Field(pattern=r'^prj_[A-Za-z0-9_-]{4,60}$')
    expected_child_content_version_id: str = Field(min_length=1,max_length=64)
    expected_child_timeline_version_id: str = Field(min_length=1,max_length=64)
    expected_child_timeline_version: int = Field(ge=1)
    source_review_render_id: str = Field(min_length=1,max_length=64)
    source_approval_id: str = Field(min_length=1,max_length=64)
    expected_source_manifest_sha256: str = Field(pattern=SHA)
    expected_semantic_sha256: str = Field(pattern=SHA)
    # Exact approved provider profile includes voice/locale/style/SDK/parameters.
    expected_profile_sha256s: list[str] = Field(min_length=1,max_length=300)
    expected_normalization_sha256s: list[str] = Field(min_length=1,max_length=300)
    voice_config: VoiceConfig
    acknowledge_fresh_child_review: Literal[True]


class NarrationReuseRead(Contract):
    schema_version: Literal['sql-variant-narration-receipt.v1'] = 'sql-variant-narration-receipt.v1'
    receipt_id: str | None
    family_id: str
    member_id: str
    workspace_id: str
    child_project_id: str
    state: Literal['disabled','pending','ready','unknown','cancelled']
    input_sha256: str | None = None
    result_sha256: str | None = None
    result: dict | None = None
    error_code: str | None = None
    actor_ref: str
    human_review_required: Literal[True] = True
    approval_transferred: Literal[False] = False
    rights_authority_transferred: Literal[False] = False
    publishing_enabled: Literal[False] = False
    owner_uat_accepted: Literal[False] = False
    new_inferences: Literal[0] = 0
    provider_calls: Literal[0] = 0


class VariantNarrationRenderProof(Contract):
    schema_version: Literal['sql-variant-narration-render-proof.v1'] = 'sql-variant-narration-render-proof.v1'
    receipt_id: str = Field(min_length=1,max_length=64)
    family_id: str = Field(min_length=1,max_length=64)
    member_id: str = Field(min_length=1,max_length=64)
    workspace_id: str = Field(min_length=1,max_length=64)
    master_project_id: str = Field(min_length=1,max_length=64)
    child_project_id: str = Field(min_length=1,max_length=64)
    input_sha256: str = Field(pattern=SHA)
    result_sha256: str = Field(pattern=SHA)
    canonical_audio_binding_sha256: str = Field(pattern=SHA)
    source_approval_transferred: Literal[False] = False
    human_review_required: Literal[True] = True
    publishing_enabled: Literal[False] = False
