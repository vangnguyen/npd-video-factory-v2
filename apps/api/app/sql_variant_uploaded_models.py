"""Uploaded derivative contracts; imports never represent a new provider job."""
from typing import Literal
from .sql_variant_derivation_models import DeriveStoryboardRequest,StoryboardDerivationRead
from .sql_variant_import_job import VariantEvidenceImportInput

class DeriveUploadedRequest(DeriveStoryboardRequest):
    schema_version:Literal['sql-variant-uploaded-derive.v1']='sql-variant-uploaded-derive.v1'

class UploadedDerivationRead(StoryboardDerivationRead):
    schema_version:Literal['sql-variant-uploaded-receipt.v1']='sql-variant-uploaded-receipt.v1'
