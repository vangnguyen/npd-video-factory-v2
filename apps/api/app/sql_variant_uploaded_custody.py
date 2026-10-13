"""Typed READY derivative custody, distinct from an original UploadSession.

The current child bytes are staged and verified by existing bounded consumers.
This SQL hook proves immutable import lineage and inherited historical scanning;
it never claims another upload, scan, inference, approval, license or paid call.
"""
from sqlalchemy import select
from .auto_edit_db import UploadSessionORM
from .auto_edit_models import MediaMetadata
from .db import AssetORM
from .sql_variant_db import SqlVariantFamilyORM, SqlVariantMemberORM, SqlVariantArtifactReceiptORM
from .sql_variant_models import digest
from .sql_variant_repository import record_value
from .sql_variant_uploaded_repository import KIND, validate_input, validate_completed

async def trusted_derivative_source(session,project,asset):
    if asset.provenance.get('source_type')!='verified_variant_derivative':
        raise ValueError('SQL_VARIANT_DERIVATIVE_SOURCE_REQUIRED')
    receipt=await session.get(SqlVariantArtifactReceiptORM,asset.provenance.get('derivation_receipt_id',''))
    if (receipt is None or receipt.kind!=KIND or receipt.state!='ready' or receipt.workspace_id!=project.workspace_id
        or receipt.result_json is None or digest(receipt.result_json)!=receipt.result_sha256
        or receipt.result_json.get('child_project_id')!=project.project_id):
        raise ValueError('SQL_VARIANT_DERIVATIVE_RECEIPT_CHANGED')
    family=await session.get(SqlVariantFamilyORM,receipt.family_id)
    members=(await session.scalars(select(SqlVariantMemberORM).where(SqlVariantMemberORM.family_id==receipt.family_id))).all()
    if family is None or family.workspace_id!=project.workspace_id:raise ValueError('SQL_VARIANT_DERIVATIVE_RECEIPT_CHANGED')
    try:
        validate_input(receipt,family,members)
        await validate_completed(session,receipt)
        old=next(old for old,new in receipt.result_json['asset_map'].items() if new==asset.asset_id)
        original=receipt.input_json['source_assets'][old];frozen=receipt.input_json['source_uploads'][old]
        upload=await session.get(UploadSessionORM,frozen['upload_id'])
        parent=await session.get(AssetORM,old)
        if (upload is None or record_value(upload)!=frozen or parent is None
            or (parent.workspace_id,parent.project_id,parent.checksum_sha256,parent.size_bytes,parent.content_type,parent.provenance.get('media_metadata'))
            !=(project.workspace_id,receipt.input_json['master_project_id'],original['checksum_sha256'],original['size_bytes'],original['content_type'],original['provenance'].get('media_metadata'))
            or asset.project_id!=project.project_id or asset.asset_class!='source' or asset.kind not in {'audio','video'}
            or asset.provenance.get('approval_inherited') is not False or asset.provenance.get('rights_override_inherited') is not False):
            raise ValueError('changed derivative origin')
        media=MediaMetadata.model_validate(asset.provenance['media_metadata'])
        if media.detected_content_type!=asset.content_type:raise ValueError('changed media')
        return media, {'schema_version':'sql-variant-source-custody.v1','receipt_id':receipt.receipt_id,
            'input_sha256':receipt.input_sha256,'result_sha256':receipt.result_sha256,
            'original_upload_id':frozen['upload_id'],'original_upload_sha256':digest(frozen),
            'scan_inherited_historical':True,'new_scan_claimed':False,'provider_calls':0,
            'child_asset_custody':_current_asset_custody(asset)}
    except (ValueError,KeyError,TypeError,StopIteration):
        raise ValueError('SQL_VARIANT_DERIVATIVE_CUSTODY_CHANGED') from None

def _current_asset_custody(asset):
    from .frozen_storage_read import asset_custody
    return asset_custody(asset)
