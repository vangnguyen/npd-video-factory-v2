"""Reviewed source graph contracts; no client can supply these definitions."""
from typing import Literal
from pydantic import Field, StrictInt, model_validator
from .model_base import StrictModel


class GraphInputBinding(StrictModel):
    parameter: Literal['prompt', 'negative_prompt', 'seed', 'reference_images', 'mask_reference',
        'scale', 'duration_seconds', 'style', 'quality', 'aspect_ratio', 'mode', 'operation']
    node_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    input_name: str = Field(pattern=r'^[A-Za-z_][A-Za-z0-9_]{0,79}$')
    index: StrictInt | None = Field(default=None, ge=0, le=9)
    transform: Literal['identity', 'aspect_width', 'aspect_height', 'verified_reference'] = 'identity'

    @model_validator(mode='after')
    def validate_reference_binding(self):
        if self.parameter == 'reference_images' and (self.index is None or self.transform != 'verified_reference'):
            raise ValueError('REFERENCE_BINDING_REQUIRES_VERIFIED_TOKEN')
        if self.parameter == 'mask_reference' and self.transform != 'verified_reference':
            raise ValueError('MASK_BINDING_REQUIRES_VERIFIED_TOKEN')
        if self.index is not None and self.parameter != 'reference_images':
            raise ValueError('REFERENCE_INDEX_INVALID')
        if self.transform in {'aspect_width', 'aspect_height'} and self.parameter != 'aspect_ratio':
            raise ValueError('ASPECT_BINDING_INVALID')
        return self


class ReviewedGraphExecution(StrictModel):
    graph_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    approval_reference: str = Field(min_length=4, max_length=200)
    approval_kind: Literal['owner_approved', 'explicit_fixture']
    allowed_node_classes: list[str] = Field(min_length=1, max_length=200)
    bindings: list[GraphInputBinding] = Field(min_length=1, max_length=100)
    output_nodes: list[str] = Field(min_length=1, max_length=10)
    aspect_dimensions: dict[str, tuple[StrictInt, StrictInt]] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_bindings(self):
        targets = [(b.node_id, b.input_name) for b in self.bindings]
        if len(targets) != len(set(targets)) or len(self.output_nodes) != len(set(self.output_nodes)):
            raise ValueError('GRAPH_EXECUTION_BINDINGS_AMBIGUOUS')
        if any(aspect not in {'9:16', '16:9', '1:1', '4:5'} or any(not 64 <= n <= 4096 for n in dims)
                for aspect, dims in self.aspect_dimensions.items()):
            raise ValueError('APPROVED_GRAPH_DIMENSIONS_INVALID')
        return self


class VerifiedReferenceToken(StrictModel):
    workspace_id: str = Field(min_length=1, max_length=200)
    project_id: str | None = Field(default=None, min_length=1, max_length=200)
    source_reference: str = Field(min_length=1, max_length=4096)
    source_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    uploaded_filename: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,120}\.(png|jpg|jpeg)$')
    upload_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    fixture: bool
